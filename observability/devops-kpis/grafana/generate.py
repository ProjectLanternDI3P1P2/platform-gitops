"""Render the four version-controlled Lantern Grafana dashboards."""
import argparse
import json
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
SERVICES = json.loads((ROOT.parent / "collector/services.json").read_text())
ALL_SERVICES = "|".join(service["service"] for service in SERVICES)
PROM = {"type": "prometheus", "uid": "lantern-devops-prometheus"}
LOKI = {"type": "loki", "uid": "${loki}"}
IDENTITY = 'service=~"${service:regex}"'
DEVELOPMENT = IDENTITY + ',repository=~"${repository:regex}",squad=~"${squad:regex}"'
WORKLOAD = 'namespace=~"${service:regex}"'
APP_CONTAINERS = 'container=~"api|player-api|frontend-game|frontend-public"'
APP_PODS = 'pod=~"(api|player-api|frontend-game|frontend-public)-[a-z0-9]+-[a-z0-9]+"'
ACTIONS = 'https://github.com/ProjectLanternDI3P1P2/${__data.fields.repository}/actions/runs/${__data.fields.run_id}'
DETAIL = '/d/lantern-devops-service/lantern-service-detail?var-service=${__data.fields.service}&${__url_time_range}'
ERROR = '(?i)(^|[[:space:]"\\[])(error|err|fail|fatal|critical)([[:space:]"\\]:,]|$)'
WARN = '(?i)(^|[[:space:]"\\[])(warn|warning)([[:space:]"\\]:,]|$)'
LOG_STREAM = '{job="kubernetes-pods",' + WORKLOAD + ',' + APP_CONTAINERS + '}'
LOG_QUERY = LOG_STREAM + ' |~ ' + json.dumps(ERROR + '|' + WARN)


def metric(name, labels=IDENTITY, extra=""):
    return f"lantern_{name}{{{labels}{',' + extra if extra else ''}}}"


def prom(expr, legend="", table=False, instant=False):
    return dict(expr=expr, legendFormat=legend, format="table" if table else "time_series",
                instant=table or instant, range=not (table or instant), datasource=PROM)


def logs(expr, legend=""):
    return dict(expr=expr, legendFormat=legend, queryType="range", datasource=LOKI)


def field_link(field, title, url):
    return dict(matcher={"id": "byName", "options": field},
                properties=[{"id": "links", "value": [{"title": title, "url": url}]}])


def panel(title, mode, *targets, width=12, height=8, unit=None, description="", overrides=None):
    ds = targets[0]["datasource"] if targets else None
    defaults = {"noValue": "Unavailable"}
    if unit:
        defaults["unit"] = unit
    options = {}
    if mode == "stat":
        options["reduceOptions"] = {"calcs": ["lastNotNull"], "fields": "", "values": False}
    if mode == "logs":
        options = {"showTime": True, "showLabels": False, "wrapLogMessage": True, "sortOrder": "Descending"}
    result = dict(title=title, type=mode, datasource=ds, description=description,
                  gridPos=dict(w=width, h=height), options=options,
                  fieldConfig=dict(defaults=defaults, overrides=overrides or []),
                  targets=[dict(target, refId=chr(65 + index)) for index, target in enumerate(targets)])
    return result


def table(title, expr, *, columns=None, date=False, description="", links=None, width=12):
    overrides = [field_link(*link) for link in (links or [])]
    if date:
        overrides.append({"matcher": {"id": "byName", "options": "Value"},
                          "properties": [{"id": "unit", "value": "dateTimeAsIso"}]})
        expr = f"1000 * ({expr})"
    result = panel(title, "table", prom(expr, table=True), description=description, overrides=overrides, width=width)
    missing = ("Time", "__name__", "job", "instance", "endpoint", "namespace", "pod",
               "container", "deployment", "repository", "squad", "Value")
    exclude = {name: True for name in missing if not columns or name not in columns}
    if columns:
        result["transformations"] = [{"id": "organize", "options": {
            "excludeByName": exclude,
            "indexByName": {name: index for index, name in enumerate(columns)},
        }}]
    return result


