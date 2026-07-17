[CmdletBinding()]
param(
    [string]$ExportRoot = (Join-Path (Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Maplestory") "exports"),
    [ValidateRange(1024, 65535)]
    [int]$Port = 8501
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$appPath = Join-Path $repositoryRoot "src\maple_monitor\dashboard\export_app.py"
$resolvedExportRoot = [IO.Path]::GetFullPath($ExportRoot)

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "The project Python environment was not found. Run uv sync --extra dashboard first."
}
if (-not (Test-Path -LiteralPath $resolvedExportRoot -PathType Container)) {
    throw "The export directory was not found: $resolvedExportRoot"
}
if (@(Get-ChildItem -LiteralPath $resolvedExportRoot -Filter "production-*.zip" -File).Count -eq 0) {
    throw "No completed production export ZIP was found in: $resolvedExportRoot"
}

$env:MAPLE_EXPORT_PATH = $resolvedExportRoot
$analysisRoot = Join-Path $resolvedExportRoot "analysis"
& $pythonPath -m maple_monitor.cli analyze-export --export-path $resolvedExportRoot --analysis-root $analysisRoot
if ($LASTEXITCODE -ne 0) {
    throw "Local semantic analysis failed."
}
$env:MAPLE_ANALYSIS_ROOT = $analysisRoot
$analysisJob = Start-Job -ArgumentList $pythonPath, $resolvedExportRoot, $analysisRoot -ScriptBlock {
    param($PythonPath, $ExportPath, $ArtifactRoot)
    while ($true) {
        & $PythonPath -m maple_monitor.cli analyze-export --export-path $ExportPath --analysis-root $ArtifactRoot *> $null
        Start-Sleep -Seconds 30
    }
}
try {
    & $pythonPath -m streamlit run $appPath --server.port $Port
    $streamlitExitCode = $LASTEXITCODE
}
finally {
    Stop-Job -Job $analysisJob -ErrorAction SilentlyContinue
    Remove-Job -Job $analysisJob -Force -ErrorAction SilentlyContinue
}
exit $streamlitExitCode
