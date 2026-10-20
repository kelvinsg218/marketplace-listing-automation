# Guia de instalação

## Requisitos mínimos
- Windows 10 ou 11, 64 bits.
- 4 GB de RAM (8 GB recomendados). O app usa cerca de 100 MB aberto; o cenário de 300 produtos usou no máximo
  81 MB no processamento.
- 1 GB livre para o programa (220 MB) e o pacote, mais o espaço das fotos do catálogo.
- Microsoft Edge (já vem no Windows). Conexão com a internet só para usar os marketplaces.

## Instalar
1. Baixe `MLA-0.2.0-windows.zip` e o arquivo `.sha256.txt`. Se quiser conferir a integridade, no PowerShell:
   `Get-FileHash .\MLA-0.2.0-windows.zip -Algorithm SHA256` deve mostrar o mesmo código do `.sha256.txt`.
2. Clique com o botão direito no `.zip` → **Extrair tudo**.
3. Na pasta extraída, dê dois cliques em **instalar.cmd**. Não precisa ser administrador.
   - Opcional: `instalar.cmd -AtalhoNaAreaDeTrabalho` cria atalho na área de trabalho.
   - Opcional: `instalar.cmd -Verificar` roda o autoteste (banco, recursos, planilhas e navegador) numa pasta
     temporária, sem tocar nos seus dados.
4. Abra o **MLA** pelo menu Iniciar.

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
Feche o MLA e execute o **instalar.cmd** da versão nova. Só a pasta do programa é trocada; se algo falhar, a versão
anterior é restaurada. Ao abrir, o MLA faz backup do banco antes de atualizá-lo.

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
Instalação, autoteste, abertura e fechamento, recusa de instalar com o app aberto, atualização por cima e
desinstalação foram executados com sucesso **nesta máquina de desenvolvimento** (Windows 11), conferindo que os dados
reais existentes não foram alterados. **Ainda não foi testado em um computador limpo**: faça isso antes do primeiro
cliente (veja o [checklist](CHECKLIST_IMPLANTACAO.md)).
