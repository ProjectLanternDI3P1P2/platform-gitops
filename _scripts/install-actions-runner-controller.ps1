[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$HelmPath,

    [string]$KubeConfig = $env:KUBECONFIG,

    [string]$GitHubAppId,

    [string]$GitHubAppInstallationId,

    [string]$GitHubAppPrivateKeyPath
)

$ErrorActionPreference = 'Stop'
$chartVersion = '0.14.2'
$controllerNamespace = 'arc-systems'
$runnerNamespace = 'arc-runners'
$githubSecretName = 'arc-github-app'
$root = Split-Path -Parent $PSScriptRoot
$platformPath = Join-Path $root 'platform\actions-runner-controller'

if (-not $KubeConfig) {
    throw 'KubeConfig is required. Set KUBECONFIG or pass -KubeConfig.'
}
if (-not (Test-Path -LiteralPath $HelmPath)) {
    throw "Helm was not found at: $HelmPath"
}

& kubectl --kubeconfig $KubeConfig apply -k $platformPath
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to apply ARC namespaces and network policy.'
}

$caValue = & kubectl --kubeconfig $KubeConfig -n harbor get secret harbor-ingress `
    -o 'jsonpath={.data.ca\.crt}'
if ($LASTEXITCODE -ne 0 -or -not $caValue) {
    throw 'Could not read the public Harbor CA from secret harbor/harbor-ingress.'
}

$temporaryCa = Join-Path ([IO.Path]::GetTempPath()) "lantern-harbor-ca-$([Guid]::NewGuid()).crt"
try {
    [IO.File]::WriteAllBytes(
        $temporaryCa,
        [Convert]::FromBase64String($caValue)
    )
    & kubectl --kubeconfig $KubeConfig -n $runnerNamespace create configmap harbor-ca `
        --from-file="ca.crt=$temporaryCa" --dry-run=client -o yaml |
        & kubectl --kubeconfig $KubeConfig apply -f -
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to create the public Harbor CA ConfigMap.'
    }
}
finally {
    Remove-Item -LiteralPath $temporaryCa -Force -ErrorAction SilentlyContinue
    Remove-Variable caValue -ErrorAction SilentlyContinue
}

& $HelmPath upgrade --install arc `
    'oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller' `
    --version $chartVersion `
    --kubeconfig $KubeConfig `
    --namespace $controllerNamespace `
    --values (Join-Path $platformPath 'values-controller.yaml') `
    --atomic --wait --timeout 10m
if ($LASTEXITCODE -ne 0) {
    throw 'ARC controller installation failed.'
}

$githubSecret = & kubectl --kubeconfig $KubeConfig -n $runnerNamespace get secret `
    $githubSecretName --ignore-not-found -o name
if (-not $githubSecret) {
    if (-not $GitHubAppId -or -not $GitHubAppInstallationId -or
        -not $GitHubAppPrivateKeyPath) {
        throw @"
ARC controller is installed, but the runner scale set needs a GitHub App.
Pass -GitHubAppId, -GitHubAppInstallationId and -GitHubAppPrivateKeyPath.
The private key content is read from the local file and is never printed.
"@
    }
    if (-not (Test-Path -LiteralPath $GitHubAppPrivateKeyPath)) {
        throw "GitHub App private key was not found: $GitHubAppPrivateKeyPath"
    }

    & kubectl --kubeconfig $KubeConfig -n $runnerNamespace create secret generic `
        $githubSecretName `
        --from-literal="github_app_id=$GitHubAppId" `
        --from-literal="github_app_installation_id=$GitHubAppInstallationId" `
        --from-file="github_app_private_key=$GitHubAppPrivateKeyPath"
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to create the GitHub App Kubernetes Secret.'
    }
}

& $HelmPath upgrade --install lantern-k3s-builders `
    'oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set' `
    --version $chartVersion `
    --kubeconfig $KubeConfig `
    --namespace $runnerNamespace `
    --values (Join-Path $platformPath 'values-runner-set.yaml') `
    --atomic --wait --timeout 10m
if ($LASTEXITCODE -ne 0) {
    throw 'ARC runner scale-set installation failed.'
}

& kubectl --kubeconfig $KubeConfig -n $controllerNamespace rollout status `
    deployment/arc-gha-rs-controller --timeout=300s
& kubectl --kubeconfig $KubeConfig -n $runnerNamespace get `
    autoscalingrunnerset,ephemeralrunnerset,pods
