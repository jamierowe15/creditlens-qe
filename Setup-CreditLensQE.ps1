<#
.SYNOPSIS
  One-click setup and full run of the CreditLens QE framework on Windows.

.DESCRIPTION
  1. Checks (and if needed installs) Git, Python 3.11+, JDK 21, Maven, Node.js
  2. Finds or clones the CreditLens repo next to this folder
  3. Creates the Python virtual environment, installs pytest/Playwright/Locust, the Chromium browser,
     and the Node tools (WireMock, axe-core)
  4. Starts CreditLens (API + UI) and the virtual environment (WireMock + UI)
  5. Runs every suite: smoke, api, bdd, security, ui, virtual, a11y, perf
  6. Opens the HTML report

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\Setup-CreditLensQE.ps1
.EXAMPLE
  .\Setup-CreditLensQE.ps1 -Headed               # watch the browser tests run (slowed down)
.EXAMPLE
  .\Setup-CreditLensQE.ps1 -Suite api            # just one suite
.EXAMPLE
  .\Setup-CreditLensQE.ps1 -CreditLensDir C:\dev\creditlens
.EXAMPLE
  .\Setup-CreditLensQE.ps1 -Publish              # also create github.com/jamierowe15/creditlens-qe and push
#>
param(
    [string]$CreditLensDir = "",
    [ValidateSet("all", "smoke", "api", "bdd", "security", "ui", "virtual", "a11y", "perf")]
    [string]$Suite = "all",
    [switch]$Headed,
    [switch]$SetupOnly,
    [switch]$Publish,
    [string]$GitHubUser = "jamierowe15"
)

# "Continue", not "Stop": Windows PowerShell 5.1 turns harmless stderr output from native tools
# (java -version, pip, npm) into terminating errors under "Stop". Native failures are caught by Check-Exit.
$ErrorActionPreference = "Continue"
$Root = $PSScriptRoot
Set-Location $Root
$Tools = Join-Path $Root ".tools"

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Ok($text)   { Write-Host "    OK  $text" -ForegroundColor Green }
function Warn($text) { Write-Host "    !!  $text" -ForegroundColor Yellow }
function Fail($text) { Write-Host "    XX  $text" -ForegroundColor Red; exit 1 }
function Have($cmd)  { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Check-Exit($what) { if ($LASTEXITCODE -ne 0) { Fail "$what failed (exit code $LASTEXITCODE)" } }

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user;$env:Path"
}

function Winget-Install($id, $label) {
    if (-not (Have "winget")) { Fail "$label is missing and winget is not available. Install $label manually, then re-run." }
    Warn "$label not found: installing with winget ($id)..."
    winget install --id $id -e --accept-source-agreements --accept-package-agreements --silent
    Refresh-Path
}

# ------------------------------------------------------------------------------------------
Step "Locating CreditLens"
if (-not $CreditLensDir) {
    $candidates = @((Join-Path (Split-Path $Root -Parent) "creditlens"), (Join-Path $HOME "creditlens"),
                    (Join-Path $HOME "Projects\creditlens"), (Join-Path $HOME "Documents\GitHub\creditlens"))
    $CreditLensDir = $candidates | Where-Object { Test-Path (Join-Path $_ "backend\pom.xml") } | Select-Object -First 1
    if (-not $CreditLensDir) { $CreditLensDir = $candidates[0] }
}
$CreditLensDir = [IO.Path]::GetFullPath($CreditLensDir)

# CreditLens' own setup script leaves the JDK / Maven / Node paths it used in .local-env.ps1
$localEnv = Join-Path $CreditLensDir ".local-env.ps1"
if (Test-Path $localEnv) { . $localEnv; Ok "loaded tool paths from $localEnv" }

# ------------------------------------------------------------------------------------------
Step "Checking prerequisites"
if (-not (Have "git")) { Winget-Install "Git.Git" "Git" }
Ok ("git    " + (git --version))

# Python: the lab's own .venv wins. Otherwise use the "py" launcher to pick 3.12 / 3.11 / 3.13.
# Bare "python" is avoided: on many PCs it is the Microsoft Store stub, or a brand-new version
# (3.14+) that the pinned test libraries do not support yet.
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
$py = $null; $pyArgs = @()
if (Test-Path $venvPy) {
    Ok ("python " + (& $venvPy --version) + " (existing .venv)")
} else {
    if (Have "py") {
        foreach ($v in @("3.12", "3.11", "3.13")) {
            & py "-$v" -c "print(1)" *> $null
            if ($LASTEXITCODE -eq 0) { $py = "py"; $pyArgs = @("-$v"); break }
        }
    }
    if (-not $py) {
        Winget-Install "Python.Python.3.12" "Python 3.12"
        $py = "py"; $pyArgs = @("-3.12")
    }
    Ok ("python " + (& $py @pyArgs --version))
}

$javaOk = $false
if (Have "java") { $javaOk = ((java -version 2>&1 | Out-String) -match 'version "2[1-9]') }
if (-not $javaOk) { Winget-Install "EclipseAdoptium.Temurin.21.JDK" "JDK 21" }
Ok ("java   " + ((java -version 2>&1 | Select-Object -First 1) -replace '^.*version ', ''))
if (-not $env:JAVA_HOME) {
    # Maven needs JAVA_HOME: derive it from wherever java.exe lives (...\jdk-21...\bin\java.exe)
    $env:JAVA_HOME = Split-Path (Split-Path (Get-Command java).Source -Parent) -Parent
}

