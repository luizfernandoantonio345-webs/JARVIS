"""
JARVIS Crypto — Criptografia AES-256-GCM para memória em repouso.
Usa Fernet (AES-128-CBC + HMAC-SHA256) ou AES-256-GCM via cryptography.
Chave derivada de JARVIS_SECRET_KEY via PBKDF2-SHA256.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from functools import lru_cache

log = logging.getLogger("jarvis.crypto")

# ── Chave ─────────────────────────────────────────────────────────────────────
def _derive_key(secret: str, salt: bytes = b"JARVIS_V6_SALT_2026") -> bytes:
    """Deriva chave AES-256 de 32 bytes via PBKDF2-SHA256."""
    return hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, iterations=100_000, dklen=32)


@lru_cache(maxsize=1)
def _get_key() -> bytes:
    secret = os.getenv("JARVIS_SECRET_KEY", "")
    if not secret:
        # Gera uma chave efémera se não houver secret configurado
        log.warning("[CRYPTO] JARVIS_SECRET_KEY não definido — usando chave efémera (dados não persistidos de forma segura)")
        secret = os.urandom(32).hex()
    return _derive_key(secret)


# ── AES-256-GCM (preferido — autenticado) ────────────────────────────────────
def encrypt(plaintext: str) -> str:
    """Criptografa string com AES-256-GCM. Retorna base64 URL-safe."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = _get_key()
        nonce = os.urandom(12)  # 96-bit nonce para GCM
        aesgcm = AESGCM(key)
        ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        payload = nonce + ct
        return base64.urlsafe_b64encode(payload).decode("ascii")
    except ImportError:
        # Fallback para Fernet se cryptography não tiver AESGCM
        return _fernet_encrypt(plaintext)
    except Exception as e:
        log.error("[CRYPTO] Erro ao encriptar: %s", e)
        return plaintext  # Fail-open: dados em claro se crypto falhar


def decrypt(ciphertext: str) -> str:
    """Decripta string cifrada com AES-256-GCM."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = _get_key()
        payload = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        nonce, ct = payload[:12], payload[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
    except ImportError:
        return _fernet_decrypt(ciphertext)
    except Exception as e:
        log.error("[CRYPTO] Erro ao decriptar: %s", e)
        return ciphertext  # Fail-open


# ── Fernet fallback ───────────────────────────────────────────────────────────
def _fernet_encrypt(plaintext: str) -> str:
    from cryptography.fernet import Fernet
    key_32 = _get_key()
    fkey = base64.urlsafe_b64encode(key_32)
    f = Fernet(fkey)
    return f.encrypt(plaintext.encode()).decode()


def _fernet_decrypt(ciphertext: str) -> str:
    from cryptography.fernet import Fernet
    key_32 = _get_key()
    fkey = base64.urlsafe_b64encode(key_32)
    f = Fernet(fkey)
    return f.decrypt(ciphertext.encode()).decode()


# ── Hash seguro (para session IDs, tokens) ───────────────────────────────────
def secure_hash(value: str) -> str:
    """HMAC-SHA256 de um valor com a chave do sistema."""
    import hmac
    key = _get_key()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def generate_token(length: int = 32) -> str:
    """Gera token aleatório URL-safe de comprimento especificado."""
    return base64.urlsafe_b64encode(os.urandom(length)).decode("ascii")[:length]
