# Get the directory where this script is located
$scriptDir = $PSScriptRoot

# Walk up the hierarchy to find the project root (directory containing .uproject file)
$projectRoot = $null
$currentDir = $scriptDir

while ($currentDir) {
    $uprojectFiles = Get-ChildItem -Path $currentDir -Filter "*.uproject" -File
    if ($uprojectFiles) {
        $projectRoot = $currentDir
        break
    }
    $parentDir = Split-Path -Parent $currentDir
    if ($parentDir -eq $currentDir) {
        # Reached the root of the filesystem
        break
    }
    $currentDir = $parentDir
}

if (-not $projectRoot) {
    Write-Error "Could not find project root. No .uproject file found in parent directories."
    exit 1
}

# Define the output file path
$outputFile = Join-Path -Path $projectRoot -ChildPath "Setup.ps1"

# Calculate the PyScripts folder location relative to project root
$pyScriptsFolder = $scriptDir | Resolve-Path -Relative -RelativeBasePath $projectRoot
# Remove leading .\ if present and normalize to forward slashes
$pyScriptsFolder = $pyScriptsFolder -replace '^\\.\\', '' -replace '\\', '/'

# Calculate relative paths from project root to the required scripts
$setupVenvPath = Split-Path -Parent $pyScriptsFolder
$setupVenvPath = "$setupVenvPath/setup_venv.ps1" -replace '\\', '/'

$setupContent = @"
try {
    .( Join-Path -Path `$PSScriptRoot -ChildPath "$pyScriptsFolder/InstallPython.ps1" )
    .( Join-Path -Path `$PSScriptRoot -ChildPath "$setupVenvPath" )
    .( Join-Path -Path `$PSScriptRoot -ChildPath "$pyScriptsFolder/PyScript.ps1" ) -moduleName "uepyscripts.tools.ue.check_engine_installation"
}
catch {
    Write-Error `$_.Exception.Message
}
"@

# Display what will be written
Write-Host "`nSetup.ps1 will be created at:" -ForegroundColor Cyan
Write-Host $outputFile -ForegroundColor Yellow
Write-Host "`nWith the following content:" -ForegroundColor Cyan
Write-Host $setupContent -ForegroundColor Gray

$confirmation = Read-Host "`nDo you want to proceed? (Y/N)"
if ($confirmation -ne 'Y' -and $confirmation -ne 'y') {
    Write-Host "Operation cancelled." -ForegroundColor Yellow
    exit
}

# Write the file
try {
    Set-Content -Path $outputFile -Value $setupContent -Encoding UTF8
    Write-Host "`nSetup.ps1 has been successfully created!" -ForegroundColor Green
    Write-Host "Location: $outputFile" -ForegroundColor Green
}
catch {
    Write-Error "Failed to create Setup.ps1: $_"
    exit 1
}

$compileAndRunEditorContent = @"
try {
    .( Join-Path -Path `$PSScriptRoot -ChildPath "$pyScriptsFolder/PyScript.ps1" ) -moduleName "uepyscripts.tools.ue.close_editor"
    .( Join-Path -Path `$PSScriptRoot -ChildPath "$pyScriptsFolder/PyScript.ps1" ) -moduleName "uepyscripts.tools.ue.compile_editor"
    .( Join-Path -Path `$PSScriptRoot -ChildPath "$pyScriptsFolder/PyScript.ps1" ) -moduleName "uepyscripts.tools.ue.run_editor"
}
catch {
    Write-Error `$_.Exception.Message
}
"@

$executeConfirmation = Read-Host "`nDo you want to create the CompileAndRunEditor.ps1 file? (Y/N)"
if ($executeConfirmation -eq 'Y' -or $executeConfirmation -eq 'y') {
    $compileAndRunEditorPath = Join-Path -Path $projectRoot -ChildPath "CompileAndRunEditor.ps1"
    Set-Content -Path $compileAndRunEditorPath -Value $compileAndRunEditorContent -Encoding UTF8
    Write-Host "`nCompileAndRunEditor.ps1 has been successfully created!" -ForegroundColor Green
    Write-Host "Location: $compileAndRunEditorPath" -ForegroundColor Green
}

$executeConfirmation = Read-Host "`nDo you want to execute Setup.ps1 now? (Y/N)"
if ($executeConfirmation -eq 'Y' -or $executeConfirmation -eq 'y') {
    Write-Host "`nExecuting Setup.ps1..." -ForegroundColor Cyan
    try {
        & $outputFile
    }
    catch {
        Write-Error "Failed to execute Setup.ps1: $_"
        exit 1
    }
}
else {
    Write-Host "Setup.ps1 was not executed. You can run it manually later." -ForegroundColor Yellow
}