# This script sets up a Python virtual environment in the parent directory and installs dependencies from requirements.txt

# Set the virtual environment directory path (parent folder)
$venvDir = Join-Path -Path $PsScriptRoot -ChildPath "../.venv"
$venvDir = [System.IO.Path]::GetFullPath( $venvDir )

# Check if Python is installed
try {
    python --version
} catch {
    Write-Host "Python is not installed. Please install Python and try again."
    exit
}

# Create virtual environment in the parent directory if it doesn't exist
if (-Not (Test-Path $venvDir)) {
    Write-Host "Creating virtual environment in parent directory..."
    python -m venv $venvDir
}

# Activate the virtual environment
$activateScript = Join-Path $venvDir "Scripts\Activate.ps1"
& $activateScript

# Upgrade pip to the latest version
Write-Host "Upgrading pip to the latest version..."
python -m pip install --upgrade pip

# Install dependencies from requirements.txt
$requirementsPath = Join-Path -Path $PsScriptRoot -ChildPath "requirements.txt"

if (Test-Path $requirementsPath) {
    Write-Host "Installing dependencies from requirements.txt..."
    pip install -r $requirementsPath
} else {
    Write-Host "requirements.txt not found."
}

Write-Host "Virtual environment setup complete."
