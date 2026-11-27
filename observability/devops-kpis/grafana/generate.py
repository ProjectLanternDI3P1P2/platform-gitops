"""Render the four version-controlled Lantern Grafana dashboards."""
import argparse
import json
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
SERVICES = json.loads((ROOT.parent / "collector/services.json").read_text())
LOKI = {"type": "loki", "uid": "${loki}"}
STREAM = '{job="kubernetes-pods",namespace="monitoring",container="lantern-kpi-collector"}'
APP_STREAM = ('{job="kubernetes-pods",namespace=~"${service:regex}",'
              'container=~"api|player-api|frontend-game|frontend-public"}')
ERROR = r'(?i)(^|[[:space:]"\[])(error|err|fail|fatal|critical)([[:space:]"\]:,]|$)'
WARN = r'(?i)(^|[[:space:]"\[])(warn|warning)([[:space:]"\]:,]|$)'
APP_ERRORS = APP_STREAM + ' |~ ' + json.dumps(ERROR + '|' + WARN)
SERVICE = 'service_id=~"${service:regex}"'
DEV = SERVICE + ' | repository=~"${repository:regex}" | squad=~"${squad:regex}"'
CI_SCOPE = 'event_time >= ${__from:date:seconds}'
ATTEMPT = ("service_id", "run_id", "attempt")
ACTIONS = 'https://github.com/ProjectLanternDI3P1P2/${__data.fields.repository}/actions/runs/${__data.fields.run_id}'
DETAIL = '/d/lantern-devops-service/lantern-service-detail?var-service=${__data.fields.service_id}&${__url_time_range}'


def aggregate(kind, group=("service_id",), *, window="15m", fields=(), filters=(), visible=SERVICE,
              aggregation="last_over_time"):
    identity = ("service_id", "repository", "squad")
    labels = ", ".join(dict.fromkeys((*identity, *group, *fields)))
    query = (f'{STREAM} |= "LANTERN_KPI " | regexp `LANTERN_KPI (?P<payload>\{{.*\}})$` '
             f'| line_format "{{{{.payload}}}}" | json kpi_kind="kind", kpi_value="value", {labels} '
             f'| kpi_kind="{kind}"')
    if visible:
        query += " | " + visible
    for clause in filters:
        query += " | " + clause
    return f'{aggregation}({query} | unwrap kpi_value | __error__="" [{window}]) by ({", ".join(group)})'


def latest(kind, columns=(), *, filters=(), visible=SERVICE):
    group = tuple(dict.fromkeys(("service_id", "snapshot", *(field for field in columns if field != "Value"))))
    values = aggregate(kind, group, filters=filters, visible=visible)
    marker = aggregate("collector_snapshot", ("service_id", "snapshot"), visible=SERVICE,
                       aggregation="max_over_time")
    return f"({values}) and on (service_id, snapshot) topk by (service_id) (1, {marker})"


def event(kind, group=ATTEMPT, *, window="$__range", filters=(), scope=True, visible=DEV):
    clauses = (*filters, CI_SCOPE) if scope else filters
    return aggregate(kind, group, window=window, fields=("event_time", "conclusion", "check"),
                     filters=clauses, visible=visible, aggregation="max_over_time")


def target(expr, legend="", query_type="range"):
    return dict(expr=expr, legendFormat=legend, queryType=query_type, datasource=LOKI, editorMode="code")


def field_link(field, title, url):
    return dict(matcher={"id": "byName", "options": field},
                properties=[{"id": "links", "value": [{"title": title, "url": url}]}])


def panel(title, mode, *targets, width=12, height=8, unit=None, description="", overrides=None):
    defaults = {"noValue": "Unavailable"}
    if unit:
        defaults["unit"] = unit
    options = {}
    if mode == "stat":
        options["reduceOptions"] = {"calcs": ["lastNotNull"], "fields": "", "values": False}
    if mode == "logs":
        options = {"showTime": True, "showLabels": False, "wrapLogMessage": True, "sortOrder": "Descending"}
    return dict(title=title, type=mode, datasource=LOKI if targets else None, description=description,
                gridPos=dict(w=width, h=height), options=options,
                fieldConfig=dict(defaults=defaults, overrides=overrides or []),
                targets=[dict(item, refId=chr(65 + index)) for index, item in enumerate(targets)])


