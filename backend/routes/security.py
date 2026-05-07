"""
/security routes — direct access to the security engine.

POST /security/scan      → static code scan (no LLM, instant)
POST /security/probe     → local endpoint HTTP probe
POST /security/full-scan → static scan + LLM security agent analysis
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.security_engine import scan_code, scan_file, probe_endpoint
from services.agent_registry import get_agent

log = logging.getLogger(__name__)
router = APIRouter()


# ── Models ─────────────────────────────────────────────────────────────────────

class CodeScanRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=200_000)
    filename: str = Field(default="<input>", max_length=256)


class FileScanRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=1024)


class ProbeRequest(BaseModel):
    url: str = Field(..., min_length=7, max_length=512)
    methods: list[str] = Field(default=["GET", "HEAD"])


class FullScanRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=200_000)
    filename: str = Field(default="<input>", max_length=256)
    session_id: str = Field(default="security-session")


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/scan", summary="Static code vulnerability scan (no LLM)")
def static_scan(body: CodeScanRequest):
    """
    Run the static security engine on a code snippet.
    Fast — no LLM involved. Returns structured findings.
    """
    result = scan_code(body.code, filename=body.filename)
    return {
        "target":   result.target,
        "count":    len(result.vulnerabilities),
        "critical": result.critical_count,
        "high":     result.high_count,
        "findings": [
            {
                "title":    v.title,
                "category": v.category,
                "severity": v.severity.value,
                "location": v.location,
                "snippet":  v.code_snippet[:200],
                "fix":      v.fix,
                "owasp":    v.owasp_ref,
            }
            for v in result.vulnerabilities
        ],
        "summary":  result.summary(),
    }


@router.post("/scan-file", summary="Static scan of a file on disk")
def static_scan_file(body: FileScanRequest):
    """
    Scan a file path on the server for vulnerabilities.
    Only files within the workspace are accessible.
    """
    result = scan_file(body.path)
    return {
        "target":   result.target,
        "count":    len(result.vulnerabilities),
        "critical": result.critical_count,
        "high":     result.high_count,
        "summary":  result.summary(),
    }


@router.post("/probe", summary="Probe a local HTTP endpoint for security headers")
def probe_local_endpoint(body: ProbeRequest):
    """
    Send safe, non-destructive HTTP probes to a LOCAL endpoint.
    Only localhost / 127.0.0.1 / ::1 are allowed.
    """
    try:
        result = probe_endpoint(body.url, methods=body.methods)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Probe failed: {exc}")
    return result


@router.post("/full-scan", summary="Static scan + AI security agent analysis")
def full_scan(body: FullScanRequest):
    """
    Run the static engine first, then invoke the Security Agent LLM
    for deeper analysis, fix explanations, and context.
    """
    agent = get_agent("security")

    message = (
        f"Perform a full security audit of this code (`{body.filename}`).\n\n"
        f"```\n{body.code}\n```"
    )

    try:
        result = agent.run(message=message)
    except Exception as exc:
        log.exception("[security/full-scan] agent failed")
        raise HTTPException(status_code=503, detail=f"Agent error: {exc}")

    return {
        "agent":    result.agent,
        "filename": body.filename,
        "response": result.response,
    }
