"""Mercado Livre bulk listing: seller accounts, official templates (registry + inspector), mappings and batches.

Rules from the official help pages are cited as P1/P2/P3 + page (docs/MLA_MERCADOLIVRE_RESEARCH.md).
"""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from mla_api import audit
from mla_api.db import utcnow
from mla_api.deps import OrgContext, require
from mla_api.domain.listing_rules import (SOURCE_FIELDS, Issue, TemplateContext, batch_size_issue, preview_rows,
                                          sheet_rows, suggest_source, validate_product, validate_template)
from mla_api.domain import workbook_writer
from mla_api.domain.sheet_builder import build_rows, validate_rows
from mla_api.domain.template_inspector import (MAX_FILE_BYTES, TemplateRejected, column_specs, compare_reports,
                                              inspect_workbook, sheet_columns)
from mla_api.models import (BatchExport, BatchStatus, ListingBatch, ListingBatchItem, MarketplaceTemplate, Product,
                            ProductStatus, SellerAccount, TemplateMapping, TemplateStatus)
from mla_api.schemas import UtcDatetime
from mla_api.services.listing_data import load_products
from mla_api.services.rules_service import rules_for_batch

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["bulk-listing"])
MARKETPLACE = "mercadolivre"
SOURCES = ("categories", "codes", "links", "shopee", "unknown")  # P1 p.5


def _today() -> date:
    return utcnow().date()


# --- seller accounts --------------------------------------------------------------------------------------------
class AccountIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    external_id: str = Field(default="", max_length=40, pattern=r"^[0-9A-Za-z_-]*$")


class AccountOut(BaseModel):
    id: uuid.UUID
    marketplace: str
    label: str
    external_id: str
    templates: int = 0
    created_at: UtcDatetime


def _account(ctx: OrgContext, account_id: uuid.UUID) -> SellerAccount:
    a = ctx.db.scalar(select(SellerAccount).where(SellerAccount.id == account_id,
                                                  SellerAccount.organization_id == ctx.org_id))
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conta de vendedor não encontrada.")
    return a


@router.get("/seller-accounts", response_model=list[AccountOut])
def list_accounts(ctx: OrgContext = Depends(require("catalog.read"))) -> list[AccountOut]:
    counts = dict(ctx.db.execute(select(MarketplaceTemplate.seller_account_id, func.count())
                                 .where(MarketplaceTemplate.organization_id == ctx.org_id)
                                 .group_by(MarketplaceTemplate.seller_account_id)).all())
    rows = ctx.db.scalars(select(SellerAccount).where(SellerAccount.organization_id == ctx.org_id)
                          .order_by(SellerAccount.label)).all()
    return [AccountOut(id=a.id, marketplace=a.marketplace, label=a.label, external_id=a.external_id,
                       templates=counts.get(a.id, 0), created_at=a.created_at) for a in rows]


@router.post("/seller-accounts", response_model=AccountOut, status_code=201)
def create_account(body: AccountIn, ctx: OrgContext = Depends(require("members.manage"))) -> AccountOut:
    a = SellerAccount(organization_id=ctx.org_id, marketplace=MARKETPLACE, label=body.label.strip(),
                      external_id=body.external_id)
    ctx.db.add(a)
    try:
        ctx.db.flush()
    except IntegrityError:
        ctx.db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma conta com este nome.")
    audit.record(ctx.db, "seller_account.created", user_id=ctx.user.id, org_id=ctx.org_id,
                 target_type="seller_account", target_id=a.id, label=a.label)
    ctx.db.commit()
    return AccountOut(id=a.id, marketplace=a.marketplace, label=a.label, external_id=a.external_id,
                      created_at=a.created_at)


