$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$trainingPython = Join-Path $env:LOCALAPPDATA 'Programs/Python/Python311/python.exe'
if (-not (Test-Path -LiteralPath $trainingPython)) {
    throw 'Python 3.11 was not found. Select your CUDA Python environment and run execute_notebook.py.'
}
& $trainingPython -u execute_notebook.py
if ($LASTEXITCODE -ne 0) { throw 'Training failed. Review notebook outputs for details.' }
