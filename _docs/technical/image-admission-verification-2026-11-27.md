# Verification report: Harbor enforcement on the `lantern` project

Date: 2026-11-27
Scope: registry side of the image admission chain (US-05). Cluster admission is not covered here (US-15).
Context: [ADR 6](../adr/6.%20ImageAdmission.md), [runbook](image-admission-runbook.md), [policy](../../security/Image%20admission%20policy.md)

## 1. Settings under test

Harbor, project `lantern`, Configuration (changed on 2026-11-27):

| Setting | Value |
|---|---|
| Cosign deployment security | Enabled (Notation: disabled) |
| Prevent vulnerable images from running | Enabled, severity Critical |
| Automatic scan on push | Enabled (Trivy v0.72.0, Success on the artifacts checked) |
| Automatic SBOM generation on push | Enabled (an `sbom.harbor` accessory is attached to new artifacts) |
| CVE allowlist | Empty |

Rollback: untick the options and save (runbook, section 10).

## 2. Pull test

Manifest requests (HTTP, read-only) with a Harbor account, run from an operator workstation on 2026-11-27 at 13:23 (Europe/Paris):

| Image | Expected | Result |
|---|---|---|
| `lantern/dungeon-backend:v2.5.0` (signed, scanned) | Pull allowed | `HTTP 200` |
| `lantern/frontend-game:main-latest` (unsigned, 1 CRITICAL) | Pull refused | `HTTP 412`, `PROJECTPOLICYVIOLATION`, "The image is not signed by cosign." |
| `lantern/frontend-public:main-latest` (unsigned) | Pull refused | `HTTP 412`, `PROJECTPOLICYVIOLATION`, "The image is not signed by cosign." |

State of `frontend-game:main-latest` in Harbor at the time of the test (pushed 2026-11-26): scan `Success` by Trivy v0.72.0, maximum severity Critical, 270 findings (1 Critical, 45 High, 118 Medium, 88 Low, 18 Unknown, 20 fixable). Its only accessory is the SBOM, there is no cosign signature.

## 3. Criteria covered and not covered

| Criterion | Status |
|---|---|
| Automatic scan on push and SBOM enabled | Covered (settings, SBOM accessory present) |
| Scanner healthy, results visible in Harbor | Covered (scan result readable on the artifact) |
| A signed and clean image can be pulled | Covered (`dungeon-backend:v2.5.0`, HTTP 200) |
| An unsigned image cannot be pulled | Covered (two images, HTTP 412) |
| An image with CRITICAL vulnerabilities cannot be pulled | **Partly covered.** The only CRITICAL images tested are also unsigned, and Harbor checks the signature first, so the refusal shown is the missing signature. The threshold setting is enabled and the CRITICAL finding is visible, but a signed image with a CRITICAL finding was not tested. To prove it: push a signed image with a known CRITICAL finding to a temporary project with the same two settings, then delete the project and its robot account |
| A rejected image produces an audit event | Not covered (US-15, T15.3) |
| Verification at admission in the cluster | Not covered (US-15, T15.1 and T15.2) |
| Image signed by an untrusted key is rejected | Not covered. Harbor only checks that a signature exists, not who made it. This is the job of the cluster policy engine (ADR 6, decision 4) |
| Unscanned image is rejected | Not covered. Several old artifacts have no scan result (for example `frontend-game:v0.3.0`); whether Harbor blocks an unscanned image has to be checked, otherwise the cluster policy must refuse it |

## 4. Images referenced by the overlays (state of `main`, 2026-11-27)

Result of `grep -rnE 'newName|newTag|digest:' apps/*/overlays/k3s/kustomization.yaml`:

| Application | Image and tag in the overlay | Digest pinned | Expected with the current Harbor settings |
|---|---|---|---|
| dungeon | `dungeon-backend:v2.5.0` | yes | Pullable (tested) |
| combat | `combat-backend:v1.2.0` | yes | Promoted by the shared workflow, not pull-tested here |
| player | `player-backend:v1.6.0` | yes | Promoted by the shared workflow, not pull-tested here |
| leaderboard | `leaderboard-backend:dev-5392a2e59afa` | no | Not produced by the shared workflow, probably unsigned |
| rewards | `reward-backend:git-3855c05…` | no | Not produced by the shared workflow, probably unsigned |
| frontend-game | `frontend-game:v0.3.0` | no | No signature and no scan result seen in Harbor, probably refused at the next pull |
| frontend-public | `frontend-public:main-latest` | no | Refused (tested, HTTP 412) |
| keycloak (platform) | `keycloak-theme:v0.3.0` | no | Published by a workflow that does not sign, probably refused |

Running pods are not affected until they restart or are rescheduled. The corrective action for each service is a `vX.Y.Z` release through the shared workflow (so the image is scanned, signed and pinned by digest). Until then a restart of `frontend-game`, `frontend-public`, `rewards`, `leaderboard` or Keycloak risks `ImagePullBackOff`.

## 5. Argo CD state during the test

`combat`, `dungeon`, `frontend-game`, `frontend-public` and `player`: Healthy and Synced. `leaderboard`: Healthy, OutOfSync, sync failed (last sync 2026-11-27 12:56, owned by another squad, not related to the image controls).

## 6. Next steps

1. US-15, T15.1: policy engine in the cluster that verifies signature by the trusted key, registry, digest and provenance at admission.
2. US-15, T15.2: run the compliant and non-compliant deployment tests in a temporary namespace (signed, unsigned, CRITICAL, signed by another key, unscanned), keep the rejection messages and events as evidence, then delete the namespace, the test project and the test robot account.
3. US-15, T15.3: exceptions and audit events.
4. Services still on the old workflows publish a signed release, then the remaining items of the table in section 4 can be pull-tested.
