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
version = '1.0.3'
names = [f'MesBrowser-Setup-{version}.exe', f'MesBrowser-{version}-windows-amd64-portable.zip', 'SHA256SUMS.txt']
notes = '''## Mes Browser 1.0.3 · Windows / macOS

修复 1.0.2 上「实例无法启动」的问题：应用自带的浏览器内核是包的一部分，它不再被服务端记录的版本号否决。

### 内核（本次修复）

- **内核随包一起发布，版本不再决定能否启动**：实例配置的内核与服务端发布的版本号只参与「优先用哪个」，不再作为放行条件。
- 服务端没有给出版本号、或给的版本与你机器上的不一致时，**照常启动**，使用包内自带内核。
- 启动之后不再因为「实际运行的内核版本 ≠ 发布环境记录的版本」而中止，改为写入日志。
- 仍然只使用随应用提供、清单校验通过的内核；包内内核的身份由清单与 payload 摘要保证。

### 从 1.0.2 更新

存在 1.0.2 上启动报 `public-cookie run has no bound browser core artifact` 的实例，升级到本版即可正常启动；无需改动实例的内核配置。

### 已知限制（与 1.0.2 相同）

- 本版之前的安装包没有内置更新公钥，收不到应用内更新；装了带公钥的版本之后才会生效。
- macOS 未公证（ad-hoc 签名），Windows 安装包未签名。
- 旧数据迁移的权限诊断仍有已知失败，详见 `macos-known-limitations.txt`。
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
    expected_lines = [actual[name] + '  ' + name for name in names[:2]]
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
