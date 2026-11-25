# US-01 — High Availability and Server Failure Resilience

## 1. Objective

The objective of this user story is to ensure that players can continue playing even if one Kubernetes worker node becomes unavailable.

Game services must remain available during a server failure.

To achieve this, the infrastructure must:

- Run multiple replicas of critical game services.
- Distribute replicas across different Kubernetes workers.
- Automatically detect unhealthy or unavailable application instances.
- Send traffic only to healthy and ready Pods.
- Restart containers when an application becomes unresponsive.
- Protect services against voluntary disruptions during maintenance.

## 2. Scope

This documentation covers the following tasks:

| Task  | Description                                                                    |
| ----- | ------------------------------------------------------------------------------ |
| T01.6 | Deploy at least two replicas of critical services in the production namespace. |
| T01.7 | Configure Kubernetes startup, readiness and liveness probes.                   |

The implementation applies to all game services identified as critical.

Examples include:

- Combat
- Dungeon
- Other game APIs required for gameplay

The list of critical services must be confirmed with the development team.

---

# Part 1 — T01.6: Deploy multiple replicas on different workers

## 3. Objective

Every critical game service must run with at least two Pods in the production namespace.

The Pods must be scheduled on different Kubernetes worker nodes.

### Expected architecture

Example with the Combat service:

```text
                Kubernetes Cluster
                       |
             ---------------------
             |                   |
          Worker 1             Worker 2
             |                   |
        Combat Pod 1        Combat Pod 2
             |                   |
             -----------+--------
                        |
                   Combat Service
                        |
                   Game Traffic
```

If Worker 1 becomes unavailable, Combat Pod 2 can continue handling requests.

The same configuration must be applied to every critical service.

## 4. Configure Deployment replicas

Each critical service must have at least two replicas.

In the Kubernetes Deployment manifest, configure:

```yaml
spec:
  replicas: 2
```

Example:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: combat
  namespace: prod
spec:
  replicas: 2
  selector:
    matchLabels:
      app: combat
  template:
    metadata:
      labels:
        app: combat
    spec:
      containers:
        - name: combat
          image: harbor.example.com/game/combat:1.0.0
          ports:
            - name: http
              containerPort: 8080
```

Important:

- Replace the example Harbor image with the actual image and tag.
- Keep the existing labels and selectors consistent with the Service.
- Do not overwrite existing environment variables, volumes, secrets or configuration.
- Apply the change to every critical service.

## 5. Configure Pod distribution with topologySpreadConstraints

Having two replicas is not sufficient if Kubernetes places both Pods on the same worker.

We must configure `topologySpreadConstraints` to distribute replicas across different workers.

Add the following configuration under `spec.template.spec` in the Deployment:

```yaml
topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: kubernetes.io/hostname
    whenUnsatisfiable: DoNotSchedule
    labelSelector:
      matchLabels:
        app: combat
```

Explanation:

| Parameter     | Purpose                                                                  |
| ------------- | ------------------------------------------------------------------------ |
| maxSkew: 1    | Limits the difference in Pod distribution between workers.               |
| topologyKey   | Uses the worker hostname to distinguish nodes.                           |
| DoNotSchedule | Prevents scheduling if the distribution requirement cannot be satisfied. |
| labelSelector | Identifies the Pods that must be distributed.                            |

The workers must have the Kubernetes label `kubernetes.io/hostname`.

With two available workers and two replicas, the expected distribution is one Pod per worker.

Important:

`DoNotSchedule` can leave a Pod Pending if Kubernetes cannot find another eligible worker. This is intentional for strict worker separation.

The cluster must therefore have enough available workers and resources.

## 6. Configure PodDisruptionBudget

A PodDisruptionBudget (PDB) protects application availability during voluntary disruptions.

Examples include:

- Worker maintenance.
- Node draining.
- Planned infrastructure operations.

Create a separate manifest for each critical service.

Example: `combat-pdb.yaml`

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: combat-pdb
  namespace: prod
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: combat
```

Explanation:

`minAvailable: 1` means Kubernetes must keep at least one matching Pod available during voluntary disruptions.

Important:

A PodDisruptionBudget does not prevent unexpected worker failures. Replica distribution and sufficient cluster capacity are still required.

## 7. Expected result for T01.6

For every critical service:

