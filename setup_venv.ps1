# PowerShell script to set up Python virtual environment and install requirements
# Usage: .\setup-env.ps1

param(
    [string]$VenvName = ".venv",
    [string]$PyProjectFile = "pyproject.toml",
    [switch]$Force
)

Write-Host "Setting up Python virtual environment..." -ForegroundColor Green

# Save current location and move to script root
Push-Location $PSScriptRoot

try {
    # Check if Python is installed
    try {
        $pythonVersion = python --version 2>&1
        Write-Host "Found Python: $pythonVersion" -ForegroundColor Yellow
    } catch {
        Write-Host "Error: Python is not installed or not in PATH" -ForegroundColor Red
        return # Use return instead of exit to ensure 'finally' runs
    }

    # Check if requirements.txt exists
    if (!(Test-Path $PyProjectFile)) {
        Write-Host "Warning: $PyProjectFile not found in current directory" -ForegroundColor Yellow
        $response = Read-Host "Continue without installing requirements? (y/n)"
        if ($response -ne "y" -and $response -ne "Y") {
            return
        }
    }

    # Function to get file hash
    function Get-FileHashString {
        param([string]$FilePath)
        if (Test-Path $FilePath) {
            $hash = Get-FileHash -Path $FilePath -Algorithm SHA256
            return $hash.Hash
        }
        return $null
    }

    # Hash tracking file
    $hashFile = ".\$VenvName\.requirements_hash"

    # Get current hash of pyproject.toml
    $currentHash = Get-FileHashString -FilePath $PyProjectFile

    # Get stored hash if it exists
    $storedHash = $null
    if (Test-Path $hashFile) {
        $storedHash = Get-Content $hashFile -Raw
    }

    # Check if requirements have changed
    $requirementsChanged = ($currentHash -ne $storedHash) -or $Force

    # Remove existing virtual environment if Force flag is used
    if ($Force -and (Test-Path $VenvName)) {
        Write-Host "Removing existing virtual environment..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force $VenvName
    }

    # Create virtual environment if it doesn't exist
    if (!(Test-Path $VenvName)) {
        Write-Host "Creating virtual environment '$VenvName'..." -ForegroundColor Yellow
        python -m venv $VenvName
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Error: Failed to create virtual environment" -ForegroundColor Red
            return
        }
        Write-Host "Virtual environment created successfully!" -ForegroundColor Green
        $requirementsChanged = $true  # Force install on new venv
    } else {
        Write-Host "Virtual environment '$VenvName' already exists" -ForegroundColor Yellow
    }

    # Activate virtual environment
    Write-Host "Activating virtual environment..." -ForegroundColor Yellow
    & ".\$VenvName\Scripts\Activate.ps1"

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to activate virtual environment" -ForegroundColor Red
        return
    }

    # Upgrade pip
    Write-Host "Upgrading pip..." -ForegroundColor Yellow
    python -m pip install --upgrade pip

    # Install requirements only if they changed
    if (Test-Path $PyProjectFile) {
        if ($requirementsChanged) {
            Write-Host "Requirements have changed. Installing packages from $PyProjectFile..." -ForegroundColor Yellow
            pip install -e .[dev]
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host "All packages installed successfully!" -ForegroundColor Green
                # Store the new hash
                $currentHash | Out-File -FilePath $hashFile -NoNewline
            } else {
                Write-Host "Error: Some packages failed to install" -ForegroundColor Red
            }
        } else {
            Write-Host "Requirements unchanged - skipping package installation" -ForegroundColor Cyan
        }
    } else {
        Write-Host "Skipping package installation - no requirements file found" -ForegroundColor Yellow
    }

    Write-Host "`nSetup complete!" -ForegroundColor Green
    Write-Host "Virtual environment is now active." -ForegroundColor Green
    Write-Host "To deactivate later, run: deactivate" -ForegroundColor Cyan
    Write-Host "To activate again, run: .\$VenvName\Scripts\Activate.ps1" -ForegroundColor Cyan

} finally {
    # This block runs no matter what happens in the 'try' block
    Pop-Location
    Write-Host "`nReturned to original directory." -ForegroundColor Gray
}