import { ComingSoon } from "@/components/coming-soon";

export default function Page() {
  return <ComingSoon title="Importações" description="Central de importação de catálogos." stage="Etapa C — Catálogo e importações"
    items={["CSV, XLSX, JSON, XML, PDF e ZIP", "Pacotes de imagens por SKU", "Pré-visualização e mapeamento de colunas", "Duplicatas e atualização de existentes",
      "Relatório de inconsistências", "Processamento em segundo plano com cancelamento"]} />;
}
