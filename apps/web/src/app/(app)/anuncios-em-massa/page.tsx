"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Layers, Plus } from "lucide-react";
import { api, ApiError, can, type Batch } from "@/lib/api";
import { when } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { BatchStatusBadge } from "@/components/listing-ui";
import { Alert, Button, Card, EmptyState, Input, PageHeader, Skeleton } from "@/components/ui";

export default function BulkListingPage() {
  const { org, role } = useSession();
  const router = useRouter();
  const { data, error, loading } = useApi<Batch[]>(org ? `/orgs/${org.id}/batches` : null);
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      const b = await api<Batch>(`/orgs/${org!.id}/batches`, { method: "POST", body: { name: name || `Lote ${new Date().toLocaleDateString("pt-BR")}` } });
      router.push(`/anuncios-em-massa/lote/?id=${b.id}`);
    } catch (e2) { setErr(e2 instanceof ApiError ? e2.message : "Falha ao criar."); }
  }

  return (
    <>
      <PageHeader title="Anúncios em massa" description="Prepare lotes para o Anunciador em massa do Mercado Livre: conta, template oficial, produtos, mapeamento, validação e revisão. Exportar não publica nada; o envio é feito por você no site oficial." />
      {(err || error) && <div className="mb-4"><Alert>{err ?? error}</Alert></div>}
      {can.write(role) && (
        <Card className="p-5 mb-6">
          <form onSubmit={create} className="flex flex-col sm:flex-row gap-3 sm:items-end">
            <label className="flex-1 flex flex-col gap-1.5"><span className="text-[13px] font-medium text-muted">Novo lote</span>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex.: Filtros — novembro" /></label>
            <Button type="submit" variant="primary"><Plus className="size-4" />Criar lote</Button>
          </form>
        </Card>
      )}
      <Card className="overflow-hidden">
        {loading && !data ? <div className="p-4"><Skeleton className="h-32" /></div> : data && data.length === 0 ? (
          <EmptyState icon={<Layers className="size-6" />} title="Nenhum lote ainda">Crie um lote para começar o fluxo guiado.</EmptyState>
        ) : data && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs uppercase tracking-wider text-faint border-b border-line">
                <th className="px-4 py-3 font-semibold">Lote</th><th className="px-4 py-3 font-semibold hidden md:table-cell">Conta / template</th>
                <th className="px-4 py-3 font-semibold text-right">Produtos</th><th className="px-4 py-3 font-semibold">Situação</th>
              </tr></thead>
              <tbody>
                {data.map((b) => (
                  <tr key={b.id} className="border-b border-line last:border-0 hover:bg-card-hover">
                    <td className="px-4 py-3"><Link href={`/anuncios-em-massa/lote/?id=${b.id}`} className="font-medium hover:text-accent-2">{b.name}</Link>
                      <div className="text-xs text-faint">atualizado {when(b.updated_at)}</div></td>
                    <td className="px-4 py-3 text-muted hidden md:table-cell">{b.seller_account_label ?? "—"}<div className="text-xs text-faint truncate max-w-64">{b.template_filename ?? "sem template"}{b.sheet_name ? ` · ${b.sheet_name}` : ""}</div></td>
                    <td className="px-4 py-3 text-right tabular-nums">{b.items}</td>
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
