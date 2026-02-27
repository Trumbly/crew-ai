#!/usr/bin/env python3
"""
Deep Research — FastAPI Server
===============================
Lightweight async API that wraps orchestrate.py endpoints.

Endpoints:
    POST /research          → Start a research job (returns job_id)
    GET  /research/{id}     → Get job status + result
    GET  /research/{id}/stream → SSE stream of status updates
    GET  /research/{id}/pdf → Download PDF report
    GET  /research/{id}/md  → Download Markdown report
    GET  /jobs              → List all jobs
    DELETE /jobs/{id}       → Cancel a running job

Usage:
    uvicorn api:app --host 0.0.0.0 --port 8042 --reload

    # Start a job
    curl -X POST http://localhost:8042/research \
         -H "Content-Type: application/json" \
         -d '{"target": "Envelio", "mode": "company"}'

    # Stream status updates (SSE)
    curl -N http://localhost:8042/research/{job_id}/stream

    # Get result
    curl http://localhost:8042/research/{job_id}
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

# Load .env
load_dotenv(Path(__file__).parent / ".env")

app = FastAPI(
    title="Deep Research API",
    description="Async CI research pipeline for the German DSO market",
    version="0.1.0",
)

# ─── Models ──────────────────────────────────────────────────


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchRequest(BaseModel):
    target: str = Field(..., description="Company name or topic to research")
    mode: str = Field("company", description="Research mode: company, topic, or quick")
    email: Optional[str] = Field(
        None, description="Send PDF to this email on completion"
    )
    output_dir: Optional[str] = Field(None, description="Custom output directory")


class JobInfo(BaseModel):
    job_id: str
    target: str
    mode: str
    status: JobStatus
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    pdf_path: Optional[str] = None
    md_path: Optional[str] = None
    error: Optional[str] = None
    updates: list[str] = []


# ─── In-memory job store ─────────────────────────────────────

jobs: dict[str, JobInfo] = {}
job_events: dict[str, asyncio.Queue] = {}  # SSE queues per job


def push_update(job_id: str, message: str):
    """Push a status update to the job and its SSE queue."""
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"[{ts}] {message}"

    if job_id in jobs:
        jobs[job_id].updates.append(entry)

    if job_id in job_events:
        try:
            job_events[job_id].put_nowait(entry)
        except asyncio.QueueFull:
            pass  # drop if consumer is slow


# ─── Background worker ───────────────────────────────────────


async def run_research_job(job_id: str, request: ResearchRequest):
    """Run the CrewAI pipeline in a subprocess, capture output for status updates."""
    job = jobs[job_id]
    job.status = JobStatus.RUNNING
    job.started_at = datetime.now().isoformat()
    push_update(job_id, f"🔍 Starting {request.mode} research: {request.target}")

    project_dir = Path(__file__).parent
    output_dir = (
        Path(request.output_dir) if request.output_dir else project_dir / "output"
    )
    output_dir.mkdir(exist_ok=True)

    env = os.environ.copy()
    env["RESEARCH_TARGET"] = request.target

    process = None

    try:
        # Determine the command based on mode
        # Uses the CLI entry point from main.py
        cmd = ["uv", "run", "deep_research", request.mode, request.target]

        push_update(job_id, f"⚙️ Running: {' '.join(cmd)}")

        # Run as async subprocess so we can stream stderr
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(project_dir),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Collect recent output lines for error reporting
        from collections import deque

        stderr_buffer = deque(maxlen=50)  # last 50 lines of stderr
        stdout_buffer = deque(maxlen=50)

        # Status update keywords (for filtered SSE updates)
        STATUS_KEYWORDS = [
            "agent",
            "task",
            "tool",
            "searching",
            "research",
            "complete",
            "error",
            "fail",
            "exception",
            "traceback",
            "✅",
            "❌",
            "🔍",
            "⚡",
            "⚠",
            "working agent",
            "starting task",
            "finished",
        ]

        async def read_stream(stream, buffer, prefix=""):
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    buffer.append(text)
                    # Send meaningful lines as SSE updates
                    if any(kw in text.lower() for kw in STATUS_KEYWORDS):
                        push_update(job_id, f"{prefix}{text[:300]}")

        # Read both streams concurrently
        await asyncio.gather(
            read_stream(process.stdout, stdout_buffer, ""),
            read_stream(process.stderr, stderr_buffer, ""),
        )

        returncode = await process.wait()

        if returncode != 0:
            # Build detailed error from stderr buffer
            error_lines = list(stderr_buffer)
            # Also include stdout — CrewAI sometimes logs errors there
            error_lines += list(stdout_buffer)

            # Extract the most relevant part (last traceback + error)
            error_detail = "\n".join(error_lines[-30:])  # last 30 lines

            job.status = JobStatus.FAILED
            job.error = f"Exit code {returncode}\n\n{error_detail}"
            push_update(job_id, f"❌ Failed: exit code {returncode}")
            # Push the actual error lines so SSE consumers see them
            for line in error_lines[-15:]:
                push_update(job_id, f"📋 {line[:300]}")
        else:
            # Find outputs — search multiple possible locations
            # main.py resolves output relative to its own package location:
            #   Path(__file__).resolve().parents[2] / "output"
            # which means: <project_root>/output
            # api.py may live in a different dir, so we search broadly.

            search_dirs = []

            # 1. Configured output dir
            search_dirs.append(output_dir)

            # 2. api.py parent / output (if api.py is in project root)
            search_dirs.append(project_dir / "output")

            # 3. Resolve the actual project root from the installed package
            try:
                import deep_research

                pkg_root = Path(deep_research.__file__).resolve().parents[2] / "output"
                search_dirs.append(pkg_root)
            except Exception:
                pass

            # 4. cwd / output (subprocess runs with cwd=project_dir)
            search_dirs.append(Path.cwd() / "output")

            # Deduplicate and resolve
            search_dirs = list(dict.fromkeys(d.resolve() for d in search_dirs))

            push_update(
                job_id, f"🔎 Searching for outputs in: {[str(d) for d in search_dirs]}"
            )

            # Also parse stdout/stderr for actual file paths printed by _save_result
            # Lines look like: "📄 Report: /abs/path/to/file.md"  or  "📄 PDF:    /abs/path/to/file.pdf"
            all_output = list(stdout_buffer) + list(stderr_buffer)
            for line in all_output:
                for token in line.replace("Report:", "").replace("PDF:", "").split():
                    clean = token.strip()
                    if clean.endswith((".md", ".pdf")) and os.sep in clean:
                        candidate = Path(clean)
                        if candidate.exists():
                            if candidate.suffix == ".md" and not job.md_path:
                                job.md_path = str(candidate)
                                push_update(
                                    job_id, f"📂 Found MD via stdout: {job.md_path}"
                                )
                            elif candidate.suffix == ".pdf" and not job.pdf_path:
                                job.pdf_path = str(candidate)
                                push_update(
                                    job_id, f"📂 Found PDF via stdout: {job.pdf_path}"
                                )
                            if candidate.parent.resolve() not in search_dirs:
                                search_dirs.append(candidate.parent.resolve())

            # Search directories for most recent files (created in last 10 min)
            import time as _time

            now = _time.time()
            max_age = 600  # 10 minutes

            for search_dir in search_dirs:
                if not search_dir.exists():
                    continue

                if not job.md_path:
                    md_files = [
                        f
                        for f in search_dir.glob("*.md")
                        if (now - f.stat().st_mtime) < max_age
                    ]
                    md_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                    if md_files:
                        job.md_path = str(md_files[0])
                        push_update(
                            job_id, f"📂 Found MD in {search_dir}: {md_files[0].name}"
                        )

                if not job.pdf_path:
                    pdf_files = [
                        f
                        for f in search_dir.glob("*.pdf")
                        if (now - f.stat().st_mtime) < max_age
                    ]
                    pdf_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                    if pdf_files:
                        job.pdf_path = str(pdf_files[0])
                        push_update(
                            job_id, f"📂 Found PDF in {search_dir}: {pdf_files[0].name}"
                        )

            # Generate PDF if MD exists but PDF doesn't
            if job.md_path and not job.pdf_path:
                push_update(job_id, "📄 Generating PDF...")
                try:
                    sys.path.insert(0, str(project_dir / "src"))
                    from deep_research.tools.pdf_report import markdown_to_pdf

                    pdf_path = markdown_to_pdf(job.md_path, request.target)
                    job.pdf_path = pdf_path
                    push_update(job_id, f"📄 PDF generated: {pdf_path}")
                except Exception as e:
                    push_update(job_id, f"⚠️ PDF generation failed: {e}")

            # Final status log
            push_update(job_id, f"📂 Result → MD: {job.md_path or 'NOT FOUND'}")
            push_update(job_id, f"📂 Result → PDF: {job.pdf_path or 'NOT FOUND'}")

            # Send email if requested
            if request.email and job.pdf_path:
                push_update(job_id, f"📧 Sending email to {request.email}...")
                try:
                    from orchestrate import send_email

                    send_email(job.pdf_path, request.target, request.email)
                    push_update(job_id, f"📧 Email sent to {request.email}")
                except Exception as e:
                    push_update(job_id, f"⚠️ Email failed: {e}")

            job.status = JobStatus.COMPLETED
            push_update(job_id, "✅ Research complete")

    except asyncio.CancelledError:
        job.status = JobStatus.CANCELLED
        push_update(job_id, "🛑 Job cancelled")
        # Kill the subprocess if still running
        if process and process.returncode is None:
            process.terminate()
    except Exception as e:
        job.status = JobStatus.FAILED
        job.error = str(e)
        push_update(job_id, f"❌ Error: {e}")
    finally:
        job.completed_at = datetime.now().isoformat()
        if job.started_at:
            start = datetime.fromisoformat(job.started_at)
            end = datetime.fromisoformat(job.completed_at)
            job.elapsed_seconds = (end - start).total_seconds()

        # Signal SSE stream to close
        push_update(job_id, "__DONE__")


# ─── Active task handles for cancellation ────────────────────

running_tasks: dict[str, asyncio.Task] = {}


# ─── Endpoints ───────────────────────────────────────────────


@app.post("/research", response_model=JobInfo, status_code=202)
async def start_research(request: ResearchRequest):
    """Start a new research job. Returns immediately with a job_id."""
    if request.mode not in ("company", "topic", "quick"):
        raise HTTPException(
            400, f"Invalid mode: {request.mode}. Use: company, topic, quick"
        )

    job_id = str(uuid.uuid4())[:8]

    job = JobInfo(
        job_id=job_id,
        target=request.target,
        mode=request.mode,
        status=JobStatus.QUEUED,
        created_at=datetime.now().isoformat(),
    )

    jobs[job_id] = job
    job_events[job_id] = asyncio.Queue(maxsize=100)

    # Launch in background
    task = asyncio.create_task(run_research_job(job_id, request))
    running_tasks[job_id] = task

    return job


@app.get("/research/{job_id}", response_model=JobInfo)
async def get_job(job_id: str):
    """Get current status and result of a research job."""
    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")
    return jobs[job_id]


@app.get("/research/{job_id}/stream")
async def stream_job(job_id: str):
    """SSE stream of real-time status updates for a job."""
    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")

    async def event_generator():
        queue = job_events.get(job_id)
        if not queue:
            yield f"data: Job {job_id} has no event stream\n\n"
            return

        # Send existing updates first (replay)
        for update in jobs[job_id].updates:
            if update != "__DONE__":
                yield f"data: {update}\n\n"

        # Then stream new ones
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=300)  # 5min timeout
                if msg == "__DONE__":
                    yield f"data: [DONE]\n\n"
                    break
                yield f"data: {msg}\n\n"
            except asyncio.TimeoutError:
                yield f"data: [TIMEOUT]\n\n"
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@app.get("/jobs", response_model=list[JobInfo])
async def list_jobs():
    """List all research jobs."""
    return sorted(jobs.values(), key=lambda j: j.created_at, reverse=True)


@app.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a running research job."""
    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")

    job = jobs[job_id]
    if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise HTTPException(400, f"Job {job_id} is already {job.status}")

    # Cancel the asyncio task
    task = running_tasks.get(job_id)
    if task and not task.done():
        task.cancel()

    job.status = JobStatus.CANCELLED
    push_update(job_id, "🛑 Cancelled by user")

    return {"message": f"Job {job_id} cancelled"}


