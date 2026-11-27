"""Collect bounded read-only snapshots for the Lantern Grafana dashboards."""
import base64
import datetime as dt
import functools
import json
import logging
import math
import re
import ssl
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

ORG = "ProjectLanternDI3P1P2"
GITOPS = f"/repos/{ORG}/platform-gitops"
REGISTRY = "10.4.111.200:18443"
SERVICE_ACCOUNT = Path("/var/run/secrets/kubernetes.io/serviceaccount")
CREDENTIALS = Path("/credentials")
SERVICES = json.loads(Path(__file__).with_name("services.json").read_text())
INTERVAL = 300
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
SHA = re.compile(r"[0-9a-f]{40}")
RELEASE = re.compile(r"v\d+\.\d+\.\d+")
SEVERITIES = ("Critical", "High", "Medium", "Low", "Negligible", "Unknown")
SONAR_METRICS = (
    "coverage", "duplicated_lines_density", "sqale_index", "bugs", "vulnerabilities", "code_smells",
    "software_quality_reliability_issues", "software_quality_security_issues",
    "software_quality_maintainability_issues",
)
FAILURE = {"failure", "timed_out", "startup_failure"}
EVENT_KINDS = {"ci_completed_timestamp_seconds", "ci_duration_seconds", "ci_check_failed", "argo_sync_failed"}
QUANTITY = re.compile(r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))((?:[eE][-+]?\d+)|(?:[numkKMGTPE]i?))?")
QUANTITY_SCALE = {
    "": 1, "n": Decimal("1e-9"), "u": Decimal("1e-6"), "m": Decimal("1e-3"),
    "k": 10**3, "M": 10**6, "G": 10**9, "T": 10**12, "P": 10**15, "E": 10**18,
    "Ki": 2**10, "Mi": 2**20, "Gi": 2**30, "Ti": 2**40, "Pi": 2**50, "Ei": 2**60,
}

