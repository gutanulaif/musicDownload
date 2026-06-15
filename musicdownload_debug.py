"""Debug 版本 - 与 musicdownload.py 代码相同，用于 pyinstaller -c 打包（带控制台输出）"""
from musicdownload import MusicDownloader, QApplication, sys

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MusicDownloader()
    win.show()
    sys.exit(app.exec())
