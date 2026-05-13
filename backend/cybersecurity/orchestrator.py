"""
JARVIS CyberSec Orchestrator v2.0

Defense-first orchestrator for cybersecurity operations.
Supports: network scanning, vulnerability assessment, defense hardening, DFIR.

All offensive capabilities require explicit authorization context.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from .schemas import (
    TargetInput, ScanResult, ExploitResult,
    PostExploitResult, DefenseResult, IncidentResult,
    CyberCommand, CVSSScore, SeverityLevel, Vulnerability,
)

log = logging.getLogger(__name__)


class CyberOrchestrator:
    """
    Routes cybersecurity commands to appropriate handlers.

    Supported actions:
      scan        → passive recon / port scan
      recon       → OSINT / passive information gathering
      defend      → apply hardening / firewall rules
      incident    → DFIR triage and containment
      report      → generate audit report
    """

    def __init__(self) -> None:
        self._session_id = str(uuid.uuid4())
        log.info("[CyberOrchestrator] Initialized session=%s", self._session_id)

    # ── Public API ─────────────────────────────────────────────────────────────

    def execute(self, command: CyberCommand) -> dict:
        """Dispatch a CyberCommand to the appropriate handler."""
        action = command.action.lower()
        log.info("[CyberOrch] action=%s target=%s", action, command.target)

        if action == "scan":
            result = self._scan(command)
            return result.model_dump()
        elif action in ("recon", "osint"):
            result = self._recon(command)
            return result.model_dump()
        elif action in ("defend", "harden", "defense"):
            result = self._defend(command)
            return result.model_dump()
        elif action in ("incident", "dfir", "triage"):
            result = self._incident(command)
            return result.model_dump()
        else:
            return {
                "error": f"Unknown action: {action}",
                "supported": ["scan", "recon", "defend", "incident"],
            }

    def scan(self, target: TargetInput) -> ScanResult:
        """Run a basic network scan against a target."""
        cmd = CyberCommand(
            action="scan",
            target=target.target,
            options=target.model_dump(exclude={"target"}),
            raw_input=f"scan {target.target}",
        )
        return self._scan(cmd)

    def defend(self, target: str, action: str = "harden") -> DefenseResult:
        """Apply defensive hardening to a target."""
        cmd = CyberCommand(action="defend", target=target, raw_input=f"{action} {target}")
        return self._defend(cmd)

    def incident_response(self, incident_id: str, target: str) -> IncidentResult:
        """Run DFIR triage for an incident."""
        cmd = CyberCommand(action="incident", target=target, raw_input=f"incident {incident_id}")
        cmd.options["incident_id"] = incident_id
        return self._incident(cmd)

    # ── Private handlers ───────────────────────────────────────────────────────

    def _scan(self, command: CyberCommand) -> ScanResult:
        """Passive / safe scan — no active exploitation."""
        target = command.target or "unknown"
        try:
            # Attempt real network probe via requests (non-invasive)
            import requests
            from backend.config import get_config
            cfg = get_config()

            # Basic HTTP probe on common ports
            open_ports: list[int] = []
            services: dict[int, str] = {}
            vulns: list[Vulnerability] = []

            for port, svc in [(80, "http"), (443, "https"), (8080, "http-alt"), (22, "ssh")]:
                try:
                    proto = "https" if port == 443 else "http"
                    resp = requests.get(f"{proto}://{target}:{port}", timeout=3, verify=False)
                    open_ports.append(port)
                    services[port] = svc
                    # Check for security headers
                    if "x-frame-options" not in resp.headers:
                        vulns.append(Vulnerability(
                            title="Missing X-Frame-Options",
                            severity=SeverityLevel.low,
                            description="X-Frame-Options header not set",
                            affected=f"{target}:{port}",
                            recommendation="Add X-Frame-Options: DENY to HTTP responses",
                        ))
                except Exception:
                    pass

            risk = min(len(vulns) * 1.5, 10.0)
            return ScanResult(
                target=target,
                scan_type="passive_http",
                open_ports=open_ports,
                services=services,
                vulnerabilities=vulns,
                risk_score=risk,
                summary=f"Found {len(open_ports)} open ports, {len(vulns)} issues on {target}",
            )
        except Exception as exc:
            log.warning("[CyberOrch._scan] failed for %s: %s", target, exc)
            return ScanResult(
                target=target,
                scan_type="failed",
                error=str(exc),
                summary=f"Scan failed: {exc}",
            )

    def _recon(self, command: CyberCommand) -> ScanResult:
        """Passive OSINT recon."""
        return ScanResult(
            target=command.target or "unknown",
            scan_type="osint",
            summary=f"Passive recon on {command.target} — no active probes performed",
        )

    def _defend(self, command: CyberCommand) -> DefenseResult:
        """Defense / hardening handler."""
        target = command.target or "localhost"
        recs = [
            "Enable firewall with default-deny policy",
            "Apply OS security patches",
            "Disable unused services and ports",
            "Enable audit logging",
            "Configure fail2ban or equivalent",
            "Use strong password policies and MFA",
        ]
        return DefenseResult(
            action=command.action,
            target=target,
            applied=False,  # Dry-run by default — safe mode
            recommendations=recs,
            hardening_score=0.0,
            output=f"[JARVIS] Defense recommendations generated for {target}. Apply manually to avoid unintended changes.",
        )

    def _incident(self, command: CyberCommand) -> IncidentResult:
        """DFIR triage handler."""
        incident_id = command.options.get("incident_id", str(uuid.uuid4()))
        target = command.target or "unknown"
        steps = [
            "Isolate affected system from network",
            "Preserve memory dump and disk image",
            "Collect running process list and network connections",
            "Review authentication logs for anomalies",
            "Check for persistence mechanisms (cron, startup, registry)",
            "Hash all suspicious files and check against threat intel",
        ]
        return IncidentResult(
            incident_id=incident_id,
            severity=SeverityLevel.high,
            affected_systems=[target],
            containment_steps=steps[:3],
            remediation_steps=steps[3:],
            output=f"[JARVIS DFIR] Incident {incident_id} triage initiated for {target}.",
        )


# ── Module-level singleton ─────────────────────────────────────────────────────

_orchestrator: Optional[CyberOrchestrator] = None


def get_cyber_orchestrator() -> CyberOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = CyberOrchestrator()
    return _orchestrator