class NoRedirect(HTTPRedirectHandler):
    """Keep credentials on their configured origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(origin, path, auth, query=None, ca=None, accept="application/json", raw=False):
    context = ssl.create_default_context()
    if ca is not None:
        context.load_verify_locations(cafile=ca)
    opener = build_opener(HTTPSHandler(context=context), NoRedirect())
    url = origin + path + ("?" + urlencode(query) if query else "")
    headers = {"Accept": accept, "Authorization": auth, "User-Agent": "lantern-kpi"}
    with opener.open(Request(url, headers=headers), timeout=10) as response:
        data = response.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("response too large")
    return data.decode() if raw else json.loads(data)


def credential(name):
    return (CREDENTIALS / name).read_text().strip()


def gh(path, query=None, raw=False):
    accept = "application/vnd.github.raw+json" if raw else "application/vnd.github+json"
    return request("https://api.github.com", path, "Bearer " + credential("github-token"),
                   query=query, accept=accept, raw=raw)


def kubernetes(path, query=None):
    return request("https://kubernetes.default.svc", path,
                   "Bearer " + (SERVICE_ACCOUNT / "token").read_text().strip(),
                   query=query, ca=SERVICE_ACCOUNT / "ca.crt")


def sonar(path, query):
    token = credential("sonar-token")
    return request("https://sonarcloud.io", path, "Bearer " + token, query=query)


def harbor(path, query):
    pair = credential("harbor-user") + ":" + credential("harbor-token")
    return request(f"https://{REGISTRY}", path, "Basic " + base64.b64encode(pair.encode()).decode(),
                   query=query, ca=CREDENTIALS / "harbor-ca.crt")


def timestamp(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def evidence(value, expression):
    return value if isinstance(value, str) and expression.fullmatch(value) else ""


class Observations:
    def __init__(self, service):
        self.identity = dict(service_id=service["service"], repository=service["repository"], squad=service["squad"])
        self.rows = []

    def add(self, kind, value=1, **fields):
        if math.isfinite(value):
            self.rows.append(dict(self.identity, kind=kind, value=value, **fields))

    def source(self, name, task):
        try:
            value = task()
        except Exception as error:
            # Avoid printing URLs, response bodies or credentials from upstream errors.
            logging.warning("%s %s %s", self.identity["service_id"], name,
                            error.code if isinstance(error, HTTPError) else type(error).__name__)
            self.add("source_available", 0, source=name)
            return None
        self.add("source_available", int(value is not None), source=name)
        return value


def github_runs(repo, workflow, count):
    return gh(f"{repo}/actions/workflows/{workflow}/runs", {"per_page": count})["workflow_runs"]


@functools.lru_cache(maxsize=2048)
def completed_jobs(repo, run_id, attempt):
    result = gh(f"{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs", {"per_page": 100})
    jobs = result["jobs"]
    if len(jobs) != result["total_count"] or any(job["status"] != "completed" for job in jobs):
        raise ValueError("incomplete jobs")
    return jobs


def ci_metrics(metrics, repo, runs):
    if not runs:
        return
    latest = max(runs, key=lambda run: run["created_at"])
    metrics.add("ci_last_run_timestamp_seconds", timestamp(latest["created_at"]),
                status=latest.get("conclusion") or latest["status"], run_id=latest["id"],
                sha=latest.get("head_sha", ""))
    partial = False
    jobs_unavailable = False
    events = []
    for run in runs:
        if run["status"] != "completed" or not run["conclusion"]:
            continue
        labels = dict(run_id=run["id"], attempt=run["run_attempt"], conclusion=run["conclusion"])
        # GitHub exposes updated_at on runs. Job completion gives a more precise
        # end time for the duration when all jobs are available.
        end = timestamp(run["updated_at"])
        labels["event_time"] = end
        metrics.add("ci_completed_timestamp_seconds", end, **labels)
        events.append(end)
        if jobs_unavailable:
            continue
        try:
            jobs = completed_jobs(repo, run["id"], run["run_attempt"])
        except (URLError, TimeoutError) as error:
            partial = True
            jobs_unavailable = not isinstance(error, HTTPError) or error.code != 404
            continue
        except ValueError:
            partial = True
            continue
        finishes = [timestamp(job["completed_at"]) for job in jobs if job.get("completed_at")]
        if finishes and run.get("run_started_at"):
            duration = max(finishes) - timestamp(run["run_started_at"])
            if duration >= 0:
                metrics.add("ci_duration_seconds", duration, **labels)
        for kind, names in {
            "build": {"build", "dotnet build", "build image", "build image outside the restricted network"},
            "test": {"dotnet test", "npm run test:unit", "cypress"},
        }.items():
            conclusions = {
                step.get("conclusion") for job in jobs for step in [job, *job.get("steps", [])]
                if step["name"].lower().split(" / ")[-1].removeprefix("run ") in names
            }
            if conclusions & (FAILURE | {"success"}):
                metrics.add("ci_check_failed", int(bool(conclusions & FAILURE)), check=kind, **labels)
    metrics.add("source_available", int(not partial), source="github_ci_jobs")
    if events:
        metrics.add("ci_oldest_observed_timestamp_seconds", min(events))


def quality_metrics(metrics, project):
    if not project:
        metrics.add("source_available", 0, source="sonar_measures")
        metrics.add("source_available", 0, source="sonar_gate")
        return
    result = metrics.source("sonar_measures", lambda: sonar(
        "/api/measures/component", {"component": project, "metricKeys": ",".join(SONAR_METRICS)}))
    if result:
        for measure in result["component"]["measures"]:
            if measure.get("value") is not None:
                metrics.add("sonar_measure", float(measure["value"]), measure=measure["metric"])
    gate = metrics.source("sonar_gate", lambda: sonar(
        "/api/qualitygates/project_status", {"projectKey": project}))
    if gate:
        metrics.add("sonar_gate_info", status=gate["projectStatus"]["status"])


def gitops_reference(contents, image):
    """Read the repository's block-style Kustomize images entries, as promotion does."""
    block = re.search(r"^images:\s*\n((?:[ \t].*\n|\s*\n)*)", contents + "\n", re.M)
    if not block:
        raise ValueError("missing images")
    matches = []
    for entry in re.split(r"(?m)^\s*-[ \t]+", block.group(1))[1:]:
        fields = dict(re.findall(r"(?m)^[ \t]*(name|newName|newTag|digest):[ \t]*([^\s#]+)", entry))
        if fields.get("newName", fields.get("name")) == image:
            matches.append(fields)
    if len(matches) != 1 or not matches[0].get("newTag"):
        raise ValueError("ambiguous image")
    fields = matches[0]
    digest = fields.get("digest", "")
    if digest and not DIGEST.fullmatch(digest):
        raise ValueError("invalid declared digest")
    return fields["newTag"], digest


