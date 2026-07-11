#!/usr/bin/env pwsh
# Start the dashboard via Docker Compose using tokens from the local .env file.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Test-Path ".env")) {
  if (Test-Path ".env.example") {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Add tokens in the UI or edit the file."
  } else {
    Write-Error @"
Missing .env file in the repository root.

Create it and add your API tokens:

  New-Item .env
  # set TINKOFF_TOKEN= and TWELVEDATA_TOKEN=

CI/CD still uses GitHub repository secrets (see .github/workflows/ci.yml).
"@
    exit 1
  }
}

docker compose up @args
