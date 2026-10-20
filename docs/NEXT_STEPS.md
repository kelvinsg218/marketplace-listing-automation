# Próximos passos

## Ações humanas necessárias (bloqueiam o próximo nível)
1. **Testar o pacote num computador limpo** (sem Python): `instalar.cmd -Verificar`, abrir, importar uma base
   fictícia, exportar, desinstalar. Registrar o resultado.
2. **Autorizar (ou não) o push** dos commits locais desta missão para o repositório e a atualização da vitrine.
3. **Primeiro piloto supervisionado** com uma base real de cliente, seguindo
   [comercial/CHECKLIST_IMPLANTACAO.md](comercial/CHECKLIST_IMPLANTACAO.md), medindo também o processo manual.
4. **Mercado Livre:** decidir entre (a) registrar um aplicativo no portal de desenvolvedores e usar a API oficial
   com OAuth do vendedor ou (b) inspeção autorizada, só leitura, do formulário real. Nenhuma das duas foi feita.
5. **Certificado de assinatura de código** (custo) para eliminar o aviso do SmartScreen antes de vender.

## Depois (desenvolvimento, por prioridade)
- Associar fotos às variações (modelo de dados e importação já suportam `ProductImage.variant`).
- Distinguir "arquivo corrompido" de "não encontrado" nas mídias pendentes.
- Preenchimento do modelo oficial de envio em massa, a partir de um modelo real baixado pelo cliente.
- Telas de regras por categoria e de consentimento de IA.
- Barra de progresso na exportação grande; atualização automática; licenças assinadas.
- Adaptador do Mercado Livre (fase 4) só depois do passo 4 acima.
