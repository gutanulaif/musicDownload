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
# 需要用Python3.13
git clone https://github.com/MrsEWE44/musicDownload.git
cd musicDownload
python -m venv gqb313
gqb313\Script\Activate.bat
cd musicDownload
pip install -r requirements.txt
python musicdownload.py 
```

### 打包教程：

```
# 需要用Python3.13
git clone https://github.com/MrsEWE44/musicDownload.git
cd musicDownload
python -m venv gqb313
gqb313\Script\Activate.bat
cd musicDownload
pip install -r requirements.txt

# 如果你是Windows系统，运行make_release.bat文件
.\make_release.bat

# 如果你是Linux、MacOS系统，运行make_release.sh文件
bash make_release.sh
```


