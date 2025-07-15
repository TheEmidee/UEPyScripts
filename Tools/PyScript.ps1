<#
.SYNOPSIS
    Runs one of the python module of the UEPyScripts package

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

.EXAMPLE
    PyScript.ps1 `
    -moduleName "uepyscripts.run.buildgraph" `
    -stringArguments "--target 'My Buildgraph Target' --verbose"

.EXAMPLE
    PyScript.ps1 `
    -moduleName "uepyscripts.run.buildgraph" `
    -arguments @{ target = "My Target" } `
    -stringArguments "--verbose --debug"
"@;
#>

[CmdletBinding()]
param (
    [string]$moduleName = "",
    [hashtable]$arguments = @{},
    [string]$stringArguments = "",
    [switch]$Help
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

function Convert-StringArgumentsToArray {
    param (
        [string]$stringArgs
    )
    
    if ([string]::IsNullOrWhiteSpace($stringArgs)) {
        return @()
    }
    
    # Simple parsing - splits on spaces but respects quoted strings
    $argArray = @()
    $matches = [regex]::Matches($stringArgs, '(?:"[^"]*"|''[^'']*''|[^\s]+)')
    
    foreach ($match in $matches) {
        $value = $match.Value
        # Remove outer quotes if present
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or 
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $argArray += $value
    }
    
    return $argArray
}

function Run-PythonModule {
    param (
        [string]$moduleName,
        [hashtable]$arguments,
        [string]$stringArguments
    )
    try {
        $argArray = @()
        if ($arguments.Count -gt 0) {
            $arguments.GetEnumerator() | ForEach-Object {
                $argArray += "--$($_.Key)"
                $argArray += $_.Value
            }
        }
        
        # Convert string arguments to array and merge
        if (-not [string]::IsNullOrWhiteSpace($stringArguments)) {
            $stringArgArray = Convert-StringArgumentsToArray -stringArgs $stringArguments
            $argArray += $stringArgArray
        }

        if ($argArray.Count -gt 0) {
            & python -m $moduleName $argArray
        } else {
            & python -m $moduleName
        }
    } catch {
        Write-Error "Failed to run Python module: $_"
        exit 1
    }
}

try {
    $packageRoot = (Join-Path $PSScriptRoot -ChildPath "../")
    Push-Location -Path $packageRoot

    Activate-VirtualEnvironment -venvPath ".venv\Scripts\Activate.ps1"
    Run-PythonModule -moduleName $moduleName -arguments $arguments -stringArguments $stringArguments
} finally {
    Pop-Location
}