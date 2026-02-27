"""Custom tools for the Deep Research system."""

import json
from crewai.tools import tool


@tool("claim_validator")
def claim_validator(claims_json: str) -> str:
    """
    Validates a list of research claims by checking source quality.

    Takes a JSON string of claims, each with 'claim', 'source_url',
    and 'confidence' fields. Returns a validation assessment.

    Input format:
    [
        {"claim": "Envelio has 50+ customers", "source_url": "https://...", "confidence": "high"},
        {"claim": "Founded in 2017", "source_url": "", "confidence": "low"}
    ]
    """
    try:
        claims = json.loads(claims_json)
    except json.JSONDecodeError:
        return "ERROR: Invalid JSON. Please provide a valid JSON array of claims."

    results = []
    for c in claims:
        status = "✅ SOURCED" if c.get("source_url") else "⚠️ UNSOURCED"
        conf = c.get("confidence", "unknown")
        results.append(
            f"{status} [{conf}] {c.get('claim', 'N/A')}\n"
            f"   Source: {c.get('source_url', 'NONE — needs verification')}"
        )

    sourced = sum(1 for c in claims if c.get("source_url"))
    summary = (
        f"\n{'='*60}\n"
        f"VALIDATION SUMMARY\n"
        f"{'='*60}\n"
        f"Total claims: {len(claims)}\n"
        f"Sourced: {sourced}\n"
        f"Unsourced: {len(claims) - sourced}\n"
        f"{'='*60}\n\n"
    )

    return summary + "\n\n".join(results)