def gitops_image(service, image):
    path = f'apps/{service["service"]}/overlays/k3s/kustomization.yaml'
    revisions = gh(f"{GITOPS}/commits", {"sha": "main", "path": path, "per_page": 1})
    revision = revisions[0]
    contents = gh(f"{GITOPS}/contents/{path}", {"ref": revision["sha"]}, raw=True)
    tag, digest = gitops_reference(contents, image)
    message = revision["commit"]["message"].splitlines()
    source_prefix = f'Source: {ORG}/{service["repository"]}@'
    source_sha = ""
    if digest and f"Digest: {digest}" in message:
        source_sha = next((evidence(line.removeprefix(source_prefix), SHA)
                           for line in message if line.startswith(source_prefix)), "")
    return tag, digest, source_sha


def argo_metrics(metrics, application):
    status = application.get("status", {})
    sync = status.get("sync", {})
    metrics.add("argo_application_info", health=status.get("health", {}).get("status", "Unknown"),
                sync=sync.get("status", "Unknown"), gitops_revision=sync.get("revision", ""))
    history = status.get("history", [])
    if history:
        last = max(history, key=lambda item: item["deployedAt"])
        metrics.add("argo_last_successful_sync_timestamp_seconds", timestamp(last["deployedAt"]),
                    gitops_revision=last["revision"])
    operation = status.get("operationState", {})
    if operation.get("phase"):
        metrics.add("argo_last_operation_info", phase=operation["phase"])
    finished = operation.get("finishedAt")
    dry_run = operation.get("operation", {}).get("sync", {}).get("dryRun")
    if finished and not dry_run and operation.get("phase") in {"Error", "Failed"}:
        when = timestamp(finished)
        metrics.add("argo_sync_failed", 1, event_time=when, operation_id=finished)


def controlled_by(obj, uid):
    return any(ref.get("controller") and ref["uid"] == uid
               for ref in obj["metadata"].get("ownerReferences", []))


