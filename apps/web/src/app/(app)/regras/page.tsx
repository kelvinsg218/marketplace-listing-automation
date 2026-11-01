"use client";

import Link from "next/link";
import { useState } from "react";
import { History, Workflow } from "lucide-react";
import { api, ApiError, can, type Rule, type RuleVersion } from "@/lib/api";
import { when } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { Alert, Badge, Button, Card, EmptyState, PageHeader, Skeleton } from "@/components/ui";

const SCOPE_LABEL: Record<string, string> = {
  organization: "Organização", account: "Conta", category: "Categoria", template: "Template", batch: "Somente um lote",
};

function Versions({ orgId, rule, onChange }: { orgId: string; rule: Rule; onChange: () => void }) {
  const { role } = useSession();
  const { data } = useApi<RuleVersion[]>(`/orgs/${orgId}/rules/${rule.id}/versions`);
  const [msg, setMsg] = useState<string | null>(null);
  if (!data) return <Skeleton className="h-16" />;
  return (
    <div className="mt-3 flex flex-col gap-2">
      {msg && <Alert>{msg}</Alert>}
      {data.map((v) => (
        <div key={v.version} className="flex flex-wrap items-center gap-2 rounded-md border border-line bg-bg-2 px-3 py-2 text-xs">
          <Badge tone={v.version === rule.version ? "accent" : "neutral"}>v{v.version}</Badge>
          <span className="text-muted">{when(v.created_at)} · {v.author ?? "—"} · {v.note}</span>
          <code className="text-faint truncate max-w-[420px]">{JSON.stringify(v.definition.params)}</code>
          {v.version !== rule.version && can.write(role) && (
            <Button size="sm" variant="ghost" className="ml-auto" onClick={async () => {
              try { await api(`/orgs/${orgId}/rules/${rule.id}/revert`, { method: "POST", body: { version: v.version } }); onChange(); }
              catch (e) { setMsg(e instanceof ApiError ? e.message : "Falha."); }
            }}>Reverter para v{v.version}</Button>
          )}
        </div>
      ))}
    </div>
  );
}

export default function RulesPage() {
  const { org, role } = useSession();
  const { data, error, loading, reload } = useApi<Rule[]>(org ? `/orgs/${org.id}/rules` : null);
  const [open, setOpen] = useState<string | null>(null);
  return (
    <>
      <PageHeader title="Regras adaptativas" description="Ajustes aplicados na geração das planilhas, criados por formulário, pelo Assistente de Correção ou a partir de um pedido em texto. Toda alteração gera nova versão; nenhuma regra muda exigências oficiais do template."
        actions={<Link href="/assistente/"><Button variant="primary">Nova regra pelo assistente</Button></Link>} />
      <Alert tone="info">Ordem de aplicação: organização → conta → categoria → template → lote (a mais específica prevalece). Depois das regras, a validação oficial do arquivo sempre é executada.</Alert>
      {error && <div className="mt-4"><Alert>{error}</Alert></div>}
      <Card className="mt-6 overflow-hidden">
        {loading && !data ? <div className="p-4"><Skeleton className="h-32" /></div> : data && data.length === 0 ? (
          <EmptyState icon={<Workflow className="size-6" />} title="Nenhuma regra criada">Use o Assistente de Correção para criar a primeira.</EmptyState>
        ) : (
          <ul>{data?.map((r) => (
            <li key={r.id} className="px-5 py-4 border-b border-line last:border-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{r.name}</span>
                <Badge>{SCOPE_LABEL[r.scope]}{r.scope === "category" ? `: ${r.scope_ref}` : ""}</Badge>
                <Badge tone="accent">v{r.version}</Badge>
                <Badge tone={r.status === "active" ? "ok" : "neutral"}>{r.status === "active" ? "ativa" : "inativa"}</Badge>
                {r.origin !== "manual" && <Badge tone="info">{r.origin === "prompt" ? "criada por pedido em texto" : "criada a partir de erro"}</Badge>}
                <div className="ml-auto flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => setOpen(open === r.id ? null : r.id)}><History className="size-4" />Versões</Button>
                  {can.write(role) && <Button size="sm" variant="ghost" onClick={async () => { await api(`/orgs/${org!.id}/rules/${r.id}`, { method: "PATCH", body: { status: r.status === "active" ? "inactive" : "active" } }); reload(); }}>{r.status === "active" ? "Desativar" : "Ativar"}</Button>}
                </div>
              </div>
              <p className="mt-1 text-sm text-muted">Coluna “{r.definition.target}” · {r.definition.operation} · {JSON.stringify(r.definition.params)}{r.definition.condition?.when !== "always" ? ` · quando: ${r.definition.condition.when}` : ""}</p>
              {r.origin_text && <p className="mt-1 text-xs text-faint truncate">Pedido original: “{r.origin_text}”</p>}
              {open === r.id && <Versions orgId={org!.id} rule={r} onChange={reload} />}
            </li>
          ))}</ul>
        )}
      </Card>
    </>
  );
}
