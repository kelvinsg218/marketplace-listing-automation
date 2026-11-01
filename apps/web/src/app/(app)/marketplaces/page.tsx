"use client";

import { useState } from "react";
import { Store, Trash2 } from "lucide-react";
import { api, ApiError, can, type SellerAccount } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { Alert, Badge, Button, Card, EmptyState, Field, Input, PageHeader, Skeleton } from "@/components/ui";

export default function MarketplacesPage() {
  const { org, role } = useSession();
  const { data, error, loading, reload } = useApi<SellerAccount[]>(org ? `/orgs/${org.id}/seller-accounts` : null);
  const [form, setForm] = useState({ label: "", external_id: "" });
  const [msg, setMsg] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);
  const manage = can.manageMembers(role);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    try {
      await api(`/orgs/${org!.id}/seller-accounts`, { method: "POST", body: form });
      setForm({ label: "", external_id: "" });
      setMsg({ tone: "ok", text: "Conta adicionada." });
      reload();
    } catch (err) { setMsg({ tone: "danger", text: err instanceof ApiError ? err.message : "Falha ao salvar." }); }
  }

  return (
    <>
      <PageHeader title="Marketplaces" description="Contas de vendedor da organização. O Mercado Livre só aceita planilhas baixadas da própria conta (P1 p.8), então cada template e cada lote ficam presos a uma conta." />
      {msg && <div className="mb-4"><Alert tone={msg.tone}>{msg.text}</Alert></div>}
      {error && <Alert>{error}</Alert>}
      <div className="grid gap-6 xl:grid-cols-[1fr_360px] items-start">
        <Card className="overflow-hidden">
          <div className="flex items-center gap-3 border-b border-line px-5 py-4">
            <span className="grid place-items-center size-9 rounded-md bg-accent-soft text-accent"><Store className="size-5" aria-hidden /></span>
            <div><p className="font-semibold">Mercado Livre</p><p className="text-xs text-faint">Anunciador em massa por planilha oficial · envio manual pelo site</p></div>
          </div>
          {loading && !data ? <div className="p-5"><Skeleton className="h-24" /></div> : data && data.length === 0 ? (
            <EmptyState icon={<Store className="size-6" />} title="Nenhuma conta cadastrada">Cadastre a conta de vendedor que vai baixar as planilhas.</EmptyState>
          ) : (
            <ul>
              {data?.map((a) => (
                <li key={a.id} className="flex items-center gap-3 px-5 py-3 border-b border-line last:border-0">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium truncate">{a.label}</p>
                    <p className="text-xs text-faint">{a.external_id ? `ID do vendedor ${a.external_id}` : "ID do vendedor não informado"}</p>
                  </div>
                  <Badge>{a.templates} {a.templates === 1 ? "template" : "templates"}</Badge>
                  {manage && (
                    <button aria-label={`Remover ${a.label}`} className="p-1.5 rounded-md text-faint hover:text-danger"
                      onClick={async () => {
                        if (!confirm(`Remover a conta ${a.label}?`)) return;
                        try { await api(`/orgs/${org!.id}/seller-accounts/${a.id}`, { method: "DELETE" }); reload(); }
                        catch (err) { setMsg({ tone: "danger", text: err instanceof ApiError ? err.message : "Falha." }); }
                      }}><Trash2 className="size-4" /></button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
        <div className="flex flex-col gap-4">
          {manage && (
            <Card className="p-5">
              <h2 className="text-sm font-semibold">Adicionar conta Mercado Livre</h2>
              <p className="mt-1 text-xs text-faint">Só um nome para identificar a conta. O MLA não guarda senha nem faz login no Mercado Livre.</p>
              <form onSubmit={add} className="mt-4 flex flex-col gap-3">
                <Field label="Nome da conta">{(id) => <Input id={id} required value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder="Ex.: Loja principal" />}</Field>
                <Field label="ID do vendedor (opcional)">{(id) => <Input id={id} inputMode="numeric" value={form.external_id} onChange={(e) => setForm({ ...form, external_id: e.target.value })} />}</Field>
                <Button type="submit" variant="primary">Adicionar</Button>
              </form>
            </Card>
          )}
          <Card className="p-5 text-sm text-muted">
            <h2 className="text-sm font-semibold text-fg">Outros marketplaces</h2>
            <p className="mt-2">Cada marketplace terá um adaptador próprio; nenhum processo é presumido igual ao do Mercado Livre.</p>
          </Card>
        </div>
      </div>
    </>
  );
}
