# 本地视频翻译台

[![Windows CI](https://github.com/Canyun259/Auto-Video-Download-Translation/actions/workflows/ci-release.yml/badge.svg)](https://github.com/Canyun259/Auto-Video-Download-Translation/actions/workflows/ci-release.yml)
[![Release](https://img.shields.io/github/v/release/Canyun259/Auto-Video-Download-Translation)](https://github.com/Canyun259/Auto-Video-Download-Translation/releases/latest)

在 Windows 本机完成视频下载、语音识别、中文翻译、字幕审核与烧录，通过网页操作。

**当前版本：v1.1.0** · [下载发布版本](https://github.com/Canyun259/Auto-Video-Download-Translation/releases/latest) · [更新日志](CHANGELOG.md) · [部署与升级](docs/DEPLOYMENT.md)

## 能做什么

- 扫描 Instagram（帖子/Reels）、YouTube 频道与视频；可选 X 账号来源。
- 导入已下载的视频：填写本机路径或上传文件，按内容去重。
- 生成原文、中文与双语 SRT、ASS 字幕，保留原视频；也可烧录成双语视频。
- 在审核区修改字幕、时间轴和标题；调整字体、字号和位置，再查看实际烧录截图。
- 可选画面 OCR、NVIDIA CUDA；默认 CPU 可运行。
- 中文标题、发布者和时间筛选、处理进度、封面保存，以及按平台/账号整理输出目录。

## 快速部署

适用于 **Windows 10/11 + Python 3.12 64 位**。发布包是源码包，需要联网安装依赖及首次下载模型。

1. 从 [Releases](https://github.com/Canyun259/Auto-Video-Download-Translation/releases/latest) 下载 ZIP 并解压。
2. 安装 Python 3.12（包含 Tkinter）、FFmpeg/ffprobe；YouTube 推荐 Node.js LTS。具体命令见 [部署指南](docs/DEPLOYMENT.md)。
3. 双击 **安装或更新依赖.bat**（或 `install-local.bat`）。自动创建虚拟环境和首次 `.env`，保留已有配置。
4. 编辑 `.env`，填写 `TRANSLATE_API_KEY`、`TRANSLATE_BASE_URL`、`TRANSLATE_MODEL`。Base URL 使用供应商的 HTTPS OpenAI 兼容接口，不带 `/chat/completions`；默认模型为 `qwen-mt-flash`。
5. 运行 `check-local.bat`，通过后双击 **启动视频翻译台.bat**。打开 http://127.0.0.1:8501。

可选：将可信的 `ffmpeg.exe` 和 `ffprobe.exe` 放在项目 `tools/bin/`，无需修改 PATH。

## 使用流程

**本地视频**：展开页面顶部的本地视频导入 → 路径/上传 → 待选择。

**在线视频**：在侧栏填写账号、频道或单条视频 HTTPS 链接 → 保存并检测 → 待选择。YouTube 可分别添加频道 `/videos`、`/shorts`。

选择输出方式后开始处理：

- **独立字幕**：视频和字幕完成后进入已完成，可下载字幕、返回审核。
- **烧录字幕**：翻译后进入审核区 → 修改文字/样式 → 选择时间点更新预览 → 确认烧录。

成品保存于 `local-data/output/平台/账号/日期_标题_短编号/`，保留源视频、字幕及审核稿。字幕锚点的横向为居中位置、纵向为底边，单位为画面百分比。修改后需重新生成预览，长字幕会自动缩小以适应画面。

关闭网页或管理窗口不会停止服务，请使用停止入口。安装或升级前请等任务结束并停止服务。

## 升级与版本

版本采用 `主版本.次版本.修订号`，`VERSION` 是唯一版本号来源，Git 标签使用 `v1.1.0` 形式。网页和启动管理器显示版本。

- **发布 ZIP 用户**：停止服务，备份 `.env`、`local-data/`，新版本解压到新目录，复制配置与数据，再安装和启动。不要搬运旧 `.venv`。
- **Git 用户**：停止服务并备份数据后，运行 `update-local.bat`。仅支持干净的 main 分支、官方 origin 和快进更新；不覆盖本地代码改动。
- 回退时使用旧代码与升级前数据备份，详见 [部署指南](docs/DEPLOYMENT.md)。

发布标签后，GitHub Actions 自动测试并生成源码 ZIP、SHA256 校验文件和 Release，详见 [版本发布规范](docs/RELEASING.md)。

## 平台登录与 GPU

- Instagram 登录：从已登录浏览器导出所需平台的 Netscape Cookies 到 `local-data/secrets/cookies.txt`，运行 `import_instagram_cookies.py --username YOUR_USERNAME --check-api current-user`，再在 `.env` 填写对应 `IG_USERNAME`。有安全验证时先回浏览器完成。
- YouTube 公开内容可先不提供凭证；需要登录时使用上述 Cookies 路径。
- X 账号扫描需自己的 `X_BEARER_TOKEN` 和 API 权限，不添加来源即可不用。
- GPU：`install-local.bat --gpu` 安装可选库，网页选择自动/CUDA；硬件和驱动需兼容。OCR 和视频烧录仍使用 CPU。

## 限制与数据

识别和翻译结果需要审核。尝试保留平台人工字幕，但生成字幕来自重新识别音轨，暂不支持手动导入 SRT。OCR 可能识别标志等无关文字，画面译文统一置顶。

语音识别和烧录在本地执行；标题和字幕会发送到你配置的翻译接口，可能产生费用。平台接口、访问权限和网络变化可能影响下载。

服务仅监听本机，没有公网登录认证。`.env`、Cookie、数据库、模型及视频属于私人运行数据，不应提交 Git；数据不会自动清理，请自行备份。日志位于 `local-data/logs/`。

## 仓库结构

| 文件/目录 | 用途 |
| --- | --- |
| `local_ui.py` / `local_import.py` | 网页、处理队列与本地视频导入 |
| `subtitle_core.py` / `mt_translation.py` | 时间轴、翻译与字幕导出 |
| `review_tools.py` | 审核、排版、预览与烧录 |
| `output_paths.py` / `video_metadata.py` | 输出目录与视频数据库 |
| `launcher.py` / `deploy.py` | 启动管理、安装、检查与升级 |
| `VERSION` / `CHANGELOG.md` | 统一版本号与更新记录 |
| `docs/` | 部署升级、版本发布文档 |
| `.github/workflows/` | Windows 测试与标签发布 |
| `test_*.py` | 单元与本地媒体集成测试 |

开发与测试见 [CONTRIBUTING.md](CONTRIBUTING.md)。许可为 [MIT](LICENSE)，第三方依赖、模型和服务适用各自条款。
