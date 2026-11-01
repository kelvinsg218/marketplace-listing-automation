"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, Download, Eye, EyeOff } from "lucide-react";
import { api, ApiError, can, type Mapping, type Template } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { fmtDate, SOURCE_LABEL, TemplateStatusBadge } from "@/components/listing-ui";
import { Alert, Badge, Button, Card, cx, Input, PageHeader, Select, Skeleton } from "@/components/ui";

const MARKER_LABEL: Record<string, string> = {
  required: "Obrigatório", error_summary: "Resumo de erros", catalog_code: "Código de catálogo ML", photos: "Fotos",
  catalog_optional_note: "Dispensável para catálogo",
};

function DeadlineCard({ t, onChange }: { t: Template; onChange: (t: Template) => void }) {
  const { org, role } = useSession();
  const [date, setDate] = useState(t.deadline_date ?? "");
  const [err, setErr] = useState<string | null>(null);
  const found = t.structure?.deadline;
  async function patch(body: object) {
    setErr(null);
    try { onChange(await api<Template>(`/orgs/${org!.id}/templates/${t.id}`, { method: "PATCH", body })); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Falha."); }
  }
  return (
    <Card className="p-5">
      <h2 className="text-sm font-semibold">Data limite de envio</h2>
      <p className="mt-1 text-xs text-faint">A aba Ajuda informa até quando a planilha pode ser enviada; depois disso é preciso baixar outra (P2 p.1).</p>
      <div className="mt-4 text-sm">
        {found ? (
          <p>Encontrado em <span className="font-mono text-xs">{found.sheet ?? "Ajuda"}!{found.cell}</span>: <span className="text-muted">“{found.text}”</span></p>
        ) : <p className="text-warn">Nenhum texto de prazo encontrado no arquivo. Confira a aba Ajuda e informe a data.</p>}
        <p className="mt-2 flex flex-wrap items-center gap-2">Data: <strong>{fmtDate(t.deadline_date)}</strong>
          {t.deadline_date && !t.deadline_confirmed && <Badge tone="warn">ano deduzido — confirme</Badge>}
          {t.deadline_confirmed && <Badge tone="ok">confirmada</Badge>}
          {t.expired && <Badge tone="danger">vencida</Badge>}
        </p>
      </div>
      {can.write(role) && (
        <div className="mt-4 flex flex-wrap gap-2 items-center">
          {t.deadline_date && !t.deadline_confirmed && <Button size="sm" variant="primary" onClick={() => patch({ confirm_deadline: true })}>Confirmar {fmtDate(t.deadline_date)}</Button>}
          <Input type="date" aria-label="Informar data limite" className="w-44 h-8" value={date} onChange={(e) => setDate(e.target.value)} />
          <Button size="sm" disabled={!date} onClick={() => patch({ deadline_date: date })}>Salvar data</Button>
        </div>
      )}
      {err && <div className="mt-3"><Alert>{err}</Alert></div>}
    </Card>
  );
}

function MappingEditor({ t, sheet }: { t: Template; sheet: string }) {
  const { org, role } = useSession();
  const [row, setRow] = useState<number | null>(null);
  const path = `/orgs/${org!.id}/templates/${t.id}/mapping?sheet=${encodeURIComponent(sheet)}${row ? `&header_row=${row}` : ""}`;
  const { data, error, loading, reload } = useApi<Mapping>(path);
  const [rules, setRules] = useState<Record<string, { source: string | null; default: string }>>({});
  const [msg, setMsg] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);
  const writable = can.write(role) && t.status === "inspected";

  useEffect(() => {
    if (!data) return;
    // Saved rules win; otherwise suggestions are pre-filled but nothing is saved until the user confirms.
    const initial: typeof rules = {};
    for (const c of data.columns) initial[c.col] = data.rules[c.col] ?? { source: data.header_row_confirmed ? null : c.suggestion, default: "" };
    setRules(initial);
  }, [data]);

  if (error) return <Alert>{error}</Alert>;
  if (loading && !data) return <Skeleton className="h-60" />;
  if (!data) return null;
  const requiredOpen = data.columns.filter((c) => c.required && !rules[c.col]?.source && !rules[c.col]?.default?.trim());

  async function save() {
    setMsg(null);
    try {
      await api(`/orgs/${org!.id}/templates/${t.id}/mapping`, { method: "PUT", body: { sheet_name: sheet, header_row: data!.header_row, rules } });
      setMsg({ tone: "ok", text: "Mapeamento salvo." });
      setRow(data!.header_row);
      reload(); // same URL when the row did not change: reload explicitly to show the confirmed state
    } catch (e) { setMsg({ tone: "danger", text: e instanceof ApiError ? e.message : "Falha ao salvar." }); }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-2">Linha de cabeçalho
          <Select className="h-8" value={data.header_row} onChange={(e) => setRow(Number(e.target.value))}>
            {Array.from({ length: 15 }, (_, i) => i + 1).map((r) => (
              <option key={r} value={r}>{r}{data.header_candidates.some((c) => c.row === r) ? " (sugerida)" : ""}</option>
            ))}
          </Select>
        </label>
        {data.header_row_confirmed ? <Badge tone="ok">confirmada</Badge> : <Badge tone="warn">sugestão — confirme ao salvar</Badge>}
        {requiredOpen.length > 0 && <Badge tone="danger">{requiredOpen.length} obrigatória(s) sem mapeamento</Badge>}
      </div>
      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
      <div className="overflow-x-auto rounded-md border border-line">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs uppercase tracking-wider text-faint bg-bg-2">
            <th className="px-3 py-2 font-semibold w-12">Col.</th><th className="px-3 py-2 font-semibold">Cabeçalho no arquivo</th>
            <th className="px-3 py-2 font-semibold">Campo do catálogo</th><th className="px-3 py-2 font-semibold">Valor padrão</th>
          </tr></thead>
          <tbody>
            {data.columns.map((c) => {
              const r = rules[c.col] ?? { source: null, default: "" };
              const isAttr = r.source?.startsWith("attr:");
              return (
                <tr key={c.col} className={cx("border-t border-line", c.required && !r.source && !r.default.trim() && "bg-danger/5")}>
                  <td className="px-3 py-2 font-mono text-xs text-faint">{c.col}</td>
                  <td className="px-3 py-2"><span className="font-medium">{c.header}</span> {c.required && <Badge tone="danger" className="ml-1">Obrigatório</Badge>}
                    {!data.header_row_confirmed && c.suggestion && <Badge tone="info" className="ml-1">sugestão</Badge>}</td>
                  <td className="px-3 py-2">
                    <div className="flex gap-2">
                      <Select aria-label={`Campo para ${c.header}`} className="h-8 min-w-44" disabled={!writable} value={isAttr ? "__attr" : r.source ?? ""}
                        onChange={(e) => setRules({ ...rules, [c.col]: { ...r, source: e.target.value === "__attr" ? "attr:" : e.target.value || null } })}>
                        <option value="">— não preencher —</option>
                        {Object.entries(data.source_fields).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                        <option value="__attr">Atributo personalizado…</option>
                      </Select>
                      {isAttr && <Input aria-label="Nome do atributo" className="h-8 w-36" placeholder="Ex.: Cor" disabled={!writable} value={r.source!.slice(5)}
                        onChange={(e) => setRules({ ...rules, [c.col]: { ...r, source: `attr:${e.target.value}` } })} />}
                    </div>
                  </td>
                  <td className="px-3 py-2"><Input aria-label={`Valor padrão para ${c.header}`} className="h-8" disabled={!writable} value={r.default}
                    onChange={(e) => setRules({ ...rules, [c.col]: { ...r, default: e.target.value } })} placeholder="Opcional" /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-faint">O MLA nunca inventa valores: coluna sem campo e sem valor padrão fica vazia; se for obrigatória, a validação acusa erro. “Resumo de erros” é do próprio arquivo e não deve ser mapeada.</p>
      {writable && <div className="flex justify-end"><Button variant="primary" onClick={save}>Salvar mapeamento</Button></div>}
    </div>
  );
}

function SheetPreview({ t, sheet }: { t: Template; sheet: string }) {
  const s = t.structure?.sheets.find((x) => x.name === sheet);
  if (!s) return null;
  const markerCells = new Map(s.markers.map((m) => [m.cell, m.key]));
  const cols = Math.min(s.preview[0]?.length ?? 0, 30);
  const letter = (n: number) => { let out = ""; for (let x = n; x > 0; x = Math.floor((x - 1) / 26)) out = String.fromCharCode(65 + ((x - 1) % 26)) + out; return out; };
  return (
    <div className="overflow-auto max-h-[420px] rounded-md border border-line">
      <table className="text-xs border-collapse">
        <thead className="sticky top-0 bg-bg-2"><tr><th className="px-2 py-1 text-faint border-r border-line" />{Array.from({ length: cols }, (_, c) => <th key={c} className="px-2 py-1 text-faint font-mono font-normal">{letter(c + 1)}</th>)}</tr></thead>
        <tbody>
          {s.preview.map((row, r) => (
            <tr key={r} className={cx(s.header_candidates.some((h) => h.row === r + 1) && "bg-accent-soft")}>
              <td className="sticky left-0 bg-bg-2 px-2 py-1 font-mono text-faint border-r border-line">{r + 1}</td>
              {row.slice(0, cols).map((v, c) => {
                const key = markerCells.get(`${letter(c + 1)}${r + 1}`);
                return <td key={c} title={v} className={cx("px-2 py-1 max-w-48 truncate whitespace-nowrap border-t border-line", key === "required" && "text-danger font-semibold", key && key !== "required" && "text-accent-2 font-semibold")}>{v}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Detail() {
  const { org } = useSession();
  const id = useSearchParams().get("id");
  const { data: t, error, loading, setData } = useApi<Template>(org && id ? `/orgs/${org.id}/templates/${id}` : null);
  const categories = useMemo(() => t?.structure?.sheets.filter((s) => !s.is_help) ?? [], [t]);
  const [sheet, setSheet] = useState<string>("");
  useEffect(() => { if (categories.length && !sheet) setSheet(categories.find((s) => s.state === "visible")?.name ?? categories[0].name); }, [categories, sheet]);
  const current = categories.find((s) => s.name === sheet);

  return (
    <>
      <Link href="/templates/" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg mb-4"><ArrowLeft className="size-4" />Templates</Link>
      {error ? <Alert>{error}</Alert> : loading && !t ? <Skeleton className="h-96" /> : t && (
        <>
          <PageHeader title={t.original_filename} description={`${t.seller_account_label} · ${SOURCE_LABEL[t.source]} · SHA-256 ${t.sha256.slice(0, 12)}…`}
            actions={<><TemplateStatusBadge t={t} /><a href={`/api/orgs/${org!.id}/templates/${t.id}/file`}><Button size="sm"><Download className="size-4" />Original</Button></a></>} />
          {t.warnings.length > 0 && <div className="mb-4 flex flex-col gap-2">{t.warnings.map((w) => <Alert key={w} tone="info">{w}</Alert>)}</div>}
          <Alert tone="info">Leitura somente: estes dados descrevem o arquivo enviado. Nada aqui foi confirmado pelo Mercado Livre como regra geral; cada categoria tem seu próprio formato (P2 p.2).</Alert>
          {t.status === "inspected" && (
            <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_360px] items-start">
              <div className="flex flex-col gap-6 min-w-0">
                <Card className="p-5">
                  <div className="flex flex-wrap items-center gap-3 mb-4">
                    <h2 className="text-base font-semibold">Aba de categoria</h2>
                    <Select aria-label="Aba" className="h-8" value={sheet} onChange={(e) => setSheet(e.target.value)}>
                      {categories.map((s) => <option key={s.name} value={s.name}>{s.name}{s.state !== "visible" ? " (oculta)" : ""}</option>)}
                    </Select>
                    {current && <span className="text-xs text-faint">{current.max_row} linhas × {current.max_column_letter} · {current.data_validations.length} validações · {current.formula_cells} fórmulas{current.protected ? " · protegida" : ""}</span>}
                  </div>
                  {current && current.state !== "visible" && <div className="mb-4"><Alert tone="info">Aba oculta: provavelmente listas internas do arquivo. Não recebe produtos.</Alert></div>}
                  {sheet && <SheetPreview t={t} sheet={sheet} />}
                  <p className="mt-2 text-xs text-faint">Linhas em destaque: candidatas a cabeçalho. Vermelho: “Obrigatório”. Laranja: outros marcadores da documentação.</p>
                </Card>
                {current && current.state === "visible" && (
                  <Card className="p-5"><h2 className="text-base font-semibold mb-4">Mapeamento de atributos</h2><MappingEditor key={sheet} t={t} sheet={sheet} /></Card>
                )}
              </div>
              <div className="flex flex-col gap-4">
                <DeadlineCard t={t} onChange={setData} />
                <Card className="p-5 text-sm">
                  <h2 className="text-sm font-semibold mb-3">Estrutura</h2>
                  <ul className="flex flex-col gap-1.5">
                    {t.structure?.sheets.map((s) => (
                      <li key={s.name} className="flex items-center gap-2">{s.state === "visible" ? <Eye className="size-3.5 text-faint" /> : <EyeOff className="size-3.5 text-faint" />}
                        <span className="truncate">{s.name}</span>{s.is_help && <Badge>Ajuda</Badge>}</li>
                    ))}
                  </ul>
                  {current && current.markers.length > 0 && (<>
                    <h3 className="mt-4 mb-2 text-xs font-semibold text-muted">Marcadores em “{current.name}”</h3>
                    <ul className="flex flex-col gap-1 text-xs">{current.markers.slice(0, 30).map((m) => <li key={m.cell + m.key}><span className="font-mono text-faint">{m.cell}</span> {MARKER_LABEL[m.key]}</li>)}</ul>
                  </>)}
                </Card>
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}

export default function TemplateDetailPage() {
  return <Suspense><Detail /></Suspense>;
}
