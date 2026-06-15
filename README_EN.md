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

The Ultimate Music Downloader: Supports lossless audio downloads, batch downloading, one-click downloads, and playlist downloads.

Enables music search and downloading from major streaming platforms—including Kugou, Kuwo, QQ Music, NetEase Cloud Music, Migu, and others—with full support for downloading lossless audio files.

Based on the [musicdl](https://github.com/CharlesPikachu/musicdl) project, modified from the [musicdlgui.py](https://github.com/CharlesPikachu/musicdl/blob/master/examples/musicdlgui/musicdlgui.py) file, and then optimized the interface and functionality using AI tools.

### What's New (v2.0)

#### 🎯 Search Experience
- **Interruptible Search**: Cancel search anytime; results already fetched are preserved
- **Concurrent Search**: Multiple music sources searched simultaneously for faster results
- **Real-time Progress**: Live progress updates showing completed sources

#### 🎵 Sample Rate Display
- New "Sample Rate" column in search results
- Auto-detect sample rate for each track (44.1kHz / 48kHz / 96kHz etc.)
- Identify Hi-Res audio at a glance

#### ⚙️ Settings Persistence
- **Music Sources**: Remembers your last source selection
- **Results Per Source**: Remembers your search limit setting
- **Download Directory**: Remembers your last save location

#### 🎨 UI Improvements
- Toast notifications replace popup dialogs — no more focus stealing
- Search/download completion messages won't interrupt your workflow

#### 📦 Packaging
- Auto-detect and bundle ffprobe — no manual installation needed
- Cross-platform support: Windows / Linux / macOS


### Screenshots:

<table align="center" border="0" cellpadding="10">

  <tr>
    <td align="center">
      <img src="images/1.png" width="350"><br>
      <b>Image1</b>
    </td>
    <td align="center">
      <img src="images/2.png" width="350"><br>
      <b>Image2</b>
    </td>
    <td align="center">
      <img src="images/3.png" width="350"><br>
      <b>Image3</b>
    </td>
  </tr>
</table>

### Quick Start:

```bash
# Requires Python 3.13+
git clone https://github.com/MrsEWE44/musicDownload.git
cd musicDownload
python -m venv gqb313
# Windows
gqb313\Script\Activate.bat
# Linux/macOS
source gqb313/bin/activate

pip install -r requirements.txt
python musicdownload.py 
```

### Build Release:

```bash
# Requires Python 3.13+
git clone https://github.com/MrsEWE44/musicDownload.git
cd musicDownload
python -m venv gqb313
# Windows
gqb313\Script\Activate.bat
# Linux/macOS
source gqb313/bin/activate

pip install -r requirements.txt

# Windows
.\make_release.bat

# Linux/macOS
bash make_release.sh
```

#### Bundling ffprobe (Optional)

The build script auto-detects and bundles ffprobe:

- **Linux/macOS**: Automatically copies from system (`/usr/bin/ffprobe`)
- **Windows**: Download `ffprobe.exe` and place in project directory

Download from: https://github.com/BtbN/FFmpeg-Builds/releases
Get `ffmpeg-master-latest-win64-gpl.zip`, extract and copy `ffprobe.exe` to project folder.


### Changelog

#### 2026-06-15
- ✅ Interruptible search with partial results
- ✅ Concurrent multi-source search
- ✅ Sample rate detection and display
- ✅ Music source selection persistence
- ✅ Search limit persistence
- ✅ Toast notifications (no focus stealing)
- ✅ Auto-bundle ffprobe
- ✅ Debug/Release versions share same codebase