def workload_state(service, image):
    ns = service["service"]
    prefix = f"/apis/apps/v1/namespaces/{ns}"
    deployment = kubernetes(f'{prefix}/deployments/{service["deployment"]}')
    match = deployment["spec"]["selector"]
    if match.get("matchExpressions") or not match.get("matchLabels"):
        raise ValueError("unsupported workload selector")
    query = {"labelSelector": ",".join(f"{key}={value}" for key, value in match["matchLabels"].items())}
    replica_sets = kubernetes(prefix + "/replicasets", query)["items"]
    owners = {rs["metadata"]["uid"] for rs in replica_sets if controlled_by(rs, deployment["metadata"]["uid"])}
    pods = kubernetes(f"/api/v1/namespaces/{ns}/pods", query)["items"]
    active = [pod for pod in pods if pod.get("status", {}).get("phase") not in {"Succeeded", "Failed"}
              and not pod["metadata"].get("deletionTimestamp") and any(controlled_by(pod, uid) for uid in owners)]
    running = []
    for pod in active:
        status = pod.get("status", {})
        for container in status.get("containerStatuses", []):
            if container["name"] != service["container"] or "running" not in container.get("state", {}):
                continue
            image_id = container.get("imageID", "")
            reference = image_id.split("://", 1)[-1]
            digest = evidence(reference.removeprefix(image + "@"), DIGEST) if reference.startswith(image + "@") else ""
            ready = container.get("ready") and any(item["type"] == "Ready" and item["status"] == "True"
                                                   for item in status.get("conditions", []))
            running.append(dict(pod=pod["metadata"]["name"], image=container["image"], image_id=image_id,
                                digest=digest, ready=bool(ready)))
    spec, status = deployment["spec"], deployment.get("status", {})
    desired = spec.get("replicas", 1)
    available = status.get("availableReplicas", 0)
    observed = status.get("observedGeneration") == deployment["metadata"]["generation"]
    complete = (observed and desired == available == status.get("updatedReplicas", 0)
                == status.get("replicas", 0) == len(active))
    failed = observed and any(condition.get("reason") in {"ProgressDeadlineExceeded", "ReplicaSetCreateError", "FailedCreate"}
                              for condition in status.get("conditions", []))
    health = dict(active_pods=[pod["metadata"]["name"] for pod in active],
                  ready_pods=sum(any(condition["type"] == "Ready" and condition["status"] == "True"
                                     for condition in pod.get("status", {}).get("conditions", [])) for pod in active))
    app_status = [container for pod in active for container in pod.get("status", {}).get("containerStatuses", [])
                  if container["name"] == service["container"]]
    health["active_container_restarts"] = sum(container["restartCount"] for container in app_status)
    health["crashloop_containers"] = sum(container.get("state", {}).get("waiting", {}).get("reason") == "CrashLoopBackOff"
                                         for container in app_status)
    template_resources = next((container.get("resources", {}) for container in spec["template"]["spec"]["containers"]
                               if container["name"] == service["container"]), {})
    return dict(health, running=running, desired=desired, available=available, resources=template_resources,
                rollout="scaled_down" if desired == 0 else "complete" if complete else "failed" if failed else "progressing")


def quantity(value):
    match = QUANTITY.fullmatch(str(value))
    if not match:
        raise ValueError("invalid Kubernetes quantity")
    number, suffix = match.groups()
    if suffix and len(suffix) > 1 and suffix[0] in "eE" and suffix[1:] != "i":
        return float(Decimal(number + suffix))
    if suffix not in QUANTITY_SCALE and suffix is not None:
        raise ValueError("unsupported Kubernetes quantity")
    return float(Decimal(number) * QUANTITY_SCALE[suffix or ""])


def pod_usage(service, workload):
    active = set(workload["active_pods"])
    if not active:
        return None
    samples = kubernetes(f'/apis/metrics.k8s.io/v1beta1/namespaces/{service["service"]}/pods')["items"]
    usage = {}
    for pod in samples:
        name = pod["metadata"]["name"]
        if name not in active:
            continue
        container = next((item for item in pod["containers"] if item["name"] == service["container"]), None)
        if container and {"cpu", "memory"} <= container["usage"].keys():
            usage[name] = container["usage"]
    if usage.keys() != active:
        return None
    return {resource: sum(quantity(item[resource]) for item in usage.values()) for resource in ("cpu", "memory")}


def workload_observations(metrics, service, workload):
    metrics.add("workload_rollout_info", status=workload["rollout"])
    for measure in ("desired", "available", "ready_pods", "active_container_restarts", "crashloop_containers"):
        metrics.add("workload_measure", workload[measure], measure=measure)
    metrics.add("workload_measure", len(workload["active_pods"]), measure="active_pods")
    for resource in ("cpu", "memory"):
        for dimension in ("requests", "limits"):
            amount = workload["resources"].get(dimension, {}).get(resource)
            if amount is not None:
                metrics.add("resource_measure", quantity(amount) * workload["desired"],
                            resource=resource, dimension=dimension)
    usage = metrics.source("kubernetes_usage", lambda: pod_usage(service, workload))
    if usage:
        for resource, value in usage.items():
            metrics.add("resource_measure", value, resource=resource, dimension="usage")
    for pod in workload["running"]:
        metrics.add("running_container_info", int(pod["ready"]), workload_pod=pod["pod"], image=pod["image"],
                    image_id=pod["image_id"], digest=pod["digest"])


def artifact_labels(artifact):
    attrs = artifact.get("extra_attrs") or {}
    config = attrs.get("config") or {}
    if not isinstance(config, dict):
        config = {}
    return ((artifact.get("annotations") or {}) | (attrs.get("labels") or {})
            | (config.get("Labels") or config.get("labels") or {}))


