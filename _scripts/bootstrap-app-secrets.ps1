[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$KubeConfig
)

$ErrorActionPreference = 'Stop'

if (-not $env:HARBOR_PULL_USERNAME -or -not $env:HARBOR_PULL_TOKEN) {
    throw 'Set HARBOR_PULL_USERNAME and HARBOR_PULL_TOKEN to a read-only Harbor robot account.'
}

function ConvertTo-Base64Utf8([string]$Value) {
    [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Value))
}

function New-RandomPassword {
    $bytes = [byte[]]::new(32)
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    [Convert]::ToBase64String($bytes)
}

function Invoke-KubectlJson([hashtable]$Manifest) {
    $Manifest | ConvertTo-Json -Depth 20 -Compress |
        kubectl --kubeconfig $KubeConfig apply -f - | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw 'kubectl apply failed.'
    }
}

$namespaces = @('combat', 'dungeon', 'frontend-game', 'frontend-public', 'leaderboard', 'player', 'rewards')
$databaseNamespaces = @('combat', 'dungeon', 'leaderboard', 'rewards')

$auth = ConvertTo-Base64Utf8 "$($env:HARBOR_PULL_USERNAME):$($env:HARBOR_PULL_TOKEN)"
$dockerConfig = @{
    auths = @{
        'registry.lantern.diiage' = @{
            username = $env:HARBOR_PULL_USERNAME
            password = $env:HARBOR_PULL_TOKEN
            auth = $auth
        }
    }
} | ConvertTo-Json -Depth 10 -Compress

foreach ($namespace in $namespaces) {
    Invoke-KubectlJson @{
        apiVersion = 'v1'
        kind = 'Namespace'
        metadata = @{ name = $namespace }
    }

    # Always apply this Secret so a robot token rotation repairs every namespace.
    Invoke-KubectlJson @{
        apiVersion = 'v1'
        kind = 'Secret'
        metadata = @{ name = 'harbor-pull'; namespace = $namespace }
        type = 'kubernetes.io/dockerconfigjson'
        data = @{ '.dockerconfigjson' = ConvertTo-Base64Utf8 $dockerConfig }
    }
}

foreach ($namespace in $databaseNamespaces) {
    $existingDatabaseSecret = & kubectl --kubeconfig $KubeConfig -n $namespace get secret db-credentials --ignore-not-found -o name
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect database secret in namespace $namespace." }
    if (-not $existingDatabaseSecret) {
        Invoke-KubectlJson @{
            apiVersion = 'v1'
            kind = 'Secret'
            metadata = @{ name = 'db-credentials'; namespace = $namespace }
            type = 'Opaque'
            data = @{ password = ConvertTo-Base64Utf8 (New-RandomPassword) }
        }
    }
}

Write-Host 'Application namespaces, Harbor pull secrets, and missing database secrets are ready.'
