# Estado atual — 20/10/2026, v0.1.1-beta (aplicativo Windows instalável)

**Beta instalável para uso supervisionado por duas pessoas, cada uma com os próprios dados; não pronto para
distribuição comercial.** Testes: 256 aprovados, 0 falhos (inclui 9 de ponta a ponta no Edge). Banco: esquema v9.

| Área | Situação |
|---|---|
| Instalador | `dist\MLA-Setup-0.1.1-beta.exe` (129 MB), por usuário, sem administrador. Testado nesta máquina: instalação silenciosa, abertura sem terminal, desinstalação mantendo dados. Não testado: máquina limpa, assistente normal |
| Atualizações | Testado de ponta a ponta pela interface (0.1.0-beta → 0.1.1-beta, canal local no formato do GitHub): dados idênticos, backup antes da migração 8 → 9. Pela internet: HTTPS/redirecionamento/SHA-256 verificados contra o GitHub real; **falta o repositório público de releases** |
| Mercado Livre (API oficial) | Implementado e testado contra simulação dos endpoints documentados: OAuth + PKCE, tokens DPAPI, renovação, importação de anúncios, sugestão de categoria e atributos (endpoints públicos reais consultados), validação sem publicar. **Não testado com conta real** (depende do aplicativo do dono). Publicação desligada |
| Catálogo, importação, empresas, exportação | Como na v0.2.0 interna (ver PROGRESSO_MVP.md e DEMO_COMERCIAL.md) |
| Shopee | Sem integração |

Documentos: [BUILD_E_DISTRIBUICAO.md](BUILD_E_DISTRIBUICAO.md), [GUIA_MERCADO_LIVRE.md](GUIA_MERCADO_LIVRE.md),
[ROTEIRO_TESTE_SEGUNDO_COMPUTADOR.md](ROTEIRO_TESTE_SEGUNDO_COMPUTADOR.md), [NEXT_STEPS.md](NEXT_STEPS.md).