def scan_result(artifact):
    reports = artifact.get("scan_overview") or {}
    order = ("application/vnd.security.vulnerability.report; version=1.1",
             "application/vnd.scanner.adapter.vuln.report.harbor+json; version=1.0")
    return next((reports[mime] for mime in order if mime in reports), {})


def harbor_base(repo):
    return f"/api/v2.0/projects/lantern/repositories/{quote(repo, safe='')}/artifacts"


def harbor_artifacts(repo):
    return harbor(harbor_base(repo), {"page_size": 50, "sort": "-push_time",
                                      "with_tag": "true", "with_scan_overview": "true",
                                      "with_immutable_status": "true", "with_accessory": "true"})


def release_candidates(artifacts):
    candidates = [(tag["name"], artifact) for artifact in artifacts if artifact["type"] == "IMAGE"
                  and evidence(artifact.get("digest"), DIGEST) for tag in artifact.get("tags") or []
                  if RELEASE.fullmatch(tag["name"])]
    return sorted(candidates, key=lambda pair: tuple(map(int, pair[0][1:].split("."))), reverse=True)


def delivery_jobs(metrics, repo, runs, tags):
    verified = {}
    if not runs:
        return verified
    phases = {
        "scan_gate": "Enforce Harbor vulnerability scan gate",
        "signed": "Sign image by digest",
        "attested": "Attach signed provenance attestation",
        "signature_and_provenance_verified": "Verify signature",
        "published_digest_verified": "Verify published image",
    }
    releases = [run for run in runs if run["event"] == "push" and run["status"] == "completed"
                and run.get("head_branch") in tags]
    for run in sorted(releases, key=lambda item: item["updated_at"], reverse=True):
        tag = run["head_branch"]
        try:
            jobs = completed_jobs(repo, run["id"], run["run_attempt"])
        except Exception:
            metrics.add("delivery_jobs_available", 0, tag=tag, run_id=run["id"])
            continue
        steps = {step["name"]: step.get("conclusion") for job in jobs for step in job.get("steps", [])}
        build_steps = ("Build image", "Build image outside the restricted network", "Build and push")
        publish_steps = ("Tag and push image", "Load, tag and push prebuilt image", "Build and push")
        states = {phase: steps[step] for phase, step in phases.items() if step in steps}
        for phase, options in (("built", build_steps), ("published", publish_steps)):
            observed = next((steps[step] for step in options if steps.get(step) not in {None, "skipped"}), None)
            if observed:
                states[phase] = observed
        for phase, conclusion in states.items():
            metrics.add("delivery_step_info", tag=tag, sha=run["head_sha"], run_id=run["id"],
                        phase=phase, conclusion=conclusion or "unknown")
        if all(states.get(step) == "success" for step in (*phases, "built", "published")):
            verified.setdefault(tag, run["head_sha"])
    return verified