- At least two replicas are configured.
- At least two Pods reach the Running state.
- Pods are distributed across different workers.
- A PodDisruptionBudget is configured.
- The service remains accessible if one worker becomes unavailable.

---

# Part 2 — T01.7: Configure Kubernetes health probes

## 8. Objective

Kubernetes must automatically monitor the health of every game service.

Three probes must be configured:

1. Startup probe.
2. Readiness probe.
3. Liveness probe.

These probes allow Kubernetes to detect application startup problems, prevent traffic from reaching unready Pods and restart stuck containers.

## 9. Required health endpoints

Each game API must expose two HTTP health endpoints.

### 9.1 Liveness endpoint

Endpoint:

```text
/health/live
```

Purpose:

Checks whether the application is alive and functioning.

If the application becomes unresponsive, Kubernetes can restart the container.

This endpoint should check the application process itself.

It should not fail simply because PostgreSQL or RabbitMQ is temporarily unavailable. Otherwise, an external dependency failure could trigger unnecessary application restarts.

### 9.2 Readiness endpoint

Endpoint:

```text
/health/ready
```

Purpose:

Checks whether the application is ready to receive traffic.

If the application is not ready, Kubernetes removes the Pod from the ready endpoints of its Service.

Requests are therefore sent only to ready Pods.

Readiness checks may include dependencies required to handle requests correctly, depending on the service architecture.

## 10. Implement health endpoints in .NET

The endpoints must exist in each ASP.NET Core application.

For a .NET application, the built-in health checks can be used.

Example in `Program.cs`:

```csharp
builder.Services.AddHealthChecks();

var app = builder.Build();

app.MapHealthChecks("/health/live", new HealthCheckOptions
{
    Predicate = _ => false
});

app.MapHealthChecks("/health/ready");

app.Run();
```

Required namespace:

```csharp
using Microsoft.AspNetCore.Diagnostics.HealthChecks;
```

This is a basic example.

If the service requires database or message broker connectivity before it can receive requests, the readiness health check should be extended with the appropriate dependency checks.

Do not add dependency checks to liveness unless restarting the application is genuinely the correct response to that dependency failure.

Verify that both endpoints return a successful HTTP response when the application is healthy.

## 11. Configure Kubernetes probes

Each game Deployment must contain all three probes.

Example for Combat:

```yaml
containers:
  - name: combat
    image: harbor.example.com/game/combat:1.0.0

    ports:
      - name: http
        containerPort: 8080

    startupProbe:
      httpGet:
        path: /health/live
        port: http
      periodSeconds: 5
      failureThreshold: 30

    readinessProbe:
      httpGet:
        path: /health/ready
        port: http
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 3

    livenessProbe:
      httpGet:
        path: /health/live
        port: http
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
```

### Startup probe

Allows the application time to start.

With the example configuration:

- Kubernetes checks every five seconds.
- The application can fail up to 30 checks before the startup probe fails.

The liveness and readiness probes are not activated until the startup probe succeeds.

### Readiness probe

Checks whether the application can receive requests.

If the readiness probe fails:

- The Pod remains running.
- The Pod is marked as not ready.
- Kubernetes removes it from the ready Service endpoints.

When the application becomes ready again, Kubernetes can send traffic to it.

### Liveness probe

Checks whether the application is still functioning.

If the liveness probe fails repeatedly, Kubernetes restarts the container.

## 12. Apply probes to all game services

The same health-check configuration must be implemented for every game API.

Example:

| Service             | Startup  | Readiness | Liveness |
| ------------------- | -------- | --------- | -------- |
| Combat              | Required | Required  | Required |
| Dungeon             | Required | Required  | Required |
| Other critical APIs | Required | Required  | Required |

Adjust the container port and health endpoints if a service uses a different configuration.

---

# Part 3 — Kubernetes Services and traffic routing

## 13. Ensure traffic only reaches healthy Pods

Kubernetes Services automatically use Pod readiness when managing their endpoints.

A Service selects Pods using labels.

Example:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: combat
  namespace: prod
spec:
  selector:
    app: combat
  ports:
    - name: http
      port: 8080
      targetPort: http
