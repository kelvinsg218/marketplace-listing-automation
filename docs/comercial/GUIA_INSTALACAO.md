# Guia de instalação

## Requisitos mínimos
- Windows 10 ou 11, 64 bits.
- 4 GB de RAM (8 GB recomendados). O app usa cerca de 100 MB aberto; o cenário de 300 produtos usou no máximo
  81 MB no processamento.
- 1 GB livre para o programa (220 MB) e o pacote, mais o espaço das fotos do catálogo.
- Microsoft Edge (já vem no Windows). Conexão com a internet só para usar os marketplaces.

## Instalar
1. Receba `MLA-Setup-<versão>.exe` e `MLA-Setup-<versão>.exe.sha256`. Para conferir a integridade, no PowerShell:
   `Get-FileHash .\MLA-Setup-<versão>.exe -Algorithm SHA256` deve mostrar o mesmo código do `.sha256`.
2. Dê dois cliques no instalador. Não precisa ser administrador. Marque, se quiser, o atalho na área de trabalho e
   clique em **Instalar**. O MLA abre no fim.

Como o executável ainda não tem assinatura digital, o Windows pode mostrar "O Windows protegeu o computador".
Confira o código SHA-256 antes de prosseguir em **Mais informações → Executar assim mesmo**.

## Onde ficam as coisas
| O quê | Onde |
|---|---|
| Programa | `%LOCALAPPDATA%\Programs\MLA` |
| Dados da empresa principal | `%LOCALAPPDATA%\MLA` (banco, imagens, arquivos, backups, logs, navegadores das contas) |
| Dados das outras empresas | `%LOCALAPPDATA%\MLA\empresas\<nome>` |
| Lista de empresas | `%LOCALAPPDATA%\MLA\workspaces.json` |

## Atualizar
No MLA: **Atualizações → Verificar agora → Baixar e instalar**. O arquivo baixado é conferido pelo SHA-256, o MLA
fecha, a versão nova é instalada e o MLA abre de novo. Também dá para executar o instalador da versão nova por
cima. Só a pasta do programa é trocada (se algo falhar, a anterior é restaurada) e o MLA faz backup do banco antes
de atualizá-lo.

## Desinstalar
**Configurações → Aplicativos → Aplicativos instalados → MLA - Marketplace Listing Automation → Desinstalar.**
Os dados são mantidos. Para apagar também os dados de todas as empresas (irreversível):
`desinstalar.cmd -RemoverDados -ConfirmarRemocaoDeDados` (as duas opções são exigidas de propósito).

## Diagnóstico
- Autoteste: `%LOCALAPPDATA%\Programs\MLA\MLA.exe --self-test` grava o relatório em `logs\self-test.txt` da pasta
  de dados.
- Logs: pasta `logs` dentro da pasta de dados de cada empresa. Os logs não guardam senhas nem cookies, e os
  endereços aparecem sem os parâmetros (onde costumam ir códigos de acesso).

## O que foi testado
Nesta máquina de desenvolvimento (Windows 11), com o instalador real: instalação em modo silencioso, primeira
abertura sem terminal, abertura com 288 produtos fictícios, **atualização 0.1.0-beta → 0.1.1-beta clicando na
própria interface** (janela de progresso do instalador, dados idênticos, backup antes da migração do banco 8 → 9),
desinstalação mantendo os dados, e os dados reais da máquina conferidos sem alteração. Ainda não verificados com
o `MLA-Setup.exe`: a janela de instalação normal (assistente) e a recusa de instalar com o MLA aberto.
**Ainda não testado em um computador limpo**: use o [roteiro do segundo computador](../ROTEIRO_TESTE_SEGUNDO_COMPUTADOR.md).