def image_metrics(metrics, repo, artifacts, verified, desired, workload, argo):
    releases = release_candidates(artifacts)
    def registry_url(digest):
        return f"https://{REGISTRY}{harbor_base(repo)}/{digest}"

    if releases:
        tag, artifact = releases[0]
        metrics.add("image_info", stage="latest_release", tag=tag, digest=artifact["digest"],
                    registry_url=registry_url(artifact["digest"]),
                    source_sha=evidence(artifact_labels(artifact).get("org.opencontainers.image.revision"), SHA))
    published = max(
        (artifact for artifact in artifacts if artifact["type"] == "IMAGE"
         and artifact.get("tags") and evidence(artifact.get("digest"), DIGEST)),
        key=lambda artifact: artifact["push_time"], default=None,
    )
    if published:
        tags = sorted(tag["name"] for tag in published["tags"])
        metrics.add("image_info", stage="latest_published", tag=", ".join(tags), digest=published["digest"],
                    registry_url=registry_url(published["digest"]), source_sha=evidence(artifact_labels(published).get("org.opencontainers.image.revision"), SHA))

    validated = None
    for tag, artifact in releases:
        sha = verified.get(tag)
        if not sha:
            continue
        digest = artifact["digest"]
        report = scan_result(artifact)
        counts = (report.get("summary") or {}).get("summary")
        oci_sha = evidence(artifact_labels(artifact).get("org.opencontainers.image.revision"), SHA)
        immutable = any(item["name"] == tag and item.get("immutable") is True for item in artifact["tags"])
        promotion_matches = desired == (tag, digest, sha)
        tag_matches = immutable and oci_sha == sha
        can_validate = ((promotion_matches or tag_matches) and (not oci_sha or oci_sha == sha)
                        and report.get("scan_status") == "Success" and isinstance(counts, dict)
                        and counts.get("Critical", 0) == 0)
        if can_validate:
            validated = digest
            metrics.add("image_info", stage="latest_observed_validated_release", tag=tag,
                        digest=digest, source_sha=sha, registry_url=registry_url(digest),
                        evidence="promotion_commit" if promotion_matches else "immutable_tag_and_oci_revision")
            break

    running_digests = {pod["digest"] for pod in workload["running"] if pod["digest"]} if workload else set()
    published_digest = published["digest"] if published else ""
    observed_digests = {"running": running_digests, "latest_published": {published_digest} - {""}}
    if validated:
        observed_digests["latest_observed_validated_release"] = {validated}
    artifacts_by_digest = {artifact["digest"]: artifact for artifact in artifacts}
    for stage, digests in observed_digests.items():
        for digest in sorted(digests):
            artifact = artifacts_by_digest.get(digest)
            if not artifact or not scan_result(artifact):
                try:
                    artifact = harbor(f"{harbor_base(repo)}/{digest}", {"with_scan_overview": "true", "with_tag": "true", "with_accessory": "true"})
                except Exception:
                    continue
            report = scan_result(artifact)
            metrics.add("harbor_scan_info", digest=digest, stage=stage, status=report.get("scan_status", "Unknown"))
            for accessory in artifact.get("accessories") or []:
                accessory_type = accessory.get("type", "")
                accessory_digest = evidence(accessory.get("digest"), DIGEST)
                if accessory_digest and ("signature" in accessory_type or "attestation" in accessory_type):
                    metrics.add("harbor_accessory_info", stage=stage, digest=digest, accessory_type=accessory_type,
                                accessory_digest=accessory_digest)
            counts = (report.get("summary") or {}).get("summary")
            if report.get("scan_status") == "Success" and counts is not None:
                for severity in SEVERITIES:
                    metrics.add("image_vulnerabilities", counts.get(severity, 0),
                                digest=digest, stage=stage, severity=severity)
            sha = evidence(artifact_labels(artifact).get("org.opencontainers.image.revision"), SHA)
            if not sha and desired and desired[1] == digest:
                sha = desired[2]
            if stage == "running":
                metrics.add("image_info", stage="running", digest=digest, registry_url=registry_url(digest), tag=", ".join(
                    sorted(tag["name"] for tag in artifact.get("tags") or [])), source_sha=sha)

    comparable = bool(workload and workload["running"]) and all(pod["digest"] for pod in workload["running"])
    if comparable and published_digest:
        metrics.add("running_image_matches", int(running_digests == {published_digest}), reference="latest_published")
    if not comparable or not argo or not desired or not desired[1]:
        metrics.add("delivery_assessment_info", status="insufficient_evidence")
        return
    matches_gitops = running_digests == {desired[1]}
    metrics.add("running_image_matches", int(matches_gitops), reference="gitops")
    argo_status = argo.get("status", {})
    sync = argo_status.get("sync", {})
    healthy = (workload["rollout"] == "complete" and workload["desired"] > 0
               and len(workload["running"]) == workload["desired"]
               and all(pod["ready"] for pod in workload["running"]))
    synchronized = (sync.get("status") == "Synced"
                    and argo_status.get("health", {}).get("status") == "Healthy")
    if healthy and synchronized and matches_gitops:
        history = [item for item in argo_status.get("history", []) if item["revision"] == sync.get("revision")]
        if history:
            last = max(history, key=lambda item: item["deployedAt"])
            metrics.add("healthy_matching_sync_timestamp_seconds", timestamp(last["deployedAt"]))

    if not validated:
        assessment = "insufficient_evidence"
    elif healthy and synchronized and matches_gitops and desired[1] == validated:
        assessment = "confirmed"
    else:
        assessment = "differs_or_unhealthy"
    metrics.add("delivery_assessment_info", status=assessment)