@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "ok",
        "active_jobs": sum(1 for j in jobs.values() if j.status == JobStatus.RUNNING),
        "total_jobs": len(jobs),
    }


# ─── File download endpoints ────────────────────────────────


@app.get("/research/{job_id}/pdf")
async def download_pdf(job_id: str):
    """Download the PDF report for a completed job."""
    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")

    job = jobs[job_id]
    if not job.pdf_path:
        raise HTTPException(
            404, f"No PDF available for job {job_id} (status: {job.status})"
        )

    path = Path(job.pdf_path)
    if not path.exists():
        raise HTTPException(404, f"PDF file no longer exists: {job.pdf_path}")

    return FileResponse(
        path=path,
        media_type="application/pdf",
        filename=path.name,
    )


@app.get("/research/{job_id}/md")
async def download_md(job_id: str):
    """Download the Markdown report for a completed job."""
    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")

    job = jobs[job_id]
    if not job.md_path:
        raise HTTPException(
            404, f"No Markdown report available for job {job_id} (status: {job.status})"
        )

    path = Path(job.md_path)
    if not path.exists():
        raise HTTPException(404, f"Markdown file no longer exists: {job.md_path}")

    return FileResponse(
        path=path,
        media_type="text/markdown",
        filename=path.name,
    )


# ─── Run directly ────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8042, reload=True)
