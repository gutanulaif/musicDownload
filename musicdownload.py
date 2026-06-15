import sys
import os
import re
import json
import shutil
import subprocess
import requests
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLayout,
    QSizePolicy,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QComboBox,
    QSpinBox,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMenu,
    QFileDialog,
    QMessageBox,
    QStyleOptionSpinBox,
    QStyle,
)
from PySide6.QtCore import (
    Qt,
    QThread,
    Signal,
    QSize,
    QRect,
    QPoint,
    QThreadPool,
    QRunnable,
    QObject,
    QSettings,
)
from PySide6.QtGui import QPixmap, QFont, QColor, QPainter, QAction

try:
    from musicdl import musicdl

    MUSICDL_AVAILABLE = True
except ImportError:
    musicdl = None
    MUSICDL_AVAILABLE = False
    print("警告：musicdl 库未安装，请运行 pip install musicdl")


def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "_", str(filename))


class ToastLabel(QLabel):
    """主窗口内的 Toast 通知标签"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                background-color: rgba(50, 50, 50, 220);
                color: white;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 11pt;
            }
        """)
        self.hide()

    def show_toast(self, text, duration=3000):
        self.setText(text)
        self.adjustSize()
        self._center_in_parent()
        self.show()
        self.raise_()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(duration, self.hide)

    def _center_in_parent(self):
        if self.parent():
            p = self.parent()
            x = (p.width() - self.width()) // 2
            y = (p.height() - self.height()) // 2
            self.move(x, y)


def show_message(parent, icon, title, text):
    """显示不抢焦点的 Toast"""
    icons = {
        QMessageBox.Icon.Information: "ℹ️",
        QMessageBox.Icon.Warning: "⚠️",
        QMessageBox.Icon.Critical: "❌",
    }
    prefix = icons.get(icon, "")
    if hasattr(parent, '_toast'):
        parent._toast.show_toast(f"{prefix} {text}")


class NumericTableItem(QTableWidgetItem):
    """支持按数值排序的表格项（用于大小、时长等列）"""

    def __lt__(self, other):
        if isinstance(other, QTableWidgetItem):
            my_val = self.data(Qt.ItemDataRole.UserRole)
            other_val = other.data(Qt.ItemDataRole.UserRole)
            if my_val is not None and other_val is not None:
                try:
                    return float(my_val) < float(other_val)
                except (ValueError, TypeError):
                    pass
        return super().__lt__(other)


def extract_numeric_value(text):
    """从显示文本中提取数值用于排序"""
    text = str(text).strip()
    if not text:
        return 0
    try:
        return float(text)
    except ValueError:
        pass
    if ":" in text:
        parts = text.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
        except ValueError:
            pass
    import re as _re

    m = _re.match(r"([\d.]+)", text)
    return float(m.group(1)) if m else 0


# ================= 自定义现代 UI 组件 (保留原样) =================
class ModernComboBox(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#6b7280"))
        font = self.font()
        font.setPixelSize(10)
        painter.setFont(font)
        rect = self.rect()
        painter.drawText(
            rect.adjusted(0, 0, -10, 0),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "▼",
        )
        painter.end()


class ModernSpinBox(QSpinBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = self.font()
        font.setPixelSize(10)
        painter.setFont(font)
        opt = QStyleOptionSpinBox()
        self.initStyleOption(opt)

        up_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox, opt, QStyle.SubControl.SC_SpinBoxUp, self
        )
        down_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            opt,
            QStyle.SubControl.SC_SpinBoxDown,
            self,
        )

        draw_up_rect = up_rect.translated(0, 2)
        draw_down_rect = down_rect.translated(0, -2)

        up_pressed = opt.activeSubControls == QStyle.SubControl.SC_SpinBoxUp and (
            opt.state & QStyle.StateFlag.State_Sunken
        )
        down_pressed = opt.activeSubControls == QStyle.SubControl.SC_SpinBoxDown and (
            opt.state & QStyle.StateFlag.State_Sunken
        )

        painter.setPen(QColor("#0078d4") if up_pressed else QColor("#4b5563"))
        painter.drawText(draw_up_rect, Qt.AlignmentFlag.AlignCenter, "▲")
        painter.setPen(QColor("#0078d4") if down_pressed else QColor("#4b5563"))
        painter.drawText(draw_down_rect, Qt.AlignmentFlag.AlignCenter, "▼")
        painter.end()


# ================= [优化 1] 引入线程池处理图片下载 =================
class ImageWorkerSignals(QObject):
    """QRunnable 不能直接发信号，需要借助 QObject"""

    finished = Signal(int, QPixmap)
    error = Signal(int)