def note(text):
    result = panel("", "text", width=24, height=3)
    result["options"] = {"mode": "markdown", "content": text}
    return result


def variable(name, label, query, multi=True):
    return dict(name=name, label=label, type="query", datasource=PROM, definition=query,
                query={"query": query, "refId": f"var-{name}"}, refresh=1,
                multi=multi, includeAll=multi, allValue=(ALL_SERVICES if name == "service" else ".*") if multi else None,
                current={"text": "All", "value": "$__all"} if multi else {"text": "combat", "value": "combat"})


def datasource_variables(development=False, detail=False, loki=False):
    variables = []
    if development:
        variables.extend([
            variable("squad", "Squad", "label_values(lantern_service_info, squad)"),
            variable("repository", "Repository",
                     'label_values(lantern_service_info{squad=~"${squad:regex}"}, repository)'),
        ])
    selected = 'lantern_service_info{repository=~"${repository:regex}",squad=~"${squad:regex}"}' if development else "lantern_service_info"
    variables.append(variable("service", "Service", f"label_values({selected}, service)", multi=not detail))
    if loki:
        variables.append(dict(name="loki", label="Kubernetes Loki", type="datasource", query="loki",
                              refresh=1, multi=False, includeAll=False, options=[]))
    return variables


def dashboard(uid, title, variables, panels, days="7d"):
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
                templating={"list": variables}, panels=panels)


def sources(labels=IDENTITY, extra=""):
    return table("Source availability", metric("source_available", labels, extra),
                 columns=["service", "source", "Value"],
                 description="1 = source responded, 0 = unavailable or not configured. Empty = no fresh collector sample.")


def ci_latest(labels=IDENTITY):
    return table("Last CI execution", metric("ci_last_run_timestamp_seconds", labels), date=True,
                 columns=["service", "repository", "status", "sha", "run_id", "Value"],
                 links=[("run_id", "Open GitHub Actions run", ACTIONS)])


def sonar_gate(labels=IDENTITY):
    return table("SonarQube Quality Gate", metric("sonar_gate_info", labels),
                 columns=["service", "status"], description="Default-branch analysis. A missing project or gate yields no row.")


