"use client";

import { AlertCircle, AlertTriangle, Info } from "lucide-react";
import type { BatchStatus, RuleIssue, Template } from "@/lib/api";
import { Badge, cx } from "./ui";

export const SOURCE_LABEL: Record<string, string> = {
  categories: "Por categorias", codes: "Por códigos universais", links: "Por links de anúncios", shopee: "Por planilha da Shopee", unknown: "Origem não informada",
};

export function TemplateStatusBadge({ t }: { t: Pick<Template, "status" | "expired" | "deadline_date" | "deadline_confirmed"> }) {
  if (t.status === "invalid") return <Badge tone="danger">Inválido</Badge>;
  if (t.status === "archived") return <Badge>Arquivado</Badge>;
  if (t.expired) return <Badge tone="danger">Prazo vencido</Badge>;
  if (!t.deadline_date) return <Badge tone="warn">Prazo desconhecido</Badge>;
  if (!t.deadline_confirmed) return <Badge tone="warn">Prazo a confirmar</Badge>;
  return <Badge tone="ok">Válido</Badge>;
}

export const BATCH_STATUS: Record<BatchStatus, { label: string; tone: "neutral" | "accent" | "ok" | "warn" | "danger" | "info" }> = {
  draft: { label: "Rascunho", tone: "neutral" },
  needs_fix: { label: "Requer correção", tone: "danger" },
  ready: { label: "Pronto", tone: "ok" },
  exported: { label: "Exportado", tone: "accent" },
  sent_external: { label: "Enviado ao ML", tone: "info" },
  result_received: { label: "Resultado recebido", tone: "info" },
  done: { label: "Concluído", tone: "ok" },
};

export function BatchStatusBadge({ status }: { status: BatchStatus }) {
  const s = BATCH_STATUS[status];
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

export const fmtDate = (iso: string | null) => (iso ? new Date(iso + "T12:00:00").toLocaleDateString("pt-BR") : "—");

const SOURCE: Record<RuleIssue["source"], { label: string; tone: "neutral" | "accent" | "info" | "warn" }> = {
  interna: { label: "Regra interna", tone: "neutral" },
  documentacao: { label: "Documentação ML", tone: "accent" },
  template: { label: "Template", tone: "info" },
  hipotese: { label: "Hipótese", tone: "warn" },
};
const SEV = { error: { icon: AlertCircle, cls: "text-danger", label: "Erro" }, warning: { icon: AlertTriangle, cls: "text-warn", label: "Aviso" }, info: { icon: Info, cls: "text-info", label: "Informação" } };

/** Issues always show severity AND source, so documentation rules are never confused with MLA rules or guesses. */
export function IssueList({ issues, showSku }: { issues: RuleIssue[]; showSku?: boolean }) {
  return (
    <ul className="flex flex-col gap-2.5">
      {issues.map((i, n) => {
        const s = SEV[i.severity];
        return (
          <li key={`${i.code}-${i.sku}-${n}`} className="flex gap-2.5 text-sm">
            <s.icon className={cx("size-4 mt-0.5 shrink-0", s.cls)} aria-label={s.label} />
            <div className="min-w-0">
              <p>{showSku && i.sku && <span className="font-mono text-xs text-muted mr-1.5">{i.sku}</span>}{i.message}</p>
              <p className="text-xs text-faint">{i.fix}</p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                <Badge tone={SOURCE[i.source].tone}>{SOURCE[i.source].label}</Badge>
                {i.ref && <Badge>{i.ref}</Badge>}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
