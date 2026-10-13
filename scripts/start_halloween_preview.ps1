$ErrorActionPreference = 'Stop'
$previewRoot = Split-Path -Parent $PSScriptRoot
$previewPython = Join-Path $previewRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $previewPython)) { throw 'Instala as dependências num .venv antes de arrancar a pré-visualização.' }
$previewFolder = Join-Path $previewRoot '.local/halloween'
New-Item -ItemType Directory -Force -Path $previewFolder | Out-Null
$env:DATABASE_URL = 'sqlite:///' + (Join-Path $previewFolder 'preview.db').Replace('\', '/')
# Explicit SQLite URL takes priority over .env. This process never uses the production database.
Push-Location (Join-Path $previewRoot 'backend')
try {
    & $previewPython -c 'from app.db import Base,engine; from app import models; Base.metadata.create_all(engine)'
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível preparar a base de dados local.' }
    Write-Host 'Pré-visualização: http://127.0.0.1:8013/preview?theme=halloween'
    & $previewPython -m uvicorn app.main:app --host 127.0.0.1 --port 8013
} finally { Pop-Location }
