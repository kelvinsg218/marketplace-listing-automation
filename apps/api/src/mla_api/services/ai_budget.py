"""Spend control for paid AI providers: reserve before the call, settle after it (D-035).

The reservation is a single conditional UPDATE, so two simultaneous requests can never both pass the limit. When the
real cost is unknown (no `usage`, timeout, ambiguous error) the reservation is kept as spent: the counter errs on the
side of stopping early, never of spending more than the budget.
"""
from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mla_api.models import AiSpend

MICRO = 1_000_000


def to_micro(usd: float) -> int:
    return int(round(usd * MICRO))


def _ensure(db: Session, provider: str) -> None:
    if db.get(AiSpend, provider) is None:
        try:
            with db.begin_nested():
                db.add(AiSpend(provider=provider))
        except IntegrityError:
            pass  # created by a concurrent request


def snapshot(db: Session, provider: str, budget_usd: float) -> dict:
    row = db.get(AiSpend, provider)
    spent, reserved = (row.spent_micro_usd, row.reserved_micro_usd) if row else (0, 0)
    remaining = max(0, to_micro(budget_usd) - spent - reserved)
    return {"budget_usd": round(budget_usd, 2), "spent_usd": round(spent / MICRO, 4),
            "reserved_usd": round(reserved / MICRO, 4), "remaining_usd": round(remaining / MICRO, 4),
            "calls": row.calls if row else 0}


def reserve(db: Session, provider: str, budget_usd: float, amount_usd: float) -> bool:
    """Holds `amount_usd` and commits; False (nothing held) when it would pass the budget."""
    _ensure(db, provider)
    amount = to_micro(amount_usd)
    held = db.execute(update(AiSpend).where(
        AiSpend.provider == provider,
        AiSpend.spent_micro_usd + AiSpend.reserved_micro_usd + amount <= to_micro(budget_usd))
        .values(reserved_micro_usd=AiSpend.reserved_micro_usd + amount)
        .execution_options(synchronize_session=False)).rowcount == 1
    db.commit()
    return held


def settle(db: Session, provider: str, reserved_usd: float, cost_usd: float | None) -> int:
    """Releases the reservation and adds the real cost (the reservation itself when unknown). Not committed."""
    held = to_micro(reserved_usd)
    charged = held if cost_usd is None else to_micro(cost_usd)
    db.execute(update(AiSpend).where(AiSpend.provider == provider).values(
        reserved_micro_usd=AiSpend.reserved_micro_usd - held, spent_micro_usd=AiSpend.spent_micro_usd + charged,
        calls=AiSpend.calls + 1).execution_options(synchronize_session=False))
    db.expire_all()
    return charged
