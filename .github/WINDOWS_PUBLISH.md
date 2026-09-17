# Windows 发布检查

发布下载版本使用本地命令，不经由 CI workflow：在 `ant-browsers` 里运行

```sh
make publish-windows-release WINDOWS_VERIFICATION_RUN=<mes-browser-windows-build 上成功的完整验证 run id>
```

（对应 `tools/windows-verification/publish_verified_windows.py`）。命令下载该 run 产出的已验证安装包，核对安装包、`SHA256SUMS.txt` 与本地源码提交三者一致后，先建 draft release、上传，再从 GitHub API 回读远端资产摘要确认一致，最后才取消 draft。任何一步不一致都不发布，也拒绝覆盖已存在的同名 tag。全程只需要本机已登录的 `gh`，不需要任何仓库 secret。

本地无发布副作用的验证：

```sh
python3 -m unittest discover -s .github/scripts -p 'test_*.py' -v
```

`windows_verification.py` 的 `windows-release-v2` 是版本化数据契约，要求额外执行缺失数据库恢复的拒绝与同意场景（`missing-state-recovery`），共 12 项；桌面更新入口保留同契约的本地副本，不从相邻仓库导入源码。修改必需场景时同步消费者与回归用例，旧报告不得自动升级为通过。
