[CmdletBinding()]
param(
    [string]$GitRepositoryUrl = "",
    [string]$GitRevision = "main",
    [string]$HelmImage = "alpine/helm:3.18.6"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

function Resolve-DockerDesktopTool {
    param(
        [Parameter(Mandatory)]
        [string]$Name
    )

    $command = Get-Command $Name -ErrorAction SilentlyContinue

    if ($command) {
        return $command.Source
    }

    $candidate = Join-Path `
        $env:ProgramFiles `
        "Docker\Docker\resources\bin\$Name.exe"

    if (Test-Path -LiteralPath $candidate) {
        return $candidate
    }

    throw "$Name was not found. Install Docker Desktop and restart the terminal."
}


# ---------------------------------------------------------------------------
# Kubernetes readiness
# ---------------------------------------------------------------------------

function Wait-DockerDesktopKubernetes {
    param(
        [int]$Attempts = 30,
        [int]$DelaySeconds = 5
    )

    Write-Host ""
    Write-Host "Checking Docker Desktop Kubernetes..." -ForegroundColor Cyan

    $contexts = @(& $kubectl config get-contexts -o name)

    if ($LASTEXITCODE -ne 0) {
        throw "Could not read Kubernetes contexts."
    }

    if ($contexts -notcontains "docker-desktop") {
        throw @"
Docker Desktop Kubernetes context 'docker-desktop' was not found.

Open Docker Desktop:
  Settings -> Kubernetes

Enable Kubernetes and wait until the cluster is created.
"@
    }

    & $kubectl config use-context docker-desktop | Out-Null

    if ($LASTEXITCODE -ne 0) {
        throw "Could not switch to the docker-desktop Kubernetes context."
    }

    $endpoint = & $kubectl config view `
        --minify `
        -o "jsonpath={.clusters[0].cluster.server}"

    Write-Host "Kubernetes endpoint: $endpoint"

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {

        $readyOutput = & $kubectl get --raw="/readyz" 2>$null

        if ($LASTEXITCODE -eq 0 -and $readyOutput -match "ok") {
            Write-Host "Docker Desktop Kubernetes is ready." -ForegroundColor Green
            return
        }

        Write-Host `
            "Kubernetes not ready ($attempt/$Attempts)..." `
            -ForegroundColor Yellow

        Start-Sleep -Seconds $DelaySeconds
    }

    Write-Host ""
    Write-Host "Kubernetes diagnostics:" -ForegroundColor Yellow

    & $kubectl cluster-info
    & $kubectl get nodes

    throw @"
Docker Desktop Kubernetes is not reachable.

Current endpoint:
  $endpoint

Try restarting/resetting Kubernetes from Docker Desktop:
  Docker Desktop -> Settings -> Kubernetes

Then run:
  kubectl config use-context docker-desktop
  kubectl get nodes
"@
}


# ---------------------------------------------------------------------------
# Generate kubeconfig usable from a Docker container
# ---------------------------------------------------------------------------

function New-HelmDockerKubeConfig {
    param(
        [Parameter(Mandatory)]
        [string]$OutputPath
    )

    Write-Host ""
    Write-Host "Generating Helm Docker kubeconfig..." -ForegroundColor Cyan

    $rawConfig = & $kubectl config view `
        --minify `
        --raw `
        -o json

    if ($LASTEXITCODE -ne 0) {
        throw "Could not read current Kubernetes configuration."
    }

    $config = $rawConfig | ConvertFrom-Json

    if (-not $config.clusters -or $config.clusters.Count -eq 0) {
        throw "No Kubernetes cluster was found in the kubeconfig."
    }

    $server = $config.clusters[0].cluster.server

    if ([string]::IsNullOrWhiteSpace($server)) {
        throw "Kubernetes API server URL was not found."
    }

    Write-Host "Host Kubernetes endpoint: $server"

    $uri = [Uri]$server

    $dockerServer = "https://host.docker.internal:$($uri.Port)"

    Write-Host "Helm container endpoint: $dockerServer"

    $config.clusters[0].cluster.server = $dockerServer

    # Docker Desktop certs are normally generated for localhost.
    # This kubeconfig is only used locally from the temporary Helm container.
    $config.clusters[0].cluster |
        Add-Member `
            -NotePropertyName "insecure-skip-tls-verify" `
            -NotePropertyValue $true `
            -Force

    if ($config.clusters[0].cluster.PSObject.Properties.Name -contains "certificate-authority-data") {
        $config.clusters[0].cluster.PSObject.Properties.Remove(
            "certificate-authority-data"
        )
    }

    if ($config.clusters[0].cluster.PSObject.Properties.Name -contains "certificate-authority") {
        $config.clusters[0].cluster.PSObject.Properties.Remove(
            "certificate-authority"
        )
    }

    $config |
        ConvertTo-Json -Depth 30 |
        Set-Content `
            -LiteralPath $OutputPath `
            -Encoding utf8

    Write-Host "Helm Docker kubeconfig generated." -ForegroundColor Green
}


# ---------------------------------------------------------------------------
# Helm
# ---------------------------------------------------------------------------

function Invoke-HelmContainer {
    param(
        [Parameter(
            ValueFromRemainingArguments = $true,
            Mandatory = $true
        )]
        [string[]]$Arguments
    )

    if (-not (Test-Path -LiteralPath $helmKubeConfig)) {
        throw "Helm kubeconfig was not generated: $helmKubeConfig"
    }

    $dockerArguments = @(
        "run",
        "--rm",

        "-v",
        "${helmKubeConfig}:/root/.kube/config:ro",

        "-v",
        "${root}:/workspace",

        "-v",
        "lantern-helm-config:/root/.config/helm",

        "-v",
        "lantern-helm-cache:/root/.cache/helm",

        "-v",
        "lantern-helm-data:/root/.local/share/helm",

        "-w",
        "/workspace",

        $HelmImage
    ) + $Arguments

    & $docker @dockerArguments

    if ($LASTEXITCODE -ne 0) {
        throw "The Helm command running in Docker failed."
    }
}


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

function New-SecretValue {

    $bytes = [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)

    return [Convert]::ToBase64String($bytes)
        .TrimEnd("=")
        .Replace("+", "-")
        .Replace("/", "_")
}


function Read-EnvFile {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    $values = [ordered]@{}

    if (-not (Test-Path -LiteralPath $Path)) {
        return $values
    }

    foreach ($line in Get-Content -LiteralPath $Path) {

        $trimmed = $line.Trim()

        if ([string]::IsNullOrWhiteSpace($trimmed)) {
            continue
        }

        if ($trimmed.StartsWith("#")) {
            continue
        }

        if ($trimmed -match '^\s*([^#][^=]*)=(.*)$') {

            $key = $matches[1].Trim()
            $value = $matches[2].Trim()

            $values[$key] = $value
        }
    }

    return $values
}


function Invoke-KubectlSecret {
    param(
        [Parameter(Mandatory)]
        [string]$Namespace,

        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string[]]$Literals
    )

    $arguments = @(
        "create",
        "secret",
        "generic",
        $Name,
        "-n",
        $Namespace
    )

    foreach ($literal in $Literals) {
        $arguments += "--from-literal=$literal"
    }

    $arguments += @(
        "--dry-run=client",
        "-o",
        "yaml"
    )

    $secretYaml = & $kubectl @arguments

    if ($LASTEXITCODE -ne 0) {
        throw "Could not generate Kubernetes secret $Namespace/$Name."
    }

    $secretYaml | & $kubectl apply -f -

    if ($LASTEXITCODE -ne 0) {
        throw "Could not create Kubernetes secret $Namespace/$Name."
    }
}


