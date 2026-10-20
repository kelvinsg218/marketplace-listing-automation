# Instalador do MLA para o usuário atual (não precisa de administrador).
#
# Programa: %LOCALAPPDATA%\Programs\MLA      Dados: %LOCALAPPDATA%\MLA (nunca tocados por este script)
# Atualizar = executar de novo com a versão nova: só a pasta do programa é trocada; se algo falhar,
# a versão anterior é restaurada.
#
# Uso: instalar.cmd [-AtalhoNaAreaDeTrabalho] [-Verificar] [-Destino <pasta>] [-SemAtalhos] [-SemRegistro]
param(
    [switch]$AtalhoNaAreaDeTrabalho,
    [switch]$Verificar,
    [string]$Destino = (Join-Path $env:LOCALAPPDATA "Programs\MLA"),
    [switch]$SemAtalhos,
    [switch]$SemRegistro
)
$ErrorActionPreference = "Stop"
$origem = Join-Path $PSScriptRoot "MLA"
$exeOrigem = Join-Path $origem "MLA.exe"
if (-not (Test-Path $exeOrigem)) {
    Write-Host "Pasta MLA com MLA.exe não encontrada ao lado deste script ($origem)." -ForegroundColor Red
    exit 1
}
$versao = (Get-Content (Join-Path $PSScriptRoot "VERSAO.txt") -ErrorAction SilentlyContinue | Select-Object -First 1)
if (-not $versao) { $versao = "desconhecida" }

$aberto = Get-Process -Name "MLA" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($Destino, [System.StringComparison]::OrdinalIgnoreCase) }
if ($aberto) {
    Write-Host "O MLA está aberto. Feche o aplicativo e execute a instalação de novo." -ForegroundColor Yellow
    exit 2
}

Write-Host "Instalando MLA $versao em $Destino"
$anterior = $null
if (Test-Path $Destino) {
    $anterior = "$Destino.anterior"
    if (Test-Path $anterior) { Remove-Item $anterior -Recurse -Force }
    Rename-Item $Destino (Split-Path $anterior -Leaf)
    Write-Host "Versão anterior guardada temporariamente em $anterior"
}
try {
    New-Item -ItemType Directory -Force -Path $Destino | Out-Null
    Copy-Item (Join-Path $origem "*") $Destino -Recurse -Force
    Copy-Item (Join-Path $PSScriptRoot "desinstalar.ps1") $Destino -Force
    Copy-Item (Join-Path $PSScriptRoot "desinstalar.cmd") $Destino -Force
    Set-Content -Path (Join-Path $Destino "VERSAO.txt") -Value $versao -Encoding UTF8
    if (-not (Test-Path (Join-Path $Destino "MLA.exe"))) { throw "MLA.exe não foi copiado." }
} catch {
    Write-Host "Falha ao copiar os arquivos: $_" -ForegroundColor Red
    if (Test-Path $Destino) { Remove-Item $Destino -Recurse -Force -ErrorAction SilentlyContinue }
    if ($anterior -and (Test-Path $anterior)) {
        Rename-Item $anterior (Split-Path $Destino -Leaf)
        Write-Host "A versão anterior foi restaurada." -ForegroundColor Yellow
    }
    exit 3
}
if ($anterior -and (Test-Path $anterior)) { Remove-Item $anterior -Recurse -Force }

$exe = Join-Path $Destino "MLA.exe"
if (-not $SemAtalhos) {
    $shell = New-Object -ComObject WScript.Shell
    $menu = Join-Path ([Environment]::GetFolderPath("Programs")) "MLA.lnk"
    $atalho = $shell.CreateShortcut($menu)
    $atalho.TargetPath = $exe
    $atalho.WorkingDirectory = $Destino
    $atalho.Description = "Marketplace Listing Automation"
    $atalho.Save()
    Write-Host "Atalho criado no menu Iniciar."
    if ($AtalhoNaAreaDeTrabalho) {
        $area = Join-Path ([Environment]::GetFolderPath("Desktop")) "MLA.lnk"
        $atalho = $shell.CreateShortcut($area)
        $atalho.TargetPath = $exe
        $atalho.WorkingDirectory = $Destino
        $atalho.Save()
        Write-Host "Atalho criado na área de trabalho."
    }
}
if (-not $SemRegistro) {
    $chave = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\MLA"
    New-Item -Path $chave -Force | Out-Null
    $desinstalar = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$Destino\desinstalar.ps1`""
    Set-ItemProperty -Path $chave -Name DisplayName -Value "MLA - Marketplace Listing Automation"
    Set-ItemProperty -Path $chave -Name DisplayVersion -Value $versao
    Set-ItemProperty -Path $chave -Name Publisher -Value "MLA"
    Set-ItemProperty -Path $chave -Name InstallLocation -Value $Destino
    Set-ItemProperty -Path $chave -Name DisplayIcon -Value $exe
    Set-ItemProperty -Path $chave -Name UninstallString -Value $desinstalar
    Set-ItemProperty -Path $chave -Name NoModify -Value 1 -Type DWord
    Set-ItemProperty -Path $chave -Name NoRepair -Value 1 -Type DWord
    Write-Host "Registrado em Configurações > Aplicativos instalados."
}

if ($Verificar) {
    # self-test in a throwaway data folder: the user's data is not opened nor migrated here
    $teste = Join-Path $env:TEMP ("mla-verificacao-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
    $env:MLA_DATA_DIR = $teste
    $processo = Start-Process -FilePath $exe -ArgumentList "--self-test" -Wait -PassThru -WindowStyle Hidden
    Remove-Item Env:\MLA_DATA_DIR
    $relatorio = Join-Path $teste "logs\self-test.txt"
    if (Test-Path $relatorio) { Get-Content $relatorio -Encoding UTF8 | ForEach-Object { Write-Host "  $_" } }
    Remove-Item $teste -Recurse -Force -ErrorAction SilentlyContinue
    if ($processo.ExitCode -ne 0) {
        Write-Host "A verificação encontrou problemas (código $($processo.ExitCode))." -ForegroundColor Yellow
        exit 4
    }
    Write-Host "Verificação concluída sem falhas."
}
Write-Host "MLA $versao instalado. Seus dados ficam em $env:LOCALAPPDATA\MLA." -ForegroundColor Green
exit 0
