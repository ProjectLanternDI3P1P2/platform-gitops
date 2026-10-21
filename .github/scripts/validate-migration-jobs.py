"""Check deployment/migration coupling without connecting to any database."""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
MIGRATED_APPS = ("player", "dungeon", "rewards")


def render(root, app):
    result = subprocess.run(
        ["kubectl", "kustomize", str(root / "apps" / app / "overlays" / "k3s")],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    return list(yaml.safe_load_all(result.stdout))


def resource(resources, kind):
    matches = [item for item in resources if item and item["kind"] == kind]
    if len(matches) != 1:
        raise AssertionError(f"Expected one {kind}, got {len(matches)}")
    return matches[0]


def environment(container):
    return {item["name"]: item for item in container.get("env", [])}


class MigrationJobTests(unittest.TestCase):
    def test_job_matches_final_deployment(self):
        for app in MIGRATED_APPS:
            with self.subTest(app=app):
                resources = render(ROOT, app)
                deployment = resource(resources, "Deployment")
                job = resource(resources, "Job")
                api = deployment["spec"]["template"]["spec"]
                migration = job["spec"]["template"]["spec"]
                api_container = api["containers"][0]
                container = migration["containers"][0]
                self.assertEqual(api_container["image"], container["image"])
                self.assertNotIn("must-be-replaced", yaml.safe_dump(job))
                self.assertEqual(deployment["metadata"]["namespace"], job["metadata"]["namespace"])
                self.assertEqual(api["imagePullSecrets"], migration["imagePullSecrets"])
                self.assertEqual(api["volumes"], migration["volumes"])
                api_env, job_env = environment(api_container), environment(container)
                for key in ("ConnectionStrings__DefaultConnection", "ConnectionStrings__PasswordFile"):
                    self.assertEqual(api_env[key], job_env[key])
                self.assertEqual("Production", job_env["ASPNETCORE_ENVIRONMENT"]["value"])
                self.assertEqual("false", job_env["RabbitMq__Enabled"]["value"])
                self.assertEqual(["--migrate"], container["args"])
                self.assertFalse(migration["automountServiceAccountToken"])
                self.assertTrue(migration["securityContext"]["runAsNonRoot"])
                self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
                self.assertEqual("Never", migration["restartPolicy"])
                self.assertEqual(0, job["spec"]["backoffLimit"])
                self.assertEqual(1, job["spec"]["parallelism"])
                self.assertEqual(600, job["spec"]["activeDeadlineSeconds"])
                annotations = job["metadata"]["annotations"]
                self.assertEqual("PreSync", annotations["argocd.argoproj.io/hook"])
                self.assertEqual("BeforeHookCreation,HookSucceeded", annotations["argocd.argoproj.io/hook-delete-policy"])

    def test_image_promotion_updates_job_and_api(self):
        with tempfile.TemporaryDirectory(prefix="migration-validation-", dir=ROOT) as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "apps", root / "apps")
            for app in MIGRATED_APPS:
                with self.subTest(app=app):
                    path = root / "apps" / app / "overlays" / "k3s" / "kustomization.yaml"
                    text, count = re.subn(r"newTag: [^\r\n]+", "newTag: v99.0.0", path.read_text(encoding="utf-8"), count=1)
                    self.assertEqual(1, count)
                    path.write_text(text, encoding="utf-8")
                    resources = render(root, app)
                    for kind in ("Deployment", "Job"):
                        image = resource(resources, kind)["spec"]["template"]["spec"]["containers"][0]["image"]
                        self.assertTrue(image.endswith(":v99.0.0"), image)

    def test_apps_without_migration_artifacts_are_not_enabled(self):
        for app in ("combat", "leaderboard", "frontend-game", "frontend-public"):
            with self.subTest(app=app):
                self.assertFalse(any(item and item["kind"] == "Job" for item in render(ROOT, app)))


if __name__ == "__main__":
    unittest.main()