def table(title, expr, columns, *, date=False, description="", links=(), width=12):
    overrides = [field_link(*link) for link in links]
    if date:
        overrides.append({"matcher": {"id": "byName", "options": "Value"},
                          "properties": [{"id": "unit", "value": "dateTimeAsIso"}]})
        expr = f"1000 * ({expr})"
    result = panel(title, "table", target(expr, query_type="instant"), description=description,
                   overrides=overrides, width=width)
    result["transformations"] = [
        {"id": "labelsToFields", "options": {"mode": "columns"}},
        {"id": "organize", "options": {
            "excludeByName": {field: True for field in ("Time", "snapshot", "Value") if field not in columns},
            "indexByName": {field: index for index, field in enumerate(columns)},
        }},
    ]
    return result


def current(title, kind, columns, *, filters=(), visible=SERVICE, **options):
    return table(title, latest(kind, columns, filters=filters, visible=visible), columns, **options)


def note(content):
    result = panel("", "text", width=24, height=3)
    result["options"] = {"mode": "markdown", "content": content}
    return result


def variable(name, label, items, multi=True):
    return dict(name=name, label=label, type="custom", query=",".join(items),
                multi=multi, includeAll=multi,
                allValue="|".join(items) if multi else None,
                current={"text": "All", "value": "$__all"} if multi else {"text": items[0], "value": items[0]},
                options=[{"text": item, "value": item, "selected": not multi and item == items[0]} for item in items])


def variables(development=False, detail=False):
    result = [dict(name="loki", label="Kubernetes Loki", type="datasource", query="loki", refresh=1,
                   multi=False, includeAll=False, options=[])]
    if development:
        result.extend([
            variable("squad", "Squad", sorted({item["squad"] for item in SERVICES})),
            variable("repository", "Repository", [item["repository"] for item in SERVICES]),
        ])
    result.append(variable("service", "Service", [item["service"] for item in SERVICES], multi=not detail))
    return result


def dashboard(uid, title, templating, panels, days="7d"):
    x = y = height = 0
    for index, item in enumerate(panels, 1):
        pos = item["gridPos"]
        if x + pos["w"] > 24:
            x, y, height = 0, y + height, 0
        pos.update(x=x, y=y)
        item["id"] = index
        x += pos["w"]
        height = max(height, pos["h"])
    return dict(uid=uid, title=title, tags=["Lantern", "DevOps"], schemaVersion=39, editable=False,
                refresh="5m", time={"from": f"now-{days}", "to": "now"}, timezone="browser",
                links=[{"type": "dashboards", "title": "Lantern DevOps", "tags": ["Lantern"],
                        "keepTime": True, "asDropdown": True}],
                templating={"list": templating}, panels=panels)


def sources(visible=SERVICE, filters=()):
    return current("Source availability", "source_available", ["service_id", "source", "Value"],
                   visible=visible, filters=filters,
                   description="1 = source responded, 0 = unavailable or unconfigured. Empty = no fresh observation.")


def ci_latest(visible=SERVICE):
    return current("Last CI execution", "ci_last_run_timestamp_seconds", ["service_id", "repository", "status", "sha", "run_id", "Value"],
                   date=True, visible=visible, links=[("run_id", "Open GitHub Actions run", ACTIONS)])


def sonar_gate(visible=SERVICE):
    return current("SonarQube Quality Gate", "sonar_gate_info", ["service_id", "status"], visible=visible)


def sonar_measure(title, regex, unit=None, visible=SERVICE):
    expr = aggregate("sonar_measure", ("service_id", "measure"), visible=visible, filters=(f'measure=~"{regex}"',))
    return panel(title, "timeseries", target(expr, "{{service_id}} · {{measure}}"), unit=unit)


