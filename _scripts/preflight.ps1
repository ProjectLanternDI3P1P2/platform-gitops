[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$kubectl = (Get-Command kubectl -ErrorAction Stop).Source
$roots = @('clusters/k3s', 'platform', 'platform/keycloak', 'bootstrap/argocd/k3s', 'bootstrap/argocd/review', 'overlays/platform-review', 'platform/traefik/k3s')
foreach ($path in $roots) {
    & $kubectl kustomize (Join-Path $root $path) | Out-Null
    if ($LASTEXITCODE) { throw "Invalid Kustomize configuration: $path" }
}
$activeFiles = @('platform/keycloak', 'platform/argocd/applications', 'bootstrap/argocd/platform', 'bootstrap/argocd/k3s', 'bootstrap/argocd/review', 'overlays/platform-review', 'platform/traefik/k3s') | ForEach-Object { Get-ChildItem (Join-Path $root $_) -Recurse -File }
$unresolved = $activeFiles | Select-String -Pattern 'REPLACE_[A-Z0-9_]+|__GIT_[A-Z_]+__'
if ($unresolved) { throw 'Unresolved configuration markers remain in active manifests.' }
Write-Host 'Active platform manifests render successfully. No cluster resources were changed.'
