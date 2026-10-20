# Conectar uma conta do Mercado Livre (API oficial)

O MLA usa a API oficial do Mercado Livre. **Você nunca informa a sua senha ao MLA**: a autorização é feita no
site do Mercado Livre, e o MLA guarda apenas códigos de acesso, criptografados para o seu usuário do Windows.
Cada pessoa conecta a própria conta no próprio computador.

## 1. Criar o seu aplicativo no Mercado Livre (uma vez, gratuito)
1. Entre com a sua conta em <https://developers.mercadolivre.com.br/devcenter> → **Criar aplicação**.
2. Preencha nome e descrição (ex.: "MLA – uso próprio").
3. **URI de redirecionamento:** um endereço HTTPS fixo, sem parâmetros. O próprio exemplo da documentação
   oficial usa `https://localhost.com/redirect`; qualquer endereço HTTPS que você controle serve. Anote-o exatamente.
4. Ative **PKCE** e marque as permissões de leitura e escrita de anúncios (o MLA só lê e valida; nada é publicado).
5. Salve e copie o **App ID** e a **Secret Key**.

A Secret Key é sua: não envie por chat nem e-mail. Se o seu amigo for usar o MLA, ele cria o próprio aplicativo.

## 2. Conectar no MLA
1. Marketplaces → conta do Mercado Livre → **API oficial**.
2. Cole App ID, Secret Key e a URI **idêntica** à cadastrada.
3. **Abrir autorização no navegador** → entre na sua conta → **Permitir**.
4. O navegador vai para a URI cadastrada (a página pode até dar erro, é normal) com `code=…` no endereço. Copie o
   **endereço inteiro** da barra do navegador e cole no MLA → **Concluir conexão**.
5. A conta passa a mostrar "API oficial: conectada como SEU_APELIDO". O acesso é renovado sozinho por até 6 meses
   sem uso; depois disso, ou se você revogar o acesso, conecte de novo.

Para desconectar: Marketplaces → Mais → **Desconectar API oficial** (apaga os códigos deste computador). Para
revogar no Mercado Livre: Minha conta → Segurança → Aplicativos conectados.

## 3. Importar os anúncios que você já tem
Marketplaces → Mais → **Importar anúncios desta conta para o catálogo**. O MLA lê até 1.000 anúncios (título,
preço, estoque, marca, modelo, GTIN, SKU, descrição, fotos e variações) e abre a revisão da Central de
Importações: nada é gravado antes da sua confirmação e nada muda no Mercado Livre.

## 4. Preparar e testar anúncios
1. Catálogo → selecione produtos → **Preparar anúncios** → Mercado Livre e a conta.
2. Em Anúncios, abra o anúncio. No bloco **Mercado Livre (API oficial)**:
   - **Sugerir categoria:** o preditor oficial sugere categorias para o título; escolha uma.
   - **Atributos:** lista os atributos obrigatórios e condicionais da categoria e cria as linhas que faltam na
     tabela para você preencher (o MLA não inventa valores).
   - **Validar no Mercado Livre (sem publicar):** envia o anúncio ao validador oficial (`/items/validate`). A
     resposta diz se o Mercado Livre aceitaria o anúncio e lista os problemas. **Nada é publicado.**
3. Corrija o que for apontado e **Aprovar**.

O que a validação ainda não envia: as fotos (o validador exige links públicos; elas serão enviadas na publicação
autorizada) e as variações. O MLA avisa isso no resultado.

## 5. Publicação real
Está **desligada** nesta versão. O Mercado Livre não tem ambiente de testes: qualquer anúncio criado fica público.
A primeira publicação real será feita só com a sua autorização explícita, em um teste supervisionado com um
produto escolhido por você.
