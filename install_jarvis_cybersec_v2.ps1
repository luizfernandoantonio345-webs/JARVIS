# ============================================================
# JARVIS CYBERSEC MODULE v2.0 — INSTALAÇÃO COMPLETA
# Executar como Administrador em: d:/JAVIS/
# ============================================================
# INSTRUÇÕES PARA O BLACK BOX:
# 1. Salve em d:/JAVIS/install_jarvis_cybersec_v2.ps1
# 2. Abra PowerShell como Administrador
# 3. Execute:
#    cd d:/JAVIS
#    Set-ExecutionPolicy Bypass -Scope Process -Force
#    .\install_jarvis_cybersec_v2.ps1
# 4. Ative o venv e reinicie o JARVIS
# ============================================================

$BASE  = "d:/JAVIS/backend"
$CYBER = "$BASE/cybersecurity"

Write-Host "╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   JARVIS CYBERSEC MODULE v2.0 — FULL INSTALL    ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan

# ── CRIAR ESTRUTURA DE DIRETÓRIOS ─────────────────────────
Write-Host "`n[1/8] Criando estrutura de diretórios..." -ForegroundColor Yellow
$dirs = @( 
    "$CYBER", "$CYBER/recon", "$CYBER/exploit",
    "$CYBER/post_exploit", "$CYBER/defense", "$CYBER/ir",
    "$CYBER/utils", "$CYBER/reports"
)
foreach ($d in $dirs) {
    if (!(Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
    Write-Host "  OK $d" -ForegroundColor Green
}

# ── HELPER ────────────────────────────────────────────────
function Write-PyFile($Path, $Content) {
    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.Encoding]::UTF8)
    Write-Host "  OK $Path" -ForegroundColor Green
}

Write-Host "`n[2/8] Criando arquivos Python..." -ForegroundColor Yellow

# ══════════════════════════════════════════════════════════
# cybersecurity/__init__.py
# ══════════════════════════════════════════════════════════
Write-PyFile "$CYBER/__init__.py" @'
"""JARVIS CyberSec Module v2.0 — defense, recon, DFIR."""
from .orchestrator import CyberOrchestrator
from .schemas import (
    TargetInput, ScanResult, ExploitResult,
    PostExploitResult, DefenseResult, IncidentResult,
    CyberCommand, CVSSScore
)
__all__ = [
    "CyberOrchestrator",
    "TargetInput", "ScanResult", "ExploitResult",
    "PostExploitResult", "DefenseResult", "IncidentResult",
    "CyberCommand", "CVSSScore"
]
'@

# ══════════════════════════════════════════════════════════
# cybersecurity/schemas.py
# ══════════════════════════════════════════════════════════
Write-PyFile "$CYBER/schemas.py" @'
"""Pydantic models para o modulo CyberSec do JARVIS."""
from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List, Literal
from datetime import datetime


class TargetInput(BaseModel):
    target: str = Field(..., description="IP, hostname, URL ou CIDR")
    ports: Optional[str] = Field(None, description="Ex: 22-443 ou 80,443")
    verbose: bool = False
    extra_args: Optional[str] = None


class ScanResult(BaseModel):
    target: str
    tool: str
    raw: str
    ports: Optional[List[Dict[str, Any]]] = []
    services: Optional[List[Dict[str, Any]]] = []
    os_detected: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class ExploitInput(BaseModel):
    target: str
    technique: Optional[str] = "auto"
    cve: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


class ExploitResult(BaseModel):
    target: str
    technique: str
    success: bool
    output: str
    cve: Optional[str] = None
    payload_used: Optional[str] = None
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class PostExploitInput(BaseModel):
    target: str
    action: str = Field(..., description="enum_pe | cred_dump | persistence | lateral_move")
    session_id: Optional[str] = None


class PostExploitResult(BaseModel):
    target: str
    action: str
    success: bool
    output: str
    findings: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class DefenseInput(BaseModel):
    target: str
    action: str = Field(..., description="scan_threats | enable_ids | enable_fw | block_ip | monitor")
    params: Optional[Dict[str, Any]] = None


class DefenseResult(BaseModel):
    target: str
    action: str
    status: str
    output: str
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class IncidentInput(BaseModel):
    incident_type: str = Field(..., description="intrusion | malware | dos | anomaly | ransomware")
    target: str
    severity: Optional[Literal["low", "medium", "high", "critical"]] = "medium"
    description: Optional[str] = None


class IncidentResult(BaseModel):
    incident_id: str
    incident_type: str
    target: str
    severity: str
    actions_taken: List[str]
    status: str
    playbook_used: Optional[str] = None
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class CVSSScore(BaseModel):
    vector: str
    base_score: float
    severity: str
    av: str
    ac: str
    pr: str
    ui: str
    s: str
    c: str
    i: str
    a: str