```

When a Pod fails its readiness probe, it is removed from the ready endpoints.

The Service can continue routing traffic to the remaining ready Pods.

No manual load-balancing configuration is required for this basic Kubernetes Service behavior.

---

# Part 4 — GitOps repository changes

## 14. Locate the Kubernetes manifests

All infrastructure changes must be committed to the `platform-gitops` repository.

Start by inspecting:

```text
platform-gitops/
├── apps/
├── clusters/
├── platform/
├── bootstrap/
└── docs/
```

The application manifests should be located in the corresponding application directories.

Inspect the actual repository structure before creating or modifying files.

Depending on the existing configuration, the repository may use:

- Plain Kubernetes YAML.
- Kustomize bases and overlays.
- Helm charts and values files.

Do not create duplicate Deployments or Services.

Modify the existing application configuration.

### Files to inspect

For each critical service, locate:

- Deployment manifest or Helm values.
- Service manifest.
- Kustomization file, if Kustomize is used.
- Existing PodDisruptionBudget, if present.

The production configuration must target the existing production namespace.

Do not assume that the namespace is named `prod` without checking the repository and cluster configuration.

## 15. Recommended changes per service

For each critical service:

| Configuration       | Required action                                 |
| ------------------- | ----------------------------------------------- |
| Deployment          | Set at least two replicas.                      |
| Pod distribution    | Add topologySpreadConstraints.                  |
| PodDisruptionBudget | Create or update the PDB.                       |
| Startup probe       | Add startupProbe.                               |
| Readiness probe     | Add readinessProbe.                             |
| Liveness probe      | Add livenessProbe.                              |
| Service             | Verify selectors and ports.                     |
| Image               | Use the correct Harbor image and immutable tag. |

All changes must preserve existing application settings.

## 16. Git workflow

Create a feature branch:

```bash
git checkout -b feature/US-01-high-availability
```

After editing the manifests, inspect the changes:

```bash
git status
git diff
```

Validate the Kubernetes configuration before pushing.

Commit:

```bash
git add .
git commit -m "feat: improve game services high availability"
```

Push:

```bash
git push -u origin feature/US-01-high-availability
```

Create a Pull Request on GitHub.

After review and merge, Argo CD must synchronize the changes according to the repository's existing synchronization policy.

A Git push alone does not prove that the cluster has applied the new configuration.

---

# Part 5 — Validation and testing

## 17. Validate Kubernetes manifests

If the repository uses Kustomize:

```bash
kubectl kustomize <path-to-production-overlay>
```

This renders the Kubernetes resources without applying them.

If the cluster is accessible, compare the rendered configuration with the live cluster:

```bash
kubectl diff -k <path-to-production-overlay>
```

For Helm-based configuration, render the chart with the existing Helm values and inspect the resulting resources.

Do not apply changes to production until the rendered configuration has been reviewed.

## 18. Verify Deployments

Check Deployments in the production namespace:

```bash
kubectl get deployments -n prod
```

Expected result for each critical service:

```text
NAME      READY   UP-TO-DATE   AVAILABLE
combat    2/2     2            2
dungeon   2/2     2            2
```

The exact service names may differ.

## 19. Verify Pod distribution

Run:

```bash
kubectl get pods -n prod -o wide
```

Example expected result:

```text
NAME             READY   STATUS    NODE
combat-abc123    1/1     Running   worker-1
combat-def456    1/1     Running   worker-2
```

The two Pods must be on different workers.

Repeat for every critical service.

## 20. Verify health probes

Inspect a Deployment:

```bash
kubectl describe deployment combat -n prod
```

Verify that the container configuration contains:

- Startup probe.
- Readiness probe.
- Liveness probe.

Inspect Pod events:

```bash
kubectl describe pod <pod-name> -n prod
```

Look for probe failures, HTTP errors and container restarts.

## 21. Verify Service endpoints

Check the Service:

```bash
kubectl get services -n prod
```

Check ready endpoints:

```bash
kubectl get endpointslices -n prod
```

Or, on clusters where the older resource is available:

```bash
kubectl get endpoints -n prod
```

A Pod that fails readiness must not appear as a ready backend for the Service.

## 22. Verify PodDisruptionBudgets

Run:

```bash
kubectl get pdb -n prod
```

Inspect a specific PDB:

```bash
kubectl describe pdb combat-pdb -n prod
```

Verify that the minimum available Pod requirement is correct.

## 23. Test a worker failure

This is the most important acceptance test.

The purpose is to verify that the game remains accessible when one worker becomes unavailable.

### Before the test

1. Verify that all critical services have two Running Pods.
2. Verify that replicas are on different workers.
3. Verify that the game is accessible.
4. Check the health endpoints.
5. Check the Service endpoints.

### During the test

Perform a controlled worker shutdown or failure simulation.

For a planned maintenance test, a worker can first be drained:

```bash
kubectl drain <worker-name> --ignore-daemonsets
```

Important:

`kubectl drain` performs a voluntary eviction, so it does not simulate every aspect of an unexpected hardware failure.

A true worker-failure test must also validate behavior when the node becomes unavailable without a graceful drain.

Only perform these tests with the infrastructure team's authorization and an appropriate recovery plan.

### After the test

Verify:

```bash
kubectl get nodes
kubectl get pods -n prod -o wide
kubectl get deployments -n prod
```

Expected behavior:

- The surviving worker continues to run the remaining game service Pods.
- The game remains accessible through the available instances.
- Kubernetes detects the unavailable worker.
- Replacement Pods are scheduled when an eligible worker has sufficient resources.
- The service returns to its expected replica count after recovery.

Important:

A failed worker does not guarantee that its Pods will be immediately recreated elsewhere. Kubernetes node detection, eviction timing, scheduling capacity and storage dependencies must all be considered.

---

# Part 6 — Important infrastructure dependencies

## 24. Database and RabbitMQ availability

Multiple application Pods do not automatically guarantee that the entire game is highly available.

The game may still become unavailable if a required dependency fails.

Important dependencies include:

- PostgreSQL.
- RabbitMQ.
- Internal networking.
- Persistent storage.
- DNS and ingress components.

The current infrastructure must be checked to determine whether these components also survive a worker failure.

For example, if PostgreSQL or RabbitMQ has only one instance on one worker, the game may still lose essential functionality when that worker becomes unavailable.

This must be considered when validating the complete US-01 acceptance criteria.

## 25. Worker capacity

The Kubernetes cluster must have enough available resources to run replacement Pods.

For example, if the cluster has only two workers and each worker is already using all available CPU and memory, Kubernetes may not be able to schedule replacement Pods after a failure.

Verify:

```bash
kubectl get nodes
kubectl describe nodes
kubectl top nodes
```

The `kubectl top` command requires Metrics Server to be installed and working.

## 26. Harbor image availability

Every service image must be accessible from the Kubernetes workers.

Verify:

- Images exist in Harbor.
- Deployments reference the correct Harbor image.
- Image tags are immutable or uniquely versioned.
- Kubernetes has the necessary image pull credentials.
- The workers can access Harbor.

Do not use `latest` for production deployments.

---

# Part 7 — Acceptance criteria

## 27. US-01 completion checklist

### T01.6 — Multiple replicas

- [ ] All critical services are deployed in the production namespace.
- [ ] Each critical service has at least two replicas.
- [ ] Each critical service has two Running Pods.
- [ ] Replicas are running on different workers.
- [ ] Topology spread constraints are configured.
- [ ] PodDisruptionBudgets are configured.
- [ ] The cluster has enough resources for replacement Pods.

### T01.7 — Health probes

- [ ] `/health/live` exists on every game API.
- [ ] `/health/ready` exists on every game API.
- [ ] Every Deployment has a startup probe.
- [ ] Every Deployment has a readiness probe.
- [ ] Every Deployment has a liveness probe.
- [ ] Unready Pods do not receive Service traffic.
- [ ] Unhealthy containers are restarted when appropriate.

### US-01 — High availability

- [ ] All game service images are stored in Harbor.
- [ ] Critical services remain available when one worker fails.
- [ ] The game remains accessible during the worker failure test.
- [ ] Required infrastructure dependencies have been checked.
- [ ] The test results have been documented.

---

# 28. Definition of Done

US-01 is considered complete when:

1. All game service images are available in Harbor.
2. Every critical service runs with at least two Pods on different workers.
3. Every game Deployment has startup, readiness and liveness probes.
4. Kubernetes sends traffic only to ready Pods.
5. Broken application containers are restarted.
6. A worker failure does not interrupt access to the game.
7. The behavior has been tested and the results documented.

**Final objective:**

The player should be able to continue playing even if one Kubernetes worker becomes unavailable, without requiring a manual restart of the game services.
