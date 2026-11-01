import { ComingSoon } from "@/components/coming-soon";

export default function Page() {
  return <ComingSoon title="Configurações" description="Preferências da organização e da conta." stage="Etapa F — Consolidação"
    items={["Dados da organização", "Alteração de senha e sessões ativas", "Convites por e-mail", "Valores padrão de anúncios"]} />;
}
