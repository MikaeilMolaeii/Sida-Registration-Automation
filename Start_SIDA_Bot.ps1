$ErrorActionPreference = "Stop"

$projectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExecutable = Join-Path $projectDirectory ".venv\Scripts\python.exe"
$mainScript = Join-Path $projectDirectory "main.py"
$inputWorkbook = Join-Path $projectDirectory "data\students.xlsx"

function Wait-ForUser([string]$message) {
    Write-Host ""
    [void](Read-Host $message)
}

Write-Host "SIDA Automation"
Write-Host "---------------"

$alreadyRunning = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -and
        $_.CommandLine -match "main\.py" -and
        $_.CommandLine -match "--run-batch"
    } |
    Select-Object -First 1

if ($alreadyRunning) {
    Write-Host "The SIDA bot is already running and waiting for your CAPTCHA/Search action."
    Wait-ForUser "Press Enter to close this window"
    exit 0
}

if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    Write-Host "Bot Python environment was not found: $pythonExecutable" -ForegroundColor Red
    Wait-ForUser "Press Enter to close this window"
    exit 1
}

if (-not (Test-Path -LiteralPath $inputWorkbook)) {
    Write-Host "Student workbook was not found: $inputWorkbook" -ForegroundColor Red
    Wait-ForUser "Press Enter to close this window"
    exit 1
}

$chromeConnected = $false
try {
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:9222/json/version" -TimeoutSec 3
    $chromeConnected = $true
} catch {
    $chromeConnected = $false
}

if (-not $chromeConnected) {
    $chromeCandidates = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    $chromeExecutable = $chromeCandidates |
        Where-Object { Test-Path -LiteralPath $_ } |
        Select-Object -First 1

    if (-not $chromeExecutable) {
        Write-Host "Google Chrome was not found." -ForegroundColor Red
        Write-Host "Open the SIDA Chrome profile with remote debugging on port 9222, then try again."
        Wait-ForUser "Press Enter to close this window"
        exit 1
    }

    Write-Host "Opening the dedicated SIDA Chrome profile..."
    Start-Process -FilePath $chromeExecutable -ArgumentList @(
        "--remote-debugging-port=9222",
        "--user-data-dir=C:\SIDA-Chrome-Profile",
        "https://sida.medu.ir"
    )

    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
        try {
            $null = Invoke-RestMethod -Uri "http://127.0.0.1:9222/json/version" -TimeoutSec 2
            $chromeConnected = $true
            break
        } catch {
            $chromeConnected = $false
        }
    }

    if (-not $chromeConnected) {
        Write-Host "Chrome did not enable the debugging connection on port 9222." -ForegroundColor Red
        Wait-ForUser "Press Enter to close this window"
        exit 1
    }

    Write-Host "Log in to SIDA in the opened Chrome window."
    Wait-ForUser "After SIDA is ready, press Enter to start the bot"
}

Set-Location -LiteralPath $projectDirectory
Write-Host "Starting the bot. Enter each CAPTCHA in Chrome and click Search."
Write-Host "Keep this window open until the bot finishes."
Write-Host ""

& $pythonExecutable -B $mainScript --input $inputWorkbook --run-batch
$botExitCode = $LASTEXITCODE

if ($botExitCode -eq 0) {
    Write-Host ""
    Write-Host "The bot finished successfully." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "The bot stopped with an error. Exit code: $botExitCode" -ForegroundColor Red
    Write-Host "You can run this launcher again after checking Chrome and the Excel file."
}

Wait-ForUser "Press Enter to close this window"
exit $botExitCode
