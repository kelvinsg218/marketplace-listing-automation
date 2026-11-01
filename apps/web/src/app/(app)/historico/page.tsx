"use client";

import { History } from "lucide-react";
import { can, type AuditEvent } from "@/lib/api";
import { describeEvent, when } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { Alert, Card, EmptyState, PageHeader, Skeleton } from "@/components/ui";

export default function HistoryPage() {
  const { org, role } = useSession();
  const allowed = can.readAudit(role);
  const { data, error, loading } = useApi<AuditEvent[]>(org && allowed ? `/orgs/${org.id}/audit?limit=200` : null);

  return (
    <>
      <PageHeader title="Histórico" description="Ações sensíveis registradas na organização (auditoria)." />
      {!allowed ? (
        <Alert tone="info">O histórico é visível para proprietários e administradores.</Alert>
      ) : error ? <Alert>{error}</Alert> : (
        <Card className="overflow-hidden">
          {loading && !data ? <div className="p-4"><Skeleton className="h-60" /></div> : data && data.length === 0 ? (
            <EmptyState icon={<History className="size-6" />} title="Nada registrado ainda" />
          ) : data && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wider text-faint border-b border-line">
                    <th scope="col" className="font-semibold px-4 py-3 w-40">Quando</th>
                    <th scope="col" className="font-semibold px-4 py-3">Quem</th>
                    <th scope="col" className="font-semibold px-4 py-3">Ação</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((e) => (
                    <tr key={e.id} className="border-b border-line last:border-0">
                      <td className="px-4 py-3 text-muted whitespace-nowrap tabular-nums">{when(e.created_at)}</td>
                      <td className="px-4 py-3 whitespace-nowrap">{e.user_name ?? "Sistema"}</td>
                      <td className="px-4 py-3 text-muted">{describeEvent(e.action, e.details)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </>
  );
}
