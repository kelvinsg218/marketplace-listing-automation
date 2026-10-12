# MLA — Marketplace Listing Automation

Aplicativo desktop para Windows que centraliza o cadastro de produtos e prepara anúncios em marketplaces no navegador,
parando para a sua revisão antes de qualquer publicação.

## O que já funciona (v0.1.0)
- Cadastro completo: dados básicos, descrição, imagens (arrastar e soltar, ordem, capa), preço, estoque, variações,
  logística e configurações por marketplace, com checagem ao vivo do que falta.
- Busca, filtros, ordenação, duplicação, exclusão, seleção múltipla, importação e exportação CSV/JSON.
- Grupos de produtos com ordem própria, marketplaces de destino, validação e execução em lote.
- Fila de automação persistente: um item por vez, pausa, retomada, cancelamento, recuperação após fechar o app,
  prevenção de anúncios duplicados, capturas de tela e registro de cada etapa.
- Revisão humana obrigatória: o formulário é preenchido, conferido contra o cadastro e só é publicado com a sua aprovação.
- Marketplace simulado embutido para testar o fluxo inteiro sem publicar nada de verdade.
- Histórico com filtros, detalhes, reexecução segura e exportação.

## Ainda não disponível
- Preenchimento dos formulários reais do **Mercado Livre** e da **Shopee** (fases 4 e 6 — dependem de uma conta
  autorizada para inspecionar os formulários). Já é possível entrar nas contas pelo navegador dedicado.
- Instalador, cobrança e servidor de licenças.

## Começar
- Usuário: veja [docs/USER_GUIDE.md](docs/USER_GUIDE.md) e [docs/INSTALLATION.md](docs/INSTALLATION.md).
- Desenvolvimento: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md), [docs/TESTING.md](docs/TESTING.md),
  [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- Estado do projeto: [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md) e [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md).
