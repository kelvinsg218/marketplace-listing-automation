# Instalação

## Para clientes (pasta com executável)
1. Copie a pasta `MLA` (gerada em `dist\MLA`) para, por exemplo, `C:\Program Files\MLA` ou `%LOCALAPPDATA%\Programs\MLA`.
2. Abra `MLA.exe`. Não é preciso Python, VS Code ou terminal.
3. Requisitos: Windows 10/11 64 bits e Microsoft Edge (já vem no Windows). Cerca de 220 MB em disco.

Os dados ficam em `%LOCALAPPDATA%\MLA` (banco, imagens, backups, logs, perfis de navegador). Atualizar ou
desinstalar o programa não apaga esses dados; para removê-los, apague essa pasta.

Diagnóstico: `MLA.exe --self-test` grava um relatório em `%LOCALAPPDATA%\MLA\logs\self-test.txt`.

## Para desenvolvimento
```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev,build]"
.venv\Scripts\python -m mla
```
Navegador Chromium do Playwright é opcional (`python -m playwright install chromium`); o padrão é o Edge do sistema.

## Gerar a distribuição
```powershell
.venv\Scripts\pyinstaller mla.spec --noconfirm
dist\MLA\MLA.exe --self-test
```
Instalador (Inno Setup/MSIX) ainda não existe — ver NEXT_STEPS.md.
