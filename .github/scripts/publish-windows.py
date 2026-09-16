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
version = '1.0.2'
names = [f'MesBrowser-Setup-{version}.exe', f'MesBrowser-{version}-windows-amd64-portable.zip', 'SHA256SUMS.txt']
notes = '''## Mes Browser 1.0.2 · Windows / macOS

本版开始，桌面端可以**在应用内检查并安装界面更新**，常规界面改动不再需要用户重新下载整包。

### 应用内更新（本次的重点）

- 客户端内置更新签名公钥，清单由离线私钥签名后才被接受；来源与签名都验过才安装。
- 两级更新：界面资源热更新（下载几 MB、重载界面、**不重装**）与整包自更新（替换安装后重启）。
- 界面坏掉不再让应用打不开：校验失败会丢弃该版本并回落到内置界面；连续两个坏界面会被退役。
- 界面若调用了当前二进制没有的后端能力，启动自检会拦下并回退，而不是等用户点到才报错。
- 下载制品只允许来自白名单主机，重定向逐跳校验。

### Windows

- 安装与更新都改为**当前用户**，默认目录 `%LOCALAPPDATA%\\Programs\\Mes Browser`，不再需要管理员权限；更新过程不再弹 UAC。
- 旧 `Program Files` 安装不会被自动迁移或删除；如需保留旧目录中的数据，请先自行备份。

### macOS

- 更新后应用内替换整包并重启；界面热更新不需要重启。
- 仍为 ad-hoc 签名、未公证（与 1.0.1 相同），首次打开若被 Gatekeeper 拦下，请在「系统设置 → 隐私与安全性」中放行。

### 已知限制

- 本版之前的安装包没有内置公钥，收不到任何更新；装了本版之后才会生效——这一次的整包更新是唯一省不掉的一次。
- macOS 未公证、Windows 安装包未签名（与上一版相同）。
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
