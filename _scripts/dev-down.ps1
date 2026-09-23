[CmdletBinding()]
param([string]$HelmImage = "alpine/helm:3.18.6")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$kubectlCommand = Get-Command kubectl -ErrorAction SilentlyContinue
$docker = if ($dockerCommand) { $dockerCommand.Source } else { Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe" }
$kubectl = if ($kubectlCommand) { $kubectlCommand.Source } else { Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\kubectl.exe" }
if (-not (Test-Path -LiteralPath $docker) -or -not (Test-Path -LiteralPath $kubectl)) { throw "Docker Desktop was not found." }

& $kubectl config use-context docker-desktop | Out-Null
$kubeDirectory = Split-Path -Parent (Join-Path $env:USERPROFILE ".kube\config")
function Invoke-HelmContainer([string[]]$Arguments) {
    & $docker run --rm -v "${kubeDirectory}:/root/.kube:ro" -v "${root}:/workspace" -v "lantern-helm-config:/root/.config/helm" -v "lantern-helm-cache:/root/.cache/helm" -v "lantern-helm-data:/root/.local/share/helm" -w /workspace $HelmImage @Arguments
    if ($LASTEXITCODE -ne 0) { throw "The Helm command running in Docker failed." }
}

foreach ($release in @(
    @{Name="ciso-assistant"; Namespace="ciso-assistant"},
    @{Name="argocd"; Namespace="argocd"},
    @{Name="mailpit"; Namespace="platform"},
    @{Name="keycloak"; Namespace="platform"},
    @{Name="traefik"; Namespace="traefik"}
)) {
    Invoke-HelmContainer @("uninstall", $release.Name, "--namespace", $release.Namespace, "--ignore-not-found")
}

$configMap = (& $kubectl get configmap coredns -n kube-system -o json | ConvertFrom-Json)
$rewritePattern = '(?m)^\s*rewrite name exact keycloak\.localhost keycloak\.platform\.svc\.cluster\.local\r?\n'
if ($configMap.data.Corefile -match $rewritePattern) {
    $configMap.data.Corefile = $configMap.data.Corefile -replace $rewritePattern, ""
    $payload = @{data = @{Corefile = $configMap.data.Corefile}} | ConvertTo-Json -Depth 5 -Compress
    & $kubectl patch configmap coredns -n kube-system --type merge --patch $payload | Out-Host
    & $kubectl rollout restart deployment/coredns -n kube-system | Out-Host
}

Write-Host "Applications were removed. The Docker Desktop cluster and persistent volumes were preserved."

