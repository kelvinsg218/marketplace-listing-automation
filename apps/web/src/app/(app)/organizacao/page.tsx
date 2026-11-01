"use client";

import { useState } from "react";
import { UserPlus } from "lucide-react";
import { api, ApiError, can, type Member, type Role } from "@/lib/api";
import { ROLE_LABEL, when } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { Alert, Badge, Button, Card, Field, Input, PageHeader, Select, Skeleton } from "@/components/ui";

const ROLES: Role[] = ["owner", "admin", "editor", "viewer"];
const ROLE_HELP: Record<Role, string> = {
  owner: "Tudo, inclusive gerenciar proprietários.",
  admin: "Catálogo, membros e histórico.",
  editor: "Cria e edita o catálogo.",
  viewer: "Somente leitura.",
};

export default function OrganizationPage() {
  const { org, role, me } = useSession();
  const { data, error, loading, reload } = useApi<Member[]>(org ? `/orgs/${org.id}/members` : null);
  const [email, setEmail] = useState("");
  const [newRole, setNewRole] = useState<Role>("editor");
  const [msg, setMsg] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const manage = can.manageMembers(role);
  const assignable = ROLES.filter((r) => r !== "owner" || role === "owner");

  async function run(fn: () => Promise<unknown>, ok: string) {
    setMsg(null);
    try { await fn(); setMsg({ tone: "ok", text: ok }); reload(); }
    catch (err) { setMsg({ tone: "danger", text: err instanceof ApiError ? err.message : "Falha na operação." }); }
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    await run(() => api(`/orgs/${org!.id}/members`, { method: "POST", body: { email, role: newRole } }), "Membro adicionado.");
    setEmail("");
    setBusy(false);
  }

  return (
    <>
      <PageHeader title="Organização" description={`Membros e papéis de ${org?.name}. As permissões são aplicadas pelo servidor.`} />
      {msg && <div className="mb-4"><Alert tone={msg.tone}>{msg.text}</Alert></div>}
      {error && <Alert>{error}</Alert>}

      <div className="grid gap-6 xl:grid-cols-[1fr_360px] items-start">
        <Card className="overflow-hidden">
          {loading && !data ? <div className="p-4"><Skeleton className="h-40" /></div> : data && (
            <ul>
              {data.map((m) => {
                const self = m.user.id === me?.user.id;
                const locked = !manage || (m.role === "owner" && role !== "owner");
                return (
                  <li key={m.user.id} className="flex flex-wrap items-center gap-3 px-5 py-4 border-b border-line last:border-0">
                    <span className="grid place-items-center size-9 rounded-full bg-bg-2 text-xs font-semibold text-muted">
                      {m.user.name.slice(0, 2).toUpperCase()}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="font-medium truncate">{m.user.name} {self && <Badge className="ml-1">você</Badge>}</p>
                      <p className="text-xs text-faint truncate">{m.user.email} · desde {when(m.created_at)}</p>
                    </div>
                    {locked ? <Badge tone={m.role === "owner" ? "accent" : "neutral"}>{ROLE_LABEL[m.role]}</Badge> : (
                      <div className="flex items-center gap-2">
                        <Select aria-label={`Papel de ${m.user.name}`} value={m.role}
                          onChange={(e) => run(() => api(`/orgs/${org!.id}/members/${m.user.id}`, { method: "PATCH", body: { role: e.target.value } }), "Papel atualizado.")}>
                          {assignable.concat(assignable.includes(m.role) ? [] : [m.role]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                        </Select>
                        <Button size="sm" variant="ghost" onClick={() => confirm(`Remover ${m.user.name} da organização?`) &&
                          run(() => api(`/orgs/${org!.id}/members/${m.user.id}`, { method: "DELETE" }), "Membro removido.")}>Remover</Button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <div className="flex flex-col gap-4">
          {manage && (
            <Card className="p-5">
              <h2 className="text-sm font-semibold flex items-center gap-2"><UserPlus className="size-4 text-accent" />Adicionar membro</h2>
              <p className="mt-1 text-xs text-faint">A pessoa precisa ter uma conta. Convites por e-mail chegam em uma próxima etapa.</p>
              <form onSubmit={add} className="mt-4 flex flex-col gap-3">
                <Field label="E-mail">{(id) => <Input id={id} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />}</Field>
                <Field label="Papel">{(id) => (
                  <Select id={id} value={newRole} onChange={(e) => setNewRole(e.target.value as Role)}>
                    {assignable.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                  </Select>
                )}</Field>
                <Button type="submit" variant="primary" busy={busy}>Adicionar</Button>
              </form>
            </Card>
          )}
          <Card className="p-5">
            <h2 className="text-sm font-semibold">Papéis</h2>
            <dl className="mt-3 flex flex-col gap-2.5 text-sm">
              {ROLES.map((r) => <div key={r}><dt className="font-medium">{ROLE_LABEL[r]}</dt><dd className="text-muted text-xs">{ROLE_HELP[r]}</dd></div>)}
            </dl>
          </Card>
        </div>
      </div>
    </>
  );
}
