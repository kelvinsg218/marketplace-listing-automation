# Estado atual — 20/10/2026, v0.1.2-beta (aplicativo Windows instalável)

**Beta instalável para uso supervisionado por duas pessoas, cada uma com os próprios dados; não pronto para
distribuição comercial.** Testes: 256 aprovados, 0 falhos (inclui 9 de ponta a ponta no Edge). Banco: esquema v9.

| Área | Situação |
|---|---|
| Instalador | `dist\MLA-Setup-0.1.2-beta.exe` (a 0.1.1-beta fica preservada, mas aponta para um canal que não existe), por usuário, sem administrador. Testado nesta máquina: assistente de instalação, instalação silenciosa, abertura sem terminal, recusa com o app aberto, desinstalação mantendo dados. Não testado: máquina limpa |
| Atualizações | Testado de ponta a ponta pela interface (0.1.0-beta → 0.1.1-beta, canal local no formato do GitHub): dados idênticos, backup antes da migração 8 → 9. Pela internet: HTTPS/redirecionamento/SHA-256 verificados contra o GitHub real; canal = releases do showcase público; **falta publicar a release** |
| Mercado Livre (API oficial) | Implementado e testado contra simulação dos endpoints documentados: OAuth + PKCE, tokens DPAPI, renovação, importação de anúncios, sugestão de categoria e atributos (endpoints públicos reais consultados), validação sem publicar. **Não testado com conta real** (depende do aplicativo do dono). Publicação desligada |
| Catálogo, importação, empresas, exportação | Como na v0.2.0 interna (ver PROGRESSO_MVP.md e DEMO_COMERCIAL.md) |
| Shopee | Sem integração |

Documentos: [BUILD_E_DISTRIBUICAO.md](BUILD_E_DISTRIBUICAO.md), [GUIA_MERCADO_LIVRE.md](GUIA_MERCADO_LIVRE.md),
[ROTEIRO_TESTE_SEGUNDO_COMPUTADOR.md](ROTEIRO_TESTE_SEGUNDO_COMPUTADOR.md), [NEXT_STEPS.md](NEXT_STEPS.md).

## MLA Web 2.0 (01/11/2026, `apps/`, versão 2.0.0-alpha.0)

**Etapa B (fundação) implementada e testada; o desktop acima segue inalterado.** API: 53 testes aprovados + 1 pulado
(RLS, que exige PostgreSQL). Web: typecheck e build estático ok; fluxo E2E no Edge ok, sem rolagem horizontal em
390 px.

| Área | Situação |
|---|---|
| Autenticação, organizações, papéis, auditoria | Implementado e testado (SQLite) |
| Isolamento entre empresas | Aplicação: testado. RLS no PostgreSQL: escrito, **não executado** (sem PostgreSQL nesta máquina) |
| Catálogo | CRUD básico (sem variações, mídias nem compatibilidades), busca, pendências internas, painel com métricas reais |
| Importações, templates, anúncios em massa, lotes | Não iniciados (etapas C a E). Exportação ML **bloqueada**: docs oficiais com 403 e sem template real |
| Docker Compose | Escrito, **não executado** (Docker ausente) |
| E-mail de produção | Não implementado (dev grava em `apps/api/.data/outbox`) |

Documentos: [MLA_WEB_ROADMAP.md](MLA_WEB_ROADMAP.md), [MLA_WEB_ARCHITECTURE.md](MLA_WEB_ARCHITECTURE.md),
[MLA_MERCADOLIVRE_RESEARCH.md](MLA_MERCADOLIVRE_RESEARCH.md), [MLA_WEB_UX_DESIGN.md](MLA_WEB_UX_DESIGN.md),
[MLA_LEGACY_MIGRATION.md](MLA_LEGACY_MIGRATION.md).
