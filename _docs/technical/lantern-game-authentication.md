# Project Lantern: production authentication

This document describes the production contract between Keycloak, Traefik and
the Project Lantern frontend. It applies to the public host
`https://groupe7.diiage.org`.

## What this deployment changes

- Keycloak serves the Lantern theme from the custom image
  `10.4.111.200:18443/lantern/keycloak-theme:v0.1.0`.
- The frontend uses the `lantern` realm and the `lantern-public` OIDC client at
  `https://groupe7.diiage.org/auth`.
- Traefik validates access tokens before it sends Player and Dungeon requests
  to their services. It removes client-provided identity headers, then forwards
  `X-User-Id` from `sub` and `X-Username` from `preferred_username`.

## Realm safety

Do **not** add `--import-realm` to the production Keycloak command to deploy
this theme. The PostgreSQL database remains the source of truth for all
realms, including realms created manually by the operations team. The custom
image only adds files under `/opt/keycloak/themes/lantern`; it neither imports,
updates nor deletes realm data.

If an import is ever deliberately required, Keycloak skips an import whose
realm already exists; it is not a realm-update mechanism. Use the admin console
or an explicit, reviewed migration for changes to the existing `lantern`
realm. See the [Keycloak import and export documentation](https://www.keycloak.org/server/importExport).

## Operator prerequisites

1. Publish the Keycloak theme through the `CD - Publish Keycloak theme`
   workflow in `frontend-game`. A push to `dev` that changes `keycloak/**`
   publishes development tags. Creating a semantic release tag (`vX.Y.Z`)
   publishes the immutable image and requests the `Promote Keycloak theme
   image` GitOps workflow. The latter updates
   `platform/keycloak/deployment-keycloak.yaml` automatically.

   The workflow requires the existing `HARBOR_USERNAME`, `HARBOR_TOKEN`, and
   `GITOPS_DISPATCH_TOKEN` repository secrets. It builds on GitHub, then pushes
   from the `lantern-k3s-builders` runner so Harbor stays private.

2. Ensure the `keycloak` namespace contains the `harbor-pull` image-pull
   secret. The Keycloak Deployment now references it because the theme image is
   stored in Harbor.

3. Provide the existing TLS secret name for `groupe7.diiage.org`. Before the
   public rollout, update the Keycloak and frontend Ingresses to use the
   `websecure` entrypoint and that secret. The name is intentionally not guessed
   in this repository: setting a wrong one would break public login. Keycloak's
   hostname is already HTTPS and the frontend/token issuer assume HTTPS.

4. Verify the Traefik CRDs (`Middleware` from `traefik.io/v1alpha1`) are
   installed. The HelmChartConfig installs the `keycloak-jwt` experimental
   plugin on every Traefik replica; wait for the Traefik rollout before applying
   an Ingress that references it.

## Keycloak configuration

Keep existing manually managed realms unchanged. In the existing `lantern`
realm, configure (or verify) the client below:

| Setting | Value |
| --- | --- |
| Client ID | `lantern-public` |
| Client type | Public OpenID Connect client |
| Standard flow | Enabled |
| PKCE method | `S256` |
| Valid redirect URIs | `https://groupe7.diiage.org/*` |
| Web origins | `https://groupe7.diiage.org` |
| Login theme | `lantern` |

Enable user registration in the `lantern` realm if self-service account
creation must remain available. A valid access token must contain `sub`,
`preferred_username`, and `azp: lantern-public`; the latter is enforced by the
Traefik middleware.

## Post-deploy validation

1. Open `https://groupe7.diiage.org/auth/realms/lantern/.well-known/openid-configuration`.
   Its issuer must be `https://groupe7.diiage.org/auth/realms/lantern`.
2. Sign in through the frontend and check that the Lantern Keycloak theme is
   used.
3. Call a Player or Dungeon API route without a token: it must return `401`.
4. Call the same route through the frontend: it must succeed and the receiving
   service must observe the trusted `X-User-Id` header.
5. Confirm that `/auth` reaches Keycloak while `/` reaches `frontend-game` on
   the same host.