# ---------------------------------------------------------------------------
# HTTP readiness
# ---------------------------------------------------------------------------

function Wait-Http {
    param(
        [Parameter(Mandatory)]
        [string]$Url,

        [int]$Attempts = 60
    )

    Write-Host "Waiting for $Url ..."

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {

        try {

            $response = Invoke-WebRequest `
                -Uri $Url `
                -MaximumRedirection 5 `
                -TimeoutSec 10 `
                -SkipHttpErrorCheck

            $status = [int]$response.StatusCode

            if ($status -ge 200 -and $status -lt 400) {
                Write-Host "$Url is ready (HTTP $status)." -ForegroundColor Green
                return
            }

            Write-Host `
                "Waiting for service ($attempt/$Attempts): $Url - HTTP $status" `
                -ForegroundColor Yellow
        }
        catch {

            Write-Host `
                "Waiting for service ($attempt/$Attempts): $Url - $($_.Exception.Message)" `
                -ForegroundColor Yellow
        }

        Start-Sleep -Seconds 10
    }

    throw "The service did not become available: $Url"
}


# ---------------------------------------------------------------------------
# Docker Desktop CoreDNS
# ---------------------------------------------------------------------------

function Set-DockerDesktopCoreDnsRewrite {

    Write-Host ""
    Write-Host "Checking CoreDNS configuration..." -ForegroundColor Cyan

    $configMapJson = & $kubectl get `
        configmap `
        coredns `
        -n kube-system `
        -o json

    if ($LASTEXITCODE -ne 0) {
        throw "Could not read Docker Desktop CoreDNS configuration."
    }

    $configMap = $configMapJson | ConvertFrom-Json

    $rewrite =
        "rewrite name exact keycloak.localhost keycloak.platform.svc.cluster.local"

    if ($configMap.data.Corefile -match [regex]::Escape($rewrite)) {
        Write-Host "CoreDNS rewrite already configured."
        return
    }

    $pattern = '(?m)^(\.:53\s+\{\r?\n)'

    if ($configMap.data.Corefile -notmatch $pattern) {
        throw "Could not locate the CoreDNS server block."
    }

    $configMap.data.Corefile = $configMap.data.Corefile -replace `
        $pattern, `
        "`$1    $rewrite`n"

    $payload = @{
        data = @{
            Corefile = $configMap.data.Corefile
        }
    } | ConvertTo-Json -Depth 5 -Compress

    & $kubectl patch `
        configmap `
        coredns `
        -n kube-system `
        --type merge `
        --patch $payload |
        Out-Host

    if ($LASTEXITCODE -ne 0) {
        throw "Could not configure Docker Desktop CoreDNS."
    }

    & $kubectl rollout restart `
        deployment/coredns `
        -n kube-system |
        Out-Host

    if ($LASTEXITCODE -ne 0) {
        throw "Could not restart CoreDNS."
    }

    & $kubectl rollout status `
        deployment/coredns `
        -n kube-system `
        --timeout=180s |
        Out-Host

    if ($LASTEXITCODE -ne 0) {
        throw "CoreDNS did not become ready."
    }
}


