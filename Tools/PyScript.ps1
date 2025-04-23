<#
.SYNOPSIS
    Runs one of the python module of the UEPyScripts package

.DESCRIPTION
    This script runs the LevelStatsCollector commandlet to process a map and generate
    metrics using a configurable grid system. It can adjust camera positions, heights,
    and rotation angles for screenshot capture.

.PARAMETER ModuleName
    Name of the module to execute

.PARAMETER Arguments
    Hashmap of the arguments to pass to the module0

.PARAMETER Help
    Displays this help message.

.EXAMPLE
    PyScript.ps1 `
    -moduleName "uepyscripts.run.buildgraph" `
    -arguments @{
        target = "My Buildgraph Target";
        properties = @"
        { 
        "TargetPlatforms" : "Win64",
        "TargetConfigurations" : "DebugGame",
        "With_Publish" : "True",
        "Skip_Test" : "True",
        "Skip_Validation_All" : "True"
        }
"@;
#>

[CmdletBinding()]
param (
    [string]$moduleName = "",
    [hashtable]$arguments = @{}
)

# If help is requested, show help and exit
if ($Help)
{
    Get-Help $MyInvocation.MyCommand.Path
    return
}

function Activate-VirtualEnvironment {
    param (
        [string]$venvPath
    )
    if (Test-Path $venvPath) {
        & $venvPath
    } else {
        Write-Error "Virtual environment activation script not found at $venvPath"
        exit 1
    }
}

function Run-PythonModule {
    param (
        [string]$moduleName,
        [hashtable]$arguments
    )
    try {
        $argArray = @()
        $arguments.GetEnumerator() | ForEach-Object {
            $argArray += "--$($_.Key)"
            $argArray += $_.Value
        }

        & python -m $moduleName $argArray
    } catch {
        Write-Error "Failed to run Python module: $_"
        exit 1
    }
}

try {
    $packageRoot = (Join-Path $PSScriptRoot -ChildPath "../")
    Push-Location -Path $packageRoot

    Activate-VirtualEnvironment -venvPath ".venv\Scripts\Activate.ps1"
    Run-PythonModule -moduleName $moduleName -argument $arguments
} finally {
    Pop-Location
}