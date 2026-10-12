"""Local license state: installation id, trial, activation, plan.

No remote server and no invasive DRM. The bundled key verifier is a
PLACEHOLDER (checksum only, forgeable by design) so the activation flow can be
built and tested; replace it with signed keys (e.g. Ed25519) or a license
server before selling (roadmap phase 8).
"""
from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from mla.licensing.features import PLAN_FEATURES, Feature, Plan
from mla.persistence.db import Database, now_iso

TRIAL_DAYS = 30
_KEY_RE = re.compile(r"^MLA-(STARTER|PROFESSIONAL|BUSINESS)-([A-Z0-9]{4})-([A-Z0-9]{4})-([0-9A-F]{4})$")
_PLACEHOLDER_SALT = "mla-dev-placeholder"


class LicenseError(ValueError):
    pass


@dataclass(frozen=True)
class KeyInfo:
    plan: Plan
    expires_at: str | None = None


class KeyVerifier(Protocol):
    def verify(self, key: str, installation_id: str) -> KeyInfo: ...


class PlaceholderKeyVerifier:
    """Checksum-only verifier for development. Not a security boundary."""

    @staticmethod
    def checksum(body: str) -> str:
        return hashlib.sha256(f"{_PLACEHOLDER_SALT}:{body}".encode()).hexdigest()[:4].upper()

    @classmethod
    def make_key(cls, plan: Plan, block1: str = "TEST", block2: str = "0001") -> str:
        body = f"MLA-{plan.value.upper()}-{block1}-{block2}"
        return f"{body}-{cls.checksum(body)}"

    def verify(self, key: str, installation_id: str) -> KeyInfo:
        match = _KEY_RE.match(key.strip().upper())
        if not match:
            raise LicenseError("Formato de chave inválido. Exemplo: MLA-PROFESSIONAL-XXXX-XXXX-XXXX")
        body = key.strip().upper().rsplit("-", 1)[0]
        if self.checksum(body) != match.group(4):
            raise LicenseError("Chave de licença inválida.")
        return KeyInfo(plan=Plan(match.group(1).lower()))


@dataclass(frozen=True)
class LicenseStatus:
    installation_id: str
    plan: Plan
    status: str  # trial | active | expired
    trial_days_left: int
    license_key: str
    activated_at: str | None
    expires_at: str | None

    @property
    def label(self) -> str:
        if self.status == "active":
            return f"Plano {self.plan.label} ativo"
        if self.status == "trial":
            return f"Avaliação: {self.trial_days_left} dias restantes"
        return "Avaliação encerrada"

    @property
    def masked_key(self) -> str:
        return self.license_key[:12] + "…" + self.license_key[-4:] if self.license_key else ""


class LicenseManager:
    def __init__(self, db: Database, verifier: KeyVerifier | None = None, enforce: bool = False):
        self.db = db
        self.verifier = verifier or PlaceholderKeyVerifier()
        self.enforce = enforce  # MVP: features are never blocked

    def _ensure(self) -> None:
        if self.db.scalar("SELECT COUNT(*) FROM license_state") == 0:
            now = now_iso()
            self.db.execute(
                "INSERT INTO license_state (id, installation_id, trial_started_at, updated_at) VALUES (1, ?, ?, ?)",
                (str(uuid.uuid4()), now, now))

    def status(self, today: datetime | None = None) -> LicenseStatus:
        self._ensure()
        row = self.db.query_one("SELECT * FROM license_state WHERE id = 1")
        assert row is not None
        today = today or datetime.now()
        trial_end = datetime.fromisoformat(row["trial_started_at"]) + timedelta(days=TRIAL_DAYS)
        days_left = max(0, (trial_end.date() - today.date()).days)
        plan = Plan(row["plan"])
        status = row["status"]
        if status == "active" and row["expires_at"] and datetime.fromisoformat(row["expires_at"]) < today:
            status = "expired"
        elif status == "trial" and days_left == 0:
            status = "expired"
        return LicenseStatus(installation_id=row["installation_id"], plan=plan, status=status,
                             trial_days_left=days_left, license_key=row["license_key"],
                             activated_at=row["activated_at"], expires_at=row["expires_at"])

    def activate(self, key: str) -> LicenseStatus:
        current = self.status()
        info = self.verifier.verify(key, current.installation_id)
        now = now_iso()
        self.db.execute(
            "UPDATE license_state SET license_key = ?, plan = ?, status = 'active', activated_at = ?,"
            " expires_at = ?, updated_at = ? WHERE id = 1",
            (key.strip().upper(), info.plan.value, now, info.expires_at, now))
        return self.status()

    def deactivate(self) -> LicenseStatus:
        self._ensure()
        self.db.execute("UPDATE license_state SET license_key = '', plan = 'trial', status = 'trial',"
                        " activated_at = NULL, expires_at = NULL, updated_at = ? WHERE id = 1", (now_iso(),))
        return self.status()

    def features(self) -> frozenset[Feature]:
        return PLAN_FEATURES[self.status().plan]

    def is_enabled(self, feature: Feature) -> bool:
        if not self.enforce:
            return True
        current = self.status()
        return current.status != "expired" and feature in PLAN_FEATURES[current.plan]
