"""Regression tests for the pinned Keycloak image identity preflight.

Docker is mocked at the command boundary. These tests never launch a container,
reach the network or inspect credentials. They do not validate the Java CVEs.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_keycloak_java_exposure.sh"
MANIFEST = "sha256:3e1ac632e743660017b1e6bb4c3ffc800fd02c82cdd0db858cd03456a98a8dfc"
CONFIG = "sha256:b55801be6ce15109868bd056dc18d62d47106bfaad7ffbd1a5d804192ec98257"
IMAGE = "quay.io/keycloak/keycloak@" + MANIFEST

FAKE_DOCKER = r"""#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == image && "$2" == inspect ]]; then
    [[ "$MOCK_INSPECT_FAIL" == 0 ]] || exit 3
    [[ "$3" == "$MOCK_IMAGE_REF" ]] || exit 4
    [[ "$4" == --format ]] || exit 5
    case "$5" in
        '{{.Id}}') printf '%s\n' "$MOCK_IMAGE_ID" ;;
        '{{range .RepoDigests}}{{println .}}{{end}}') printf '%s\n' "$MOCK_REPO_DIGESTS" ;;
        *) exit 6 ;;
    esac
elif [[ "$1" == run ]]; then
    # A marker proves the script would have reached container execution.
    : > "$MOCK_RUN_MARKER"
    printf 'MOCK_CONTAINER_INSPECTION=REACHED\n'
else
    exit 7
fi
"""


class KeycloakImageIdentityTests(unittest.TestCase):
    def invoke(self, *, image_id=MANIFEST, repo_digests=IMAGE, inspect_fail=False):
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            fake_docker = temp / "docker"
            fake_docker.write_text(FAKE_DOCKER, encoding="utf-8")
            fake_docker.chmod(0o700)
            marker = temp / "container-ran"
            env = os.environ.copy()
            env.update({
                "PATH": str(temp) + os.pathsep + env.get("PATH", ""),
                "MOCK_IMAGE_REF": IMAGE,
                "MOCK_IMAGE_ID": image_id,
                "MOCK_REPO_DIGESTS": repo_digests,
                "MOCK_RUN_MARKER": str(marker),
                "MOCK_INSPECT_FAIL": "1" if inspect_fail else "0",
            })
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                env=env, capture_output=True, text=True, timeout=12, check=False,
            )
            return result, marker.exists()

    def test_script_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_manifest_id_with_matching_repo_digest_passes(self):
        result, ran = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(ran)
        self.assertIn("CANDIDATE_PINNED_REPOSITORY_DIGEST=PASS", result.stdout)
        self.assertIn("CANDIDATE_DOCKER_ID_KIND=MANIFEST", result.stdout)
        self.assertIn("CANDIDATE_IDENTITY=PASS", result.stdout)

    def test_config_id_with_matching_repo_digest_passes(self):
        result, ran = self.invoke(image_id=CONFIG)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(ran)
        self.assertIn("CANDIDATE_DOCKER_ID_KIND=CONFIGURATION", result.stdout)

    def test_multiple_repo_digests_with_exact_match_passes(self):
        extra = "example.invalid/other@sha256:" + "a" * 64
        result, ran = self.invoke(repo_digests=extra + "\n" + IMAGE)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(ran)

    def test_similar_but_incorrect_digest_is_rejected(self):
        wrong = "quay.io/keycloak/keycloak@sha256:" + "0" * 64
        result, ran = self.invoke(repo_digests=wrong)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(ran)
        self.assertIn("CANDIDATE_PINNED_REPOSITORY_DIGEST=FAIL", result.stdout)

    def test_empty_repo_digest_is_rejected(self):
        result, ran = self.invoke(repo_digests="")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(ran)

    def test_extra_characters_are_rejected(self):
        result, ran = self.invoke(repo_digests=IMAGE + r"\n")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(ran)

    def test_unrecognised_image_id_is_rejected(self):
        result, ran = self.invoke(image_id="sha256:" + "1" * 64)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(ran)
        self.assertIn("CANDIDATE_IDENTITY=FAIL", result.stdout)

    def test_failed_docker_inspect_does_not_run_container(self):
        result, ran = self.invoke(inspect_fail=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(ran)
        self.assertIn("CANDIDATE_IMAGE=BLOCKED", result.stdout)


if __name__ == "__main__":
    unittest.main()