class ImageDownloadTask(QRunnable):
    """使用 QRunnable 放入线程池，避免瞬间开启几十个 QThread 导致程序崩溃/内存泄漏"""

    def __init__(self, row, image_url):
        super().__init__()
        self.row = row
        self.image_url = image_url
        self.signals = ImageWorkerSignals()

    def run(self):
        try:
            if not self.image_url:
                self.signals.error.emit(self.row)
                return
            response = requests.get(
                self.image_url, timeout=5
            )  # [优化] 缩短超时时间避免死等
            if response.status_code == 200:
                pixmap = QPixmap()
                pixmap.loadFromData(response.content)
                scaled_pixmap = pixmap.scaled(
                    44,
                    44,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.signals.finished.emit(self.row, scaled_pixmap)
            else:
                self.signals.error.emit(self.row)
        except Exception:
            self.signals.error.emit(self.row)


# ================= 采样率检测任务 =================
def find_ffprobe():
    """查找 ffprobe 可执行文件，按优先级搜索多个位置"""
    # PyInstaller 打包后的临时目录
    if getattr(sys, 'frozen', False):
        bundle_dir = sys._MEIPASS
        for name in ["ffprobe", "ffprobe.exe"]:
            path = os.path.join(bundle_dir, name)
            if os.path.isfile(path):
                return path

    # 脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    for name in ["ffprobe", "ffprobe.exe"]:
        path = os.path.join(script_dir, name)
        if os.path.isfile(path):
            return path

    # 脚本同级的 bin 目录
    for name in ["ffprobe", "ffprobe.exe"]:
        path = os.path.join(script_dir, "bin", name)
        if os.path.isfile(path):
            return path

    # 系统 PATH
    import shutil
    path = shutil.which("ffprobe")
    if path:
        return path

    return None


class SampleRateWorkerSignals(QObject):
    finished = Signal(int, str)  # row, 采样率文本
    error = Signal(int)


class SampleRateDetectTask(QRunnable):
    """通过 ffprobe 检测下载 URL 的采样率"""

    def __init__(self, row, download_url):
        super().__init__()
        self.row = row
        self.download_url = download_url
        self.signals = SampleRateWorkerSignals()

    def run(self):
        try:
            ffprobe_path = find_ffprobe()
            if not ffprobe_path:
                self.signals.error.emit(self.row)
                return
            if not self.download_url or not str(self.download_url).startswith("http"):
                self.signals.error.emit(self.row)
                return
            result = subprocess.run(
                [
                    ffprobe_path, "-v", "quiet",
                    "-print_format", "json",
                    "-show_streams", "-select_streams", "a:0",
                    str(self.download_url),
                ],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                self.signals.error.emit(self.row)
                return
            info = json.loads(result.stdout)
            streams = info.get("streams", [])
            if streams:
                sr = streams[0].get("sample_rate", "")
                if sr:
                    sr_khz = int(sr) / 1000
                    self.signals.finished.emit(self.row, f"{sr_khz:.0f} kHz")
                    return
            self.signals.error.emit(self.row)
        except Exception:
            self.signals.error.emit(self.row)


# ================= 后台搜索与下载线程 =================
class SearchThread(QThread):
    finished = Signal(dict)       # 全部完成
    partial = Signal(dict, str)   # 部分完成 (当前结果, 刚完成的源名称)
    error = Signal(str)
    progress = Signal(str)        # 进度消息

    def __init__(self, music_client, keyword, search_type, source_map_en_to_cn=None):
        super().__init__()
        self.music_client = music_client
        self.keyword = keyword
        self.search_type = search_type
        self._cancelled = False
        self._source_map_en_to_cn = source_map_en_to_cn or {}

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            if self.search_type == "搜索歌曲":
                self._search_concurrent()
            else:
                results = self.music_client.parseplaylist(self.keyword)
                if not isinstance(results, dict):
                    results = {"歌单": results}
                self.finished.emit(results)
        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))

    def _search_concurrent(self):
        """并发搜索所有音乐源，支持中途取消"""
        from concurrent.futures import ThreadPoolExecutor
        import threading
        import time
        from datetime import datetime

        all_results = {}
        lock = threading.Lock()
        sources = list(self.music_client.music_clients.keys())
        total = len(sources)
        completed_count = [0]

        # 恢复 musicdl 风格的日志输出，用作信息块分隔
        source_names = "|".join(sources)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        print(f"{ts} - musicdl - INFO - Searching \033[93m{self.keyword}\033[0m From \033[93m{source_names}\033[0m")

        self.progress.emit(f"正在并发搜索 {total} 个音乐源...")

        def search_one_source(source):
            if self._cancelled:
                return source, []
            try:
                result = self.music_client.music_clients[source].search(
                    keyword=self.keyword,
                    num_threadings=self.music_client.clients_threadings.get(source, 1),
                    request_overrides=self.music_client.requests_overrides.get(source, {}),
                    rule=self.music_client.search_rules.get(source, None),
                )
                return source, result or []
            except Exception as e:
                print(f"搜索 {source} 失败: {e}")
                return source, []

        # 一次性提交所有源，轮询检查完成状态
        # 注意：不用 with 语句，因为 __exit__ 会等待所有线程完成
        executor = ThreadPoolExecutor(max_workers=min(total, 10))
        try:
            futures = {
                executor.submit(search_one_source, src): src
                for src in sources
            }
            pending = set(futures.keys())

            while pending and not self._cancelled:
                # 非阻塞轮询：检查哪些 future 已完成
                done = [f for f in pending if f.done()]
                if not done:
                    time.sleep(0.1)  # 没有完成的，短暂等待后继续检查
                    continue

                for future in done:
                    pending.discard(future)
                    source = futures[future]
                    source_cn = self._source_map_en_to_cn.get(source, source)

                    try:
                        source, result = future.result(timeout=0)
                    except Exception as e:
                        print(f"搜索 {source} 异常: {e}")
                        result = []

                    # 日志
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
                    count = len(result) if result else 0
                    print(f"{ts} - musicdl - INFO - {source}.search >>> Completed ({completed_count[0]+1}/{total}) Search URLs, got {count} results")

                    if result:
                        with lock:
                            all_results[source] = result
                            completed_count[0] += 1
                            self.partial.emit(
                                dict(all_results),
                                f"{source_cn} ({completed_count[0]}/{total})",
                            )

            # 取消或正常完成
            self.finished.emit(all_results)
        finally:
            # 不等待，直接关闭
            executor.shutdown(wait=False)