def development():
    eligible = event("ci_completed_timestamp_seconds", filters=('conclusion=~"success|failure|timed_out|startup_failure"',))
    total = f"count by (service_id) ({eligible})"
    panels = [note("CI uses observed attempts from the latest 50 runs per repository. "
                   "Historical trends start when Loki receives observations. Select the existing Kubernetes Loki datasource.")]
    for outcome, condition in (("success", "success"), ("failure", "failure|timed_out|startup_failure")):
        events = event("ci_completed_timestamp_seconds", filters=(f'conclusion=~"{condition}"',))
        count = f"count by (service_id) ({events})"
        expr = f"100 * (({count}) or on (service_id) (0 * {total})) / ({total})"
        panels.append(panel(f"CI {outcome} rate", "stat", target(expr, "{{service_id}}", "instant"), width=6, unit="percent"))
    duration = event("ci_duration_seconds")
    duration_trend = event("ci_duration_seconds", window="1d", scope=False)
    oldest = current("Oldest observed CI completion", "ci_oldest_observed_timestamp_seconds",
                     ["service_id", "Value"], date=True, visible=DEV, width=6)
    panels += [
        panel("Average CI duration", "stat", target(f"avg by (service_id) ({duration})", "{{service_id}}", "instant"),
              width=6, unit="s"),
        oldest,
        ci_latest(DEV),
        panel("Daily average duration of recorded CI attempts", "timeseries",
              target(f"avg by (service_id) ({duration_trend})", "{{service_id}}"), unit="s",
              description="Uses observation time in Loki. At initial collection, recent completed runs are recorded together."),
    ]
    for kind in ("build", "test"):
        failed = event("ci_check_failed", filters=(f'check="{kind}"',))
        panels.append(panel(f"CI runs with failed {kind} checks", "stat",
                            target(f"sum by (service_id) ({failed})", "{{service_id}}", "instant")))
    panels += [
        sonar_gate(DEV), sources(DEV, ('source=~"github_ci.*|sonar_.*"',)),
        sonar_measure("Test coverage", "coverage", "percent", DEV),
        sonar_measure("Code duplication", "duplicated_lines_density", "percent", DEV),
        sonar_measure("Technical debt", "sqale_index", "m", DEV),
        sonar_measure("Bugs, vulnerabilities and code smells", "bugs|vulnerabilities|code_smells", visible=DEV),
        sonar_measure("Software quality issues", "software_quality_.*_issues", visible=DEV),
    ]
    return dashboard("lantern-devops-development", "Lantern · Development & Code Quality", variables(development=True), panels)


def image_table(title, stages):
    return current(title, "image_info", ["service_id", "stage", "tag", "digest", "source_sha", "evidence", "registry_url"],
                   filters=(f'stage=~"{stages}"',),
                   links=[("service_id", "Open service detail", DETAIL), ("registry_url", "Open Harbor artifact", "${__value.raw}")])


def runtime_table():
    return current("Running pod images and readiness", "running_container_info",
                   ["service_id", "workload_pod", "image", "image_id", "digest", "Value"],
                   description="1 = pod and application container are Ready. Digest comparisons require a registry-qualified digest.")


def argo_table():
    return current("Argo CD application status", "argo_application_info", ["service_id", "health", "sync", "gitops_revision"])


def assessment():
    return current("Release delivery assessment", "delivery_assessment_info", ["service_id", "status"],
                   links=[("service_id", "Open service detail", DETAIL)])


def deployments():
    failures = event("argo_sync_failed", ("service_id", "operation_id"), visible=SERVICE)
    healthy_sync = aggregate("healthy_matching_sync_timestamp_seconds", window="$__range", aggregation="max_over_time")
    rollout = aggregate("workload_rollout_info", ("service_id", "status"), window="$__range",
                        filters=('status="failed"',), aggregation="max_over_time")
    panels = [
        note("Confirmation requires matching GitOps and running digests, a complete healthy rollout and Argo CD Synced/Healthy. "
             "Choose Kubernetes Loki to load the observations."),
        assessment(),
        table("Latest healthy matching deployment observed", healthy_sync, ["service_id", "Value"], date=True),
        image_table("Harbor publications and validated releases", "latest.*"),
        image_table("GitOps declaration and runtime image metadata", "gitops|running"),
        runtime_table(),
        current("Image comparisons", "running_image_matches", ["service_id", "reference", "Value"],
                description="1 = all observed running digests match the reference. 0 = digests differ. Empty = evidence unavailable."),
        argo_table(),
        current("Last successful Argo CD synchronization", "argo_last_successful_sync_timestamp_seconds",
                ["service_id", "gitops_revision", "Value"], date=True),
        current("Latest Argo CD operation", "argo_last_operation_info", ["service_id", "phase"]),
        table("Argo CD sync failures observed", f"count by (service_id) ({failures})", ["service_id", "Value"],
              description="Counts distinct failures sampled from Application status. Short-lived failures may be missed."),
        table("Kubernetes rollout failures observed", rollout, ["service_id", "status"]),
        current("Release workflow evidence", "delivery_step_info", ["service_id", "repository", "tag", "sha", "phase", "conclusion", "run_id"],
                width=24, links=[("run_id", "Open release workflow run", ACTIONS)]),
        current("Harbor scan status", "harbor_scan_info", ["service_id", "stage", "digest", "status"]),
        current("Harbor signature and attestation metadata", "harbor_accessory_info",
                ["service_id", "stage", "digest", "accessory_type", "accessory_digest"]),
        current("Vulnerabilities by image and severity", "image_vulnerabilities",
                ["service_id", "stage", "digest", "severity", "Value"]),
        sources(),
    ]
    return dashboard("lantern-devops-deployments", "Lantern · Deployments & Container Security", variables(), panels)


