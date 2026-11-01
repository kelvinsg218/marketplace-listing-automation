# MLA — Marketplace Listing Automation (Web 2.0)

Plataforma web multiempresa para preparar anúncios em massa no Mercado Livre a partir de um catálogo de produtos.

O cliente organiza o catálogo e escolhe produtos, conta e categoria. O MLA preenche uma **cópia da planilha oficial**
que a própria conta baixou no Anunciador em Massa. Antes do envio, ele valida os dados contra as regras do arquivo e
da documentação oficial. Quando o Mercado Livre recusa algo, a correção é feita na web, por regras ("só neste lote"
ou permanentes). O Excel vira formato de troca de arquivos: o cliente não precisa preenchê-lo à mão.

> **Estado:** 2.0.0-alpha. Funciona de ponta a ponta em desenvolvimento, mas a planilha gerada **ainda não passou por
> um envio real** ao Mercado Livre. Nada é publicado automaticamente.

## Funcionalidades

| Área | O que faz |
|---|---|
| Contas e organizações | Cadastro, login, sessões seguras, redefinição de senha, papéis (proprietário, administrador, editor, leitor), auditoria |
| Isolamento entre empresas | Rotas por organização, filtros em todas as consultas e Row-Level Security no PostgreSQL |
| Catálogo mestre | Produtos, variações, preços, estoque, GTIN com dígito verificador, atributos, Código de catálogo ML, painel de qualidade |
| Central de Fotos | Arquivos verificados pelo conteúdo, URLs oficiais do Gestor de fotos, ordem, pendências |
| Templates oficiais | Registro do XLSX baixado da conta (original imutável + SHA-256), inspeção da estrutura (abas, obrigatórios, listas, limites, fórmulas, prazo), comparação entre versões |
| Mapeamento | Campos do catálogo → colunas oficiais, com listas e padrões do próprio arquivo e reaproveitamento por nome de coluna |
| Validação | Regras internas, da documentação (com página citada) e do template; hipóteses nunca bloqueiam |
| Writer oficial | Preenche só as células de dados de uma cópia; abas, fórmulas, validações e imagens ficam idênticas; verificação de integridade a cada exportação |
| Anúncios em massa | Assistente de 12 etapas, lotes rastreáveis; envio e resultado só mudam com confirmação do usuário |
| Regras adaptativas | Por lote, categoria, template, conta ou organização; simulação antes/depois, aprovação, versões e reversão |
| Assistente de Correção | Lê o "Resumo de erros" colado ou um pedido em texto e propõe uma regra (interpretação local, sem IA externa) |
| Importação (base) | Leitores CSV/XLSX/JSON/XML/PDF, ZIP seguro, reconhecimento de colunas e parsing de valores. A tela da Central de Importações ainda não existe |

## Arquitetura

```
apps/web  (Next.js 15, React 19, Tailwind 4; exportação estática)
   │  mesma origem, cookie HttpOnly
apps/api  (FastAPI, Pydantic 2, SQLAlchemy 2, Alembic)
   ├── domain/     regras puras: catálogo, inspetor de templates, writer, sheet builder, regras adaptativas
   ├── importing/  leitores e parsing de arquivos de catálogo
   ├── routers/    auth, organizações, catálogo, fotos, templates, lotes, regras
   └── storage     arquivos por organização (orgs/<id>/…), download só por rota autorizada
PostgreSQL 17/18 (RLS)   ·   infra/postgres/init.sql   ·   docker-compose.yml (ainda não executado)
```

Detalhes: [docs/MLA_WEB_ARCHITECTURE.md](docs/MLA_WEB_ARCHITECTURE.md) e decisões em [docs/DECISIONS.md](docs/DECISIONS.md).

## Executar localmente (Windows, PowerShell)

Pré-requisitos: Python 3.13 e Node 22+. O PostgreSQL é opcional em desenvolvimento: sem ele, a API usa SQLite em
`apps/api/.data/`.

```powershell
# API (porta 8000)
cd apps\api
py -3.13 -m venv .venv; .venv\Scripts\python -m pip install -e ".[dev]"
copy .env.example .env
.venv\Scripts\python -m alembic upgrade head
$env:PYTHONPATH="src"; .venv\Scripts\python -m uvicorn mla_api.asgi:app --reload --reload-dir src

# Web (porta 3000, outro terminal)
cd apps\web
npm install; npm run dev
```

Abra http://localhost:3000 e crie uma conta. A documentação da API fica em http://localhost:8000/api/docs, só em
desenvolvimento.

### Banco de dados
- **Desenvolvimento:** SQLite automático, ou PostgreSQL definindo `MLA_DATABASE_URL` no `apps/api/.env`.
- **PostgreSQL local:** `psql -U postgres -h localhost -f infra/postgres/init.sql` cria o papel `mla`, que **não** é
  superusuário (superusuários ignoram RLS), e os bancos `mla` e `mla_test`.
- **Produção:** a API recusa SQLite e cookie sem `Secure`.

## Testes

```powershell
cd apps\api; .venv\Scripts\python -m pytest                       # API
$env:MLA_TEST_DATABASE_URL="postgresql+psycopg://mla:mla-dev-password@localhost:5432/mla_test"
.venv\Scripts\python -m pytest -m postgres                          # RLS real
cd ..\web; npm run typecheck; npm run build
```

Os fluxos no navegador (Playwright + Edge) ficam em `apps/web/e2e/`, com dependências em `requirements.txt`. Os
testes usam **somente dados fictícios** e um XLSX sintético que reproduz o layout oficial. Templates reais de
vendedores nunca entram no repositório.

## Limitações conhecidas
- A planilha gerada ainda não foi aceita num envio real; também não se sabe se o Mercado Livre recalcula as fórmulas
  do arquivo.
- O arquivo de retorno com "Resumo de erros" ainda não é importado automaticamente; hoje o conteúdo é colado no
  Assistente.
- A publicação pela API oficial (OAuth) está só planejada; o envio é manual, no site do Mercado Livre.
- Faltam a tela da Central de Importações, as compatibilidades veiculares e a fila de processamento.
- O RLS não foi executado em PostgreSQL real, o Docker Compose não foi executado e o Firefox não foi testado.

## Próximas entregas
1. Envio controlado e autorizado para confirmar a compatibilidade.
2. Importador do arquivo de retorno.
3. Adaptador da API oficial do Mercado Livre (OAuth + confirmação antes de publicar).
4. Central de Importações com processamento em segundo plano.

Roteiro completo: [docs/MLA_WEB_ROADMAP.md](docs/MLA_WEB_ROADMAP.md).
