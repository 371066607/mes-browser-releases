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
version = '1.0.1'
names = [f'MesBrowser-Setup-{version}.exe', f'MesBrowser-{version}-windows-amd64-portable.zip', 'SHA256SUMS.txt']
notes = '''## Windows 1.0.1

针对安装后双击无窗口的问题，补齐嵌入的前端页面，并改为当前用户安装，避免默认安装到 Program Files 后无法写入配置和数据库。本包已通过 Windows Server 2025 CI，供 Windows 11 设备继续实测。

- 推荐下载 `MesBrowser-Setup-1.0.1.exe`，按默认目录安装后，从开始菜单启动 Mes Browser。
- 默认目录：`%LOCALAPPDATA%\\Programs\\Mes Browser`，无需管理员权限。
- 已包含 Windows x64 浏览器内核和代理运行时；未启用 DevTools。
- 启动故障会记录到 `%LOCALAPPDATA%\\Ant Browser\\logs`；已接入的启动错误会弹框说明，不再一律静默退出。
- 便携版也可使用；请解压到当前用户可写的目录后运行 `mes-browser.exe`。

### 验证范围

在 GitHub Windows Server 2025 上，验证了普通无参数启动显示窗口、受限权限安装、登录框实际输入、覆盖安装后再次启动、已有配置和测试数据保留、最小化后二次启动唤醒窗口，以及随包内核通过 CDP 执行 JavaScript。只读目录和锁错误注入均验证了原生错误框、独立启动日志和关闭后退出码 1。验证过程确认管理员身份已移除，且不能写入 Program Files。安装版、升级版和便携版的桌面 EXE 哈希一致；本次发布直接复用这批验证包，没有重新编译或重打包。

尚未在反馈问题的 Windows 11 设备上验收，也未验证线上账号业务。Windows 安装包未签名。

### 从 1.0.0 更新

升级前请先退出旧版 Mes Browser；旧版缺少新的窗口激活协议。

本版使用新的当前用户安装目录，不会自动删除或迁移旧版 Program Files 目录。安装完成后使用开始菜单中新建的 Mes Browser 快捷方式；旧目录中若有需要保留的数据，请先保留。
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
