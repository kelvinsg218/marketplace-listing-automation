"use client";

import { useEffect, useState } from "react";
import { Link2, RefreshCw, ShieldCheck, Store, Trash2, Unplug } from "lucide-react";
import { api, ApiError, can, type SellerAccount } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { Alert, Badge, Button, Card, EmptyState, Field, Input, PageHeader, Skeleton } from "@/components/ui";

interface Conn { seller_account_id: string; status: string; nickname: string; remote_user_id: string; expires_at: string | null; checked_at: string | null; last_error: string }
interface Integration { configured: boolean; message: string | null; redirect_uri: string | null; accounts: Conn[] }

const CONN: Record<string, { label: string; tone: "ok" | "warn" | "danger" | "neutral" }> = {
  connected: { label: "Conectada (OAuth)", tone: "ok" }, needs_reauth: { label: "Reconexão necessária", tone: "danger" },
  error: { label: "Falha na última verificação", tone: "warn" }, disconnected: { label: "Desconectada", tone: "neutral" },
  not_connected: { label: "Não conectada", tone: "neutral" },
};
const RETURN: Record<string, { tone: "ok" | "danger" | "info"; text: string }> = {
  conectado: { tone: "ok", text: "Conta conectada pelo OAuth oficial do Mercado Livre." },
  negado: { tone: "info", text: "A autorização foi cancelada no Mercado Livre; nada foi alterado." },
  conta_diferente: { tone: "danger", text: "A conta autorizada no Mercado Livre é diferente do ID de vendedor cadastrado. Nada foi salvo." },
  ja_conectada: { tone: "danger", text: "Esta conta do Mercado Livre já está ligada a outra conta desta organização." },
  expirado: { tone: "danger", text: "O pedido de autorização expirou ou já foi usado. Comece de novo." },
  sessao: { tone: "danger", text: "Sessão ou organização inválida no retorno do Mercado Livre. Entre e tente de novo." },
  sem_permissao: { tone: "danger", text: "Só administradores podem conectar contas." },
  erro: { tone: "danger", text: "O Mercado Livre não confirmou a autorização. Tente novamente mais tarde." },
};

export default function MarketplacesPage() {
  const { org, role } = useSession();
  const { data, error, loading, reload } = useApi<SellerAccount[]>(org ? `/orgs/${org.id}/seller-accounts` : null);
  const [form, setForm] = useState({ label: "", external_id: "" });
  const [msg, setMsg] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);
  const manage = can.manageMembers(role);
  const { data: ml, reload: reloadMl } = useApi<Integration>(org ? `/orgs/${org.id}/integrations/mercadolivre` : null);
  const conns = new Map(ml?.accounts.map((c) => [c.seller_account_id, c]) ?? []);

  useEffect(() => {
    const r = new URLSearchParams(window.location.search).get("ml");
    if (r && RETURN[r]) { setMsg({ tone: RETURN[r].tone === "ok" ? "ok" : "danger", text: RETURN[r].text }); window.history.replaceState(null, "", window.location.pathname); }
  }, []);

  async function oauth(accountId: string, action: "start" | "check" | "refresh" | "disconnect", ok: string) {
    setMsg(null);
    try {
      const r = await api<{ authorization_url?: string }>(`/orgs/${org!.id}/seller-accounts/${accountId}/oauth/${action}`, { method: "POST" });
      if (r.authorization_url) { window.location.assign(r.authorization_url); return; }
      setMsg({ tone: "ok", text: ok });
    } catch (err) { setMsg({ tone: "danger", text: err instanceof ApiError ? err.message : "Falha." }); }
    reloadMl();
  }

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
          {ml && !ml.configured && <div className="px-5 pt-4"><Alert tone="info">{ml.message}</Alert></div>}
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
                  {(() => { const c = conns.get(a.id); const st = CONN[c?.status ?? "not_connected"] ?? CONN.not_connected; return (
                    <div className="flex flex-col items-end gap-1">
                      <Badge tone={st.tone}>{st.label}{c?.nickname ? ` · ${c.nickname}` : ""}</Badge>
                      {c?.last_error && <span className="text-[11px] text-faint max-w-64 truncate" title={c.last_error}>{c.last_error}</span>}
                      {manage && ml?.configured && (
                        <div className="flex gap-1">
                          {c?.status === "connected" || c?.status === "error" ? (<>
                            <Button size="sm" onClick={() => oauth(a.id, "check", "Conexão confirmada com o Mercado Livre.")}><ShieldCheck className="size-4" />Verificar</Button>
                            <Button size="sm" onClick={() => oauth(a.id, "refresh", "Autorização renovada.")}><RefreshCw className="size-4" />Renovar</Button>
                            <Button size="sm" variant="danger" onClick={() => { if (confirm(`Desconectar ${a.label}? Os tokens serão apagados do MLA.`)) oauth(a.id, "disconnect", "Desconectada. Para retirar a permissão também no Mercado Livre, faça isso pela sua conta no Mercado Livre."); }}><Unplug className="size-4" />Desconectar</Button>
                          </>) : <Button size="sm" variant="primary" onClick={() => oauth(a.id, "start", "")}><Link2 className="size-4" />{c && c.status !== "not_connected" ? "Reconectar" : "Conectar"}</Button>}
                        </div>
                      )}
                    </div>); })()}
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
          <Card className="p-5 text-sm text-muted">
            <h2 className="text-sm font-semibold text-fg">Sobre a conexão OAuth</h2>
            <p className="mt-2">A conexão oficial identifica a conta e permite usar a API do Mercado Livre. Ela <strong>não</strong> envia a planilha XLSX: o arquivo gerado continua sendo enviado por você no site do Mercado Livre. O MLA não publica anúncios pela API sem a sua autorização explícita.</p>
            <p className="mt-2">O login acontece na página do Mercado Livre; o MLA nunca vê sua senha. Os tokens ficam cifrados no servidor.</p>
          </Card>
        </div>
      </div>
    </>
  );
}
