"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, Check, ChevronRight, Lock, Search } from "lucide-react";
import { api, ApiError, can, type Batch, type ExportRecord, type Mapping, type ProductPage, type SellerAccount, type Template, type Validation } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { BatchStatusBadge, fmtDate, IssueList, TemplateStatusBadge } from "@/components/listing-ui";
import { Alert, Badge, Button, Card, cx, Input, PageHeader, Select, Skeleton } from "@/components/ui";

type Step = { key: string; title: string; done: boolean; available: boolean };

// Required columns the official file already pre-fills (e.g. "Novo", "Clássico") are not missing.
const hasFileDefault = (v?: string | null) => !!v && v !== "Selecionar" && !v.startsWith("Insira ou selecione");

function Kpi({ label, value, tone }: { label: string; value: number | string; tone?: "ok" | "danger" | "warn" }) {
  return (
    <Card className="p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className={cx("mt-1 text-2xl font-bold tabular-nums", tone === "ok" && "text-ok", tone === "danger" && "text-danger", tone === "warn" && "text-warn")}>{value}</p>
    </Card>
  );
}

function Wizard({ id }: { id: string }) {
  const { org, role } = useSession();
  const base = `/orgs/${org!.id}/batches/${id}`;
  const { data: batch, error, setData: setBatch } = useApi<Batch>(base);
  const { data: accounts } = useApi<SellerAccount[]>(`/orgs/${org!.id}/seller-accounts`);
  const { data: templates } = useApi<Template[]>(`/orgs/${org!.id}/templates`);
  const { data: template } = useApi<Template>(batch?.template_id ? `/orgs/${org!.id}/templates/${batch.template_id}` : null);
  const { data: mapping } = useApi<Mapping>(batch?.template_id && batch.sheet_name ? `/orgs/${org!.id}/templates/${batch.template_id}/mapping?sheet=${encodeURIComponent(batch.sheet_name)}` : null);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [step, setStep] = useState(0);
  const [msg, setMsg] = useState<{ tone: "ok" | "danger" | "info"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const writable = can.write(role) && !!batch && !["sent_external", "result_received", "done"].includes(batch.status);

  async function patch(body: object) {
    setMsg(null);
    try { setBatch(await api<Batch>(base, { method: "PATCH", body })); setValidation(null); }
    catch (e) { setMsg({ tone: "danger", text: e instanceof ApiError ? e.message : "Falha." }); }
  }
  async function validate() {
    setBusy(true); setMsg(null);
    try { setValidation(await api<Validation>(`${base}/validate`, { method: "POST" })); setBatch(await api<Batch>(base)); }
    catch (e) { setMsg({ tone: "danger", text: e instanceof ApiError ? e.message : "Falha." }); }
    finally { setBusy(false); }
  }

  const accountTemplates = useMemo(() => (templates ?? []).filter((t) => t.seller_account_id === batch?.seller_account_id && t.status === "inspected"), [templates, batch]);
  const categorySheets = template?.sheets.filter((s) => !s.is_help && s.state === "visible") ?? [];
  const requiredOpen = mapping ? mapping.columns.filter((c) => c.required && !mapping.rules[c.col]?.source && !mapping.rules[c.col]?.default?.trim() && !hasFileDefault(c.template_default)).length : 0;
  const v = batch?.validation ?? {};

  if (error) return <Alert>{error}</Alert>;
  if (!batch) return <Skeleton className="h-96" />;

  const steps: Step[] = [
    { key: "mkt", title: "Marketplace", done: true, available: true },
    { key: "acc", title: "Conta", done: !!batch.seller_account_id, available: true },
    { key: "tpl", title: "Template", done: !!batch.template_id && !!batch.sheet_name, available: !!batch.seller_account_id },
    { key: "prd", title: "Produtos", done: batch.items > 0, available: true },
    { key: "map", title: "Mapeamento", done: !!mapping?.header_row_confirmed && requiredOpen === 0, available: !!batch.sheet_name },
    { key: "val", title: "Validar", done: !!v.validated_at, available: batch.items > 0 },
    { key: "fix", title: "Corrigir", done: v.ready === true, available: !!validation },
    { key: "rev", title: "Revisar", done: false, available: !!mapping?.header_row_confirmed },
    { key: "exp", title: "Exportar", done: ["exported", "sent_external", "result_received", "done"].includes(batch.status), available: true },
    { key: "snd", title: "Enviar ao ML", done: ["sent_external", "result_received", "done"].includes(batch.status), available: true },
    { key: "res", title: "Importar resultados", done: ["result_received", "done"].includes(batch.status), available: true },
    { key: "rep", title: "Reprocessar", done: false, available: true },
  ];

  return (
    <>
      <PageHeader title={batch.name} description="Fluxo guiado do Anunciador em massa. Cada etapa salva no lote."
        actions={<BatchStatusBadge status={batch.status} />} />
      <div className="mb-5 grid gap-3 grid-cols-2 lg:grid-cols-5">
        <Kpi label="Produtos selecionados" value={batch.items} />
        <Kpi label="Linhas na planilha" value={v.rows ?? "—"} />
        <Kpi label="Completos" value={v.complete ?? "—"} tone="ok" />
        <Kpi label="Com erros" value={v.with_errors ?? "—"} tone={v.with_errors ? "danger" : undefined} />
        <Kpi label="Pronto para exportar" value={v.validated_at ? (v.ready ? "Sim" : "Não") : "—"} tone={v.validated_at ? (v.ready ? "ok" : "danger") : undefined} />
      </div>
      <p className="mb-5 text-xs text-faint">Conta: <span className="text-muted">{batch.seller_account_label ?? "—"}</span> · Template: <span className="text-muted">{batch.template_filename ?? "—"}{batch.sheet_name ? ` · ${batch.sheet_name}` : ""}</span>{batch.template_expired && <Badge tone="danger" className="ml-2">prazo vencido</Badge>}{v.validated_at && <> · validado em {new Date(v.validated_at).toLocaleString("pt-BR")}</>}</p>
      {msg && <div className="mb-4"><Alert tone={msg.tone}>{msg.text}</Alert></div>}

      <div className="grid gap-6 lg:grid-cols-[230px_1fr] items-start">
        <nav aria-label="Etapas" className="flex lg:flex-col gap-1 overflow-x-auto lg:sticky lg:top-8 -mx-4 px-4 lg:mx-0 lg:px-0 pb-2 lg:pb-0">
          {steps.map((s, i) => (
            <button key={s.key} onClick={() => setStep(i)} aria-current={step === i ? "step" : undefined}
              className={cx("flex items-center gap-2.5 rounded-md px-3 h-9 text-sm whitespace-nowrap text-left transition-colors shrink-0",
                step === i ? "bg-card text-fg" : "text-muted hover:text-fg hover:bg-card/60")}>
              <span className={cx("grid place-items-center size-6 shrink-0 rounded-full text-[11px] font-semibold border",
                s.done ? "bg-accent border-accent text-on-accent" : step === i ? "border-accent text-accent" : "border-line-strong text-faint")}>
                {s.done ? <Check className="size-3.5" strokeWidth={3} /> : i + 1}
              </span>
              {s.title}
              {!s.available && <Lock className="size-3 text-faint ml-auto" aria-label="indisponível" />}
            </button>
          ))}
        </nav>

        <Card className="p-6 min-w-0">
          <h2 className="text-lg font-semibold mb-1">{step + 1}. {steps[step].title}</h2>
          <div className="mt-4">
            {step === 0 && <p className="text-sm text-muted">Mercado Livre — Anunciador em massa por planilha Excel (P1 p.1). Outros marketplaces terão fluxos próprios.</p>}

            {step === 1 && (
              <div className="flex flex-col gap-3 max-w-md">
                <p className="text-sm text-muted">Escolha a conta de vendedor que vai baixar e enviar a planilha. O Mercado Livre só aceita planilhas baixadas da própria conta (P1 p.8).</p>
                {accounts?.length === 0 ? <Alert tone="info">Cadastre uma conta em <Link className="underline" href="/marketplaces/">Marketplaces</Link>.</Alert> : (
                  <Select aria-label="Conta de vendedor" disabled={!writable} value={batch.seller_account_id ?? ""} onChange={(e) => patch({ seller_account_id: e.target.value || null })}>
                    <option value="">Selecione…</option>
                    {accounts?.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
                  </Select>
                )}
              </div>
            )}

            {step === 2 && (
              !batch.seller_account_id ? <Alert tone="info">Escolha a conta primeiro.</Alert> : (
                <div className="flex flex-col gap-4">
                  {accountTemplates.length === 0 ? (
                    <Alert tone="info">Nenhum template desta conta. Baixe a planilha no Anunciador em massa e registre em <Link className="underline" href="/templates/">Templates</Link>.</Alert>
                  ) : (
                    <ul className="flex flex-col gap-2">
                      {accountTemplates.map((t) => (
                        <li key={t.id}>
                          <label className={cx("flex items-center gap-3 rounded-md border px-4 py-3 cursor-pointer", batch.template_id === t.id ? "border-accent bg-accent-soft" : "border-line hover:border-line-strong")}>
                            <input type="radio" name="tpl" disabled={!writable} checked={batch.template_id === t.id} onChange={() => patch({ template_id: t.id })} className="accent-[var(--color-accent)]" />
                            <span className="min-w-0 flex-1"><span className="block truncate font-medium">{t.original_filename}</span><span className="text-xs text-faint">Prazo {fmtDate(t.deadline_date)}</span></span>
                            <TemplateStatusBadge t={t} />
                          </label>
                        </li>
                      ))}
                    </ul>
                  )}
                  {batch.template_id && (
                    <label className="flex flex-col gap-1.5 max-w-sm text-sm"><span className="text-[13px] text-muted">Aba de categoria (uma aba por categoria — P2 p.2)</span>
                      <Select disabled={!writable} value={batch.sheet_name} onChange={(e) => patch({ sheet_name: e.target.value })}>
                        <option value="">Selecione…</option>
                        {categorySheets.map((s) => <option key={s.name} value={s.name}>{s.name}</option>)}
                      </Select>
                    </label>
                  )}
                </div>
              )
            )}

            {step === 3 && <ProductPicker base={base} batch={batch} writable={writable} onChange={(b) => { setBatch(b); setValidation(null); }} />}

            {step === 4 && (
              !batch.sheet_name || !batch.template_id ? <Alert tone="info">Escolha template e aba primeiro.</Alert> : !mapping ? <Skeleton className="h-24" /> : (
                <div className="flex flex-col gap-3 text-sm">
                  <p className="text-muted">Relacione os campos do catálogo às colunas da aba <strong className="text-fg">{batch.sheet_name}</strong>. O mapeamento fica salvo no template e é reutilizado por outros lotes.</p>
                  <div className="flex flex-wrap gap-2">
                    {mapping.header_row_confirmed ? <Badge tone="ok">Cabeçalho confirmado (linha {mapping.header_row})</Badge> : <Badge tone="warn">Cabeçalho não confirmado</Badge>}
                    <Badge>{Object.keys(mapping.rules).length} de {mapping.columns.length} colunas mapeadas</Badge>
                    {requiredOpen > 0 && <Badge tone="danger">{requiredOpen} obrigatória(s) sem mapeamento</Badge>}
                  </div>
                  <Link href={`/templates/detalhe/?id=${batch.template_id}`}><Button>Abrir editor de mapeamento <ChevronRight className="size-4" /></Button></Link>
                </div>
              )
            )}

            {step === 5 && (
              <div className="flex flex-col gap-4">
                <p className="text-sm text-muted">A validação do MLA indica a origem de cada regra: interna, documentação oficial, template ou hipótese. Ela não substitui a validação do Mercado Livre no envio (P1 p.7) nem a coluna “Resumo de erros” do arquivo (P2 p.4–5).</p>
                <div><Button variant="primary" busy={busy} disabled={!can.write(role) || batch.items === 0} onClick={validate}>Validar lote</Button></div>
                {validation && (
                  <>
                    {[...validation.template_issues, ...validation.batch_issues].length > 0 && (
                      <Card className="p-4 bg-bg-2"><h3 className="text-sm font-semibold mb-3">Lote e template</h3><IssueList issues={[...validation.template_issues, ...validation.batch_issues]} /></Card>
                    )}
                    <p className="text-sm">{validation.summary.complete} completos · {validation.summary.with_warnings} com avisos · <span className="text-danger">{validation.summary.with_errors} com erros</span> — veja em “Corrigir”.</p>
                  </>
                )}
              </div>
            )}

            {step === 6 && (
              !validation ? <Alert tone="info">Rode a validação na etapa anterior.</Alert> : (
                <div className="flex flex-col gap-3">
                  <p className="text-sm text-muted">Corrija no catálogo (vale para todos os canais) ou crie uma regra no <Link className="underline" href={`/assistente/?lote=${batch.id}`}>Assistente de Correção</Link> (só deste lote ou permanente). Depois valide de novo.</p>
                  {validation.products.filter((p) => p.issues.some((i) => i.severity !== "info")).map((p) => (
                    <details key={p.product_id} className="rounded-md border border-line bg-bg-2 px-4 py-3" open={p.errors > 0}>
                      <summary className="cursor-pointer flex flex-wrap items-center gap-2 text-sm">
                        <span className="font-medium">{p.name}</span><span className="font-mono text-xs text-faint">{p.sku}</span>
                        {p.errors > 0 && <Badge tone="danger">{p.errors} erro(s)</Badge>}{p.warnings > 0 && <Badge tone="warn">{p.warnings} aviso(s)</Badge>}
                        <Link href={`/catalogo/produto/?id=${p.product_id}`} target="_blank" className="ml-auto text-xs text-accent hover:text-accent-2">Editar produto ↗</Link>
                      </summary>
                      <div className="mt-3"><IssueList issues={p.issues} /></div>
                    </details>
                  ))}
                  {validation.products.every((p) => !p.issues.some((i) => i.severity !== "info")) && <Alert tone="ok">Nenhum erro ou aviso nos produtos.</Alert>}
                </div>
              )
            )}

            {step === 7 && <Review base={base} enabled={!!mapping?.header_row_confirmed} />}

            {step === 8 && <ExportStep base={base} batch={batch} onBatch={setBatch} canWrite={can.write(role)} />}

            {step === 9 && (
              <div className="flex flex-col gap-3 text-sm">
                <ol className="list-decimal pl-5 flex flex-col gap-1.5 text-muted">
                  <li>No Mercado Livre: lista de anúncios → “Anunciar” → “Em massa” (P1 p.1).</li>
                  <li>Escolha “Envie a planilha Excel que você baixou” e selecione o arquivo exportado (P1 p.6).</li>
                  <li>O carregamento não pode ser interrompido e leva alguns minutos; você pode sair da tela (P1 p.7–8).</li>
                  <li>Limite: 10.000 anúncios criados por dia (P1 p.8). Só planilhas baixadas da mesma conta são aceitas.</li>
                </ol>
                <div><Button disabled={batch.status !== "exported" || !can.write(role)} onClick={async () => { try { setBatch(await api<Batch>(`${base}/confirm-sent`, { method: "POST", body: {} })); } catch (e) { setMsg({ tone: "danger", text: e instanceof ApiError ? e.message : "Falha." }); } }}>Confirmo que enviei a planilha</Button></div>
                <p className="text-xs text-faint">Disponível depois da exportação. O MLA nunca marca um lote como enviado sem a sua confirmação.</p>
              </div>
            )}

            {step === 10 && (
              <div className="flex flex-col gap-3 text-sm">
                <p className="text-muted">O Mercado Livre avisa por e-mail quando termina. Se houver erros, ele oferece um novo arquivo só com os anúncios não criados e a coluna “Resumo de erros” (P1 p.8).</p>
                <Alert tone="info">A importação automática do arquivo de erros depende de uma planilha de retorno real para conhecer o formato. Enquanto isso, cole o conteúdo da coluna “Resumo de erros” no <Link className="underline" href={`/assistente/?lote=${batch.id}`}>Assistente de Correção</Link>.</Alert>
                <div><Button disabled={batch.status !== "sent_external" || !can.write(role)} onClick={async () => { try { setBatch(await api<Batch>(`${base}/confirm-result`, { method: "POST", body: {} })); } catch (e) { setMsg({ tone: "danger", text: e instanceof ApiError ? e.message : "Falha." }); } }}>Recebi o e-mail de conclusão</Button></div>
              </div>
            )}

            {step === 11 && (
              <div className="flex flex-col gap-3 text-sm">
                <p className="text-muted">Corrija os itens recusados com o Assistente de Correção (regra só para este lote ou regra permanente), valide de novo e gere uma nova planilha. Para um novo envio, crie um lote com os produtos recusados: lotes enviados ficam travados para preservar o histórico.</p>
                <div><Link href={`/assistente/?lote=${batch.id}`}><Button variant="primary">Abrir Assistente de Correção</Button></Link></div>
              </div>
            )}
          </div>

          <div className="mt-8 flex justify-between border-t border-line pt-4">
            <Button variant="ghost" disabled={step === 0} onClick={() => setStep(step - 1)}>Voltar</Button>
            <Button disabled={step === steps.length - 1} onClick={() => setStep(step + 1)}>Próxima etapa <ChevronRight className="size-4" /></Button>
          </div>
        </Card>
      </div>

      {batch.history.length > 0 && (
        <details className="mt-6 text-sm"><summary className="cursor-pointer text-muted">Histórico do lote ({batch.history.length})</summary>
          <ol className="mt-3 flex flex-col gap-1 text-xs text-muted">{batch.history.slice().reverse().map((h, i) => (
            <li key={i}><span className="text-faint">{new Date(h.at).toLocaleString("pt-BR")}</span> · {h.by} · {h.event}{h.status ? ` → ${String(h.status)}` : ""}{h.reason ? ` (${String(h.reason)})` : ""}</li>
          ))}</ol>
        </details>
      )}
    </>
  );
}

function ExportStep({ base, batch, onBatch, canWrite }: { base: string; batch: Batch; onBatch: (b: Batch) => void; canWrite: boolean }) {
  const { data: exports, reload } = useApi<ExportRecord[]>(`${base}/exports`);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);
  const locked = ["sent_external", "result_received", "done"].includes(batch.status);
  async function generate() {
    setBusy(true); setMsg(null);
    try {
      const e = await api<ExportRecord>(`${base}/export`, { method: "POST" });
      setMsg({ tone: "ok", text: `Planilha gerada: ${e.rows} linha(s), integridade verificada.` });
      onBatch(await api<Batch>(base)); reload();
    } catch (err) { setMsg({ tone: "danger", text: err instanceof ApiError ? err.message : "Falha ao gerar." }); }
    finally { setBusy(false); }
  }
  return (
    <div className="flex flex-col gap-4 text-sm">
      <p className="text-muted">O MLA preenche uma <strong className="text-fg">cópia</strong> da planilha oficial da conta: só as células de dados mudam; abas, fórmulas, listas, validações e instruções ficam como o Mercado Livre enviou. Gerar o arquivo <strong className="text-fg">não publica</strong> nada.</p>
      {batch.validation.writer_available === false && <Alert tone="danger">Este template não tem a estrutura oficial reconhecida; não é possível gerar a planilha.</Alert>}
      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
      <div><Button variant="primary" busy={busy} disabled={!canWrite || locked} onClick={generate}>Validar e gerar planilha</Button></div>
      {exports && exports.length > 0 && (
        <ul className="flex flex-col gap-2">
          {exports.map((e) => (
            <li key={e.id} className="flex flex-wrap items-center gap-3 rounded-md border border-line bg-bg-2 px-4 py-3">
              <span className="font-medium">{new Date(e.created_at).toLocaleString("pt-BR")}</span>
              <Badge>{e.rows} linha(s)</Badge><Badge tone="ok">integridade ok</Badge>
              {e.rules_applied.length > 0 && <Badge tone="info">{e.rules_applied.length} regra(s) aplicada(s)</Badge>}
              <span className="font-mono text-xs text-faint">SHA-256 {e.sha256.slice(0, 10)}…</span>
              <a className="ml-auto text-accent hover:text-accent-2" href={`/api${base}/exports/${e.id}/file`}>Baixar XLSX para conferência</a>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-faint">Risco conhecido: as fórmulas auxiliares do arquivo são recalculadas ao abrir no Excel; ainda não sabemos se o Mercado Livre recalcula ao processar. Faça um envio de teste controlado antes de lotes grandes.</p>
    </div>
  );
}

function ProductPicker({ base, batch, writable, onChange }: { base: string; batch: Batch; writable: boolean; onChange: (b: Batch) => void }) {
  const { org } = useSession();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  useEffect(() => { const t = setTimeout(() => setQuery(q), 300); return () => clearTimeout(t); }, [q]);
  const { data } = useApi<ProductPage>(`/orgs/${org!.id}/products?q=${encodeURIComponent(query)}&limit=50&sort=name`);
  const { data: ids, setData: setIds } = useApi<string[]>(`${base}/items`);
  const selected = useMemo(() => new Set(ids ?? []), [ids]);

  async function change(body: object) {
    const b = await api<Batch>(`${base}/items`, { method: "PUT", body });
    onChange(b);
    setIds(await api<string[]>(`${base}/items`));
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col sm:flex-row gap-2">
        <div className="relative flex-1"><Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-faint" aria-hidden />
          <Input aria-label="Buscar produtos" placeholder="Buscar por nome, SKU ou marca" className="pl-9" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        {writable && <Button onClick={() => change({ mode: "add", all_matching: { q: query } })}>Adicionar todos {query ? "do filtro" : "do catálogo"}{data ? ` (${data.total})` : ""}</Button>}
        {writable && selected.size > 0 && <Button variant="ghost" onClick={() => change({ mode: "replace", product_ids: [] })}>Limpar seleção</Button>}
      </div>
      <p className="text-sm text-muted"><strong className="text-fg">{batch.items}</strong> produto(s) no lote.</p>
      <div className="overflow-x-auto rounded-md border border-line">
        <table className="w-full text-sm">
          <tbody>
            {data?.items.map((p) => {
              const on = selected.has(p.id);
              return (
                <tr key={p.id} className="border-b border-line last:border-0">
                  <td className="w-10 px-3 py-2"><input type="checkbox" aria-label={`Selecionar ${p.name}`} disabled={!writable} checked={on}
                    onChange={() => change({ mode: on ? "remove" : "add", product_ids: [p.id] })} className="size-4 accent-[var(--color-accent)]" /></td>
                  <td className="px-3 py-2"><span className="font-medium">{p.name}</span> <span className="font-mono text-xs text-faint">{p.sku}</span></td>
                  <td className="px-3 py-2 text-right">{p.pendings.some((x) => x.severity === "error") ? <Badge tone="danger">pendências</Badge> : <Badge tone="ok">ok no catálogo</Badge>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {data && data.total > 50 && <p className="text-xs text-faint">Mostrando 50 de {data.total}. Refine a busca ou use “Adicionar todos”.</p>}
    </div>
  );
}

function Review({ base, enabled }: { base: string; enabled: boolean }) {
  const { data, error } = useApi<{ columns: { col: string; header: string; required: boolean }[]; rows: { sku: string; values: Record<string, string> }[]; total_rows: number }>(enabled ? `${base}/preview?limit=100` : null);
  if (!enabled) return <Alert tone="info">Confirme o mapeamento antes de revisar.</Alert>;
  if (error) return <Alert>{error}</Alert>;
  if (!data) return <Skeleton className="h-40" />;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-muted">Valores que iriam para as linhas de dados ({data.total_rows} linha(s); uma por variação — P1 p.6). Nenhum arquivo é alterado nesta etapa.</p>
      <div className="overflow-auto max-h-[460px] rounded-md border border-line">
        <table className="text-xs">
          <thead className="sticky top-0 bg-bg-2"><tr>{data.columns.map((c) => <th key={c.col} className="px-3 py-2 text-left font-semibold whitespace-nowrap">{c.header}{c.required && <span className="text-danger"> *</span>}</th>)}</tr></thead>
          <tbody>{data.rows.map((r, i) => (
            <tr key={i} className="border-t border-line">{data.columns.map((c) => {
              const val = r.values[c.col];
              return <td key={c.col} title={val} className={cx("px-3 py-1.5 max-w-60 truncate whitespace-nowrap", !val && c.required && "bg-danger/10")}>{val || <span className="text-faint">—</span>}</td>;
            })}</tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}

function BatchPage() {
  const id = useSearchParams().get("id");
  return (
    <>
      <Link href="/anuncios-em-massa/" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg mb-4"><ArrowLeft className="size-4" />Anúncios em massa</Link>
      {id ? <Wizard id={id} /> : <Alert>Lote não informado.</Alert>}
    </>
  );
}

export default function Page() {
  return <Suspense><BatchPage /></Suspense>;
}
