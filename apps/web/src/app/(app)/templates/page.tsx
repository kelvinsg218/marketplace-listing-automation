"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { FileSpreadsheet, Upload } from "lucide-react";
import { ApiError, apiUpload, can, type SellerAccount, type Template } from "@/lib/api";
import { when } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { Alert, Button, Card, EmptyState, Field, PageHeader, Select, Skeleton } from "@/components/ui";
import { fmtDate, SOURCE_LABEL, TemplateStatusBadge } from "@/components/listing-ui";

export default function TemplatesPage() {
  const { org, role } = useSession();
  const { data, error, loading, reload } = useApi<Template[]>(org ? `/orgs/${org.id}/templates` : null);
  const { data: accounts } = useApi<SellerAccount[]>(org ? `/orgs/${org.id}/seller-accounts` : null);
  const [account, setAccount] = useState("");
  const [source, setSource] = useState("categories");
  const [msg, setMsg] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function upload(file: File) {
    setBusy(true); setMsg(null);
    const fd = new FormData();
    fd.append("file", file); fd.append("seller_account_id", account); fd.append("source", source);
    try {
      const t = await apiUpload<Template>(`/orgs/${org!.id}/templates`, fd);
      setMsg({ tone: t.status === "invalid" ? "danger" : "ok", text: t.status === "invalid" ? `Arquivo registrado, mas não pôde ser lido: ${t.warnings.join(" ")}` : "Template registrado e inspecionado." });
      reload();
    } catch (err) { setMsg({ tone: "danger", text: err instanceof ApiError ? err.message : "Falha no envio." }); }
    finally { setBusy(false); }
  }

  return (
    <>
      <PageHeader title="Templates" description="Planilhas oficiais baixadas no Anunciador em massa. O arquivo original é guardado intacto; o MLA só lê a estrutura e nunca altera abas, colunas ou linhas de instrução (P1 p.6, P2 p.2)." />
      {msg && <div className="mb-4"><Alert tone={msg.tone}>{msg.text}</Alert></div>}
      {error && <Alert>{error}</Alert>}

      {can.write(role) && (
        <Card className="p-5 mb-6">
          <h2 className="text-sm font-semibold flex items-center gap-2"><Upload className="size-4 text-accent" />Registrar planilha oficial</h2>
          <p className="mt-1 text-xs text-faint">No Mercado Livre: Anúncios → Anunciar → Em massa → gere e baixe a planilha (P1 p.1, p.5). Envie o .xlsx sem editar.</p>
          {accounts && accounts.length === 0 ? (
            <div className="mt-4"><Alert tone="info">Cadastre primeiro a conta de vendedor em <Link href="/marketplaces/" className="underline">Marketplaces</Link>.</Alert></div>
          ) : (
            <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_auto] items-end">
              <Field label="Conta que baixou a planilha">{(id) => (
                <Select id={id} value={account} onChange={(e) => setAccount(e.target.value)}>
                  <option value="">Selecione…</option>
                  {accounts?.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
                </Select>
              )}</Field>
              <Field label="Como foi gerada">{(id) => (
                <Select id={id} value={source} onChange={(e) => setSource(e.target.value)}>
                  {Object.entries(SOURCE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </Select>
              )}</Field>
              <input ref={fileRef} type="file" accept=".xlsx" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
              <Button variant="primary" busy={busy} disabled={!account} onClick={() => fileRef.current?.click()}><FileSpreadsheet className="size-4" />Escolher .xlsx</Button>
            </div>
          )}
        </Card>
      )}

      <Card className="overflow-hidden">
        {loading && !data ? <div className="p-4"><Skeleton className="h-32" /></div> : data && data.length === 0 ? (
          <EmptyState icon={<FileSpreadsheet className="size-6" />} title="Nenhum template registrado">
            Sem uma planilha oficial real, o MLA não gera arquivos para o Anunciador em massa.
          </EmptyState>
        ) : data && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs uppercase tracking-wider text-faint border-b border-line">
                <th className="px-4 py-3 font-semibold">Arquivo</th><th className="px-4 py-3 font-semibold hidden md:table-cell">Conta</th>
                <th className="px-4 py-3 font-semibold hidden lg:table-cell">Abas de categoria</th><th className="px-4 py-3 font-semibold">Prazo</th>
                <th className="px-4 py-3 font-semibold">Situação</th>
              </tr></thead>
              <tbody>
                {data.map((t) => (
                  <tr key={t.id} className="border-b border-line last:border-0 hover:bg-card-hover">
                    <td className="px-4 py-3 max-w-[300px]">
                      <Link href={`/templates/detalhe/?id=${t.id}`} className="block truncate font-medium hover:text-accent-2">{t.original_filename}</Link>
                      <span className="text-xs text-faint">{SOURCE_LABEL[t.source]} · {when(t.created_at)}</span>
                    </td>
                    <td className="px-4 py-3 text-muted hidden md:table-cell">{t.seller_account_label}</td>
                    <td className="px-4 py-3 text-muted hidden lg:table-cell">{t.sheets.filter((s) => !s.is_help && s.state === "visible").map((s) => s.name).join(", ") || "—"}</td>
                    <td className="px-4 py-3 tabular-nums">{fmtDate(t.deadline_date)}</td>
                    <td className="px-4 py-3"><TemplateStatusBadge t={t} /></td>
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
