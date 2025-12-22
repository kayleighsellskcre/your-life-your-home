# OpenAI API Key Setup Script for Windows PowerShell
# Run this script to set up your OpenAI API key

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "OpenAI API Key Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if .env file exists
if (Test-Path ".env") {
    Write-Host "✓ .env file found" -ForegroundColor Green
} else {
    Write-Host "Creating .env file..." -ForegroundColor Yellow
    New-Item -Path ".env" -ItemType File | Out-Null
    Write-Host "✓ .env file created" -ForegroundColor Green
}

Write-Host ""
Write-Host "Please enter your OpenAI API key:" -ForegroundColor Yellow
Write-Host "(You can get one from https://platform.openai.com/api-keys)" -ForegroundColor Gray
Write-Host ""
$apiKey = Read-Host "API Key" -AsSecureString
$apiKeyPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($apiKey))

if ($apiKeyPlain -match "^sk-") {
    # Check if OPENAI_API_KEY already exists in .env
    $envContent = Get-Content ".env" -ErrorAction SilentlyContinue
    $updated = $false
    $newContent = @()
    
    foreach ($line in $envContent) {
        if ($line -match "^OPENAI_API_KEY=") {
            $newContent += "OPENAI_API_KEY=$apiKeyPlain"
            $updated = $true
        } else {
            $newContent += $line
        }
    }
    
    if (-not $updated) {
        $newContent += "OPENAI_API_KEY=$apiKeyPlain"
    }
    
    $newContent | Set-Content ".env"
    
    Write-Host ""
    Write-Host "✓ API key saved to .env file" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. Install OpenAI library: pip install openai" -ForegroundColor White
    Write-Host "2. Restart your Flask app" -ForegroundColor White
    Write-Host "3. Test by clicking 'Refine' button on Feature Spotlight Cards" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "✗ Invalid API key format. Should start with 'sk-'" -ForegroundColor Red
    Write-Host ""
}

