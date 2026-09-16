import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from windows_verification import BUILD_REPOSITORY, REQUIRED_CASES, validate_bundle, verify_origin


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        payload = b"fixture installer"
        digest = hashlib.sha256(payload).hexdigest()
        (self.root / "MesBrowser-Setup-1.2.3.exe").write_bytes(payload)
        (self.root / "SHA256SUMS.txt").write_text(digest + "  MesBrowser-Setup-1.2.3.exe\n")
        self.report = dict(schemaVersion=1, suite="windows-release-v1", verificationLevel="full", releaseEligible=True,
                           repository=BUILD_REPOSITORY, version="1.2.3", installerSha256=digest, sourceCommit="a" * 40,
                           sourceSnapshotSha256="b" * 64, buildRepositoryCommit="c" * 40, verificationCommit="d" * 40,
                           sourceBuildRun="101", verificationRun="102", includesWorktreeChanges=False,
                           cases=[dict(name=name, status="passed") for name in sorted(REQUIRED_CASES)])
        self.provenance = dict(self.report, devtools=False, productionTagVerified=True)
        self.run = dict(repository={"full_name": BUILD_REPOSITORY}, head_branch="main", event="workflow_dispatch",
                        status="completed", conclusion="success", head_sha="d" * 40,
                        path=".github/workflows/verify-existing-windows.yml")
        self.build = dict(self.run, head_sha="c" * 40, path=".github/workflows/build-windows.yml", conclusion="failure")
        self.artifacts = dict(total_count=1, artifacts=[dict(name="Verified-Windows-packages-12", expired=False, digest="sha256:" + "e" * 64)])

    def save(self):
        for name, value in (("verification.json", self.report), ("build-provenance.json", self.provenance)):
            (self.root / name).write_text(json.dumps(value))

    def api(self, endpoint):
        if "artifacts?" in endpoint:
            return self.artifacts
        return self.build if endpoint.endswith("/101") else self.run

    def test_full_exact_artifact_can_reverify_a_build_that_failed_later(self):
        self.save()
        report = validate_bundle(self.root, "1.2.3")
        verify_origin(report, "e" * 64, self.api)

    def test_build_and_verification_can_be_the_same_successful_run(self):
        self.report.update(verificationRun="101", verificationCommit="c" * 40)
        self.build["conclusion"] = "success"
        self.artifacts["artifacts"][0]["name"] = "MesBrowser-windows-amd64-10"
        self.save()
        report = validate_bundle(self.root, "1.2.3")
        verify_origin(report, "e" * 64, self.api)

    def test_reject_incomplete_or_misleading_report(self):
        original = copy.deepcopy(self.report)
        mutations = [dict(verificationLevel="fast"), dict(releaseEligible=False), dict(cases=[]),
                     dict(cases=[dict(name=n, status="skipped") for n in REQUIRED_CASES]),
                     dict(cases=original["cases"] + [original["cases"][0]]), dict(installerSha256="f" * 64),
                     dict(includesWorktreeChanges=True), dict(sourceCommit="f" * 40), dict(sourceBuildRun="999"), dict(suite="old")]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.report = dict(original, **mutation)
                self.save()
                with self.assertRaises(ValueError):
                    validate_bundle(self.root, "1.2.3")

    def test_reject_changed_installer_without_overwriting_checksums(self):
        self.save()
        (self.root / "MesBrowser-Setup-1.2.3.exe").write_bytes(b"different")
        with self.assertRaises(ValueError):
            validate_bundle(self.root, "1.2.3")

    def test_reject_untrusted_or_unsuccessful_run(self):
        for mutation in (dict(head_branch="feature"), dict(conclusion="failure"), dict(head_sha="f" * 40),
                         dict(path=".github/workflows/other.yml"), dict(event="pull_request")):
            original = self.run.copy()
            with self.subTest(mutation=mutation):
                self.run.update(mutation)
                with self.assertRaises(ValueError):
                    verify_origin(self.report, "e" * 64, self.api)
            self.run = original

    def test_reject_archive_substitution_and_expired_or_ambiguous_artifact(self):
        with self.assertRaises(ValueError):
            verify_origin(self.report, "f" * 64, self.api)
        self.artifacts["artifacts"][0]["expired"] = True
        with self.assertRaises(ValueError):
            verify_origin(self.report, "e" * 64, self.api)
        self.artifacts["artifacts"][0]["expired"] = False
        self.artifacts["artifacts"] *= 2
        self.artifacts["total_count"] = 2
        with self.assertRaises(ValueError):
            verify_origin(self.report, "e" * 64, self.api)

    def test_reject_incomplete_artifact_inventory(self):
        self.artifacts["total_count"] = 101
        with self.assertRaisesRegex(ValueError, "Incomplete artifact inventory"):
            verify_origin(self.report, "e" * 64, self.api)

    def test_reject_unrelated_source_build(self):
        for mutation in (dict(head_branch="feature"), dict(head_sha="f" * 40), dict(status="in_progress"),
                         dict(path=".github/workflows/build-macos.yml")):
            original = self.build.copy()
            with self.subTest(mutation=mutation):
                self.build.update(mutation)
                with self.assertRaises(ValueError):
                    verify_origin(self.report, "e" * 64, self.api)
            self.build = original


if __name__ == "__main__":
    unittest.main()
