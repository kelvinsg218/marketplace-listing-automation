# Guia de configuração para validação real — MLA Web 2.0

Três configurações que só você pode fazer: PostgreSQL (para validar o RLS), aplicativo do Mercado Livre (OAuth) e
chave da OpenAI (Estúdio de IA). Nenhuma delas publica anúncios. Senhas, segredos e chaves ficam **só** no seu
computador (`apps/api/.env`, ignorado pelo Git); **não cole nenhum deles no chat**.

---

## 1. PostgreSQL e RLS

Estado verificado em 02/11/2026: PostgreSQL 18.6, serviço `postgresql-x64-18` rodando, porta 5432, toda conexão local
exige senha (`scram-sha-256`). Não foi possível saber se o papel `mla` já existe sem a senha do `postgres`.

**1.1 Criar o papel e os bancos** (abra um PowerShell **seu**, fora do Claude; o `psql` vai pedir a senha do
superusuário `postgres`, definida na instalação do PostgreSQL):

```powershell
cd C:\Users\garci\projetos\MLA
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -f infra\postgres\init.sql
```

O script só cria o que falta (papel `mla` sem superusuário, bancos `mla` e `mla_test`) e nunca altera o que já existe.
No fim ele mostra duas tabelinhas: o papel `mla` deve aparecer com `rolsuper = f` e `rolbypassrls = f`, e os dois
bancos com dono `mla`.

> Se o papel `mla` **já existia** com outra senha, o script não a troca. Nesse caso use a senha que você definiu
> antes no passo 1.2, ou troque-a conscientemente no `psql` (`ALTER ROLE mla PASSWORD '...';`).

**1.2 Avisar o Claude.** Basta dizer "PostgreSQL pronto". O teste usa o banco **`mla_test`** (ele apaga e recria o
schema desse banco a cada execução e se recusa a rodar em bancos cujo nome não termina em `_test`):

```powershell
cd C:\Users\garci\projetos\MLA\apps\api
$env:MLA_TEST_DATABASE_URL = "postgresql+psycopg://mla:mla-dev-password@localhost:5432/mla_test"
.venv\Scripts\python -m pytest -m postgres
```

O banco `mla` (desenvolvimento) não é tocado pelos testes. Usar PostgreSQL também no dia a dia é opcional
(`MLA_DATABASE_URL` no `.env` + `alembic upgrade head`); os dados atuais em SQLite não são migrados automaticamente.

---

## 2. Aplicativo do Mercado Livre (OAuth oficial)

O MLA usa o fluxo oficial de autorização (código + PKCE). O login acontece na página do Mercado Livre; o MLA nunca vê
a senha. A conexão **não** envia a planilha XLSX e **não** publica anúncios.

**2.1 Endereço HTTPS público.** O Mercado Livre devolve o navegador para uma URL de retorno HTTPS que precisa ser
**idêntica** à cadastrada no aplicativo. No computador local isso exige um túnel HTTPS. Para que o cookie de sessão e
o retorno fiquem no mesmo endereço, sirva o site pela própria API (um único endereço) e use o MLA **pelo endereço do
túnel** durante o teste:

```powershell
# 1) gerar o site estático (pare o "npm run dev" antes)
cd C:\Users\garci\projetos\MLA\apps\web; npm run build
# 2) túnel HTTPS para a API (exemplo com Cloudflare Tunnel; ngrok também serve)
cloudflared tunnel --url http://localhost:8000
```

Anote o endereço `https://...` que o túnel mostrar. Túneis rápidos mudam de endereço a cada execução; se mudar,
atualize a URL de retorno no aplicativo e no `.env`. (Para uso contínuo, um domínio fixo é o caminho certo.)

**2.2 Criar o aplicativo** no portal de desenvolvedores do Mercado Livre (developers.mercadolivre.com.br), entrando
com a conta de vendedor que será conectada:
- Nome e descrição: livres (ex.: "MLA – teste interno").
- **URL de retorno (redirect URI):** `https://SEU-ENDERECO/api/integrations/mercadolivre/callback`
- **Permissões/escopos:** acesso offline (`offline_access`, necessário para renovar o token sem novo login) e
  leitura. Escrita só será necessária quando a publicação pela API for implementada e autorizada.
