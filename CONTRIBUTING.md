# 参与贡献

开发环境为 Windows 和 Python 3.12。运行 `install-local.bat` 创建环境。

提交前运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -p "test_*.py"
```

网页检查 `check_ui.py` 会生成运行数据，应在独立测试副本运行，避免影响正在处理的任务。
问题反馈请附版本号、复现步骤和脱敏日志。请勿提交 `.env`、Cookie、会话、数据库、模型或私人视频。
部署文档见 [DEPLOYMENT](docs/DEPLOYMENT.md)，版本规则和发布流程见 [RELEASING](docs/RELEASING.md)。
