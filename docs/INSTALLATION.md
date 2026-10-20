# Instalação

## Para usuários
Baixe `MLA-Setup-<versão>.exe` (e o `.sha256`) e dê dois cliques. Instalação por usuário, sem administrador:
programa em `%LOCALAPPDATA%\Programs\MLA`, dados em `%LOCALAPPDATA%\MLA` (outras empresas em
`%LOCALAPPDATA%\MLA\empresas\<nome>`), nunca apagados ao atualizar ou desinstalar. Atualizações: dentro do app,
em **Atualizações**. Detalhes: [guia de instalação](comercial/GUIA_INSTALACAO.md) e
[roteiro para um segundo computador](ROTEIRO_TESTE_SEGUNDO_COMPUTADOR.md).

Diagnóstico: `MLA.exe --self-test` grava um relatório em `logs\self-test.txt` da pasta de dados (banco, recursos,
planilhas/PDF e Edge com sandbox).

## Para desenvolvimento
```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev,build]"
.venv\Scripts\python -m mla
```

## Gerar o instalador
`.venv\Scripts\python tools\build_release.py` → `dist\MLA-Setup-<versão>.exe` + `.sha256` + notas da versão.
Processo completo, atualizações e publicação: [BUILD_E_DISTRIBUICAO.md](BUILD_E_DISTRIBUICAO.md).