def collect(service, metrics):
    ns, name = service["service"], service["repository"]
    repo = f"/repos/{ORG}/{name}"
    image = f"{REGISTRY}/lantern/{name}"
    metrics.add("service_info", 1, deployment=service["deployment"], container=service["container"],
                github_url=f"https://github.com/{ORG}/{name}",
                sonar_url=f'https://sonarcloud.io/dashboard?id={service["sonar"]}' if service["sonar"] else "",
                harbor_url=f"https://{REGISTRY}{harbor_base(name)}",
                argocd_url=f"https://10.4.111.200:8443/applications/argocd/{ns}")

    commit = metrics.source("github_commit", lambda: gh(f"{repo}/commits", {"per_page": 1}))
    if commit:
        metrics.add("github_latest_commit_info", sha=commit[0]["sha"])

    runs = metrics.source("github_ci", lambda: github_runs(repo, service["ci"], 50))
    if runs is not None:
        ci_metrics(metrics, repo, runs)

    quality_metrics(metrics, service["sonar"])
    argo = metrics.source("argocd", lambda: kubernetes(f"/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/{ns}"))
    if argo is not None:
        argo_metrics(metrics, argo)

    workload = metrics.source("kubernetes", lambda: workload_state(service, image))
    if workload:
        workload_observations(metrics, service, workload)
    else:
        metrics.add("source_available", 0, source="kubernetes_usage")

    desired = metrics.source("gitops", lambda: gitops_image(service, image))
    if desired:
        metrics.add("image_info", stage="gitops", tag=desired[0], digest=desired[1], source_sha=desired[2])

    artifacts = metrics.source("harbor", lambda: harbor_artifacts(name))
    cd_runs = metrics.source("github_delivery", lambda: github_runs(repo, service["cd"], 50))
    tags = {tag for tag, _ in release_candidates(artifacts or [])}
    if cd_runs:
        tags.update(run["head_branch"] for run in cd_runs if RELEASE.fullmatch(run.get("head_branch") or ""))
    verified = delivery_jobs(metrics, repo, cd_runs, tags)
    image_metrics(metrics, name, artifacts or [], verified, desired, workload, argo)


def collect_service(service):
    metrics = Observations(service)
    try:
        collect(service, metrics)
    except (ValueError, KeyError, TypeError, IndexError) as error:
        logging.error("%s snapshot %s", service["service"], type(error).__name__)
        metrics.add("source_available", 0, source="collector")
    return metrics.rows


def emit_snapshot(rows, snapshot, recent_events):
    service_id = None
    for row in rows:
        if row["kind"] in EVENT_KINDS:
            event = json.dumps(row, sort_keys=True, separators=(",", ":"))
            if event in recent_events:
                recent_events.move_to_end(event)
                continue
            recent_events[event] = None
            if len(recent_events) > 6000:
                recent_events.popitem(last=False)
        else:
            service_id = row["service_id"]
        print("LANTERN_KPI " + json.dumps(dict(row, snapshot=snapshot), separators=(",", ":")))
    # Emit a marker only after the service's snapshot rows have been written.
    if service_id:
        marker = dict(kind="collector_snapshot", service_id=service_id, snapshot=snapshot,
                      value=snapshot)
        print("LANTERN_KPI " + json.dumps(marker, separators=(",", ":")))


def poll():
    recent_events = OrderedDict()
    with ThreadPoolExecutor(max_workers=7) as pool:
        while True:
            start = time.monotonic()
            for rows in pool.map(collect_service, SERVICES):
                emit_snapshot(rows, time.time_ns() // 1_000_000, recent_events)
            time.sleep(max(1, INTERVAL - (time.monotonic() - start)))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    poll()
