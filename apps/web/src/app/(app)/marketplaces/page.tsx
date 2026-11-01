import { ComingSoon } from "@/components/coming-soon";

export default function Page() {
  return <ComingSoon title="Marketplaces" description="Canais de venda configurados pela organização." stage="Etapa D — Mercado Livre"
    items={["Mercado Livre por planilha oficial (primeiro canal)", "Consulta de atributos por categoria (API pública)", "Outros marketplaces por adaptadores próprios",
      "Nenhuma publicação automática sem integração oficial e autorização"]} />;
}
