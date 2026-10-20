# Instalação

## Para clientes
Use o pacote `MLA-<versão>-windows.zip` e siga o [guia de instalação](comercial/GUIA_INSTALACAO.md): extrair e
executar `instalar.cmd` (por usuário, sem administrador). Programa em `%LOCALAPPDATA%\Programs\MLA`; dados em
`%LOCALAPPDATA%\MLA` (outras empresas em `%LOCALAPPDATA%\MLA\empresas\<nome>`), nunca apagados ao atualizar ou
desinstalar, a menos que `desinstalar.cmd -RemoverDados -ConfirmarRemocaoDeDados` seja usado.

Diagnóstico: `MLA.exe --self-test` grava um relatório em `logs\self-test.txt` da pasta de dados (banco, recursos,
planilhas/PDF e Edge com sandbox).

## Para desenvolvimento
```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev,build]"
.venv\Scripts\python -m mla
```
Navegador Chromium do Playwright é opcional (`python -m playwright install chromium`); o padrão é o Edge do sistema.

## Gerar a distribuição
```powershell
.venv\Scripts\python tools\build_release.py
```
Faz o build com PyInstaller (`mla.spec`), roda `MLA.exe --self-test` numa pasta de dados temporária e monta
`dist\MLA-<versão>-windows.zip` (programa + `installer\*` + `VERSAO.txt`) e o `.sha256.txt`. Se o autoteste falhar,
o pacote não é gerado. Versão 0.2.0: build em cerca de 2 minutos, pasta do programa com 219 MB, zip com 85 MB.

Ainda pendente: assinatura digital de código (SmartScreen) e teste em máquina limpa.
