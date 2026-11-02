"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ImagePlus, Images, Link2, Search, Sparkles, Star, X } from "lucide-react";
import { api, ApiError, apiUpload, can, type ProductImage } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { Alert, Badge, Button, Card, cx, EmptyState, Input, PageHeader, Select, Textarea } from "@/components/ui";

interface Item { product_id: string; sku: string; name: string; gtin: string; images: number; approved: number; pending: number; with_gestor_url: number }
interface Img extends ProductImage { source: string; status: string; parent_image_id: string | null; prompt: string; provider: string; external_url: string; created_at: string }
interface AiStatus { configured: boolean; provider: string | null; external: boolean | null; message: string | null }

const SOURCE: Record<string, string> = { upload: "Arquivo no MLA", url_externa: "URL externa (baixada)", gestor: "URL do Gestor de fotos", ia: "Versão por IA" };
const STATUS: Record<string, { label: string; tone: "ok" | "warn" | "danger" }> = { approved: { label: "aprovada", tone: "ok" }, pending: { label: "pendente", tone: "warn" }, rejected: { label: "rejeitada", tone: "danger" } };
const EXAMPLES = ["Remova o fundo e deixe branco.", "Melhore a iluminação sem modificar o produto.", "Centralize o produto e melhore a nitidez."];

function Thumb({ base, img, className }: { base: string; img: Img; className?: string }) {
  return img.has_file
    // eslint-disable-next-line @next/next/no-img-element
    ? <img src={`/api${base}/${img.id}/file`} alt={img.original_name || "Imagem"} className={cx("object-contain bg-bg", className)} />
    : <div className={cx("grid place-items-center bg-bg text-faint", className)}><Link2 className="size-6" aria-hidden /><span className="sr-only">Somente URL</span></div>;
}

