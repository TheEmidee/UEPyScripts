$requiredVersionNumber = [version] "3.12"

function Install-Python
{
    
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
            $promptInstall = ($requiredVersionNumber -ge $currentVersionNumber)
        } catch {
            $promptInstall = $true
        }

        if ( $promptInstall ) {
            Write-Warning "The installed python version is not compatible. You must install Python $($requiredVersionNumber)"
            $choice = Read-Host "Do you want to install this version now? (Y/N)"
    
            # Check the user's response
            if ( $choice -eq "Y" -or $choice -eq "y" ) {
                winget install python.python.3.12
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