[CmdletBinding()]
param([string]$HelmImage = "alpine/helm:3.18.6")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$kubectlCommand = Get-Command kubectl -ErrorAction SilentlyContinue
$docker = if ($dockerCommand) { $dockerCommand.Source } else { Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe" }
$kubectl = if ($kubectlCommand) { $kubectlCommand.Source } else { Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\kubectl.exe" }
if (-not (Test-Path -LiteralPath $docker) -or -not (Test-Path -LiteralPath $kubectl)) { throw "Docker Desktop was not found." }

$productionFiles = @(
    "charts/keycloak/values-prod.yaml",
    "charts/mailpit/values-prod.yaml",
    "platform/argocd/values-prod.yaml",
    "platform/ciso-assistant/values-prod.yaml",
    "bootstrap/argocd/production/*.yaml"
)
$unresolved = Get-ChildItem $productionFiles | Select-String -Pattern 'REPLACE_[A-Z0-9_]+' -AllMatches
if ($unresolved) {
    Write-Host "Unresolved production values remain in:"
    $unresolved.Path | Sort-Object -Unique | ForEach-Object { Write-Host "  $_" }
    throw "Replace all REPLACE_* markers before production deployment."
}

& $docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop is not running." }
$kubeDirectory = Split-Path -Parent (Join-Path $env:USERPROFILE ".kube\config")
function Invoke-HelmContainer([string[]]$Arguments) {
    & $docker run --rm -v "${kubeDirectory}:/root/.kube:ro" -v "${root}:/workspace" -v "lantern-helm-config:/root/.config/helm" -v "lantern-helm-cache:/root/.cache/helm" -v "lantern-helm-data:/root/.local/share/helm" -w /workspace $HelmImage @Arguments
    if ($LASTEXITCODE -ne 0) { throw "The Helm validation command failed." }
}

Invoke-HelmContainer @("lint", "/workspace/charts/keycloak", "--values", "/workspace/charts/keycloak/values-prod.yaml")
Invoke-HelmContainer @("lint", "/workspace/charts/mailpit", "--values", "/workspace/charts/mailpit/values-prod.yaml")
Invoke-HelmContainer @("repo", "add", "traefik", "https://traefik.github.io/charts", "--force-update")
Invoke-HelmContainer @("template", "traefik", "traefik/traefik", "--version", "41.6.0", "--namespace", "traefik", "--values", "/workspace/platform/traefik/values-prod.yaml") | Out-Null
Invoke-HelmContainer @("repo", "add", "argo", "https://argoproj.github.io/argo-helm", "--force-update")
Invoke-HelmContainer @("template", "argocd", "argo/argo-cd", "--version", "10.9.2", "--namespace", "argocd", "--values", "/workspace/platform/argocd/values-prod.yaml") | Out-Null
Invoke-HelmContainer @("template", "ciso-assistant", "oci://ghcr.io/intuitem/helm-charts/ce/ciso-assistant", "--version", "0.11.5", "--namespace", "ciso-assistant", "--values", "/workspace/platform/ciso-assistant/values-prod.yaml") | Out-Null
& $kubectl kustomize (Join-Path $root "clusters/prod") | Out-Null
if ($LASTEXITCODE -ne 0) { throw "The production Kustomize overlay is invalid." }

Write-Host "Production manifests are syntactically valid and contain no unresolved placeholders."