if ($env:CREDITLENS_MVN -and (Test-Path $env:CREDITLENS_MVN)) {
    Ok "maven  $env:CREDITLENS_MVN"
} elseif (Have "mvn") {
    $env:CREDITLENS_MVN = (Get-Command mvn).Source
    Ok "maven  $env:CREDITLENS_MVN"
} else {
    $mvnVersion = "3.9.11"
    $mvnHome = Join-Path $Tools "apache-maven-$mvnVersion"
    if (-not (Test-Path $mvnHome)) {
        Warn "Maven not found: downloading a portable copy into .tools\"
        New-Item -ItemType Directory -Force $Tools | Out-Null
        $zip = Join-Path $Tools "maven.zip"
        Invoke-WebRequest "https://archive.apache.org/dist/maven/maven-3/$mvnVersion/binaries/apache-maven-$mvnVersion-bin.zip" -OutFile $zip -UseBasicParsing -ErrorAction Stop
        Expand-Archive $zip -DestinationPath $Tools -Force -ErrorAction Stop
        Remove-Item $zip
    }
    $env:Path = "$mvnHome\bin;$env:Path"
    $env:CREDITLENS_MVN = Join-Path $mvnHome "bin\mvn.cmd"
    Ok "maven  $env:CREDITLENS_MVN (portable)"
}

$nodeOk = $false
if (Have "node") { $nodeOk = ((node --version) -match '^v(2[2-9]|[3-9]\d)\.') }
if (-not $nodeOk) { Winget-Install "OpenJS.NodeJS.LTS" "Node.js 22+" }
Ok ("node   " + (node --version))

# ------------------------------------------------------------------------------------------
Step "System under test"
if (-not (Test-Path (Join-Path $CreditLensDir "backend\pom.xml"))) {
    Warn "CreditLens not found: cloning into $CreditLensDir"
    git clone "https://github.com/$GitHubUser/creditlens.git" $CreditLensDir
    Check-Exit "git clone"
}
Ok "CreditLens at $CreditLensDir"
$env:QE_SUT_DIR = $CreditLensDir

# ------------------------------------------------------------------------------------------
Step "Python virtual environment and test libraries"
if (-not (Test-Path $venvPy)) {
    & $py @pyArgs -m venv .venv
    Check-Exit "python -m venv"
}
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -r requirements.txt
Check-Exit "pip install"
Ok "pytest, pytest-bdd, Playwright, Locust, jsonschema installed"

& $venvPy -m playwright install chromium
Check-Exit "playwright install"
Ok "Chromium for Playwright installed"

Step "Node tools (WireMock, axe-core)"
if (Test-Path "package-lock.json") { npm ci --no-audit --no-fund } else { npm install --no-audit --no-fund }
Check-Exit "npm install"
Ok "WireMock and axe-core installed"

& $venvPy qe.py doctor

if ($SetupOnly) { Write-Host "`nSetup complete. Run everything with:  .\.venv\Scripts\python qe.py all" -ForegroundColor Green; exit 0 }

# ------------------------------------------------------------------------------------------
$headedArg = @()
if ($Headed) { $headedArg = @("--headed") }

if ($Suite -eq "all") {
    Step "Running the full QE pipeline (first run builds CreditLens, allow ~5 minutes)"
    & $venvPy qe.py all @headedArg
    $result = $LASTEXITCODE
} else {
    Step "Running suite '$Suite'"
    if ($Suite -eq "virtual") { & $venvPy qe.py virtual start } else { & $venvPy qe.py sut start }
    & $venvPy qe.py test $Suite @headedArg
    $result = $LASTEXITCODE
    & $venvPy qe.py report | Out-Null
    Warn "Servers left running for more test runs. Stop them with:  .\.venv\Scripts\python qe.py sut stop  (and: virtual stop)"
}

$index = Join-Path $Root "reports\index.html"
if (Test-Path $index) { Start-Process $index }
$trace = Join-Path $Root "reports\traceability.html"
if (Test-Path $trace) { Start-Process $trace }

# ------------------------------------------------------------------------------------------
if ($Publish) {
    Step "Publishing to GitHub"
    if (-not (Have "gh")) { Winget-Install "GitHub.cli" "GitHub CLI"; gh auth login }
    if (-not (Test-Path (Join-Path $Root ".git"))) {
        git init -b main | Out-Null
    }
    git add -A
    git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) { git commit -m "CreditLens QE framework: API, BDD, UI, virtualization, a11y, security and performance suites" | Out-Null }
    $exists = $false
    gh repo view "$GitHubUser/creditlens-qe" *> $null
    if ($LASTEXITCODE -eq 0) { $exists = $true }
    if ($exists) {
        if (-not (git remote | Select-String -Quiet "origin")) { git remote add origin "https://github.com/$GitHubUser/creditlens-qe.git" }
        git push -u origin main
    } else {
        gh repo create "$GitHubUser/creditlens-qe" --public --source . --push --description "Test automation framework for CreditLens: pytest, Playwright, pytest-bdd, WireMock, axe-core, Locust, GitHub Actions"
    }
    Check-Exit "publish"
    Ok "https://github.com/$GitHubUser/creditlens-qe  (the QE workflow starts automatically: check the Actions tab)"
}

if ($result -eq 0) { Write-Host "`nAll suites passed. Report: $index" -ForegroundColor Green }
else { Write-Host "`nSome tests failed. Open $index, then the suite report, to see why." -ForegroundColor Red }
exit $result
