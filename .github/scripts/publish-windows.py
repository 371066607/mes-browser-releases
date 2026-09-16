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
version = '1.0.4'
# The portable ZIP is gone: the installer is already a per-user, no-elevation
# install, so a portable copy had no separate audience and only cost build time.
names = [f'MesBrowser-Setup-{version}.exe', 'SHA256SUMS.txt']
notes = '''## Mes Browser 1.0.4 · Windows / macOS

本版的重点是「云模式不再因为本机缓存权限被锁死」，同时带上最近两版的修复。

### 云模式与内核

- 缓存目录不可写时（Windows 上常见于继承旧安装 ACL 的 `data\\cloud`）：先隔离旧目录并在原处重建（重建目录继承父目录权限），仍不可写则回退到用户数据目录；只有都失败才拒绝云模式，错误里直接给出路径与两处修改建议。
- 云锁定页不再把本机权限问题说成「控制面暂时不可达」。
- 成员运行（服务端不下发内核）总是使用随包自带内核：实例配置的核心与服务端发布版本只参与排序，解析失败也不再中止启动。
- 启动后不再因「运行内核版本 ≠ 已发布环境记录」而中止，改为记录告警。
- 云模式退出不再被契约校验弹窗取消。

### 更新

- 应用内更新通道改由公开仓的 release 资产提供，发布不再需要任何管理员凭据。
- **本版之前的安装包没有内置更新公钥**，收不到应用内更新；这一次整包更新仍是省不掉的一步。

### Windows

- **不再发布便携包**（`*-windows-amd64-portable.zip`）：安装包本身就是当前用户安装、免提权，便携版没有独立用途。请下载 `MesBrowser-Setup-1.0.4.exe`。
- 安装包未签名（与上一版相同）。

### macOS

- ad-hoc 签名、未公证（与上一版相同）；首次打开若被 Gatekeeper 拦下，请在「系统设置 → 隐私与安全性」中放行。
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
