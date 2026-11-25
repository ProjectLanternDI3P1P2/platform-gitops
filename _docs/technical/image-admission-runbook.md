# Runbook: image admission chain

Date: 2026-11-25
Applies to: shared workflow `publish-and-promote` (platform-gitops), Harbor project `lantern`, K3s cluster.
Context and decisions: [ADR 6](../adr/6.%20ImageAdmission.md). Rules: [Image admission policy](../../security/Image%20admission%20policy.md).

Commands below need cosign v2 (the pipeline uses v2.6.5). `--allow-insecure-registry` is needed because Harbor has a self-signed certificate. Never paste a private key or a password in a chat, a ticket or a log.

## 1. Understand what the chain does

1. The CD builds the image and pushes it to Harbor (`main-<sha>` or the release tag).
2. It resolves the image digest.
3. Scan gate: it waits for the Harbor scan and fails on CRITICAL, scan error or timeout.
4. It signs the digest with cosign, then verifies the signature with the CI public key.
5. It attaches a signed provenance attestation and verifies it (commit must match).
6. On a release tag, it asks the promotion workflow to update the overlay (tag and digest).

## 2. A CD run failed: which step?

| Failed step | Likely cause | What to do |
|---|---|---|
| Enforce Harbor vulnerability scan gate, HTTP 403 | The Harbor robot of the CD lacks the Artifact read permission | Add it on the robot (Harbor, project `lantern`, Robots) |
| same, "CRITICAL vulnerabilities: N" | The image has N CRITICAL findings | Fix or update the dependency or base image, rebuild. For an urgent case see section 5 |
| same, "scan did not succeed" or timeout | Trivy failed or is slow | Check the scanner in Harbor (Administration, Interrogation services), rerun the scan on the artifact, rerun the job |
| Sign image by digest, "unsupported pem type: PUBLIC KEY" | The secret `COSIGN_PRIVATE_KEY` contains the public key | Put the content of the private key file |
| Sign image by digest, wrong password | `COSIGN_PASSWORD` does not match the key | Restore the password from the vault |
| Verify signature | The signature was made with another key than the public key of the workflow | Check that the secret key and the public key in the workflow are the same pair |
| Image must use 10.4.111.200:18443/lantern/ | The `image` input of the caller is wrong | Use the internal registry name |
| Promotion: `GH013` repository rule violations | The promotion tried to push on `main` | See the decision about promotion by pull request in the ADR |

## 3. Check an image by hand

Replace `IMAGE` by `10.4.111.200:18443/lantern/<service>` and `DIGEST` by `sha256:...` (digest of the tag, visible in Harbor).

```bash
# Signature made with the CI key
cosign verify --key cosign.pub --insecure-ignore-tlog=true --allow-insecure-registry "$IMAGE@$DIGEST"

# Provenance (shows the source repository, commit and workflow run)
cosign verify-attestation --key cosign.pub --type slsaprovenance --insecure-ignore-tlog=true --allow-insecure-registry "$IMAGE@$DIGEST" \
  | jq -r '.payload' | base64 -d | jq '.predicate'

# What is attached to the image
cosign tree --allow-insecure-registry "$IMAGE@$DIGEST"
```

`cosign.pub` is the CI public key (it is stored in the workflow and in the vault).

## 4. Understand a rejected deployment

- **Pod in `ImagePullBackOff`, event with HTTP 412**: Harbor refused the pull. Either the image has vulnerabilities at or above the blocking threshold, or (when enabled) it has no signature. Open the artifact in Harbor: the Vulnerabilities column and the Signed column give the reason. `kubectl describe pod` shows the message.
- **Rejection by the admission policy of the cluster (US-07)**: the message states the image, the rule (unsigned, wrong key, missing provenance, registry not allowed) and the date. The audit event goes to the monitoring stack. *To complete when the policy engine is chosen.*
- **The image is in the overlay by tag only**: it is not protected by the signature. The overlay must reference the digest (see the ADR).

First thing to check in all cases: does the deployed digest in the overlay match a signed artifact in Harbor.

## 5. Request and revoke an emergency exception

Only the Security team can approve. Maximum duration: 7 days.

1. Open a work item with: image and digest, reason, risk accepted, requested duration, owner.
2. Security approves in the work item (comment with name and date).
3. Apply the exception, for a vulnerability: in Harbor, project `lantern`, Configuration, CVE allowlist, add the CVE identifiers and set the **expiry date** (7 days maximum). For a signature or provenance exception: *procedure to complete with the policy engine of US-07*.
4. Log the exception and its use in the work item.
5. Revoke: remove the CVE from the allowlist (or let it expire) and close the work item. An expired exception must not allow the deployment any more: check it on the expiry date.

Never disable the scan, the signature or the provenance checks without a documented exception (policy, section 6).

## 6. Rotate the signing key (every 12 months, next: 2027-11-25)

1. On a trusted machine: `cosign generate-key-pair` with a strong password. Store `cosign.key` and the password in the vault (collection Security) before anything else.
2. Add the new public key to the trusted keys of the policy engine, **keeping the old one** during the transition.
3. Update the organization secrets `COSIGN_PRIVATE_KEY` and `COSIGN_PASSWORD`.
4. Open a pull request on platform-gitops that replaces the public key in the step "Verify signature" of `publish-and-promote.yaml`. After the merge, update the pin of each service.
5. Re-sign the images that are currently deployed with the new key (by digest), without rebuilding them.
6. After every deployed image is signed with the new key, remove the old public key from the policy engine and archive the old private key as revoked in the vault.
7. Delete the key file from the working machine.

## 7. Suspected compromise of the key, of the Harbor robot or of an image

1. Revoke at once: disable the Harbor robot of the CD, and remove the compromised public key from the policy engine.
2. Report to the Security team without delay.
3. Generate a new key pair (section 6, steps 1 to 4), create a new robot account and update the secrets.
4. Rescan the images concerned, redeploy from a verified build, re-sign the trusted images.
5. Review the Harbor logs (push and pull events of the robot) and the CD runs since the suspected date.

## 8. Before enabling a new control on the `lantern` project

Enabling the blocking of vulnerabilities or the Cosign requirement affects every pull, including the pull robot of the cluster. Check first, image by image, that every image referenced by `apps/*/overlays/k3s` is scanned below the threshold and signed. Test on the project `test-us05` first. A control enabled too early leaves pods unable to restart.
