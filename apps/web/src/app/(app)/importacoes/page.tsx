"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, FileUp, History, Loader2 } from "lucide-react";
import { api, ApiError, apiUpload, can } from "@/lib/api";
import { when } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { Alert, Badge, Button, Card, cx, Input, PageHeader, Select } from "@/components/ui";

interface Job { id: string; filename: string; format: string; sheet: string; status: string; mapping: Record<string, string>; options: { update_existing?: boolean }; totals: { plan?: Record<string, number>; result?: Record<string, number>; error?: string }; report: { where: string; sku: string; action: string; changes?: string[]; issues: { severity: string; message: string }[] }[]; created_at: string }
interface Analysis { job: Job; headers: string[]; sheets: string[]; notes: string[]; preview: { where: string; values: Record<string, string> }[]; suggestions: { column: string; field: string; confidence: string; reason: string }[]; fields: { key: string; label: string; group: string }[] }
interface Profile { id: string; name: string; mapping: Record<string, string> }

const STATUS: Record<string, { label: string; tone: "neutral" | "ok" | "warn" | "danger" | "info" | "accent" }> = {
  analyzed: { label: "Analisado", tone: "neutral" }, planned: { label: "Simulado", tone: "info" }, running: { label: "Processando", tone: "accent" },
  done: { label: "Concluído", tone: "ok" }, failed: { label: "Falhou", tone: "danger" }, cancelled: { label: "Cancelado", tone: "neutral" },
};
const ACTION: Record<string, string> = { create: "Novos", update: "Atualizar", unchanged: "Sem mudança", variant: "Variações", skip: "Ignorados (já existem)", error: "Com erro" };