class DownloadThread(QThread):
    finished = Signal(int)
    error = Signal(str)

    def __init__(self, music_client, song_infos, target_dir):
        super().__init__()
        self.music_client = music_client
        self.song_infos = song_infos
        self.target_dir = target_dir

    def _get_val(self, obj, key, default=""):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default) if hasattr(obj, key) else default

    def run(self):
        try:
            downloaded_songs = self.music_client.download(song_infos=self.song_infos)
            success_count = 0

            for song in downloaded_songs:
                save_path = self._get_val(song, "save_path")
                if not save_path or not os.path.exists(save_path):
                    continue

                song_name = self._get_val(song, "song_name", "未知歌曲")
                singers = self._get_val(song, "singers", "未知歌手")
                if isinstance(singers, list):
                    singer = "&".join([str(s) for s in singers])
                else:
                    singer = str(singers)

                album = self._get_val(song, "album", "")
                identifier = self._get_val(song, "identifier", "")

                ext = os.path.splitext(save_path)[1].lstrip(".")
                if not ext:
                    ext = self._get_val(song, "ext", "mp3")

                parts = [song_name, singer]
                if album:
                    parts.append(str(album))
                if identifier:
                    parts.append(str(identifier))

                base_name = sanitize_filename("-".join(parts))
                new_audio_name = f"{base_name}.{ext}"
                new_audio_path = os.path.join(self.target_dir, new_audio_name)

                # [优化 4] 防止同名文件覆盖报错
                try:
                    if os.path.exists(new_audio_path):
                        os.remove(new_audio_path)
                    shutil.move(save_path, new_audio_path)
                    success_count += 1
                except Exception as e:
                    print(f"移动音频文件失败 {save_path}: {e}")

                old_lrc_path = os.path.splitext(save_path)[0] + ".lrc"
                if os.path.exists(old_lrc_path):
                    new_lrc_name = f"{base_name}.lrc"
                    new_lrc_path = os.path.join(self.target_dir, new_lrc_name)
                    try:
                        if os.path.exists(new_lrc_path):
                            os.remove(new_lrc_path)
                        shutil.move(old_lrc_path, new_lrc_path)
                    except Exception as e:
                        print(f"移动歌词文件失败: {e}")

            self.finished.emit(success_count)
        except Exception as e:
            self.error.emit(str(e))


