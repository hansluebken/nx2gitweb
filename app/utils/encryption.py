"""
Encryption utilities for securing sensitive data like API keys and tokens
Uses Fernet (symmetric encryption) with a key stored in a secure file
"""
import os
from pathlib import Path
from cryptography.fernet import Fernet
from typing import Optional


class EncryptionManager:
    """
    Manages encryption and decryption of sensitive data.
    Uses Fernet symmetric encryption with a key file.
    """

    def __init__(self, key_path: Optional[str] = None):
        """
        Initialize encryption manager

        Args:
            key_path: Path to the encryption key file.
                     Defaults to /app/data/keys/encryption.key
        """
        if key_path is None:
            key_path = os.getenv('ENCRYPTION_KEY_PATH', '/app/data/keys/encryption.key')

        self.key_path = Path(key_path)
        self._fernet = None
        self._ensure_key_exists()

    def _ensure_key_exists(self):
        """Ensure encryption key file exists, create if not"""
        if not self.key_path.exists():
            # Create directory if it doesn't exist
            self.key_path.parent.mkdir(parents=True, exist_ok=True)

            # Generate and save new key
            key = Fernet.generate_key()
            self.key_path.write_bytes(key)

            # Secure permissions (owner read/write only)
            os.chmod(self.key_path, 0o600)

            print(f"✓ New encryption key generated at {self.key_path}")
        else:
            # Verify permissions
            current_permissions = oct(os.stat(self.key_path).st_mode)[-3:]
            if current_permissions != '600':
                os.chmod(self.key_path, 0o600)
                print(f"⚠ Fixed encryption key permissions at {self.key_path}")

    def _get_fernet(self) -> Fernet:
        """Get or create Fernet instance"""
        if self._fernet is None:
            key = self.key_path.read_bytes()
            self._fernet = Fernet(key)
        return self._fernet

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext string

        Args:
            plaintext: String to encrypt

        Returns:
            Encrypted string (base64 encoded)
        """
        if not plaintext:
            return ""

        fernet = self._get_fernet()
        encrypted_bytes = fernet.encrypt(plaintext.encode('utf-8'))
        return encrypted_bytes.decode('utf-8')

    def decrypt(self, encrypted: str) -> str:
        """
        Decrypt an encrypted string

        Args:
            encrypted: Encrypted string (base64 encoded)

        Returns:
            Decrypted plaintext string

        Raises:
            cryptography.fernet.InvalidToken: If decryption fails
        """
        if not encrypted:
            return ""

        fernet = self._get_fernet()
        decrypted_bytes = fernet.decrypt(encrypted.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')

    def rotate_key(self, new_key_path: Optional[str] = None):
        """
        Rotate encryption key (for advanced use cases)

        WARNING: This will invalidate all existing encrypted data!
        You must re-encrypt all data with the new key.

        Args:
            new_key_path: Path for the new key file
        """
        if new_key_path:
            self.key_path = Path(new_key_path)

        # Generate new key
        new_key = Fernet.generate_key()

        # Backup old key
        if self.key_path.exists():
            backup_path = self.key_path.with_suffix('.key.backup')
            self.key_path.rename(backup_path)
            print(f"✓ Old key backed up to {backup_path}")

        # Save new key
        self.key_path.write_bytes(new_key)
        os.chmod(self.key_path, 0o600)

        # Reset Fernet instance
        self._fernet = None

        print(f"✓ New encryption key generated at {self.key_path}")
        print("⚠ WARNING: All existing encrypted data must be re-encrypted!")


# Global instance
_encryption_manager: Optional[EncryptionManager] = None


def get_encryption_manager() -> EncryptionManager:
    """Get global encryption manager instance"""
    global _encryption_manager
    if _encryption_manager is None:
        _encryption_manager = EncryptionManager()
    return _encryption_manager
