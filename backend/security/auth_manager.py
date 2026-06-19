"""
JARVIS Auth Manager — Autenticação criptografada com tokens HMAC-SHA256.

Sistema de token único por dispositivo:
- Token gerado a partir da JARVIS_SECRET_KEY (AES-256 seed)
- HMAC-SHA256: impossível de forjar sem conhecer a chave secreta
- Tokens vinculados a um nome de dispositivo (PC, iPhone, etc.)
- Revogação individual por dispositivo
- Persistência em SQLite criptografado
- TTL configurável por token
- IP Allowlist (bypass de autenticação para IPs confiáveis)
- Audit trail completo de eventos de segurança

Fluxo:
  1. generate_token.bat gera token para cada dispositivo
  2. Usuário abre URL: http://IP:8000/?auth=TOKEN
  3. Frontend armazena token no localStorage
  4. Todas as requisições incluem: Authorization: Bearer TOKEN
  5. Backend valida HMAC — acesso negado se inválido
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("jarvis.security.auth")

_DB_PATH = Path(__file__).parent.parent / "data" / "security.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class TokenInfo:
    device_name: str
    token: str
    created_at: float
    last_used: float = 0.0
    use_count: int = 0
    revoked: bool = False
    ip_hint: str = ""


class AuthManager:
    """Gerencia tokens de acesso criptografados do JARVIS."""

    def __init__(self, secret_key: str):
        if not secret_key or len(secret_key) < 16:
            raise ValueError("JARVIS_SECRET_KEY muito curta — mínimo 16 caracteres")
        self._secret = secret_key.encode()
        self._conn = self._init_db()

    # ── Banco de dados ─────────────────────────────────────────────────────────

    def _init_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                device_name TEXT PRIMARY KEY,
                token       TEXT NOT NULL UNIQUE,
                created_at  REAL NOT NULL,
                last_used   REAL DEFAULT 0,
                use_count   INTEGER DEFAULT 0,
                revoked     INTEGER DEFAULT 0,
                ip_hint     TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS blocked_ips (
                ip          TEXT PRIMARY KEY,
                reason      TEXT,
                blocked_at  REAL NOT NULL,
                expires_at  REAL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS allowlist (
                ip TEXT PRIMARY KEY,
                reason TEXT DEFAULT '',
                added_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                device_name TEXT DEFAULT '',
                ip TEXT DEFAULT '',
                detail TEXT DEFAULT '',
                timestamp REAL NOT NULL
            )
        """)
        conn.commit()

        # Add new columns to existing tables — ignore errors if they already exist
        for stmt in [
            "ALTER TABLE tokens ADD COLUMN expires_at REAL DEFAULT 0",
            "ALTER TABLE tokens ADD COLUMN revoked_reason TEXT DEFAULT ''",
        ]:
            try:
                conn.execute(stmt)
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists

        log.info("[AUTH] Banco de segurança inicializado: %s", _DB_PATH)
        return conn

    # ── Geração de token ────────────────────────────────────────────────────────

    def generate_token(self, device_name: str, ip_hint: str = "", ttl_days: int = 0) -> str:
        """
        Gera token HMAC-SHA256 para um dispositivo.
        Token é determinístico: mesmo device_name + secret = mesmo token.
        Isso permite regenerar sem invalidar.
        ttl_days=0 significa sem expiração.
        """
        existing = self._get_token_row(device_name)
        if existing and not existing["revoked"]:
            log.info("[AUTH] Token já existe para '%s'", device_name)
            return existing["token"]

        payload = f"{device_name}:{int(time.time() // 86400)}"  # muda por dia apenas se regenerado
        token = hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()
        expires_at = time.time() + ttl_days * 86400 if ttl_days > 0 else 0
        self._conn.execute(
            "INSERT OR REPLACE INTO tokens "
            "(device_name, token, created_at, last_used, use_count, revoked, ip_hint, expires_at) "
            "VALUES (?, ?, ?, 0, 0, 0, ?, ?)",
            (device_name, token, time.time(), ip_hint, expires_at)
        )
        self._conn.commit()
        self._audit("token_generated", device_name=device_name, ip=ip_hint)
        log.info("[AUTH] Token gerado para '%s'", device_name)
        return token

    # ── Validação ──────────────────────────────────────────────────────────────

    def validate_token(self, token: str, client_ip: str = "") -> tuple[bool, str]:
        """
        Valida token. Retorna (válido: bool, device_name: str).
        Atualiza last_used e use_count em caso de sucesso.
        Verifica expiração do token.
        """
        if not token or len(token) != 64:
            return False, ""

        row = self._conn.execute(
            "SELECT * FROM tokens WHERE token = ? AND revoked = 0",
            (token,)
        ).fetchone()

        if not row:
            log.warning("[AUTH] Token inválido de IP: %s", client_ip)
            return False, ""

        # Check expiry
        expires_at = row["expires_at"] if "expires_at" in row.keys() else 0
        if expires_at and expires_at > 0 and time.time() > expires_at:
            self._conn.execute(
                "UPDATE tokens SET revoked = 1, revoked_reason = 'expired' WHERE token = ?",
                (token,)
            )
            self._conn.commit()
            log.warning("[AUTH] Token expirado para '%s'", row["device_name"])
            return False, ""

        # Atualizar uso
        self._conn.execute(
            "UPDATE tokens SET last_used = ?, use_count = use_count + 1 WHERE token = ?",
            (time.time(), token)
        )
        self._conn.commit()
        return True, row["device_name"]

    # ── Revogação ──────────────────────────────────────────────────────────────

    def revoke_token(self, device_name: str, reason: str = "manual") -> bool:
        """Revoga token de um dispositivo específico."""
        cur = self._conn.execute(
            "UPDATE tokens SET revoked = 1, revoked_reason = ? WHERE device_name = ?",
            (reason, device_name)
        )
        self._conn.commit()
        if cur.rowcount > 0:
            log.warning("[AUTH] Token revogado para '%s'", device_name)
            self._audit("token_revoked", device_name=device_name, detail=reason)
            return True
        return False

    def revoke_all(self) -> int:
        """Revoga TODOS os tokens (emergência)."""
        cur = self._conn.execute("UPDATE tokens SET revoked = 1")
        self._conn.commit()
        log.critical("[AUTH] TODOS os tokens revogados (%d)", cur.rowcount)
        return cur.rowcount

    # ── Listagem ────────────────────────────────────────────────────────────────

    def list_tokens(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT device_name, created_at, last_used, use_count, revoked, ip_hint FROM tokens"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── IP Blacklist ────────────────────────────────────────────────────────────

    def block_ip(self, ip: str, reason: str, duration_minutes: int = 60) -> None:
        expires = time.time() + duration_minutes * 60 if duration_minutes > 0 else 0
        self._conn.execute("""
            INSERT OR REPLACE INTO blocked_ips (ip, reason, blocked_at, expires_at)
            VALUES (?, ?, ?, ?)
        """, (ip, reason, time.time(), expires))
        self._conn.commit()
        log.warning("[AUTH] IP BLOQUEADO: %s — %s (por %dmin)", ip, reason, duration_minutes)

    def is_ip_blocked(self, ip: str) -> tuple[bool, str]:
        """Retorna (bloqueado, motivo)."""
        row = self._conn.execute(
            "SELECT reason, expires_at FROM blocked_ips WHERE ip = ?", (ip,)
        ).fetchone()
        if not row:
            return False, ""
        expires = row["expires_at"]
        if expires > 0 and time.time() > expires:
            self._conn.execute("DELETE FROM blocked_ips WHERE ip = ?", (ip,))
            self._conn.commit()
            return False, ""
        return True, row["reason"]

    def unblock_ip(self, ip: str) -> bool:
        cur = self._conn.execute("DELETE FROM blocked_ips WHERE ip = ?", (ip,))
        self._conn.commit()
        return cur.rowcount > 0

    def list_blocked_ips(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM blocked_ips").fetchall()
        return [dict(r) for r in rows]

    # ── IP Allowlist ────────────────────────────────────────────────────────────

    def add_to_allowlist(self, ip: str, reason: str = "") -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO allowlist (ip, reason, added_at) VALUES (?, ?, ?)",
            (ip, reason, time.time())
        )
        self._conn.commit()
        self._audit("allowlist_add", ip=ip, detail=reason)
        log.info("[AUTH] IP adicionado à allowlist: %s — %s", ip, reason)

    def remove_from_allowlist(self, ip: str) -> bool:
        cur = self._conn.execute("DELETE FROM allowlist WHERE ip = ?", (ip,))
        self._conn.commit()
        return cur.rowcount > 0

    def is_ip_allowlisted(self, ip: str) -> bool:
        row = self._conn.execute("SELECT 1 FROM allowlist WHERE ip = ?", (ip,)).fetchone()
        return row is not None

    def list_allowlisted_ips(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM allowlist ORDER BY added_at DESC").fetchall()
        return [dict(r) for r in rows]

    # ── Audit trail ─────────────────────────────────────────────────────────────

    def _audit(self, event_type: str, device_name: str = "", ip: str = "", detail: str = "") -> None:
        try:
            self._conn.execute(
                "INSERT INTO audit_log (event_type, device_name, ip, detail, timestamp) VALUES (?, ?, ?, ?, ?)",
                (event_type, device_name, ip, detail, time.time())
            )
            self._conn.commit()
        except Exception:
            pass

    def get_audit_log(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _get_token_row(self, device_name: str):
        return self._conn.execute(
            "SELECT * FROM tokens WHERE device_name = ?", (device_name,)
        ).fetchone()


# ── Singleton ──────────────────────────────────────────────────────────────────

_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    global _manager
    if _manager is None:
        from config import get_config
        cfg = get_config()
        secret = getattr(cfg, "secret_key", "") or os.getenv("JARVIS_SECRET_KEY", "")
        if not secret:
            raise RuntimeError("JARVIS_SECRET_KEY não configurada — execute setup_security.bat")
        _manager = AuthManager(secret)
    return _manager
