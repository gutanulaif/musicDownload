<h1 align="center">MusicDownload</h1>

<p align="center">
  🇺🇸 <a href="./README_EN.md">English</a> | 🇨🇳 <a href="./README.md">简体中文</a>
</p>

<p align="center">
<a href="https://peps.python.org/pep-0719"><img alt="PyPI - Python Version" src="https://img.shields.io/pypi/pyversions/musicdl">
</a>
 <a href="https://pypi.org/project/musicdl"><img alt="PyPI - Version" src="https://img.shields.io/pypi/v/musicdl">
</a>
 <a href="https://github.com/MrsEWE44/musicDownload/releases"><img alt="GitHub Release" src="https://img.shields.io/github/v/release/MrsEWE44/musicDownload"></a>
 <a><img alt="GitHub Repo stars" src="https://img.shields.io/github/stars/MrsEWE44/musicDownload?style=flat"></a>
 <a><img alt="GitHub forks" src="https://img.shields.io/github/forks/MrsEWE44/musicDownload?style=flat"></a>
 <a><img alt="GitHub Downloads (all assets, all releases)" src="https://img.shields.io/github/downloads/MrsEWE44/musicDownload/total"></a>
 <a><img alt="GitHub watchers" src="https://img.shields.io/github/watchers/MrsEWE44/musicDownload?style=flat"></a>
 
</p>

宇宙超级无敌音乐下载器，支持无损音乐文件下载、批量下载、一键下载，支持歌单下载。

支持酷狗、酷我、QQ音乐、网易云、咪咕等主流音乐平台音乐搜索、下载。支持无损音乐文件下载。


基于 [musicdl](https://github.com/CharlesPikachu/musicdl) 项目做的，基于 [musicdlgui.py](https://github.com/CharlesPikachu/musicdl/blob/master/examples/musicdlgui/musicdlgui.py) 文件修改的，然后用豆包Ai优化了一下界面和功能。

### 主要更新 (v2.0)

#### 🎯 搜索体验优化
- **搜索可中断**：搜索过程中可随时点击"取消"按钮，已返回的结果会保留在表格中
- **并发搜索**：多个音乐源同时搜索，速度更快
- **实时进度**：搜索过程中实时显示当前进度和已完成的源

#### 🎵 新增采样率显示
- 搜索结果新增"采样率"列
- 自动检测每首歌的采样率（44.1kHz / 48kHz / 96kHz 等）
- 帮助识别 Hi-Res 高解析度音频

#### ⚙️ 设置持久化
- **音乐源选择**：记住上次勾选的音乐平台
- **单源获取数量**：记住上次设置的搜索结果数量
- **保存目录**：记住上次选择的下载目录

#### 🎨 界面改进
- Toast 通知替代弹窗提示，不抢输入焦点
- 搜索完成、下载完成等提示不再打断用户操作

#### 📦 打包优化
- 自动检测并打包 ffprobe，无需用户手动安装
- 支持 Windows / Linux / macOS 跨平台打包


### 软件截图:

<table align="center" border="0" cellpadding="10">

  <tr>
    <td align="center">
      <img src="images/1.png" width="350"><br>
      <b>图片1</b>
    </td>
    <td align="center">
      <img src="images/2.png" width="350"><br>
      <b>图片2</b>
    </td>
    <td align="center">
      <img src="images/3.png" width="350"><br>
      <b>图片3</b>
    </td>
  </tr>
</table>

### 使用教程：

```bash
# 需要用Python3.13+
git clone https://github.com/MrsEWE44/musicDownload.git
cd musicDownload
python -m venv gqb313
# Windows
gqb313\Script\Activate.bat
# Linux/MacOS
source gqb313/bin/activate

pip install -r requirements.txt
python musicdownload.py 
```

### 打包教程：

```bash
# 需要用Python3.13+
git clone https://github.com/MrsEWE44/musicDownload.git
cd musicDownload
python -m venv gqb313
# Windows
gqb313\Script\Activate.bat
# Linux/MacOS
source gqb313/bin/activate

pip install -r requirements.txt

# 如果你是Windows系统，运行make_release.bat文件
.\make_release.bat

# 如果你是Linux、MacOS系统，运行make_release.sh文件
bash make_release.sh
```

#### 打包 ffprobe（可选）

打包脚本会自动检测并打包 ffprobe：

- **Linux/macOS**：自动从系统复制 `/usr/bin/ffprobe`
- **Windows**：需要手动下载 `ffprobe.exe` 放到项目目录

下载地址：https://github.com/BtbN/FFmpeg-Builds/releases
选择 `ffmpeg-master-latest-win64-gpl.zip`，解压后复制 `ffprobe.exe` 到项目目录。


### 更新日志

#### 2026-06-15
- ✅ 搜索可中断，支持取消后显示已获取结果
- ✅ 并发搜索多个音乐源
- ✅ 新增采样率检测和显示
- ✅ 音乐源选择持久化
- ✅ 单源获取数量持久化
- ✅ Toast 通知替代弹窗，不抢焦点
- ✅ 自动打包 ffprobe
- ✅ Debug 版本与 Release 版本代码同步

