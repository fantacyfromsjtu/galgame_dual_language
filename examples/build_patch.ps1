param(
    [Parameter(Mandatory=$true)]
    [string]$StageDir,

    [string]$OutputXp3 = "dual_sub_patch.xp3",
    [string]$InstallDir = "",
    [switch]$NoBackup
)

$ErrorActionPreference = "Stop"

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptPath
$packer = Join-Path $repoRoot "scripts\xp3_pack.py"

if (!(Test-Path -LiteralPath $packer)) {
    throw "Missing packer script: $packer"
}
if (!(Test-Path -LiteralPath $StageDir)) {
    throw "Missing stage directory: $StageDir"
}

python $packer $StageDir $OutputXp3

if ($InstallDir) {
    New-Item -ItemType Directory -Force $InstallDir | Out-Null
    $target = Join-Path $InstallDir (Split-Path -Leaf $OutputXp3)
    if (!$NoBackup -and (Test-Path -LiteralPath $target)) {
        $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
        Copy-Item -LiteralPath $target -Destination "$target.before_$stamp" -Force
    }
    Copy-Item -LiteralPath $OutputXp3 -Destination $target -Force
    Get-Item -LiteralPath $target
}
else {
    Get-Item -LiteralPath $OutputXp3
}
