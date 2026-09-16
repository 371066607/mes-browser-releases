"""Fail-closed Windows release contract; importing this module never publishes."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

BUILD_REPOSITORY = "371066607/mes-browser-windows-build"
SUITE = "windows-release-v1"
REQUIRED_CASES = frozenset({
    "artifact-integrity", "native-windows-regression", "frontend-assets", "restricted-install",
    "installer-registration", "desktop-activation", "readonly-install", "historical-upgrade",
    "lock-failure", "core-cdp", "owned-process-cleanup",
})
WORKFLOWS = {
    ".github/workflows/build-windows.yml": "MesBrowser-windows-amd64-",
    ".github/workflows/verify-existing-windows.yml": "Verified-Windows-packages-",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def validate_bundle(root, version):
    """Validate content first. The caller MUST subsequently anchor it to GitHub."""
    root = Path(root)
    require(re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", version), "Invalid version")
    installer = root / f"MesBrowser-Setup-{version}.exe"
    report = read_json(root / "verification.json")
    provenance = read_json(root / "build-provenance.json")
    require(report.get("schemaVersion") == 1 and report.get("suite") == SUITE, "Unsupported verification suite")
    require(report.get("verificationLevel") == "full" and report.get("releaseEligible") is True, "Full verification required")
    require(report.get("repository") == BUILD_REPOSITORY, "Unexpected build repository")
    require(report.get("version") == version == provenance.get("version"), "Version mismatch")
    require(provenance.get("devtools") is False and provenance.get("productionTagVerified") is True, "Production build required")
    require(provenance.get("includesWorktreeChanges") is False and report.get("includesWorktreeChanges") is False,
            "Release source must be committed")
    for field, length in (("sourceCommit", 40), ("sourceSnapshotSha256", 64), ("buildRepositoryCommit", 40)):
        value = report.get(field, "")
        require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % length, value), f"Invalid {field}")
        require(value == provenance.get(field), f"Provenance mismatch: {field}")
    require(re.fullmatch(r"[0-9a-f]{40}", str(report.get("verificationCommit", ""))), "Invalid verification commit")
    for field in ("sourceBuildRun", "verificationRun"):
        require(re.fullmatch(r"[1-9][0-9]*", str(report.get(field, ""))), f"Invalid {field}")
    require(str(report["sourceBuildRun"]) == str(provenance.get("sourceBuildRun")), "Original build run mismatch")
    cases = report.get("cases")
    require(isinstance(cases, list) and all(isinstance(case, dict) for case in cases), "Missing scenario results")
    names = [case.get("name") for case in cases]
    require(all(isinstance(name, str) for name in names) and len(set(names)) == len(names), "Duplicate or invalid scenario")
    require(REQUIRED_CASES.issubset(names), "Missing required scenario")
    require(all(case.get("status") == "passed" for case in cases), "Failed, skipped or unexecuted scenario")
    actual = sha256(installer)
    require(report.get("installerSha256") == actual == provenance.get("installerSha256"), "Installer digest mismatch")
    require((root / "SHA256SUMS.txt").read_text(encoding="utf-8-sig").splitlines() == [f"{actual}  {installer.name}"],
            "Original package checksum mismatch")
    return report


def gh_json(endpoint):
    # GH_TOKEN is supplied by the caller; never print an artifact URL or token.
    return json.loads(subprocess.check_output(["gh", "api", endpoint], text=True))


def verify_origin(report, archive_digest, api=gh_json):
    """An API-authenticated artifact digest anchors the entire downloaded bundle."""
    prefix = f"repos/{BUILD_REPOSITORY}/actions"
    run = api(f"{prefix}/runs/{report['verificationRun']}")
    require(run.get("repository", {}).get("full_name") == BUILD_REPOSITORY, "Wrong verification repository")
    require(run.get("head_branch") == "main" and run.get("event") == "workflow_dispatch", "Untrusted verification branch/event")
    require(run.get("status") == "completed" and run.get("conclusion") == "success", "Verification run did not succeed")
    require(run.get("head_sha") == report["verificationCommit"], "Verification commit mismatch")
    workflow = run.get("path")
    require(workflow in WORKFLOWS, "Untrusted verification workflow")
    metadata = api(f"{prefix}/runs/{report['verificationRun']}/artifacts?per_page=100")
    artifacts = metadata.get("artifacts", [])
    require(metadata.get("total_count") == len(artifacts), "Incomplete artifact inventory")
    candidates = [a for a in artifacts if a.get("name", "").startswith(WORKFLOWS[workflow]) and not a.get("expired", True)]
    require(len(candidates) == 1 and candidates[0].get("digest") == "sha256:" + archive_digest,
            "Downloaded archive is not the unique verified run artifact")
    build = run if str(report["sourceBuildRun"]) == str(report["verificationRun"]) else api(f"{prefix}/runs/{report['sourceBuildRun']}")
    require(build.get("repository", {}).get("full_name") == BUILD_REPOSITORY and build.get("head_branch") == "main",
            "Untrusted source build")
    require(build.get("path") == ".github/workflows/build-windows.yml" and build.get("event") == "workflow_dispatch"
            and build.get("status") == "completed", "Invalid source build workflow")
    require(build.get("head_sha") == report["buildRepositoryCommit"], "Source build commit mismatch")
    return candidates[0]
