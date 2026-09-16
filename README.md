# Mes Browser 下载

[下载最新版本](https://github.com/371066607/mes-browser-releases/releases/latest)

此仓库用于公开分发 Mes Browser 桌面端安装包，不存放应用源码。

- Windows x64 安装包：下载 `MesBrowser-Setup-*.exe`。
- macOS Apple Silicon（M 系列）：下载 `*-macos-arm64.zip`，解压后将 `.app` 拖入“应用程序”。不适用于 Intel Mac。
- Windows 使用 `SHA256SUMS.txt`，macOS 使用 `SHA256SUMS-macos-arm64.txt` 检查文件完整性。

macOS 包包含浏览器内核和代理运行时，未启用 DevTools；采用 ad-hoc 签名，尚未经过 Apple 公证。升级前先退出旧版应用。

macOS 1.0.2 起，桌面端可以**在应用内检查并安装界面更新**（1.0.4 起清单由公开仓的 release 资产提供）。：界面资源热更新只下载几 MB、重载界面即可生效，不需要重装；Windows 的安装与更新都改为当前用户目录，不再需要管理员权限。macOS 包覆盖 D / MODULE 图标（含随包内核），仍为 ad-hoc 签名、未公证；旧数据迁移诊断仍有已知权限失败，请阅读 Release 说明和 `macos-known-limitations.txt`。已有实例继续使用原先绑定的内核。

内核版本、验证范围和签名状态请查看对应版本的发布说明。
