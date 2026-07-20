[CmdletBinding()]
param(
    [string]$SshHost = "maple-vps",
    [string]$OutputRoot = (Join-Path (Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Maplestory") "exports"),
    [ValidateRange(1, 600)]
    [int]$PruneTimeoutSeconds = 120,
    [switch]$PlanOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$requiredCsvFiles = @(
    "latest_post_metrics.csv",
    "cumulative_top50.csv",
    "collection_runs.csv",
    "security_quarantine.csv"
)
$requiredFiles = @($requiredCsvFiles + "SHA256SUMS.txt")
$remoteReleaseRoot = "/opt/maple-inven-monitor/exports/releases/"
$remoteInflightRoot = "/opt/maple-inven-monitor/exports/inflight/"
$remoteLatestLink = "/opt/maple-inven-monitor/exports/latest-download"
$remoteHelper = "/opt/maple-inven-monitor/scripts/export-production-csv.sh"

function Stop-ProcessTree {
    param([Parameter(Mandatory = $true)][Diagnostics.Process]$Process)

    if ($Process.HasExited) {
        return
    }
    if ($env:OS -eq "Windows_NT") {
        & "$env:SystemRoot\System32\taskkill.exe" /PID $Process.Id /T /F 2>&1 | Out-Null
    } else {
        $Process.Kill()
    }
    $Process.WaitForExit()
}

function Invoke-ApplicationWithTimeout {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $captureRoot = Join-Path ([IO.Path]::GetTempPath()) ("maple-command-" + [Guid]::NewGuid().ToString("N"))
    $stdoutPath = "$captureRoot.stdout"
    $stderrPath = "$captureRoot.stderr"
    $process = $null
    try {
        $launchPath = $FilePath
        $launchArguments = $Arguments
        if ([IO.Path]::GetExtension($FilePath) -in @(".cmd", ".bat")) {
            $launchPath = "$env:SystemRoot\System32\cmd.exe"
            $launchArguments = @("/d", "/c", $FilePath) + $Arguments
        }

        $process = Start-Process `
            -FilePath $launchPath `
            -ArgumentList $launchArguments `
            -NoNewWindow `
            -PassThru `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath
        # Windows PowerShell 5.1 can lose ExitCode for fast processes unless the handle is retained.
        $null = $process.Handle
        $completed = $process.WaitForExit($TimeoutSeconds * 1000)
        if (-not $completed) {
            Stop-ProcessTree -Process $process
        } else {
            # Flush redirected output before reading the capture files.
            $process.WaitForExit()
            $process.Refresh()
        }

        $exitCode = if ($completed) { [int]$process.ExitCode } else { $null }

        $stdout = if (Test-Path -LiteralPath $stdoutPath) {
            [IO.File]::ReadAllText($stdoutPath)
        } else {
            ""
        }
        $stderr = if (Test-Path -LiteralPath $stderrPath) {
            [IO.File]::ReadAllText($stderrPath)
        } else {
            ""
        }
        [PSCustomObject]@{
            TimedOut = -not $completed
            ExitCode = $exitCode
            Stdout = $stdout
            Stderr = $stderr
        }
    } finally {
        foreach ($capturePath in @($stdoutPath, $stderrPath)) {
            if (Test-Path -LiteralPath $capturePath) {
                Remove-Item -LiteralPath $capturePath -Force
            }
        }
        if ($null -ne $process) {
            $process.Dispose()
        }
    }
}

if (
    [string]::IsNullOrWhiteSpace($SshHost) -or
    $SshHost -notmatch '^[A-Za-z0-9._-]+$' -or
    $SshHost.StartsWith("-", [StringComparison]::Ordinal)
) {
    throw "Invalid SSH host. Use only letters, digits, dot, underscore, or hyphen, and do not begin with a hyphen."
}

$resolvedOutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$timestamp = [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss")
$destinationName = "production-$timestamp"
$finalPath = Join-Path $resolvedOutputRoot $destinationName
$zipPath = "$finalPath.zip"

if ($PlanOnly) {
    [ordered]@{
        SshHost = $SshHost
        OutputRoot = $resolvedOutputRoot
        RequiredFiles = $requiredFiles
        Destination = $finalPath
    } | ConvertTo-Json -Compress
    exit 0
}

$sshCommand = Get-Command ssh -CommandType Application -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($null -eq $sshCommand) {
    throw "The ssh command was not found. Install or enable the Windows OpenSSH client."
}
$scpCommand = Get-Command scp -CommandType Application -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($null -eq $scpCommand) {
    throw "The scp command was not found. Install or enable the Windows OpenSSH client."
}

New-Item -ItemType Directory -Path $resolvedOutputRoot -Force | Out-Null
if ((Test-Path -LiteralPath $finalPath) -or (Test-Path -LiteralPath $zipPath)) {
    throw "Export destination already exists: $destinationName"
}

$runId = [Guid]::NewGuid().ToString("N")
$partialName = ".$destinationName-$runId.partial"
$partialPath = Join-Path $resolvedOutputRoot $partialName
$temporaryZipPath = Join-Path $resolvedOutputRoot ".$destinationName-$runId.partial.zip"
$finalFolderOwned = $false
$finalZipOwned = $false

try {
    $sshArguments = @(
        "-o", "BatchMode=yes",
        "-o", "NumberOfPasswordPrompts=0",
        "-o", "ConnectTimeout=15",
        "--",
        $SshHost,
        $remoteHelper
    )
    $remoteOutput = @(& $sshCommand.Source @sshArguments)
    if ($LASTEXITCODE -ne 0) {
        throw "The remote production export helper failed with exit code $LASTEXITCODE."
    }

    $remoteLines = @(
        $remoteOutput |
            ForEach-Object { ([string]$_).Trim() } |
            Where-Object { $_.Length -gt 0 }
    )
    if ($remoteLines.Count -ne 1) {
        throw "The remote helper must return exactly one release path."
    }
    $remoteReleasePath = $remoteLines[0]
    $escapedReleaseRoot = [Regex]::Escape($remoteReleaseRoot)
    if ($remoteReleasePath -notmatch "^${escapedReleaseRoot}[A-Za-z0-9][A-Za-z0-9._-]*$") {
        throw "The remote helper returned a path outside the production release directory."
    }

    & $scpCommand.Source -r -- "${SshHost}:$remoteReleasePath" $partialPath
    if ($LASTEXITCODE -ne 0) {
        throw "The production export download failed with exit code $LASTEXITCODE."
    }
    if (-not (Test-Path -LiteralPath $partialPath -PathType Container)) {
        throw "The production export download did not create its partial directory."
    }

    $downloadedItems = @(Get-ChildItem -LiteralPath $partialPath -Force)
    $downloadedNames = @($downloadedItems | ForEach-Object { $_.Name } | Sort-Object)
    $expectedNames = @($requiredFiles | Sort-Object)
    $fileDifference = @(Compare-Object -ReferenceObject $expectedNames -DifferenceObject $downloadedNames)
    if (
        $downloadedItems.Count -ne $requiredFiles.Count -or
        @($downloadedItems | Where-Object { -not $_.PSIsContainer }).Count -ne $requiredFiles.Count -or
        $fileDifference.Count -ne 0
    ) {
        throw "The downloaded release does not contain exactly the required export files."
    }

    $checksums = @{}
    foreach ($line in Get-Content -LiteralPath (Join-Path $partialPath "SHA256SUMS.txt")) {
        if ($line -notmatch '^([0-9A-Fa-f]{64}) [ *]([^\\/]+)$') {
            throw "SHA256SUMS.txt contains an invalid entry."
        }
        $checksumName = $Matches[2]
        if ($checksumName -notin $requiredCsvFiles -or $checksums.ContainsKey($checksumName)) {
            throw "SHA256SUMS.txt contains an unexpected or duplicate file entry."
        }
        $checksums[$checksumName] = $Matches[1]
    }
    if ($checksums.Count -ne $requiredCsvFiles.Count) {
        throw "SHA256SUMS.txt does not cover every required CSV file."
    }

    foreach ($csvName in $requiredCsvFiles) {
        $csvPath = Join-Path $partialPath $csvName
        $actualHash = (Get-FileHash -LiteralPath $csvPath -Algorithm SHA256).Hash
        if (-not $actualHash.Equals($checksums[$csvName], [StringComparison]::OrdinalIgnoreCase)) {
            throw "Checksum verification failed for $csvName."
        }
    }

    if (
        (Test-Path -LiteralPath $finalPath) -or
        (Test-Path -LiteralPath $zipPath) -or
        (Test-Path -LiteralPath $temporaryZipPath)
    ) {
        throw "Export destination already exists: $destinationName"
    }

    $compressArguments = @{
        Path = Join-Path $partialPath "*"
        DestinationPath = $temporaryZipPath
        CompressionLevel = "Optimal"
    }
    Compress-Archive @compressArguments
    if (-not (Test-Path -LiteralPath $temporaryZipPath -PathType Leaf)) {
        throw "ZIP preparation did not create the temporary archive."
    }

    $pruneArguments = @(
        "-n",
        "-o", "BatchMode=yes",
        "-o", "NumberOfPasswordPrompts=0",
        "-o", "ConnectTimeout=15",
        "--",
        $SshHost,
        $remoteHelper,
        "--prune",
        $remoteReleasePath
    )
    $pruneResult = Invoke-ApplicationWithTimeout `
        -FilePath $sshCommand.Source `
        -Arguments $pruneArguments `
        -TimeoutSeconds $PruneTimeoutSeconds
    Write-Verbose "Prune SSH result: timed_out=$($pruneResult.TimedOut); exit_code=$($pruneResult.ExitCode)"
    if ($pruneResult.TimedOut) {
        $remoteReleaseName = [IO.Path]::GetFileName($remoteReleasePath)
        $remoteInflightPath = "$remoteInflightRoot$remoteReleaseName"
        $verificationArguments = @(
            "-n",
            "-o", "BatchMode=yes",
            "-o", "NumberOfPasswordPrompts=0",
            "-o", "ConnectTimeout=15",
            "--",
            $SshHost,
            "test", "-d", $remoteReleasePath,
            "-a", "!", "-e", $remoteInflightPath,
            "-a", $remoteReleasePath, "-ef", $remoteLatestLink
        )
        $verificationResult = Invoke-ApplicationWithTimeout `
            -FilePath $sshCommand.Source `
            -Arguments $verificationArguments `
            -TimeoutSeconds ([Math]::Min($PruneTimeoutSeconds, 30))
        if ($verificationResult.TimedOut) {
            throw "The remote prune SSH session timed out, and completion verification also timed out."
        }
        if ($verificationResult.ExitCode -ne 0) {
            throw "The remote prune SSH session timed out before the completed release state could be verified (exit code $($verificationResult.ExitCode)). $($verificationResult.Stderr.Trim())"
        }
        if (-not [string]::IsNullOrWhiteSpace($verificationResult.Stdout)) {
            throw "The remote prune completion verification returned unexpected output."
        }
        Write-Verbose "The prune SSH session did not close, but the completed remote release state was verified. Continuing safely."
    } elseif ($pruneResult.ExitCode -ne 0) {
        throw "The remote release pruning failed with exit code $($pruneResult.ExitCode). $($pruneResult.Stderr.Trim())"
    }
    $unexpectedPruneOutput = @(
        $pruneResult.Stdout -split "`r?`n" |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_.Length -gt 0 }
    )
    if ($unexpectedPruneOutput.Count -ne 0) {
        throw "The remote prune helper returned unexpected output."
    }

    Rename-Item -LiteralPath $partialPath -NewName $destinationName
    $partialPath = $null
    $finalFolderOwned = $true
    Move-Item -LiteralPath $temporaryZipPath -Destination $zipPath
    $temporaryZipPath = $null
    $finalZipOwned = $true

    Write-Output $finalPath
    Write-Output $zipPath
}
catch {
    if ($finalZipOwned -and (Test-Path -LiteralPath $zipPath)) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    if ($finalFolderOwned -and (Test-Path -LiteralPath $finalPath)) {
        Remove-Item -LiteralPath $finalPath -Recurse -Force
    }
    if ($null -ne $temporaryZipPath -and (Test-Path -LiteralPath $temporaryZipPath)) {
        Remove-Item -LiteralPath $temporaryZipPath -Force
    }
    if ($null -ne $partialPath -and (Test-Path -LiteralPath $partialPath)) {
        Remove-Item -LiteralPath $partialPath -Recurse -Force
    }
    throw
}
