# Harbor availability announcement

Draft: send only after the private cutover and authenticated push/pull validation.

Harbor is now available on the Lantern Kubernetes platform at:

**https://10.4.111.200:18443**

The registry provides private OCI image storage, immutable image references and
Trivy vulnerability scanning. It is backed by replicated Longhorn volumes and
is currently restricted to trusted private, CI and cluster networks.

Before using it, developers must obtain:

- private access to `10.4.111.200:18443` through pfSense;
- trust in the Harbor private CA and the matching server certificate;
- an individual Harbor account or a scoped robot account for CI.

Please use the following image naming convention:

```text
10.4.111.200:18443/lantern/<service>:<git-sha>
```

Do not use the `latest` tag, do not use the administrator account for builds,
and never store Harbor credentials in a repository. CI should only build and
push images; deployments remain managed through reviewed changes in the GitOps
repository.

The complete usage guide is available in
`platform/harbor/DEVELOPER_GUIDE.md`.
