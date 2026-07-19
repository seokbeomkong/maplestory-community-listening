[CmdletBinding()]
param(
    [string]$SshHost = "maple-vps",
    [string]$ExportRoot = (Join-Path (Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Maplestory") "exports"),
    [ValidatePattern('^(?!-)[A-Za-z0-9._/-]+$')]
    [string]$Remote = "origin",
    [ValidatePattern('^(?!-)[A-Za-z0-9._/-]+$')]
    [string]$Branch = "main",
    [string]$DownloadScriptPath = "",
    [string]$PythonExecutablePath = "",
    [switch]$PlanOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$resolvedExportRoot = [IO.Path]::GetFullPath($ExportRoot)
$publicDataRoot = Join-Path $repositoryRoot "portfolio_data"
$analysisRoot = Join-Path $resolvedExportRoot "analysis"
$downloadScript = if ([string]::IsNullOrWhiteSpace($DownloadScriptPath)) {
    Join-Path $PSScriptRoot "download-production-data.ps1"
} else {
    [IO.Path]::GetFullPath($DownloadScriptPath)
}
$pythonPath = if ([string]::IsNullOrWhiteSpace($PythonExecutablePath)) {
    Join-Path $repositoryRoot ".venv\Scripts\python.exe"
} else {
    [IO.Path]::GetFullPath($PythonExecutablePath)
}
$requiredAnalysisFiles = @("manifest.json", "semantic_posts.csv", "semantic_comments.csv")
$steps = @("download", "analyze", "validate", "publish", "commit", "push")

if ($PlanOnly) {
    [ordered]@{
        RepositoryRoot = $repositoryRoot
        ExportRoot = $resolvedExportRoot
        PublicDataRoot = $publicDataRoot
        Remote = $Remote
        Branch = $Branch
        Steps = $steps
    } | ConvertTo-Json -Compress
    exit 0
}

if (-not (Test-Path -LiteralPath $downloadScript -PathType Leaf)) {
    throw "The production download script was not found: $downloadScript"
}
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "The project Python environment was not found. Run uv sync --extra dashboard --extra local-analysis first."
}

$gitCommand = Get-Command git -CommandType Application -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($null -eq $gitCommand) {
    throw "The git command was not found."
}

$gitRoot = (& $gitCommand.Source -C $repositoryRoot rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or [IO.Path]::GetFullPath($gitRoot) -ne $repositoryRoot) {
    throw "The publish script must run from its own Git repository."
}

$currentBranch = (& $gitCommand.Source -C $repositoryRoot symbolic-ref --quiet --short HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $currentBranch -ne $Branch) {
    throw "Publishing requires the checked-out branch to be '$Branch'; detached HEAD and other branches are rejected."
}

$gitDirectory = (& $gitCommand.Source -C $repositoryRoot rev-parse --absolute-git-dir).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to locate the Git metadata directory."
}
foreach ($operationPath in @("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply")) {
    if (Test-Path -LiteralPath (Join-Path $gitDirectory $operationPath)) {
        throw "A Git merge, rebase, cherry-pick, or revert is in progress. Finish it before publishing."
    }
}

# A clean starting point lets this script roll back only changes it owns.
$initialStatus = @(& $gitCommand.Source -C $repositoryRoot status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect the Git working tree."
}
if ($initialStatus.Count -ne 0) {
    throw "The Git working tree is not clean. Commit or restore existing changes before publishing."
}

& $gitCommand.Source -C $repositoryRoot fetch --no-tags $Remote $Branch
if ($LASTEXITCODE -ne 0) {
    throw "Unable to fetch $Remote/$Branch."
}
$baselineHead = (& $gitCommand.Source -C $repositoryRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to resolve the local branch HEAD."
}
$remoteHead = (& $gitCommand.Source -C $repositoryRoot rev-parse FETCH_HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to resolve the fetched remote branch HEAD."
}
if ($baselineHead -ne $remoteHead) {
    throw "Local $Branch must exactly match $Remote/$Branch before publishing. Pull or synchronize it first."
}

$stagingRoot = Join-Path ([IO.Path]::GetTempPath()) ("maple-dashboard-publish-" + [Guid]::NewGuid().ToString("N"))
$publicMutationStarted = $false
$commitCreated = $false

try {
    Write-Host "[1/6] Downloading the latest verified VPS export."
    $downloadOutput = @(& $downloadScript -SshHost $SshHost -OutputRoot $resolvedExportRoot)
    if ($downloadOutput.Count -ne 2) {
        throw "The download script must return exactly the created folder and ZIP paths."
    }
    $downloadedArchivePath = [IO.Path]::GetFullPath(([string]$downloadOutput[1]).Trim())
    $exportPrefix = $resolvedExportRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (
        -not $downloadedArchivePath.StartsWith($exportPrefix, [StringComparison]::OrdinalIgnoreCase) -or
        [IO.Path]::GetFileName($downloadedArchivePath) -notmatch '^production-\d{8}-\d{6}\.zip$' -or
        -not (Test-Path -LiteralPath $downloadedArchivePath -PathType Leaf)
    ) {
        throw "The downloader returned an invalid production ZIP path."
    }
    $latestArchive = Get-Item -LiteralPath $downloadedArchivePath

    Write-Host "[2/6] Updating semantic analysis for the downloaded release."
    & $pythonPath -m maple_monitor.cli analyze-export `
        --export-path $latestArchive.FullName `
        --analysis-root $analysisRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Semantic analysis failed with exit code $LASTEXITCODE."
    }

    Write-Host "[3/6] Validating the ZIP and matching analysis artifacts."
    $sourceAnalysisRoot = Join-Path $analysisRoot $latestArchive.BaseName
    foreach ($filename in $requiredAnalysisFiles) {
        $requiredPath = Join-Path $sourceAnalysisRoot $filename
        if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
            throw "Required analysis artifact was not found: $requiredPath"
        }
    }

    $manifestPath = Join-Path $sourceAnalysisRoot "manifest.json"
    $manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $manifestPath | ConvertFrom-Json
    if ($manifest.complete -ne $true) {
        throw "The analysis manifest is not complete."
    }
    if ([string]$manifest.source_archive -ne $latestArchive.Name) {
        throw "The analysis manifest points to a different source archive."
    }
    $archiveHash = (Get-FileHash -LiteralPath $latestArchive.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    if ([string]$manifest.source_sha256 -ne $archiveHash) {
        throw "The analysis manifest source_sha256 does not match the downloaded ZIP."
    }

    $stagedDataRoot = Join-Path $stagingRoot "portfolio_data"
    $stagedAnalysisRoot = Join-Path (Join-Path $stagedDataRoot "analysis") $latestArchive.BaseName
    New-Item -ItemType Directory -Path $stagedAnalysisRoot -Force | Out-Null
    Copy-Item -LiteralPath $latestArchive.FullName -Destination $stagedDataRoot -Force
    foreach ($filename in $requiredAnalysisFiles) {
        Copy-Item -LiteralPath (Join-Path $sourceAnalysisRoot $filename) `
            -Destination $stagedAnalysisRoot -Force
    }

    $headBeforeMutation = (& $gitCommand.Source -C $repositoryRoot rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to recheck HEAD after analysis."
    }
    $statusBeforeMutation = @(& $gitCommand.Source -C $repositoryRoot status --porcelain --untracked-files=all)
    if ($LASTEXITCODE -ne 0 -or $headBeforeMutation -ne $baselineHead -or $statusBeforeMutation.Count -ne 0) {
        throw "The repository changed while analysis was running; publication was cancelled."
    }

    Write-Host "[4/6] Replacing the public dashboard snapshot."
    $publicMutationStarted = $true
    New-Item -ItemType Directory -Path (Join-Path $publicDataRoot "analysis") -Force | Out-Null
    Get-ChildItem -LiteralPath $publicDataRoot -Filter "production-*.zip" -File |
        Remove-Item -Force
    Get-ChildItem -LiteralPath (Join-Path $publicDataRoot "analysis") -Filter "production-*" -Directory |
        Remove-Item -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $stagedDataRoot $latestArchive.Name) `
        -Destination $publicDataRoot -Force
    Copy-Item -LiteralPath $stagedAnalysisRoot `
        -Destination (Join-Path $publicDataRoot "analysis") -Recurse -Force

    Write-Host "[5/6] Recording only the public dashboard data."
    # Contract: git add -- "portfolio_data"
    & $gitCommand.Source -C $repositoryRoot add -- "portfolio_data"
    if ($LASTEXITCODE -ne 0) {
        throw "Git staging failed with exit code $LASTEXITCODE."
    }

    $headBeforeCommit = (& $gitCommand.Source -C $repositoryRoot rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to resolve HEAD before commit."
    }
    $stagedPaths = @(& $gitCommand.Source -C $repositoryRoot diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect staged paths."
    }
    $unstagedPaths = @(& $gitCommand.Source -C $repositoryRoot diff --name-only)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect unstaged paths."
    }
    $untrackedPaths = @(& $gitCommand.Source -C $repositoryRoot ls-files --others --exclude-standard)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect untracked paths."
    }
    $invalidStagedPaths = @($stagedPaths | Where-Object { $_ -notlike "portfolio_data/*" })
    if (
        $headBeforeCommit -ne $baselineHead -or
        $invalidStagedPaths.Count -ne 0 -or
        $unstagedPaths.Count -ne 0 -or
        $untrackedPaths.Count -ne 0
    ) {
        throw "Repository scope changed before commit; only staged portfolio_data paths are allowed."
    }
    & $gitCommand.Source -C $repositoryRoot diff --cached --quiet -- "portfolio_data"
    $diffExitCode = $LASTEXITCODE
    if ($diffExitCode -eq 0) {
        Write-Host "The public snapshot is already current; no GitHub update is needed."
        exit 0
    }
    if ($diffExitCode -ne 1) {
        throw "Unable to inspect staged dashboard data."
    }

    $expectedTree = (& $gitCommand.Source -C $repositoryRoot write-tree).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to record the validated Git index tree."
    }

    & $gitCommand.Source -C $repositoryRoot commit `
        -m ("data: publish {0}" -f $latestArchive.BaseName)
    if ($LASTEXITCODE -ne 0) {
        throw "Git commit failed with exit code $LASTEXITCODE."
    }
    $commitCreated = $true

    $publishedHead = (& $gitCommand.Source -C $repositoryRoot rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to resolve the generated commit."
    }
    $publishedParent = (& $gitCommand.Source -C $repositoryRoot rev-parse HEAD^).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to resolve the generated commit parent."
    }
    $publishedPaths = @(& $gitCommand.Source -C $repositoryRoot diff-tree --no-commit-id --name-only -r HEAD)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect the generated commit paths."
    }
    $invalidPublishedPaths = @($publishedPaths | Where-Object { $_ -notlike "portfolio_data/*" })
    $publishedTree = (& $gitCommand.Source -C $repositoryRoot rev-parse 'HEAD^{tree}').Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to resolve the generated commit tree."
    }
    if (
        $publishedParent -ne $baselineHead -or
        $publishedTree -ne $expectedTree -or
        $invalidPublishedPaths.Count -ne 0
    ) {
        throw "The generated commit did not contain exactly one scoped dashboard-data change."
    }

    Write-Host "[6/6] Pushing the verified commit to GitHub."
    $pushRef = "${publishedHead}:refs/heads/$Branch"
    & $gitCommand.Source -C $repositoryRoot push $Remote $pushRef
    if ($LASTEXITCODE -ne 0) {
        throw "Git push failed. The local publish commit was preserved; retry: git push $Remote $pushRef"
    }

    [ordered]@{
        Status = "published"
        Archive = $latestArchive.Name
        Analysis = $sourceAnalysisRoot
        Remote = $Remote
        Branch = $Branch
    } | ConvertTo-Json -Compress
}
catch {
    if ($publicMutationStarted -and -not $commitCreated) {
        $originalFailure = $_.Exception.Message
        & $gitCommand.Source -C $repositoryRoot restore --source=HEAD --staged --worktree -- portfolio_data
        $restoreExitCode = $LASTEXITCODE
        & $gitCommand.Source -C $repositoryRoot clean -fd -- portfolio_data
        $cleanExitCode = $LASTEXITCODE
        $remainingOwnedChanges = @(
            & $gitCommand.Source -C $repositoryRoot status --porcelain --untracked-files=all -- portfolio_data
        )
        $statusExitCode = $LASTEXITCODE
        if (
            $restoreExitCode -ne 0 -or
            $cleanExitCode -ne 0 -or
            $statusExitCode -ne 0 -or
            $remainingOwnedChanges.Count -ne 0
        ) {
            throw "Publish failed: $originalFailure Rollback also failed. Run: git restore --source=HEAD --staged --worktree -- portfolio_data"
        }
    }
    throw
}
finally {
    if (Test-Path -LiteralPath $stagingRoot) {
        try {
            Remove-Item -LiteralPath $stagingRoot -Recurse -Force -ErrorAction Stop
        }
        catch {
            Write-Warning "Temporary publish files could not be removed: $stagingRoot"
        }
    }
}
