# Production cluster foundation

This overlay creates the platform namespaces and enables Pod Security Admission
at the baseline enforcement level with restricted audit and warning checks.

Production does not rewrite public DNS through CoreDNS. Keycloak, Argo CD and
CISO Assistant must use stable HTTPS records resolvable from browsers and pods.

Apply this foundation only after the CNI, CSI, ingress controller and
cert-manager are healthy.

