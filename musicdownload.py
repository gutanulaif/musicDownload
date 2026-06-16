import sys
import os

# 抑制 FFmpeg/GStreamer 解码警告（需在 QApplication 创建前设置）
os.environ["QT_LOGGING_RULES"] = "qt.multimedia.ffmpeg=false;qt.multimedia.gstreamer=false"
os.environ["GST_DEBUG"] = "0"
os.environ["FF_LOG_LEVEL"] = "quiet"

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
    QSlider,
    QGraphicsDropShadowEffect,
    QGridLayout,
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
    QUrl,
    QTimer,
)
from PySide6.QtGui import QPixmap, QFont, QColor, QPainter, QAction, QIcon
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

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
                creationflags=subprocess.CREATE_NO_WINDOW,
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

    def maximumSize(self):
        """重写最大尺寸：高度由宽度决定，防止被外部 Maximum 策略拉伸"""
        _MAX = (1 << 24) - 1  # Qt QWIDGETSIZE_MAX
        return QSize(_MAX, self.heightForWidth(_MAX) if self.count() > 0 else _MAX)

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


class ModernDialog(QDialog):
    """现代风格弹窗：圆角 + 阴影 + 统一按钮"""

    def __init__(self, parent=None, title="", message="", icon="question",
                 buttons=("取消", "确定"), default=1):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self._result = -1
        self._buttons = []
        self._init_ui(title, message, icon, buttons, default)

    def _init_ui(self, title, message, icon, buttons, default):
        # 外层容器（绘制背景 + 圆角）
        self._container = QWidget(self)
        self._container.setObjectName("DialogContainer")
        self._container.setStyleSheet("""
            #DialogContainer {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._container)

        layout = QVBoxLayout(self._container)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 16)

        # 图标 + 标题
        icon_map = {"question": "❓", "warning": "⚠️", "error": "❌", "info": "ℹ️", "success": "✅"}
        icon_text = icon_map.get(icon, "❓")

        if title:
            title_row = QHBoxLayout()
            title_row.setSpacing(8)
            icon_lbl = QLabel(icon_text)
            icon_lbl.setStyleSheet("font-size: 16pt; background: transparent; border: none;")
            title_row.addWidget(icon_lbl)
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet("color: #0f172a; font-size: 12pt; font-weight: bold; background: transparent; border: none;")
            title_row.addWidget(title_lbl)
            title_row.addStretch()
            layout.addLayout(title_row)

        # 消息内容
        msg_lbl = QLabel(message)
        msg_lbl.setStyleSheet("color: #475569; font-size: 10pt; background: transparent; border: none;")
        msg_lbl.setWordWrap(True)
        layout.addWidget(msg_lbl)

        # 按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        for i, text in enumerate(buttons):
            btn = QPushButton(text)
            btn.setFixedHeight(34)
            btn.setMinimumWidth(80)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if i == default:
                btn.setObjectName("PrimaryBtn")
                btn.setStyleSheet("""
                    QPushButton#PrimaryBtn {
                        background-color: #14b8a6; color: white;
                        border: none; border-radius: 8px;
                        font-weight: bold; font-size: 10pt;
                        padding: 0 20px;
                    }
                    QPushButton#PrimaryBtn:hover { background-color: #2dd4bf; }
                    QPushButton#PrimaryBtn:pressed { background-color: #0d9488; }
                """)
            else:
                btn.setObjectName("SecondaryBtn")
                btn.setStyleSheet("""
                    QPushButton#SecondaryBtn {
                        background-color: #f1f5f9; color: #475569;
                        border: 1px solid #e2e8f0; border-radius: 8px;
                        font-size: 10pt; padding: 0 20px;
                    }
                    QPushButton#SecondaryBtn:hover { background-color: #e2e8f0; }
                    QPushButton#SecondaryBtn:pressed { background-color: #cbd5e1; }
                """)
            btn.clicked.connect(lambda checked, idx=i: self._on_button(idx))
            self._buttons.append(btn)
            btn_layout.addWidget(btn)

        layout.addLayout(btn_layout)

        # 阴影
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 40))
        self._container.setGraphicsEffect(shadow)

    def _on_button(self, index):
        self._result = index
        self.accept()

    def result(self):
        return self._result

    # 支持拖动移动
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if hasattr(self, '_drag_pos') and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    @staticmethod
    def question(parent, title, message, buttons=("取消", "确定"), default=1):
        """便捷方法：返回按钮索引"""
        dlg = ModernDialog(parent, title, message, "question", buttons, default)
        dlg.exec()
        return dlg.result()

    @staticmethod
    def warning(parent, title, message, buttons=("确定",), default=0):
        dlg = ModernDialog(parent, title, message, "warning", buttons, default)
        dlg.exec()
        return dlg.result()

    @staticmethod
    def information(parent, title, message, buttons=("确定",), default=0):
        dlg = ModernDialog(parent, title, message, "info", buttons, default)
        dlg.exec()
        return dlg.result()


class AudioPlayerWidget(QWidget):
    """底部在线播放器控件"""

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self._slider_pressed = False
        self._current_title = ""
        self._settings = settings
        # 防止播放器在垂直方向扩展
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(56)
        self._init_ui()
        self._init_player()
        self._apply_style()

    def _init_ui(self):
        # 外层容器强制深色背景，防止父窗口样式穿透
        self._container = QWidget(self)
        self._container.setObjectName("PlayerContainer")
        self._container.setAutoFillBackground(True)
        self._container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cpal = self._container.palette()
        cpal.setColor(self._container.backgroundRole(), QColor("#e2e8f0"))
        self._container.setPalette(cpal)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._container)

        layout = QHBoxLayout(self._container)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # 歌曲信息
        self.title_label = QLabel("未播放")
        self.title_label.setStyleSheet("color: #0f172a; font-size: 11pt; font-weight: bold;")
        self.title_label.setMinimumWidth(120)
        self.title_label.setMaximumWidth(250)
        self.title_label.setWordWrap(False)
        layout.addWidget(self.title_label)

        # 播放控制按钮
        self.prev_btn = self._make_btn(QStyle.StandardPixmap.SP_MediaSkipBackward, "上一首")
        self.play_btn = self._make_btn(QStyle.StandardPixmap.SP_MediaPlay, "播放/暂停")
        self.play_btn.setFixedSize(40, 40)
        self.stop_btn = self._make_btn(QStyle.StandardPixmap.SP_MediaStop, "停止")

        self.prev_btn.clicked.connect(self._on_prev)
        self.play_btn.clicked.connect(self._on_play_pause)
        self.stop_btn.clicked.connect(self._on_stop)

        for btn in (self.prev_btn, self.play_btn, self.stop_btn):
            layout.addWidget(btn)

        # 进度条区域
        self.time_current = QLabel("00:00")
        self.time_current.setStyleSheet("color: #64748b; font-size: 10pt; font-weight: bold;")
        self.time_current.setFixedWidth(50)

        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderPressed.connect(self._on_slider_pressed)
        self.position_slider.sliderReleased.connect(self._on_slider_released)
        self.position_slider.sliderMoved.connect(self._on_seek)

        self.time_total = QLabel("00:00")
        self.time_total.setStyleSheet("color: #64748b; font-size: 10pt; font-weight: bold;")
        self.time_total.setFixedWidth(50)

        layout.addWidget(self.time_current)
        layout.addWidget(self.position_slider, 1)
        layout.addWidget(self.time_total)

        # 音量控制
        self.mute_btn = self._make_btn(QStyle.StandardPixmap.SP_MediaVolume, "静音切换")
        self.mute_btn.setFixedSize(34, 34)
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        # 加载保存的音量，默认70
        saved_volume = int(self._settings.value("volume", 70)) if self._settings else 70
        self.volume_slider.setValue(saved_volume)
        self.volume_slider.setFixedWidth(90)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.mute_btn.clicked.connect(self._on_mute_toggle)

        layout.addWidget(self.mute_btn)
        layout.addWidget(self.volume_slider)

    def _make_btn(self, icon, tooltip=""):
        btn = QPushButton()
        btn.setIcon(self._colorize_icon(self.style().standardIcon(icon)))
        btn.setFixedSize(34, 34)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setIconSize(QSize(20, 20))
        btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #3a3a5a; }
            QPushButton:pressed { background-color: #4a4a6a; }
        """)
        return btn

    @staticmethod
    def _colorize_icon(std_icon, color="#475569", size=20):
        """将标准图标重新着色为指定颜色"""
        pixmap = std_icon.pixmap(QSize(size, size))
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(color))
        painter.end()
        return QIcon(pixmap)

    def _apply_style(self):
        self._container.setStyleSheet("""
            #PlayerContainer {
                background-color: #e2e8f0;
                border-top: 3px solid #94a3b8;
            }
            #PlayerContainer QLabel {
                color: #334155;
                background: transparent;
                border: none;
            }
            #PlayerContainer QPushButton {
                background-color: transparent;
                color: #475569;
                border: none;
                border-radius: 4px;
                padding: 4px;
            }
            #PlayerContainer QPushButton:hover {
                background-color: #cbd5e1;
            }
            #PlayerContainer QPushButton:pressed {
                background-color: #94a3b8;
            }
            #PlayerContainer QSlider::groove:horizontal {
                height: 4px;
                background: #cbd5e1;
                border-radius: 2px;
            }
            #PlayerContainer QSlider::handle:horizontal {
                background: #14b8a6;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            #PlayerContainer QSlider::handle:horizontal:hover {
                background: #2dd4bf;
            }
            #PlayerContainer QSlider::sub-page:horizontal {
                background: #14b8a6;
                border-radius: 2px;
            }
        """)

    def _init_player(self):
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        # 使用滑块的初始值设置音量
        self.audio_output.setVolume(self.volume_slider.value() / 100.0)

        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_state_changed)
        self.player.errorOccurred.connect(self._on_error)

    def play_url(self, url, title=""):
        """加载并播放指定 URL"""
        self._current_title = title
        if title:
            self.title_label.setText(title)
            self.title_label.setToolTip(title)
        self.player.setSource(QUrl(url))
        self.player.play()

    def _on_play_pause(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_stop(self):
        self.player.stop()

    def _on_prev(self):
        self.player.setPosition(0)

    def _on_slider_pressed(self):
        self._slider_pressed = True

    def _on_slider_released(self):
        self._slider_pressed = False

    def _on_seek(self, position):
        self.player.setPosition(position)

    def _on_position_changed(self, position):
        if not self._slider_pressed:
            self.position_slider.setValue(position)
        self.time_current.setText(self._fmt_time(position))

    def _on_duration_changed(self, duration):
        self.position_slider.setRange(0, duration)
        self.time_total.setText(self._fmt_time(duration))

    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlayingState:
            self.play_btn.setIcon(self._colorize_icon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause)))
            self.play_btn.setToolTip("暂停")
        else:
            self.play_btn.setIcon(self._colorize_icon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)))
            self.play_btn.setToolTip("播放")

    def _on_error(self, error, msg):
        # 只显示严重错误，忽略非致命的解码警告
        if error != QMediaPlayer.Error.NoError:
            self.play_btn.setIcon(self._colorize_icon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)))

    def _on_volume_changed(self, value):
        self.audio_output.setVolume(value / 100.0)
        # 保存音量设置
        if self._settings:
            self._settings.setValue("volume", value)

    def _on_mute_toggle(self):
        muted = self.audio_output.isMuted()
        self.audio_output.setMuted(not muted)

    @staticmethod
    def _fmt_time(ms):
        s = int(ms / 1000)
        return f"{s // 60:02d}:{s % 60:02d}"


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

        self.source_groups = {
            "国内源": [
                ("酷我音乐", "KuwoMusicClient"),
                ("酷狗音乐", "KugouMusicClient"),
                ("咪咕音乐", "MiguMusicClient"),
                ("网易云音乐", "NeteaseMusicClient"),
                ("QQ音乐", "QQMusicClient"),
                ("千千音乐", "QianqianMusicClient"),
                ("汽水音乐", "SodaMusicClient"),
            ],
            "海外源": [
                ("苹果音乐", "AppleMusicClient"),
                ("Deezer", "DeezerMusicClient"),
                ("5sing", "FiveSingMusicClient"),
                ("Jamendo", "JamendoMusicClient"),
                ("Joox", "JooxMusicClient"),
                ("Qobuz", "QobuzMusicClient"),
                ("SoundCloud", "SoundCloudMusicClient"),
                ("StreetVoice", "StreetVoiceMusicClient"),
                ("Spotify", "SpotifyMusicClient"),
                ("TIDAL", "TIDALMusicClient"),
            ],
        }
        self.source_map_cn_to_en = {}
        for group_sources in self.source_groups.values():
            for cn_name, en_name in group_sources:
                self.source_map_cn_to_en[cn_name] = en_name
        self.source_map_en_to_cn = {v: k for k, v in self.source_map_cn_to_en.items()}

        self.search_results = {}
        self.music_records = {}
        self.music_client = None
        self.current_right_click_row = -1

        # [优化 1] 初始化全局线程池，控制最大并发数防止卡死
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(10)

        self.current_dir = os.getcwd()
        # 使用 INI 文件存储设置，便于便携部署
        settings_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "settings.ini")
        self.settings = QSettings(settings_path, QSettings.Format.IniFormat)
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
            self.saved_sources = ["酷我音乐"]

        # 加载已保存的单源获取数量
        self.saved_limit = int(self.settings.value("search_limit", 3))

        central = QWidget()
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        self.setup_top(main_layout)
        self.setup_table(main_layout)

        # 底部播放器
        self.audio_player = AudioPlayerWidget(self, self.settings)
        main_layout.addWidget(self.audio_player)

        # 初始化 Toast 通知
        self._toast = ToastLabel(self)

        if not MUSICDL_AVAILABLE:
            show_message(self, QMessageBox.Icon.Warning, "警告", "musicdl 库未安装！\n请运行: pip install musicdl")

    def get_modern_style(self):
        return """
        /* ===== 基础 ===== */
        #CentralWidget { background-color: #f1f5f9; }

        /* ===== 分组卡片（用 #SourceCard 替代）===== */

        /* ===== 复选框 ===== */
        QCheckBox {
            spacing: 6px;
            color: #475569;
            font-size: 10pt;
        }
        QCheckBox:hover { color: #14b8a6; }
        QCheckBox::indicator {
            width: 16px; height: 16px;
            border: 2px solid #cbd5e1;
            border-radius: 4px;
            background: #ffffff;
        }
        QCheckBox::indicator:hover {
            border-color: #14b8a6;
        }
        QCheckBox::indicator:checked {
            background-color: #14b8a6;
            border-color: #14b8a6;
        }

        /* ===== 输入框 / 微调框 ===== */
        QLineEdit, ModernSpinBox {
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 5px 12px;
            background: #ffffff;
            min-height: 24px;
            color: #0f172a;
            font-size: 10pt;
        }
        QLineEdit:focus, ModernSpinBox:focus {
            border: 2px solid #14b8a6;
            padding: 4px 11px;
        }
        ModernSpinBox { padding-right: 24px; }
        ModernSpinBox::up-button, ModernSpinBox::down-button {
            subcontrol-origin: border; width: 22px;
            border-left: 1px solid transparent; background: transparent;
        }
        ModernSpinBox::up-button {
            subcontrol-position: top right; border-bottom: 1px solid transparent;
            border-top-right-radius: 7px;
        }
        ModernSpinBox::down-button {
            subcontrol-position: bottom right; border-bottom-right-radius: 7px;
        }
        ModernSpinBox::up-button:hover, ModernSpinBox::down-button:hover {
            background: #f1f5f9;
        }
        ModernSpinBox::up-arrow, ModernSpinBox::down-arrow { image: none; }

        /* ===== 按钮 ===== */
        QPushButton {
            border: none; border-radius: 8px;
            padding: 7px 18px;
            background-color: #14b8a6;
            color: white;
            font-weight: bold; font-size: 10pt;
        }
        QPushButton:hover { background-color: #2dd4bf; }
        QPushButton:pressed { background-color: #0d9488; }
        QPushButton:disabled { background-color: #cbd5e1; color: #f1f5f9; }

        /* ===== 表格 ===== */
        QTableWidget {
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            background: #ffffff;
            alternate-background-color: #f8fafc;
            color: #334155;
            outline: none;
            font-size: 10pt;
        }
        QHeaderView::section {
            background: #f1f5f9;
            color: #475569;
            font-weight: bold; font-size: 10pt;
            border: none;
            border-bottom: 2px solid #e2e8f0;
            border-right: 1px solid #e2e8f0;
            padding: 8px 10px;
        }
        QTableWidget::item { padding: 3px; border-bottom: 1px solid #f1f5f9; }
        QTableWidget::item:selected { background-color: #ccfbf1; color: #0f172a; }

        /* ===== 滚动条 ===== */
        QScrollBar:vertical {
            border: none; background: #f1f5f9;
            width: 8px; border-radius: 4px; margin: 2px;
        }
        QScrollBar::handle:vertical {
            background: #cbd5e1; min-height: 24px; border-radius: 4px;
        }
        QScrollBar::handle:vertical:hover { background: #94a3b8; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """

    def setup_top(self, main_layout):
        # === 音乐源卡片（直接 addWidget 到 main_layout，消除中间 QLayoutItem）===
        card = QWidget()
        card.setObjectName("SourceCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        card.setStyleSheet("""
            #SourceCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(2)
        card_layout.setContentsMargins(12, 6, 12, 4)

        # 标题
        title = QLabel("选择音乐源")
        title.setStyleSheet("color: #14b8a6; font-size: 11pt; font-weight: bold; border: none; background: transparent;")
        card_layout.addWidget(title)

        # 收集所有源
        all_sources = []
        for sources in self.source_groups.values():
            all_sources.extend(sources)

        # FlowLayout 自动换行，统一最小宽度保证列对齐
        flow = FlowLayout()
        flow.setSpacing(8)
        flow.setContentsMargins(0, 0, 0, 0)
        self.source_checkboxes = []
        for cn_name, en_name in all_sources:
            cb = QCheckBox(cn_name)
            cb.setMinimumWidth(140)  # 统一最小宽度，保证列对齐
            if cn_name in self.saved_sources:
                cb.setChecked(True)
            cb.stateChanged.connect(self._on_source_checkbox_changed)
            self.source_checkboxes.append(cb)
            flow.addWidget(cb)

        # 用 wrapper widget 包裹 FlowLayout，让它传播 heightForWidth
        flow_widget = QWidget()
        flow_widget.setLayout(flow)
        flow_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        card_layout.addWidget(flow_widget)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setXOffset(0)
        shadow.setYOffset(1)
        shadow.setColor(QColor(0, 0, 0, 20))
        card.setGraphicsEffect(shadow)
        main_layout.addWidget(card)

        # === 单源获取数量 + 保存目录 ===
        h1_widget = QWidget()
        h1_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        h1 = QHBoxLayout(h1_widget)
        h1.setContentsMargins(0, 0, 0, 0)
        h1.setSpacing(0)
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
        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.clicked.connect(self.on_browse_save_dir)

        h1.addWidget(label_limit)
        h1.addWidget(self.spin_limit)
        h1.addSpacing(15)
        h1.addWidget(label_save)
        h1.addWidget(self.save_dir_edit, 1)
        h1.addWidget(self.btn_browse)
        main_layout.addWidget(h1_widget)

        # === 搜索输入 ===
        h2_widget = QWidget()
        h2_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        h2 = QHBoxLayout(h2_widget)
        h2.setContentsMargins(0, 0, 0, 0)
        h2.setSpacing(8)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "请输入关键词或输入歌单链接，按回车键也可搜索..."
        )
        self.search_edit.returnPressed.connect(self.on_search)

        self.btn_search = QPushButton("立即搜索")
        self.btn_search.setFixedWidth(110)
        self.btn_search.clicked.connect(self.on_search)

        h2.addWidget(self.search_edit, 1)
        h2.addWidget(self.btn_search)
        main_layout.addWidget(h2_widget)

    def setup_table(self, parent_layout):
        # 空状态提示
        self.empty_label = QLabel("输入关键词，点击搜索")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("""
            color: #94a3b8; font-size: 12pt; padding: 60px 0;
            background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px;
        """)
        parent_layout.addWidget(self.empty_label, 1)  # stretch=1，占剩余空间

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
        self.results_table.doubleClicked.connect(self.on_play_row)

        self.results_table.setSortingEnabled(True)
        header = self.results_table.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.setSectionsClickable(True)

        # 表格阴影
        table_shadow = QGraphicsDropShadowEffect()
        table_shadow.setBlurRadius(16)
        table_shadow.setXOffset(0)
        table_shadow.setYOffset(2)
        table_shadow.setColor(QColor(0, 0, 0, 25))
        self.results_table.setGraphicsEffect(table_shadow)

        # 初始状态：隐藏表格，显示空状态
        self.results_table.hide()
        parent_layout.addWidget(self.results_table, 1)  # stretch=1，占剩余空间

    def show_table_context_menu(self, pos):
        item = self.results_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        self.current_right_click_row = row

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 4px; }
            QMenu::item { padding: 6px 20px; color: #334155; border-radius: 4px; }
            QMenu::item:selected { background-color: #ccfbf1; color: #0f172a; }
            QMenu::separator { height: 1px; background: #e2e8f0; margin: 4px 8px; }
        """)

        # 单曲下载
        song_name_item = self.results_table.item(row, 2)
        singer_item = self.results_table.item(row, 3)
        action_text = (
            f"下载：{song_name_item.text()} - {singer_item.text()}"
            if (song_name_item and singer_item)
            else "下载此歌曲"
        )
        download_action = QAction(action_text, self)
        download_action.triggered.connect(self.download_current_row)
        menu.addAction(download_action)

        # 批量下载
        download_checked_action = QAction("下载勾选的歌曲", self)
        download_checked_action.triggered.connect(lambda: self._download_by_scope("勾选"))
        menu.addAction(download_checked_action)

        download_all_action = QAction("下载全部歌曲", self)
        download_all_action.triggered.connect(lambda: self._download_by_scope("全选"))
        menu.addAction(download_all_action)

        menu.addSeparator()

        # 全选/取消全选
        select_all_action = QAction("全选所有歌曲", self)
        select_all_action.triggered.connect(self.select_all_songs)
        menu.addAction(select_all_action)

        deselect_all_action = QAction("取消全选", self)
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
        singers = song_info.get("singers", "未知歌手")
        if isinstance(singers, list):
            singers = ", ".join(singers)

        # dlg = QMessageBox(self)
        # dlg.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        # dlg.setIcon(QMessageBox.Icon.Question)
        # dlg.setText(f"确定要下载这首歌曲吗？\n\n🎵 {song_name} - {singers}")
        # dlg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        # dlg.setDefaultButton(QMessageBox.StandardButton.No)
        # if dlg.exec() != QMessageBox.StandardButton.Yes:
        #     return
        if ModernDialog.question(self, "确认下载",
                f"确定要下载这首歌曲吗？\n\n🎵 {song_name} - {singers}") != 1:
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

    def _download_by_scope(self, scope):
        """按范围下载：'勾选' 或 '全选'"""
        songs = []
        for row in range(self.results_table.rowCount()):
            cell_widget = self.results_table.cellWidget(row, 0)
            if not cell_widget:
                continue
            checkbox = cell_widget.findChild(QCheckBox)
            is_checked = checkbox.isChecked() if checkbox else False
            if scope == "全选" or (scope == "勾选" and is_checked):
                song_info = getattr(checkbox, "song_info", None) if checkbox else None
                if not song_info and str(row) in self.music_records:
                    song_info = self.music_records[str(row)]
                if song_info:
                    songs.append(song_info)

        if not songs:
            show_message(self, QMessageBox.Icon.Warning, "提示", "没有符合条件的歌曲，请检查是否已勾选！")
            return

        if ModernDialog.question(self, "确认下载",
                f"确定要下载 {len(songs)} 首歌曲吗？\n保存目录：{self.save_dir}") == 1:
            self._start_download_task(songs, f"正在批量下载 {len(songs)} 首歌曲...")

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

    def on_play_row(self, index):
        """双击表格行播放歌曲"""
        row = index.row()
        cell_widget = self.results_table.cellWidget(row, 0)
        if not cell_widget:
            return
        checkbox = cell_widget.findChild(QCheckBox)
        if not checkbox or not hasattr(checkbox, "song_info"):
            return
        song_info = checkbox.song_info
        play_url = song_info.get("download_url", "")
        if not play_url:
            show_message(self, QMessageBox.Icon.Warning, "提示", "该歌曲无法在线试听")
            return
        song_name = song_info.get("song_name", "未知歌曲")
        artist = song_info.get("singers", "未知歌手")
        self.audio_player.play_url(play_url, f"{song_name} - {artist}")

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
        self.empty_label.hide()
        self.results_table.show()

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
                w.setStyleSheet("background: transparent;")
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

        self.results_table.setSortingEnabled(True)
        show_message(self, QMessageBox.Icon.Information, "搜索完毕", f"搜索完成！共找到 {row} 首歌曲。\n(专辑封面正在后台加载...)")

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
            label.setStyleSheet("background: transparent; border-radius: 3px;")
            self.results_table.setCellWidget(row, 1, label)
        except Exception as e:
            print(f"设置专辑封面失败: {e}")

    def on_image_error(self, row):
        try:
            label = QLabel("🎵")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("background: transparent; font-size: 20px; color: #d1d5db;")
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
            "搜索中", "正在全网搜罗音乐，请稍候...", None, self,
            cancellable=True,
        )
        dlg.show()

        # 自动检测搜索类型：URL 开头的解析为歌单，其他搜索歌曲
        search_type = "解析歌单链接" if keyword.startswith("http") else "搜索歌曲"
        self.search_thread = SearchThread(
            self.music_client, keyword, search_type,
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
            self.btn_search.setText("立即搜索")
            if results:
                self.load_table_with_results(results)
            else:
                self.empty_label.setText("未找到相关歌曲")
                self.empty_label.show()
                self.results_table.hide()

        def on_error(error_msg):
            dlg.accept()
            self.btn_search.setEnabled(True)
            self.btn_search.setText("立即搜索")
            show_message(self, QMessageBox.Icon.Critical, "错误", f"搜索失败：{error_msg}")

        self.search_thread.progress.connect(on_progress)
        self.search_thread.partial.connect(on_partial)
        self.search_thread.finished.connect(on_finished)
        self.search_thread.error.connect(on_error)
        self.search_thread.start()



if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MusicDownloader()
    win.show()
    sys.exit(app.exec())