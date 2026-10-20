[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$KubeConfig
)

# Crée les Secrets de MongoDB et RabbitMQ, et leurs copies dans les namespaces des applications.
# Ne crée que les Secrets manquants : un mot de passe existant n'est jamais régénéré.
# Quand un compte a deux Secrets (côté serveur et côté application), le mot de passe est lu
# dans le Secret serveur existant, pour que les deux restent identiques.
# Aucun mot de passe n'apparaît dans les arguments de commande, dans un fichier ou dans Git.

$ErrorActionPreference = 'Stop'

$producers = @('player', 'dungeon', 'combat', 'rewards')
$consumer = 'leaderboard'

function ConvertTo-Base64Utf8([string]$Value) {
    [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Value))
}

function ConvertFrom-Base64Utf8([string]$Value) {
    [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Value))
}

# 32 octets aléatoires en hexadécimal (64 caractères) : aucun caractère à échapper
# dans une URI MongoDB ni dans le JSON de l'API RabbitMQ.
function New-RandomPassword {
    $bytes = [byte[]]::new(32)
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    [Convert]::ToHexString($bytes).ToLowerInvariant()
}

function Invoke-KubectlJson([hashtable]$Manifest) {
    $Manifest | ConvertTo-Json -Depth 20 -Compress |
        kubectl --kubeconfig $KubeConfig apply -f - | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'kubectl apply failed.' }
}

function Get-SecretData([string]$Namespace, [string]$Name) {
    $json = & kubectl --kubeconfig $KubeConfig -n $Namespace get secret $Name --ignore-not-found -o json
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect secret $Namespace/$Name." }
    if (-not $json) { return $null }
    $data = @{}
    ($json | ConvertFrom-Json).data.PSObject.Properties | ForEach-Object {
        $data[$_.Name] = ConvertFrom-Base64Utf8 $_.Value
    }
    return $data
}

# Retourne le contenu du Secret ; le crée avec $Default s'il n'existe pas.
function Initialize-Secret([string]$Namespace, [string]$Name, [hashtable]$Default, [string]$Type = 'Opaque') {
    $existing = Get-SecretData $Namespace $Name
    if ($existing) {
        Write-Host "Secret $Namespace/$Name already exists, left unchanged."
        return $existing
    }
    $data = @{}
    foreach ($key in $Default.Keys) { $data[$key] = ConvertTo-Base64Utf8 $Default[$key] }
    Invoke-KubectlJson @{
        apiVersion = 'v1'
        kind = 'Secret'
        metadata = @{ name = $Name; namespace = $Namespace }
        type = $Type
        data = $data
    }
    return $Default
}

foreach ($namespace in @('mongodb', 'rabbitmq')) {
    Invoke-KubectlJson @{ apiVersion = 'v1'; kind = 'Namespace'; metadata = @{ name = $namespace } }
}

# --- MongoDB ---------------------------------------------------------------
Initialize-Secret 'mongodb' 'mongodb-root' @{ username = 'root'; password = (New-RandomPassword) } 'kubernetes.io/basic-auth' | Out-Null

$keyBytes = [byte[]]::new(756)
[Security.Cryptography.RandomNumberGenerator]::Fill($keyBytes)
Initialize-Secret 'mongodb' 'mongodb-keyfile' @{ keyfile = [Convert]::ToBase64String($keyBytes) } | Out-Null

$mongoUsers = Initialize-Secret 'mongodb' 'mongodb-users' @{
    'leaderboard' = (New-RandomPassword)
    'leaderboard-migrator' = (New-RandomPassword)
}

$mongoHost = 'mongodb.mongodb.svc.cluster.local:27017'
$mongoOptions = 'authSource=progression_lake&replicaSet=rs0'
Initialize-Secret $consumer 'leaderboard-mongodb' @{
    'connection-string' = "mongodb://leaderboard:$($mongoUsers['leaderboard'])@$mongoHost/progression_lake?$mongoOptions"
    'migration-connection-string' = "mongodb://leaderboard-migrator:$($mongoUsers['leaderboard-migrator'])@$mongoHost/progression_lake?$mongoOptions"
} | Out-Null

# --- RabbitMQ --------------------------------------------------------------
Initialize-Secret 'rabbitmq' 'rabbitmq-admin' @{ username = 'admin'; password = (New-RandomPassword) } 'kubernetes.io/basic-auth' | Out-Null

$rabbitDefaults = @{}
foreach ($user in @($consumer) + $producers) { $rabbitDefaults[$user] = New-RandomPassword }
$rabbitUsers = Initialize-Secret 'rabbitmq' 'rabbitmq-users' $rabbitDefaults

foreach ($user in @($consumer) + $producers) {
    if (-not $rabbitUsers[$user]) {
        throw "rabbitmq/rabbitmq-users has no key '$user': add it by hand, then run this script again."
    }
    # Même nom de Secret dans chaque namespace applicatif, comme db-credentials.
    Initialize-Secret $user 'rabbitmq-credentials' @{ username = $user; password = $rabbitUsers[$user] } 'kubernetes.io/basic-auth' | Out-Null
}

Write-Host 'MongoDB and RabbitMQ secrets are ready.'
