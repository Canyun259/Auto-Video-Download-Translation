# 本地视频翻译台

[![Windows CI](https://github.com/Canyun259/Auto-Video-Download-Translation/actions/workflows/ci-release.yml/badge.svg?branch=main&event=push)](https://github.com/Canyun259/Auto-Video-Download-Translation/actions/workflows/ci-release.yml)

[![Release](https://img.shields.io/github/v/release/Canyun259/Auto-Video-Download-Translation?cacheSeconds=300)](https://github.com/Canyun259/Auto-Video-Download-Translation/releases/latest)

在 Windows 本机完成视频下载、语音识别、中文翻译、字幕审核与烧录，通过网页操作。

**最新发布版：v1.3.0** · [下载发布版本](https://github.com/Canyun259/Auto-Video-Download-Translation/releases/latest) · [更新日志](CHANGELOG.md) · [部署与升级](docs/DEPLOYMENT.md)

## 能做什么

- 扫描 Instagram（帖子/Reels）、YouTube 频道与视频；可选 X 账号来源。
- 粘贴单条视频地址导入，无需加入监控账号；失败时显示原因与处理建议。
- 处理前或审核区导入 SRT / VTT，支持中文及双语字幕；处理前导入可跳过语音识别与翻译。
- 导入已下载的视频：填写本机路径或上传文件，按内容去重。
- 生成原文、中文与双语 SRT、ASS 字幕，保留原视频；也可烧录成双语视频。
- 在审核区修改字幕、时间轴和标题。可分别设置中英文颜色、字体、描边、背景框、位置和双语顺序，并查看实际烧录截图。
- 可选 NVIDIA CUDA；默认 CPU 可运行。
- 中文标题、发布者和时间筛选、处理进度、封面保存，以及按平台/账号整理输出目录。

## 快速部署

适用于 **Windows 10/11 + Python 3.12 64 位**。发布包是源码包，需要联网安装依赖及首次下载模型。

1. 从 [Releases](https://github.com/Canyun259/Auto-Video-Download-Translation/releases/latest) 下载 ZIP 并解压。
2. 安装 Python 3.12（包含 Tkinter）、FFmpeg/ffprobe；YouTube 推荐 Node.js LTS。具体命令见 [部署指南](docs/DEPLOYMENT.md)。
3. 双击 **安装或更新依赖.bat**（或 `install-local.bat`）。自动创建虚拟环境和首次 `.env`，保留已有配置。
4. 使用自动翻译时，编辑 `.env`，填写 `TRANSLATE_API_KEY`、`TRANSLATE_BASE_URL`、`TRANSLATE_MODEL`。Base URL 使用供应商的 HTTPS OpenAI 兼容接口，不带 `/chat/completions`；默认模型为 `qwen-mt-flash`。
5. 运行 `check-local.bat`，通过后双击 **启动视频翻译台.bat**。打开 http://127.0.0.1:8501。

可选：将可信的 `ffmpeg.exe` 和 `ffprobe.exe` 放在项目 `tools/bin/`，无需修改 PATH。

## 使用流程

**本地视频**：展开页面顶部的本地视频导入 → 路径/上传 → 待选择。

**在线视频**：顶部「通过视频地址导入」可导入单条视频；也可在侧栏填写账号、频道或单条视频 HTTPS 链接 → 保存设置后点击手动检测 → 待选择。YouTube 可分别添加频道 `/videos`、`/shorts`。

选择输出方式后开始处理。已有字幕时，将「字幕获取方式」设为「导入现成字幕」，上传 SRT / VTT 后可直接送审或保存，不需要翻译 API 配置。中文模式直接使用全文；双语模式要求每条首行中文、后续行原文。字幕随任务保存，重试无需重新上传；下载后按实际视频时长再次校验，错误不会回退自动翻译。

审核区也可导入替换字幕，原审核稿自动备份，之后可继续编辑与预览。文件支持 UTF-8、GB18030、带 BOM 的 UTF-16，最大 5 MB。

画面文字识别与翻译已移除，历史审核稿中的画面字幕仍可使用。

输出流程：

- **独立字幕**：视频和字幕完成后进入已完成，可下载字幕、返回审核。
- **烧录字幕**：翻译后进入审核区 → 修改文字/样式 → 选择时间点更新预览 → 确认烧录。

成品保存于 `local-data/output/平台/账号/日期_标题_短编号/`，保留源视频、字幕及审核稿。完成时一并保存封面为 cover.jpg。本地视频从原片取帧，已完成详情可获取或下载封面。字幕锚点的横向为居中位置、纵向为底边，单位为画面百分比。修改后需重新生成预览，长字幕会自动缩小以适应画面。

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
- GPU：`install-local.bat --gpu` 安装可选库，网页选择自动/CUDA；硬件和驱动需兼容。视频烧录仍使用 CPU。

## 限制与数据

识别和翻译结果需要审核。中文字幕保留句中标点，每行末尾的标点会自动去除。

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
| `tests/` | 单元、界面与本地媒体测试 |

开发与测试见 [CONTRIBUTING.md](CONTRIBUTING.md)。许可为 [MIT](LICENSE)，第三方依赖、模型和服务适用各自条款。


## 列表管理与增量检测

视频列表按当前分区加载，每页最多 12 个视频。展开详情后才加载审核设置、成品播放器和字幕下载。发布者筛选可搜索候选并勾选多个账号。旧视频缺少发布者或时间时，可在详情中点「补全发布信息」。

待选择、审核区和已完成均提供单条删除及本页批量删除。删除只移出 WebUI，原视频、字幕及成品均保留；删除标记保存在本地数据库中，后续检测不会重新入库。处理中任务不可删除。删除标记与检测时间随 `local-data/library.sqlite` 备份，删除数据库将丢失这些记录。

每个来源独立记录上次成功检测的开始时间；后续检测跳过更早的视频，失败不会推进记录。首次检测保留原扫描范围。平台仅提供日期时会保留边界当天，缺少日期时继续按视频 ID 去重，避免因时间不明确漏掉视频。扫描数量仍限制每轮检查范围，停机较久或更新密集时应调大。列表及发布时间仍需通过平台接口获取。

任务中可选择“只显示中文字幕”，审核区也可切换；原文、中文与双语字幕文件分别保留。默认优先翻译已有的平台或内嵌文字字幕，无可读字幕时识别语音。画面上已经印出的原文不会被抹除。

监控设置中的代理地址留空时采用系统代理，也可填写 HTTP/HTTPS 代理地址。修改后点击「保存设置」，再点击「手动检测」。请保持代理软件运行。


## YouTube 限流保护
频道检测只读取列表，避免逐条打开视频；列表未提供的发布时间可能显示未知，仍按视频 ID 去重。YouTube 请求采用下载器建议的请求、下载和字幕间隔；检测、导入、下载共用串行请求与冷却状态。遇到明确的会话限流或 HTTP 429 时暂停 YouTube 请求一小时，重启和手动检测不会绕过冷却，其他平台不受影响。侧栏显示剩余时间，到期后可重新检测。遇到连接提前中断（SSL EOF）时，单条视频查询或下载会自动重试一次，可续传已有的下载片段。程序不能提前解除平台限流，请勿反复重试。


## 手动检测
不再定时轮询，启动程序、刷新页面或保存设置都不会发起来源检测。点击「手动检测」才扫描一次，检测中重复点击不会追加任务。每个来源以本次点击的时间记录成功检测起点，下一次只接收此时间之后的视频；失败或限流不推进记录。侧栏可查看各来源上次成功手动检测时间。旧的自动检测时间保留但不再参与过滤，升级后首次手动检测按扫描数量读取并按视频 ID 去重。发布时间缺失的视频仍按 ID 去重。