# ===========================================================================
# START
# ===========================================================================

$docker = Resolve-DockerDesktopTool "docker"
$kubectl = Resolve-DockerDesktopTool "kubectl"


# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "Checking Docker Desktop..." -ForegroundColor Cyan

& $docker info *> $null

if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop is not running."
}

Write-Host "Docker Desktop is running." -ForegroundColor Green


# ---------------------------------------------------------------------------
# Kubernetes
# ---------------------------------------------------------------------------

Wait-DockerDesktopKubernetes


# ---------------------------------------------------------------------------
# Stop old k3d cluster if present
# ---------------------------------------------------------------------------

$legacyContainers = @(
    & $docker ps `
        -q `
        --filter "label=k3d.cluster=lantern-dev"
)

if ($legacyContainers.Count -gt 0) {

    Write-Host ""
    Write-Host `
        "Stopping the previous Lantern k3d cluster to release ports 80 and 443." `
        -ForegroundColor Yellow

    & $docker stop $legacyContainers | Out-Null

    if ($LASTEXITCODE -ne 0) {
        throw "Could not stop the previous development cluster containers."
    }
}


# ---------------------------------------------------------------------------
# Kubeconfig
# ---------------------------------------------------------------------------

$kubeConfig = if ($env:KUBECONFIG) {

    ($env:KUBECONFIG -split [IO.Path]::PathSeparator)[0]

}
else {

    Join-Path $env:USERPROFILE ".kube\config"
}

if (-not (Test-Path -LiteralPath $kubeConfig)) {
    throw "Docker Desktop kubeconfig was not found: $kubeConfig"
}


# ---------------------------------------------------------------------------
# Rendered files
# ---------------------------------------------------------------------------

$rendered = Join-Path $root ".rendered"

New-Item `
    -ItemType Directory `
    -Force `
    -Path $rendered |
    Out-Null


# ---------------------------------------------------------------------------
# Helm kubeconfig
# ---------------------------------------------------------------------------

$helmKubeConfig = Join-Path `
    $rendered `
    "helm-kubeconfig.json"

New-HelmDockerKubeConfig `
    -OutputPath $helmKubeConfig