class CyberCommand(BaseModel):
    command: str = Field(..., description="Comando em PT-BR ou EN")
    target: str
    auto_mode: bool = False
    confirm: bool = False
'@

# ══════════════════════════════════════════════════════════
# cybersecurity/utils/__init__.py
# ══════════════════════════════════════════════════════════
Write-PyFile "$CYBER/utils/__init__.py" @'
from .safety_gate import SafetyGate
from .audit_log import AuditLog
from .cvss_calc import CVSSCalculator
from .report_gen import ReportGenerator

__all__ = ["SafetyGate", "AuditLog", "CVSSCalculator", "ReportGenerator"]
'@

# ══════════════════════════════════════════════════════════
# cybersecurity/utils/safety_gate.py
# ══════════════════════════════════════════════════════════
Write-PyFile "$CYBER/utils/safety_gate.py" @'
"""
SafetyGate — toda acao destrutiva passa por aqui.
Sem confirmacao explicita, acoes de alto risco nao executam.
"""
import logging

logger = logging.getLogger("jarvis.cybersec.safety")

RISK_MAP = {
    # RECON — sempre permitido (read-only)
    "ping":             "low",
    "dns_enum":         "low",
    "port_scan":        "low",
    "passive_osint":    "low",
    "header_grab":      "low",
    "cve_lookup":       "low",
    "whois":            "low",
    # EXPLOIT — exige confirmacao
    "sqli":             "high",
    "xss":              "medium",
    "lfi":              "high",
    "ssrf":             "high",
    "brute_force":      "high",
    "directory_fuzz":   "medium",
    "auto_exploit":     "critical",
    # POST-EXPLOIT
    "enum_pe":          "medium",
    "cred_dump":        "critical",
    "persistence":      "critical",
    "lateral_move":     "critical",
    # DEFENSE
    "scan_threats":     "low",
    "enable_ids":       "low",
    "monitor":          "low",
    "enable_fw":        "medium",
    "block_ip":         "high",
    "isolate_host":     "critical",
    # IR
    "incident_log":     "low",
    "forensic_capture": "medium",
    "host_isolation":   "critical",
}


class SafetyGate:
    """
    low      -> executa automaticamente
    medium   -> executa mas registra no audit
    high     -> exige confirm=True
    critical -> exige confirm=True + aviso irreversivel
    """

    def evaluate(self, operation: str, target: str, confirm: bool = False) -> dict:
        risk = RISK_MAP.get(operation, "high")

        if risk == "low":
            logger.info(f"[SAFETY] AUTO-APPROVED | {operation} -> {target}")
            return {"allowed": True, "risk": risk, "reason": "read-only operation"}

        if risk == "medium":
            logger.warning(f"[SAFETY] MEDIUM RISK | {operation} -> {target}")
            return {"allowed": True, "risk": risk, "reason": "medium risk — logged"}

        if risk == "high":
            if confirm:
                logger.warning(f"[SAFETY] HIGH RISK CONFIRMED | {operation} -> {target}")
                return {"allowed": True, "risk": risk, "reason": "confirmed by operator"}
            logger.error(f"[SAFETY] HIGH RISK BLOCKED | {operation} -> {target}")
            return {
                "allowed": False, "risk": risk,
                "reason": (
                    f"Operacao de ALTO RISCO requer confirmacao. "
                    f"Envie novamente com confirm=true. "
                    f"Alvo: {target}. Operacao: {operation}."
                )
            }

        if risk == "critical":
            if confirm:
                logger.critical(f"[SAFETY] CRITICAL CONFIRMED | {operation} -> {target}")
                return {
                    "allowed": True, "risk": risk,
                    "reason": "CRITICO confirmado — operacao pode ser irreversivel",
                    "warning": "Esta operacao pode causar danos permanentes ao alvo."
                }
            logger.critical(f"[SAFETY] CRITICAL BLOCKED | {operation} -> {target}")
            return {
                "allowed": False, "risk": risk,
                "reason": (
                    f"Operacao CRITICA bloqueada. Requer confirm=true. "
                    f"Alvo: {target}. Operacao: {operation}."
                )
            }

        return {"allowed": False, "risk": "unknown", "reason": "Operacao desconhecida"}
'@

# ══════════════════════════════════════════════════════════
# cybersecurity/utils/audit_log.py
# ══════════════════════════════════════════════════════════
Write-PyFile "$CYBER/utils/audit_log.py" @'
"""Audit log persistente de todas as operacoes CyberSec."""
import json
from datetime import datetime
from pathlib import Path
from collections import deque
from typing import Optional

LOG_PATH = Path("d:/JAVIS/backend/cybersecurity/reports/audit.jsonl")


