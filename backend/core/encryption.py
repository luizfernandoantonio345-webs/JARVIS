"""
Encryption module for sensitive data in JARVIS.
Provides EncryptedString for API keys, tokens, and passwords.
"""
import base64
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


class EncryptionError(Exception):
    """Raised when encryption/decryption fails."""
    pass


class EncryptedString:
    """
    Secure wrapper for sensitive strings (API keys, tokens, passwords).
    Encrypts at rest, decrypts on demand.
    """

    _cipher: Optional[Fernet] = None
    _key_env_var = "JARVIS_ENCRYPTION_KEY"

    @classmethod
    def initialize(cls, key: Optional[str] = None) -> None:
        """
        Initialize cipher with encryption key.

        Args:
            key: Encryption key (URL-safe base64). If None, tries to load from env.
        """
        if key is None:
            key = os.environ.get(cls._key_env_var)

        if key is None:
            # Generate new key
            key = Fernet.generate_key().decode()
            print(f"Generated new encryption key. Set {cls._key_env_var}={key}")

        try:
            cls._cipher = Fernet(key if isinstance(key, bytes) else key.encode())
        except Exception as e:
            raise EncryptionError(f"Failed to initialize cipher: {e}")

    @classmethod
    def get_cipher(cls) -> Fernet:
        """Get or initialize cipher."""
        if cls._cipher is None:
            cls.initialize()
        return cls._cipher

    @classmethod
    def generate_key(cls) -> str:
        """Generate a new encryption key."""
        return Fernet.generate_key().decode()

    def __init__(self, plaintext: str):
        """
        Create encrypted string.

        Args:
            plaintext: The sensitive string to encrypt
        """
        if not plaintext:
            raise EncryptionError("Cannot encrypt empty string")

        try:
            cipher = self.get_cipher()
            self._encrypted = cipher.encrypt(plaintext.encode()).decode()
        except Exception as e:
            raise EncryptionError(f"Encryption failed: {e}")

    def decrypt(self) -> str:
        """
        Decrypt and return the original string.

        Returns:
            The decrypted plaintext
        """
        try:
            cipher = self.get_cipher()
            return cipher.decrypt(self._encrypted.encode()).decode()
        except InvalidToken:
            raise EncryptionError("Decryption failed: invalid token/corrupted data")
        except Exception as e:
            raise EncryptionError(f"Decryption failed: {e}")

    def __str__(self) -> str:
        """Return last 4 chars for logging (safe display)."""
        return f"***{self.decrypt()[-4:]}"

    def __repr__(self) -> str:
        """Return masked representation."""
        return f"EncryptedString(***)"

    def __eq__(self, other: object) -> bool:
        """Compare decrypted values."""
        if not isinstance(other, EncryptedString):
            return False
        try:
            return self.decrypt() == other.decrypt()
        except EncryptionError:
            return False


class EncryptedConfig:
    """Helper for encrypting sensitive config values."""

    def __init__(self, config_dict: dict):
        self.config = config_dict
        self._encrypted_fields = {}

    def encrypt_field(self, field_name: str) -> None:
        """Encrypt a specific field in config."""
        if field_name in self.config and self.config[field_name]:
            try:
                self._encrypted_fields[field_name] = EncryptedString(
                    str(self.config[field_name])
                )
                self.config[field_name] = f"[ENCRYPTED:{field_name}]"
            except EncryptionError as e:
                print(f"Failed to encrypt {field_name}: {e}")

    def decrypt_field(self, field_name: str) -> Optional[str]:
        """Decrypt a specific field."""
        if field_name in self._encrypted_fields:
            try:
                return self._encrypted_fields[field_name].decrypt()
            except EncryptionError:
                return None
        return self.config.get(field_name)


# Module initialization
def setup_encryption() -> None:
    """Setup encryption with key from environment."""
    key = os.environ.get("JARVIS_ENCRYPTION_KEY")
    try:
        EncryptedString.initialize(key)
        if key:
            print("[SECURITY] Encryption initialized with existing key")
        else:
            print("[SECURITY] WARNING: No encryption key found. Generate one with:")
            print(f"  EncryptedString.generate_key()")
    except EncryptionError as e:
        print(f"[SECURITY] Encryption setup failed: {e}")
