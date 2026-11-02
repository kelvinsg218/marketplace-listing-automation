"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Archive, ArchiveRestore, Copy, Layers, MoreHorizontal, Pencil, Play, Plus, Trash2 } from "lucide-react";
import { api, ApiError, can, type Batch } from "@/lib/api";
import { when } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { BatchStatusBadge } from "@/components/listing-ui";
import { Alert, Badge, Button, Card, EmptyState, Input, PageHeader, Skeleton } from "@/components/ui";

const PHASES = ["Conta", "Produtos", "Preparação", "Revisão", "Exportação"];
const DELETABLE = ["draft", "needs_fix", "ready"];

function Actions({ b, onDone, onError }: { b: Batch; onDone: (msg: string) => void; onError: (msg: string) => void }) {
  const { org } = useSession();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const url = `/orgs/${org!.id}/batches/${b.id}`;
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  async function run(fn: () => Promise<unknown>, msg: string) {
    setOpen(false);
    try { await fn(); onDone(msg); } catch (e) { onError(e instanceof ApiError ? e.message : "Falha."); }
  }
  const canDelete = DELETABLE.includes(b.status) && b.exports === 0;
  const item = "flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-card-hover disabled:opacity-40 disabled:pointer-events-none";
  return (
    <div className="relative" ref={ref}>
      <button aria-label={`Ações do lote ${b.name}`} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}
        className="rounded-md p-1.5 text-muted hover:text-fg hover:bg-card"><MoreHorizontal className="size-5" /></button>
      {open && (
        <div role="menu" className="absolute right-0 z-20 mt-1 w-52 overflow-hidden rounded-md border border-line bg-bg-2 shadow-2xl">
          <button role="menuitem" className={item} onClick={() => router.push(`/anuncios-em-massa/lote/?id=${b.id}`)}><Play className="size-4" />Continuar</button>
          <button role="menuitem" className={item} onClick={() => { const name = prompt("Novo nome do lote:", b.name); if (name && name.trim()) run(() => api(url, { method: "PATCH", body: { name } }), "Lote renomeado."); }}
            disabled={["sent_external", "result_received", "done"].includes(b.status)}><Pencil className="size-4" />Renomear</button>
          <button role="menuitem" className={item} onClick={() => run(() => api(`${url}/duplicate`, { method: "POST" }), "Lote duplicado como rascunho.")}><Copy className="size-4" />Duplicar</button>
          {b.archived
            ? <button role="menuitem" className={item} onClick={() => run(() => api(`${url}/unarchive`, { method: "POST" }), "Lote restaurado.")}><ArchiveRestore className="size-4" />Desarquivar</button>
            : <button role="menuitem" className={item} onClick={() => run(() => api(`${url}/archive`, { method: "POST" }), "Lote arquivado.")}><Archive className="size-4" />Arquivar</button>}
          <button role="menuitem" className={`${item} text-danger`} disabled={!canDelete}
            title={canDelete ? "" : "Lotes que geraram planilha ou foram enviados são preservados; arquive-os."}
            onClick={() => { if (confirm(`Excluir o rascunho "${b.name}"? Os produtos do catálogo não são afetados.`)) run(() => api(url, { method: "DELETE" }), "Rascunho excluído."); }}>
            <Trash2 className="size-4" />Excluir rascunho</button>
        </div>
      )}
    </div>
  );
}

export default function BulkListingPage() {
  const { org, role } = useSession();
  const router = useRouter();
  const [archived, setArchived] = useState(false);
  const { data, error, loading, reload } = useApi<Batch[]>(org ? `/orgs/${org.id}/batches?archived=${archived}` : null);
  const [name, setName] = useState("");
  const [msg, setMsg] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      const b = await api<Batch>(`/orgs/${org!.id}/batches`, { method: "POST", body: { name: name || `Lote ${new Date().toLocaleDateString("pt-BR")}` } });
      router.push(`/anuncios-em-massa/lote/?id=${b.id}`);
    } catch (e2) { setMsg({ tone: "danger", text: e2 instanceof ApiError ? e2.message : "Falha ao criar." }); }
  }

  return (
    <>
      <PageHeader title="Anúncios em massa" description="Prepare lotes para o Anunciador em massa do Mercado Livre em cinco fases. Exportar não publica nada; o envio é feito por você no site oficial." />
      {(msg || error) && <div className="mb-4"><Alert tone={msg?.tone ?? "danger"}>{msg?.text ?? error}</Alert></div>}
      {can.write(role) && !archived && (
        <Card className="p-5 mb-6">
          <form onSubmit={create} className="flex flex-col sm:flex-row gap-3 sm:items-end">
            <label className="flex-1 flex flex-col gap-1.5"><span className="text-[13px] font-medium text-muted">Novo lote</span>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex.: Filtros — novembro" /></label>
            <Button type="submit" variant="primary"><Plus className="size-4" />Criar lote</Button>
          </form>
        </Card>
      )}
      <div className="mb-3 flex gap-2">
        <Button size="sm" variant={archived ? "ghost" : "secondary"} onClick={() => setArchived(false)}>Ativos</Button>
        <Button size="sm" variant={archived ? "secondary" : "ghost"} onClick={() => setArchived(true)}><Archive className="size-4" />Arquivados</Button>
      </div>
      <Card className="overflow-visible">
        {loading && !data ? <div className="p-4"><Skeleton className="h-32" /></div> : data && data.length === 0 ? (
          <EmptyState icon={<Layers className="size-6" />} title={archived ? "Nenhum lote arquivado" : "Nenhum lote ainda"}>{archived ? "" : "Crie um lote para começar."}</EmptyState>
        ) : data && (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs uppercase tracking-wider text-faint border-b border-line">
              <th className="px-4 py-3 font-semibold">Lote</th><th className="px-4 py-3 font-semibold hidden md:table-cell">Conta / template</th>
              <th className="px-4 py-3 font-semibold text-right">Produtos</th><th className="px-4 py-3 font-semibold">Situação</th><th className="w-12" />
            </tr></thead>
            <tbody>
              {data.map((b) => (
                <tr key={b.id} className="border-b border-line last:border-0 hover:bg-card-hover">
                  <td className="px-4 py-3"><Link href={`/anuncios-em-massa/lote/?id=${b.id}`} className="font-medium hover:text-accent-2">{b.name}</Link>
                    <div className="text-xs text-faint">atualizado {when(b.updated_at)} · parou em: {PHASES[(b.last_phase ?? 1) - 1]}</div></td>
                  <td className="px-4 py-3 text-muted hidden md:table-cell">{b.seller_account_label ?? "—"}<div className="text-xs text-faint truncate max-w-64">{b.template_filename ?? "sem template"}{b.sheet_name ? ` · ${b.sheet_name}` : ""}</div></td>
                  <td className="px-4 py-3 text-right tabular-nums">{b.items}</td>
                  <td className="px-4 py-3"><BatchStatusBadge status={b.status} />{b.exports > 0 && <Badge className="ml-1">{b.exports} planilha(s)</Badge>}</td>
                  <td className="px-2 py-3">{can.write(role) && <Actions b={b} onDone={(t) => { setMsg({ tone: "ok", text: t }); reload(); }} onError={(t) => setMsg({ tone: "danger", text: t })} />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
