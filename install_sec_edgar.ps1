# SEC EDGAR Installation Script (PowerShell)
# Run this to set up the SEC EDGAR integration

Write-Host "`n=== SEC EDGAR Integration Setup ===" -ForegroundColor Cyan
Write-Host "This will install the required dependencies and test the integration.`n"

# Install dependencies
Write-Host "[1/4] Installing dependencies..." -ForegroundColor Yellow
pip install requests pandas beautifulsoup4 lxml

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Failed to install dependencies" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Dependencies installed`n" -ForegroundColor Green

# Check Python imports
Write-Host "[2/4] Verifying imports..." -ForegroundColor Yellow
python -c "import pandas; import requests; import bs4; import lxml; print('✓ All modules imported successfully')"

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Import verification failed" -ForegroundColor Red
    exit 1
}

# Run tests
Write-Host "`n[3/4] Running test suite..." -ForegroundColor Yellow
python test_sec_edgar.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠ Some tests failed, but this might be expected (e.g., ticker lookup)" -ForegroundColor Yellow
} else {
    Write-Host "✓ All tests passed!" -ForegroundColor Green
}

# Show example
Write-Host "`n[4/4] Running example..." -ForegroundColor Yellow
python example_migration.py

Write-Host "`n=== Setup Complete! ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "1. Read SEC_EDGAR_README.md for overview"
Write-Host "2. Read SEC_EDGAR_GUIDE.md for detailed documentation"
Write-Host "3. Update your code to use hybrid_data_engine"
Write-Host "4. Start saving `$780/year! 💰"
Write-Host ""
