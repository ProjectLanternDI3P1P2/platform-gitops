# Private Argo CD and Harbor access

The public HAProxy migration is superseded. Both services use private pfSense
forwarding and terminate TLS themselves:

| Service | Private URL | Internal target |
| --- | --- | --- |
| Argo CD | `https://10.4.111.200:8443` | `192.168.0.30:30443` |
| Harbor | `https://10.4.111.200:18443` | `192.168.0.11:30444` |

- [Private Argo CD setup](argocd/NAT_EXPOSURE.md)
- [Private Harbor setup and CD prerequisites](harbor/NAT_EXPOSURE.md)

Disable the old public NAT rules and public frontends for these services.
Keep existing unrelated HTTPS port 443 and Keycloak routes unchanged.
Editing these files does not change pfSense, rotate certificates or modify
credentials. Complete those prerequisites before merging the corresponding PRs.
