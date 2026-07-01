# Substitutes CLOUD_HOST / MTX_SRTPUBLISHPASS from .env.edge into
# edge/mediamtx.edge.yml, writing edge/mediamtx.edge.generated.yml.
# Called by start_edge.bat — not meant to be run standalone.
param(
    [string]$EnvFile = ".env.edge",
    [string]$Template = "edge\mediamtx.edge.yml",
    [string]$OutFile = "edge\mediamtx.edge.generated.yml"
)

$envVars = @{}
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') {
        $envVars[$matches[1]] = $matches[2]
    }
}

if (-not $envVars.ContainsKey('CLOUD_HOST') -or [string]::IsNullOrWhiteSpace($envVars['CLOUD_HOST'])) {
    Write-Error "CLOUD_HOST is not set in $EnvFile"
    exit 1
}
if (-not $envVars.ContainsKey('MTX_SRTPUBLISHPASS') -or [string]::IsNullOrWhiteSpace($envVars['MTX_SRTPUBLISHPASS'])) {
    Write-Error "MTX_SRTPUBLISHPASS is not set in $EnvFile"
    exit 1
}

(Get-Content $Template -Raw) `
    -replace '%CLOUD_HOST%', $envVars['CLOUD_HOST'] `
    -replace '%MTX_SRTPUBLISHPASS%', $envVars['MTX_SRTPUBLISHPASS'] |
    Set-Content -NoNewline -Encoding utf8 $OutFile

Write-Host "[OK] Generated $OutFile"
