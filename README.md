# 本地视频翻译台

面向 Windows 的视频发现、翻译、人工审核和双语字幕烧录工具，通过本地网页操作。
本仓库仅包含本地部署代码，不包含云端服务、Docker、用户账号或运行数据。

## 功能
- 定时扫描 Instagram（帖子和 Reels）、YouTube 频道及单条视频，支持可选 X 来源。
- 候选列表展示封面、时长、发布者、发布时间和中文标题。
- 按发布时间排序、按平台筛选、搜索发布者。
- 手动选择视频后下载、识别和翻译，显示分阶段进度。
- 翻译后进入审核区，允许修改原文、中文、标题及时间轴，再确认烧录。
- 横竖屏字幕自适应换行；画面文字 OCR 默认关闭。
- Windows 一键启动、重启、停止、重复启动检测和日志。
- CPU 语音识别及可选 NVIDIA CUDA 加速。

## 准备环境
推荐 Windows 10/11、Python 3.12（包含 Tkinter，安装时加入 PATH）。
安装包含 libass/subtitles 滤镜的 FFmpeg，并将 ffmpeg、ffprobe 加入 PATH。
YouTube 部分视频可能需要 JavaScript 运行环境，程序会使用 PATH 中的 Node.js。
启动管理器依赖 Windows；其他系统的完整部署流程尚未验证。

## 安装和启动
1. 下载仓库，双击“安装或更新依赖.bat”，它会在项目目录创建 .venv 并安装基础依赖。
2. 将 .env.example 复制为 .env，填写自己的配置：
   - TRANSLATE_API_KEY：翻译 API 密钥。
   - TRANSLATE_BASE_URL：从供应商控制台复制 HTTPS OpenAI 兼容 Base URL，通常以 /v1 结尾，不带 /chat/completions。
   - TRANSLATE_MODEL：模型名，默认为 qwen-mt-flash。其他模型需支持聊天接口和 JSON 输出。
   - IG_USERNAME：需要 Instagram 登录时填写。
   - X_BEARER_TOKEN：仅扫描 X 账号时需要。
3. 双击“启动视频翻译台.bat”，浏览器自动打开 http://127.0.0.1:8501。
4. 在侧栏填写账号、频道或视频 HTTPS 链接，每行一个，保存后扫描。YouTube 可分别添加频道 /videos 和 /shorts 页面。
5. 在待选择区选择视频，翻译完成后进入审核区，修改并确认烧录。
6. 成品保存在 local-data/output/平台/账号/日期_标题_短编号/result.mp4，同时保留字幕和审核稿。

启动不会重复安装依赖；安装入口不更新项目代码。更新代码前停止服务，更新后按需安装依赖再启动。
关闭网页或管理窗口不会停止服务，请使用“停止视频翻译台.bat”。处理中停止可能需要重试，已排队任务在重启后继续。
管理窗口可检查环境、打开日志文件夹。日志位于 local-data/logs。

## 可选 NVIDIA 加速
在项目目录 PowerShell 执行：

    .\.venv\Scripts\python.exe -m pip install -r requirements-gpu.txt

保持显卡驱动和 CUDA 库兼容，在网页选择“自动”或“CUDA”并保存。
自动模式在基础 CUDA 检查失败时使用 CPU，显存不足等运行错误需人工处理。
首次语音模型下载需要网络。OCR 和 FFmpeg libx264 编码仍在 CPU 上执行。
可选 GPU 依赖不能保证适用于所有 NVIDIA 显卡。

## 平台登录
仅访问自己有权访问的内容，程序不绕过平台安全验证。

1. 在浏览器登录 Instagram 并完成验证。
2. 用自己信任的工具，仅导出需要的平台的 Netscape 格式 Cookies。
3. 创建 local-data/secrets，将导出文件保存为 cookies.txt。
4. 在项目目录运行（替换 YOUR_USERNAME）：

    .\.venv\Scripts\python.exe import_instagram_cookies.py --username YOUR_USERNAME --check-api current-user

成功后生成 instagram.session，在 .env 中设置相同的 IG_USERNAME，重启。
若遇到 feedback_required 或安全验证，先回浏览器处理，不要反复重试。
YouTube 公开内容可先不提供凭证；需要登录时，同一路径的 Cookies 文件供下载器使用。
X 为可选能力，不添加来源即可不使用；账号扫描需自己的 API 访问权限。

## 字幕、费用和限制
- faster-whisper 识别语音并生成时间戳，中文沿用原文分段时间轴；识别和翻译结果需要审核。
- 尝试保留一份平台人工字幕，但烧录字幕来自重新识别音轨，暂不支持手动导入 SRT。
- OCR 每约 0.5 秒采样，可能识别标志、用户名等无关文字。译文统一置顶，不是逐字贴在原字幕旁。
- 语音识别和烧录在本地执行。候选视频标题会自动发送到翻译接口；字幕在选择处理后发送。两者都可能产生 API 费用。
- 进度条表示当前阶段，不是精确剩余时间；模型加载或未知下载大小时可能停在零。
- 平台限制、接口变化和网络可能导致发现或下载失败，不保证获取全部视频。
- 服务只监听本机，没有面向公网的身份认证，不应直接开放到公网。
- 运行数据不会自动清理。local-data、.env、登录凭证、模型和视频均不应提交 Git。

## 代码结构
- local_ui.py：网页、视频发现和处理队列。
- subtitle_core.py：时间轴、翻译、字幕导出及可选 X 发现函数。
- review_tools.py：审核校验、字幕排版和烧录。
- mt_translation.py：千问 MT 适配。
- video_metadata.py：视频信息和数据库迁移。
- launcher.py：Windows 启动管理。
- import_instagram_cookies.py：导入用户导出的 Cookies。

## 开发验证
安装依赖后，在项目目录运行：

    .\.venv\Scripts\python.exe -m unittest discover -p "test_*.py"

check_ui.py 为界面冒烟检查，会生成本目录的运行数据，只应在未运行服务的独立测试副本中使用。
单元测试不调用真实账号或翻译接口，不代表所有平台的端到端验证。

## 开源与贡献
使用 MIT 许可证，见 LICENSE。第三方依赖、模型及服务适用各自的许可证和条款。
提交问题时提供复现步骤和脱敏错误信息，不要上传密钥、Cookie、登录会话、私人视频或运行数据库。

## 可读的视频目录
视频按“平台 / 发布账号 / 发布日期_中文标题_短编号”保存，优先使用中文标题，缺失时使用原标题。
非法文件名字符会替换，过长标题截短；短编号防止同名覆盖。首次下载后目录固定，后续编辑标题不会更改路径。
旧编号目录仍兼容。若从旧版本升级，可先停止服务，在项目目录执行：
    .\.venv\Scripts\python.exe output_paths.py
整理工具只移动已知的视频目录，不覆盖现有目标；没有历史数据时无需运行。

审核确认后，烧录任务会将平台封面保存为同目录 cover.jpg。封面下载失败不会阻断视频烧录，已完成页提供“保存/重试封面”，也可用于为旧成品补存封面。
