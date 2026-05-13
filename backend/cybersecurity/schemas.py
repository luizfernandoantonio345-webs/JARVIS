"""
JARVIS CyberSec Schemas v2.0

Pydantic models for cybersecurity operations: recon, exploit, post-exploit,
defense, incident response.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field


class SeverityLevel(str, Enum):
    critical = "critical"
    high     = "high"
    medium   = "medium"
    low      = "low"
    info     = "info"


class CVSSScore(BaseModel):
    """CVSS v3.1 score details."""
    base_score:        float  = Field(default=0.0, ge=0.0, le=10.0)
    vector_string:     str    = Field(default="")
    severity:          SeverityLevel = Field(default=SeverityLevel.info)
    exploitability:    float  = Field(default=0.0)
    impact:            float  = Field(default=0.0)


class TargetInput(BaseModel):
    """Target specification for cyber operations."""
    target:            str    = Field(..., description="IP, hostname, CIDR, or URL")
    ports:             Optional[str]  = Field(default=None, description="Port range, e.g. '1-1024' or '80,443'")
    depth:             int    = Field(default=1, ge=1, le=5, description="Scan depth 1-5")
    stealth:           bool   = Field(default=True, description="Use stealth mode")
    timeout:           int    = Field(default=30, description="Timeout per check in seconds")
    tags:              List[str] = Field(default_factory=list, description="Optional labels")
    extra:             Dict[str, Any] = Field(default_factory=dict)


class CyberCommand(BaseModel):
    """A parsed cybersecurity command from natural language."""
    action:            str    = Field(..., description="One of: scan, recon, exploit, defend, incident, dfir")
    target:            Optional[str]  = Field(default=None)
    options:           Dict[str, Any] = Field(default_factory=dict)
    raw_input:         str    = Field(default="")
    confidence:        float  = Field(default=1.0, ge=0.0, le=1.0)


class Vulnerability(BaseModel):
    """Single vulnerability finding."""
    cve_id:            Optional[str] = Field(default=None)
    title:             str           = Field(default="Unknown")
    severity:          SeverityLevel = Field(default=SeverityLevel.info)
    cvss:              Optional[CVSSScore] = Field(default=None)
    description:       str           = Field(default="")
    affected:          str           = Field(default="")
    recommendation:    str           = Field(default="")
    references:        List[str]     = Field(default_factory=list)


class ScanResult(BaseModel):
    """Result of a network/vulnerability scan."""
    target:            str
    scan_type:         str           = Field(default="basic")
    open_ports:        List[int]     = Field(default_factory=list)
    services:          Dict[int, str] = Field(default_factory=dict)
    os_detected:       Optional[str] = Field(default=None)
    vulnerabilities:   List[Vulnerability] = Field(default_factory=list)
    risk_score:        float         = Field(default=0.0, ge=0.0, le=10.0)
    summary:           str           = Field(default="")
    raw_output:        str           = Field(default="")
    error:             Optional[str] = Field(default=None)

    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == SeverityLevel.critical)

    @property
    def high_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == SeverityLevel.high)


class ExploitResult(BaseModel):
    """Result of an exploitation attempt (authorized pen-test only)."""
    target:            str
    exploit_name:      str
    success:           bool          = Field(default=False)
    session_type:      Optional[str] = Field(default=None, description="shell, meterpreter, etc.")
    output:            str           = Field(default="")
    error:             Optional[str] = Field(default=None)
    cvss:              Optional[CVSSScore] = Field(default=None)


class PostExploitResult(BaseModel):
    """Result of post-exploitation activities."""
    target:            str
    actions_taken:     List[str]     = Field(default_factory=list)
    artifacts_found:   List[str]     = Field(default_factory=list)
    lateral_movement:  List[str]     = Field(default_factory=list)
    persistence:       List[str]     = Field(default_factory=list)
    output:            str           = Field(default="")
    error:             Optional[str] = Field(default=None)


class DefenseResult(BaseModel):
    """Result of a defensive security action."""
    action:            str
    target:            str
    applied:           bool          = Field(default=False)
    rules_added:       List[str]     = Field(default_factory=list)
    rules_removed:     List[str]     = Field(default_factory=list)
    hardening_score:   float         = Field(default=0.0, ge=0.0, le=10.0)
    recommendations:   List[str]     = Field(default_factory=list)
    output:            str           = Field(default="")
    error:             Optional[str] = Field(default=None)


class IncidentResult(BaseModel):
    """Result of a DFIR (Digital Forensics & Incident Response) operation."""
    incident_id:       str
    severity:          SeverityLevel = Field(default=SeverityLevel.medium)
    indicators:        List[str]     = Field(default_factory=list, description="IOCs found")
    timeline:          List[Dict[str, Any]] = Field(default_factory=list)
    affected_systems:  List[str]     = Field(default_factory=list)
    containment_steps: List[str]     = Field(default_factory=list)
    remediation_steps: List[str]     = Field(default_factory=list)
    output:            str           = Field(default="")
    error:             Optional[str] = Field(default=None)
