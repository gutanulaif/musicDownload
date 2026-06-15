# -*- coding: utf-8 -*-
"""
音乐下载器 (Music Downloader)
==============================
功能：从多个音乐平台（酷我、酷狗、QQ音乐、网易云等）搜索并下载音乐
技术栈：Python + PySide6 (Qt GUI框架) + musicdl (音乐下载库)

作者：MrsEWE44
"""

import sys  # 系统相关功能，如命令行参数、退出程序等
import os   # 操作系统相关功能，如文件路径、目录操作等

# =====================================================================
# 第一部分：环境配置（必须在创建 GUI 窗口之前执行）
# =====================================================================

# 抑制 FFmpeg/GStreamer 解码警告
# 原因：PySide6 的多媒体模块在后台会调用 FFmpeg/GStreamer 处理音频，
#        但这些库会输出很多调试信息，影响用户体验，所以先关闭
os.environ["QT_LOGGING_RULES"] = "qt.multimedia.ffmpeg=false;qt.multimedia.gstreamer=false"
os.environ["GST_DEBUG"] = "0"      # GStreamer 调试级别设为 0（关闭）
os.environ["FF_LOG_LEVEL"] = "quiet"  # FFmpeg 日志级别设为安静模式

# =====================================================================
# 第二部分：导入依赖库
# =====================================================================

import re           # 正则表达式库，用于文本匹配和替换（如清理文件名中的特殊字符）
import json         # JSON 数据处理库，用于解析 ffprobe 返回的音频信息
import shutil       # 高级文件操作库，用于移动文件（如把下载的音乐移到目标目录）
import subprocess   # 子进程管理库，用于调用外部程序（如 ffprobe 检测音频采样率）
import requests     # HTTP 请求库，用于下载专辑封面图片

# ==================== PySide6 (Qt) GUI 组件导入 ====================
# PySide6 是 Qt 框架的 Python 绑定，用于创建图形用户界面
# Qt 是一个跨平台的 GUI 框架，可以创建桌面应用程序

# --- 窗口和基础组件 ---
from PySide6.QtWidgets import (
    QApplication,     # 应用程序对象，每个 Qt 程序必须有且仅有一个
    QMainWindow,      # 主窗口类，提供菜单栏、状态栏等基础框架
    QWidget,          # 所有 UI 组件的基类
    QDialog,          # 对话框（弹窗）基类
    QVBoxLayout,      # 垂直布局管理器（从上到下排列组件）
    QHBoxLayout,      # 水平布局管理器（从左到右排列组件）
    QLayout,          # 布局管理器基类
    QSizePolicy,      # 控件大小策略，决定控件如何响应窗口大小变化
    QGroupBox,        # 分组框，用于将相关控件组织在一起
    QLabel,           # 文本标签，用于显示文字或图片
    QLineEdit,        # 单行文本输入框
    QPushButton,      # 按钮
    QCheckBox,        # 复选框（打勾的方框）
    QComboBox,        # 下拉选择框
    QSpinBox,         # 数字微调框（可以上下调整数字）
    QProgressBar,     # 进度条
    QTableWidget,     # 表格控件，用于显示多行多列的数据
    QTableWidgetItem, # 表格中的单个单元格项
    QHeaderView,      # 表格的表头
    QMenu,            # 右键菜单
    QFileDialog,      # 文件/目录选择对话框
    QMessageBox,      # 消息提示框
    QStyleOptionSpinBox,  # 微调框的样式选项（用于自定义绘制）
    QStyle,           # 样式相关常量
    QSlider,          # 滑块控件（用于音量调节、播放进度等）
    QGraphicsDropShadowEffect,  # 阴影效果，给控件添加投影
    QGridLayout,      # 网格布局管理器（按行列排列组件）
)

# --- 核心功能组件 ---
from PySide6.QtCore import (
    Qt,               # 包含各种枚举常量（对齐方式、鼠标按钮等）
    QThread,          # 线程类，用于在后台执行耗时操作（如搜索、下载）
    Signal,           # 信号机制，用于线程间通信（安全地更新 UI）
    QSize,            # 尺寸类，表示宽×高
    QRect,            # 矩形类，表示位置和大小
    QPoint,           # 点类，表示坐标位置
    QThreadPool,      # 线程池，管理和复用线程
    QRunnable,        # 可运行的任务，配合线程池使用
    QObject,          # 所有 Qt 对象的基类，信号必须定义在 QObject 上
    QSettings,        # 配置存储，用于保存用户设置（如保存目录、选择的音乐源）
    QUrl,            # URL 处理类
    QTimer,          # 定时器，用于延迟执行（如 Toast 提示自动消失）
)

# --- 图形和字体 ---
from PySide6.QtGui import (
    QPixmap,    # 图片处理类，用于加载和显示图片
    QFont,      # 字体类
    QColor,     # 颜色类
    QPainter,   # 画笔/绘制器，用于自定义绘制 UI
    QAction,    # 动作，用于菜单项和工具栏按钮
    QIcon,      # 图标类
)

# --- 多媒体播放 ---
from PySide6.QtMultimedia import (
    QMediaPlayer,   # 媒体播放器，用于播放音频
    QAudioOutput,   # 音频输出，控制音量和静音
)

# =====================================================================
# 第三部分：导入音乐下载库（可选依赖）
# =====================================================================

# musicdl 是一个第三方音乐下载库，支持从多个平台搜索和下载音乐
# try/except 用于处理"库未安装"的情况，避免程序直接崩溃
try:
    from musicdl import musicdl  # 导入音乐下载核心模块
    MUSICDL_AVAILABLE = True     # 标记：musicdl 可用
except ImportError:
    musicdl = None               # 导入失败，设为 None
    MUSICDL_AVAILABLE = False    # 标记：musicdl 不可用
    print("警告：musicdl 库未安装，请运行 pip install musicdl")


# =====================================================================
# 第四部分：工具函数
# =====================================================================

def sanitize_filename(filename):
    """
    清理文件名，移除不允许出现在文件名中的特殊字符

    Windows 文件名不允许包含这些字符：\\ / * ? : " < > |
    这个函数会把这些字符替换为下划线 _

    参数:
        filename: 原始文件名
    返回:
        清理后的安全文件名
    """
    return re.sub(r'[\\/*?:"<>|]', "_", str(filename))


# =====================================================================
# 第五部分：自定义 UI 组件
# =====================================================================