function ProductImages({ orgId, item, onChange }: { orgId: string; item: Item; onChange: () => void }) {
  const { role } = useSession();
  const base = `/orgs/${orgId}/products/${item.product_id}/images`;
  const { data: imgs, reload } = useApi<Img[]>(base);
  const { data: ai } = useApi<AiStatus>(`/orgs/${orgId}/images/ai/status`);
  const [selected, setSelected] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [gestor, setGestor] = useState("");
  const [prompt, setPrompt] = useState("");
  const [consent, setConsent] = useState(false);
  const [msg, setMsg] = useState<{ tone: "ok" | "danger" | "info"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const write = can.write(role);
  useEffect(() => { setSelected(null); setMsg(null); }, [item.product_id]);
  const current = imgs?.find((i) => i.id === selected) ?? imgs?.[0];
  const parent = current?.parent_image_id ? imgs?.find((i) => i.id === current.parent_image_id) : undefined;
  const versions = imgs?.filter((i) => i.source === "ia") ?? [];

  async function run(fn: () => Promise<unknown>, ok: string) {
    setBusy(true); setMsg(null);
    try { await fn(); setMsg({ tone: "ok", text: ok }); reload(); onChange(); }
    catch (e) { setMsg({ tone: "danger", text: e instanceof ApiError ? e.message : "Falha." }); }
    finally { setBusy(false); }
  }

  return (
    <Card className="p-5 min-w-0">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div><h2 className="text-base font-semibold">{item.name}</h2><p className="font-mono text-xs text-faint">{item.sku}{item.gtin ? ` · GTIN ${item.gtin}` : ""}</p></div>
        <span className="text-xs text-faint">Na planilha oficial entram só imagens <strong>aprovadas</strong> com URL do Gestor de fotos.</span>
      </div>
      {msg && <div className="mt-3"><Alert tone={msg.tone}>{msg.text}</Alert></div>}

      {imgs && imgs.length === 0 ? <p className="mt-4 text-sm text-muted">Sem imagens.</p> : current && (
        <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_220px]">
          <div>
            {parent ? (
              <div className="grid grid-cols-2 gap-2">
                <figure><Thumb base={base} img={parent} className="aspect-square w-full rounded-md border border-line" /><figcaption className="mt-1 text-xs text-muted">Original (preservada)</figcaption></figure>
                <figure><Thumb base={base} img={current} className="aspect-square w-full rounded-md border border-accent/50" /><figcaption className="mt-1 text-xs text-muted">Editada · “{current.prompt}”</figcaption></figure>
              </div>
            ) : <Thumb base={base} img={current} className="aspect-[4/3] w-full rounded-md border border-line" />}
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
              <Badge>{SOURCE[current.source] ?? current.source}</Badge><Badge tone={STATUS[current.status]?.tone}>{STATUS[current.status]?.label}</Badge>
              {imgs?.[0]?.id === current.id && current.status === "approved" && <Badge tone="accent"><Star className="size-3" />principal</Badge>}
              {current.official_url && <Badge tone="info">URL do Gestor</Badge>}
              {current.external_url && <span className="truncate text-faint max-w-72" title={current.external_url}>origem: {current.external_url}</span>}
            </div>
            {write && (
              <div className="mt-3 flex flex-wrap gap-2">
                {current.status !== "approved" && <Button size="sm" variant="primary" onClick={() => run(() => api(`${base}/${current.id}/review`, { method: "POST", body: { decision: "approve" } }), "Imagem aprovada.")}><Check className="size-4" />Aprovar</Button>}
                {current.status !== "approved" && <Button size="sm" variant="primary" onClick={() => run(() => api(`${base}/${current.id}/review`, { method: "POST", body: { decision: "approve", set_primary: true } }), "Aprovada como principal.")}><Star className="size-4" />Aprovar como principal</Button>}
                {current.status === "approved" && imgs?.[0]?.id !== current.id && <Button size="sm" onClick={() => run(() => api(`${base}/${current.id}/primary`, { method: "POST" }), "Imagem principal definida.")}><Star className="size-4" />Definir como principal</Button>}
                {current.status !== "rejected" && <Button size="sm" variant="danger" onClick={() => run(() => api(`${base}/${current.id}/review`, { method: "POST", body: { decision: "reject" } }), "Imagem rejeitada.")}><X className="size-4" />Rejeitar</Button>}
              </div>
            )}
          </div>
          <ul className="grid grid-cols-3 lg:grid-cols-2 gap-2 content-start">
            {imgs?.map((i, n) => (
              <li key={i.id}>
                <button onClick={() => setSelected(i.id)} aria-label={`Ver imagem ${n + 1}`} className={cx("block w-full rounded-md border p-0.5", current.id === i.id ? "border-accent" : "border-line hover:border-line-strong")}>
                  <Thumb base={base} img={i} className="aspect-square w-full rounded-sm" />
                  <span className="block truncate px-1 text-[10px] text-faint">{n === 0 && i.status === "approved" ? "★ " : ""}{STATUS[i.status]?.label} · {i.source === "ia" ? "IA" : i.source === "gestor" ? "Gestor" : i.source === "url_externa" ? "URL" : "arquivo"}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {write && (
        <div className="mt-6 grid gap-4 lg:grid-cols-3 border-t border-line pt-5">
          <div>
            <p className="text-[13px] font-medium text-muted mb-1.5">Enviar arquivo</p>
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(e) => { const f = e.target.files?.[0]; if (!f) return; const fd = new FormData(); fd.append("file", f); run(() => apiUpload(`${base}/upload`, fd), "Imagem enviada."); e.target.value = ""; }} />
            <Button size="sm" busy={busy} onClick={() => fileRef.current?.click()}><ImagePlus className="size-4" />JPG, PNG ou WEBP</Button>
          </div>
          <form onSubmit={(e) => { e.preventDefault(); run(() => api(`${base}/from-url`, { method: "POST", body: { url } }), "Imagem baixada e guardada.").then(() => setUrl("")); }}>
            <p className="text-[13px] font-medium text-muted mb-1.5">Importar por URL (https)</p>
            <div className="flex gap-2"><Input aria-label="URL da imagem" className="h-8" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" /><Button size="sm" type="submit" disabled={!url}>Baixar</Button></div>
          </form>
          <form onSubmit={(e) => { e.preventDefault(); run(() => api(base, { method: "POST", body: [{ official_url: gestor }] }), "URLs do Gestor registradas.").then(() => setGestor("")); }}>
            <p className="text-[13px] font-medium text-muted mb-1.5">URLs do Gestor de fotos</p>
            <div className="flex gap-2"><Input aria-label="URLs do Gestor" className="h-8 font-mono text-xs" value={gestor} onChange={(e) => setGestor(e.target.value)} placeholder="https://http2.mlstatic.com/…" /><Button size="sm" type="submit" disabled={!gestor}>Registrar</Button></div>
          </form>
        </div>
      )}

      <div className="mt-6 border-t border-line pt-5">
        <h3 className="text-sm font-semibold flex items-center gap-2"><Sparkles className="size-4 text-accent" />Estúdio de IA</h3>
        {ai && !ai.configured ? (
          <div className="mt-3"><Alert tone="info">{ai.message}</Alert></div>
        ) : ai && (
          <div className="mt-3 flex flex-col gap-2">
            <p className="text-xs text-faint">Provedor: {ai.provider}{ai.external ? " (externo — a imagem sai do MLA)" : ""}. O resultado vira uma nova versão pendente; a original nunca é alterada.</p>
            <div className="flex flex-wrap gap-1.5">{EXAMPLES.map((ex) => <button key={ex} type="button" onClick={() => setPrompt(ex)} className="rounded-sm border border-line px-2 py-0.5 text-xs text-muted hover:text-fg">{ex}</button>)}</div>
            <Textarea aria-label="Pedido de edição" className="min-h-16" value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Descreva a edição desejada…" />
            {ai.external && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="size-4 accent-[var(--color-accent)]" />Autorizo enviar esta imagem ao provedor externo</label>}
            <div><Button variant="primary" busy={busy} disabled={!write || !current?.has_file || prompt.trim().length < 3 || (!!ai.external && !consent)}
              onClick={() => run(async () => { const v = await api<Img>(`${base}/${current!.id}/ai-edit`, { method: "POST", body: { prompt, consent } }); setSelected(v.id); }, "Nova versão gerada; revise e aprove ou rejeite.")}>Gerar</Button></div>
          </div>
        )}
        {versions.length > 0 && (
          <div className="mt-4"><p className="text-xs font-semibold text-muted mb-2">Histórico de versões</p>
            <ul className="flex flex-col gap-1 text-xs">{versions.map((v) => (
              <li key={v.id}><button className="hover:text-accent-2" onClick={() => setSelected(v.id)}>{new Date(v.created_at).toLocaleString("pt-BR")} · {v.provider} · “{v.prompt}” · <Badge tone={STATUS[v.status]?.tone}>{STATUS[v.status]?.label}</Badge></button></li>
            ))}</ul></div>
        )}
      </div>
    </Card>
  );
}

export default function ImagesPage() {
  const { org } = useSession();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [pending, setPending] = useState(false);
  const [current, setCurrent] = useState<Item | null>(null);
  useEffect(() => { const t = setTimeout(() => setQuery(q), 300); return () => clearTimeout(t); }, [q]);
  const { data: cats } = useApi<{ id: string; path: string }[]>(org ? `/orgs/${org.id}/categories` : null);
  const { data, error, reload } = useApi<{ items: Item[] }>(org ? `/orgs/${org.id}/images/products?q=${encodeURIComponent(query)}&only_pending=${pending}${category ? `&category_id=${category}` : ""}&limit=200` : null);
  const selected = current && data?.items.find((i) => i.product_id === current.product_id);

  return (
    <>
      <PageHeader title="Central de Imagens" description="Imagens de cada produto: arquivos, URLs externas, URLs do Gestor de fotos e versões editadas. Aprovação explícita, original sempre preservada." />
      {error && <Alert>{error}</Alert>}
      <div className="grid gap-6 xl:grid-cols-[360px_1fr] items-start">
        <Card className="p-4">
          <div className="flex flex-col gap-2 mb-3">
            <div className="relative"><Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-faint" aria-hidden />
              <Input aria-label="Buscar" placeholder="Nome, SKU ou GTIN" value={q} onChange={(e) => setQ(e.target.value)} className="pl-9" /></div>
            <Select aria-label="Categoria" value={category} onChange={(e) => setCategory(e.target.value)}><option value="">Todas as categorias</option>{cats?.map((c) => <option key={c.id} value={c.id}>{c.path}</option>)}</Select>
            <label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={pending} onChange={(e) => setPending(e.target.checked)} className="size-4 accent-[var(--color-accent)]" />Só pendências (sem imagem aprovada, sem URL do Gestor ou com versões a revisar)</label>
          </div>
          {data && data.items.length === 0 ? <EmptyState icon={<Images className="size-6" />} title="Nenhum produto" /> : (
            <ul className="flex flex-col gap-1 max-h-[640px] overflow-y-auto">{data?.items.map((i) => (
              <li key={i.product_id}>
                <button onClick={() => setCurrent(i)} className={cx("w-full rounded-md px-3 py-2 text-left text-sm", current?.product_id === i.product_id ? "bg-card-hover" : "hover:bg-card-hover")}>
                  <span className="block truncate font-medium">{i.name}</span>
                  <span className="flex flex-wrap gap-1 mt-0.5 text-[11px]"><span className="font-mono text-faint">{i.sku}</span>
                    {i.approved === 0 ? <Badge tone="warn">sem imagem aprovada</Badge> : <Badge>{i.approved} aprovada(s)</Badge>}
                    {i.pending > 0 && <Badge tone="warn">{i.pending} a revisar</Badge>}
                    {i.with_gestor_url === 0 && <Badge tone="info">sem URL do Gestor</Badge>}</span>
                </button>
              </li>
            ))}</ul>
          )}
        </Card>
        {selected ? <ProductImages orgId={org!.id} item={selected} onChange={reload} /> : (
          <Card className="p-8 text-center text-sm text-muted">Selecione um produto para ver, aprovar e editar as imagens.</Card>
        )}
      </div>
    </>
  );
}
