"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Sparkles, Wand2 } from "lucide-react";
import { api, ApiError, can, type Batch, type ErrorItem, type Interpretation, type RuleDefinition, type Simulation } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { Alert, Badge, Button, Card, cx, Field, Input, PageHeader, Select, Textarea } from "@/components/ui";

const OP_LABEL: Record<string, string> = {
  copy_field: "copiar do catálogo", set_value: "valor fixo", default_if_empty: "valor padrão se vazio", normalize: "normalizar",
  truncate: "limitar caracteres", map_value: "trocar valores", prefix: "texto antes", suffix: "texto depois", replace_text: "substituir trecho", require: "exigir preenchimento",
};

function describe(d: RuleDefinition) {
  const p = d.params as Record<string, string>;
  const what = d.operation === "copy_field" ? `${OP_LABEL[d.operation]} (${String(p.field).replace("attr:", "")})`
    : p.value !== undefined ? `${OP_LABEL[d.operation]}: “${p.value}”` : OP_LABEL[d.operation] ?? d.operation;
  return `Coluna “${d.target}” → ${what}${d.condition?.when === "target_empty" ? ", só quando estiver vazia" : ""}`;
}

function ProposalPanel({ batch, definition, origin, originText, initialScope, onDone }: {
  batch: Batch; definition: RuleDefinition; origin: "prompt" | "erro"; originText: string; initialScope: "batch" | "category"; onDone: () => void;
}) {
  const { org, role } = useSession();
  const [sim, setSim] = useState<Simulation | null>(null);
  const [scope, setScope] = useState<"batch" | "category">(initialScope);
  const [name, setName] = useState(describe(definition).slice(0, 110));
  const [msg, setMsg] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function simulate() {
    setMsg(null);
    try { setSim(await api<Simulation>(`/orgs/${org!.id}/rules/simulate`, { method: "POST", body: { batch_id: batch.id, definition, scope, scope_ref: scope === "category" ? batch.sheet_name : "" } })); }
    catch (e) { setMsg({ tone: "danger", text: e instanceof ApiError ? e.message : "Falha na simulação." }); }
  }
  async function approve() {
    setBusy(true); setMsg(null);
    try {
      await api(`/orgs/${org!.id}/rules`, { method: "POST", body: { batch_id: batch.id, definition, scope, scope_ref: scope === "category" ? batch.sheet_name : "", name, origin, origin_text: originText, approved: true } });
      setMsg({ tone: "ok", text: scope === "batch" ? "Regra aplicada somente neste lote." : `Regra salva para a categoria ${batch.sheet_name}; vale para os próximos lotes.` });
      onDone();
    } catch (e) { setMsg({ tone: "danger", text: e instanceof ApiError ? e.message : "Falha ao salvar." }); }
    finally { setBusy(false); }
  }

  return (
    <div className="rounded-md border border-line bg-bg-2 p-4 flex flex-col gap-3 text-sm">
      <p className="font-medium">{describe(definition)}</p>
      <div className="flex flex-wrap gap-2">
        <label className={cx("flex items-center gap-2 rounded-md border px-3 py-2 cursor-pointer", scope === "batch" ? "border-accent bg-accent-soft" : "border-line")}>
          <input type="radio" checked={scope === "batch"} onChange={() => { setScope("batch"); setSim(null); }} className="accent-[var(--color-accent)]" />Aplicar somente neste lote
        </label>
        <label className={cx("flex items-center gap-2 rounded-md border px-3 py-2 cursor-pointer", scope === "category" ? "border-accent bg-accent-soft" : "border-line")}>
          <input type="radio" checked={scope === "category"} onChange={() => { setScope("category"); setSim(null); }} className="accent-[var(--color-accent)]" />Salvar como regra para a categoria “{batch.sheet_name}”
        </label>
      </div>
      {!sim ? <div><Button onClick={simulate}>Simular antes e depois</Button></div> : (
        <>
          {sim.official_conflict && <Alert>Não é possível aplicar: {sim.official_conflict}</Alert>}
          {sim.conflicts.map((c) => <Alert key={c} tone="info">{c}</Alert>)}
          <div className="overflow-x-auto rounded-md border border-line">
            <table className="w-full text-xs">
              <thead><tr className="text-left text-faint"><th className="px-3 py-2">SKU</th><th className="px-3 py-2">Antes</th><th className="px-3 py-2">Depois</th></tr></thead>
              <tbody>{sim.rows.map((r) => (
                <tr key={r.sku} className={cx("border-t border-line", r.changed && "bg-accent-soft")}>
                  <td className="px-3 py-1.5 font-mono">{r.sku}</td><td className="px-3 py-1.5 text-muted">{r.before || "—"}</td><td className="px-3 py-1.5">{r.after || "—"}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <p className="text-xs text-faint">{sim.changed} de {sim.rows.length} linha(s) simuladas mudam. A validação oficial continua valendo depois da regra.</p>
          {sim.can_apply && can.write(role) && (
            <div className="flex flex-wrap items-end gap-2">
              <Field label="Nome da regra" className="flex-1 min-w-60">{(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
              <Button variant="primary" busy={busy} onClick={approve}>Aprovar</Button>
              <Button variant="ghost" onClick={onDone}>Cancelar</Button>
            </div>
          )}
        </>
      )}
      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
    </div>
  );
}

function ErrorItemRow({ item, batch, text }: { item: ErrorItem; batch: Batch; text: string }) {
  const [choice, setChoice] = useState<number | null>(null);
  const [value, setValue] = useState("");
  const [done, setDone] = useState(false);
  const p = choice !== null ? item.proposals[choice] : null;
  const def = p ? (p.needs_value ? { ...p.definition, params: { value } } : p.definition) : null;
  return (
    <li className="rounded-md border border-line p-3 flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{item.text}</span>
        {item.column ? <Badge tone="info">coluna “{item.column}”</Badge> : <Badge tone="warn">não reconhecido</Badge>}
        {item.required && <Badge tone="danger">obrigatória no arquivo</Badge>}
        {done && <Badge tone="ok">regra criada</Badge>}
      </div>
      {item.message && <p className="text-xs text-warn">{item.message}</p>}
      {!done && item.proposals.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {item.proposals.map((pr, i) => <Button key={i} size="sm" variant={choice === i ? "primary" : "secondary"} onClick={() => setChoice(i)}>{pr.label}</Button>)}
        </div>
      )}
      {p?.needs_value && (p.options && p.options.length ? (
        <Select aria-label="Valor" value={value} onChange={(e) => setValue(e.target.value)}><option value="">Escolha um valor da lista oficial…</option>{p.options.map((o) => <option key={o}>{o}</option>)}</Select>
      ) : <Input aria-label="Valor" placeholder="Valor a usar" value={value} onChange={(e) => setValue(e.target.value)} />)}
      {def && !done && (!p?.needs_value || value) && <ProposalPanel key={JSON.stringify(def)} batch={batch} definition={def} origin="erro" originText={text} initialScope="batch" onDone={() => setDone(true)} />}
    </li>
  );
}

function Assistant() {
  const { org } = useSession();
  const params = useSearchParams();
  const { data: batches } = useApi<Batch[]>(org ? `/orgs/${org.id}/batches` : null);
  const [batchId, setBatchId] = useState(params.get("lote") ?? "");
  const batch = batches?.find((b) => b.id === batchId);
  const [errText, setErrText] = useState("");
  const [items, setItems] = useState<ErrorItem[] | null>(null);
  const [prompt, setPrompt] = useState("");
  const [interp, setInterp] = useState<Interpretation | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const usable = batch && batch.template_id && batch.sheet_name;

  async function analyze() {
    setMsg(null);
    try { setItems((await api<{ items: ErrorItem[] }>(`/orgs/${org!.id}/batches/${batchId}/error-summary`, { method: "POST", body: { text: errText } })).items); }
    catch (e) { setMsg(e instanceof ApiError ? e.message : "Falha."); }
  }
  async function interpret() {
    setMsg(null); setInterp(null);
    try { setInterp(await api<Interpretation>(`/orgs/${org!.id}/rules/interpret`, { method: "POST", body: { batch_id: batchId, text: prompt } })); }
    catch (e) { setMsg(e instanceof ApiError ? e.message : "Falha."); }
  }

  return (
    <>
      <PageHeader title="Assistente de Correção" description="Corrija anúncios recusados sem abrir o Excel: informe o erro do Mercado Livre ou descreva o ajuste, revise a simulação e escolha se a regra vale só para este lote ou para os próximos." />
      <Card className="p-5 mb-6 flex flex-wrap items-end gap-3">
        <Field label="Lote" className="min-w-72">{(id) => (
          <Select id={id} value={batchId} onChange={(e) => { setBatchId(e.target.value); setItems(null); setInterp(null); }}>
            <option value="">Selecione…</option>
            {batches?.map((b) => <option key={b.id} value={b.id}>{b.name}{b.sheet_name ? ` · ${b.sheet_name}` : ""}</option>)}
          </Select>
        )}</Field>
        {batch && <Link href={`/anuncios-em-massa/lote/?id=${batch.id}`} className="text-sm text-accent hover:text-accent-2 mb-2.5">Abrir lote ↗</Link>}
      </Card>
      {msg && <div className="mb-4"><Alert>{msg}</Alert></div>}
      {batch && !usable && <Alert tone="info">Este lote ainda não tem template e aba definidos.</Alert>}
      {usable && (
        <div className="grid gap-6 xl:grid-cols-2 items-start">
          <Card className="p-5 flex flex-col gap-3">
            <h2 className="text-base font-semibold flex items-center gap-2"><Wand2 className="size-4 text-accent" />Erro recebido</h2>
            <p className="text-xs text-faint">Cole o conteúdo da coluna “Resumo de erros” (ex.: “- Marca”, “- Estoque”) ou a mensagem recebida. O MLA só reconhece colunas que existem na aba; o resto é sinalizado, não adivinhado.</p>
            <Textarea aria-label="Erro recebido" value={errText} onChange={(e) => setErrText(e.target.value)} placeholder={"- Marca\n- Forma de envio"} />
            <div><Button disabled={!errText.trim()} onClick={analyze}>Analisar erro</Button></div>
            {items && <ul className="flex flex-col gap-2">{items.map((it, i) => <ErrorItemRow key={i} item={it} batch={batch} text={errText} />)}</ul>}
          </Card>
          <Card className="p-5 flex flex-col gap-3">
            <h2 className="text-base font-semibold flex items-center gap-2"><Sparkles className="size-4 text-accent" />Descreva o ajuste</h2>
            <p className="text-xs text-faint">Ex.: “Daqui para frente, use o fabricante cadastrado no campo Marca quando estiver vazio.” A interpretação é feita por regras do próprio MLA, sem enviar dados a serviços externos. Nada é aplicado sem sua aprovação.</p>
            <Textarea aria-label="Descreva o ajuste" value={prompt} onChange={(e) => setPrompt(e.target.value)} />
            <div><Button disabled={prompt.trim().length < 3} onClick={interpret}>Interpretar pedido</Button></div>
            {interp && (
              <div className="flex flex-col gap-2">
                {interp.explanation && <p className="text-sm">{interp.explanation} <Badge tone={interp.confidence === "alta" ? "ok" : "warn"}>confiança {interp.confidence}</Badge></p>}
                {interp.questions.map((q) => <Alert key={q} tone="info">{q}</Alert>)}
                {interp.definition && <ProposalPanel key={JSON.stringify(interp.definition)} batch={batch} definition={interp.definition} origin="prompt" originText={prompt} initialScope={interp.scope === "batch" ? "batch" : "category"} onDone={() => setInterp(null)} />}
              </div>
            )}
          </Card>
        </div>
      )}
    </>
  );
}

export default function AssistantPage() {
  return <Suspense><Assistant /></Suspense>;
}
