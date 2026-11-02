"""Central de Importações: upload -> analyze -> plan (dry run) -> run in background -> report."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from mla_api import audit
from mla_api.db import set_tenant, utcnow
from mla_api.deps import OrgContext, require
from mla_api.importing.mapping import field_by_key, suggest_mapping
from mla_api.importing.readers import SourceError
from mla_api.models import ImportJob, ImportProfile
from mla_api.schemas import UtcDatetime
from mla_api.services.catalog_import import (ALLOWED_FORMATS, CHUNK, MAX_IMPORT_BYTES, REPORT_LIMIT, commit_plan,
                                             open_from_bytes, plan_rows, target_fields)

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["imports"])
PREVIEW_ROWS = 20
SPECIAL_KEYS = {"", "attr", "spec", "images"}


class JobOut(BaseModel):
    id: uuid.UUID
    filename: str
    format: str
    sheet: str
    status: str
    mapping: dict
    options: dict
    totals: dict
    report: list
    created_at: UtcDatetime
    finished_at: UtcDatetime | None


class AnalysisOut(BaseModel):
    job: JobOut
    headers: list[str]
    sheets: list[str]
    notes: list[str]
    preview: list[dict]
    suggestions: list[dict]
    fields: list[dict]


def _out(j: ImportJob) -> JobOut:
    return JobOut(id=j.id, filename=j.filename, format=j.format, sheet=j.sheet, status=j.status, mapping=j.mapping,
                  options=j.options, totals=j.totals, report=j.report, created_at=j.created_at,
                  finished_at=j.finished_at)


def _job(ctx: OrgContext, job_id: uuid.UUID) -> ImportJob:
    j = ctx.db.scalar(select(ImportJob).where(ImportJob.id == job_id, ImportJob.organization_id == ctx.org_id))
    if j is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Importação não encontrada.")
    return j


def _source(ctx: OrgContext, j: ImportJob, sheet: str | None = None):
    data = ctx.storage.read(ctx.org_id, j.storage_key)
    try:
        return open_from_bytes(data, j.filename, sheet if sheet is not None else j.sheet)
    except SourceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


def _analysis(ctx: OrgContext, j: ImportJob, sheet: str | None = None) -> AnalysisOut:
    source, tmp = _source(ctx, j, sheet)
    try:
        preview = source.preview(PREVIEW_ROWS)
        info = source.info
        suggestions = suggest_mapping(info.headers, [r.values for r in preview])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return AnalysisOut(job=_out(j), headers=info.headers, sheets=info.sheets, notes=info.notes,
                       preview=[{"where": r.where, "values": r.values} for r in preview],
                       suggestions=[{"column": s.column, "field": s.field, "confidence": s.confidence,
                                     "reason": s.reason} for s in suggestions],
                       fields=target_fields())


@router.get("/imports", response_model=list[JobOut])
def list_imports(ctx: OrgContext = Depends(require("catalog.read"))) -> list[JobOut]:
    rows = ctx.db.scalars(select(ImportJob).where(ImportJob.organization_id == ctx.org_id)
                          .order_by(ImportJob.created_at.desc()).limit(100)).all()
    return [_out(j) for j in rows]


@router.post("/imports", response_model=AnalysisOut, status_code=201)
async def upload(file: UploadFile = File(...), ctx: OrgContext = Depends(require("catalog.write"))) -> AnalysisOut:
    name = Path(file.filename or "arquivo").name[:200]
    ext = Path(name).suffix.lower().lstrip(".")
    if ext not in ALLOWED_FORMATS:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            "Formatos aceitos: XLSX, CSV, JSON e XML. PDF e ZIP ainda não estão liberados aqui.")
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Arquivo acima de 50 MB; divida em partes.")
    try:
        source, tmp = open_from_bytes(data, name)
        shutil.rmtree(tmp, ignore_errors=True)
    except SourceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if source.info.format not in ALLOWED_FORMATS:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "O conteúdo não corresponde a XLSX, CSV, JSON ou XML.")
    job_id = uuid.uuid4()
    key = ctx.storage.put(ctx.org_id, "imports", f"{job_id}.{ext}", data)
    j = ImportJob(id=job_id, organization_id=ctx.org_id, filename=name, storage_key=key, format=source.info.format,
                  sheet=source.info.sheet or "", status="analyzed", mapping={}, options={}, totals={}, report=[],
                  created_by=ctx.user.id)
    ctx.db.add(j)
    audit.record(ctx.db, "import.uploaded", user_id=ctx.user.id, org_id=ctx.org_id, target_type="import",
                 target_id=j.id, filename=name)
    ctx.db.commit()
    return _analysis(ctx, j)


@router.get("/imports/{job_id}", response_model=AnalysisOut)
def get_import(job_id: uuid.UUID, sheet: str | None = None,
               ctx: OrgContext = Depends(require("catalog.read"))) -> AnalysisOut:
    return _analysis(ctx, _job(ctx, job_id), sheet)


class PlanIn(BaseModel):
    mapping: dict[str, str] = Field(max_length=500)
    sheet: str = Field(default="", max_length=120)
    update_existing: bool = False


def _check_mapping(mapping: dict[str, str], headers: list[str]) -> dict[str, str]:
    clean = {}
    for column, key in mapping.items():
        if column not in headers:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Coluna inexistente no arquivo: {column}")
        if key not in SPECIAL_KEYS and field_by_key("products", key) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Campo de destino inválido: {key}")
        clean[column] = key
    if "sku" not in clean.values():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Mapeie a coluna que contém o SKU.")
    return clean


@router.post("/imports/{job_id}/plan", response_model=JobOut)
def plan(job_id: uuid.UUID, body: PlanIn, ctx: OrgContext = Depends(require("catalog.write"))) -> JobOut:
    """Dry run over the whole file: nothing is written to the catalog."""
    j = _job(ctx, job_id)
    if j.status not in ("analyzed", "planned"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta importação já foi processada.")
    source, tmp = _source(ctx, j, body.sheet or None)
    try:
        mapping = _check_mapping(body.mapping, source.info.headers)
        totals = {"rows": 0, "create": 0, "update": 0, "unchanged": 0, "variant": 0, "skip": 0, "error": 0,
                  "warnings": 0}
        report = []
        for row_plan, _ in plan_rows(ctx.db, ctx.org_id, source, mapping, body.update_existing):
            totals["rows"] += 1
            totals[row_plan.action] += 1
            totals["warnings"] += sum(i["severity"] == "warning" for i in row_plan.issues)
            if (row_plan.issues or row_plan.action == "update") and len(report) < REPORT_LIMIT:
                report.append({"where": row_plan.where, "sku": row_plan.sku, "action": row_plan.action,
                               "changes": row_plan.changes, "issues": row_plan.issues})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    j.mapping, j.sheet, j.options = mapping, body.sheet or j.sheet, {"update_existing": body.update_existing}
    j.totals, j.report, j.status = {"plan": totals}, report, "planned"
    ctx.db.commit()
    return _out(j)


def run_import(app, org_id: uuid.UUID, job_id: uuid.UUID) -> None:
    """Background processing with its own session, tenant set, chunked commits and cancellation."""
    db = app.state.sessionmaker()
    set_tenant(db, org_id)
    try:
        j = db.get(ImportJob, job_id)
        data = app.state.storage.read(org_id, j.storage_key)
        source, tmp = open_from_bytes(data, j.filename, j.sheet)
        totals = {"processed": 0, "created": 0, "updated": 0, "variants": 0, "skipped": 0, "errors": 0}
        report: list = []

        def cancelled() -> bool:
            db.refresh(j, ["cancel_requested"])
            return j.cancel_requested
        try:
            chunk = []
            for item in plan_rows(db, org_id, source, j.mapping, j.options.get("update_existing", False), cancelled):
                chunk.append(item)
                if len(chunk) >= CHUNK:
                    _commit_chunk(db, org_id, j, chunk, totals, report)
                    chunk = []
                    if cancelled():
                        break
            if chunk and not j.cancel_requested:
                _commit_chunk(db, org_id, j, chunk, totals, report)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        j.status = "cancelled" if j.cancel_requested else "done"
        j.totals = {**(j.totals or {}), "result": totals}
        j.report = report[:REPORT_LIMIT]
        j.finished_at = utcnow()
        db.commit()
    except Exception as exc:  # recorded for the user; nothing half-written survives the failed chunk
        db.rollback()
        j = db.get(ImportJob, job_id)
        j.status, j.finished_at = "failed", utcnow()
        j.totals = {**(j.totals or {}), "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
        db.commit()
    finally:
        db.close()


def _commit_chunk(db, org_id, j, chunk, totals, report) -> None:
    try:
        counts = commit_plan(db, org_id, chunk)
        for plan, _ in chunk:
            totals["processed"] += 1
            if plan.action in ("skip", "unchanged"):
                totals["skipped"] += 1
            elif plan.action == "error":
                totals["errors"] += 1
            if plan.issues and len(report) < REPORT_LIMIT:
                report.append({"where": plan.where, "sku": plan.sku, "action": plan.action, "issues": plan.issues})
        for k in ("created", "updated", "variants"):
            totals[k] += counts[k]
        j.totals = {**(j.totals or {}), "result": dict(totals)}
        db.commit()
    except IntegrityError:
        db.rollback()
        for plan, _ in chunk:
            totals["processed"] += 1
            totals["errors"] += 1
            if len(report) < REPORT_LIMIT:
                report.append({"where": plan.where, "sku": plan.sku, "action": "error",
                               "issues": [{"severity": "error", "message": "Conflito ao gravar o bloco (SKU já existe)."}]})


@router.post("/imports/{job_id}/run", response_model=JobOut, status_code=202)
def run(job_id: uuid.UUID, request: Request, background: BackgroundTasks,
        ctx: OrgContext = Depends(require("catalog.write"))) -> JobOut:
    j = _job(ctx, job_id)
    if j.status != "planned":
        raise HTTPException(status.HTTP_409_CONFLICT, "Simule a importação antes de processar.")
    j.status = "running"
    audit.record(ctx.db, "import.started", user_id=ctx.user.id, org_id=ctx.org_id, target_type="import",
                 target_id=j.id, rows=(j.totals.get("plan") or {}).get("rows"))
    ctx.db.commit()
    background.add_task(run_import, request.app, ctx.org_id, j.id)
    return _out(j)


@router.post("/imports/{job_id}/cancel", response_model=JobOut)
def cancel(job_id: uuid.UUID, ctx: OrgContext = Depends(require("catalog.write"))) -> JobOut:
    j = _job(ctx, job_id)
    if j.status == "running":
        j.cancel_requested = True
    elif j.status in ("analyzed", "planned"):
        j.status, j.finished_at = "cancelled", utcnow()
    else:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta importação já terminou.")
    ctx.db.commit()
    return _out(j)


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    mapping: dict[str, str] = Field(max_length=500)


@router.get("/import-profiles")
def list_profiles(ctx: OrgContext = Depends(require("catalog.read"))) -> list[dict]:
    rows = ctx.db.scalars(select(ImportProfile).where(ImportProfile.organization_id == ctx.org_id)
                          .order_by(ImportProfile.name)).all()
    return [{"id": str(p.id), "name": p.name, "mapping": p.mapping} for p in rows]


@router.post("/import-profiles", status_code=201)
def save_profile(body: ProfileIn, ctx: OrgContext = Depends(require("catalog.write"))) -> dict:
    for key in body.mapping.values():
        if key not in SPECIAL_KEYS and field_by_key("products", key) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Campo de destino inválido: {key}")
    p = ctx.db.scalar(select(ImportProfile).where(ImportProfile.organization_id == ctx.org_id,
                                                  ImportProfile.name == body.name.strip()))
    if p is None:
        p = ImportProfile(organization_id=ctx.org_id, name=body.name.strip())
        ctx.db.add(p)
    p.mapping = body.mapping
    ctx.db.commit()
    return {"id": str(p.id), "name": p.name, "mapping": p.mapping}
