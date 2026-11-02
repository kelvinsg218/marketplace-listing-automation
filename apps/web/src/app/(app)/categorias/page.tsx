"use client";

import { useState } from "react";
import { FolderTree, Play, Sparkles } from "lucide-react";
import { api, ApiError, can } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { Alert, Badge, Button, Card, cx, EmptyState, Field, Input, PageHeader, Select } from "@/components/ui";

interface Cat { id: string; name: string; parent_id: string | null; path: string; keywords: { phrases?: string[]; words?: string[]; exclude?: string[] }; ml_category_id: string; ml_category_confirmed: boolean; products: number }
interface Row { product_id: string; sku: string; name: string; status: string; confidence: string; score: number; evidence: string[]; category_id: string | null; category_path: string | null }

const CONF = { alta: { label: "Alta confiança", tone: "ok" }, media: { label: "Necessita confirmação", tone: "warn" }, baixa: { label: "Não classificado", tone: "neutral" } } as const;
const list = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

function CategoryEditor({ cat, onSaved }: { cat: Cat; onSaved: () => void }) {
  const { org } = useSession();
  const [f, setF] = useState({ phrases: (cat.keywords.phrases ?? []).join(", "), words: (cat.keywords.words ?? []).join(", "), exclude: (cat.keywords.exclude ?? []).join(", "), ml: cat.ml_category_id, mlOk: cat.ml_category_confirmed });
  const [msg, setMsg] = useState<string | null>(null);
  async function save() {
    try {
      await api(`/orgs/${org!.id}/categories/${cat.id}`, { method: "PUT", body: { name: cat.name, parent_id: cat.parent_id, keywords: { phrases: list(f.phrases), words: list(f.words), exclude: list(f.exclude) }, ml_category_id: f.ml.trim(), ml_category_confirmed: f.mlOk } });
      setMsg("Salvo."); onSaved();
    } catch (e) { setMsg(e instanceof ApiError ? e.message : "Falha."); }
  }
  return (
    <div className="mt-3 grid gap-3 sm:grid-cols-2 rounded-md border border-line bg-bg-2 p-3">
      <Field label="Expressões (valem 3 pontos no nome)" hint="Separadas por vírgula. Ex.: pastilha de freio">{(id) => <Input id={id} value={f.phrases} onChange={(e) => setF({ ...f, phrases: e.target.value })} />}</Field>
      <Field label="Palavras (1 ponto; sozinhas não classificam)">{(id) => <Input id={id} value={f.words} onChange={(e) => setF({ ...f, words: e.target.value })} />}</Field>
      <Field label="Excluir quando contiver">{(id) => <Input id={id} value={f.exclude} onChange={(e) => setF({ ...f, exclude: e.target.value })} />}</Field>
      <Field label="Categoria oficial do Mercado Livre (opcional)" hint="Use o ID confirmado no Mercado Livre; o MLA não inventa.">{(id) => (
        <div className="flex items-center gap-2"><Input id={id} className="font-mono" placeholder="Ex.: MLB1234" value={f.ml} onChange={(e) => setF({ ...f, ml: e.target.value })} />
          <label className="flex items-center gap-1 text-xs text-muted whitespace-nowrap"><input type="checkbox" checked={f.mlOk} onChange={(e) => setF({ ...f, mlOk: e.target.checked })} className="accent-[var(--color-accent)]" />confirmada</label></div>
      )}</Field>
      <div className="sm:col-span-2 flex items-center gap-3"><Button size="sm" variant="primary" onClick={save}>Salvar regra</Button>{msg && <span className="text-xs text-muted">{msg}</span>}</div>
    </div>
  );
}

