# 参与贡献

开发环境为 Windows 和 Python 3.12。运行 `install-local.bat` 创建环境。

提交前运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t .
.\.venv\Scripts\python.exe check_ui.py
```

测试集中在 `tests/`。网页检查使用临时视频库。
问题反馈请附版本号、复现步骤和脱敏日志。请勿提交 `.env`、Cookie、会话、数据库、模型或私人视频。
部署文档见 [DEPLOYMENT](docs/DEPLOYMENT.md)，版本规则和发布流程见 [RELEASING](docs/RELEASING.md)。