@router.delete("/seller-accounts/{account_id}", status_code=204, response_class=Response, response_model=None)
def delete_account(account_id: uuid.UUID, ctx: OrgContext = Depends(require("members.manage"))) -> None:
    a = _account(ctx, account_id)
    if ctx.db.scalar(select(MarketplaceTemplate.id).where(MarketplaceTemplate.seller_account_id == a.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A conta tem templates registrados; arquive-os antes.")
    audit.record(ctx.db, "seller_account.deleted", user_id=ctx.user.id, org_id=ctx.org_id,
                 target_type="seller_account", target_id=a.id, label=a.label)
    ctx.db.delete(a)
    ctx.db.commit()


# --- templates --------------------------------------------------------------------------------------------------
class TemplateOut(BaseModel):
    id: uuid.UUID
    seller_account_id: uuid.UUID
    seller_account_label: str
    marketplace: str
    source: str
    original_filename: str
    sha256: str
    size_bytes: int
    status: str
    deadline_text: str
    deadline_date: date | None
    deadline_confirmed: bool
    expired: bool
    sheets: list[dict]          # [{name, state, is_help, max_row, max_column}]
    warnings: list[str]
    created_at: UtcDatetime
    structure: dict | None = None


def _template_out(t: MarketplaceTemplate, label: str, full: bool = False) -> TemplateOut:
    st = t.structure or {}
    return TemplateOut(
        id=t.id, seller_account_id=t.seller_account_id, seller_account_label=label, marketplace=t.marketplace,
        source=t.source, original_filename=t.original_filename, sha256=t.sha256, size_bytes=t.size_bytes,
        status=t.status, deadline_text=t.deadline_text, deadline_date=t.deadline_date,
        deadline_confirmed=t.deadline_confirmed, expired=bool(t.deadline_date and t.deadline_date < _today()),
        sheets=[{k: s[k] for k in ("name", "state", "is_help", "max_row", "max_column")} for s in st.get("sheets", [])],
        warnings=st.get("warnings", []) + ([st["error"]] if st.get("error") else []), created_at=t.created_at,
        structure=st if full else None)


def _template(ctx: OrgContext, template_id: uuid.UUID) -> MarketplaceTemplate:
    t = ctx.db.scalar(select(MarketplaceTemplate).where(MarketplaceTemplate.id == template_id,
                                                        MarketplaceTemplate.organization_id == ctx.org_id))
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template não encontrado.")
    return t


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(ctx: OrgContext = Depends(require("catalog.read"))) -> list[TemplateOut]:
    rows = ctx.db.execute(select(MarketplaceTemplate, SellerAccount.label)
                          .join(SellerAccount, SellerAccount.id == MarketplaceTemplate.seller_account_id)
                          .where(MarketplaceTemplate.organization_id == ctx.org_id)
                          .order_by(MarketplaceTemplate.created_at.desc())).all()
    return [_template_out(t, label) for t, label in rows]


@router.post("/templates", response_model=TemplateOut, status_code=201)
async def upload_template(file: UploadFile = File(...), seller_account_id: uuid.UUID = Form(...),
                          source: Literal["categories", "codes", "links", "shopee", "unknown"] = Form("unknown"),
                          ctx: OrgContext = Depends(require("catalog.write"))) -> TemplateOut:
    """Stores the official workbook untouched and inspects a read-only copy in memory."""
    account = _account(ctx, seller_account_id)
    name = (file.filename or "planilha.xlsx")[:255]
    if not name.lower().endswith(".xlsx"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Envie o arquivo .xlsx baixado do Anunciador "
                                                                   "em massa.")
    data = await file.read(MAX_FILE_BYTES + 1)
    sha = hashlib.sha256(data).hexdigest()
    if ctx.db.scalar(select(MarketplaceTemplate.id).where(MarketplaceTemplate.organization_id == ctx.org_id,
                                                          MarketplaceTemplate.sha256 == sha)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Este mesmo arquivo já foi registrado.")
    try:
        report, state = inspect_workbook(data, today=_today()), TemplateStatus.INSPECTED
    except TemplateRejected as exc:
        if len(data) > MAX_FILE_BYTES or not data.startswith(b"PK"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
        report, state = {"error": str(exc), "sheets": []}, TemplateStatus.INVALID
    template_id = uuid.uuid4()
    key = ctx.storage.put(ctx.org_id, "templates", f"{template_id}.xlsx", data)
    deadline = report.get("deadline") or {}
    t = MarketplaceTemplate(
        id=template_id, organization_id=ctx.org_id, seller_account_id=account.id, marketplace=MARKETPLACE,
        source=source, original_filename=name, storage_key=key, sha256=sha, size_bytes=len(data), status=state,
        structure=report, deadline_text=deadline.get("text", ""),
        deadline_date=date.fromisoformat(deadline["date"]) if deadline.get("date") else None,
        deadline_confirmed=bool(deadline) and not deadline.get("year_inferred", True), uploaded_by=ctx.user.id)
    previous = ctx.db.scalar(select(MarketplaceTemplate).where(
        MarketplaceTemplate.organization_id == ctx.org_id, MarketplaceTemplate.seller_account_id == account.id,
        MarketplaceTemplate.status == TemplateStatus.INSPECTED).order_by(MarketplaceTemplate.created_at.desc()))
    if previous is not None and state == TemplateStatus.INSPECTED:
        # Change detection between versions: facts only (what changed), never assumptions about why.
        report["comparison"] = {"previous_template_id": str(previous.id),
                                "previous_filename": previous.original_filename,
                                "diff": compare_reports(previous.structure or {}, report)}
        t.structure = report
    ctx.db.add(t)
    audit.record(ctx.db, "template.uploaded", user_id=ctx.user.id, org_id=ctx.org_id, target_type="template",
                 target_id=t.id, filename=name, sha256=sha[:12], status=state)
    ctx.db.commit()
    return _template_out(t, account.label, full=True)


@router.get("/templates/{template_id}", response_model=TemplateOut)
def get_template(template_id: uuid.UUID, ctx: OrgContext = Depends(require("catalog.read"))) -> TemplateOut:
    t = _template(ctx, template_id)
    return _template_out(t, _account(ctx, t.seller_account_id).label, full=True)


class TemplatePatch(BaseModel):
    deadline_date: date | None = None
    confirm_deadline: bool = False
    archive: bool = False


@router.patch("/templates/{template_id}", response_model=TemplateOut)
def update_template(template_id: uuid.UUID, body: TemplatePatch,
                    ctx: OrgContext = Depends(require("catalog.write"))) -> TemplateOut:
    t = _template(ctx, template_id)
    if body.deadline_date is not None:
        t.deadline_date, t.deadline_confirmed = body.deadline_date, True
    elif body.confirm_deadline:
        if t.deadline_date is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Não há data para confirmar; informe a data.")
        t.deadline_confirmed = True
    if body.archive:
        t.status = TemplateStatus.ARCHIVED
    audit.record(ctx.db, "template.updated", user_id=ctx.user.id, org_id=ctx.org_id, target_type="template",
                 target_id=t.id, archived=body.archive, deadline=str(t.deadline_date or ""))
    ctx.db.commit()
    return _template_out(t, _account(ctx, t.seller_account_id).label, full=True)


@router.get("/templates/{template_id}/file")
def download_template(template_id: uuid.UUID, ctx: OrgContext = Depends(require("catalog.read"))) -> Response:
    t = _template(ctx, template_id)
    data = ctx.storage.read(ctx.org_id, t.storage_key)
    safe = "".join(ch for ch in t.original_filename if ch.isalnum() or ch in "._- ") or "template.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{safe}"'})


# --- mapping ----------------------------------------------------------------------------------------------------
class ColumnsOut(BaseModel):
    sheet_name: str
    header_row: int
    header_row_confirmed: bool
    header_candidates: list[dict]
    columns: list[dict]                 # [{col, header, required, suggestion}]
    rules: dict[str, dict]
    source_fields: dict[str, str]


def _sheet(t: MarketplaceTemplate, sheet: str) -> dict:
    s = next((s for s in (t.structure or {}).get("sheets", []) if s["name"] == sheet), None)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aba não encontrada no template.")
    if s["is_help"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A aba Ajuda não recebe produtos (P2 p.1).")
    return s


def _mapping(ctx: OrgContext, template_id: uuid.UUID, sheet: str) -> TemplateMapping | None:
    return ctx.db.scalar(select(TemplateMapping).where(TemplateMapping.template_id == template_id,
                                                       TemplateMapping.organization_id == ctx.org_id,
                                                       TemplateMapping.sheet_name == sheet))


@router.get("/templates/{template_id}/mapping", response_model=ColumnsOut)
def get_mapping(template_id: uuid.UUID, sheet: str, header_row: int | None = None,
                ctx: OrgContext = Depends(require("catalog.read"))) -> ColumnsOut:
    t = _template(ctx, template_id)
    s = _sheet(t, sheet)
    saved = _mapping(ctx, t.id, sheet)
    candidates = s.get("header_candidates", [])
    layout_row = (s.get("layout") or {}).get("header_row")
    row = header_row or (saved.header_row if saved else (layout_row or (candidates[0]["row"] if candidates else 1)))
    try:
        columns = sheet_columns(t.structure, sheet, row)
    except IndexError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Linha de cabeçalho fora da pré-visualização.")
    specs = column_specs(t.structure, sheet) if row == layout_row else {}
    for c in columns:
        c["suggestion"] = suggest_source(c["header"])
        spec = specs.get(c["col"]) or {}
        c.update({"options": spec.get("options"), "strict": spec.get("strict", False),
                  "max_length": spec.get("max_length"), "template_default": spec.get("default"),
                  "help": spec.get("help", "")})
    rules = saved.rules if saved and saved.header_row == row else {}
    return ColumnsOut(sheet_name=sheet, header_row=row, header_row_confirmed=bool(saved and saved.header_row == row),
                      header_candidates=candidates, columns=columns, rules=rules, source_fields=SOURCE_FIELDS)


class RuleIn(BaseModel):
    source: str | None = Field(default=None, max_length=80)
    default: str = Field(default="", max_length=500)


class MappingIn(BaseModel):
    sheet_name: str = Field(min_length=1, max_length=64)
    header_row: int = Field(ge=1, le=200)
    rules: dict[str, RuleIn] = Field(default_factory=dict, max_length=500)


@router.put("/templates/{template_id}/mapping", response_model=ColumnsOut)
def save_mapping(template_id: uuid.UUID, body: MappingIn,
                 ctx: OrgContext = Depends(require("catalog.write"))) -> ColumnsOut:
    t = _template(ctx, template_id)
    if t.status != TemplateStatus.INSPECTED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Template inválido ou arquivado.")
    _sheet(t, body.sheet_name)
    try:
        columns = sheet_columns(t.structure, body.sheet_name, body.header_row)
    except IndexError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Linha de cabeçalho fora da pré-visualização.")
    letters = {c["col"] for c in columns}
    rules = {}
    for col, rule in body.rules.items():
        if col not in letters:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Coluna {col} não existe no cabeçalho.")
        if rule.source and rule.source not in SOURCE_FIELDS and not (rule.source.startswith("attr:")
                                                                     and len(rule.source) > 5):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Campo de origem inválido: {rule.source}")
        if rule.source or rule.default.strip():
            rules[col] = {"source": rule.source, "default": rule.default}
    m = _mapping(ctx, t.id, body.sheet_name)
    if m is None:
        m = TemplateMapping(organization_id=ctx.org_id, template_id=t.id, sheet_name=body.sheet_name,
                            header_row=body.header_row)
        ctx.db.add(m)
    m.header_row, m.columns, m.rules = body.header_row, [{k: c[k] for k in ("col", "header", "required")}
                                                         for c in columns], rules
    audit.record(ctx.db, "template.mapping_saved", user_id=ctx.user.id, org_id=ctx.org_id, target_type="template",
                 target_id=t.id, sheet=body.sheet_name, mapped=len(rules))
    ctx.db.commit()
    return get_mapping(template_id, body.sheet_name, body.header_row, ctx)


@router.post("/templates/{template_id}/mapping/copy-from/{source_id}", response_model=ColumnsOut)
def copy_mapping(template_id: uuid.UUID, source_id: uuid.UUID, sheet: str,
                 ctx: OrgContext = Depends(require("catalog.write"))) -> ColumnsOut:
    """Reuses a mapping from another template of the organization, matching columns by header text (letters may
    move between versions). Unmatched columns are left for review."""
    t, src = _template(ctx, template_id), _template(ctx, source_id)
    s = _sheet(t, sheet)
    old = _mapping(ctx, src.id, sheet)
    if old is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "O template de origem não tem mapeamento para esta aba.")
    layout_row = (s.get("layout") or {}).get("header_row") or old.header_row
    columns = sheet_columns(t.structure, sheet, layout_row)
    by_header = {norm_header(c["header"]): c["col"] for c in columns}
    old_headers = {c["col"]: c["header"] for c in old.columns}
    rules = {}
    for col, rule in old.rules.items():
        new_col = by_header.get(norm_header(old_headers.get(col, "")))
        if new_col:
            rules[new_col] = rule
    return save_mapping(template_id, MappingIn(sheet_name=sheet, header_row=layout_row,
                                               rules={k: RuleIn(**v) for k, v in rules.items()}), ctx)


def norm_header(text: str) -> str:
    return " ".join(str(text).lower().split())


# --- batches ----------------------------------------------------------------------------------------------------
LOCKED = {BatchStatus.SENT_EXTERNAL, BatchStatus.RESULT_RECEIVED, BatchStatus.DONE}


class BatchIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class BatchPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    seller_account_id: uuid.UUID | None = None
    template_id: uuid.UUID | None = None
    sheet_name: str | None = Field(default=None, max_length=64)


class BatchOut(BaseModel):
    id: uuid.UUID
    name: str
    marketplace: str
    status: str
    seller_account_id: uuid.UUID | None
    seller_account_label: str | None
    template_id: uuid.UUID | None
    template_filename: str | None
    template_expired: bool
    sheet_name: str
    items: int
    validation: dict
    history: list[dict]
    created_at: UtcDatetime
    updated_at: UtcDatetime


def _batch(ctx: OrgContext, batch_id: uuid.UUID) -> ListingBatch:
    b = ctx.db.scalar(select(ListingBatch).where(ListingBatch.id == batch_id,
                                                 ListingBatch.organization_id == ctx.org_id))
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lote não encontrado.")
    return b


def _batch_out(ctx: OrgContext, b: ListingBatch) -> BatchOut:
    account = ctx.db.get(SellerAccount, b.seller_account_id) if b.seller_account_id else None
    template = ctx.db.get(MarketplaceTemplate, b.template_id) if b.template_id else None
    items = ctx.db.scalar(select(func.count()).select_from(ListingBatchItem).where(ListingBatchItem.batch_id == b.id))
    return BatchOut(id=b.id, name=b.name, marketplace=b.marketplace, status=b.status,
                    seller_account_id=b.seller_account_id, seller_account_label=account.label if account else None,
                    template_id=b.template_id, template_filename=template.original_filename if template else None,
                    template_expired=bool(template and template.deadline_date and template.deadline_date < _today()),
                    sheet_name=b.sheet_name, items=items or 0, validation=b.validation or {}, history=b.history or [],
                    created_at=b.created_at, updated_at=b.updated_at)


def _log(ctx: OrgContext, b: ListingBatch, event: str, **detail) -> None:
    b.history = [*(b.history or []), {"at": utcnow().isoformat(), "by": ctx.user.name, "event": event, **detail}]


def _editable(b: ListingBatch) -> None:
    if b.status in LOCKED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Lote já enviado ao Mercado Livre; não pode ser alterado.")


def _reset(ctx: OrgContext, b: ListingBatch) -> None:
    """Any content change invalidates the previous validation."""
    if b.status != BatchStatus.DRAFT:
        _log(ctx, b, "status", status=BatchStatus.DRAFT, reason="conteúdo alterado")
    b.status, b.validation = BatchStatus.DRAFT, {}


@router.get("/batches", response_model=list[BatchOut])
def list_batches(ctx: OrgContext = Depends(require("catalog.read"))) -> list[BatchOut]:
    rows = ctx.db.scalars(select(ListingBatch).where(ListingBatch.organization_id == ctx.org_id)
                          .order_by(ListingBatch.updated_at.desc())).all()
    return [_batch_out(ctx, b) for b in rows]


@router.post("/batches", response_model=BatchOut, status_code=201)
def create_batch(body: BatchIn, ctx: OrgContext = Depends(require("catalog.write"))) -> BatchOut:
    b = ListingBatch(organization_id=ctx.org_id, name=body.name.strip(), marketplace=MARKETPLACE,
                     status=BatchStatus.DRAFT, validation={}, history=[], created_by=ctx.user.id)
    _log(ctx, b, "created")
    ctx.db.add(b)
    audit.record(ctx.db, "batch.created", user_id=ctx.user.id, org_id=ctx.org_id, target_type="batch",
                 target_id=b.id, name=b.name)
    ctx.db.commit()
    return _batch_out(ctx, b)


@router.get("/batches/{batch_id}", response_model=BatchOut)
def get_batch(batch_id: uuid.UUID, ctx: OrgContext = Depends(require("catalog.read"))) -> BatchOut:
    return _batch_out(ctx, _batch(ctx, batch_id))


@router.patch("/batches/{batch_id}", response_model=BatchOut)
def update_batch(batch_id: uuid.UUID, body: BatchPatch,
                 ctx: OrgContext = Depends(require("catalog.write"))) -> BatchOut:
    b = _batch(ctx, batch_id)
    _editable(b)
    sent = body.model_fields_set
    if body.name:
        b.name = body.name.strip()
    if "seller_account_id" in sent:
        if body.seller_account_id:
            _account(ctx, body.seller_account_id)
        if body.seller_account_id != b.seller_account_id:
            b.seller_account_id, b.template_id, b.sheet_name = body.seller_account_id, None, ""
            _reset(ctx, b)
    if "template_id" in sent:
        if body.template_id:
            t = _template(ctx, body.template_id)
            # Sheets are only accepted by the account that downloaded them (P1 p.8).
            if t.seller_account_id != b.seller_account_id:
                raise HTTPException(status.HTTP_409_CONFLICT, "O template pertence a outra conta de vendedor. "
                                                              "O Mercado Livre só aceita planilhas baixadas da "
                                                              "própria conta.")
            if t.status != TemplateStatus.INSPECTED:
                raise HTTPException(status.HTTP_409_CONFLICT, "Template inválido ou arquivado.")
        if body.template_id != b.template_id:
            b.template_id, b.sheet_name = body.template_id, ""
            _reset(ctx, b)
    if body.sheet_name is not None and body.sheet_name != b.sheet_name:
        if not b.template_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Escolha o template antes da aba.")
        _sheet(_template(ctx, b.template_id), body.sheet_name)
        b.sheet_name = body.sheet_name
        _reset(ctx, b)
    ctx.db.commit()
    return _batch_out(ctx, b)


class ItemsIn(BaseModel):
    mode: Literal["add", "remove", "replace"] = "add"
    product_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20_000)
    all_matching: dict | None = None  # {"q": str, "status": str}: adds every product matching the catalog filter


@router.put("/batches/{batch_id}/items", response_model=BatchOut)
def set_items(batch_id: uuid.UUID, body: ItemsIn, ctx: OrgContext = Depends(require("catalog.write"))) -> BatchOut:
    b = _batch(ctx, batch_id)
    _editable(b)
    ids = set(body.product_ids)
    if body.all_matching is not None:
        cond = [Product.organization_id == ctx.org_id]
        q = str(body.all_matching.get("q") or "").strip()
        if q:
            like = f"%{q.replace('%', '').replace('_', '')}%"
            cond.append(or_(Product.name.ilike(like), Product.sku.ilike(like), Product.brand.ilike(like)))
        if body.all_matching.get("status") in {s.value for s in ProductStatus}:
            cond.append(Product.status == body.all_matching["status"])
        ids |= set(ctx.db.scalars(select(Product.id).where(*cond)))
    # Only ids of this organization survive (foreign ids are silently dropped, never linked).
    valid = set(ctx.db.scalars(select(Product.id).where(Product.organization_id == ctx.org_id,
                                                        Product.id.in_(ids)))) if ids else set()
    current = set(ctx.db.scalars(select(ListingBatchItem.product_id).where(ListingBatchItem.batch_id == b.id)))
    target = {"add": current | valid, "remove": current - valid, "replace": valid}[body.mode]
    for pid in target - current:
        ctx.db.add(ListingBatchItem(organization_id=ctx.org_id, batch_id=b.id, product_id=pid))
    removed = current - target
    if removed:
        for item in ctx.db.scalars(select(ListingBatchItem).where(ListingBatchItem.batch_id == b.id,
                                                                  ListingBatchItem.product_id.in_(removed))):
            ctx.db.delete(item)
    if target != current:
        _log(ctx, b, "items", added=len(target - current), removed=len(removed))
        _reset(ctx, b)
    ctx.db.commit()
    return _batch_out(ctx, b)


@router.get("/batches/{batch_id}/items", response_model=list[str])
def list_items(batch_id: uuid.UUID, ctx: OrgContext = Depends(require("catalog.read"))) -> list[str]:
    b = _batch(ctx, batch_id)
    return [str(i) for i in ctx.db.scalars(select(ListingBatchItem.product_id)
                                           .where(ListingBatchItem.batch_id == b.id))]


def _context(ctx: OrgContext, b: ListingBatch) -> TemplateContext | None:
    if not b.template_id:
        return None
    t = _template(ctx, b.template_id)
    m = _mapping(ctx, t.id, b.sheet_name) if b.sheet_name else None
    return TemplateContext(deadline=t.deadline_date, deadline_confirmed=t.deadline_confirmed,
                           columns=m.columns if m else [], rules=m.rules if m else {})


def _layout(ctx: OrgContext, b: ListingBatch) -> tuple[MarketplaceTemplate, dict] | None:
    """Official layout of the batch's sheet (inspector v2), when known."""
    if not b.template_id or not b.sheet_name:
        return None
    t = _template(ctx, b.template_id)
    sheet = next((s for s in (t.structure or {}).get("sheets", []) if s["name"] == b.sheet_name), None)
    layout = (sheet or {}).get("layout")
    return (t, layout) if layout and layout.get("data_start_row") else None


def _build(ctx: OrgContext, b: ListingBatch, products):
    found = _layout(ctx, b)
    if not found:
        return None, None, []
    t, layout = found
    m = _mapping(ctx, t.id, b.sheet_name)
    rows = build_rows(products, layout, m.rules if m else {}, rules_for_batch(ctx.db, ctx.org_id, b))
    validate_rows(rows, layout, products)
    return t, layout, rows


class ProductReport(BaseModel):
    product_id: str
    sku: str
    name: str
    rows: int
    errors: int
    warnings: int
    issues: list[dict]


class ValidationOut(BaseModel):
    summary: dict
    template_issues: list[dict]
    batch_issues: list[dict]
    products: list[ProductReport]


def _run_validation(ctx: OrgContext, b: ListingBatch):
    ids = list(ctx.db.scalars(select(ListingBatchItem.product_id).where(ListingBatchItem.batch_id == b.id)))
    products = load_products(ctx.db, ctx.org_id, ids)
    template_issues = validate_template(_context(ctx, b), _today())
    if not b.seller_account_id:
        template_issues.insert(0, Issue("account_missing", "error", "documentacao", "Nenhuma conta de vendedor.",
                                        "Escolha a conta que baixou a planilha.", "account", "P1 p.8"))
    t, layout, sheet_rows_built = _build(ctx, b, products)
    if layout:
        # With the official layout, required columns are checked per row (template defaults + mapping + rules),
        # which is more precise than "column has a mapping": the file pre-fills some required columns itself.
        template_issues = [i for i in template_issues if i.code != "required_unmapped"]
    row_count = len(sheet_rows_built) if layout else sum(sheet_rows(p) for p in products)
    batch_issues = [i for i in [batch_size_issue(row_count)] if i]
    if layout and row_count > (layout.get("capacity") or 0):
        batch_issues.append(Issue("sheet_capacity", "error", "template",
                                  f"A aba comporta {layout['capacity']} linhas; o lote gera {row_count}.",
                                  "Divida o lote.", "batch", "Template: linhas com fórmulas"))
    if not products:
        batch_issues.append(Issue("batch_empty", "error", "interna", "Nenhum produto selecionado.",
                                  "Selecione produtos do catálogo.", "items"))
    per_product: dict[str, list[Issue]] = {}
    for r in sheet_rows_built:
        per_product.setdefault(r.product_id, []).extend(r.issues)
    reports = []
    for p in products:
        # With an official layout the template decides required columns; the generic photo/brand advice stays.
        issues = validate_product(p) + per_product.get(p.id, [])
        reports.append(ProductReport(product_id=p.id, sku=p.sku, name=p.name, rows=sheet_rows(p),
                                     errors=sum(i.severity == "error" for i in issues),
                                     warnings=sum(i.severity == "warning" for i in issues),
                                     issues=[i.as_dict() for i in issues]))
    reports.sort(key=lambda r: (-r.errors, -r.warnings, r.name))
    blocking = any(i.severity == "error" for i in template_issues + batch_issues) or any(r.errors for r in reports)
    summary = {"validated_at": utcnow().isoformat(), "products": len(products), "rows": row_count,
               "complete": sum(1 for r in reports if not r.errors and not r.warnings),
               "with_errors": sum(1 for r in reports if r.errors),
               "with_warnings": sum(1 for r in reports if r.warnings and not r.errors),
               "errors_total": sum(r.errors for r in reports) + sum(i.severity == "error"
                                                                    for i in template_issues + batch_issues),
               "ready": not blocking, "writer_available": bool(layout)}
    return products, template_issues, batch_issues, reports, summary, (t, layout, sheet_rows_built)


@router.post("/batches/{batch_id}/validate", response_model=ValidationOut)
def validate_batch(batch_id: uuid.UUID, ctx: OrgContext = Depends(require("catalog.write"))) -> ValidationOut:
    b = _batch(ctx, batch_id)
    _, template_issues, batch_issues, reports, summary, _ = _run_validation(ctx, b)
    if b.status not in LOCKED and b.status != BatchStatus.EXPORTED:
        new = BatchStatus.READY if summary["ready"] else BatchStatus.NEEDS_FIX
        if new != b.status:
            _log(ctx, b, "status", status=new)
        b.status = new
    b.validation = summary
    ctx.db.commit()
    return ValidationOut(summary=summary, template_issues=[i.as_dict() for i in template_issues],
                         batch_issues=[i.as_dict() for i in batch_issues], products=reports)


@router.get("/batches/{batch_id}/preview")
def preview_batch(batch_id: uuid.UUID, limit: int = 50,
                  ctx: OrgContext = Depends(require("catalog.read"))) -> dict:
    """Values that go into each data row (official layout: final cell values, MLA-written ones flagged)."""
    b = _batch(ctx, batch_id)
    ids = list(ctx.db.scalars(select(ListingBatchItem.product_id).where(ListingBatchItem.batch_id == b.id)))
    products = load_products(ctx.db, ctx.org_id, ids)
    t, layout, rows = _build(ctx, b, products)
    limit = max(1, min(limit, 500))
    if layout:
        cols = [{"col": c["col"], "header": c["header"], "required": c["required"]}
                for c in layout["columns"] if c.get("writable")]
        return {"columns": cols, "total_rows": len(rows), "first_row": layout["data_start_row"],
                "rows": [{"product_id": r.product_id, "sku": r.sku, "values": {k: str(v) for k, v in r.final.items()},
                          "written": sorted(r.values), "rules": [list(a) for a in r.applied]} for r in rows[:limit]]}
    tc = _context(ctx, b)
    if tc is None or not tc.columns:
        raise HTTPException(status.HTTP_409_CONFLICT, "Confirme template, aba e mapeamento antes de revisar.")
    prev = preview_rows(products, tc)
    return {"columns": tc.columns, "rows": prev[:limit], "total_rows": len(prev)}


class ExportOut(BaseModel):
    id: uuid.UUID
    sheet_name: str
    rows: int
    sha256: str
    size_bytes: int
    rules_applied: list
    checks: dict
    created_at: UtcDatetime


@router.post("/batches/{batch_id}/export", response_model=ExportOut, status_code=201)
def export_batch(batch_id: uuid.UUID, ctx: OrgContext = Depends(require("catalog.write"))) -> ExportOut:
    """Fills a copy of the account's official file. Never publishes anything."""
    b = _batch(ctx, batch_id)
    _editable(b)
    _, template_issues, batch_issues, reports, summary, (t, layout, rows) = _run_validation(ctx, b)
    if not layout:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este template não tem a estrutura oficial reconhecida; "
                                                      "não é possível gerar a planilha.")
    if not summary["ready"]:
        b.validation, b.status = summary, BatchStatus.NEEDS_FIX
        ctx.db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, f"O lote tem {summary['errors_total']} erro(s); corrija antes "
                                                      "de gerar a planilha.")
    original = ctx.storage.read(ctx.org_id, t.storage_key)
    if hashlib.sha256(original).hexdigest() != t.sha256:
        raise HTTPException(status.HTTP_409_CONFLICT, "O arquivo original do template não confere com o registrado.")
    try:
        result = workbook_writer.fill(original, b.sheet_name, layout, [r.values for r in rows])
    except workbook_writer.WriterError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    problems = workbook_writer.verify(original, result.data, result.sheet_part)
    if problems:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            "A verificação de integridade falhou; nada foi gerado: " + "; ".join(problems[:3]))
    export_id = uuid.uuid4()
    key = ctx.storage.put(ctx.org_id, "exports", f"{export_id}.xlsx", result.data)
    applied = sorted({tuple(a) for r in rows for a in r.applied})
    e = BatchExport(id=export_id, organization_id=ctx.org_id, batch_id=b.id, template_id=t.id,
                    sheet_name=b.sheet_name, storage_key=key, sha256=hashlib.sha256(result.data).hexdigest(),
                    size_bytes=len(result.data), rows=result.rows_written, rules_applied=[list(a) for a in applied],
                    checks={"integrity": "ok", "cells_written": result.cells_written,
                            "recalc_on_open": True, "template_sha256": t.sha256}, created_by=ctx.user.id)
    ctx.db.add(e)
    b.status, b.validation = BatchStatus.EXPORTED, summary
    _log(ctx, b, "exported", rows=result.rows_written, rules=len(applied), export=str(export_id))
    audit.record(ctx.db, "batch.exported", user_id=ctx.user.id, org_id=ctx.org_id, target_type="batch",
                 target_id=b.id, rows=result.rows_written)
    ctx.db.commit()
    return ExportOut(id=e.id, sheet_name=e.sheet_name, rows=e.rows, sha256=e.sha256, size_bytes=e.size_bytes,
                     rules_applied=e.rules_applied, checks=e.checks, created_at=e.created_at)