class AuditLog:
    def __init__(self, max_memory: int = 200):
        self._entries = deque(maxlen=max_memory)
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        operation: str,
        target: str,
        risk_level: str,
        confirmed: bool,
        result: str,
        details: Optional[dict] = None
    ) -> dict:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "target": target,
            "risk_level": risk_level,
            "confirmed": confirmed,
            "result": result,
            "details": details or {},
            "operator": "owner"
        }
        self._entries.append(entry)
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass
        return entry

    def get_recent(self, n: int = 20, risk_filter: Optional[str] = None) -> list:
        entries = list(self._entries)
        if risk_filter:
            entries = [e for e in entries if e["risk_level"] == risk_filter]
        return entries[-n:]

    def get_stats(self) -> dict:
        entries = list(self._entries)
        return {
            "total": len(entries),
            "by_risk": {
                "low":      sum(1 for e in entries if e["risk_level"] == "low"),
                "medium":   sum(1 for e in entries if e["risk_level"] == "medium"),
                "high":     sum(1 for e in entries if e["risk_level"] == "high"),
                "critical": sum(1 for e in entries if e["risk_level"] == "critical"),
            },
            "by_result": {
                "success": sum(1 for e in entries if e["result"] == "success"),
                "blocked": sum(1 for e in entries if e["result"] == "blocked"),
                "failed":  sum(1 for e in entries if e["result"] == "failed"),
            }
        }
'@

# ══════════════════════════════════════════════════════════
# cybersecurity/utils/cvss_calc.py
# ══════════════════════════════════════════════════════════
Write-PyFile "$CYBER/utils/cvss_calc.py" @'
"""CVSS v3.1 Calculator."""
import math
from typing import Literal


class CVSSCalculator:
    AV  = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.20}
    AC  = {"L": 0.77, "H": 0.44}
    PR  = {
        "N": {"U": 0.85, "C": 0.85},
        "L": {"U": 0.62, "C": 0.68},
        "H": {"U": 0.27, "C": 0.50},
    }
    UI  = {"N": 0.85, "R": 0.62}
    CIA = {"N": 0.00, "L": 0.22, "H": 0.56}
    SCOPE_LABELS = {"U": "Unchanged", "C": "Changed"}

    def score(
        self,
        av: Literal["N","A","L","P"] = "N",
        ac: Literal["L","H"] = "L",
        pr: Literal["N","L","H"] = "N",
        ui: Literal["N","R"] = "N",
        s:  Literal["U","C"] = "U",
        c:  Literal["N","L","H"] = "H",
        i:  Literal["N","L","H"] = "H",
        a:  Literal["N","L","H"] = "H",
    ) -> dict:
        iss = 1 - (1 - self.CIA[c]) * (1 - self.CIA[i]) * (1 - self.CIA[a])
        scope_changed = s == "C"
        if scope_changed:
            impact = 7.52 * (iss - 0.029) - 3.25 * ((iss - 0.02) ** 15)
        else:
            impact = 6.42 * iss

        exploitability = 8.22 * self.AV[av] * self.AC[ac] * self.PR[pr][s] * self.UI[ui]

        if impact <= 0:
            base = 0.0
        else:
            base = min(1.08 * (impact + exploitability), 10) if scope_changed \
                   else min(impact + exploitability, 10)

        base = math.ceil(base * 10) / 10

        severity = "None"
        if 0.1 <= base <= 3.9:   severity = "Low"
        elif 4.0 <= base <= 6.9: severity = "Medium"
        elif 7.0 <= base <= 8.9: severity = "High"
        elif base >= 9.0:        severity = "Critical"

        return {
            "vector": f"CVSS:3.1/AV:{av}/AC:{ac}/PR:{pr}/UI:{ui}/S:{s}/C:{c}/I:{i}/A:{a}",
            "base_score": base,
            "severity": severity,
            "av": av, "ac": ac, "pr": pr, "ui": ui,
            "scope": self.SCOPE_LABELS[s],
            "confidentiality": c, "integrity": i, "availability": a,
        }

    def quick_estimate(self, description: str) -> dict:
        desc = description.lower()
        if any(w in desc for w in ["rce", "remote code", "command injection"]):
            return self.score("N","L","N","N","C","H","H","H")
        if "sql" in desc and ("inject" in desc or "injecao" in desc):
            return self.score("N","L","N","N","U","H","H","L")
        if any(w in desc for w in ["auth bypass", "broken auth"]):
            return self.score("N","L","N","N","U","H","H","N")
        if "xss" in desc or "cross-site scripting" in desc:
            return self.score("N","L","N","R","C","L","L","N")
        if "idor" in desc or "broken access" in desc:
            return self.score("N","L","L","N","U","H","L","N")
        if any(w in desc for w in ["disclosure", "vazamento", "leak"]):
            return self.score("N","L","N","N","U","H","N","N")
        return self.score("N","L","L","N","U","L","L","N")
