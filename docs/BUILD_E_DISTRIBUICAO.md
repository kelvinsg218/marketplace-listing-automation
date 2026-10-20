# Build, distribuição e atualizações (Windows)

## Arquitetura escolhida (e por que não Electron)
O MLA é um aplicativo Python/PySide6 (Qt) com SQLite e Playwright no mesmo processo: não existe frontend web nem
backend HTTP. Avaliação de 20/10/2026:

| Critério | Electron + electron-builder + electron-updater | PyInstaller + instalador próprio (escolhido) |
|---|---|---|
| Compatibilidade com o código atual | Exigiria reescrever as 13 telas em HTML/JS e expor o Python como serviço local (reconstrução) | Usa o código como está |
| Memória (notebook de 8 GB) | Chromium do Electron (~150 MB) + Python + Edge da automação | Um processo Qt (~100 MB aberto) + Edge da automação |
| Segurança interface ↔ processos | Precisaria de IPC/HTTP local (porta exposta, contextIsolation etc.) | Sem servidor local nem porta aberta |
| Instalador `.exe` | electron-builder (NSIS) | `MLA-Setup-<versão>.exe` gerado com PyInstaller (sem software novo) |
| Atualização | electron-updater (GitHub Releases) | Atualizador do app lendo GitHub Releases + SHA-256 |
| Dependências novas | Node/Electron no build | Nenhuma (PyInstaller já era usado) |

electron-builder e electron-updater só empacotam e atualizam aplicativos Electron, por isso não foram instalados.

## Como gerar uma versão
1. Atualize `__version__` em `src/mla/__init__.py` (ex.: `0.1.1-beta`) e `version` em `pyproject.toml`
   (formato PEP 440: `0.1.1b0`).
2. `.venv\Scripts\python -m pytest` (suíte completa).
3. `.venv\Scripts\python tools\build_release.py`
   - build do programa (`mla.spec`, pasta `dist\MLA`);
   - `MLA.exe --self-test` numa pasta de dados temporária (banco, recursos, planilhas/PDF, Edge com sandbox);
     se falhar, nada é empacotado;
   - pacote interno `build\setup-payload\MLA.zip` (programa + `desinstalar.ps1/.cmd` + `LEIA-ME.txt`);
   - instalador de arquivo único `dist\MLA-Setup-<versão>.exe` (`installer\setup.spec`);
   - `dist\MLA-Setup-<versão>.exe.sha256` e `dist\release-notes-<versão>.md`.
   `--version X` gera uma versão só para teste sem alterar o código-fonte.

Tempos medidos (0.1.0-beta, esta máquina): programa 124 s, instalador 106 s; instalador com 129 MB.

## O instalador
- Instalação por usuário, sem administrador: programa em `%LOCALAPPDATA%\Programs\MLA`; dados em
  `%LOCALAPPDATA%\MLA` (outras empresas em `...\MLA\empresas\<nome>`), nunca dentro da pasta do programa.
- Extrai para `MLA.novo`, troca as pastas de uma vez e só então apaga a versão anterior; se a troca falhar, a
  versão anterior é restaurada. Recusa pacote com caminhos fora da pasta (`..\`).
- Cria atalho no menu Iniciar (e, se marcado, na área de trabalho) e o registro em "Aplicativos instalados"
  (`HKCU\...\Uninstall\MLA`), cujo desinstalador é `desinstalar.ps1` (mantém os dados).
- Modos: assistente (padrão), `--atualizar --aguardar-pid N --abrir` (chamado pelo app), `--silencioso` (testes).
- Log: `%LOCALAPPDATA%\MLA\logs\instalador.log`.

## Atualizações
- O app consulta um feed no formato da API do GitHub Releases. Padrão (desde a 0.1.2-beta):
  `https://api.github.com/repos/kelvinsg218/marketplace-listing-automation-showcase/releases` — as **releases do
  repositório público de apresentação**. Elas carregam só o instalador e o SHA-256; o código-fonte fica no
  repositório principal, que continua privado (o GitHub não permite que um app baixe releases de repositório
  privado sem token, e nenhum token é embutido no app). Releases sem `MLA-Setup-<versão>.exe` são ignoradas.
- A 0.1.1-beta procurava um repositório `mla-releases` que não será criado: quem a instalou atualiza instalando a
  0.1.2-beta por cima (dados mantidos).
- Uma versão é instalável só se tiver o arquivo `MLA-Setup-<versão>.exe` e o SHA-256 (campo `digest` do GitHub ou
  arquivo `MLA-Setup-<versão>.exe.sha256`). Download em `%LOCALAPPDATA%\MLA\atualizacoes`, conferido antes de
  executar; arquivo divergente é apagado e nada é instalado. Só HTTPS (ou `127.0.0.1` para testes).
- Versões beta recebem betas; versões estáveis ignoram pré-lançamentos. Rascunhos são ignorados.
- Fluxo: Atualizações → Verificar agora (ou verificação automática 8 s após abrir) → Baixar e instalar → o app
  fecha → o instalador mostra o progresso, troca a pasta do programa e reabre o MLA. Na abertura, o MLA faz backup
  do banco antes de qualquer migração.
- Canal alternativo: `%LOCALAPPDATA%\MLA\atualizacoes\canal.json` com `{"feed_url": "...",
  "include_prereleases": true}` ou a variável `MLA_UPDATE_FEED` (testes).

### Publicar uma versão
1. Gerar a versão (seção acima) e rodar a suíte de testes.
2. No GitHub, no repositório **marketplace-listing-automation-showcase** → Releases → **Draft a new release**:
   tag `v<versão>` (ex.: `v0.1.2-beta`), título `MLA <versão>`, texto de `dist\release-notes-<versão>.md`,
   marcar **Set as a pre-release** para betas, anexar `MLA-Setup-<versão>.exe` e `MLA-Setup-<versão>.exe.sha256`
   (arquivos de release aceitam até 2 GB; o instalador tem ~130 MB e não pode ir como arquivo no Git, que limita a
   100 MB por arquivo). **Publish release**.
3. Conferir: `https://api.github.com/repos/kelvinsg218/marketplace-listing-automation-showcase/releases` deve
   listar a versão; no MLA instalado, Atualizações → Verificar agora.

Não anexe outros arquivos do projeto à release (nada de `dist\MLA`, `build\`, bancos ou logs).

## Limitações conhecidas
- Sem assinatura digital: o Windows SmartScreen pode avisar no primeiro uso do instalador. O SHA-256 garante que
  o arquivo não se corrompeu no download, mas não substitui a assinatura (que exige certificado pago).
- Instaladores de arquivo único gerados com PyInstaller às vezes são marcados por antivírus (falso positivo).
- O desinstalador é um script PowerShell (abre uma janela de console por alguns segundos).