# ---------------------------------------------------------------------------
# Test Helm -> Kubernetes
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "Testing Kubernetes access from Helm container..." -ForegroundColor Cyan

& $docker run `
    --rm `
    -v "${helmKubeConfig}:/root/.kube/config:ro" `
    $HelmImage `
    list `
    --all-namespaces

if ($LASTEXITCODE -ne 0) {
    throw @"
The Helm Docker container cannot reach Kubernetes.

kubectl works from Windows, but Helm cannot connect from Docker.

Expected Kubernetes hostname from Docker:
  host.docker.internal
"@
}

Write-Host "Helm container can reach Kubernetes." -ForegroundColor Green


# ---------------------------------------------------------------------------
# Traefik
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "Installing Traefik..." -ForegroundColor Cyan

Invoke-HelmContainer `
    repo `
    add `
    traefik `
    "https://traefik.github.io/charts" `
    --force-update

Invoke-HelmContainer `
    upgrade `
    --install `
    traefik `
    traefik/traefik `
    --version "41.6.0" `
    --namespace traefik `
    --create-namespace `
    --values "/workspace/platform/traefik/values-dev.yaml" `
    --wait `
    --timeout "10m"


# ---------------------------------------------------------------------------
# Development secrets
# ---------------------------------------------------------------------------

$secretPath = Join-Path $root ".dev-secrets.env"

$secrets = Read-EnvFile $secretPath

$secretNames = @(
    "KEYCLOAK_ADMIN_PASSWORD",
    "KEYCLOAK_DB_PASSWORD",
    "DEV_OPS_PASSWORD",
    "DEV_DEVELOPER_PASSWORD",
    "ARGOCD_OIDC_CLIENT_SECRET",
    "CISO_ASSISTANT_OIDC_CLIENT_SECRET",
    "CISO_ASSISTANT_DJANGO_SECRET"
)

foreach ($name in $secretNames) {

    if (
        -not $secrets.Contains($name) -or
        [string]::IsNullOrWhiteSpace($secrets[$name])
    ) {
        $secrets[$name] = New-SecretValue
    }
}

$lines = @(
    "# Local development secrets. Never commit this file."
)

foreach ($name in $secretNames) {
    $lines += "$name=$($secrets[$name])"
}

Set-Content `
    -LiteralPath $secretPath `
    -Value $lines `
    -Encoding utf8


# ---------------------------------------------------------------------------
# Kubernetes base
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "Applying Kubernetes development foundation..." -ForegroundColor Cyan

& $kubectl apply `
    -k `
    (Join-Path $root "clusters/dev") |
    Out-Host

if ($LASTEXITCODE -ne 0) {
    throw "The Kubernetes foundation could not be applied."
}


# ---------------------------------------------------------------------------
# CoreDNS
# ---------------------------------------------------------------------------

Set-DockerDesktopCoreDnsRewrite


# ---------------------------------------------------------------------------
# Keycloak secret
# ---------------------------------------------------------------------------

Invoke-KubectlSecret `
    "platform" `
    "keycloak-dev-secrets" `
    @(
        "admin-password=$($secrets["KEYCLOAK_ADMIN_PASSWORD"])",
        "database-password=$($secrets["KEYCLOAK_DB_PASSWORD"])",
        "dev-ops-password=$($secrets["DEV_OPS_PASSWORD"])",
        "dev-developer-password=$($secrets["DEV_DEVELOPER_PASSWORD"])",
        "argocd-oidc-client-secret=$($secrets["ARGOCD_OIDC_CLIENT_SECRET"])",
        "ciso-assistant-oidc-client-secret=$($secrets["CISO_ASSISTANT_OIDC_CLIENT_SECRET"])"
    )


# ---------------------------------------------------------------------------
# CISO Assistant secret
# ---------------------------------------------------------------------------

