#!/usr/bin/env python3
"""
Deep Research Orchestrator Endpoint
====================================
Standalone script that can be called by any orchestrator (OpenClaw, n8n, etc.)
to run a research job and return the PDF path.

Usage:
    python orchestrate.py "Envelio"
    python orchestrate.py "ThinkLabs AI" --email max@example.com
    python orchestrate.py "§14a EnWG" --output /tmp/reports/

Exit codes:
    0 — Success (PDF path printed to stdout on last line)
    1 — Error (error message on stderr)

Integration:
    The last line of stdout is always the PDF file path on success.
    Parse it like: pdf_path=$(python orchestrate.py "Envelio" | tail -1)
"""

import sys
import os
import argparse
import subprocess
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path
from datetime import datetime


def send_email(pdf_path: str, target: str, recipient: str):
    """Send the PDF report via email using SMTP settings from env."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    sender = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_user or not smtp_pass:
        print("⚠️  SMTP not configured (set SMTP_USER, SMTP_PASS in .env). Skipping email.", file=sys.stderr)
        return False

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = f"🔍 CI Report: {target} — {datetime.now():%Y-%m-%d}"

    body = (
        f"Hi,\n\n"
        f"Your competitive intelligence report for \"{target}\" is attached.\n\n"
        f"Generated: {datetime.now():%Y-%m-%d %H:%M}\n"
        f"System: Deep Research Multi-Agent Pipeline\n\n"
        f"Best,\nDeep Research Bot"
    )
    msg.attach(MIMEText(body, "plain"))

    # Attach PDF
    with open(pdf_path, "rb") as f:
        part = MIMEBase("application", "pdf")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        f"attachment; filename={Path(pdf_path).name}",
    )
    msg.attach(part)

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print(f"📧 Email sent to {recipient}")
        return True
    except Exception as e:
        print(f"❌ Email failed: {e}", file=sys.stderr)
        return False


def run_research(target: str, output_dir: str = None) -> str:
    """
    Run the CrewAI research pipeline and generate a PDF.

    Returns the path to the generated PDF.
    """
    project_dir = Path(__file__).parent
    output_dir = Path(output_dir) if output_dir else project_dir / "output"
    output_dir.mkdir(exist_ok=True)

    # Set the target as env var so main.py picks it up
    env = os.environ.copy()
    env["RESEARCH_TARGET"] = target

    # Run the crew via uv
    print(f"🔍 Starting research: {target}", file=sys.stderr)
    result = subprocess.run(
        ["uv", "run", "run_crew"],
        cwd=str(project_dir),
        env=env,
        capture_output=False,  # Let output stream to stderr
    )

    if result.returncode != 0:
        print(f"❌ Crew failed with exit code {result.returncode}", file=sys.stderr)
        sys.exit(1)

    # Find the most recent PDF in output/
    pdfs = sorted(output_dir.glob("*.pdf"), key=os.path.getmtime, reverse=True)
    if pdfs:
        return str(pdfs[0])

    # Fallback: convert markdown if PDF wasn't generated
    md_files = sorted(output_dir.glob("*.md"), key=os.path.getmtime, reverse=True)
    if md_files:
        # Import here to use the project's venv
        sys.path.insert(0, str(project_dir / "src"))
        from deep_research.tools.pdf_report import markdown_to_pdf
        return markdown_to_pdf(str(md_files[0]), target)

    print("❌ No output files found", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Deep Research Orchestrator")
    parser.add_argument("target", help="Company name or topic to research")
    parser.add_argument("--email", help="Send PDF to this email address")
    parser.add_argument("--output", help="Output directory for reports")
    args = parser.parse_args()

    pdf_path = run_research(args.target, args.output)

    if args.email:
        send_email(pdf_path, args.target, args.email)

    # Last line of stdout = PDF path (for parsing by orchestrator)
    print(pdf_path)


if __name__ == "__main__":
    main()
