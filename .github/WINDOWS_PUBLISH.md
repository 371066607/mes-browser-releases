# Windows 发布检查

`Publish verified Windows packages` 需要明确填写版本、原构建 run、成功的完整验证 run 和下载归档 SHA-256。归档可以来自完整构建或 installer-only 独立验证；`fast`、失败/跳过场景、未提交源码快照均被拒绝。

保留现有 `WINDOWS_PACKAGE_ARTIFACT_URL` 临时下载地址 secret。另需 `WINDOWS_BUILD_READ_TOKEN` 能读取 `371066607/mes-browser-windows-build` 的 Actions runs/artifacts（最小只读范围）；没有配置时尝试当前 `GH_TOKEN`，若没有跨仓读取权限会在创建 Release 前失败。不要把 token 或临时 URL 写入日志。

报告必须匹配原安装器、原校验文件和来源记录；发布脚本还向 GitHub API 核对 main 上受信任 workflow 的成功运行、提交及唯一 artifact digest。通过后才创建 draft、上传、核对远端哈希并发布。保持 Windows Server 自动验证与用户 Windows 11 验收的区别。

本地无发布副作用的验证：

```sh
python3 -m unittest discover -s .github/scripts -p 'test_*.py' -v
```

`windows_verification.py` 的 `windows-release-v1` 是版本化数据契约；桌面更新入口保留同契约的本地副本，不从相邻仓库导入源码。修改必需场景时同步消费者与回归用例，旧报告不得自动升级为通过。
