"""Encrypt small secrets for the current Windows user (DPAPI). Copies of the database on another computer or
another Windows user cannot decrypt them: the user simply connects the account again."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

_ENTROPY = b"MLA marketplace credentials v1"


class SecureStoreError(RuntimeError):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[_Blob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _call(function, data: bytes) -> bytes:
    if sys.platform != "win32":
        raise SecureStoreError("Armazenamento seguro disponível só no Windows.")
    source, _keep = _blob(data)
    entropy, _keep2 = _blob(_ENTROPY)
    out = _Blob()
    if not function(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 0x1, ctypes.byref(out)):
        raise SecureStoreError("Não foi possível proteger/ler a credencial com o Windows (DPAPI).")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def protect(text: str) -> bytes:
    return _call(ctypes.windll.crypt32.CryptProtectData, text.encode("utf-8"))


def unprotect(blob: bytes) -> str:
    return _call(ctypes.windll.crypt32.CryptUnprotectData, bytes(blob)).decode("utf-8")
