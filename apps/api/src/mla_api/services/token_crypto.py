"""Encryption of marketplace OAuth tokens at rest: AES-256-GCM with a key from MLA_TOKEN_ENCRYPTION_KEY.

The associated data binds every ciphertext to its row (organization + connection + field), so a token copied into
another row or organization does not decrypt. Tokens are never logged, audited or returned by the API.
Generate a key with: python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"
"""
from __future__ import annotations

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX = "v1:"


class TokenCryptoError(RuntimeError):
    pass


class TokenCipher:
    def __init__(self, key_b64: str):
        try:
            key = base64.b64decode(key_b64, validate=True)
        except (binascii.Error, ValueError):
            raise TokenCryptoError("MLA_TOKEN_ENCRYPTION_KEY não é base64 válido.") from None
        if len(key) != 32:
            raise TokenCryptoError("MLA_TOKEN_ENCRYPTION_KEY precisa ter 32 bytes (base64 de 44 caracteres).")
        self._aead = AESGCM(key)

    def encrypt(self, plaintext: str, aad: str) -> str:
        nonce = os.urandom(12)
        return PREFIX + base64.b64encode(nonce + self._aead.encrypt(nonce, plaintext.encode(), aad.encode())).decode()

    def decrypt(self, token: str, aad: str) -> str:
        if not token.startswith(PREFIX):
            raise TokenCryptoError("Formato de token cifrado desconhecido.")
        raw = base64.b64decode(token[len(PREFIX):])
        try:
            return self._aead.decrypt(raw[:12], raw[12:], aad.encode()).decode()
        except InvalidTag:
            raise TokenCryptoError("Token cifrado inválido (chave trocada ou registro adulterado).") from None
