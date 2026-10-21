[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$kubectl = (Get-Command kubectl -ErrorAction Stop).Source
$roots = @('clusters/k3s', 'platform', 'platform/keycloak', 'bootstrap/argocd/k3s', 'bootstrap/argocd/platform', 'platform/traefik/k3s')
foreach ($path in $roots) {
    & $kubectl kustomize (Join-Path $root $path) | Out-Null
    if ($LASTEXITCODE) { throw "Invalid Kustomize configuration: $path" }
}
$activeFiles = @('platform/keycloak', 'platform/argocd/applications', 'bootstrap/argocd/platform', 'bootstrap/argocd/k3s', 'platform/traefik/k3s') | ForEach-Object { Get-ChildItem (Join-Path $root $_) -Recurse -File }
$unresolved = $activeFiles | Select-String -Pattern 'REPLACE_[A-Z0-9_]+|__GIT_[A-Z_]+__'
if ($unresolved) { throw 'Unresolved configuration markers remain in active manifests.' }
$valueReferences = Get-ChildItem (Join-Path $root 'platform/argocd/applications') -Filter '*.yaml' | Select-String -Pattern '\$values/([A-Za-z0-9_./-]+)' -AllMatches
foreach ($reference in $valueReferences) {
    foreach ($match in $reference.Matches) {
        $path = Join-Path $root $match.Groups[1].Value
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing Helm values file: $path" }
    }
}
Write-Host 'Active platform manifests render successfully. No cluster resources were changed.'