def development():
    labels = DEVELOPMENT
    all_events = metric("ci_completed_timestamp_seconds", labels)
    def completion(selector, window):
        seconds = "$__range_s" if window == "$__range" else "86400"
        return f"max_over_time({selector}[{window}]) > time() - {seconds}"
    eligible = completion(metric("ci_completed_timestamp_seconds", labels, 'conclusion=~"success|failure|timed_out|startup_failure"'), "$__range")
    rates = []
    for outcome, condition in [("Success", "success"), ("Failure", "failure|timed_out|startup_failure")]:
        events = completion(metric("ci_completed_timestamp_seconds", labels, f'conclusion=~"{condition}"'), "$__range")
        count = f"count by(service) ({events})"
        total = f"count by(service) ({eligible})"
        rates.append(panel(f"CI {outcome.lower()} rate", "stat",
                           prom(f"100 * (({count}) or on(service) (0 * {total})) / ({total})",
                                "{{service}}", instant=True), width=6, unit="percent"))
    duration = metric("ci_duration_seconds", labels)
    def avg_duration(window, events):
        return (f"avg by(service) (last_over_time({duration}[{window}]) "
                f"and on(service,run_id,attempt,conclusion) ({events}))")
    panels = [
        note("CI covers the latest 50 workflow runs per repository, with jobs for the latest observed attempt. "
             "Rates exclude canceled, skipped and neutral runs. Sonar trends start when collection begins."),
        *rates,
        panel("Average CI duration", "stat", prom(avg_duration("$__range", completion(all_events, "$__range")),
              "{{service}}", instant=True), width=6, unit="s"),
        panel("Oldest observed CI completion", "stat",
              prom(f'1000 * {metric("ci_oldest_observed_timestamp_seconds", labels)}', "{{service}}", instant=True),
              width=6, unit="dateTimeAsIso"),
        ci_latest(labels),
        panel("Daily average CI duration", "timeseries",
              prom(avg_duration("1d", completion(all_events, "1d")), "{{service}}"), unit="s"),
    ]
    for kind in ("build", "test"):
        failed = metric("ci_check_failed", labels, f'check="{kind}"')
        events = completion(all_events, "$__range")
        expr = f"sum by(service) (max_over_time({failed}[$__range]) and on(service,run_id,attempt,conclusion) ({events}))"
        panels.append(panel(f"CI runs with failed {kind} checks", "stat", prom(expr, "{{service}}", instant=True),
                            description="Observed named jobs or steps with a failed conclusion. Missing jobs or unclassified checks can undercount."))
    panels.extend([sonar_gate(labels), sources(labels, 'source=~"github_ci.*|sonar_.*"')])
    for title, measures, unit in [
        ("Test coverage", "coverage", "percent"),
        ("Code duplication", "duplicated_lines_density", "percent"),
        ("Technical debt", "sqale_index", "m"),
        ("Bugs, vulnerabilities and code smells", "bugs|vulnerabilities|code_smells", None),
        ("Software quality issues", "software_quality_.*_issues", None),
    ]:
        panels.append(panel(title, "timeseries", prom(metric("sonar_measure", labels, f'measure=~"{measures}"'),
                                                      "{{service}} · {{measure}}"), unit=unit))
    return dashboard("lantern-devops-development", "Lantern · Development & Code Quality",
                     datasource_variables(development=True), panels)


def image_table(title, stages, width=12):
    return table(title, metric("image_info", extra=f'stage=~"{stages}"'),
                 columns=["service", "stage", "tag", "digest", "source_sha", "evidence", "registry_url"], width=width,
                 links=[("service", "Open service detail", DETAIL), ("registry_url", "Open Harbor artifact", "${__value.raw}")])


def runtime_table():
    return table("Running pod images and readiness", metric("running_container_info"),
                 columns=["service", "pod", "image", "image_id", "digest", "Value"],
                 description="1 = pod and application container are Ready. A registry-qualified digest is required for comparison.")


def argo_table():
    return table("Argo CD application status", metric("argo_application_info"),
                 columns=["service", "health", "sync", "gitops_revision"])


