"""Outgoing e-mail. Only development/test implementations exist; production SMTP is a stage F item."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from mla_api.db import utcnow

log = logging.getLogger("mla_api.mailer")


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


@dataclass
class MemoryMailer:
    sent: list[dict] = field(default_factory=list)

    def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append({"to": to, "subject": subject, "body": body})


@dataclass
class OutboxMailer:
    """Development: writes each message as JSON to a local folder instead of sending it."""
    folder: Path

    def send(self, to: str, subject: str, body: str) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        stamp = utcnow().strftime("%Y%m%dT%H%M%S%f")
        (self.folder / f"{stamp}.json").write_text(
            json.dumps({"to": to, "subject": subject, "body": body}, ensure_ascii=False, indent=1), encoding="utf-8")
        log.info("E-mail de desenvolvimento gravado em %s", self.folder)


class DisabledMailer:
    def send(self, to: str, subject: str, body: str) -> None:
        log.warning("Envio de e-mail não configurado; mensagem '%s' descartada.", subject)
