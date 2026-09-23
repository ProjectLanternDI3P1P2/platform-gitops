#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HELM_IMAGE="${HELM_IMAGE:-alpine/helm:3.18.6}"
GIT_REPOSITORY_URL="${GIT_REPOSITORY_URL:-}"
GIT_REVISION="${GIT_REVISION:-main}"
SECRETS_FILE="$ROOT/.dev-secrets.env"

for tool in docker kubectl openssl curl; do
  command -v "$tool" >/dev/null || { echo "$tool is required. Docker Desktop provides docker and kubectl." >&2; exit 1; }
done
docker info >/dev/null
kubectl config get-contexts -o name | grep -qx docker-desktop || {
  echo "Enable Kubernetes in Docker Desktop Settings > Kubernetes, then run this script again." >&2
  exit 1
}
kubectl config use-context docker-desktop >/dev/null
kubectl cluster-info >/dev/null

mapfile -t legacy_containers < <(docker ps -q --filter 'label=k3d.cluster=lantern-dev')
if (( ${#legacy_containers[@]} > 0 )); then
  echo "Stopping the previous Lantern development cluster containers to release ports 80 and 443."
  docker stop "${legacy_containers[@]}" >/dev/null
fi

helm_container() {
  docker run --rm \
    -v "$HOME/.kube:/root/.kube:ro" \
    -v "$ROOT:/workspace" \
    -v lantern-helm-config:/root/.config/helm \
    -v lantern-helm-cache:/root/.cache/helm \
    -v lantern-helm-data:/root/.local/share/helm \
    -w /workspace "$HELM_IMAGE" "$@"
}

helm_container repo add traefik https://traefik.github.io/charts --force-update
helm_container upgrade --install traefik traefik/traefik --version 41.6.0 \
  --namespace traefik --create-namespace --values /workspace/platform/traefik/values-dev.yaml \
  --wait --timeout 10m

touch "$SECRETS_FILE"
chmod 600 "$SECRETS_FILE"
secret_value() {
  local name="$1" value
  value="$(sed -n "s/^${name}=//p" "$SECRETS_FILE" | tail -1)"
  if [[ -z "$value" ]]; then value="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n')"; fi
  printf '%s' "$value"
}

KEYCLOAK_ADMIN_PASSWORD="$(secret_value KEYCLOAK_ADMIN_PASSWORD)"
KEYCLOAK_DB_PASSWORD="$(secret_value KEYCLOAK_DB_PASSWORD)"
DEV_OPS_PASSWORD="$(secret_value DEV_OPS_PASSWORD)"
DEV_DEVELOPER_PASSWORD="$(secret_value DEV_DEVELOPER_PASSWORD)"
ARGOCD_OIDC_CLIENT_SECRET="$(secret_value ARGOCD_OIDC_CLIENT_SECRET)"
CISO_ASSISTANT_OIDC_CLIENT_SECRET="$(secret_value CISO_ASSISTANT_OIDC_CLIENT_SECRET)"
CISO_ASSISTANT_DJANGO_SECRET="$(secret_value CISO_ASSISTANT_DJANGO_SECRET)"
cat > "$SECRETS_FILE" <<EOF
# Local development secrets. Never commit this file.
KEYCLOAK_ADMIN_PASSWORD=$KEYCLOAK_ADMIN_PASSWORD
KEYCLOAK_DB_PASSWORD=$KEYCLOAK_DB_PASSWORD
DEV_OPS_PASSWORD=$DEV_OPS_PASSWORD
DEV_DEVELOPER_PASSWORD=$DEV_DEVELOPER_PASSWORD
ARGOCD_OIDC_CLIENT_SECRET=$ARGOCD_OIDC_CLIENT_SECRET
CISO_ASSISTANT_OIDC_CLIENT_SECRET=$CISO_ASSISTANT_OIDC_CLIENT_SECRET
CISO_ASSISTANT_DJANGO_SECRET=$CISO_ASSISTANT_DJANGO_SECRET
EOF

kubectl apply -k "$ROOT/clusters/dev"
mkdir -p "$ROOT/.rendered"
COREFILE="$ROOT/.rendered/Corefile"
PATCHED_COREFILE="$ROOT/.rendered/Corefile.patched"
kubectl -n kube-system get configmap coredns -o jsonpath='{.data.Corefile}' > "$COREFILE"
if ! grep -q 'rewrite name exact keycloak.localhost keycloak.platform.svc.cluster.local' "$COREFILE"; then
  awk '/^\.:53 \{/ && !done {print; print "    rewrite name exact keycloak.localhost keycloak.platform.svc.cluster.local"; done=1; next} {print}' "$COREFILE" > "$PATCHED_COREFILE"
  kubectl -n kube-system create configmap coredns --from-file="Corefile=$PATCHED_COREFILE" --dry-run=client -o yaml | kubectl apply -f -
  kubectl -n kube-system rollout restart deployment/coredns
  kubectl -n kube-system rollout status deployment/coredns --timeout=180s
fi
kubectl -n platform create secret generic keycloak-dev-secrets \
  --from-literal="admin-password=$KEYCLOAK_ADMIN_PASSWORD" \
  --from-literal="database-password=$KEYCLOAK_DB_PASSWORD" \
  --from-literal="dev-ops-password=$DEV_OPS_PASSWORD" \
  --from-literal="dev-developer-password=$DEV_DEVELOPER_PASSWORD" \
  --from-literal="argocd-oidc-client-secret=$ARGOCD_OIDC_CLIENT_SECRET" \
  --from-literal="ciso-assistant-oidc-client-secret=$CISO_ASSISTANT_OIDC_CLIENT_SECRET" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n ciso-assistant create secret generic ciso-assistant-secrets \
  --from-literal="django-secret-key=$CISO_ASSISTANT_DJANGO_SECRET" \
  --dry-run=client -o yaml | kubectl apply -f -

cat > "$ROOT/.rendered/argocd-secrets.yaml" <<EOF
configs:
  secret:
    extra:
      oidc.keycloak.clientSecret: "$ARGOCD_OIDC_CLIENT_SECRET"
EOF

helm_container upgrade --install keycloak /workspace/charts/keycloak -n platform --wait --timeout 10m
helm_container upgrade --install mailpit /workspace/charts/mailpit -n platform --wait --timeout 5m
helm_container repo add argo https://argoproj.github.io/argo-helm --force-update
helm_container upgrade --install argocd argo/argo-cd --version 10.9.2 -n argocd \
  -f /workspace/platform/argocd/values-dev.yaml -f /workspace/.rendered/argocd-secrets.yaml \
  --wait --timeout 10m
helm_container upgrade --install ciso-assistant oci://ghcr.io/intuitem/helm-charts/ce/ciso-assistant \
  --version 0.11.5 -n ciso-assistant -f /workspace/platform/ciso-assistant/values-dev.yaml \
  --wait --timeout 15m

for url in \
  http://keycloak.localhost/realms/lantern-dev/.well-known/openid-configuration \
  http://argocd.localhost \
  http://ciso.localhost \
  http://mail.localhost; do
  for attempt in $(seq 1 60); do
    if curl --fail --silent --location --max-time 10 "$url" >/dev/null; then break; fi
    if [[ "$attempt" == 60 ]]; then echo "Service unavailable: $url" >&2; exit 1; fi
    sleep 10
  done
done

if [[ -n "$GIT_REPOSITORY_URL" ]]; then
  mkdir -p "$ROOT/.rendered/bootstrap"
  for file in "$ROOT"/bootstrap/argocd/{projects,applications}/*.yaml; do
    sed -e "s|__GIT_REPOSITORY_URL__|$GIT_REPOSITORY_URL|g" -e "s|__GIT_REVISION__|$GIT_REVISION|g" "$file" \
      > "$ROOT/.rendered/bootstrap/$(basename "$file")"
  done
  kubectl apply -f "$ROOT/.rendered/bootstrap"
fi

cat <<EOF

Docker Desktop environment is ready:
  Keycloak         http://keycloak.localhost
  Argo CD          http://argocd.localhost
  CISO Assistant   http://ciso.localhost
  Development mail http://mail.localhost

No tool other than Docker Desktop is required. Helm runs inside Docker.
Local credentials are stored in $SECRETS_FILE
EOF

