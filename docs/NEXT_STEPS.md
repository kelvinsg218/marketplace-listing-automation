# Próximos passos

## Ações humanas necessárias
1. **Publicar a release `v0.1.2-beta` no showcase** (público) com `MLA-Setup-0.1.2-beta.exe` + `.sha256`, pelo
   site do GitHub ([passo a passo](BUILD_E_DISTRIBUICAO.md#publicar-uma-versão)). Sem isso, o botão Atualizações
   responde "Nenhuma versão publicada".
2. **Segundo computador:** enviar o instalador ao seu amigo com o
   [roteiro](ROTEIRO_TESTE_SEGUNDO_COMPUTADOR.md) e receber a tabela preenchida + logs.
3. **Mercado Livre:** criar o seu aplicativo no portal de desenvolvedores e conectar a conta
   ([guia](GUIA_MERCADO_LIVRE.md)); rodar "Validar no Mercado Livre (sem publicar)" em 2 ou 3 anúncios.
4. **Publicação real:** decidir se e quando autoriza um teste supervisionado de publicação com um produto escolhido.
5. **Assinatura de código** (certificado pago) para eliminar o aviso do SmartScreen antes de distribuir mais.

## Desenvolvimento, por prioridade
- Publicação supervisionada pela API (POST /items + upload de fotos via /pictures) atrás de confirmação explícita,
  depois do passo 4.
- Variações e fotos na validação do Mercado Livre.
- Associar fotos às variações; distinguir arquivo corrompido de não encontrado nas mídias pendentes.
- Desinstalador sem console (hoje é um script PowerShell).
