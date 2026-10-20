# Próximos passos

## Ações humanas necessárias
1. **Autorizar o push** dos commits locais para `marketplace-listing-automation` (privado).
2. **Canal de atualizações:** aprovar a criação de um repositório **público só com instaladores**
   (`kelvinsg218/mla-releases`, padrão do app) e a publicação da release `v0.1.1-beta` com
   `MLA-Setup-0.1.1-beta.exe` + `.sha256`. Sem isso, o botão Atualizações responde "canal não encontrado".
3. **Segundo computador:** enviar o instalador ao seu amigo com o
   [roteiro](ROTEIRO_TESTE_SEGUNDO_COMPUTADOR.md) e receber a tabela preenchida + logs.
4. **Mercado Livre:** criar o seu aplicativo no portal de desenvolvedores e conectar a conta
   ([guia](GUIA_MERCADO_LIVRE.md)); rodar "Validar no Mercado Livre (sem publicar)" em 2 ou 3 anúncios.
5. **Publicação real:** decidir se e quando autoriza um teste supervisionado de publicação com um produto escolhido.
6. **Assinatura de código** (certificado pago) para eliminar o aviso do SmartScreen antes de distribuir mais.

## Desenvolvimento, por prioridade
- Publicação supervisionada pela API (POST /items + upload de fotos via /pictures) atrás de confirmação explícita,
  depois do passo 5.
- Variações e fotos na validação do Mercado Livre.
- Testar com o `MLA-Setup.exe`: janela de instalação normal e recusa com o app aberto (só o modo silencioso e a
  atualização foram testados).
- Associar fotos às variações; distinguir arquivo corrompido de não encontrado nas mídias pendentes.
- Desinstalador sem console (hoje é um script PowerShell).
