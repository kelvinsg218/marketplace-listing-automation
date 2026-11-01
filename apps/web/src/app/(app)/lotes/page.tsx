"use client";

import Link from "next/link";
import { PackageOpen } from "lucide-react";
import type { Batch, BatchStatus } from "@/lib/api";
import { when } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { BATCH_STATUS, BatchStatusBadge } from "@/components/listing-ui";
import { Alert, Card, EmptyState, PageHeader, Skeleton } from "@/components/ui";

export default function BatchesPage() {
  const { org } = useSession();
  const { data, error, loading } = useApi<Batch[]>(org ? `/orgs/${org.id}/batches` : null);
  const counts = (data ?? []).reduce<Record<string, number>>((acc, b) => ({ ...acc, [b.status]: (acc[b.status] ?? 0) + 1 }), {});

  return (
    <>
      <PageHeader title="Lotes e exportações" description="Rastreabilidade de cada lote. “Enviado ao ML” e “Resultado recebido” só aparecem com a sua confirmação ou com evidência importada — gerar um arquivo nunca significa anúncio publicado." />
      {error && <Alert>{error}</Alert>}
      {data && data.length > 0 && (
        <div className="mb-5 flex flex-wrap gap-2">
          {(Object.keys(BATCH_STATUS) as BatchStatus[]).filter((s) => counts[s]).map((s) => (
            <span key={s} className="inline-flex items-center gap-2 rounded-md border border-line bg-card px-3 py-1.5 text-sm"><BatchStatusBadge status={s} /><strong>{counts[s]}</strong></span>
          ))}
        </div>
      )}
      <Card className="overflow-hidden">
        {loading && !data ? <div className="p-4"><Skeleton className="h-32" /></div> : data && data.length === 0 ? (
          <EmptyState icon={<PackageOpen className="size-6" />} title="Nenhum lote">Crie lotes em <Link href="/anuncios-em-massa/" className="underline">Anúncios em massa</Link>.</EmptyState>
        ) : data && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs uppercase tracking-wider text-faint border-b border-line">
                <th className="px-4 py-3 font-semibold">Lote</th><th className="px-4 py-3 font-semibold text-right">Produtos</th>
                <th className="px-4 py-3 font-semibold text-right hidden md:table-cell">Linhas</th><th className="px-4 py-3 font-semibold hidden md:table-cell">Última validação</th>
                <th className="px-4 py-3 font-semibold">Situação</th>
              </tr></thead>
              <tbody>
                {data.map((b) => (
                  <tr key={b.id} className="border-b border-line last:border-0 hover:bg-card-hover">
                    <td className="px-4 py-3"><Link href={`/anuncios-em-massa/lote/?id=${b.id}`} className="font-medium hover:text-accent-2">{b.name}</Link>
                      <div className="text-xs text-faint">{b.seller_account_label ?? "sem conta"} · {b.history.length} evento(s)</div></td>
                    <td className="px-4 py-3 text-right tabular-nums">{b.items}</td>
                    <td className="px-4 py-3 text-right tabular-nums hidden md:table-cell">{b.validation.rows ?? "—"}</td>
                    <td className="px-4 py-3 text-muted hidden md:table-cell">{b.validation.validated_at ? `${when(b.validation.validated_at)} · ${b.validation.ready ? "sem erros" : `${b.validation.errors_total} erro(s)`}` : "—"}</td>
                    <td className="px-4 py-3"><BatchStatusBadge status={b.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