Invoke-KubectlSecret `
    "ciso-assistant" `
    "ciso-assistant-secrets" `
    @(
        "django-secret-key=$($secrets["CISO_ASSISTANT_DJANGO_SECRET"])"
    )


# ---------------------------------------------------------------------------
# Argo CD generated values
# ---------------------------------------------------------------------------

$argoSecretValues = Join-Path `
    $rendered `
    "argocd-secrets.yaml"

@"
configs:
  secret:
    extra:
      oidc.keycloak.clientSecret: "$($secrets["ARGOCD_OIDC_CLIENT_SECRET"])"
"@ |
Set-Content `
    -LiteralPath $argoSecretValues `
    -Encoding utf8


# ---------------------------------------------------------------------------
# Keycloak
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "Installing Keycloak..." -ForegroundColor Cyan

Invoke-HelmContainer `
    upgrade `
    --install `
    keycloak `
    "/workspace/charts/keycloak" `
    --namespace platform `
    --wait `
    --timeout "10m"


# ---------------------------------------------------------------------------
# Mailpit
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "Installing Mailpit..." -ForegroundColor Cyan

Invoke-HelmContainer `
    upgrade `
    --install `
    mailpit `
    "/workspace/charts/mailpit" `
    --namespace platform `
    --wait `
    --timeout "5m"


# ---------------------------------------------------------------------------
# Argo CD
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "Installing Argo CD..." -ForegroundColor Cyan

Invoke-HelmContainer `
    repo `
    add `
    argo `
    "https://argoproj.github.io/argo-helm" `
    --force-update

Invoke-HelmContainer `
    upgrade `
    --install `
    argocd `
    argo/argo-cd `
    --version "10.9.2" `
    --namespace argocd `
    --create-namespace `
    --values "/workspace/platform/argocd/values-dev.yaml" `
    --values "/workspace/.rendered/argocd-secrets.yaml" `
    --wait `
    --timeout "10m"


# ---------------------------------------------------------------------------
# CISO Assistant
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "Installing CISO Assistant..." -ForegroundColor Cyan

Invoke-HelmContainer `
    upgrade `
    --install `
    ciso-assistant `
    "oci://ghcr.io/intuitem/helm-charts/ce/ciso-assistant" `
    --version "0.11.5" `
    --namespace ciso-assistant `
    --create-namespace `
    --values "/workspace/platform/ciso-assistant/values-dev.yaml" `
    --wait `
    --timeout "15m"


# ---------------------------------------------------------------------------
# Service readiness
# ---------------------------------------------------------------------------

Wait-Http `
    "http://keycloak.localhost/realms/lantern-dev/.well-known/openid-configuration"

Wait-Http `
    "http://argocd.localhost"

Wait-Http `
    "http://ciso.localhost"

Wait-Http `
    "http://mail.localhost"


# ---------------------------------------------------------------------------
# Argo CD GitOps bootstrap
# ---------------------------------------------------------------------------

if (-not [string]::IsNullOrWhiteSpace($GitRepositoryUrl)) {

    Write-Host ""
    Write-Host "Bootstrapping Argo CD applications..." -ForegroundColor Cyan

    $bootstrapDir = Join-Path `
        $rendered `
        "bootstrap"

    New-Item `
        -ItemType Directory `
        -Force `
        -Path $bootstrapDir |
        Out-Null

    $bootstrapSources = @(
        (Join-Path $root "bootstrap/argocd/projects")
        (Join-Path $root "bootstrap/argocd/applications")
    )

    Get-ChildItem `
        -Path $bootstrapSources `
        -Filter "*.yaml" `
        -File |
        ForEach-Object {

            $content = Get-Content `
                -LiteralPath $_.FullName `
                -Raw

            $content = $content
                .Replace(
                    "__GIT_REPOSITORY_URL__",
                    $GitRepositoryUrl
                ) `
                .Replace(
                    "__GIT_REVISION__",
                    $GitRevision
                )

            Set-Content `
                -LiteralPath (Join-Path $bootstrapDir $_.Name) `
                -Value $content `
                -Encoding utf8
        }

    & $kubectl apply `
        -f $bootstrapDir |
        Out-Host

    if ($LASTEXITCODE -ne 0) {
        throw "Could not bootstrap Argo CD applications."
    }
}


# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host " Docker Desktop environment is ready" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
Write-Host ""

Write-Host "  Keycloak         http://keycloak.localhost"
Write-Host "  Argo CD          http://argocd.localhost"
Write-Host "  CISO Assistant   http://ciso.localhost"
Write-Host "  Development mail http://mail.localhost"

Write-Host ""
Write-Host "No tool other than Docker Desktop is required."
Write-Host "Helm runs inside Docker."
Write-Host ""
Write-Host "Local credentials:"
Write-Host "  $secretPath"