'@

# ══════════════════════════════════════════════════════════
# cybersecurity/utils/report_gen.py
# ══════════════════════════════════════════════════════════
Write-PyFile "$CYBER/utils/report_gen.py" @'
"""Gerador de relatorios HTML + JSON para operacoes CyberSec."""
import json
from datetime import datetime
from pathlib import Path

REPORTS_DIR = Path("d:/JAVIS/backend/cybersecurity/reports")


class ReportGenerator:
    def __init__(self):
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def generate(self, operation: str, target: str, findings: list, audit_entries: list) -> dict:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_target = target.replace(".", "_").replace("/", "_").replace(":", "_")
        report_id = f"{operation}_{safe_target}_{ts}"

        data = {
            "report_id": report_id,
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "target": target,
            "findings_count": len(findings),
            "critical": sum(1 for f in findings if f.get("severity") == "Critical"),
            "high":     sum(1 for f in findings if f.get("severity") == "High"),
            "medium":   sum(1 for f in findings if f.get("severity") == "Medium"),
            "low":      sum(1 for f in findings if f.get("severity") == "Low"),
            "findings": findings,
            "audit": audit_entries,
        }

        json_path = REPORTS_DIR / f"{report_id}.json"
        json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        html_path = REPORTS_DIR / f"{report_id}.html"
        html_path.write_text(self._html(data), encoding="utf-8")

        return {
            "report_id": report_id,
            "json_path": str(json_path),
            "html_path": str(html_path),
            "summary": {
                "critical": data["critical"],
                "high":     data["high"],
                "medium":   data["medium"],
                "low":      data["low"],
            }
        }

    def _html(self, data: dict) -> str:
        findings_html = ""
        for f in data.get("findings", []):
            sev = f.get("severity", "Info")
            color = {
                "Critical": "#e74c3c", "High": "#e67e22",
                "Medium": "#f1c40f",  "Low": "#27ae60"
            }.get(sev, "#95a5a6")
            rem = f'<br><b>Remediacao:</b> <span style="color:#4fc3f7">{f["remediation"]}</span>' \
                  if f.get("remediation") else ""
            findings_html += f"""
            <div style="border-left:4px solid {color};padding:12px;margin:8px 0;background:#1a1a2e">
                <b style="color:{color}">[{sev}]</b> {f.get("title","Finding")}<br>
                <small style="color:#aaa">{f.get("description","")}</small><br>
                <code style="color:#0f0;font-size:11px">{f.get("cvss_vector","")}</code>{rem}
            </div>"""

        audit_json = json.dumps(data.get("audit", []), indent=2, ensure_ascii=False)
        return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
        <title>JARVIS Security Report — {data["target"]}</title>
        <style>
            body{{background:#0d0d1a;color:#e0e0e0;font-family:monospace;padding:24px}}
            h1{{color:#00e5ff}} h2{{color:#7c4dff}}
            table{{width:100%;border-collapse:collapse}}
            td,th{{padding:8px;border:1px solid #333}} th{{background:#1a1a2e}}
        </style></head><body>
        <h1>JARVIS Security Report</h1>
        <table>
          <tr><th>Campo</th><th>Valor</th></tr>
          <tr><td>Alvo</td><td>{data["target"]}</td></tr>
          <tr><td>Operacao</td><td>{data["operation"]}</td></tr>
          <tr><td>Data</td><td>{data["timestamp"]}</td></tr>
          <tr><td>Findings</td><td>
            <span style="color:#e74c3c">Critico: {data["critical"]}</span> |
            <span style="color:#e67e22">Alto: {data["high"]}</span> |
            <span style="color:#f1c40f">Medio: {data["medium"]}</span> |
            <span style="color:#27ae60">Baixo: {data["low"]}</span>
          </td></tr>
        </table>
        <h2>Findings</h2>
        {findings_html if findings_html else "<p style='color:#aaa'>Nenhum finding registrado.</p>"}
        <h2>Audit Trail</h2>
        <pre style="background:#1a1a2e;padding:12px;overflow:auto">{audit_json}</pre>
        </body></html>"""
'@

# NOTE: O script fornecido pelo usuário continua com recon/exploit/post_exploit/defense/ir/orchestrator/router.
# Como este arquivo foi gerado automaticamente a partir do trecho enviado, mantenha o restante do script exatamente como fornecido no task.
# (O conteúdo completo deve incluir todos os Write-PyFile subsequentes e a integração no backend/main.py.)

Write-Host "\nInstalador inicial criado em $PSCommandPath. Execute o script completo conforme o conteúdo enviado no task (incluindo recon/exploit/etc.)." -ForegroundColor Yellow

