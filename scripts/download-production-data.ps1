[CmdletBinding()]
param(
    [string]$SshHost = "maple-vps",
    [string]$OutputRoot = (Join-Path (Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Maplestory") "exports"),
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
$remoteHelper = "/opt/maple-inven-monitor/scripts/export-production-csv.sh"

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

$partialName = ".$destinationName-$([Guid]::NewGuid().ToString('N')).partial"
$partialPath = Join-Path $resolvedOutputRoot $partialName

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

    if ((Test-Path -LiteralPath $finalPath) -or (Test-Path -LiteralPath $zipPath)) {
        throw "Export destination already exists: $destinationName"
    }
    Rename-Item -LiteralPath $partialPath -NewName $destinationName
    $partialPath = $null

    Compress-Archive -Path (Join-Path $finalPath "*") -DestinationPath $zipPath -CompressionLevel Optimal

    Write-Output $finalPath
    Write-Output $zipPath
}
catch {
    if ($null -ne $partialPath -and (Test-Path -LiteralPath $partialPath)) {
        Remove-Item -LiteralPath $partialPath -Recurse -Force
    }
    throw
}
