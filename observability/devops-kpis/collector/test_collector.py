import contextlib
import io
import json
import unittest
from collections import OrderedDict
from pathlib import Path
from unittest.mock import patch

import collector


SERVICE = next(service for service in collector.SERVICES if service["service"] == "combat")
DIGEST = "sha256:" + "a" * 64
OLDER_DIGEST = "sha256:" + "b" * 64
SHA = "c" * 40
IMAGE = f"{collector.REGISTRY}/lantern/combat-backend"
DATE = "2026-11-27T10:00:00Z"
MIME = "application/vnd.security.vulnerability.report; version=1.1"


def artifact():
    return {
        "type": "IMAGE", "digest": DIGEST, "push_time": DATE,
        "tags": [{"name": "v1.2.0", "immutable": True}],
        "extra_attrs": {"config": {"Labels": {"org.opencontainers.image.revision": SHA}}},
        "scan_overview": {MIME: {"scan_status": "Success", "summary": {"summary": {"High": 2}}}},
    }


class CollectorTest(unittest.TestCase):
    def test_gitops_catalog_overlays(self):
        platform = Path(__file__).resolve().parents[3]
        for service in collector.SERVICES:
            with self.subTest(service=service["service"]):
                path = platform / "apps" / service["service"] / "overlays/k3s/kustomization.yaml"
                image = f'{collector.REGISTRY}/lantern/{service["repository"]}'
                tag, digest = collector.gitops_reference(path.read_text(), image)
                self.assertTrue(tag)
                self.assertFalse(digest and not collector.DIGEST.fullmatch(digest))

    def test_gitops_trace_is_bound_to_the_declared_digest(self):
        overlay = f"images:\n  - name: {IMAGE}\n    newTag: v1.2.0\n    digest: {DIGEST}\n"
        commit = {"sha": "gitops-revision", "commit": {"message": f"Source: {collector.ORG}/combat-backend@{SHA}\nDigest: {DIGEST}"}}
        with patch.object(collector, "gh", side_effect=([commit], overlay)) as github:
            self.assertEqual(collector.gitops_image(SERVICE, IMAGE), ("v1.2.0", DIGEST, SHA))
            self.assertEqual(github.call_args.args[1], {"ref": "gitops-revision"})

    def test_unknown_digest_or_mutable_tag_cannot_confirm_release(self):
        latest = artifact()
        argo = {"status": {"sync": {"status": "Synced", "revision": "revision"},
                           "health": {"status": "Healthy"},
                           "history": [{"deployedAt": DATE, "revision": "revision"}]}}
        for digest, immutable, ready, expected in (
            (DIGEST, True, True, "confirmed"),
            ("", True, True, "insufficient_evidence"),
            (DIGEST, False, True, "insufficient_evidence"),
            (DIGEST, True, False, "differs_or_unhealthy"),
            (OLDER_DIGEST, True, True, "differs_or_unhealthy"),
        ):
            with self.subTest(digest=digest, immutable=immutable, ready=ready):
                latest["tags"][0]["immutable"] = immutable
                workload = {"desired": 1, "rollout": "complete", "running": [{"digest": digest, "ready": ready}]}
                metrics = collector.Observations(SERVICE)
                with patch.object(collector, "harbor", side_effect=FileNotFoundError):
                    collector.image_metrics(metrics, SERVICE["repository"], [latest], {"v1.2.0": SHA},
                                            ("v1.2.0", DIGEST, ""), workload, argo)
                assessment = next(row for row in metrics.rows if row["kind"] == "delivery_assessment_info")
                self.assertEqual(assessment["status"], expected)
                if expected == "confirmed":
                    self.assertTrue(any(row["kind"] == "healthy_matching_sync_timestamp_seconds" for row in metrics.rows))

    def test_ci_metrics_derive_duration_and_failures_from_jobs(self):
        metrics = collector.Observations(SERVICE)
        runs = [{"id": 123, "status": "completed", "run_attempt": 1, "conclusion": "failure",
                 "created_at": DATE, "updated_at": "2026-11-27T10:10:00Z", "run_started_at": DATE}]
        jobs = [{"name": "tests", "completed_at": "2026-11-27T10:03:00Z", "steps": [
            {"name": "Run npm run test:unit", "conclusion": "failure"},
            {"name": "Build", "conclusion": "success"},
        ]}]
        with patch.object(collector, "completed_jobs", return_value=jobs):
            collector.ci_metrics(metrics, "/repos/test", runs)
        duration = next(row for row in metrics.rows if row["kind"] == "ci_duration_seconds")
        self.assertEqual(duration["value"], 180)
        checks = {row["check"]: row["value"] for row in metrics.rows if row["kind"] == "ci_check_failed"}
        self.assertEqual(checks, {"build": 0, "test": 1})

    def test_release_accepts_existing_combined_build_and_push_step(self):
        runs = [{"id": 123, "event": "push", "head_branch": "v1.2.0", "status": "completed",
                 "run_attempt": 1, "head_sha": SHA, "updated_at": DATE}]
        steps = ["Build and push", "Enforce Harbor vulnerability scan gate", "Sign image by digest",
                 "Attach signed provenance attestation", "Verify signature", "Verify published image"]
        jobs = [{"steps": [{"name": step, "conclusion": "success"} for step in steps]}]
        with patch.object(collector, "completed_jobs", return_value=jobs):
            self.assertEqual(collector.delivery_jobs(collector.Observations(SERVICE), "/repos/test", runs, {"v1.2.0"}),
                             {"v1.2.0": SHA})

    def test_rbac_or_api_failure_emits_availability_without_measurement(self):
        metrics = collector.Observations(SERVICE)
        with patch.object(collector, "credential", side_effect=FileNotFoundError):
            collector.quality_metrics(metrics, SERVICE["sonar"])
        self.assertEqual(len(metrics.rows), 2)
        self.assertTrue(all(row["kind"] == "source_available" and row["value"] == 0 for row in metrics.rows))

    def test_usage_requires_samples_for_all_active_pods(self):
        workload = {"active_pods": ["api-one", "api-two"]}
        samples = {"items": [
            {"metadata": {"name": "api-one"}, "containers": [{"name": "api", "usage": {"cpu": "250000000n", "memory": "16Mi"}}]},
            {"metadata": {"name": "api-two"}, "containers": [{"name": "api", "usage": {"cpu": "500m", "memory": "32Mi"}}]},
            {"metadata": {"name": "other"}, "containers": [{"name": "api", "usage": {"cpu": "1", "memory": "4Gi"}}]},
        ]}
        with patch.object(collector, "kubernetes", return_value=samples):
            self.assertEqual(collector.pod_usage(SERVICE, workload), {"cpu": 0.75, "memory": 48 * 2**20})
            self.assertIsNone(collector.pod_usage(SERVICE, {"active_pods": ["api-one", "unobserved"]}))

    def test_snapshot_emits_events_once_and_marks_complete_service(self):
        metrics = collector.Observations(SERVICE)
        metrics.add("workload_measure", 1, measure="desired")
        metrics.add("argo_sync_failed", 1, operation_id="operation")
        events = OrderedDict()
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            collector.emit_snapshot(metrics.rows, 10, events)
            collector.emit_snapshot(metrics.rows, 20, events)
        rows = [json.loads(line.removeprefix("LANTERN_KPI ")) for line in log.getvalue().splitlines()]
        self.assertEqual([row["kind"] for row in rows], [
            "workload_measure", "argo_sync_failed", "collector_snapshot", "workload_measure", "collector_snapshot",
        ])
        self.assertEqual(rows[-1]["snapshot"], 20)


if __name__ == "__main__":
    unittest.main()
