[CmdletBinding()]
param(
    [string]$KubeConfig = $env:KUBECONFIG,
    [string]$HelmPath = "helm",
    [string]$ChartReference = "harbor/harbor",
    [string]$Namespace = "harbor",
    [string]$ReleaseName = "harbor"
)

$ErrorActionPreference = "Stop"
$chartVersion = "1.19.2"
$root = Split-Path -Parent $PSScriptRoot
$namespaceManifest = Join-Path $root "platform\harbor\namespace.yaml"
$valuesFile = Join-Path $root "platform\harbor\values-k3s.yaml"

if (-not $KubeConfig) {
    throw "KubeConfig is required. Pass -KubeConfig or set KUBECONFIG."
}

if (-not (Test-Path -LiteralPath $KubeConfig)) {
    throw "Kubeconfig was not found: $KubeConfig"
}

function New-RandomText {
    param(
        [Parameter(Mandatory)]
        [int]$Length
    )

    $alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    $bytes = [byte[]]::new($Length)
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    $characters = for ($index = 0; $index -lt $Length; $index++) {
        $alphabet[$bytes[$index] % $alphabet.Length]
    }
    -join $characters
}

function ConvertFrom-SecretValue {
    param(
        [Parameter(Mandatory)]
        [string]$Value
    )

    [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Value))
}

& kubectl --kubeconfig $KubeConfig apply -f $namespaceManifest | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Could not apply the Harbor namespace."
}

& kubectl --kubeconfig $KubeConfig get secret harbor-bootstrap -n $Namespace `
    --request-timeout=10s *> $null

if ($LASTEXITCODE -ne 0) {
    $secretDocument = [ordered]@{
        apiVersion = "v1"
        kind = "Secret"
        metadata = [ordered]@{
            name = "harbor-bootstrap"
            namespace = $Namespace
        }
        type = "Opaque"
        stringData = [ordered]@{
            HARBOR_ADMIN_PASSWORD = New-RandomText -Length 32
            secretKey = New-RandomText -Length 16
            databasePassword = New-RandomText -Length 32
            registryPassword = New-RandomText -Length 32
        }
    }

    $secretDocument |
        ConvertTo-Json -Depth 8 -Compress |
        & kubectl --kubeconfig $KubeConfig apply -f - |
        Out-Host

    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the Harbor bootstrap Secret."
    }
}

$bootstrapSecret = & kubectl --kubeconfig $KubeConfig get secret harbor-bootstrap `
    -n $Namespace -o json |
    ConvertFrom-Json

$requiredKeys = @(
    "HARBOR_ADMIN_PASSWORD",
    "secretKey",
    "databasePassword",
    "registryPassword"
)

foreach ($requiredKey in $requiredKeys) {
    if (-not $bootstrapSecret.data.$requiredKey) {
        throw "The harbor-bootstrap Secret is missing key: $requiredKey"
    }
}

$secretValues = [ordered]@{
    database = [ordered]@{
        internal = [ordered]@{
            password = ConvertFrom-SecretValue $bootstrapSecret.data.databasePassword
        }
    }
    registry = [ordered]@{
        credentials = [ordered]@{
            password = ConvertFrom-SecretValue $bootstrapSecret.data.registryPassword
        }
    }
}

$chartVersionArguments = @()
if ($ChartReference -eq "harbor/harbor") {
    & $HelmPath repo add harbor https://helm.goharbor.io --force-update | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Could not configure the official Harbor Helm repository."
    }
    $chartVersionArguments = @("--version", $chartVersion)
}

$secretValues |
    ConvertTo-Json -Depth 8 -Compress |
    & $HelmPath upgrade --install $ReleaseName $ChartReference `
        @chartVersionArguments `
        --namespace $Namespace `
        --kubeconfig $KubeConfig `
        --values $valuesFile `
        --values - `
        --atomic `
        --wait `
        --timeout 20m `
        --history-max 10 |
    Out-Host

if ($LASTEXITCODE -ne 0) {
    throw "Harbor Helm deployment failed."
}

Write-Host "Harbor deployment completed." -ForegroundColor Green
Write-Host "The administrator password remains only in Secret harbor/harbor-bootstrap."
