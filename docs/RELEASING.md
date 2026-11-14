# 版本管理与发布

版本格式为 `MAJOR.MINOR.PATCH`（如 `1.1.0`），Git 标签为 `v1.1.0`。

- MAJOR：不兼容升级，例如破坏已有配置或数据兼容性。
- MINOR：兼容的新功能。
- PATCH：兼容的问题修复。

`VERSION` 是唯一版本号来源，`version.py` 负责读取，网页和启动管理器显示同一版本。
更新记录写入 `CHANGELOG.md`。没有版本号的早期提交保留原历史，不补写为已发布的版本。

## 发布步骤

1. 更新 `VERSION` 和 `CHANGELOG.md`，说明新增、修复及升级注意事项。
2. 提交到 main，等待 CI 测试通过。
3. 创建并推送与 VERSION 一致的标签：

   ```powershell
   git tag -a v1.1.0 -m "Release v1.1.0"
   git push origin v1.1.0
   ```

4. 标签触发发布工作流：核对版本，执行完整单元测试及隔离的网页检查，生成源码 ZIP 及 SHA256SUMS.txt，发布到 GitHub Releases。
5. 在 Actions 和 Releases 确认成功。下载包包含启动脚本、示例配置、文档和测试，不含密钥、视频或运行数据库。

CI 使用 Windows + Python 3.12；不会访问真实平台账号或收费翻译接口，不代表所有平台和 GPU 的端到端验证。
工作流失败时不应移动已发布 tag。先修复，再使用新补丁版本发布。