class SimpleProgressDialog(QDialog):
    def __init__(self, title, message, save_dir=None, parent=None, cancellable=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(360)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setStyleSheet("""
            QDialog { background-color: #ffffff; border: 1px solid #d1d5db; border-radius: 10px; }
        """)
        if parent:
            self.move(
                parent.x() + (parent.width() - self.width()) // 2,
                parent.y() + (parent.height() - self.height()) // 2,
            )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self.label = QLabel(message)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("font-size: 11pt; color: #1f2937; font-weight: bold;")
        layout.addWidget(self.label)

        if save_dir:
            dir_label = QLabel(f"保存到：{save_dir}")
            dir_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dir_label.setStyleSheet("font-size: 9pt; color: #6b7280;")
            dir_label.setWordWrap(True)
            layout.addWidget(dir_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setStyleSheet("""
            QProgressBar { border: none; border-radius: 4px; background-color: #f3f4f6; height: 6px; }
            QProgressBar::chunk { background-color: #0078d4; border-radius: 4px; }
        """)
        layout.addWidget(self.progress)

        # 取消按钮
        self.cancel_btn = None
        self._cancelled = False
        if cancellable:
            self.cancel_btn = QPushButton("取消")
            self.cancel_btn.setFixedWidth(80)
            self.cancel_btn.setStyleSheet("""
                QPushButton { background-color: #6b7280; color: white; font-size: 9pt; padding: 4px 12px; }
                QPushButton:hover { background-color: #4b5563; }
            """)
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()
            btn_layout.addWidget(self.cancel_btn)
            btn_layout.addStretch()
            layout.addLayout(btn_layout)

        # 根据内容自适应高度
        self.adjustSize()
        self.setFixedHeight(self.sizeHint().height())

    def set_message(self, text):
        """更新提示文本"""
        self.label.setText(text)

    def set_cancelled(self):
        """标记为已取消"""
        self._cancelled = True
        if self.cancel_btn:
            self.cancel_btn.setEnabled(False)
            self.cancel_btn.setText("已取消")

    def is_cancelled(self):
        return self._cancelled


class FlowLayout(QLayout):
    # (流式布局代码较长，未修改，保持原样)
    def __init__(self, parent=None, margin=-1, hspacing=-1, vspacing=-1):
        super(FlowLayout, self).__init__(parent)
        self._item_list = []
        self._hspacing = hspacing
        self._vspacing = vspacing
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._item_list.append(item)

    def horizontalSpacing(self):
        return (
            self._hspacing
            if self._hspacing >= 0
            else self.smartSpacing(QStyle.PixelMetric.PM_LayoutHorizontalSpacing)
        )

    def verticalSpacing(self):
        return (
            self._vspacing
            if self._vspacing >= 0
            else self.smartSpacing(QStyle.PixelMetric.PM_LayoutVerticalSpacing)
        )

    def count(self):
        return len(self._item_list)

    def itemAt(self, index):
        return self._item_list[index] if 0 <= index < len(self._item_list) else None

    def takeAt(self, index):
        return self._item_list.pop(index) if 0 <= index < len(self._item_list) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.calculateHeight(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super(FlowLayout, self).setGeometry(rect)
        self.calculateHeight(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom()
        )

    def calculateHeight(self, rect, testOnly):
        margins = self.contentsMargins()
        effective = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        x, y = effective.x(), effective.y()
        lineHeight = 0
        for item in self._item_list:
            widget = item.widget()
            spaceX = self.horizontalSpacing()
            if spaceX == -1:
                spaceX = widget.style().layoutSpacing(
                    QSizePolicy.ControlType.PushButton,
                    QSizePolicy.ControlType.PushButton,
                    Qt.Orientation.Horizontal,
                )
            spaceY = self.verticalSpacing()
            if spaceY == -1:
                spaceY = widget.style().layoutSpacing(
                    QSizePolicy.ControlType.PushButton,
                    QSizePolicy.ControlType.PushButton,
                    Qt.Orientation.Vertical,
                )
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > effective.right() and lineHeight > 0:
                x, y = effective.x(), y + lineHeight + spaceY
                nextX, lineHeight = x + item.sizeHint().width() + spaceX, 0
            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x, lineHeight = nextX, max(lineHeight, item.sizeHint().height())
        return y + lineHeight - rect.y() + margins.bottom()

    def smartSpacing(self, pm):
        parent = self.parent()
        if not parent:
            return -1
        if isinstance(parent, QWidget):
            return parent.style().pixelMetric(pm, None, parent)
        elif isinstance(parent, QLayout):
            return parent.spacing()
        return -1


# 主窗口
class MusicDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎵 音乐下载器")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)

        font = QFont("Microsoft YaHei", 10)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        QApplication.setFont(font)
        self.setStyleSheet(self.get_modern_style())

        self.source_map_cn_to_en = {
            "苹果音乐": "AppleMusicClient",
            "Deezer": "DeezerMusicClient",
            "5sing": "FiveSingMusicClient",
            "Jamendo": "JamendoMusicClient",
            "Joox": "JooxMusicClient",
            "酷我音乐": "KuwoMusicClient",
            "酷狗音乐": "KugouMusicClient",
            "咪咕音乐": "MiguMusicClient",
            "网易云音乐": "NeteaseMusicClient",
            "QQ音乐": "QQMusicClient",
            "千千音乐": "QianqianMusicClient",
            "Qobuz": "QobuzMusicClient",
            "SoundCloud": "SoundCloudMusicClient",
            "StreetVoice": "StreetVoiceMusicClient",
            "汽水音乐": "SodaMusicClient",
            "Spotify": "SpotifyMusicClient",
            "TIDAL": "TIDALMusicClient",
        }
        self.source_map_en_to_cn = {v: k for k, v in self.source_map_cn_to_en.items()}

        self.search_results = {}
        self.music_records = {}
        self.music_client = None
        self.current_right_click_row = -1

        # [优化 1] 初始化全局线程池，控制最大并发数防止卡死
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(10)

        self.current_dir = os.getcwd()
        self.settings = QSettings("musicDownload", "MusicDownloader")
        saved = self.settings.value("save_dir", "")
        if saved and os.path.isdir(saved):
            self.save_dir = saved
        else:
            self.save_dir = os.path.join(self.current_dir, "已下载音乐")
        os.makedirs(self.save_dir, exist_ok=True)

        # 加载已保存的音乐源选择
        saved_sources = self.settings.value("selected_sources", "")
        if saved_sources:
            self.saved_sources = [s for s in saved_sources.split(",") if s]
        else:
            self.saved_sources = ["酷我音乐", "酷狗音乐"]

        # 加载已保存的单源获取数量
        self.saved_limit = int(self.settings.value("search_limit", 10))

        self.auto_download_after_search = False

        central = QWidget()
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        self.setup_top(main_layout)
        self.setup_table(main_layout)

        # 初始化 Toast 通知
        self._toast = ToastLabel(self)

        if not MUSICDL_AVAILABLE:
            show_message(self, QMessageBox.Icon.Warning, "警告", "musicdl 库未安装！\n请运行: pip install musicdl")

    def get_modern_style(self):
        # 样式表太长省略部分重复内容，保留核心
        return """
        #CentralWidget { background-color: #f3f4f6; }
        QGroupBox { font-size: 11pt; font-weight: bold; color: #1f2937; background-color: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; margin-top: 12px; padding-top: 14px; padding-bottom: 6px; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #0078d4; }
        QCheckBox { padding: 2px; color: #4b5563; }
        QCheckBox:hover { color: #0078d4; }
        QLineEdit, ModernComboBox, ModernSpinBox { border: 1px solid #d1d5db; border-radius: 6px; padding: 4px 10px; background: #ffffff; min-height: 24px; color: #1f2937; }
        QLineEdit:focus, ModernComboBox:focus, ModernSpinBox:focus { border: 1px solid #0078d4; }
        ModernComboBox::drop-down { width: 24px; border: none; background: transparent; }
        ModernComboBox::down-arrow { image: none; }
        ModernComboBox QAbstractItemView { border: 1px solid #d1d5db; border-radius: 6px; background-color: #ffffff; selection-background-color: #e0f2fe; selection-color: #0369a1; outline: none; padding: 2px; }
        ModernComboBox QAbstractItemView::item { min-height: 28px; border-radius: 4px; padding-left: 6px; }
        ModernSpinBox { padding-right: 22px; }
        ModernSpinBox::up-button, ModernSpinBox::down-button { subcontrol-origin: border; width: 20px; border-left: 1px solid transparent; background: transparent; }
        ModernSpinBox::up-button { subcontrol-position: top right; border-bottom: 1px solid transparent; border-top-right-radius: 5px; }
        ModernSpinBox::down-button { subcontrol-position: bottom right; border-bottom-right-radius: 5px; }
        ModernSpinBox::up-button:hover, ModernSpinBox::down-button:hover { background: #f3f4f6; }
        ModernSpinBox::up-arrow, ModernSpinBox::down-arrow { image: none; }
        QPushButton { border: none; border-radius: 6px; padding: 6px 16px; background-color: #0078d4; color: white; font-weight: bold; font-size: 10pt; }
        QPushButton:hover { background-color: #1089e5; }
        QPushButton:pressed { background-color: #005a9e; }
        QPushButton:disabled { background-color: #9ca3af; color: #f3f4f6; }
        QPushButton#SearchBtn { background-color: #10b981; }
        QPushButton#SearchBtn:hover { background-color: #059669; }
        QTableWidget { border: 1px solid #e5e7eb; border-radius: 8px; background: #ffffff; alternate-background-color: #f9fafb; color: #374151; selection-background-color: #e0f2fe; selection-color: #0369a1; outline: none; }
        QHeaderView::section { background: #f3f4f6; color: #4b5563; font-weight: bold; border: none; border-bottom: 1px solid #e5e7eb; border-right: 1px solid #e5e7eb; padding: 6px 8px; }
        QTableWidget::item { padding: 2px; border-bottom: 1px solid #f3f4f6; }
        QScrollBar:vertical { border: none; background: #f3f4f6; width: 8px; border-radius: 4px; }
        QScrollBar::handle:vertical { background: #d1d5db; min-height: 20px; border-radius: 4px; }
        QScrollBar::handle:vertical:hover { background: #9ca3af; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """

    def setup_top(self, parent_layout):
        layout = QVBoxLayout()
        layout.setSpacing(10)

        group = QGroupBox("选择音乐源")
        flow = FlowLayout()
        self.source_checkboxes = []
        for cn_name in self.source_map_cn_to_en.keys():
            cb = QCheckBox(cn_name)
            if cn_name in self.saved_sources:
                cb.setChecked(True)
            cb.stateChanged.connect(self._on_source_checkbox_changed)
            self.source_checkboxes.append(cb)
            flow.addWidget(cb)
        group.setLayout(flow)
        layout.addWidget(group)

        h1 = QHBoxLayout()
        label_limit = QLabel("单源获取数量：")
        self.spin_limit = ModernSpinBox()
        self.spin_limit.setRange(1, 100)
        self.spin_limit.setValue(self.saved_limit)
        self.spin_limit.setSuffix(" 条")
        self.spin_limit.setFixedWidth(100)
        self.spin_limit.valueChanged.connect(self._on_limit_changed)

        label_save = QLabel("保存目录：")
        self.save_dir_edit = QLineEdit(self.save_dir)
        self.save_dir_edit.setReadOnly(True)
        self.btn_browse = QPushButton("📁 浏览...")
        self.btn_browse.clicked.connect(self.on_browse_save_dir)

        self.check_auto_download = QCheckBox("🚀 搜索后自动下载全部")
        self.check_auto_download.setStyleSheet("font-weight: bold; color: #dc2626;")
        self.check_auto_download.stateChanged.connect(self.on_auto_download_toggle)

        h1.addWidget(label_limit)
        h1.addWidget(self.spin_limit)
        h1.addSpacing(15)
        h1.addWidget(label_save)
        h1.addWidget(self.save_dir_edit, 1)
        h1.addWidget(self.btn_browse)
        h1.addSpacing(15)
        h1.addWidget(self.check_auto_download)
        layout.addLayout(h1)

        h2 = QHBoxLayout()
        self.search_mode = ModernComboBox()
        self.search_mode.addItems(["搜索歌曲", "解析歌单链接"])
        self.search_mode.setFixedWidth(130)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "请输入关键词或输入歌单链接，按回车键也可搜索..."
        )
        self.search_edit.returnPressed.connect(self.on_search)

        self.btn_search = QPushButton("🔍 立即搜索")
        self.btn_search.setObjectName("SearchBtn")
        self.btn_search.setFixedWidth(110)
        self.btn_search.clicked.connect(self.on_search)

        h2.addWidget(self.search_mode)
        h2.addWidget(self.search_edit)
        h2.addWidget(self.btn_search)
        layout.addLayout(h2)
        parent_layout.addLayout(layout)

    def setup_table(self, parent_layout):
        layout = QVBoxLayout()
        layout.setSpacing(10)

        batch = QHBoxLayout()
        scope_label = QLabel("下载范围：")
        self.combo_download_scope = ModernComboBox()
        self.combo_download_scope.addItems(["勾选", "全选", "未勾选"])
        self.combo_download_scope.setFixedWidth(110)

        self.btn_download = QPushButton("⬇️ 下载选中内容")
        self.btn_download.clicked.connect(self.on_download)
        self.btn_download.setEnabled(False)

        batch.addWidget(scope_label)
        batch.addWidget(self.combo_download_scope)
        batch.addStretch()
        batch.addWidget(self.btn_download)
        layout.addLayout(batch)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(10)
        self.results_table.setHorizontalHeaderLabels(
            [
                "选择",
                "专辑封面",
                "歌曲名",
                "歌手",
                "专辑",
                "格式",
                "采样率",
                "大小",
                "时长",
                "来源",
            ]
        )
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setShowGrid(False)
        self.results_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.results_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(
            self.show_table_context_menu
        )

        self.results_table.setColumnWidth(0, 40)
        self.results_table.setColumnWidth(1, 65)
        self.results_table.setColumnWidth(2, 280)
        self.results_table.setColumnWidth(3, 160)
        self.results_table.setColumnWidth(4, 200)
        self.results_table.setColumnWidth(5, 60)
        self.results_table.setColumnWidth(6, 80)
        self.results_table.setColumnWidth(7, 80)
        self.results_table.setColumnWidth(8, 70)
        self.results_table.verticalHeader().setDefaultSectionSize(54)

        self.results_table.setSortingEnabled(True)
        header = self.results_table.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.setSectionsClickable(True)

        layout.addWidget(self.results_table)
        parent_layout.addLayout(layout)

    def on_auto_download_toggle(self, state):
        self.auto_download_after_search = state == Qt.CheckState.Checked

    # 右键菜单等保持原样...
    def show_table_context_menu(self, pos):
        item = self.results_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        self.current_right_click_row = row

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: white; border: 1px solid #e5e7eb; border-radius: 6px; } QMenu::item { padding: 4px 20px; color: #374151; } QMenu::item:selected { background-color: #0078d4; color: white; }"
        )

        song_name_item = self.results_table.item(row, 2)
        singer_item = self.results_table.item(row, 3)
        action_text = (
            f"📥 下载：{song_name_item.text()} - {singer_item.text()}"
            if (song_name_item and singer_item)
            else "📥 下载此歌曲"
        )

        download_action = QAction(action_text, self)
        download_action.triggered.connect(self.download_current_row)
        menu.addAction(download_action)
        menu.addSeparator()

        select_all_action = QAction("☑️ 全选所有歌曲", self)
        select_all_action.triggered.connect(self.select_all_songs)
        menu.addAction(select_all_action)

        deselect_all_action = QAction("🔲 取消全选", self)
        deselect_all_action.triggered.connect(self.deselect_all_songs)
        menu.addAction(deselect_all_action)

        menu.exec(self.results_table.mapToGlobal(pos))

    def download_current_row(self):
        # 获取当前行对应的 checkbox，并从 checkbox 上取得绑定的 song_info，
        # 这样在表格排序后仍可保证下载顺序与可视顺序一致。
        if self.current_right_click_row < 0 or not self.music_client:
            return
        cell_widget = self.results_table.cellWidget(self.current_right_click_row, 0)
        if not cell_widget:
            return
        checkbox = cell_widget.findChild(QCheckBox)
        song_info = getattr(checkbox, "song_info", None) or self.music_records.get(
            str(self.current_right_click_row)
        )
        if not song_info:
            return
        song_name = song_info.get("song_name", "未知歌曲")
        singers = ", ".join(song_info.get("singers", []))

        reply = QMessageBox.question(
            self,
            "确认下载",
            f"确定要下载这首歌曲吗？\n\n🎵 {song_name} - {singers}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._start_download_task([song_info], f"正在处理：{song_name}")

    def select_all_songs(self):
        for row in range(self.results_table.rowCount()):
            cell_widget = self.results_table.cellWidget(row, 0)
            if cell_widget:
                # Use a lowercase variable name 'checkbox'
                checkbox = cell_widget.findChild(QCheckBox)
                if checkbox:
                    checkbox.setChecked(True)

    def deselect_all_songs(self):
        for row in range(self.results_table.rowCount()):
            cell_widget = self.results_table.cellWidget(row, 0)
            if cell_widget:
                # Use a lowercase variable name 'checkbox'
                checkbox = cell_widget.findChild(QCheckBox)
                if checkbox:
                    checkbox.setChecked(False)

    def on_browse_save_dir(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择保存/导出目录", self.current_dir
        )
        if dir_path:
            self.save_dir = dir_path
            self.save_dir_edit.setText(dir_path)
            self.settings.setValue("save_dir", dir_path)

    def _on_source_checkbox_changed(self, state):
        """音乐源选择变化时保存到配置"""
        selected = [
            cb.text() for cb in self.source_checkboxes if cb.isChecked()
        ]
        self.settings.setValue("selected_sources", ",".join(selected))

    def _on_limit_changed(self, value):
        """单源获取数量变化时保存到配置"""
        self.settings.setValue("search_limit", value)

    def init_music_client(self):
        if not MUSICDL_AVAILABLE:
            return None
        os.makedirs(self.save_dir, exist_ok=True)
        temp_work_dir = os.path.join(self.current_dir, ".musicdl_temp")
        os.makedirs(temp_work_dir, exist_ok=True)

        src_names = self.get_selected_sources()
        if not src_names:
            show_message(self, QMessageBox.Icon.Warning, "提示", "请至少选择一个音乐来源！")
            return None

        cfg = {
            src: {
                "search_size_per_source": self.spin_limit.value(),
                "work_dir": temp_work_dir,
            }
            for src in src_names
        }
        try:
            if musicdl:
                return musicdl.MusicClient(
                    music_sources=src_names, init_music_clients_cfg=cfg
                )
            return None
        except Exception as e:
            show_message(self, QMessageBox.Icon.Critical, "错误", f"初始化 musicdl 客户端失败：{str(e)}")
            return None

    def get_selected_sources(self):
        return [
            self.source_map_cn_to_en[cb.text()]
            for cb in self.source_checkboxes
            if cb.isChecked()
        ]

    def get_file_format(self, song_info):
        for field in ["format", "ext", "file_format", "type"]:
            if song_info.get(field):
                return str(song_info[field]).upper()
        url = song_info.get("download_url", "").lower()
        for ext in ["mp3", "flac", "wav", "m4a", "aac"]:
            if f".{ext}" in url:
                return ext.upper()
        return "未知"

    def get_album_image_url(self, song_info):
        for field in [
            "cover",
            "album_cover",
            "pic",
            "picture",
            "img",
            "image",
            "album_img",
            "album_pic",
            "cover_url",
            "pic_url",
        ]:
            url = str(song_info.get(field, ""))
            if url.startswith("http"):
                return url
        return ""

    def load_table_with_results(self, search_results):
        self.results_table.setSortingEnabled(False)
        self.results_table.setRowCount(0)
        self.search_results = search_results
        self.music_records = {}

        # [优化 2] 清理线程池排队任务（如果有旧的未完成的搜索任务图）
        self.thread_pool.clear()

        all_songs = []
        for per_source in search_results.values():
            all_songs.extend(per_source)

        self.results_table.setRowCount(len(all_songs))
        row = 0
        for _, per_source_search_results in search_results.items():
            for per_source_search_result in per_source_search_results:
                # Checkbox
                w = QWidget()
                lay = QHBoxLayout(w)
                checkbox = QCheckBox()
                # attach song_info to checkbox so it stays with the widget when the table is sorted
                checkbox.song_info = per_source_search_result
                lay.addWidget(checkbox)
                lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lay.setContentsMargins(0, 0, 0, 0)
                self.results_table.setCellWidget(row, 0, w)

                song_name = per_source_search_result.get("song_name", "")
                singers = per_source_search_result.get("singers", "")
                album = per_source_search_result.get("album", "")
                source_cn = self.source_map_en_to_cn.get(
                    per_source_search_result.get("source", ""), ""
                )

                columns_data = [
                    (2, str(song_name)),
                    (3, str(singers)),
                    (4, str(album)),
                    (5, self.get_file_format(per_source_search_result)),
                    (6, "检测中..."),  # 采样率，异步检测后填充
                    (7, str(per_source_search_result.get("file_size", ""))),
                    (8, str(per_source_search_result.get("duration", ""))),
                    (9, str(source_cn)),
                ]

                for column, text in columns_data:
                    if column in (7, 8):
                        table_item = NumericTableItem(text)
                        table_item.setData(
                            Qt.ItemDataRole.UserRole,
                            extract_numeric_value(text),
                        )
                    else:
                        table_item = QTableWidgetItem(text)
                    align = (
                        Qt.AlignmentFlag.AlignLeft
                        if column in [2, 3, 4]
                        else Qt.AlignmentFlag.AlignHCenter
                    )
                    table_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | align)
                    self.results_table.setItem(row, column, table_item)

                self.music_records[str(row)] = per_source_search_result

                # 提交采样率检测任务
                download_url = per_source_search_result.get("download_url", "")
                if download_url:
                    task = SampleRateDetectTask(row, download_url)
                    task.signals.finished.connect(self.on_samplerate_detected)
                    task.signals.error.connect(self.on_samplerate_error)
                    self.thread_pool.start(task)

                # [优化 1] 将图片下载投递到线程池，而不是直接 new QThread
                album_image_url = self.get_album_image_url(per_source_search_result)
                if album_image_url:
                    task = ImageDownloadTask(row, album_image_url)
                    task.signals.finished.connect(self.on_image_downloaded)
                    task.signals.error.connect(self.on_image_error)
                    self.thread_pool.start(task)
                else:
                    self.on_image_error(row)

                row += 1

        self.btn_download.setEnabled(row > 0)
        self.results_table.setSortingEnabled(True)

        if self.auto_download_after_search and all_songs:
            self._start_download_task(all_songs, f"正在处理 {len(all_songs)} 首歌曲")
        else:
            show_message(self, QMessageBox.Icon.Information, "搜索完毕", f"🎉 搜索完成！共找到 {row} 首歌曲。\n(专辑封面正在后台加载...)")

    def _start_download_task(self, songs_list, msg):
        """[优化] 提取出公共的下载弹窗逻辑"""
        dlg = SimpleProgressDialog("下载提取中", msg, self.save_dir, self)
        dlg.show()

        self.download_thread = DownloadThread(
            self.music_client, songs_list, self.save_dir
        )

        def on_finished(success_count):
            dlg.accept()
            show_message(self, QMessageBox.Icon.Information, "下载完成", f"✅ 成功提取 {success_count} 首歌曲！\n已保存在：{self.save_dir}")

        def on_error(error_msg):
            dlg.accept()
            show_message(self, QMessageBox.Icon.Critical, "错误", f"❌ 下载失败：{error_msg}")

        self.download_thread.finished.connect(on_finished)
        self.download_thread.error.connect(on_error)
        self.download_thread.start()

    def on_image_downloaded(self, row, pixmap):
        try:
            label = QLabel()
            label.setPixmap(pixmap)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("border-radius: 3px;")
            self.results_table.setCellWidget(row, 1, label)
        except Exception as e:
            print(f"设置专辑封面失败: {e}")

    def on_image_error(self, row):
        try:
            label = QLabel("🎵")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-size: 20px; color: #d1d5db;")
            self.results_table.setCellWidget(row, 1, label)
        except Exception as e:
            print(f"设置专辑封面失败: {e}")

    def on_samplerate_detected(self, row, sr_text):
        try:
            item = QTableWidgetItem(sr_text)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
            )
            self.results_table.setItem(row, 6, item)
        except Exception as e:
            print(f"设置采样率失败: {e}")

    def on_samplerate_error(self, row):
        try:
            item = QTableWidgetItem("-")
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
            )
            self.results_table.setItem(row, 6, item)
        except Exception as e:
            print(f"设置采样率失败: {e}")

    def get_songs_by_download_scope(self):
        scope = self.combo_download_scope.currentText()
        songs = []
        for row in range(self.results_table.rowCount()):
            cell_widget = self.results_table.cellWidget(row, 0)
            if not cell_widget:
                continue
            checkbox = cell_widget.findChild(QCheckBox)
            is_checked = checkbox.isChecked() if checkbox else False
            if (
                scope == "全选"
                or (scope == "勾选" and is_checked)
                or (scope == "未勾选" and not is_checked)
            ):
                # 首先尝试从 checkbox 获取绑定的 song_info（此对象随行排序移动），
                # 否则退回到旧的 music_records 映射以保持兼容性。
                song_info = getattr(checkbox, "song_info", None)
                if not song_info and str(row) in self.music_records:
                    song_info = self.music_records[str(row)]
                if song_info:
                    songs.append(song_info)
        return songs

    def on_search(self):
        keyword = self.search_edit.text().strip()
        if not keyword:
            show_message(self, QMessageBox.Icon.Warning, "提示", "请输入你要搜索的关键词！")
            return

        self.music_client = self.init_music_client()
        if not self.music_client:
            return

        # [优化 3] 搜索时禁用按钮防止重复点击引发异常
        self.btn_search.setEnabled(False)
        self.btn_search.setText("搜索中...")

        dlg = SimpleProgressDialog(
            "🔍 搜索中", "正在全网搜罗音乐，请稍候...", None, self,
            cancellable=True,
        )
        dlg.show()

        self.search_thread = SearchThread(
            self.music_client, keyword, self.search_mode.currentText(),
            source_map_en_to_cn=self.source_map_en_to_cn,
        )

        def on_cancel():
            dlg.set_cancelled()
            dlg.set_message("正在取消搜索...")
            self.search_thread.cancel()

        dlg.cancel_btn.clicked.connect(on_cancel)

        def on_progress(msg):
            if not dlg.is_cancelled():
                dlg.set_message(msg)

        def on_partial(results, source_name):
            """部分搜索完成，实时更新表格"""
            if not dlg.is_cancelled():
                source_cn = self.source_map_en_to_cn.get(source_name, source_name)
                dlg.set_message(f"已完成 {source_cn}，继续搜索中...")

        def on_finished(results):
            dlg.accept()
            self.btn_search.setEnabled(True)
            self.btn_search.setText("🔍 立即搜索")
            if results:
                self.load_table_with_results(results)

        def on_error(error_msg):
            dlg.accept()
            self.btn_search.setEnabled(True)
            self.btn_search.setText("🔍 立即搜索")
            show_message(self, QMessageBox.Icon.Critical, "错误", f"搜索失败：{error_msg}")

        self.search_thread.progress.connect(on_progress)
        self.search_thread.partial.connect(on_partial)
        self.search_thread.finished.connect(on_finished)
        self.search_thread.error.connect(on_error)
        self.search_thread.start()

    def on_download(self):
        if not self.music_client:
            return
        songs_to_download = self.get_songs_by_download_scope()
        if not songs_to_download:
            show_message(self, QMessageBox.Icon.Warning, "提示", "没有符合条件的歌曲，请检查是否已勾选！")
            return

        reply = QMessageBox.question(
            self,
            "确认下载",
            f"确定要下载选中的 {len(songs_to_download)} 首歌曲吗？\n保存目录：{self.save_dir}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._start_download_task(
                songs_to_download, f"正在批量下载 {len(songs_to_download)} 首歌曲..."
            )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MusicDownloader()
    win.show()
    sys.exit(app.exec())