@router.get("/batches/{batch_id}/exports", response_model=list[ExportOut])
def list_exports(batch_id: uuid.UUID, ctx: OrgContext = Depends(require("catalog.read"))) -> list[ExportOut]:
    b = _batch(ctx, batch_id)
    rows = ctx.db.scalars(select(BatchExport).where(BatchExport.batch_id == b.id,
                                                    BatchExport.organization_id == ctx.org_id)
                          .order_by(BatchExport.created_at.desc())).all()
    return [ExportOut(id=e.id, sheet_name=e.sheet_name, rows=e.rows, sha256=e.sha256, size_bytes=e.size_bytes,
                      rules_applied=e.rules_applied, checks=e.checks, created_at=e.created_at) for e in rows]


@router.get("/batches/{batch_id}/exports/{export_id}/file")
def download_export(batch_id: uuid.UUID, export_id: uuid.UUID,
                    ctx: OrgContext = Depends(require("catalog.read"))) -> Response:
    b = _batch(ctx, batch_id)
    e = ctx.db.scalar(select(BatchExport).where(BatchExport.id == export_id, BatchExport.batch_id == b.id,
                                                BatchExport.organization_id == ctx.org_id))
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exportação não encontrada.")
    data = ctx.storage.read(ctx.org_id, e.storage_key)
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", f"MLA-{b.name}")[:60] + f"-{e.created_at:%Y%m%d-%H%M}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