def deployments():
    sync_failures = ('sum by(name) (increase(argocd_app_sync_total{phase=~"Error|Failed",dry_run!="true",'
                     'name=~"${service:regex}"}[$__range]))')
    rollout_failures = metric("workload_rollout_info", extra='status="failed"')
    panels = [
        note("Confirmed means the latest observed validated release matches GitOps and every running replica, "
             "the rollout is complete, and Argo CD reports Synced and Healthy. Missing evidence is shown as insufficient."),
        table("Release delivery assessment", metric("delivery_assessment_info"),
              columns=["service", "status"], links=[("service", "Open service detail", DETAIL)]),
        table("Latest healthy matching deployment observed",
              f'max by(service) (max_over_time({metric("healthy_matching_sync_timestamp_seconds")}[$__range]))',
              columns=["service", "Value"], date=True,
              description="Successful Argo sync time for a deployment later observed healthy and digest-matched by the collector."),
        image_table("Harbor publications and validated releases", "latest.*"),
        image_table("GitOps declaration and runtime image metadata", "gitops|running"),
        runtime_table(),
        table("Image comparisons", metric("running_image_matches"),
              columns=["service", "reference", "Value"],
              description="1 = digest matches all observed running application containers. 0 = digests differ. No row = evidence missing."),
        argo_table(),
        table("Last successful Argo CD synchronization", metric("argo_last_successful_sync_timestamp_seconds"),
              columns=["service", "gitops_revision", "Value"], date=True),
        table("Latest Argo CD operation", metric("argo_last_operation_info"), columns=["service", "phase"]),
        table("Kubernetes rollout failures observed",
              f'max by(service, status) (max_over_time({rollout_failures}[$__range]))',
              columns=["service", "status"],
              description="Shows services that were observed with a Kubernetes deployment failure condition."),
        table("Failed Argo CD syncs in time range", sync_failures, columns=["name", "Value"],
              description="Estimated increase of the Argo CD controller counter, including counter resets."),
        table("Release workflow evidence", metric("delivery_step_info"), width=24,
              columns=["service", "repository", "tag", "sha", "phase", "conclusion", "run_id"],
              links=[("run_id", "Open release workflow run", ACTIONS)]),
        table("Harbor scan status", metric("harbor_scan_info"), columns=["service", "stage", "digest", "status"]),
        table("Registered Harbor signatures and attestations", metric("harbor_accessory_info"),
              columns=["service", "stage", "digest", "accessory_type", "accessory_digest"],
              description="Harbor accessory metadata. The release workflow panel records signature and provenance verification."),
        table("Vulnerabilities by image and severity", metric("image_vulnerabilities"),
              columns=["service", "stage", "digest", "severity", "Value"]),
        sources(),
        panel("Native metrics scrape health", "timeseries",
              prom('up{job=~"lantern-kpi-argocd-metrics|harbor-(exporter|core|registry|jobservice)"}', "{{job}} {{instance}}")),
    ]
    return dashboard("lantern-devops-deployments", "Lantern · Deployments & Container Security",
                     datasource_variables(), panels)


def replicas():
    targets = [
        prom(f'kube_deployment_spec_replicas{{{WORKLOAD},deployment=~"api|player-api|frontend-game|frontend-public"}}',
             "{{namespace}} desired"),
        prom(f'kube_deployment_status_replicas_available{{{WORKLOAD},deployment=~"api|player-api|frontend-game|frontend-public"}}',
             "{{namespace}} available"),
    ]
    return panel("Desired and available replicas", "timeseries", *targets)


def resources():
    cpu = f'sum by (namespace) (rate(container_cpu_usage_seconds_total{{{WORKLOAD},{APP_CONTAINERS},image!=""}}[$__rate_interval]))'
    memory = f'sum by (namespace) (container_memory_working_set_bytes{{{WORKLOAD},{APP_CONTAINERS},image!=""}})'
    result = []
    for resource, usage, unit in [("cpu", cpu, "suffix: cores"), ("memory", memory, "bytes")]:
        targets = [prom(usage, "{{namespace}} usage")]
        for kind in ("requests", "limits"):
            expr = f'sum by (namespace) (kube_pod_container_resource_{kind}{{{WORKLOAD},{APP_CONTAINERS},resource="{resource}"}})'
            targets.append(prom(expr, "{{namespace}} " + kind))
        result.append(panel(f"{resource.upper() if resource == 'cpu' else 'Memory'} usage, requests and limits",
                            "timeseries", *targets, unit=unit,
                            description="Application containers. Requests and limits are omitted when unset."))
    return result


def log_panel(heading):
    result = panel(heading, "logs", logs(LOG_QUERY), width=24, height=10,
                   description="Matches log text for error and warning severity tokens. Select the existing Kubernetes Loki datasource.")
    query_marker = "LANTERN_SERVICE_TOKEN"
    expression = LOG_QUERY.replace("${service:regex}", query_marker)
    explore = {"logs": {"datasource": "${loki}", "queries": [{"refId": "A", "expr": expression, "queryType": "range"}],
                        "range": {"from": "${__from}", "to": "${__to}"}}}
    panes = quote(json.dumps(explore, separators=(",", ":")), safe="").replace(query_marker, "${service:regex}")
    for variable_name in ("loki", "__from", "__to"):
        variable_expression = "${" + variable_name + "}"
        panes = panes.replace(quote(variable_expression, safe=""), variable_expression)
    result["links"] = [{"title": "Open application logs in Explore", "url": "/explore?schemaVersion=1&panes=" + panes}]
    return result


