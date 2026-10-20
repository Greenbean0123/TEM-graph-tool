TEM Graph tool 0.0.4

| 你的电脑 / Computer | 下载 / Download |
| --- | --- |
| Windows 64 位电脑 / Windows x64 | [Windows EXE](https://github.com/Greenbean0123/TEM-graph-tool/releases/download/v0.0.4/TEM-graph-tool-0.0.4-windows-x86_64.exe) |
| Mac：Apple Silicon，M 系列芯片 | [Apple Silicon DMG — arm64](https://github.com/Greenbean0123/TEM-graph-tool/releases/download/v0.0.4/TEM-graphic-tool-0.0.4-macos-arm64.dmg) |
| Mac：Intel 处理器 | [Intel DMG — x86_64](https://github.com/Greenbean0123/TEM-graph-tool/releases/download/v0.0.4/TEM-graphic-tool-0.0.4-macos-x86_64.dmg) |

**Mac 安装：**打开对应 DMG，将 **TEM Graph tool** 拖到 **Applications（应用程序）**。复制完成后弹出 DMG，再从 Applications 启动。苹果菜单 → 关于本机中，显示 M 系列芯片选 Apple Silicon，显示 Intel 选 Intel。

### 新功能与修复

- TEM 可叠加紧凑的粒径分布图：拖动位置、拖动右下角改变大小，支持白底、透明底和仅绘图区白底。
- 柱子、Gaussian 拟合线分别选色、调整透明度；背景透明度也可调。默认红柱、蓝线。
- 叠加图坐标轴标签、刻度、Mean / Std / N 字号分别可调。
- 支持概率密度模式；保留 Count 和 Frequency (%)。使用用户 CSV，不自动测颗粒。
- 独立分布图和合成图均支持 SVG / PDF；分布图柱子、曲线和文字保留矢量，TEM 本身保留为图像。PNG / TIFF 仍可导出。
- 叠加进度条显示读取、标定、绘图、合成及导出阶段。
- 浅色 / 深色主题，80%–200% 界面缩放，预览缩放与平移。
- 拖动中间分割条只预览分割线，松开后应用布局，先显示低清预览再加载清晰图，避免持续重排全部控件。
- 预览顶部显示当前 TIFF 名；叠加或查看分布时同时标明 CSV。标尺参数按 TIFF 保存；CSV 和直方图参数仍使用当前共用选择，请选对样本 CSV。
- 新图片默认标尺线粗 36 px、字体 128 px，原有项目设置优先。原始 TIFF 不会被覆盖。
- 应用名称改为 **TEM Graph tool**。

已安装旧版的用户可在 **Updates → Check for Updates** 更新。更新成功且新版正常启动后，会清理旧程序备份与临时更新包；研究数据和项目保留。

Mac ZIP 附件供自动更新使用；手动安装请选择上面的 DMG。`updates.json` 为签名更新清单，`SHA256SUMS.txt` 提供安装包校验值。Mac 使用 ad-hoc 签名，未配置 Apple Developer ID 公证。