class ToastLabel(QLabel):
    """
    Toast 通知标签

    什么是 Toast？
    就是那种短暂显示后自动消失的提示信息（类似手机上的通知）。
    比如"下载完成"、"搜索中"这类提示。

    这个组件会显示在主窗口中央，几秒后自动消失。
    """

    def __init__(self, parent=None):
        super().__init__(parent)  # 调用父类 QLabel 的初始化方法
        # 设置居中对齐
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 设置样式：深色背景、白色文字、圆角
        self.setStyleSheet("""
            QLabel {
                background-color: rgba(50, 50, 50, 220);  /* 半透明深色背景 */
                color: white;
                padding: 12px 24px;        /* 内边距 */
                border-radius: 8px;        /* 圆角 */
                font-size: 11pt;
            }
        """)
        self.hide()  # 初始状态隐藏

    def show_toast(self, text, duration=3000):
        """
        显示 Toast 提示

        参数:
            text: 要显示的文字
            duration: 显示时长（毫秒），默认 3000 毫秒 = 3 秒
        """
        self.setText(text)       # 设置文字
        self.adjustSize()        # 自动调整大小以适应文字
        self._center_in_parent() # 移动到父窗口中央
        self.show()              # 显示
        self.raise_()            # 确保在最上层（不被其他控件遮挡）
        # 定时器：duration 毫秒后调用 self.hide() 隐藏
        QTimer.singleShot(duration, self.hide)

    def _center_in_parent(self):
        """将自己移动到父窗口的正中央"""
        if self.parent():
            p = self.parent()
            # 计算居中位置：(父窗口宽度 - 自己宽度) / 2
            x = (p.width() - self.width()) // 2
            y = (p.height() - self.height()) // 2
            self.move(x, y)


def show_message(parent, icon, title, text):
    """
    显示 Toast 消息的便捷函数

    参数:
        parent: 父窗口（通常是主窗口）
        icon: 图标类型（信息、警告、错误）
        title: 标题（目前未使用，保留接口）
        text: 要显示的消息内容
    """
    # 图标类型映射为 emoji
    icons = {
        QMessageBox.Icon.Information: "ℹ️",  # 信息
        QMessageBox.Icon.Warning: "⚠️",      # 警告
        QMessageBox.Icon.Critical: "❌",     # 错误
    }
    prefix = icons.get(icon, "")  # 获取对应的 emoji
    # 检查父窗口是否有 _toast 属性（即是否已初始化 Toast）
    if hasattr(parent, '_toast'):
        parent._toast.show_toast(f"{prefix} {text}")


class NumericTableItem(QTableWidgetItem):
    """
    支持按数值排序的表格项

    问题：普通的 QTableWidgetItem 按字符串排序，
         所以 "10" 会排在 "2" 前面（因为 "1" < "2"）

    解决：重写 __lt__ 方法，让比较基于实际数值而不是字符串
         这样 "2" 就会正确地排在 "10" 前面
    """

    def __lt__(self, other):
        """重写小于运算符，实现数值比较"""
        if isinstance(other, QTableWidgetItem):
            # 从 UserRole 获取存储的数值（在创建时设置的）
            my_val = self.data(Qt.ItemDataRole.UserRole)
            other_val = other.data(Qt.ItemDataRole.UserRole)
            if my_val is not None and other_val is not None:
                try:
                    return float(my_val) < float(other_val)  # 按数值比较
                except (ValueError, TypeError):
                    pass  # 转换失败，使用默认比较
        # 如果不是数值或转换失败，使用默认的字符串比较
        return super().__lt__(other)


def extract_numeric_value(text):
    """
    从显示文本中提取数值，用于排序

    支持的格式：
    - 纯数字：'128' -> 128.0
    - 带小数：'3.5' -> 3.5
    - 时间格式：'3:45' -> 225.0 (3分45秒 = 225秒)
    - 带单位：'10 MB' -> 10.0

    参数:
        text: 文本字符串
    返回:
        提取出的数值
    """
    text = str(text).strip()  # 转为字符串并去除首尾空格
    if not text:
        return 0

    # 尝试直接转换为浮点数
    try:
        return float(text)
    except ValueError:
        pass

    # 尝试解析时间格式 "分:秒"
    if ":" in text:
        parts = text.split(":")
        try:
            if len(parts) == 2:
                # 分钟 * 60 + 秒 = 总秒数
                return int(parts[0]) * 60 + float(parts[1])
        except ValueError:
            pass

    # 使用正则表达式提取第一个数字
    import re as _re
    m = _re.match(r"([\d.]+)", text)
    return float(m.group(1)) if m else 0


# =====================================================================
# 第六部分：自定义现代风格 UI 组件
# =====================================================================

class ModernComboBox(QComboBox):
    """
    现代风格下拉框

    重写了两个方法：
    1. paintEvent - 自定义绘制下拉箭头
    2. showPopup - 下拉时自动调整宽度
    """

    def paintEvent(self, event):
        """自定义绘制：在右侧画一个下拉箭头 ▼"""
        super().paintEvent(event)  # 先执行默认绘制
        painter = QPainter(self)   # 创建画笔
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)  # 开启抗锯齿
        painter.setPen(QColor("#6b7280"))  # 设置画笔颜色（灰色）
        font = self.font()
        font.setPixelSize(10)  # 字体大小设为 10 像素
        painter.setFont(font)
        rect = self.rect()
        # 在右侧居中绘制 "▼"
        painter.drawText(
            rect.adjusted(0, 0, -10, 0),  # 右边留 10px 边距
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "▼",
        )
        painter.end()  # 释放画笔资源

    def showPopup(self):
        """下拉时自动调整弹出列表的宽度"""
        super().showPopup()  # 先显示弹出列表
        popup = self.view()
        # 计算所有选项中最宽的那个
        max_width = self.width()
        for i in range(self.count()):
            # horizontalAdvance 计算文字像素宽度，+40 是左右内边距
            text_width = self.fontMetrics().horizontalAdvance(self.itemText(i)) + 40
            max_width = max(max_width, text_width)
        popup.setFixedWidth(max_width)  # 设置宽度
        popup.setFixedHeight(popup.sizeHint().height())  # 高度紧贴内容


class ModernSpinBox(QSpinBox):
    """
    现代风格数字微调框

    重写 paintEvent，用 ▲▼ 代替默认的箭头按钮
    """

    def paintEvent(self, event):
        super().paintEvent(event)  # 先执行默认绘制
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = self.font()
        font.setPixelSize(10)
        painter.setFont(font)

        # 获取上下按钮的矩形区域
        opt = QStyleOptionSpinBox()
        self.initStyleOption(opt)
        up_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox, opt,
            QStyle.SubControl.SC_SpinBoxUp, self
        )
        down_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox, opt,
            QStyle.SubControl.SC_SpinBoxDown, self,
        )

        # 微调位置使箭头更居中
        draw_up_rect = up_rect.translated(0, 2)
        draw_down_rect = down_rect.translated(0, -2)

        # 检测按钮是否被按下（用于改变颜色）
        up_pressed = opt.activeSubControls == QStyle.SubControl.SC_SpinBoxUp and (
            opt.state & QStyle.StateFlag.State_Sunken
        )
        down_pressed = opt.activeSubControls == QStyle.SubControl.SC_SpinBoxDown and (
            opt.state & QStyle.StateFlag.State_Sunken
        )

        # 绘制 ▲ 和 ▼，按下时变蓝
        painter.setPen(QColor("#0078d4") if up_pressed else QColor("#4b5563"))
        painter.drawText(draw_up_rect, Qt.AlignmentFlag.AlignCenter, "▲")
        painter.setPen(QColor("#0078d4") if down_pressed else QColor("#4b5563"))
        painter.drawText(draw_down_rect, Qt.AlignmentFlag.AlignCenter, "▼")
        painter.end()


