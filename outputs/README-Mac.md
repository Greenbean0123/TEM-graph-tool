# TEM Studio for macOS

此包包含同一套跨平台桌面程序：逐图标尺测量、在图像上拖动大比例尺、黑/白样式、粒径分布与高斯拟合、PNG/TIFF/PDF 导出、可滚动的左侧参数区。

在 [GitHub Releases](https://github.com/Greenbean0123/TEM-graph-tool/releases) 下载对应架构的 Mac ZIP，解压后运行 TEM-Studio.app，无需安装 Python。Apple Silicon 与 Intel 版本均经过 GitHub 原生 macOS 构建及打包应用自检。

下方说明适用于源码启动包与自行构建；Windows EXE 不能在 macOS 运行。

## 运行

1. 将 ZIP 复制到 Mac，解压到有写入权限的位置。
2. 安装带 Tkinter 的 Python 3（可从 https://www.python.org/downloads/macos/ 获取）。
3. 双击 `Start-TEM-Studio.command`。首次启动会创建本目录 `.venv` 并联网安装 requirements.txt 中的开源库。
4. 如果 Finder 提示没有执行权限，在终端进入解压目录运行 `chmod +x *.command`，或直接运行 `bash Start-TEM-Studio.command`。

可通过 `TEM_PYTHON=/完整路径/python3 bash Start-TEM-Studio.command` 选择 Python。

左侧三个参数页均支持滚动条与鼠标滚轮/触控板滚动；缩小窗口后仍可访问底部设置。Mac 不包含实验样本，请 Add TIFF / Open diameter CSV 导入本地文件。

## 在 Mac 构建独立 .app

双击 `Build-Mac.command`，或终端运行 `bash Build-Mac.command`。

输出 `dist/TEM-Studio.app` 与带版本及处理器架构名称的 ZIP。构建脚本会实际运行新 .app 的自检，检查小窗口滚动、Distribution 预览、Count/Frequency 的 PNG/PDF 导出、统计结果与更新验证。自检通过后才生成分发 ZIP，报告在 `dist/packaged-self-test.json`。

在 Apple Silicon Mac 上用原生 ARM Python 构建 ARM 版本；Intel Mac 用 Intel Python 构建 Intel 版本。`.app` 为本机构建，未经 Apple Developer ID 签名或公证。收件人的系统可能需要在“系统设置 → 隐私与安全性”允许打开。

完整功能说明见 README.md。
