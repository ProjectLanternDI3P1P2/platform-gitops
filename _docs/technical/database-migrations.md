# Database migrations before API rollout

Player, Dungeon and Rewards use a shared Kustomize migration component.
Each full Argo CD sync first runs a `PreSync` Job from the exact API image.
The Job passes `--migrate`, applies pending EF migrations, and exits without
starting HTTP, message consumers, or Development data seeding. API rollout
continues only after success.

## Image prerequisites and first activation

This configuration depends on the migration-command changes in the three
backend repositories. Existing image tags do not contain that command.

1. Merge and validate the Player, Dungeon and Rewards backend changes.
2. Publish an immutable release image for each backend through the existing CD.
3. In this GitOps change, select those new release tags before merging. Do not
   enable the hook against the currently selected older images. In particular,
   replace the existing Rewards `dev-latest` tag with a reviewed immutable tag.
4. Confirm the database, schema and `lantern-db` Secret already exist in each
   namespace. PreSync runs before ordinary resources are applied, so initial
   database/bootstrap provisioning must complete separately.
5. Review the pending migrations and ensure a tested database backup exists.
   Use backward-compatible schema changes because the old API can still serve
   traffic while the PreSync Job runs.

This PR does not execute any production migration or promote a new image.

## Configuration coupling

Replacements run in each application overlay after its environment/secret
patches. They copy the final API image, connection string (including its
service-specific Search Path), password-file path, database Secret name and
image-pull Secrets into the migration Job. Image promotion therefore updates
the API and migration together without a second tag to maintain.

The Job currently uses the existing service schema-owner identity and the
mounted `lantern-db` password. This does not introduce or broaden database
permissions. A separate DDL identity and runtime DML-only role can be adopted
later by changing the Job credential source deliberately.

Each Job has one completion, parallelism one, no Kubernetes retry and a
10-minute deadline. EF Core's migration locking protects simultaneous runs
against the same migration history. Different service schemas can migrate
independently. The ApplicationSet's existing Argo retry policy can rerun a
failed sync; the migration command must remain repeatable.

Successful hooks are deleted. Failed hooks remain available for logs until
the next full sync, which replaces them using `BeforeHookCreation`. Jobs
have no Kubernetes API token and run as non-root with dropped capabilities.

## Failure and operations

An error exits nonzero and prevents the new Deployment from being applied.
Inspect the failed Job before retrying. Never use `EnsureCreated`, reset the
database, mark migrations applied manually, or run automatic down migrations.
Application rollback does not roll back the database; use a reviewed forward
fix or an approved backup recovery if necessary.

Use full application syncs for releases. Argo CD skips hooks during selective
resource sync, so selectively syncing only a Deployment bypasses this gate.

Combat and Leaderboard are not enabled: their current `main` branches contain
no EF migration files (Leaderboard still carries the Combat template). Mongo
bootstrap is not a substitute for a versioned Mongo migration mechanism.
Frontends do not own database migrations.

## Validation

GitOps CI renders participating overlays and checks that Job settings match
the final Deployment, that tag promotion updates both images, and that apps
without migration artifacts have no migration Job. It does not connect to a
database.

Backend CI runs the actual published command against its disposable PostgreSQL
service: first apply, repeat without changing history, no application seed data,
and prompt nonzero failure when the mounted password file is missing.

References: [Argo CD hooks](https://argo-cd.readthedocs.io/en/stable/user-guide/resource_hooks/),
[EF migration deployment](https://learn.microsoft.com/en-us/ef/core/managing-schemas/migrations/applying).
