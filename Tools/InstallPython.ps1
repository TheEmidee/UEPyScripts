$requiredVersionNumber = [version] "3.12.10"

function Install-Python
{
    $pythonUrl = "https://www.python.org/ftp/python/$requiredVersionNumber/python-$requiredVersionNumber-amd64.exe"
    $installerPath = "$env:TEMP\python-$requiredVersionNumber-installer.exe"

    Write-Host "Downloading Python $requiredVersionNumber..." -ForegroundColor Green

    try {
        Invoke-WebRequest -Uri $pythonUrl -OutFile $installerPath
        Write-Host "Download completed!" -ForegroundColor Green
    } catch {
        Write-Host "Error downloading Python installer: $_" -ForegroundColor Red
        exit 1
    }

    Write-Host "Installing Python $requiredVersionNumber..." -ForegroundColor Green

    # Install Python silently with options:
    # - /quiet: Silent installation
    # - InstallAllUsers=1: Install for all users (requires admin)
    # - PrependPath=1: Add Python to PATH
    # - Include_test=0: Don't install test suite
    # - Include_pip=1: Install pip
    $installArgs = "/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1"

    try {
        Start-Process -FilePath $installerPath -ArgumentList $installArgs -Wait
        Write-Host "Python $requiredVersionNumber installed successfully!" -ForegroundColor Green
    } catch {
        Write-Host "Error installing Python: $_" -ForegroundColor Red
        exit 1
    }

    # Clean up installer
    Remove-Item $installerPath -Force
    Write-Host "Installer cleaned up." -ForegroundColor Green

}

function Test-PythonInstallation
{
    Write-Host "Check if python is installed..."

    $pythonPath = Get-Command python -ErrorAction SilentlyContinue

    if ($pythonPath) {
        # Get the Python version
        $pythonVersion = & $pythonPath.Source --version

        if ( $null -eq $pythonVersion ) {
            $pythonVersion = ""
        }

        # Extract just the version number
        $pythonVersionStr = $pythonVersion -replace "Python ", ""

        $promptInstall = $False

        try {
            $currentVersionNumber = [version]$pythonVersionStr
            $promptInstall = ($requiredVersionNumber -gt $currentVersionNumber)
        } catch {
            $promptInstall = $true
        }

        if ( $promptInstall ) {
            Write-Warning "The installed python version is not compatible. Current version is $currentVersionNumber. Required version is $($requiredVersionNumber)"
            $choice = Read-Host "Do you want to install this version now? (Y/N)"
    
            # Check the user's response
            if ( $choice -eq "Y" -or $choice -eq "y" ) {
                Install-Python
            }
            else {
                throw "Python is not installed."
            }
        } else {
            # Output the installation path and version number
            Write-Host "Python is installed at: $($pythonPath.Source)" -ForegroundColor Green
            Write-Host "Python version: $currentVersionNumber" -ForegroundColor Green
        }

    } else {
        throw "Python is not installed."
    }
}

Test-PythonInstallation