- Ao salvar, o portal mostra o **ID do aplicativo** (client id) e a **chave secreta** (client secret).

**2.3 Preencher `apps/api/.env`:**

```ini
MLA_PUBLIC_URL=https://SEU-ENDERECO
MLA_COOKIE_SECURE=true
MLA_WEB_DIST_DIR=../web/out
MLA_ML_CLIENT_ID=<ID do aplicativo>
MLA_ML_CLIENT_SECRET=<chave secreta>
MLA_ML_REDIRECT_URI=https://SEU-ENDERECO/api/integrations/mercadolivre/callback
MLA_TOKEN_ENCRYPTION_KEY=<gerada no passo abaixo>
```

Gere a chave de cifragem dos tokens (guarde-a: sem ela os tokens salvos não podem ser lidos, e a conta precisa ser
reconectada):

```powershell
cd C:\Users\garci\projetos\MLA\apps\api
.venv\Scripts\python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"
```

**2.4 Aplicar e testar:** migre (`.venv\Scripts\python -m alembic upgrade head`), reinicie a API, abra
`https://SEU-ENDERECO/marketplaces/`, entre no MLA, clique **Conectar** na conta de vendedor e autorize na página do
Mercado Livre. Ao voltar deve aparecer "Conta conectada pelo OAuth oficial" com o apelido da conta. Depois use
**Verificar**. Se o ID de vendedor cadastrado for diferente da conta que autorizou, o MLA recusa e não salva nada.

Ao terminar o teste, volte o `.env` para `MLA_PUBLIC_URL=http://localhost:3000` e `MLA_COOKIE_SECURE=false` se for
continuar com `npm run dev`. Se a chave secreta vazar, gere outra no portal.

---

## 3. Chave da OpenAI e Estúdio de IA (orçamento de US$ 5)

Nenhuma chamada paga acontece enquanto **as duas** condições não estiverem presentes: chave configurada **e**
`MLA_IMAGE_AI_ENABLED=true`. Além disso, cada pedido exige marcar o consentimento de envio da imagem.

**3.1 Chave:** crie uma chave de API no painel da OpenAI (platform.openai.com, seção de API keys), de preferência
num projeto separado para o MLA. Se o painel oferecer limite de gasto por projeto, defina também US$ 5 ali: é uma
segunda trava, independente da do MLA.

**3.2 Configurar ainda desligado** (`apps/api/.env`):

```ini
MLA_IMAGE_AI_PROVIDER=openai
MLA_OPENAI_API_KEY=<sua chave>
MLA_IMAGE_AI_ENABLED=false
MLA_IMAGE_AI_BUDGET_USD=5
MLA_OPENAI_IMAGE_QUALITY=low
```

Reinicie a API. Na Central de Imagens o Estúdio deve dizer "Provedor OpenAI configurado, mas desativado". Isso
confirma que a chave foi lida sem nenhuma chamada.

**3.3 Ativar (decisão sua):** troque para `MLA_IMAGE_AI_ENABLED=true` e reinicie a API. O Estúdio passa a mostrar o
modelo (`gpt-image-2`), a qualidade e o orçamento usado. Recomendação para o primeiro teste: qualidade `low`, um
produto fictício, uma imagem. O custo real de cada pedido (calculado do `usage` da resposta) aparece no histórico de
versões.

Como o orçamento funciona: antes de cada pedido o MLA reserva US$ 0,25 (`MLA_IMAGE_AI_RESERVE_USD`); ao terminar,
troca a reserva pelo custo real. Se a OpenAI não informar o custo, a reserva inteira é contada. Quando um novo pedido
passaria de US$ 5, ele é recusado antes de chamar a OpenAI. O contador é da instalação (soma todas as organizações).
Para desligar a qualquer momento: `MLA_IMAGE_AI_ENABLED=false` e reiniciar a API.

---

## Onde ficam as coisas

| Item | Onde | Vai para o Git? |
|---|---|---|
| Senha do `postgres` | só no seu terminal, na hora | Não |
| Client secret do ML, chave OpenAI, chave de cifragem | `apps/api/.env` | Não (ignorado) |
| Tokens do Mercado Livre | banco, cifrados (AES-256-GCM) | Não |
| Lista de variáveis (sem valores) | `apps/api/.env.example` | Sim |
