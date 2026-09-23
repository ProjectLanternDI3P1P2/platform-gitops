#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HELM_IMAGE="${HELM_IMAGE:-alpine/helm:3.18.6}"
kubectl config use-context docker-desktop >/dev/null

helm_container() {
  docker run --rm \
    -v "$HOME/.kube:/root/.kube:ro" \
    -v "$ROOT:/workspace" \
    -v lantern-helm-config:/root/.config/helm \
    -v lantern-helm-cache:/root/.cache/helm \
    -v lantern-helm-data:/root/.local/share/helm \
    -w /workspace "$HELM_IMAGE" "$@"
}

helm_container uninstall ciso-assistant -n ciso-assistant --ignore-not-found
helm_container uninstall argocd -n argocd --ignore-not-found
helm_container uninstall mailpit -n platform --ignore-not-found
helm_container uninstall keycloak -n platform --ignore-not-found
helm_container uninstall traefik -n traefik --ignore-not-found

mkdir -p "$ROOT/.rendered"
COREFILE="$ROOT/.rendered/Corefile"
PATCHED_COREFILE="$ROOT/.rendered/Corefile.patched"
kubectl -n kube-system get configmap coredns -o jsonpath='{.data.Corefile}' > "$COREFILE"
if grep -q 'rewrite name exact keycloak.localhost keycloak.platform.svc.cluster.local' "$COREFILE"; then
  grep -v 'rewrite name exact keycloak.localhost keycloak.platform.svc.cluster.local' "$COREFILE" > "$PATCHED_COREFILE"
  kubectl -n kube-system create configmap coredns --from-file="Corefile=$PATCHED_COREFILE" --dry-run=client -o yaml | kubectl apply -f -
  kubectl -n kube-system rollout restart deployment/coredns
fi

echo "Applications were removed. The Docker Desktop cluster and persistent volumes were preserved."
