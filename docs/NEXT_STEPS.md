# Próximos passos — MLA Web 2.0

Ações humanas:
1. **Aceite real (o mais importante):** autorizar um envio controlado de 1 produto fictício ou de teste, gerado pelo
   MLA a partir de uma planilha **nova** da sua conta (a atual vence em 01/12), e trazer o resultado (e-mail e, se
   houver, o arquivo de erros). É isso que confirma a compatibilidade e o comportamento das fórmulas.
2. **Arquivo de retorno com "Resumo de erros"**, para o importador automático.
3. **RLS:** rodar uma vez `& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -f infra\postgres\init.sql`
   (só cria o papel `mla` e os bancos `mla`/`mla_test`).

Desenvolvimento: importador do arquivo de retorno; adaptador da API oficial (OAuth web + `/items` com confirmação);
Central de Importações (etapa C) com fila e worker; IA externa opcional com consentimento para interpretar pedidos; escolher um provedor real para o Estúdio de IA
(D-034) e definir limites de custo.
