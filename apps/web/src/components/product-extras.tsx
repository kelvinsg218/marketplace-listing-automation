"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, ImagePlus, Link2, Plus, Trash2 } from "lucide-react";
import { api, ApiError, apiUpload, type ProductImage, type Variant } from "@/lib/api";
import { money } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { Alert, Badge, Button, Card, Field, Input, Textarea } from "./ui";

const errText = (err: unknown, fallback: string) => (err instanceof ApiError ? err.message : fallback);

function Section({ title, description, children, action }: { title: string; description?: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          {description && <p className="mt-1 text-xs text-faint max-w-2xl">{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </Card>
  );
}

/** "Cor=Azul; Tamanho=M" <-> {Cor: "Azul", Tamanho: "M"} */
const attrsToText = (a: Record<string, string>) => Object.entries(a).map(([k, v]) => `${k}=${v}`).join("; ");
function textToAttrs(t: string): Record<string, string> {
  return Object.fromEntries(t.split(";").map((p) => p.split("=").map((x) => x.trim())).filter(([k, v]) => k && v));
}

export function VariantsCard({ orgId, productId, canWrite }: { orgId: string; productId: string; canWrite: boolean }) {
  const base = `/orgs/${orgId}/products/${productId}/variants`;
  const { data, reload } = useApi<Variant[]>(base);
  const [form, setForm] = useState({ sku: "", attrs: "", gtin: "", stock: "0" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      await api(base, { method: "POST", body: { sku: form.sku, attributes: textToAttrs(form.attrs), gtin: form.gtin, stock: Number(form.stock || 0) } });
      setForm({ sku: "", attrs: "", gtin: "", stock: "0" });
      reload();
    } catch (err) { setError(errText(err, "Falha ao salvar a variação.")); } finally { setBusy(false); }
  }

  return (
    <Section title="Variações" description="Cada variação vira uma linha da planilha (o Mercado Livre cria variações duplicando linhas — P1 p.6). A forma exata de agrupar depende do template real.">
      {data && data.length > 0 ? (
        <div className="overflow-x-auto -mx-2">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs uppercase tracking-wider text-faint">
              <th className="px-2 py-2 font-semibold">SKU</th><th className="px-2 py-2 font-semibold">Atributos</th>
              <th className="px-2 py-2 font-semibold">GTIN</th><th className="px-2 py-2 font-semibold text-right">Preço</th>
              <th className="px-2 py-2 font-semibold text-right">Estoque</th><th />
            </tr></thead>
            <tbody>
              {data.map((v) => (
                <tr key={v.id} className="border-t border-line">
                  <td className="px-2 py-2 font-mono text-xs">{v.sku}</td>
                  <td className="px-2 py-2">{Object.entries(v.attributes).map(([k, val]) => <Badge key={k} className="mr-1">{k}: {val}</Badge>)}</td>
                  <td className="px-2 py-2 font-mono text-xs">{v.gtin || "—"} {v.gtin && !v.gtin_valid && <Badge tone="warn">dígito inválido</Badge>}</td>
                  <td className="px-2 py-2 text-right">{v.price_cents == null ? <span className="text-faint">do produto</span> : money(v.price_cents)}</td>
                  <td className="px-2 py-2 text-right">{v.stock}</td>
                  <td className="px-2 py-2 text-right">{canWrite && (
                    <button aria-label={`Excluir variação ${v.sku}`} className="p-1.5 rounded-md text-faint hover:text-danger"
                      onClick={async () => { if (confirm(`Excluir a variação ${v.sku}?`)) { await api(`${base}/${v.id}`, { method: "DELETE" }); reload(); } }}>
                      <Trash2 className="size-4" />
                    </button>
                  )}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="text-sm text-muted">Sem variações: o produto vira uma única linha.</p>}
      {canWrite && (
        <form onSubmit={add} className="mt-5 grid gap-3 sm:grid-cols-[1fr_2fr_1fr_90px_auto] items-end border-t border-line pt-5">
          <Field label="SKU da variação">{(id) => <Input id={id} className="font-mono" value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} />}</Field>
          <Field label="Atributos" hint="Ex.: Cor=Azul; Tamanho=M">{(id, d) => <Input id={id} aria-describedby={d} value={form.attrs} onChange={(e) => setForm({ ...form, attrs: e.target.value })} />}</Field>
          <Field label="GTIN">{(id) => <Input id={id} inputMode="numeric" value={form.gtin} onChange={(e) => setForm({ ...form, gtin: e.target.value })} />}</Field>
          <Field label="Estoque">{(id) => <Input id={id} inputMode="numeric" value={form.stock} onChange={(e) => setForm({ ...form, stock: e.target.value })} />}</Field>
          <Button type="submit" busy={busy} className="mb-[22px]"><Plus className="size-4" />Adicionar</Button>
          {error && <div className="sm:col-span-5"><Alert>{error}</Alert></div>}
        </form>
      )}
    </Section>
  );
}

export function PhotosCard({ orgId, productId, canWrite }: { orgId: string; productId: string; canWrite: boolean }) {
  const base = `/orgs/${orgId}/products/${productId}/images`;
  const { data, reload, setData } = useApi<ProductImage[]>(base);
  const [urls, setUrls] = useState("");
  const [msg, setMsg] = useState<{ tone: "danger" | "ok"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const withUrl = data?.filter((i) => i.official_url).length ?? 0;

  async function run(fn: () => Promise<unknown>, ok?: string) {
    setBusy(true); setMsg(null);
    try { await fn(); if (ok) setMsg({ tone: "ok", text: ok }); reload(); }
    catch (err) { setMsg({ tone: "danger", text: errText(err, "Falha na operação.") }); }
    finally { setBusy(false); }
  }

  async function move(index: number, delta: number) {
    if (!data) return;
    const ids = data.map((i) => i.id);
    [ids[index], ids[index + delta]] = [ids[index + delta], ids[index]];
    setData(await api<ProductImage[]>(`${base}/order`, { method: "PUT", body: { ids } }));
  }

  return (
    <Section title="Fotos"
      description="A planilha oficial recebe URLs geradas no Gestor de fotos do Mercado Livre, separadas por vírgula (P3). Guarde aqui os arquivos e cole as URLs oficiais; o MLA não envia fotos ao Gestor."
      action={<Badge tone={withUrl ? "ok" : "warn"}>{withUrl} com URL oficial</Badge>}>
      {msg && <div className="mb-4"><Alert tone={msg.tone}>{msg.text}</Alert></div>}
      {data && data.length > 0 ? (
        <ol className="flex flex-col gap-2">
          {data.map((img, n) => (
            <li key={img.id} className="flex items-center gap-3 rounded-md border border-line bg-bg-2 p-2">
              <span className="w-6 text-center font-mono text-xs text-faint">{n + 1}</span>
              <div className="size-14 shrink-0 overflow-hidden rounded-sm bg-line grid place-items-center">
                {img.has_file
                  // eslint-disable-next-line @next/next/no-img-element
                  ? <img src={`/api${base}/${img.id}/file`} alt={img.original_name || `Foto ${n + 1}`} className="size-full object-cover" />
                  : <Link2 className="size-5 text-faint" aria-hidden />}
              </div>
              <div className="min-w-0 flex-1 text-sm">
                <p className="truncate">{img.original_name || (img.has_file ? "Arquivo" : "Somente URL")}</p>
                {img.official_url
                  ? <a href={img.official_url} target="_blank" rel="noreferrer noopener" className="block truncate text-xs text-info hover:underline">{img.official_url}</a>
                  : <p className="text-xs text-warn">Sem URL oficial do Gestor de fotos</p>}
                {img.url_problem && <p className="text-xs text-warn">{img.url_problem}</p>}
              </div>
              {canWrite && (
                <div className="flex items-center gap-1">
                  {!img.official_url && (
                    <Button size="sm" variant="ghost" onClick={() => {
                      const url = prompt("Cole a URL desta foto copiada do Gestor de fotos:");
                      if (url) run(() => api(`${base}/${img.id}`, { method: "PATCH", body: { official_url: url } }), "URL registrada.");
                    }}>Colar URL</Button>
                  )}
                  <button aria-label="Subir" disabled={n === 0} onClick={() => move(n, -1)} className="p-1.5 rounded-md text-faint hover:text-fg disabled:opacity-30"><ArrowUp className="size-4" /></button>
                  <button aria-label="Descer" disabled={n === data.length - 1} onClick={() => move(n, 1)} className="p-1.5 rounded-md text-faint hover:text-fg disabled:opacity-30"><ArrowDown className="size-4" /></button>
                  <button aria-label="Excluir foto" onClick={() => confirm("Excluir esta foto?") && run(() => api(`${base}/${img.id}`, { method: "DELETE" }))} className="p-1.5 rounded-md text-faint hover:text-danger"><Trash2 className="size-4" /></button>
                </div>
              )}
            </li>
          ))}
        </ol>
      ) : <p className="text-sm text-muted">Nenhuma foto.</p>}

      {canWrite && (
        <div className="mt-5 grid gap-4 lg:grid-cols-2 border-t border-line pt-5">
          <div>
            <p className="text-[13px] font-medium text-muted mb-1.5">Arquivo de imagem</p>
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" hidden
              onChange={(e) => { const f = e.target.files?.[0]; if (!f) return; const fd = new FormData(); fd.append("file", f); run(() => apiUpload(`${base}/upload`, fd), "Foto enviada."); e.target.value = ""; }} />
            <Button busy={busy} onClick={() => fileRef.current?.click()}><ImagePlus className="size-4" />Enviar JPG, PNG ou WEBP</Button>
            <p className="mt-2 text-xs text-faint">Até 10 MB. Fica privado na sua organização.</p>
          </div>
          <form onSubmit={(e) => { e.preventDefault(); if (urls.trim()) run(() => api(base, { method: "POST", body: [{ official_url: urls }] }), "URLs registradas.").then(() => setUrls("")); }}>
            <Field label="URLs do Gestor de fotos" hint='No Gestor: "Copiar URLs" e cole aqui (várias, separadas por vírgula).'>
              {(id, d) => <Textarea id={id} aria-describedby={d} className="min-h-20 font-mono text-xs" value={urls} onChange={(e) => setUrls(e.target.value)} placeholder="https://http2.mlstatic.com/..." />}
            </Field>
            <Button type="submit" className="mt-2" disabled={!urls.trim()} busy={busy}><Link2 className="size-4" />Registrar URLs</Button>
          </form>
        </div>
      )}
    </Section>
  );
}

export function MercadoLivreCard({ orgId, productId, canWrite }: { orgId: string; productId: string; canWrite: boolean }) {
  const url = `/orgs/${orgId}/products/${productId}/channels/mercadolivre`;
  const { data } = useApi<{ catalog_code: string; category_id: string }>(url);
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState<{ tone: "danger" | "ok"; text: string } | null>(null);
  useEffect(() => { if (data) setCode(data.catalog_code); }, [data]);
  return (
    <Section title="Mercado Livre" description='Com "Código de catálogo ML", parte das colunas pode ficar vazia — o template indica quais (P2 p.2–3). Sem código, valem os campos "Obrigatório".'>
      {msg && <div className="mb-3"><Alert tone={msg.tone}>{msg.text}</Alert></div>}
      <form className="flex flex-wrap items-end gap-3" onSubmit={async (e) => {
        e.preventDefault(); setMsg(null);
        try { await api(url, { method: "PUT", body: { catalog_code: code.trim(), category_id: data?.category_id ?? "" } }); setMsg({ tone: "ok", text: "Código salvo." }); }
        catch (err) { setMsg({ tone: "danger", text: errText(err, "Falha ao salvar.") }); }
      }}>
        <Field label="Código de catálogo ML" className="flex-1 min-w-56">{(id) => <Input id={id} className="font-mono" value={code} readOnly={!canWrite} onChange={(e) => setCode(e.target.value)} placeholder="Opcional" />}</Field>
        {canWrite && <Button type="submit">Salvar</Button>}
      </form>
    </Section>
  );
}
