# This script sets up a Python virtual environment in the parent directory and installs dependencies from requirements.txt
$venvName = ".venv"
$venvPath = Join-Path -Path $PSScriptRoot -ChildPath $venvName

function Initialize-PythonVEnv
{
    Write-Host "Create python virtual environment in $($venvPath)"

    Push-Location $PSScriptRoot

    python -m venv $venvName

    Pop-Location

    if ( Test-Path -Path $venvPath ) {
        Write-Host "Python virtual environment '$($venvName)' has been created successfully." -ForegroundColor Green

        # Activate the virtual environment
        $activateScript = Join-Path -Path $venvPath -ChildPath "Scripts\Activate.ps1"
        & $activateScript

        # Upgrade pip to the latest version
        Write-Host "Upgrading pip to the latest version..."
        python -m pip install --upgrade pip

        # Install dependencies from requirements.txt
        $requirementsPath = Join-Path -Path $PsScriptRoot -ChildPath "requirements.txt"

        if ( Test-Path $requirementsPath ) {
            Write-Host "Installing dependencies from requirements.txt..."
            pip install -r $requirementsPath
        } else {
            Write-Host "requirements.txt not found."
        }

        Write-Host "Virtual environment setup complete."
    } else {
        throw "Failed to create the Python virtual environment."
    }
}

function Test-PythonVirtualEnvironment
{
    Write-Host "Check if the python virtual environment is setup..."

    if ( $false -eq ( Test-Path -Path $venvPath ) ) {
        Write-Warning "No Python virtual environment found in the working directory at $($venvPath)."
        
        Initialize-PythonVEnv
    } else {
        Write-Host "Python virtual environment found at $venvPath" -ForegroundColor Green
    }
}

Test-PythonVirtualEnvironment