# =====================================================================
# 第七部分：后台任务（线程池任务）
# =====================================================================

# ==================== 图片下载任务 ====================

class ImageWorkerSignals(QObject):
    """
    图片下载任务的信号容器

    为什么需要这个类？
    QRunnable（可运行任务）不能直接定义信号，必须借助 QObject 来定义。
    这是 Qt 的限制：只有 QObject 的子类才能使用信号槽机制。
    """
    finished = Signal(int, QPixmap)  # 信号：下载完成，参数是(行号, 图片)
    error = Signal(int)              # 信号：下载失败，参数是(行号)


class ImageDownloadTask(QRunnable):
    """
    图片下载任务（使用线程池执行）

    为什么用 QRunnable + 线程池，而不是直接创建 QThread？
    - 如果同时下载 50 张封面，直接创建 50 个 QThread 会消耗大量内存
    - 线程池可以复用有限数量的线程，比如最多 10 个线程处理 50 个任务
    - 这样内存使用更可控，程序更稳定
    """

    def __init__(self, row, image_url):
        """
        参数:
            row: 表格中的行号（用于知道图片该显示在哪一行）
            image_url: 图片的 URL 地址
        """
        super().__init__()
        self.row = row
        self.image_url = image_url
        self.signals = ImageWorkerSignals()  # 创建信号对象

    def run(self):
        """任务执行体（在线程池中运行）"""
        try:
            if not self.image_url:
                self.signals.error.emit(self.row)
                return

            # 发起 HTTP GET 请求下载图片
            response = requests.get(self.image_url, timeout=5)  # 5秒超时

            if response.status_code == 200:  # 200 表示成功
                pixmap = QPixmap()
                pixmap.loadFromData(response.content)  # 从二进制数据加载图片
                # 缩放到 44x44 像素（保持比例，平滑变换）
                scaled_pixmap = pixmap.scaled(
                    44, 44,
                    Qt.AspectRatioMode.KeepAspectRatio,     # 保持宽高比
                    Qt.TransformationMode.SmoothTransformation,  # 平滑缩放
                )
                self.signals.finished.emit(self.row, scaled_pixmap)
            else:
                self.signals.error.emit(self.row)
        except Exception:
            self.signals.error.emit(self.row)


# ==================== 采样率检测任务 ====================

def find_ffprobe():
    """
    查找 ffprobe 可执行文件的路径

    ffprobe 是 FFmpeg 工具集的一部分，用于检测音频/视频的详细信息
    （如采样率、比特率、编码格式等）

    搜索优先级：
    1. PyInstaller 打包后的临时目录
    2. 脚本所在目录
    3. 脚本同级的 bin 目录
    4. 系统 PATH 环境变量中的路径

    返回:
        ffprobe 的完整路径，找不到则返回 None
    """
    # 检查是否是 PyInstaller 打包的程序
    if getattr(sys, 'frozen', False):
        bundle_dir = sys._MEIPASS  # PyInstaller 临时解压目录
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

    # 系统 PATH（让操作系统帮我们找）
    path = shutil.which("ffprobe")
    if path:
        return path

    return None


class SampleRateWorkerSignals(QObject):
    """采样率检测任务的信号容器"""
    finished = Signal(int, str)  # 信号：检测完成，参数是(行号, 采样率文本)
    error = Signal(int)          # 信号：检测失败


class SampleRateDetectTask(QRunnable):
    """
    采样率检测任务

    通过调用 ffprobe 命令行工具，检测音频 URL 的采样率
    采样率越高，音质越好（常见：44100Hz, 48000Hz, 96000Hz 等）
    """

    def __init__(self, row, download_url):
        super().__init__()
        self.row = row
        self.download_url = download_url
        self.signals = SampleRateWorkerSignals()

    def run(self):
        """任务执行体"""
        try:
            ffprobe_path = find_ffprobe()
            if not ffprobe_path:
                self.signals.error.emit(self.row)
                return

            # 验证 URL 是否有效
            if not self.download_url or not str(self.download_url).startswith("http"):
                self.signals.error.emit(self.row)
                return

            # 调用 ffprobe 命令行工具
            # 参数说明：
            # -v quiet       : 安静模式，不输出额外信息
            # -print_format json : 以 JSON 格式输出（方便解析）
            # -show_streams  : 显示流信息
            # -select_streams a:0 : 只选择第一个音频流
            result = subprocess.run(
                [
                    ffprobe_path, "-v", "quiet",
                    "-print_format", "json",
                    "-show_streams", "-select_streams", "a:0",
                    str(self.download_url),
                ],
                capture_output=True,  # 捕获输出
                text=True,            # 以文本模式返回
                timeout=15,           # 15秒超时
            )

            if result.returncode != 0:  # 非 0 表示出错
                self.signals.error.emit(self.row)
                return

            # 解析 JSON 输出
            info = json.loads(result.stdout)
            streams = info.get("streams", [])

            if streams:
                sr = streams[0].get("sample_rate", "")
                if sr:
                    # 转换为 kHz 显示，如 44100 -> "44 kHz"
                    sr_khz = int(sr) / 1000
                    self.signals.finished.emit(self.row, f"{sr_khz:.0f} kHz")
                    return

            self.signals.error.emit(self.row)
        except Exception:
            self.signals.error.emit(self.row)


# =====================================================================
# 第八部分：后台搜索线程
# =====================================================================

