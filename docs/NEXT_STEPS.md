# Próximos passos — MLA Web 2.0

Ações humanas:
1. **Aceite real (o mais importante):** autorizar um envio controlado de 1 produto fictício ou de teste, gerado pelo
   MLA a partir de uma planilha **nova** da sua conta (a atual vence em 01/12), e trazer o resultado (e-mail e, se
   houver, o arquivo de erros). É isso que confirma a compatibilidade e o comportamento das fórmulas.
2. **Arquivo de retorno com "Resumo de erros"**, para o importador automático.
3. **RLS:** rodar uma vez `& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -f infra\postgres\init.sql`
   (pede a senha do `postgres`; só cria o que falta — papel `mla`, bancos `mla`/`mla_test` — e nunca altera o que existe).
   Depois, em `apps/api`: `$env:MLA_TEST_DATABASE_URL="postgresql+psycopg://mla:mla-dev-password@localhost:5432/mla_test"`
   e `.venv\Scripts\python -m pytest -m postgres`.
4. **OpenAI:** colocar `MLA_IMAGE_AI_PROVIDER=openai` e `MLA_OPENAI_API_KEY` em `apps/api/.env`; só com
   `MLA_IMAGE_AI_ENABLED=true` alguma chamada paga acontece (orçamento interno US$ 5).
5. **Mercado Livre:** criar o aplicativo no portal de desenvolvedores (redirect URI https idêntica, `offline_access`)
   e preencher `MLA_ML_CLIENT_ID`, `MLA_ML_CLIENT_SECRET`, `MLA_ML_REDIRECT_URI`, `MLA_TOKEN_ENCRYPTION_KEY`.

Desenvolvimento: importador do arquivo de retorno; publicação pela API oficial (`/items`, só com confirmação explícita; OAuth pronto);
Central de Importações (etapa C) com fila e worker; IA externa opcional com consentimento para interpretar pedidos; escolher um provedor real para o Estúdio de IA
(D-034) e definir limites de custo.
