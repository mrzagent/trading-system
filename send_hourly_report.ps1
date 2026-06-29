#!/usr/bin/env powershell
# send_hourly_report.ps1 — Send Reuben's trading report to Telegram
# This script ensures the report is fresh before sending

$ReportFile = "D:\\dev\\trading\\.latest_report.txt"
$TradingDir = "D:\\dev\\trading"
$TelegramChatId = "8305325794"

# Get bot token from main .env file
$EnvFile = "C:\\Users\\mrztms\\.openclaw\\.env"
$BotToken = $null
$ChatId = $null
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^REUBEN_TELEGRAM_BOT_TOKEN=(.+)$') {
            $BotToken = $matches[1].Trim()
        }
        if ($_ -match '^TELEGRAM_CHAT_ID=(.+)$') {
            $ChatId = $matches[1].Trim()
        }
    }
}

# Override default chat ID if found in env
if ($ChatId) {
    $TelegramChatId = $ChatId
}

if (-not $BotToken) {
    Write-Error "TELEGRAM_BOT_TOKEN not found in .env file"
    exit 1
}

# Check if report exists and is fresh (< 10 minutes old)
$needsRefresh = $true
if (Test-Path $ReportFile) {
    $lastWrite = (Get-Item $ReportFile).LastWriteTime
    $age = [DateTime]::Now - $lastWrite
    if ($age.TotalMinutes -lt 10) {
        $needsRefresh = $false
        Write-Host "Report is fresh (age: $($age.TotalMinutes.ToString('F1')) min)"
    } else {
        Write-Host "Report is stale (age: $($age.TotalMinutes.ToString('F1')) min), refreshing..."
    }
} else {
    Write-Host "Report file not found, generating..."
}

# Generate report from orchestrator signals (not hardcoded strategy)
if ($needsRefresh) {
    Push-Location $TradingDir
    try {
        # Run Python and capture output, but ignore exit code (Python logging writes to stderr)
        $output = python generate_trading_report.py 2>&1
        # Check if report file was created/updated successfully
        if (Test-Path $ReportFile) {
            $lastWrite = (Get-Item $ReportFile).LastWriteTime
            $age = [DateTime]::Now - $lastWrite
            if ($age.TotalMinutes -lt 2) {
                Write-Host "Report generated successfully"
            } else {
                Write-Error "Report file not updated (age: $($age.TotalMinutes.ToString('F1')) min)"
                exit 1
            }
        } else {
            Write-Error "Report file not found after generation"
            exit 1
        }
    } finally {
        Pop-Location
    }
}

# Read and send report
if (-not (Test-Path $ReportFile)) {
    Write-Error "Report file still not found after refresh"
    exit 1
}

$report = Get-Content $ReportFile -Raw

# Send to Telegram
$uri = "https://api.telegram.org/bot$BotToken/sendMessage"

# Build JSON manually to avoid PowerShell object serialization issues
$bodyJson = "{`"chat_id`":`"$TelegramChatId`",`"text`":`"" + ($report -replace '"', '\"' -replace "`r`n", "\n" -replace "`n", "\n") + "`"}"

try {
    $response = Invoke-RestMethod -Uri $uri -Method POST -ContentType "application/json" -Body $bodyJson
    Write-Host "Report sent successfully to Telegram"
} catch {
    Write-Error "Failed to send to Telegram: $_"
    exit 1
}