class SearchThread(QThread):
    """
    搜索线程

    为什么搜索要放在单独的线程中？
    - 搜索需要网络请求，可能很慢（几秒到几十秒）
    - 如果在主线程执行，界面会"卡死"，用户无法操作
    - 放在后台线程，界面保持响应，可以显示进度

    信号说明：
    - finished(dict): 全部搜索完成，发送所有结果
    - partial(dict, str): 部分源搜索完成，实时更新进度
    - error(str): 搜索出错
    - progress(str): 进度消息
    """

    finished = Signal(dict)
    partial = Signal(dict, str)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, music_client, keyword, search_type, source_map_en_to_cn=None):
        """
        参数:
            music_client: 音乐下载客户端对象
            keyword: 搜索关键词
            search_type: 搜索类型（"搜索歌曲" 或 "解析歌单链接"）
            source_map_en_to_cn: 英文源名到中文名的映射字典
        """
        super().__init__()
        self.music_client = music_client
        self.keyword = keyword
        self.search_type = search_type
        self._cancelled = False  # 取消标志
        self._source_map_en_to_cn = source_map_en_to_cn or {}

    def cancel(self):
        """设置取消标志，让搜索线程在下一个检查点退出"""
        self._cancelled = True

    def run(self):
        """线程执行体"""
        try:
            if self.search_type == "搜索歌曲":
                self._search_concurrent()  # 并发搜索所有源
            else:
                # 解析歌单链接
                results = self.music_client.parseplaylist(self.keyword)
                if not isinstance(results, dict):
                    results = {"歌单": results}
                self.finished.emit(results)
        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))

    def _search_concurrent(self):
        """
        并发搜索所有音乐源

        工作原理：
        1. 把所有搜索源（酷我、酷狗、QQ音乐等）一次性提交给线程池
        2. 线程池同时执行多个搜索任务
        3. 使用轮询方式检查哪些任务完成了
        4. 每完成一个，就通过 partial 信号通知主线程更新 UI
        5. 全部完成后，通过 finished 信号发送所有结果
        """
        from concurrent.futures import ThreadPoolExecutor
        import threading
        import time
        from datetime import datetime

        all_results = {}       # 存储所有搜索结果
        lock = threading.Lock()  # 线程锁，保护 all_results 的并发访问
        sources = list(self.music_client.music_clients.keys())  # 所有音乐源
        total = len(sources)
        completed_count = [0]  # 用列表而不是普通变量，因为闭包需要可变对象

        # 打印搜索日志（仿照 musicdl 的格式）
        source_names = "|".join(sources)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        print(f"{ts} - musicdl - INFO - Searching \033[93m{self.keyword}\033[0m From \033[93m{source_names}\033[0m")

        self.progress.emit(f"正在并发搜索 {total} 个音乐源...")

        def search_one_source(source):
            """搜索单个音乐源的函数"""
            if self._cancelled:
                return source, []
            try:
                # 调用 musicdl 库的搜索方法
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

        # 创建线程池，最大并发数 = min(源数量, 10)
        executor = ThreadPoolExecutor(max_workers=min(total, 10))
        try:
            # 提交所有搜索任务
            futures = {
                executor.submit(search_one_source, src): src
                for src in sources
            }
            pending = set(futures.keys())  # 待完成的任务集合

            while pending and not self._cancelled:
                # 轮询检查：哪些任务已完成？
                done = [f for f in pending if f.done()]
                if not done:
                    time.sleep(0.1)  # 没有完成的，等 100ms 再检查
                    continue

                # 处理已完成的任务
                for future in done:
                    pending.discard(future)  # 从待完成集合移除
                    source = futures[future]
                    source_cn = self._source_map_en_to_cn.get(source, source)

                    try:
                        source, result = future.result(timeout=0)  # 获取结果
                    except Exception as e:
                        print(f"搜索 {source} 异常: {e}")
                        result = []

                    # 打印日志
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
                    count = len(result) if result else 0
                    print(f"{ts} - musicdl - INFO - {source}.search >>> Completed ({completed_count[0]+1}/{total}) Search URLs, got {count} results")

                    if result:
                        with lock:  # 加锁保护共享数据
                            all_results[source] = result
                            completed_count[0] += 1
                            # 发送部分完成信号，实时更新 UI
                            self.partial.emit(
                                dict(all_results),
                                f"{source_cn} ({completed_count[0]}/{total})",
                            )

            # 所有任务完成（或被取消）
            self.finished.emit(all_results)
        finally:
            executor.shutdown(wait=False)  # 关闭线程池，不等待未完成的任务


# =====================================================================
# 第九部分：下载线程
# =====================================================================

class DownloadThread(QThread):
    """
    下载线程

    负责将搜索到的音乐下载并保存到指定目录
    """

    finished = Signal(int)   # 信号：下载完成，参数是成功数量
    error = Signal(str)      # 信号：下载出错

    def __init__(self, music_client, song_infos, target_dir):
        """
        参数:
            music_client: 音乐客户端
            song_infos: 要下载的歌曲信息列表
            target_dir: 保存目录
        """
        super().__init__()
        self.music_client = music_client
        self.song_infos = song_infos
        self.target_dir = target_dir

    def _get_val(self, obj, key, default=""):
        """
        安全获取对象的值（兼容 dict 和对象）

        参数:
            obj: 字典或对象
            key: 键名/属性名
            default: 默认值
        """
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default) if hasattr(obj, key) else default

    def run(self):
        """线程执行体"""
        try:
            # 调用 musicdl 库的下载方法
            downloaded_songs = self.music_client.download(song_infos=self.song_infos)
            success_count = 0

            for song in downloaded_songs:
                save_path = self._get_val(song, "save_path")
                if not save_path or not os.path.exists(save_path):
                    continue

                # 获取歌曲信息
                song_name = self._get_val(song, "song_name", "未知歌曲")
                singers = self._get_val(song, "singers", "未知歌手")
                if isinstance(singers, list):
                    singer = "&".join([str(s) for s in singers])
                else:
                    singer = str(singers)

                album = self._get_val(song, "album", "")
                identifier = self._get_val(song, "identifier", "")

                # 获取文件扩展名
                ext = os.path.splitext(save_path)[1].lstrip(".")
                if not ext:
                    ext = self._get_val(song, "ext", "mp3")

                # 构建新文件名：歌曲名-歌手-专辑-标识.扩展名
                parts = [song_name, singer]
                if album:
                    parts.append(str(album))
                if identifier:
                    parts.append(str(identifier))

                base_name = sanitize_filename("-".join(parts))
                new_audio_name = f"{base_name}.{ext}"
                new_audio_path = os.path.join(self.target_dir, new_audio_name)

                # 移动音频文件
                try:
                    if os.path.exists(new_audio_path):
                        os.remove(new_audio_path)  # 删除已存在的同名文件
                    shutil.move(save_path, new_audio_path)
                    success_count += 1
                except Exception as e:
                    print(f"移动音频文件失败 {save_path}: {e}")

                # 移动歌词文件（如果有）
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


# =====================================================================
# 第十部分：进度对话框
# =====================================================================