def health():
    ready = f'sum by(namespace) (kube_pod_status_ready{{{WORKLOAD},{APP_PODS},condition="true"}})'
    selected_container = f"{WORKLOAD},{APP_CONTAINERS}"
    panels = [
        table("Workload rollout status", metric("workload_rollout_info"), columns=["service", "status"],
              links=[("service", "Open service detail", DETAIL)]),
        argo_table(),
        replicas(),
        panel("Ready and observed application pods", "timeseries", prom(ready, "{{namespace}} ready"),
              prom(f'count by(namespace) (kube_pod_status_ready{{{WORKLOAD},{APP_PODS},condition="true"}})', "{{namespace}} observed")),
        panel("Container restarts", "timeseries",
              prom(f'sum by(namespace) (increase(kube_pod_container_status_restarts_total{{{selected_container}}}[$__rate_interval]))',
                   "{{namespace}}")),
        panel("Containers in CrashLoopBackOff", "timeseries",
              prom(f'sum by(namespace) (kube_pod_container_status_waiting_reason{{{selected_container},reason="CrashLoopBackOff"}})',
                   "{{namespace}}")),
        *resources(),
        panel("Application error and warning log lines", "timeseries", *(
            logs(f'sum by(namespace) (count_over_time({LOG_STREAM} |~ {json.dumps(pattern)} [$__interval]))',
                 "{{namespace}} " + severity)
            for severity, pattern in (("errors", ERROR), ("warnings", WARN))),
            description="Severity tokens in application log text. A line can match both queries."),
        log_panel("Application errors and warnings"),
        panel("Kubernetes node readiness", "timeseries",
              prom('kube_node_status_condition{condition="Ready",status="true"}', "{{node}}")),
        panel("Kubernetes metrics scrape health", "timeseries",
              prom('up{job=~"kubelet|kube-state-metrics"}', "{{job}} {{instance}}")),
        sources(extra='source=~"kubernetes|argocd"'),
    ]
    return dashboard("lantern-devops-health", "Lantern · Kubernetes & Microservices Health",
                     datasource_variables(loki=True), panels, "24h")


def detail():
    links = [(field, title, "${__value.raw}") for field, title in [
        ("github_url", "Open repository"), ("sonar_url", "Open SonarQube Cloud"),
        ("harbor_url", "Open Harbor"), ("argocd_url", "Open Argo CD"),
    ]]
    panels = [
        table("Service links", metric("service_info"), width=24,
              columns=["service", "repository", "github_url", "sonar_url", "harbor_url", "argocd_url"], links=links),
        table("Latest default-branch commit", metric("github_latest_commit_info"),
              columns=["service", "repository", "sha"],
              links=[("sha", "Open commit", "https://github.com/ProjectLanternDI3P1P2/${__data.fields.repository}/commit/${__value.raw}")]),
        ci_latest(),
        sonar_gate(),
        panel("SonarQube coverage", "timeseries", prom(metric("sonar_measure", extra='measure="coverage"'), "{{service}}"), unit="percent"),
        image_table("Published, promoted and running image metadata", "latest_published|gitops|running"),
        runtime_table(),
        argo_table(),
        table("Delivery assessment", metric("delivery_assessment_info"), columns=["service", "status"]),
        replicas(),
        *resources(),
        sources(),
        log_panel("Recent application errors and warnings"),
    ]
    return dashboard("lantern-devops-service", "Lantern · Service Detail",
                     datasource_variables(detail=True, loki=True), panels, "24h")


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
