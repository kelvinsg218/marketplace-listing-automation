import { ComingSoon } from "@/components/coming-soon";

export default function Page() {
  return <ComingSoon title="Lotes e exportações" description="Rastreabilidade de cada planilha gerada." stage="Etapa E — Lotes e resultados"
    items={["Rascunho → Validando → Requer correção → Pronto → Exportado", "Enviado externamente e Resultado recebido somente com confirmação ou evidência",
      "Download autorizado por organização", "Reprocessamento de rejeitados"]} />;
}
