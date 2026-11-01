import { ComingSoon } from "@/components/coming-soon";

export default function Page() {
  return <ComingSoon title="Anúncios em massa" description="Fluxo guiado do catálogo até a planilha oficial do Mercado Livre." stage="Etapa D — Mercado Livre"
    items={["1. Marketplace", "2. Template oficial", "3. Seleção de produtos", "4. Mapeamento de atributos", "5. Validação", "6. Correção",
      "7. Revisão", "8. Exportação da planilha", "9. Acompanhamento do lote"]}
    blocker="Bloqueado: a exportação só será implementada sobre uma planilha oficial baixada da conta de vendedor (formato ainda não comprovado)." />;
}
