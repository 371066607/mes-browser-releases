"""Publish verified binaries using an expiring, single-artifact download URL."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request
import zipfile

from windows_verification import validate_bundle, verify_origin

repository = os.environ['GITHUB_REPOSITORY']
if os.environ.get('GITHUB_REF') != 'refs/heads/main':
    raise SystemExit('Publication requires the trusted release repository main branch')
expected = os.environ['EXPECTED_ARTIFACT_SHA256'].removeprefix('sha256:')
if not re.fullmatch(r'[0-9a-f]{64}', expected):
    raise SystemExit('Invalid expected artifact SHA-256')
version = os.environ['PACKAGE_VERSION']
if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', version):
    raise SystemExit('Invalid package version')
# The portable ZIP is gone: the installer is already a per-user, no-elevation
# install, so a portable copy had no separate audience and only cost build time.
names = [f'MesBrowser-Setup-{version}.exe', 'SHA256SUMS.txt']
def build_api(endpoint):
    environment = os.environ.copy()
    environment['GH_TOKEN'] = os.environ.get('WINDOWS_BUILD_READ_TOKEN') or environment.get('GH_TOKEN', '')
    return json.loads(subprocess.check_output(['gh', 'api', endpoint], env=environment, text=True))


with tempfile.TemporaryDirectory(prefix='mes-release-') as temporary:
    root = Path(temporary)
    archive = root / 'verified-artifact.zip'
    digest = hashlib.sha256()
    with urllib.request.urlopen(os.environ['WINDOWS_PACKAGE_ARTIFACT_URL'], timeout=60) as source, archive.open('wb') as target:
        while block := source.read(1024 * 1024):
            target.write(block)
            digest.update(block)
    if digest.hexdigest() != expected:
        raise SystemExit('Artifact digest mismatch; refusing publication')
    with zipfile.ZipFile(archive) as source:
        for name in names + ['verification.json', 'build-provenance.json']:
            if source.namelist().count(name) != 1:
                raise SystemExit('Missing or duplicate package: ' + name)
            with source.open(name) as data, (root / name).open('wb') as target:
                while block := data.read(1024 * 1024):
                    target.write(block)
    report = validate_bundle(root, version)
    if str(report['verificationRun']) != os.environ['VERIFICATION_RUN'] or str(report['sourceBuildRun']) != os.environ['SOURCE_BUILD_RUN']:
        raise SystemExit('Requested run IDs do not match the verification report')
    verify_origin(report, digest.hexdigest(), build_api)
    notes = f'''## Mes Browser {version} · Windows

发布文件与完整 Windows 验证使用的安装器 SHA-256 一致。

- 验证套件：{report['suite']}，必需场景全部通过。
- 源码提交：`{report['sourceCommit']}`。
- 安装包 SHA-256：`{report['installerSha256']}`。
- Windows Server 2025 自动化验证不代表用户 Windows 11 设备或生产账号验收。
- Windows 安装包未签名。
- 此次发布仅包含 Windows 安装包；macOS 请使用已有含 macOS 资产的版本。
'''
    actual = {}
    for name in names:
        digest = hashlib.sha256()
        with (root / name).open('rb') as data:
            while block := data.read(1024 * 1024):
                digest.update(block)
        actual[name] = digest.hexdigest()
        print(name, (root / name).stat().st_size, actual[name], flush=True)
    expected_lines = [actual[name] + '  ' + name for name in names[:-1]]
    if (root / 'SHA256SUMS.txt').read_text(encoding='utf-8-sig').splitlines() != expected_lines:
        raise SystemExit('Package checksum file mismatch')
    notes_file = root / 'release-notes.md'
    notes_file.write_text(notes, encoding='utf-8')
    tag = 'v' + version
    subprocess.run(['gh', 'release', 'create', tag, '--repo', repository, '--draft', '--title', 'Mes Browser ' + version + ' · Windows', '--notes-file', str(notes_file)], check=True)
    subprocess.run(['gh', 'release', 'upload', tag, '--repo', repository, *[str(root / name) for name in names]], check=True)
    # Tag lookup does not resolve an unpublished draft. The authenticated list
    # includes the newly created draft and its uploaded asset digests.
    releases = json.loads(subprocess.check_output(['gh', 'api', f'repos/{repository}/releases?per_page=100']))
    drafts = [release for release in releases if release['tag_name'] == tag and release['draft']]
    if len(drafts) != 1:
        raise SystemExit('Expected exactly one matching draft; refusing publication')
    metadata = drafts[0]
    remote = {asset['name']: asset.get('digest') for asset in metadata['assets']}
    if remote != {name: 'sha256:' + value for name, value in actual.items()}:
        raise SystemExit('Uploaded asset digest mismatch; release remains draft')
    subprocess.run(['gh', 'release', 'edit', tag, '--repo', repository, '--draft=false', '--latest'], check=True)
    print(f'https://github.com/{repository}/releases/tag/{tag}', flush=True)
