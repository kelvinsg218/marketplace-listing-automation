import { ComingSoon } from "@/components/coming-soon";

export default function Page() {
  return <ComingSoon title="Templates" description="Planilhas oficiais do Anunciador em Massa, por categoria." stage="Etapa D — Mercado Livre"
    items={["Upload da planilha oficial baixada da sua conta", "Leitura de abas, cabeçalhos, validações e listas", "Origem, versão e categoria registradas",
      "Detecção de mudança de estrutura", "Mapeamentos salvos e reutilizáveis", "Preenchimento de cópias do arquivo oficial"]}
    blocker="Aguardando uma planilha oficial real para análise da estrutura interna." />;
}
