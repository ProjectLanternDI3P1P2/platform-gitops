# Image Admission Policy — Scanned, Signed and Traceable Images Only

Scope: Container images built by the CI/CD pipelines, stored in the Harbor registry and deployed on the Lantern K3s cluster through Argo CD
Version: 1.0 (draft for review)
Status: Deny by default — an image is deployed only if it is scanned, signed by a trusted identity, referenced by immutable digest, comes from the trusted registry and has verifiable provenance

---

# 1. Purpose and Scope

This policy defines which container images are allowed to reach the runtime platform in the Lantern Project, and how this is checked. It aims to reduce the risk of deploying a vulnerable, tampered or unknown image, which is a frequent vector of software supply chain attacks.

It applies to:

- all images published by the CI/CD pipelines of the project;
- the Harbor registry, the shared CD workflow (`platform-gitops`) and the Kubernetes cluster;
- all members of the project who build, publish or deploy images.

# 2. References

- SLSA (Supply-chain Levels for Software Artifacts) — framework for build integrity and provenance.
- NIST SP 800-204D — Software supply chain security in DevSecOps CI/CD pipelines.
- ISO/IEC 27001:2022 — Annex A, controls A.5.21 (managing information security in the ICT supply chain) and A.8.8 (management of technical vulnerabilities).
- Internal: Filtering policy (network flows) and Password policies (secrets and service accounts).

# 3. Guiding Principles

1. **Deny by default**: an image that is not explicitly compliant is refused.
2. **Trusted registry only**: images must come from the Harbor registry, under the `lantern/` project. This is already checked by the shared CD workflow.
3. **Scan before sign**: the CI signs an image only after all mandatory scans succeed.
4. **Signed by a trusted identity**: every image is signed by the CD pipeline, **by digest**. Unsigned images and signatures made by an untrusted identity are refused at deployment.
5. **Immutable reference**: deployments reference an immutable digest, not a moving tag such as `main-latest`.
6. **Verifiable provenance**: every image comes with a provenance attestation linking it to its source commit and its build.
7. **Layered enforcement**: the checks exist in Harbor (scan gate), in the CD pipeline (scan, signature, provenance) and in the cluster (verification at admission).
8. **Auditability**: a rejected deployment produces a clear policy violation and an audit event. The chain from commit to deployed version can be reconstructed at any time.
9. **Controlled exceptions**: emergency exceptions require approval, are time-limited and are logged.
10. **Periodic review** of the policy, the accepted severity, the trusted identities and the exceptions.

# 4. Requirements

| Control | Requirement | Enforced by |
|---|---|---|
| Trusted registry | Image name starts with the Harbor `lantern/` project | CD workflow, cluster policy |
| Vulnerability scan | Automatic scan on push. Images with CRITICAL vulnerabilities are blocked. The threshold is reviewed periodically and may be lowered to HIGH | Harbor, CI |
| Scan before sign | The signature step runs only if all mandatory scans succeed | CD workflow |
| Signature | Signed by digest with cosign (key-based) | CD workflow |
| Trusted identity | Only signatures made with the CI signing key are accepted. The list of trusted keys is managed by the Security team | Policy engine |
| Immutable digest | Deployments reference the image digest | GitOps repository, policy engine |
| Provenance | A provenance attestation (source repository, commit, workflow run, build) is attached to the image and verified at admission | CD workflow, policy engine |
| Traceability | For any deployed version, the commit, build, scan result, provenance and digest can be retrieved | CD workflow, GitOps repository |
| Audit event | Every rejected deployment produces a policy violation message and an audit event sent to the monitoring stack | Policy engine, logging |
| Signing key | Private key stored in the vault, never in a repository or a plaintext file. Rotation every 12 months | Security team |
| CI service account | Harbor robot account follows the service account rule of the Password policies (rotation every 90 days) | Security team |
| Network flows | Flows from the runners and from the cluster to Harbor are opened only by documented rules, as defined in the Filtering policy | Security team |

# 5. Exceptions

A non-compliant image can be deployed only through a documented exception, including in an emergency:

- request through a work item, with the reason and the risk accepted;
- approval by the Security team before the deployment;
- a limited lifespan of 7 days maximum, after which the exception is removed automatically or manually;
- a comment with author, date and reason, as for firewall rules;
- the exception and the deployment are logged.

# 6. Formal Prohibitions

- deploying an image pulled directly from a public registry into a project namespace;
- storing the signing key or its password in a repository;
- disabling the signature, provenance or scan checks, even temporarily, without a documented exception;
- referencing an image only by a moving tag in a deployment;
- signing an image whose scan failed or was not run.

# 7. Procedure in Case of Suspected Compromise

If the signing key, the Harbor token or a published image is suspected to be compromised:

1. Revoke the key or the token immediately.
2. Report the incident to the Security team without delay.
3. Generate a new key, update the trusted key in the policy engine and re-sign the trusted images.
4. Rescan the images concerned and redeploy from a verified build.

# 8. Responsibilities

- **Security team**: defines and maintains this policy, manages the keys, the trusted identities and the exceptions.
- **Operations**: implements and operates the scan gate, the signature and provenance steps and the admission control.
- **Developers**: fix the vulnerabilities reported on their images.
