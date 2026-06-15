# CLAUDE.md

## 项目概述

MusicDownload — 基于 musicdl 的全网音乐下载器，PySide6 GUI，支持 17 个音乐源并发搜索、在线试听、批量下载。

## 开发环境

- Python 3.14（venv: `gqb313/`）
- PySide6 + musicdl
- 打包：`make_release.sh` → PyInstaller

## 运行与测试

```bash
gqb313/bin/python3 musicdownload.py       # 直接运行（开发用）
gqb313/bin/python3 musicdownload_debug.py  # 调试版（控制台输出）
gqb313/bin/python3 -c "import musicdownload; print('OK')"  # 快速验证 import
```

**不要在对话中执行打包编译**，会阻塞聊天。用户确认功能正常后自行编译。

## Qt / PySide6 经验（重要）

### 1. addLayout vs addWidget — 布局问题首要排查点

| | `addLayout()` | `addWidget()` |
|---|---|---|
| 插入物 | `QLayoutItem` | `QWidgetItem` |
| 有 SizePolicy？ | ❌ 没有 | ✅ 有 |
| 外层如何处理 | 默认拉伸填满 | 尊重 size policy |

**当布局区域出现不该有的空白/拉伸时，首先检查是否用了 `addLayout`。**

### 2. FlowLayout + heightForWidth 的正确用法

FlowLayout 有 `hasHeightForWidth()=True`，但必须放在 QWidget 里才能传播高度计算：

```python
# ❌ 不传播 heightForWidth
parent_layout.addLayout(flow_layout)

# ✅ 正确方式
wrapper = QWidget()
wrapper.setLayout(flow_layout)
wrapper.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
parent_layout.addWidget(wrapper)
```

### 3. QVBoxLayout 不传播子 layout 的 heightForWidth

`QVBoxLayout.addLayout(child_layout)` 不会使用 child 的 `heightForWidth()` 来计算高度。需要将 child layout 包裹在 QWidget 中再 `addWidget`。

### 4. Qt 布局调试原则

1. **先画父子关系树** — 列出所有 `addWidget`/`addLayout` 调用
2. **`addLayout` = 危险信号** — 除非确认不需要 size policy
3. **CSS 是最后手段** — 布局问题优先查 layout 机制，不是 padding/margin
4. **最小实验** — 改一处验证一次，不要批量改完再测

## 播放器相关

### PySide6 多媒体

- 使用 `QMediaPlayer` + `QAudioOutput`（Qt6 API，不是 Qt5 的 setMedia）
- Linux 后端：GStreamer 或 FFmpeg（`QT_MEDIA_BACKEND=ffmpeg`）
- 需要 `gst-plugins-base gst-plugins-good gst-plugins-bad gst-plugins-ugly gst-libav`
- URL 可以直接播放（HTTP/HTTPS），不需要先下载

### SongInfo 字段名

```python
# musicdl 的 SongInfo.todict() 返回的字段名（注意不是 songname/artist）
song_info.get("song_name")    # ✅ 歌曲名
song_info.get("singers")      # ✅ 歌手
song_info.get("download_url") # ✅ 播放/下载 URL（不是 play_url）
```

### QStyle 标准图标

```python
# PySide6 中的正确名称（SP_ 前缀）
QStyle.StandardPixmap.SP_MediaPlay
QStyle.StandardPixmap.SP_MediaPause
QStyle.StandardPixmap.SP_MediaStop
QStyle.StandardPixmap.SP_MediaSkipBackward
QStyle.StandardPixmap.SP_MediaVolume

# 深色背景上需要重新着色
@staticmethod
def _colorize_icon(std_icon, color="#e0e0e0", size=20):
    pixmap = std_icon.pixmap(QSize(size, size))
    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(color))
    painter.end()
    return QIcon(pixmap)
```

## UI 设计规范

### 色彩体系（Teal 主题）

```
主色:     #14b8a6    hover: #2dd4bf    pressed: #0d9488
背景:     #f1f5f9    卡片: #ffffff     边框: #e2e8f0
文字主:   #0f172a    文字次: #475569   文字弱: #94a3b8
选中背景: #ccfbf1
播放器:   #1e293b（深蓝灰）
```

### Toast 通知（替代 QMessageBox）

QMessageBox 会抢窗口焦点，用自定义 ToastLabel（QLabel 子控件）替代：

```python
class ToastLabel(QLabel):
    # 作为主窗口的子控件，不抢焦点
    # WA_ShowWithoutActivating 对 QMessageBox 无效
    # Wayland 下 Tool window flag 不显示，必须用子控件
```

### 播放器固定高度

播放器在底部用 `setFixedHeight(56)` + `SizePolicy.Fixed` 防止垂直扩展。

## 音乐源

- 国内源：酷我、酷狗、咪咕、网易云、QQ、千千、汽水
- 海外源：Apple、Deezer、5sing、Jamendo、Joox、Qobuz、SoundCloud、StreetVoice、Spotify、TIDAL
- 搜索 API：`music_client.music_clients[source].search(keyword, num_threadings=N)`
- 并发搜索用 `ThreadPoolExecutor`，取消用 `future.done()` 轮询 + `executor.shutdown(wait=False)`
