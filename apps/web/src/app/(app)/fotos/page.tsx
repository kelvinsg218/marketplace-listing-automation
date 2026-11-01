"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Images, Search } from "lucide-react";
import type { PhotoStatus } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { Alert, Badge, Card, EmptyState, Input, PageHeader, Skeleton } from "@/components/ui";

const STEPS = [
  ["Abra a planilha baixada", 'Na coluna "Fotos", clique em "Obter URLs no Gestor de fotos" (P3 p.1–2).'],
  ["Crie um grupo por produto", 'Use "Criar grupo de fotos" com o nome do produto; até 10 fotos por grupo, na ordem desejada (P3 p.2).'],
  ["Copie as URLs", 'Clique em "Copiar URLs" no grupo (P3 p.3).'],
  ["Registre no MLA", "Abra o produto aqui e cole as URLs em Fotos. Na exportação elas vão para a coluna Fotos, separadas por vírgula (P3 p.4)."],
];

export default function PhotosPage() {
  const { org } = useSession();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [pending, setPending] = useState(true);
  useEffect(() => { const t = setTimeout(() => setQuery(q), 300); return () => clearTimeout(t); }, [q]);
  const { data, error, loading } = useApi<PhotoStatus[]>(org ? `/orgs/${org.id}/photos/status?only_pending=${pending}&q=${encodeURIComponent(query)}&limit=200` : null);

  return (
    <>
      <PageHeader title="Central de Fotos" description="Fotos do catálogo e as URLs oficiais do Gestor de fotos do Mercado Livre. O MLA não envia fotos ao Gestor (não há integração oficial documentada); ele organiza e confere as URLs." />
      <div className="grid gap-6 xl:grid-cols-[1fr_380px] items-start">
        <div className="min-w-0">
          <div className="flex flex-col sm:flex-row gap-3 mb-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-faint" aria-hidden />
              <Input aria-label="Buscar" placeholder="Buscar por nome ou SKU" value={q} onChange={(e) => setQ(e.target.value)} className="pl-9" />
            </div>
            <label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={pending} onChange={(e) => setPending(e.target.checked)} className="accent-[var(--color-accent)] size-4" />Só pendências</label>
          </div>
          {error && <Alert>{error}</Alert>}
          <Card className="overflow-hidden">
            {loading && !data ? <div className="p-4"><Skeleton className="h-40" /></div> : data && data.length === 0 ? (
              <EmptyState icon={<Images className="size-6" />} title={pending ? "Nenhuma pendência de fotos" : "Nenhum produto"} />
            ) : data && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-xs uppercase tracking-wider text-faint border-b border-line">
                    <th className="px-4 py-3 font-semibold">Produto</th><th className="px-4 py-3 font-semibold text-right">Fotos</th>
                    <th className="px-4 py-3 font-semibold text-right">Com URL oficial</th><th className="px-4 py-3 font-semibold">Situação</th>
                  </tr></thead>
                  <tbody>
                    {data.map((p) => (
                      <tr key={p.product_id} className="border-b border-line last:border-0 hover:bg-card-hover">
                        <td className="px-4 py-3"><Link href={`/catalogo/produto/?id=${p.product_id}`} className="font-medium hover:text-accent-2">{p.name}</Link><div className="font-mono text-xs text-faint">{p.sku}</div></td>
                        <td className="px-4 py-3 text-right tabular-nums">{p.images}</td>
                        <td className="px-4 py-3 text-right tabular-nums">{p.with_url}</td>
                        <td className="px-4 py-3">
                          {p.with_url === 0 ? <Badge tone="warn">Sem URL oficial</Badge> : p.without_url ? <Badge tone="info">{p.without_url} sem URL</Badge> : <Badge tone="ok">OK</Badge>}
                          {p.over_group_limit && <Badge tone="warn" className="ml-1">mais de 10</Badge>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
        <Card className="p-5">
          <h2 className="text-sm font-semibold">Como usar o Gestor de fotos</h2>
          <ol className="mt-4 flex flex-col gap-4">
            {STEPS.map(([title, text], i) => (
              <li key={title} className="flex gap-3">
                <span className="grid place-items-center size-7 shrink-0 rounded-md border border-line bg-bg-2 font-mono text-xs text-accent-2">{i + 1}</span>
                <div><p className="text-sm font-medium">{title}</p><p className="text-xs text-muted">{text}</p></div>
              </li>
            ))}
          </ol>
          <p className="mt-5 text-xs text-faint">O gestor confere requisitos básicos das fotos; confira também os critérios de qualidade da categoria. Use só imagens próprias ou autorizadas (P1 p.6, P3 p.1).</p>
        </Card>
      </div>
    </>
  );
}
