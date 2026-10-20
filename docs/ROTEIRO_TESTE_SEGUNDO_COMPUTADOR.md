# Roteiro de instalação e teste no segundo computador

Para quem recebe o MLA (versão beta). Leva cerca de 20 minutos. Anote o resultado de cada passo na tabela do fim
e envie de volta junto com a pasta `%LOCALAPPDATA%\MLA\logs` compactada (os logs não têm senhas).

## Antes de começar
- Windows 10 ou 11 (64 bits), com Microsoft Edge.
- Receba **dois arquivos**: `MLA-Setup-0.1.1-beta.exe` e `MLA-Setup-0.1.1-beta.exe.sha256`.
- Confira o arquivo no PowerShell (Iniciar → digite PowerShell):
  ```
  Get-FileHash "$env:USERPROFILE\Downloads\MLA-Setup-0.1.1-beta.exe" -Algorithm SHA256
  ```
  O código mostrado deve ser igual ao que está dentro do `.sha256`. Se for diferente, **não instale**.

## Passos
1. **Instalar:** dê dois cliques no `MLA-Setup-0.1.1-beta.exe`. Se aparecer "O Windows protegeu o computador",
   clique em **Mais informações → Executar assim mesmo** (o instalador ainda não tem assinatura digital).
   Marque "Criar atalho na área de trabalho" se quiser e clique em **Instalar**. Não precisa ser administrador.
2. **Primeira abertura:** o MLA abre sozinho no fim. Anote se abriu e quanto tempo levou.
3. **Sua empresa:** clique no nome "Empresa principal" (canto superior esquerdo) → **Renomear empresa atual…** →
   seu nome ou da sua loja.
4. **Produto manual:** Catálogo → **Novo produto** → preencha nome, SKU, preço (ex.: 49,90), estoque e uma foto →
   **Salvar produto**.
5. **Importação:** Importações → **Nova importação** → escolha uma planilha sua (CSV ou Excel) com uma coluna de
   código (SKU). Siga Prévia → Mapeamento → Revisão → **Confirmar importação**. Anote quantas linhas entraram e
   quantas foram recusadas (e os motivos).
6. **Fotos:** Importações → **Associar imagens de uma pasta** → pasta com fotos nomeadas pelo SKU.
7. **Fechar e abrir de novo:** feche o MLA e abra pelo menu Iniciar. Os produtos devem continuar lá.
8. **Conta do Mercado Livre:** siga o [guia de conexão](GUIA_MERCADO_LIVRE.md): crie o seu aplicativo gratuito
   no portal de desenvolvedores do Mercado Livre, depois Marketplaces → conta do Mercado Livre → **API oficial**.
   Anote se apareceu "API oficial: conectada como …". O MLA nunca pede a sua senha. Opcional: Mais → **Importar
   anúncios desta conta para o catálogo** (só lê; nada muda no Mercado Livre).
9. **Anúncios:** Catálogo → selecione produtos prontos → **Preparar anúncios** → Mercado Livre e a sua conta.
   Em Anúncios, abra um anúncio: **Sugerir categoria**, **Atributos** e **Validar no Mercado Livre (sem
   publicar)**. Anote a resposta do validador. Depois **Aprovar**, **Exportar planilha** e abra o Excel gerado.
10. **Automação de teste:** Marketplaces → conta do **Marketplace simulado** → prepare e aprove um anúncio nela →
    **Enviar aprovados para a fila** → em Automações, revise e clique em **Aprovar e publicar**. Nada vai para o
    Mercado Livre: é o marketplace de treino que vem com o app.
11. **Atualizações:** menu **Atualizações** → **Verificar agora**. Anote a mensagem.
12. **Desinstalar (opcional):** Configurações do Windows → Aplicativos instalados → MLA → Desinstalar. Os seus
    dados ficam guardados em `%LOCALAPPDATA%\MLA`.

## Limitações desta beta
- O MLA **não publica anúncios no Mercado Livre** ainda: ele conecta pela API oficial, importa, prepara, valida
  sem publicar e exporta. A publicação será liberada só com autorização, em teste supervisionado.
- "Testar conexão" (navegador) do Mercado Livre não confirma a sessão; use a API oficial.
- Sem assinatura digital (aviso do SmartScreen).

## Resultado
| Passo | Funcionou? (sim / não / em parte) | Observação ou mensagem de erro |
|---|---|---|
| 1 Instalar | | |
| 2 Primeira abertura (tempo) | | |
| 3 Empresa | | |
| 4 Produto manual | | |
| 5 Importação (aceitas / recusadas) | | |
| 6 Fotos | | |
| 7 Reabrir e dados mantidos | | |
| 8 Conta Mercado Livre (API oficial) | | |
| 9 Anúncios, validação e planilha | | |
| 10 Automação simulada | | |
| 11 Atualizações | | |
| 12 Desinstalar | | |

Windows (10/11), memória RAM, antivírus usado: ________
