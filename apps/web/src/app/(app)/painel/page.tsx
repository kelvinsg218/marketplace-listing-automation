"use client";

import Link from "next/link";
import { AlertTriangle, ArrowUpRight, Boxes, CheckCircle2, FileSpreadsheet, Layers, PackagePlus, ShieldAlert } from "lucide-react";
import type { Dashboard } from "@/lib/api";
import { can } from "@/lib/api";
import { count, describeEvent, STATUS_LABEL, when } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { Alert, Button, Card, cx, EmptyState, PageHeader, Skeleton } from "@/components/ui";

function Kpi({ label, value, icon: Icon, tone = "neutral", note, href }: {
  label: string; value: number | null; icon: React.ElementType; tone?: "neutral" | "ok" | "warn" | "accent"; note?: string; href?: string;
}) {
  const toneClass = { neutral: "text-muted bg-line/60", ok: "text-ok bg-ok/10", warn: "text-warn bg-warn/10", accent: "text-accent bg-accent-soft" }[tone];
  const body = (
    <Card className={cx("p-5 h-full transition-colors", href && "hover:border-line-strong hover:bg-card-hover")}>
      <div className="flex items-start justify-between">
        <p className="text-[13px] font-medium text-muted">{label}</p>
        <span className={cx("grid place-items-center size-8 rounded-md", toneClass)}><Icon className="size-4" aria-hidden /></span>
      </div>
      <p className={cx("mt-3 text-[32px] leading-none font-bold tracking-tight", value == null && "text-faint")}>{count(value)}</p>
      <p className="mt-2 text-xs text-faint min-h-4">{note}</p>
    </Card>
  );
  return href ? <Link href={href} className="block rounded-lg">{body}</Link> : body;
}

function CatalogHealth({ d }: { d: Dashboard }) {
  const pct = d.products_total ? Math.round((d.products_complete / d.products_total) * 100) : 0;
  const segments: { key: keyof Dashboard["products_by_status"]; color: string }[] = [
    { key: "active", color: "bg-accent" }, { key: "draft", color: "bg-accent/45" }, { key: "archived", color: "bg-line-strong" },
  ];
  return (
    <Card className="p-6">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-base font-semibold">Saúde do catálogo</h2>
        <span className="text-xs text-faint">regras internas do catálogo</span>
      </div>
      <div className="mt-6 flex items-end gap-3">
        <span className="text-5xl font-extrabold tracking-tight">{pct}<span className="text-2xl text-muted">%</span></span>
        <span className="pb-1.5 text-sm text-muted">dos produtos sem pendências</span>
      </div>
      <div className="mt-4 h-2 rounded-full bg-line overflow-hidden" role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Produtos completos">
        <div className="h-full rounded-full bg-gradient-to-r from-accent to-accent-2 transition-[width] duration-700" style={{ width: `${pct}%` }} />
      </div>
      <h3 className="mt-8 text-[13px] font-medium text-muted">Por status</h3>
      <div className="mt-3 flex h-3 rounded-sm overflow-hidden gap-px bg-bg">
        {segments.map(({ key, color }) => d.products_by_status[key] > 0 && (
          <div key={key} className={color} style={{ flexGrow: d.products_by_status[key] }} title={`${STATUS_LABEL[key]}: ${d.products_by_status[key]}`} />
        ))}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-sm">
        {segments.map(({ key, color }) => (
          <li key={key} className="flex items-center gap-2">
            <span className={cx("size-2.5 rounded-sm", color)} aria-hidden />
            <span className="text-muted">{STATUS_LABEL[key]}</span>
            <span className="font-semibold">{count(d.products_by_status[key])}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Activity({ d }: { d: Dashboard }) {
  return (
    <Card className="p-6">
      <h2 className="text-base font-semibold">Atividade recente</h2>
      {d.recent_activity.length === 0 ? (
        <p className="mt-4 text-sm text-muted">Nenhuma atividade ainda.</p>
      ) : (
        <ol className="mt-4 flex flex-col">
          {d.recent_activity.map((e) => (
            <li key={e.id} className="flex gap-3 py-2.5 border-b border-line last:border-0">
              <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-accent" aria-hidden />
              <div className="min-w-0 text-sm">
                <p className="truncate"><span className="font-medium">{e.user_name ?? "Sistema"}</span> <span className="text-muted">{describeEvent(e.action, e.details)}</span></p>
                <p className="text-xs text-faint">{when(e.created_at)}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

export default function DashboardPage() {
  const { org, role, me } = useSession();
  const { data: d, error, loading } = useApi<Dashboard>(org ? `/orgs/${org.id}/dashboard` : null);
  const first = me?.user.name.split(" ")[0];

  return (
    <>
      <PageHeader title={`Olá, ${first}`} description={`Visão geral de ${org?.name}.`}
        actions={can.write(role) && <Link href="/catalogo/?novo=1"><Button variant="primary"><PackagePlus className="size-4" />Novo produto</Button></Link>} />
      {error && <Alert>{error}</Alert>}
      {loading && !d ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-[132px]" />)}</div>
      ) : d && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <Kpi label="Total de produtos" value={d.products_total} icon={Boxes} tone="accent" href="/catalogo/" />
            <Kpi label="Produtos completos" value={d.products_complete} icon={CheckCircle2} tone="ok" note="sem erros nem avisos internos" />
            <Kpi label="Com pendências" value={d.products_with_pendings} icon={AlertTriangle} tone="warn" href="/catalogo/" note="corrija antes de preparar anúncios" />
            <Kpi label="Lotes criados" value={d.batches_total} icon={Layers} href="/lotes/" note="preparações de anúncios em massa" />
            <Kpi label="Planilhas exportadas" value={d.exports_total} icon={FileSpreadsheet} note="aguarda template oficial do Mercado Livre" />
            <Kpi label="Erros de validação" value={d.validation_errors} icon={ShieldAlert} note="disponível na etapa D (validação)" />
          </div>
          {d.products_total === 0 ? (
            <Card className="mt-6">
              <EmptyState icon={<Boxes className="size-6" />} title="Seu catálogo está vazio"
                action={can.write(role) && <Link href="/catalogo/?novo=1"><Button variant="primary">Cadastrar primeiro produto <ArrowUpRight className="size-4" /></Button></Link>}>
                Cadastre produtos manualmente agora. A importação de planilhas e arquivos em massa chega na etapa C.
              </EmptyState>
            </Card>
          ) : (
            <div className="mt-6 grid gap-4 xl:grid-cols-[1.4fr_1fr]">
              <CatalogHealth d={d} />
              <Activity d={d} />
            </div>
          )}
        </>
      )}
    </>
  );
}