class SimpleProgressDialog(QDialog):
    """
    简单的进度对话框

    无边框、圆角、现代风格
    可选是否显示取消按钮
    """

    def __init__(self, title, message, save_dir=None, parent=None, cancellable=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(360)
        # 无边框窗口标志
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        # 应用模态：阻止用户操作其他窗口
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setStyleSheet("""
            QDialog { background-color: #ffffff; border: 1px solid #d1d5db; border-radius: 10px; }
        """)

        # 居中显示在父窗口中央
        if parent:
            self.move(
                parent.x() + (parent.width() - self.width()) // 2,
                parent.y() + (parent.height() - self.height()) // 2,
            )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        # 提示文字
        self.label = QLabel(message)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("font-size: 11pt; color: #1f2937; font-weight: bold;")
        layout.addWidget(self.label)

        # 保存目录（如果有的话）
        if save_dir:
            dir_label = QLabel(f"保存到：{save_dir}")
            dir_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dir_label.setStyleSheet("font-size: 9pt; color: #6b7280;")
            dir_label.setWordWrap(True)
            layout.addWidget(dir_label)

        # 进度条（不确定模式：来回滚动的动画）
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # 设置为不确定模式
        self.progress.setStyleSheet("""
            QProgressBar { border: none; border-radius: 4px; background-color: #f3f4f6; height: 6px; }
            QProgressBar::chunk { background-color: #0078d4; border-radius: 4px; }
        """)
        layout.addWidget(self.progress)

        # 取消按钮（可选）
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
        """更新提示文字"""
        self.label.setText(text)

    def set_cancelled(self):
        """标记为已取消"""
        self._cancelled = True
        if self.cancel_btn:
            self.cancel_btn.setEnabled(False)
            self.cancel_btn.setText("已取消")

    def is_cancelled(self):
        return self._cancelled


# =====================================================================
# 第十一部分：流式布局
# =====================================================================

class FlowLayout(QLayout):
    """
    流式布局（FlowLayout）

    类似于文字排版：从左到右排列控件，一行放不下时自动换行。
    常用于标签云、按钮组等需要自动换行的场景。

    这是一个自定义布局类，Qt 没有内置的流式布局。
    """

    def __init__(self, parent=None, margin=-1, hspacing=-1, vspacing=-1):
        super(FlowLayout, self).__init__(parent)
        self._item_list = []     # 存储所有布局项
        self._hspacing = hspacing  # 水平间距
        self._vspacing = vspacing  # 垂直间距
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        """析构函数：清理所有布局项"""
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        """添加一个布局项"""
        self._item_list.append(item)

    def horizontalSpacing(self):
        """获取水平间距"""
        return (
            self._hspacing
            if self._hspacing >= 0
            else self.smartSpacing(QStyle.PixelMetric.PM_LayoutHorizontalSpacing)
        )

    def verticalSpacing(self):
        """获取垂直间距"""
        return (
            self._vspacing
            if self._vspacing >= 0
            else self.smartSpacing(QStyle.PixelMetric.PM_LayoutVerticalSpacing)
        )

    def count(self):
        """返回布局项数量"""
        return len(self._item_list)

    def itemAt(self, index):
        """获取指定索引的布局项"""
        return self._item_list[index] if 0 <= index < len(self._item_list) else None

    def takeAt(self, index):
        """移除并返回指定索引的布局项"""
        return self._item_list.pop(index) if 0 <= index < len(self._item_list) else None

    def expandingDirections(self):
        """返回不扩展的方向（流式布局不需要扩展）"""
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        """返回 True 表示高度由宽度决定（这是流式布局的核心特性）"""
        return True

    def heightForWidth(self, width):
        """根据给定宽度计算需要的高度"""
        return self.calculateHeight(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        """设置布局的几何区域（实际排列控件的位置）"""
        super(FlowLayout, self).setGeometry(rect)
        self.calculateHeight(rect, False)

    def sizeHint(self):
        """返回推荐大小"""
        return self.minimumSize()

    def minimumSize(self):
        """返回最小大小"""
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom()
        )

    def maximumSize(self):
        """返回最大大小"""
        _MAX = (1 << 24) - 1  # Qt QWIDGETSIZE_MAX
        return QSize(_MAX, self.heightForWidth(_MAX) if self.count() > 0 else _MAX)

    def calculateHeight(self, rect, testOnly):
        """
        核心算法：计算布局高度并排列控件

        testOnly=True 时只计算高度不实际移动控件（用于 hasHeightForWidth）
        testOnly=False 时计算并实际排列控件
        """
        margins = self.contentsMargins()
        effective = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        x, y = effective.x(), effective.y()
        lineHeight = 0

        for item in self._item_list:
            widget = item.widget()
            # 计算水平间距
            spaceX = self.horizontalSpacing()
            if spaceX == -1:
                spaceX = widget.style().layoutSpacing(
                    QSizePolicy.ControlType.PushButton,
                    QSizePolicy.ControlType.PushButton,
                    Qt.Orientation.Horizontal,
                )
            # 计算垂直间距
            spaceY = self.verticalSpacing()
            if spaceY == -1:
                spaceY = widget.style().layoutSpacing(
                    QSizePolicy.ControlType.PushButton,
                    QSizePolicy.ControlType.PushButton,
                    Qt.Orientation.Vertical,
                )

            # 计算下一个控件的位置
            nextX = x + item.sizeHint().width() + spaceX

            # 如果超出右边界且不是第一项，换行
            if nextX - spaceX > effective.right() and lineHeight > 0:
                x, y = effective.x(), y + lineHeight + spaceY
                nextX, lineHeight = x + item.sizeHint().width() + spaceX, 0

            # 如果不是测试模式，实际设置控件位置
            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x, lineHeight = nextX, max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y() + margins.bottom()

    def smartSpacing(self, pm):
        """智能获取间距"""
        parent = self.parent()
        if not parent:
            return -1
        if isinstance(parent, QWidget):
            return parent.style().pixelMetric(pm, None, parent)
        elif isinstance(parent, QLayout):
            return parent.spacing()
        return -1


# =====================================================================
# 第十二部分：现代风格对话框
# =====================================================================

class ModernDialog(QDialog):
    """
    现代风格对话框

    特点：
    - 无边框 + 圆角
    - 阴影效果
    - 自定义按钮样式
    - 支持拖动移动
    - 提供便捷的静态方法（question, warning, information）
    """

    def __init__(self, parent=None, title="", message="", icon="question",
                 buttons=("取消", "确定"), default=1):
        super().__init__(parent)
        # 窗口标志：无边框、对话框、置顶
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        # 透明背景（阴影效果需要）
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)  # 模态对话框
        self._result = -1    # 返回结果（按钮索引）
        self._buttons = []   # 存储按钮引用
        self._init_ui(title, message, icon, buttons, default)

    def _init_ui(self, title, message, icon, buttons, default):
        """初始化界面"""
        # 外层容器（绘制白色背景 + 圆角）
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

        # 图标 + 标题行
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
                # 默认按钮（蓝色）
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
                # 次要按钮（灰色）
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

        # 阴影效果
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 40))
        self._container.setGraphicsEffect(shadow)

    def _on_button(self, index):
        """按钮点击处理"""
        self._result = index
        self.accept()  # 关闭对话框

    def result(self):
        """返回用户点击的按钮索引"""
        return self._result

    # 支持拖动移动窗口
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if hasattr(self, '_drag_pos') and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    @staticmethod
    def question(parent, title, message, buttons=("取消", "确定"), default=1):
        """便捷方法：显示询问对话框，返回按钮索引"""
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


# =====================================================================
# 第十三部分：音频播放器组件
# =====================================================================