export default function CategoriesPage() {
  const { org, role } = useSession();
  const base = `/orgs/${org!.id}`;
  const { data: cats, reload } = useApi<Cat[]>(`${base}/categories`);
  const [view, setView] = useState<"review" | "confirmed">("review");
  const { data: rows, reload: reloadRows } = useApi<Row[]>(`${base}/classification?view=${view}`);
  const [open, setOpen] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [target, setTarget] = useState("");
  const [msg, setMsg] = useState<{ tone: "ok" | "danger" | "info"; text: string } | null>(null);
  const [newCat, setNewCat] = useState({ name: "", parent: "" });
  const write = can.write(role);

  async function act(fn: () => Promise<unknown>, ok: (r: unknown) => string) {
    setMsg(null);
    try { const r = await fn(); setMsg({ tone: "ok", text: ok(r) }); reload(); reloadRows(); setSelected(new Set()); }
    catch (e) { setMsg({ tone: "danger", text: e instanceof ApiError ? e.message : "Falha." }); }
  }

  return (
    <>
      <PageHeader title="Categorias e classificação" description="Categorias internas da sua empresa (independentes do Mercado Livre) e classificação automática por regras explicáveis. Produtos confirmados manualmente nunca são alterados pela classificação automática."
        actions={write && <>
          {cats && cats.length === 0 && <Button onClick={() => act(() => api(`${base}/categories/seed-defaults`, { method: "POST" }), (r) => `${(r as { created: number }).created} categorias de exemplo criadas.`)}><FolderTree className="size-4" />Criar árvore de exemplo</Button>}
          <Button variant="primary" onClick={() => act(() => api(`${base}/classification/run`, { method: "POST", body: {} }), (r) => { const t = r as Record<string, number>; return `Classificação: ${t.alta} alta confiança, ${t.media} para confirmar, ${t.baixa} sem categoria, ${t.kept_confirmed} confirmados mantidos.`; })}><Play className="size-4" />Classificar produtos</Button>
        </>} />
      {msg && <div className="mb-4"><Alert tone={msg.tone}>{msg.text}</Alert></div>}
      <div className="grid gap-6 xl:grid-cols-[380px_1fr] items-start">
        <Card className="p-4">
          <h2 className="text-sm font-semibold mb-3">Árvore de categorias</h2>
          {cats && cats.length === 0 ? <EmptyState icon={<FolderTree className="size-6" />} title="Nenhuma categoria">Crie as suas ou use a árvore de exemplo.</EmptyState> : (
            <ul className="flex flex-col gap-1">{cats?.map((c) => (
              <li key={c.id} className={cx("rounded-md px-2 py-1.5", c.parent_id ? "ml-4" : "font-semibold")}>
                <button className="flex w-full items-center gap-2 text-left text-sm hover:text-accent-2" onClick={() => setOpen(open === c.id ? null : c.id)}>
                  <span className="truncate">{c.name}</span>
                  {c.products > 0 && <Badge>{c.products}</Badge>}
                  {c.ml_category_id && <Badge tone={c.ml_category_confirmed ? "ok" : "warn"}>{c.ml_category_id}{c.ml_category_confirmed ? "" : " ?"}</Badge>}
                  {!c.keywords.phrases?.length && !c.keywords.words?.length && c.parent_id && <Badge tone="warn">sem regras</Badge>}
                </button>
                {open === c.id && write && <CategoryEditor cat={c} onSaved={reload} />}
              </li>
            ))}</ul>
          )}
          {write && (
            <div className="mt-4 flex flex-col gap-2 border-t border-line pt-4">
              <Input aria-label="Nova categoria" placeholder="Nova categoria" value={newCat.name} onChange={(e) => setNewCat({ ...newCat, name: e.target.value })} />
              <Select aria-label="Categoria pai" value={newCat.parent} onChange={(e) => setNewCat({ ...newCat, parent: e.target.value })}>
                <option value="">(categoria principal)</option>{cats?.filter((c) => !c.parent_id).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
              <Button size="sm" disabled={!newCat.name.trim()} onClick={() => act(() => api(`${base}/categories`, { method: "POST", body: { name: newCat.name, parent_id: newCat.parent || null } }), () => { setNewCat({ name: "", parent: "" }); return "Categoria criada."; })}>Adicionar</Button>
            </div>
          )}
        </Card>

        <Card className="p-4 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <h2 className="text-sm font-semibold flex items-center gap-2"><Sparkles className="size-4 text-accent" />Fila de revisão</h2>
            <Select aria-label="Visão" className="h-8 ml-auto" value={view} onChange={(e) => setView(e.target.value as "review" | "confirmed")}>
              <option value="review">A revisar</option><option value="confirmed">Confirmados</option>
            </Select>
          </div>
          {write && selected.size > 0 && (
            <div className="mb-3 flex flex-wrap items-center gap-2 rounded-md border border-accent/40 bg-accent-soft px-3 py-2 text-sm">
              <span>{selected.size} selecionado(s)</span>
              <Button size="sm" onClick={() => act(() => api(`${base}/classification/confirm`, { method: "POST", body: { product_ids: [...selected], mode: "accept_suggestion" } }), (r) => `${(r as { changed: number }).changed} sugestão(ões) aceita(s).`)}>Aceitar sugestões</Button>
              <Select aria-label="Mover para" className="h-8" value={target} onChange={(e) => setTarget(e.target.value)}><option value="">Definir categoria…</option>{cats?.filter((c) => c.parent_id).map((c) => <option key={c.id} value={c.id}>{c.path}</option>)}</Select>
              <Button size="sm" variant="primary" disabled={!target} onClick={() => act(() => api(`${base}/classification/confirm`, { method: "POST", body: { product_ids: [...selected], mode: "set", category_id: target } }), (r) => `${(r as { changed: number }).changed} produto(s) confirmado(s).`)}>Confirmar</Button>
            </div>
          )}
          {rows && rows.length === 0 ? <p className="text-sm text-muted">{view === "review" ? "Nada para revisar. Rode a classificação após importar produtos." : "Nenhum produto confirmado."}</p> : (
            <div className="overflow-x-auto rounded-md border border-line">
              <table className="w-full text-sm"><tbody>{rows?.map((r) => (
                <tr key={r.product_id} className="border-t border-line first:border-0 align-top">
                  {write && view === "review" && <td className="px-3 py-2"><input type="checkbox" aria-label={`Selecionar ${r.name}`} checked={selected.has(r.product_id)} onChange={(e) => { const s = new Set(selected); if (e.target.checked) s.add(r.product_id); else s.delete(r.product_id); setSelected(s); }} className="size-4 accent-[var(--color-accent)]" /></td>}
                  <td className="px-3 py-2"><p className="font-medium">{r.name}</p><p className="font-mono text-xs text-faint">{r.sku}</p></td>
                  <td className="px-3 py-2">{r.category_path ?? <span className="text-faint">—</span>}<p className="text-xs text-faint">{r.evidence.slice(0, 3).join(" · ")}</p></td>
                  <td className="px-3 py-2 whitespace-nowrap">{r.status === "confirmed" ? <Badge tone="ok">confirmado</Badge> : <Badge tone={CONF[r.confidence as keyof typeof CONF]?.tone ?? "neutral"}>{CONF[r.confidence as keyof typeof CONF]?.label}</Badge>}</td>
                </tr>
              ))}</tbody></table>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
