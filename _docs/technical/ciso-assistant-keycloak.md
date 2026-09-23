# Connect CISO Assistant to Keycloak

The Keycloak chart provisions the confidential `ciso-assistant` client. Its
secret is generated in `.dev-secrets.env` for development and must come from a
secret manager in production.

After signing in with the local CISO Assistant administrator, open
**Extra > Settings > SSO settings**, enable SSO and select **OpenID Connect**.

Development values:

- Client ID: `ciso-assistant`
- Client secret: `CISO_ASSISTANT_OIDC_CLIENT_SECRET`
- Server URL: `http://keycloak.localhost/realms/lantern-dev/.well-known/openid-configuration`
- Additional scopes: `groups`
- Callback: `http://ciso.localhost/api/accounts/oidc/openid_connect/login/callback/`

Production uses the same client ID with the HTTPS domains declared in
`charts/keycloak/values-prod.yaml`. CISO Assistant requires a user to exist in
the application before the first OIDC sign-in. Keep one audited local emergency
administrator until SSO recovery has been tested.

Keycloak sends `/ciso-admins` in the `groups` claim. CISO Assistant does not
automatically turn that claim into an administrator role; grant the application
role explicitly and review it regularly.