class ConfirmIn(BaseModel):
    note: str = Field(default="", max_length=500)


@router.post("/batches/{batch_id}/confirm-sent", response_model=BatchOut)
def confirm_sent(batch_id: uuid.UUID, body: ConfirmIn,
                 ctx: OrgContext = Depends(require("catalog.write"))) -> BatchOut:
    """The user states they uploaded the exported file in the Anunciador em massa (P1 p.6-7)."""
    b = _batch(ctx, batch_id)
    if b.status != BatchStatus.EXPORTED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Só é possível confirmar o envio de um lote exportado.")
    b.status = BatchStatus.SENT_EXTERNAL
    _log(ctx, b, "status", status=b.status, evidence="confirmação do usuário", note=body.note)
    ctx.db.commit()
    return _batch_out(ctx, b)


@router.post("/batches/{batch_id}/confirm-result", response_model=BatchOut)
def confirm_result(batch_id: uuid.UUID, body: ConfirmIn,
                   ctx: OrgContext = Depends(require("catalog.write"))) -> BatchOut:
    """The user states Mercado Livre's e-mail arrived (P1 p.8). Rejected rows need the error file (pending)."""
    b = _batch(ctx, batch_id)
    if b.status != BatchStatus.SENT_EXTERNAL:
        raise HTTPException(status.HTTP_409_CONFLICT, "Confirme primeiro que a planilha foi enviada.")
    b.status = BatchStatus.RESULT_RECEIVED
    _log(ctx, b, "status", status=b.status, evidence="e-mail do Mercado Livre informado pelo usuário",
         note=body.note)
    ctx.db.commit()
    return _batch_out(ctx, b)

