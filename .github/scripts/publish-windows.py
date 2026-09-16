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

repository = os.environ['GITHUB_REPOSITORY']
expected = os.environ['EXPECTED_ARTIFACT_SHA256'].removeprefix('sha256:')
if not re.fullmatch(r'[0-9a-f]{64}', expected):
    raise SystemExit('Invalid expected artifact SHA-256')
version = '1.0.5'
# The portable ZIP is gone: the installer is already a per-user, no-elevation
# install, so a portable copy had no separate audience and only cost build time.
names = [f'MesBrowser-Setup-{version}.exe', 'SHA256SUMS.txt']
notes = '''## Mes Browser 1.0.5 · Windows / macOS

本版继续收拾 Windows 上「云模式被本机权限锁死」这一类问题，并让状态与缓存路径更耐操。

### 云模式与缓存

- 安装目录不可写时（Program Files、其他账户建立的目录、带着旧 ACL 拷贝过来的目录），状态与缓存改到 `%LOCALAPPDATA%`；安装目录可写时行为不变。
- 缓存根恢复反复失败时不再死磕坏目录：会隔离并在原处重建；成员 public-cookie 缓存改为按 scope 隔离，一个 scope 坏掉不再让整块缓存不可用。
- Windows 遗留文件清理对 ACCESS_DENIED / SHARING_VIOLATION / LOCK_VIOLATION 做有限重试，并可修复删除句柄与权限。

### 更新

- 应用内更新通道改由公开仓的 release 资产提供：从本版起，装了 1.0.2 及以上（内置公钥）的客户端会在应用内直接看到更新。

### 已知限制（与前几版相同）

- macOS 为 ad-hoc 签名、未公证；Windows 安装包未签名。
- 本版之前的安装包没有内置更新公钥，收不到应用内更新。
'''
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
        for name in names:
            if source.namelist().count(name) != 1:
                raise SystemExit('Missing or duplicate package: ' + name)
            with source.open(name) as data, (root / name).open('wb') as target:
                while block := data.read(1024 * 1024):
                    target.write(block)
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
    subprocess.run(['gh', 'release', 'create', tag, '--repo', repository, '--draft', '--title', 'Mes Browser ' + version + ' · Windows / macOS', '--notes-file', str(notes_file)], check=True)
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