class AudioPlayerWidget(QWidget):
    """
    底部在线音频播放器

    功能：
    - 播放/暂停/停止
    - 上一首（回到开头）
    - 进度条（可拖动）
    - 音量调节
    - 静音切换

    位于主窗口底部，固定高度 56px
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._slider_pressed = False  # 标记进度条是否被按住
        self._current_title = ""      # 当前播放的歌曲名
        # 固定高度，防止在垂直方向扩展
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(56)
        self._init_ui()
        self._init_player()
        self._apply_style()

    def _init_ui(self):
        """初始化界面布局"""
        # 外层容器（深色背景）
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

        # 歌曲标题
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
        layout.addWidget(self.position_slider, 1)  # stretch=1 表示占据剩余空间
        layout.addWidget(self.time_total)

        # 音量控制
        self.mute_btn = self._make_btn(QStyle.StandardPixmap.SP_MediaVolume, "静音切换")
        self.mute_btn.setFixedSize(34, 34)
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)  # 默认音量 70%
        self.volume_slider.setFixedWidth(90)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.mute_btn.clicked.connect(self._on_mute_toggle)

        layout.addWidget(self.mute_btn)
        layout.addWidget(self.volume_slider)

    def _make_btn(self, icon, tooltip=""):
        """创建播放控制按钮"""
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
        """应用播放器样式"""
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
        """初始化媒体播放器"""
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.7)  # 默认音量 70%

        # 连接信号到槽函数
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_state_changed)
        self.player.errorOccurred.connect(self._on_error)

    def play_url(self, url, title=""):
        """加载并播放指定 URL 的音频"""
        self._current_title = title
        if title:
            self.title_label.setText(title)
            self.title_label.setToolTip(title)
        self.player.setSource(QUrl(url))
        self.player.play()

    def _on_play_pause(self):
        """播放/暂停切换"""
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_stop(self):
        """停止播放"""
        self.player.stop()

    def _on_prev(self):
        """回到开头"""
        self.player.setPosition(0)

    def _on_slider_pressed(self):
        self._slider_pressed = True

    def _on_slider_released(self):
        self._slider_pressed = False

    def _on_seek(self, position):
        """跳转到指定位置"""
        self.player.setPosition(position)

    def _on_position_changed(self, position):
        """播放位置变化时更新进度条"""
        if not self._slider_pressed:  # 用户没有拖动进度条时才自动更新
            self.position_slider.setValue(position)
        self.time_current.setText(self._fmt_time(position))

    def _on_duration_changed(self, duration):
        """音频总时长变化时更新进度条范围"""
        self.position_slider.setRange(0, duration)
        self.time_total.setText(self._fmt_time(duration))

    def _on_state_changed(self, state):
        """播放状态变化时切换按钮图标"""
        if state == QMediaPlayer.PlayingState:
            self.play_btn.setIcon(self._colorize_icon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause)))
            self.play_btn.setToolTip("暂停")
        else:
            self.play_btn.setIcon(self._colorize_icon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)))
            self.play_btn.setToolTip("播放")

    def _on_error(self, error, msg):
        """播放出错时恢复按钮图标"""
        if error != QMediaPlayer.Error.NoError:
            self.play_btn.setIcon(self._colorize_icon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)))

    def _on_volume_changed(self, value):
        """音量变化时更新播放器音量"""
        self.audio_output.setVolume(value / 100.0)

    def _on_mute_toggle(self):
        """静音切换"""
        muted = self.audio_output.isMuted()
        self.audio_output.setMuted(not muted)

    @staticmethod
    def _fmt_time(ms):
        """将毫秒格式化为 mm:ss 格式"""
        s = int(ms / 1000)
        return f"{s // 60:02d}:{s % 60:02d}"


# =====================================================================
# 第十四部分：主窗口
# =====================================================================

class MusicDownloader(QMainWindow):
    """
    音乐下载器主窗口

    这是程序的核心类，负责：
    1. 界面布局和控件管理
    2. 音乐搜索和结果展示
    3. 音乐下载和文件管理
    4. 用户设置的保存和加载
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎵 音乐下载器")
        self.setMinimumSize(1000, 700)  # 最小尺寸
        self.resize(1200, 800)          # 默认尺寸

        # 设置全局字体
        font = QFont("Microsoft YaHei", 10)  # 微软雅黑，10pt
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)  # 优先抗锯齿
        QApplication.setFont(font)
        self.setStyleSheet(self.get_modern_style())

        # ==================== 音乐源配置 ====================
        # 定义所有可用的音乐源，分为国内和海外两组
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

        # 创建中英文名称映射
        self.source_map_cn_to_en = {}
        for group_sources in self.source_groups.values():
            for cn_name, en_name in group_sources:
                self.source_map_cn_to_en[cn_name] = en_name
        self.source_map_en_to_cn = {v: k for k, v in self.source_map_cn_to_en.items()}

        # ==================== 状态变量 ====================
        self.search_results = {}      # 搜索结果
        self.music_records = {}       # 音乐记录（行号 -> 歌曲信息）
        self.music_client = None      # 音乐客户端
        self.current_right_click_row = -1  # 右键点击的行

        # ==================== 线程池 ====================
        # 全局线程池，用于图片下载和采样率检测
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(10)  # 最多 10 个并发线程

        # ==================== 用户设置 ====================
        self.current_dir = os.getcwd()
        self.settings = QSettings("musicDownload", "MusicDownloader")  # 配置文件

        # 加载保存的目录
        saved = self.settings.value("save_dir", "")
        if saved and os.path.isdir(saved):
            self.save_dir = saved
        else:
            self.save_dir = os.path.join(self.current_dir, "已下载音乐")
        os.makedirs(self.save_dir, exist_ok=True)

        # 加载保存的音乐源选择
        saved_sources = self.settings.value("selected_sources", "")
        if saved_sources:
            self.saved_sources = [s for s in saved_sources.split(",") if s]
        else:
            self.saved_sources = ["酷我音乐"]

        # 加载保存的搜索数量限制
        self.saved_limit = int(self.settings.value("search_limit", 3))

        # ==================== 创建界面 ====================
        central = QWidget()
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        # 设置顶部区域（音乐源选择 + 搜索框）
        self.setup_top(main_layout)
        # 设置表格区域（搜索结果展示）
        self.setup_table(main_layout)

        # 底部播放器
        self.audio_player = AudioPlayerWidget(self)
        main_layout.addWidget(self.audio_player)

        # 初始化 Toast 通知
        self._toast = ToastLabel(self)

        # 检查 musicdl 是否可用
        if not MUSICDL_AVAILABLE:
            show_message(self, QMessageBox.Icon.Warning, "警告", "musicdl 库未安装！\n请运行: pip install musicdl")

    def get_modern_style(self):
        """
        返回全局 QSS 样式表

        QSS (Qt Style Sheets) 类似于网页的 CSS，用于美化 Qt 界面
        """
        return """
        /* ===== 基础背景 ===== */
        #CentralWidget { background-color: #f1f5f9; }

        /* ===== 复选框 ===== */
        QCheckBox {
            spacing: 6px;
            color: #475569;
            font-size: 10pt;
        }
        QCheckBox:hover { color: #14b8a6; }
        QCheckBox::indicator {  /* 复选框的方框部分 */
            width: 16px; height: 16px;
            border: 2px solid #cbd5e1;
            border-radius: 4px;
            background: #ffffff;
        }
        QCheckBox::indicator:hover {
            border-color: #14b8a6;
        }
        QCheckBox::indicator:checked {  /* 选中状态 */
            background-color: #14b8a6;
            border-color: #14b8a6;
        }

        /* ===== 输入框 / 下拉框 / 数字微调框 ===== */
        QLineEdit, ModernComboBox, ModernSpinBox {
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 5px 12px;
            background: #ffffff;
            min-height: 24px;
            color: #0f172a;
            font-size: 10pt;
        }
        QLineEdit:focus, ModernComboBox:focus, ModernSpinBox:focus {
            border: 2px solid #14b8a6;
            padding: 4px 11px;
        }
        ModernComboBox::drop-down { width: 26px; border: none; background: transparent; }
        ModernComboBox::down-arrow { image: none; }
        ModernComboBox QAbstractItemView {
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            background-color: #ffffff;
            selection-background-color: #ccfbf1;
            selection-color: #0f172a;
            outline: none; padding: 4px;
            min-width: 140px;
        }
        ModernComboBox QAbstractItemView::item {
            min-height: 32px; border-radius: 4px; padding: 4px 12px;
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
            alternate-background-color: #f8fafc;  /* 交替行颜色 */
            color: #334155;
            selection-background-color: #ccfbf1;
            selection-color: #0f172a;
            outline: none;
            font-size: 10pt;
        }
        QHeaderView::section {  /* 表头样式 */
            background: #f1f5f9;
            color: #475569;
            font-weight: bold; font-size: 10pt;
            border: none;
            border-bottom: 2px solid #e2e8f0;
            border-right: 1px solid #e2e8f0;
            padding: 8px 10px;
        }
        QTableWidget::item { padding: 3px; border-bottom: 1px solid #f1f5f9; }

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
        """
        设置顶部区域

        包含：
        1. 音乐源选择卡片（复选框组）
        2. 单源获取数量 + 保存目录
        3. 搜索输入框 + 搜索按钮
        """
        # ==================== 音乐源选择卡片 ====================
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

        # 收集所有音乐源
        all_sources = []
        for sources in self.source_groups.values():
            all_sources.extend(sources)

        # 使用流式布局排列复选框（自动换行）
        flow = FlowLayout()
        flow.setSpacing(8)
        flow.setContentsMargins(0, 0, 0, 0)
        self.source_checkboxes = []  # 存储所有复选框的引用
        for cn_name, en_name in all_sources:
            cb = QCheckBox(cn_name)
            cb.setMinimumWidth(140)  # 统一最小宽度
            if cn_name in self.saved_sources:
                cb.setChecked(True)  # 恢复上次的选择
            cb.stateChanged.connect(self._on_source_checkbox_changed)
            self.source_checkboxes.append(cb)
            flow.addWidget(cb)

        # 用普通 widget 包裹 FlowLayout（因为 layout 不能直接 addWidget）
        flow_widget = QWidget()
        flow_widget.setLayout(flow)
        flow_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        card_layout.addWidget(flow_widget)

        # 添加阴影效果
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setXOffset(0)
        shadow.setYOffset(1)
        shadow.setColor(QColor(0, 0, 0, 20))
        card.setGraphicsEffect(shadow)
        main_layout.addWidget(card)

        # ==================== 单源获取数量 + 保存目录 ====================
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
        self.save_dir_edit.setReadOnly(True)  # 只读，只能通过浏览按钮选择
        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.clicked.connect(self.on_browse_save_dir)

        h1.addWidget(label_limit)
        h1.addWidget(self.spin_limit)
        h1.addSpacing(15)
        h1.addWidget(label_save)
        h1.addWidget(self.save_dir_edit, 1)  # stretch=1 表示占据剩余空间
        h1.addWidget(self.btn_browse)
        main_layout.addWidget(h1_widget)

        # ==================== 搜索输入框 ====================
        h2_widget = QWidget()
        h2_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        h2 = QHBoxLayout(h2_widget)
        h2.setContentsMargins(0, 0, 0, 0)
        h2.setSpacing(8)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "请输入关键词或输入歌单链接，按回车键也可搜索..."
        )
        self.search_edit.returnPressed.connect(self.on_search)  # 回车键触发搜索

        self.btn_search = QPushButton("立即搜索")
        self.btn_search.setFixedWidth(110)
        self.btn_search.clicked.connect(self.on_search)

        h2.addWidget(self.search_edit, 1)
        h2.addWidget(self.btn_search)
        main_layout.addWidget(h2_widget)

    def setup_table(self, parent_layout):
        """
        设置搜索结果表格

        表格列说明：
        0. 选择（复选框）
        1. 专辑封面（图片）
        2. 歌曲名
        3. 歌手
        4. 专辑
        5. 格式（MP3, FLAC 等）
        6. 采样率（44 kHz 等）
        7. 大小
        8. 时长
        9. 来源（酷我、QQ音乐等）
        """
        # 空状态提示
        self.empty_label = QLabel("输入关键词，点击搜索")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("""
            color: #94a3b8; font-size: 12pt; padding: 60px 0;
            background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px;
        """)
        parent_layout.addWidget(self.empty_label, 1)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(10)
        self.results_table.setHorizontalHeaderLabels([
            "选择", "专辑封面", "歌曲名", "歌手", "专辑",
            "格式", "采样率", "大小", "时长", "来源",
        ])
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)  # 禁止编辑
        self.results_table.verticalHeader().setVisible(False)  # 隐藏行号
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)  # 整行选择
        self.results_table.setAlternatingRowColors(True)  # 交替行颜色
        self.results_table.setShowGrid(False)  # 隐藏网格线
        self.results_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 禁止焦点
        self.results_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(self.show_table_context_menu)

        # 设置列宽
        self.results_table.setColumnWidth(0, 40)   # 选择
        self.results_table.setColumnWidth(1, 65)   # 封面
        self.results_table.setColumnWidth(2, 280)  # 歌曲名
        self.results_table.setColumnWidth(3, 160)  # 歌手
        self.results_table.setColumnWidth(4, 200)  # 专辑
        self.results_table.setColumnWidth(5, 60)   # 格式
        self.results_table.setColumnWidth(6, 80)   # 采样率
        self.results_table.setColumnWidth(7, 80)   # 大小
        self.results_table.setColumnWidth(8, 70)   # 时长
        self.results_table.verticalHeader().setDefaultSectionSize(54)  # 行高
        self.results_table.doubleClicked.connect(self.on_play_row)  # 双击播放

        # 启用排序
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
        parent_layout.addWidget(self.results_table, 1)

    def show_table_context_menu(self, pos):
        """显示右键菜单"""
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
        """下载当前右键点击的歌曲"""
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

        # 显示确认对话框
        if ModernDialog.question(self, "确认下载",
                f"确定要下载这首歌曲吗？\n\n🎵 {song_name} - {singers}") != 1:
            return

        self._start_download_task([song_info], f"正在处理：{song_name}")

    def select_all_songs(self):
        """全选所有歌曲"""
        for row in range(self.results_table.rowCount()):
            cell_widget = self.results_table.cellWidget(row, 0)
            if cell_widget:
                checkbox = cell_widget.findChild(QCheckBox)
                if checkbox:
                    checkbox.setChecked(True)

    def deselect_all_songs(self):
        """取消全选"""
        for row in range(self.results_table.rowCount()):
            cell_widget = self.results_table.cellWidget(row, 0)
            if cell_widget:
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
        """浏览选择保存目录"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择保存/导出目录", self.current_dir
        )
        if dir_path:
            self.save_dir = dir_path
            self.save_dir_edit.setText(dir_path)
            self.settings.setValue("save_dir", dir_path)  # 保存到配置

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
        """初始化音乐下载客户端"""
        if not MUSICDL_AVAILABLE:
            return None
        os.makedirs(self.save_dir, exist_ok=True)
        temp_work_dir = os.path.join(self.current_dir, ".musicdl_temp")
        os.makedirs(temp_work_dir, exist_ok=True)

        src_names = self.get_selected_sources()
        if not src_names:
            show_message(self, QMessageBox.Icon.Warning, "提示", "请至少选择一个音乐来源！")
            return None

        # 构建配置
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
        """获取用户选择的所有音乐源（英文名）"""
        return [
            self.source_map_cn_to_en[cb.text()]
            for cb in self.source_checkboxes
            if cb.isChecked()
        ]

    def get_file_format(self, song_info):
        """从歌曲信息中提取文件格式"""
        for field in ["format", "ext", "file_format", "type"]:
            if song_info.get(field):
                return str(song_info[field]).upper()
        # 尝试从 URL 中推断
        url = song_info.get("download_url", "").lower()
        for ext in ["mp3", "flac", "wav", "m4a", "aac"]:
            if f".{ext}" in url:
                return ext.upper()
        return "未知"

    def get_album_image_url(self, song_info):
        """从歌曲信息中提取专辑封面 URL"""
        for field in [
            "cover", "album_cover", "pic", "picture", "img",
            "image", "album_img", "album_pic", "cover_url", "pic_url",
        ]:
            url = str(song_info.get(field, ""))
            if url.startswith("http"):
                return url
        return ""

    def load_table_with_results(self, search_results):
        """
        将搜索结果加载到表格中

        参数:
            search_results: 搜索结果字典 {源名: [歌曲列表]}
        """
        self.results_table.setSortingEnabled(False)  # 先禁用排序（提高性能）
        self.results_table.setRowCount(0)
        self.search_results = search_results
        self.music_records = {}
        self.empty_label.hide()
        self.results_table.show()

        self.thread_pool.clear()  # 清理旧的排队任务

        # 统计所有歌曲
        all_songs = []
        for per_source in search_results.values():
            all_songs.extend(per_source)

        self.results_table.setRowCount(len(all_songs))
        row = 0
        for _, per_source_search_results in search_results.items():
            for per_source_search_result in per_source_search_results:
                # 创建复选框
                w = QWidget()
                lay = QHBoxLayout(w)
                checkbox = QCheckBox()
                checkbox.song_info = per_source_search_result  # 绑定歌曲信息
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
                        # 大小和时长使用 NumericTableItem（支持数值排序）
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

                # 异步检测采样率
                download_url = per_source_search_result.get("download_url", "")
                if download_url:
                    task = SampleRateDetectTask(row, download_url)
                    task.signals.finished.connect(self.on_samplerate_detected)
                    task.signals.error.connect(self.on_samplerate_error)
                    self.thread_pool.start(task)

                # 异步下载专辑封面
                album_image_url = self.get_album_image_url(per_source_search_result)
                if album_image_url:
                    task = ImageDownloadTask(row, album_image_url)
                    task.signals.finished.connect(self.on_image_downloaded)
                    task.signals.error.connect(self.on_image_error)
                    self.thread_pool.start(task)
                else:
                    self.on_image_error(row)

                row += 1

        self.results_table.setSortingEnabled(True)  # 重新启用排序
        show_message(self, QMessageBox.Icon.Information, "搜索完毕", f"搜索完成！共找到 {row} 首歌曲。\n(专辑封面正在后台加载...)")

    def _start_download_task(self, songs_list, msg):
        """启动下载任务"""
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
        """图片下载完成的回调"""
        try:
            label = QLabel()
            label.setPixmap(pixmap)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("border-radius: 3px;")
            self.results_table.setCellWidget(row, 1, label)
        except Exception as e:
            print(f"设置专辑封面失败: {e}")

    def on_image_error(self, row):
        """图片下载失败的回调"""
        try:
            label = QLabel("🎵")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-size: 20px; color: #d1d5db;")
            self.results_table.setCellWidget(row, 1, label)
        except Exception as e:
            print(f"设置专辑封面失败: {e}")

    def on_samplerate_detected(self, row, sr_text):
        """采样率检测完成的回调"""
        try:
            item = QTableWidgetItem(sr_text)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
            )
            self.results_table.setItem(row, 6, item)
        except Exception as e:
            print(f"设置采样率失败: {e}")

    def on_samplerate_error(self, row):
        """采样率检测失败的回调"""
        try:
            item = QTableWidgetItem("-")
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
            )
            self.results_table.setItem(row, 6, item)
        except Exception as e:
            print(f"设置采样率失败: {e}")

    def on_search(self):
        """
        执行搜索

        流程：
        1. 获取搜索关键词
        2. 初始化音乐客户端
        3. 创建搜索线程
        4. 显示进度对话框
        5. 等待搜索完成
        6. 加载结果到表格
        """
        keyword = self.search_edit.text().strip()
        if not keyword:
            show_message(self, QMessageBox.Icon.Warning, "提示", "请输入你要搜索的关键词！")
            return

        self.music_client = self.init_music_client()
        if not self.music_client:
            return

        # 禁用搜索按钮，防止重复点击
        self.btn_search.setEnabled(False)
        self.btn_search.setText("搜索中...")

        # 显示进度对话框
        dlg = SimpleProgressDialog(
            "搜索中", "正在全网搜罗音乐，请稍候...", None, self,
            cancellable=True,
        )
        dlg.show()

        # 自动检测搜索类型
        search_type = "解析歌单链接" if keyword.startswith("http") else "搜索歌曲"
        self.search_thread = SearchThread(
            self.music_client, keyword, search_type,
            source_map_en_to_cn=self.source_map_en_to_cn,
        )

        # 取消按钮回调
        def on_cancel():
            dlg.set_cancelled()
            dlg.set_message("正在取消搜索...")
            self.search_thread.cancel()

        dlg.cancel_btn.clicked.connect(on_cancel)

        # 进度更新回调
        def on_progress(msg):
            if not dlg.is_cancelled():
                dlg.set_message(msg)

        # 部分完成回调
        def on_partial(results, source_name):
            if not dlg.is_cancelled():
                source_cn = self.source_map_en_to_cn.get(source_name, source_name)
                dlg.set_message(f"已完成 {source_cn}，继续搜索中...")

        # 搜索完成回调
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

        # 搜索出错回调
        def on_error(error_msg):
            dlg.accept()
            self.btn_search.setEnabled(True)
            self.btn_search.setText("立即搜索")
            show_message(self, QMessageBox.Icon.Critical, "错误", f"搜索失败：{error_msg}")

        # 连接信号到槽函数
        self.search_thread.progress.connect(on_progress)
        self.search_thread.partial.connect(on_partial)
        self.search_thread.finished.connect(on_finished)
        self.search_thread.error.connect(on_error)
        self.search_thread.start()


# =====================================================================
# 第十五部分：程序入口
# =====================================================================

if __name__ == "__main__":
    """
    程序入口点

    __name__ 是 Python 的内置变量：
    - 当脚本被直接运行时，__name__ 的值是 "__main__"
    - 当脚本被其他文件导入时，__name__ 的值是模块名

    所以这个 if 判断确保：只有直接运行这个脚本时才执行下面的代码
    """
    app = QApplication(sys.argv)  # 创建应用程序对象
    win = MusicDownloader()       # 创建主窗口
    win.show()                    # 显示窗口
    sys.exit(app.exec())          # 进入事件循环，等待用户操作
