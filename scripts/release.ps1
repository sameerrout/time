# =====================================================================
# Issue Slip Manager & TTL Scanner - Automated Clean Release Script
# =====================================================================
[CmdletBinding()]
param (
    [switch]$SkipAndroidBuild,
    [switch]$SkipPyInstaller
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Issue Slip Manager & TTL Scanner Release Builder" -ForegroundColor Cyan
Write-Host " Project Root: $ProjectRoot" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# ---------------------------------------------------------------------
# 1. Environment & Prerequisites
# ---------------------------------------------------------------------
Write-Host "`n[1/6] Checking prerequisites..." -ForegroundColor Yellow

# Locate Java JDK with jlink
$JdkPath = "C:\Users\samee\.jdk17\jdk-17.0.20.1+1"
if (-not (Test-Path "$JdkPath\bin\jlink.exe")) {
    $altJdk = (Get-ChildItem -Path "C:\Program Files\Java", "C:\Users\samee\.jdk*" -Recurse -Filter "jlink.exe" -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($altJdk) {
        $JdkPath = Split-Path -Parent (Split-Path -Parent $altJdk.FullName)
    } else {
        throw "Standard OpenJDK with jlink.exe not found at $JdkPath."
    }
}
$env:JAVA_HOME = $JdkPath
Write-Host "  Using JAVA_HOME: $env:JAVA_HOME" -ForegroundColor Green

# Verify cloudflared binary
$CloudflaredBin = Join-Path $ProjectRoot "bin\cloudflared.exe"
$CloudflaredLicense = Join-Path $ProjectRoot "bin\LICENSE-cloudflared.txt"
if (-not (Test-Path $CloudflaredBin) -or -not (Test-Path $CloudflaredLicense)) {
    Write-Host "  Downloading cloudflared.exe..." -ForegroundColor Yellow
    python "$ProjectRoot\scripts\download_cloudflared.py"
    if (-not (Test-Path $CloudflaredBin)) {
        throw "Failed to download cloudflared.exe."
    }
}
Write-Host "  cloudflared.exe verified at: $CloudflaredBin" -ForegroundColor Green

# Ensure output directory exists
$DistDir = Join-Path $ProjectRoot "dist"
if (-not (Test-Path $DistDir)) {
    New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
}

# ---------------------------------------------------------------------
# 2. Build Android Signed Release APK
# ---------------------------------------------------------------------
$ApkTarget = Join-Path $DistDir "TTL-Scanner-1.0.0.apk"

if ($SkipAndroidBuild -and (Test-Path $ApkTarget)) {
    Write-Host "`n[2/6] Skipping Android APK build (flag provided, using existing APK)..." -ForegroundColor DarkGray
} else {
    Write-Host "`n[2/6] Building signed Android Release APK..." -ForegroundColor Yellow
    Push-Location (Join-Path $ProjectRoot "android")
    try {
        & ".\gradlew.bat" assembleRelease
        if ($LASTEXITCODE -ne 0) {
            throw "Gradle assembleRelease failed with exit code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }

    $BuiltApk = Join-Path $ProjectRoot "android\app\build\outputs\apk\release\app-release.apk"
    if (-not (Test-Path $BuiltApk)) {
        throw "Expected release APK not found at: $BuiltApk"
    }

    Copy-Item $BuiltApk $ApkTarget -Force
}

$ApkHash = (Get-FileHash -Path $ApkTarget -Algorithm SHA256).Hash.ToLower()
$ApkItem = Get-Item $ApkTarget
$ApkSizeMb = [math]::Round($ApkItem.Length / 1MB, 1)
Write-Host "  Android APK: $ApkTarget ($ApkSizeMb MB)" -ForegroundColor Green
Write-Host "  SHA-256:     $ApkHash" -ForegroundColor Gray

# ---------------------------------------------------------------------
# 3. Build Windows PyInstaller Executable
# ---------------------------------------------------------------------
$WindowsStagingDir = Join-Path $DistDir "IssueSlipManager"
$WindowsZipTarget = Join-Path $DistDir "IssueSlipManager-v1.0.0-Windows-x64.zip"

if ($SkipPyInstaller -and (Test-Path "$WindowsStagingDir\IssueSlipManager.exe")) {
    Write-Host "`n[3/6] Skipping PyInstaller compilation (flag provided, using existing staging)..." -ForegroundColor DarkGray
} else {
    Write-Host "`n[3/6] Compiling Windows desktop application with PyInstaller..." -ForegroundColor Yellow
    
    if (Test-Path $WindowsStagingDir) {
        Remove-Item $WindowsStagingDir -Recurse -Force
    }
    
    Push-Location $ProjectRoot
    try {
        & pyinstaller --noconfirm "IssueSlipManager.spec"
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller build failed with exit code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }

    if (-not (Test-Path "$WindowsStagingDir\IssueSlipManager.exe")) {
        throw "IssueSlipManager.exe was not created in $WindowsStagingDir"
    }
}

# ---------------------------------------------------------------------
# 4. Bundle Required Binaries & Prepare Clean Data Directory
# ---------------------------------------------------------------------
Write-Host "`n[4/6] Bundling binaries & sanitizing distribution staging..." -ForegroundColor Yellow

# Copy cloudflared to staging bin/
$StagingBin = Join-Path $WindowsStagingDir "bin"
if (-not (Test-Path $StagingBin)) {
    New-Item -ItemType Directory -Path $StagingBin -Force | Out-Null
}
Copy-Item $CloudflaredBin (Join-Path $StagingBin "cloudflared.exe") -Force
Copy-Item $CloudflaredLicense (Join-Path $StagingBin "LICENSE-cloudflared.txt") -Force

# Prune unintended AI/scientific libraries bundled by global environment
$InternalDir = Join-Path $WindowsStagingDir "_internal"
$BloatedDirs = @("torch", "torchvision", "torchaudio", "transformers", "scipy", "scipy.libs", "sklearn", "matplotlib", "llvmlite", "pandas", "jedi")
foreach ($b in $BloatedDirs) {
    $targetBloat = Join-Path $InternalDir $b
    if (Test-Path $targetBloat) {
        Write-Host "  Pruning unneeded external library from staging: $b" -ForegroundColor DarkGray
        Remove-Item $targetBloat -Recurse -Force
    }
}

# Create freshly initialized clean SQLite database (0 user records)
$StagingData = Join-Path $WindowsStagingDir "data"
if (Test-Path $StagingData) {
    Remove-Item $StagingData -Recurse -Force
}
New-Item -ItemType Directory -Path $StagingData -Force | Out-Null

# Generate a pristine empty database with schemas 1, 2, 3 applied
$CleanDbPath = Join-Path $StagingData "issue_slip.db"
$InitScript = @"
import os
import sys
sys.path.insert(0, r'$ProjectRoot')
os.environ['ISSUE_SLIP_HOME'] = r'$WindowsStagingDir'
from app.core.database import initialize_database, get_db_cursor

initialize_database()

with get_db_cursor() as cursor:
    cursor.execute("SELECT count(*) as c FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchone()['c']
    cursor.execute("SELECT count(*) as c FROM materials;")
    materials = cursor.fetchone()['c']
    cursor.execute("SELECT count(*) as c FROM issue_slips;")
    slips = cursor.fetchone()['c']
    cursor.execute("SELECT count(*) as c FROM scan_events;")
    scans = cursor.fetchone()['c']

if materials != 0 or slips != 0 or scans != 0:
    raise RuntimeError(f"Sanitization failed: materials={materials}, slips={slips}, scans={scans}")
print(f"CLEAN_DB_SUCCESS: {tables} tables, 0 materials, 0 slips, 0 scans")
"@

$InitPy = [System.IO.Path]::GetTempFileName() + ".py"
Set-Content -Path $InitPy -Value $InitScript -Encoding UTF8
try {
    $dbInitOutput = python $InitPy
    Write-Host "  Database init: $dbInitOutput" -ForegroundColor Green
} finally {
    Remove-Item $InitPy -Force -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------------
# 5. Strict Cleanliness & Privacy Verification
# ---------------------------------------------------------------------
Write-Host "`n[5/6] Auditing distribution files for secrets, logs & private data..." -ForegroundColor Yellow

$ForbiddenPatterns = @("*.pem", "*.key", "*.log", "plant_inventory_master.json", "plant_qr_catalog.json")
$Violations = @()

foreach ($pattern in $ForbiddenPatterns) {
    $matches = Get-ChildItem -Path $WindowsStagingDir -Recurse -Filter $pattern -ErrorAction SilentlyContinue
    if ($matches) {
        foreach ($m in $matches) {
            if ($m.FullName -like "*_internal*certifi*cacert.pem") {
                continue
            }
            $Violations += $m.FullName
        }
    }
}

if ($Violations.Count -gt 0) {
    Write-Host "FATAL: Distribution contains unauthorized/private files:" -ForegroundColor Red
    $Violations | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    throw "Cleanliness audit failed: $Violations"
}
Write-Host "  Zero forbidden files detected (no certificates, keys, personal data, or logs)." -ForegroundColor Green

# Package portable ZIP using fast Python zip creator
if (Test-Path $WindowsZipTarget) {
    Remove-Item $WindowsZipTarget -Force
}
Write-Host "  Compressing $WindowsZipTarget using Python streaming engine..." -ForegroundColor Yellow
$ZipBase = $WindowsZipTarget -replace '\.zip$', ''
python -c "import shutil, sys; shutil.make_archive(sys.argv[1], 'zip', sys.argv[2])" "$ZipBase" "$WindowsStagingDir"
if (-not (Test-Path $WindowsZipTarget)) {
    throw "Failed to create ZIP at $WindowsZipTarget"
}

$ZipHash = (Get-FileHash -Path $WindowsZipTarget -Algorithm SHA256).Hash.ToLower()
$ZipItem = Get-Item $WindowsZipTarget
$ZipSizeMb = [math]::Round($ZipItem.Length / 1MB, 1)

Write-Host "  Windows ZIP: $WindowsZipTarget ($ZipSizeMb MB)" -ForegroundColor Green
Write-Host "  SHA-256:     $ZipHash" -ForegroundColor Gray

# ---------------------------------------------------------------------
# 6. Update Static Web releases.json Metadata
# ---------------------------------------------------------------------
Write-Host "`n[6/6] Updating web/releases.json metadata..." -ForegroundColor Yellow

$ReleasesJsonPath = Join-Path $ProjectRoot "web\releases.json"
$ReleaseDate = (Get-Date).ToString("yyyy-MM-dd")

$ReleasesData = [PSCustomObject]@{
    version = "1.0.0"
    releaseDate = $ReleaseDate
    githubRepo = "sameerrout/time"
    downloads = [PSCustomObject]@{
        android = [PSCustomObject]@{
            filename = "TTL-Scanner-1.0.0.apk"
            version = "1.0.0"
            platform = "Android 7.0+ (ARM64 / x86_64)"
            size = "$ApkSizeMb MB"
            sha256 = $ApkHash
            url = "https://github.com/sameerrout/time/releases/download/v1.0.0/TTL-Scanner-1.0.0.apk"
        }
        windows = [PSCustomObject]@{
            filename = "IssueSlipManager-v1.0.0-Windows-x64.zip"
            version = "1.0.0"
            platform = "Windows 10 / 11 (64-bit)"
            size = "$ZipSizeMb MB"
            sha256 = $ZipHash
            url = "https://github.com/sameerrout/time/releases/download/v1.0.0/IssueSlipManager-v1.0.0-Windows-x64.zip"
        }
    }
}

$ReleasesJsonContent = $ReleasesData | ConvertTo-Json -Depth 5
Set-Content -Path $ReleasesJsonPath -Value $ReleasesJsonContent -Encoding UTF8
Write-Host "  web/releases.json updated with calculated hashes and sizes." -ForegroundColor Green

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host " RELEASE BUILD COMPLETED SUCCESSFULLY" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Android APK:   $ApkTarget ($ApkSizeMb MB)" -ForegroundColor White
Write-Host "   SHA-256:     $ApkHash" -ForegroundColor Gray
Write-Host " Windows Zip:   $WindowsZipTarget ($ZipSizeMb MB)" -ForegroundColor White
Write-Host "   SHA-256:     $ZipHash" -ForegroundColor Gray
Write-Host " Web Releases:  $ReleasesJsonPath" -ForegroundColor White
Write-Host "==========================================================" -ForegroundColor Cyan
