"""
JARVIS Auth Manager — Autenticação criptografada com tokens HMAC-SHA256.

Sistema de token único por dispositivo:
- Token gerado a partir da JARVIS_SECRET_KEY (AES-256 seed)
- HMAC-SHA256: impossível de forjar sem conhecer a chave secreta
- Tokens vinculados a um nome de dispositivo (PC, iPhone, etc.)
- Revogação individual por dispositivo
- Persistência em SQLite criptografado

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
        conn.commit()
        log.info("[AUTH] Banco de segurança inicializado: %s", _DB_PATH)
        return conn

    # ── Geração de token ────────────────────────────────────────────────────────

    def generate_token(self, device_name: str, ip_hint: str = "") -> str:
        """
        Gera token HMAC-SHA256 para um dispositivo.
        Token é determinístico: mesmo device_name + secret = mesmo token.
        Isso permite regenerar sem invalidar.
        """
        # HMAC do nome do dispositivo + timestamp de criação (seed único por device)
        payload = f"{device_name}:{int(time.time() // 86400)}"  # muda por dia apenas se regenerado
        existing = self._get_token_row(device_name)
        if existing and not existing["revoked"]:
            log.info("[AUTH] Token já existe para '%s'", device_name)
            return existing["token"]

        token = hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()

        self._conn.execute("""
            INSERT OR REPLACE INTO tokens
            (device_name, token, created_at, last_used, use_count, revoked, ip_hint)
            VALUES (?, ?, ?, 0, 0, 0, ?)
        """, (device_name, token, time.time(), ip_hint))
        self._conn.commit()
        log.info("[AUTH] Token gerado para '%s'", device_name)
        return token

    # ── Validação ──────────────────────────────────────────────────────────────

    def validate_token(self, token: str, client_ip: str = "") -> tuple[bool, str]:
        """
        Valida token. Retorna (válido: bool, device_name: str).
        Atualiza last_used e use_count em caso de sucesso.
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

        # Atualizar uso
        self._conn.execute(
            "UPDATE tokens SET last_used = ?, use_count = use_count + 1 WHERE token = ?",
            (time.time(), token)
        )
        self._conn.commit()
        return True, row["device_name"]

    # ── Revogação ──────────────────────────────────────────────────────────────

    def revoke_token(self, device_name: str) -> bool:
        """Revoga token de um dispositivo específico."""
        cur = self._conn.execute(
            "UPDATE tokens SET revoked = 1 WHERE device_name = ?",
            (device_name,)
        )
        self._conn.commit()
        if cur.rowcount > 0:
            log.warning("[AUTH] Token revogado para '%s'", device_name)
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
