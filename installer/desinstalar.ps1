# Desinstalador do MLA (usuário atual). Remove o programa, os atalhos e o registro em "Aplicativos instalados".
# Os DADOS (%LOCALAPPDATA%\MLA: catálogo, imagens, contas, sessões e backups) são mantidos, a menos que
# -RemoverDados seja informado junto com -ConfirmarRemocaoDeDados (as duas opções, de propósito).
#
# Uso: desinstalar.cmd [-Destino <pasta>] [-RemoverDados -ConfirmarRemocaoDeDados]
param(
    [string]$Destino = "",
    [switch]$RemoverDados,
    [switch]$ConfirmarRemocaoDeDados
)
$ErrorActionPreference = "Stop"
if (-not $Destino) {
    $chave = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\MLA"
    $registro = Get-ItemProperty -Path $chave -ErrorAction SilentlyContinue
    $Destino = if ($registro -and $registro.InstallLocation) { $registro.InstallLocation } else { $PSScriptRoot }
}
if (-not (Test-Path (Join-Path $Destino "MLA.exe"))) {
    Write-Host "MLA.exe não encontrado em $Destino; nada a remover." -ForegroundColor Yellow
    exit 1
}
$aberto = Get-Process -Name "MLA" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($Destino, [System.StringComparison]::OrdinalIgnoreCase) }
if ($aberto) {
    Write-Host "O MLA está aberto. Feche o aplicativo e execute a desinstalação de novo." -ForegroundColor Yellow
    exit 2
}

foreach ($atalho in @((Join-Path ([Environment]::GetFolderPath("Programs")) "MLA.lnk"),
                      (Join-Path ([Environment]::GetFolderPath("Desktop")) "MLA.lnk"))) {
    if (Test-Path $atalho) { Remove-Item $atalho -Force; Write-Host "Atalho removido: $atalho" }
}
Remove-Item "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\MLA" -Recurse -Force -ErrorAction SilentlyContinue
Set-Location $env:TEMP  # never keep the folder being removed as the current directory
Remove-Item $Destino -Recurse -Force
Write-Host "Programa removido de $Destino."

$dados = Join-Path $env:LOCALAPPDATA "MLA"
if ($RemoverDados -and $ConfirmarRemocaoDeDados) {
    if (Test-Path $dados) {
        Remove-Item $dados -Recurse -Force
        Write-Host "Dados removidos de $dados." -ForegroundColor Yellow
    }
} elseif ($RemoverDados) {
    Write-Host "Para apagar também os dados, repita com -RemoverDados -ConfirmarRemocaoDeDados. Nada foi apagado." -ForegroundColor Yellow
} else {
    Write-Host "Seus dados foram mantidos em $dados (reinstale para usá-los de novo)."
}
exit 0
