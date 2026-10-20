# Limitações conhecidas (versão 0.2.0)

## Publicação
- **Não publica diretamente no Mercado Livre nem na Shopee.** A automação completa (preencher, revisar, publicar)
  funciona hoje só no marketplace simulado que vem com o app. Para os marketplaces reais é preciso, com
  autorização do dono da conta, mapear o formulário real ou usar a API oficial (Mercado Livre exige aplicativo
  registrado e autorização OAuth; Shopee exige aprovação como parceiro).
- **A planilha exportada é intermediária**, não o modelo oficial de envio em massa. O Mercado Livre gera o modelo
  por categoria dentro da conta do vendedor e pede fotos por link (Gestor de fotos); a Shopee usa modelos da
  Central do Vendedor. Copiar para o modelo oficial é etapa supervisionada.
- Categorias e atributos obrigatórios de cada categoria do marketplace não são preenchidos automaticamente; o MLA
  não adivinha esses valores.

## Catálogo e importação
- Fotos nomeadas pelo SKU da variação não são ligadas à variação automaticamente; a associação por variação é
  manual.
- Uma foto corrompida aparece como "mídia pendente", sem dizer que o arquivo existe mas está danificado (o motivo
  aparece na revisão da importação).
- PDF: só PDFs com texto (sem OCR para documentos escaneados); texto quebrado em várias linhas dentro de uma célula
  não é juntado.
- Imagens embutidas dentro de células do Excel não são extraídas; links de imagem são registrados como pendentes, não
  baixados.
- Um anúncio por produto em cada conta (não há, por exemplo, "clássico" e "premium" do mesmo produto na mesma conta).
- Sem telas ainda para regras de categoria e para associar imagem a uma variação.

## Instalação e licença
- O executável **não tem assinatura digital**: o Windows pode exibir o aviso do SmartScreen.
- Instalação testada apenas na máquina de desenvolvimento, não em um computador limpo.
- Atualização é manual (instalar a versão nova por cima); não há atualização automática.
- Licença: período de avaliação exibido, mas nada é bloqueado; o período de avaliação é contado por empresa.
- Apenas Windows 10/11 64 bits, com Microsoft Edge.

## Operação
- Um item de automação por vez.
- Exportações grandes rodam sem barra de progresso (no cenário de 266 anúncios e 469 fotos: menos de 2 segundos).
- Não há inteligência de mercado nem sugestões de IA ativas (só a estrutura).