def workload_panel(title, regex):
    expr = aggregate("workload_measure", ("service_id", "measure"), filters=(f'measure=~"{regex}"',), window="10m")
    return panel(title, "timeseries", target(expr, "{{service_id}} · {{measure}}"))


def replicas():
    return workload_panel("Desired and available replicas", "desired|available")


def resources():
    result = []
    for resource, title, unit in (("cpu", "CPU", "suffix: cores"), ("memory", "Memory", "bytes")):
        expr = aggregate("resource_measure", ("service_id", "dimension"), fields=("resource",),
                         filters=(f'resource="{resource}"',), window="10m")
        result.append(panel(f"{title} usage, requests and limits", "timeseries",
                            target(expr, "{{service_id}} · {{dimension}}"), unit=unit,
                            description="Usage comes from the K3s resource metrics API. Requests and limits describe the desired replicas."))
    return result


def log_panel(heading):
    result = panel(heading, "logs", target(APP_ERRORS), width=24, height=10)
    marker = "LANTERN_SERVICE_TOKEN"
    expr = APP_ERRORS.replace("${service:regex}", marker)
    explore = {"logs": {"datasource": "${loki}", "queries": [{"refId": "A", "expr": expr, "queryType": "range"}],
                        "range": {"from": "${__from}", "to": "${__to}"}}}
    panes = quote(json.dumps(explore, separators=(",", ":")), safe="").replace(marker, "${service:regex}")
    for name in ("loki", "__from", "__to"):
        variable_expression = "${" + name + "}"
        panes = panes.replace(quote(variable_expression, safe=""), variable_expression)
    result["links"] = [{"title": "Open application logs in Explore", "url": "/explore?schemaVersion=1&panes=" + panes}]
    return result


def health():
    panels = [
        current("Workload rollout status", "workload_rollout_info", ["service_id", "status"],
                links=[("service_id", "Open service detail", DETAIL)]),
        argo_table(),
        replicas(),
        workload_panel("Ready and observed application pods", "ready_pods|active_pods"),
        workload_panel("Restart count in active application containers", "active_container_restarts"),
        workload_panel("Containers in CrashLoopBackOff", "crashloop_containers"),
        *resources(),
        panel("Application error and warning log lines", "timeseries", *(
            target(f'sum by (namespace) (count_over_time({APP_STREAM} |~ {json.dumps(pattern)} [$__interval]))',
                   "{{namespace}} " + severity)
            for severity, pattern in (("errors", ERROR), ("warnings", WARN)))),
        log_panel("Application errors and warnings"),
        sources(filters=('source=~"kubernetes.*|argocd"',)),
    ]
    return dashboard("lantern-devops-health", "Lantern · Kubernetes & Microservices Health", variables(), panels, "24h")


def detail():
    links = [(field, title, "${__value.raw}") for field, title in [
        ("github_url", "Open repository"), ("sonar_url", "Open SonarQube Cloud"),
        ("harbor_url", "Open Harbor"), ("argocd_url", "Open Argo CD"),
    ]]
    panels = [
        current("Service links", "service_info",
                ["service_id", "repository", "github_url", "sonar_url", "harbor_url", "argocd_url"], width=24, links=links),
        current("Latest default-branch commit", "github_latest_commit_info", ["service_id", "repository", "sha"],
                links=[("sha", "Open commit", "https://github.com/ProjectLanternDI3P1P2/${__data.fields.repository}/commit/${__value.raw}")]),
        ci_latest(),
        sonar_gate(),
        sonar_measure("SonarQube coverage", "coverage", "percent"),
        image_table("Published, promoted and running image metadata", "latest_published|gitops|running"),
        runtime_table(),
        argo_table(),
        assessment(),
        replicas(),
        *resources(),
        sources(),
        log_panel("Recent application errors and warnings"),
    ]
    return dashboard("lantern-devops-service", "Lantern · Service Detail", variables(detail=True), panels, "24h")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    check = parser.parse_args().check
    for name, render in (("development", development), ("deployments", deployments),
                         ("health", health), ("service", detail)):
        path = ROOT / "dashboards" / f"{name}.json"
        content = json.dumps(render(), ensure_ascii=False, indent=2) + "\n"
        if check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f"{path.name} is out of date. Run {Path(__file__).name}.")
        else:
            path.write_text(content)


if __name__ == "__main__":
    main()