export default function ImportsPage() {
  const { org, role } = useSession();
  const base = `/orgs/${org!.id}`;
  const { data: history, reload } = useApi<Job[]>(`${base}/imports`);
  const { data: profiles, reload: reloadProfiles } = useApi<Profile[]>(`${base}/import-profiles`);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [updateExisting, setUpdateExisting] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [profileName, setProfileName] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  function load(a: Analysis) {
    setAnalysis(a); setJob(a.job);
    setMapping(Object.fromEntries(a.suggestions.map((s) => [s.column, s.field])));
  }
  async function upload(f: File) {
    setBusy(true); setMsg(null);
    const fd = new FormData(); fd.append("file", f);
    try { load(await apiUpload<Analysis>(`${base}/imports`, fd)); reload(); }
    catch (e) { setMsg(e instanceof ApiError ? e.message : "Falha no envio."); }
    finally { setBusy(false); }
  }
  async function plan() {
    setBusy(true); setMsg(null);
    try { setJob(await api<Job>(`${base}/imports/${analysis!.job.id}/plan`, { method: "POST", body: { mapping, sheet: analysis!.job.sheet, update_existing: updateExisting } })); }
    catch (e) { setMsg(e instanceof ApiError ? e.message : "Falha na simulação."); }
    finally { setBusy(false); }
  }
  async function run() {
    setBusy(true); setMsg(null);
    try { setJob(await api<Job>(`${base}/imports/${job!.id}/run`, { method: "POST" })); }
    catch (e) { setMsg(e instanceof ApiError ? e.message : "Falha."); setBusy(false); }
  }
  useEffect(() => {
    if (!job || job.status !== "running") { if (job && ["done", "failed", "cancelled"].includes(job.status)) { setBusy(false); reload(); } return; }
    const t = setInterval(async () => {
      const list = await api<Job[]>(`${base}/imports`);
      const fresh = list.find((j) => j.id === job.id);
      if (fresh) setJob(fresh);
    }, 1200);
    return () => clearInterval(t);
  }, [job, base, reload]);

  const planT = job?.totals.plan;
  const result = job?.totals.result;
  const groups = analysis ? [...new Set(analysis.fields.map((f) => f.group))] : [];

  return (
    <>
      <PageHeader title="Importações" description="Traga a base de produtos da sua empresa (XLSX, CSV, JSON ou XML) sem cadastrar um a um. Nada é gravado antes da simulação e da sua confirmação." />
      {msg && <div className="mb-4"><Alert>{msg}</Alert></div>}
      <div className="grid gap-6 xl:grid-cols-[1fr_320px] items-start">
        <div className="flex flex-col gap-6 min-w-0">
          <Card className="p-5">
            <h2 className="text-base font-semibold mb-1">1. Arquivo</h2>
            <p className="text-xs text-faint mb-4">Até 50 MB. Códigos com zero à esquerda são preservados quando a coluna está como texto. PDF e ZIP ainda não estão liberados nesta tela.</p>
            <input ref={fileRef} type="file" accept=".xlsx,.csv,.json,.xml" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
            <Button variant="primary" busy={busy && !analysis} disabled={!can.write(role)} onClick={() => fileRef.current?.click()}><FileUp className="size-4" />Escolher arquivo</Button>
            {analysis && (
              <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
                <Badge tone="info">{analysis.job.format.toUpperCase()}</Badge><span className="font-medium">{analysis.job.filename}</span>
                {analysis.sheets.length > 1 && (
                  <Select aria-label="Aba" className="h-8" value={analysis.job.sheet} onChange={async (e) => load(await api<Analysis>(`${base}/imports/${analysis.job.id}?sheet=${encodeURIComponent(e.target.value)}`))}>
                    {analysis.sheets.map((s) => <option key={s}>{s}</option>)}
                  </Select>
                )}
                {analysis.notes.map((n) => <span key={n} className="text-xs text-warn">{n}</span>)}
              </div>
            )}
          </Card>

          {analysis && (
            <Card className="p-5">
              <h2 className="text-base font-semibold mb-1">2. Pré-visualização e mapeamento</h2>
              <p className="text-xs text-faint mb-4">Sugestões pelo nome das colunas (ex.: “EAN” → GTIN, “Saldo” → Estoque). Confira: colunas desconhecidas podem virar atributos personalizados em vez de serem descartadas.</p>
              <div className="flex flex-wrap items-end gap-2 mb-4">
                {profiles && profiles.length > 0 && (
                  <Select aria-label="Aplicar perfil" className="h-8" defaultValue="" onChange={(e) => { const p = profiles.find((x) => x.id === e.target.value); if (p) setMapping({ ...mapping, ...Object.fromEntries(Object.entries(p.mapping).filter(([c]) => analysis.headers.includes(c))) }); }}>
                    <option value="">Aplicar perfil salvo…</option>{profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </Select>
                )}
                <Input aria-label="Nome do perfil" className="h-8 w-48" placeholder="Nome do perfil (ex.: ERP)" value={profileName} onChange={(e) => setProfileName(e.target.value)} />
                <Button size="sm" disabled={!profileName.trim()} onClick={async () => { await api(`${base}/import-profiles`, { method: "POST", body: { name: profileName, mapping } }); setProfileName(""); reloadProfiles(); }}>Salvar perfil</Button>
              </div>
              <div className="overflow-x-auto rounded-md border border-line">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-xs uppercase tracking-wider text-faint bg-bg-2"><th className="px-3 py-2">Coluna do arquivo</th><th className="px-3 py-2">Exemplos</th><th className="px-3 py-2">Campo no MLA</th></tr></thead>
                  <tbody>
                    {analysis.headers.map((h) => {
                      const s = analysis.suggestions.find((x) => x.column === h);
                      return (
                        <tr key={h} className="border-t border-line">
                          <td className="px-3 py-2 font-medium">{h}{s && s.confidence === "probable" && <Badge tone="warn" className="ml-2">confirme</Badge>}</td>
                          <td className="px-3 py-2 text-xs text-muted max-w-64 truncate">{analysis.preview.slice(0, 3).map((r) => r.values[h]).filter(Boolean).join(" · ") || "—"}</td>
                          <td className="px-3 py-2">
                            <Select aria-label={`Campo para ${h}`} className="h-8 min-w-52" value={mapping[h] ?? ""} onChange={(e) => setMapping({ ...mapping, [h]: e.target.value })}>
                              <option value="">— ignorar —</option>
                              <option value="attr">Atributo personalizado</option>
                              {groups.map((g) => <optgroup key={g} label={g}>{analysis.fields.filter((f) => f.group === g).map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}</optgroup>)}
                            </Select>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <label className="mt-4 flex items-center gap-2 text-sm"><input type="checkbox" checked={updateExisting} onChange={(e) => setUpdateExisting(e.target.checked)} className="size-4 accent-[var(--color-accent)]" />
                Atualizar produtos que já existem (mesmo SKU) — só os campos preenchidos no arquivo; nada é apagado</label>
              <div className="mt-4"><Button variant="primary" busy={busy && job?.status !== "running"} disabled={!can.write(role) || !Object.values(mapping).includes("sku") || ["running", "done"].includes(job?.status ?? "")} onClick={plan}>3. Simular importação</Button>
                {!Object.values(mapping).includes("sku") && <span className="ml-3 text-xs text-warn">Mapeie a coluna de SKU.</span>}</div>
            </Card>
          )}

          {job && planT && (
            <Card className="p-5">
              <h2 className="text-base font-semibold mb-3">4. Resultado da simulação {job.status === "planned" && <Badge tone="info">nada foi gravado ainda</Badge>}</h2>
              <div className="grid gap-3 grid-cols-2 md:grid-cols-4">
                {Object.entries(ACTION).map(([k, label]) => (planT[k] ?? 0) > 0 && (
                  <div key={k} className="rounded-md border border-line bg-bg-2 px-3 py-2"><p className="text-xs text-muted">{label}</p><p className={cx("text-xl font-bold tabular-nums", k === "error" && "text-danger")}>{planT[k]}</p></div>
                ))}
              </div>
              {job.status === "planned" && (
                <div className="mt-4 flex gap-2">
                  <Button variant="primary" busy={busy} onClick={run}>Confirmar e importar {planT.create + (planT.update ?? 0) + (planT.variant ?? 0)} item(ns)</Button>
                  <Button variant="ghost" onClick={async () => { setJob(await api<Job>(`${base}/imports/${job.id}/cancel`, { method: "POST" })); }}>Cancelar</Button>
                </div>
              )}
              {job.status === "running" && (
                <div className="mt-4 flex items-center gap-3 text-sm"><Loader2 className="size-4 animate-spin text-accent" />Processando {result?.processed ?? 0} de {planT.rows} linha(s)…
                  <Button size="sm" variant="ghost" onClick={async () => setJob(await api<Job>(`${base}/imports/${job.id}/cancel`, { method: "POST" }))}>Cancelar</Button></div>
              )}
              {result && job.status !== "running" && (
                <Alert tone={job.status === "done" ? "ok" : "danger"}>
                  <CheckCircle2 className="inline size-4 mr-1" />{STATUS[job.status]?.label}: {result.created} criado(s), {result.updated} atualizado(s), {result.variants} variação(ões), {result.skipped} ignorado(s), {result.errors} com erro. <Link href="/catalogo/" className="underline">Ver produtos</Link>
                </Alert>
              )}
              {job.totals.error && <Alert>{job.totals.error}</Alert>}
              {job.report.length > 0 && (
                <div className="mt-4 max-h-80 overflow-auto rounded-md border border-line">
                  <table className="w-full text-xs"><tbody>{job.report.map((r, i) => (
                    <tr key={i} className="border-t border-line"><td className="px-3 py-1.5 text-faint whitespace-nowrap">{r.where}</td><td className="px-3 py-1.5 font-mono">{r.sku || "—"}</td>
                      <td className="px-3 py-1.5"><Badge tone={r.action === "error" ? "danger" : r.action === "update" ? "info" : "neutral"}>{ACTION[r.action] ?? r.action}</Badge></td>
                      <td className="px-3 py-1.5">{r.issues.map((x) => x.message).join(" · ")}{r.changes && r.changes.length > 0 ? ` Campos: ${r.changes.join(", ")}` : ""}</td></tr>
                  ))}</tbody></table>
                </div>
              )}
            </Card>
          )}
        </div>

        <Card className="p-5">
          <h2 className="text-sm font-semibold flex items-center gap-2 mb-3"><History className="size-4 text-accent" />Histórico</h2>
          <ul className="flex flex-col gap-2 text-sm">
            {history?.length === 0 && <li className="text-muted">Nenhuma importação.</li>}
            {history?.map((j) => (
              <li key={j.id} className="rounded-md border border-line bg-bg-2 px-3 py-2">
                <p className="font-medium truncate">{j.filename}</p>
                <p className="text-xs text-faint">{when(j.created_at)} · <Badge tone={STATUS[j.status]?.tone}>{STATUS[j.status]?.label}</Badge>
                  {j.totals.result && ` · ${j.totals.result.created} novo(s), ${j.totals.result.updated} atualizado(s)`}</p>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}
