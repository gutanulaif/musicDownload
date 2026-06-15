#!/bin/bash
# 打包脚本 - 自动检测并打包 ffprobe

# 自动复制系统 ffprobe 到项目目录（如果不存在）
if [ ! -f "ffprobe" ] && [ ! -f "ffprobe.exe" ]; then
    # 检测系统 ffprobe
    SYS_FFPROBE=$(command -v ffprobe 2>/dev/null)
    if [ -n "$SYS_FFPROBE" ]; then
        cp "$SYS_FFPROBE" .
        echo "✅ 已从 $SYS_FFPROBE 复制 ffprobe 到项目目录"
    else
        echo "⚠️  未找到系统 ffprobe，请手动下载放到项目目录"
    fi
fi

# 检测 ffprobe 是否存在
FFPROBE_ARG=""
if [ -f "ffprobe" ] || [ -f "ffprobe.exe" ]; then
    # Windows 下用分号，Linux/Mac 下用冒号
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
        FFPROBE_ARG="--add-binary ffprobe.exe;."
    else
        FFPROBE_ARG="--add-binary ffprobe:."
    fi
    echo "✅ 将 ffprobe 打包进程序"
else
    echo "⚠️  未检测到 ffprobe，采样率检测将依赖系统 PATH"
fi

# 打包 debug 版（控制台模式）
echo "打包 debug 版..."
gqb313/bin/pyinstaller -F -c --clean $FFPROBE_ARG musicdownload_debug.py

# 打包 release 版（窗口模式）
echo "打包 release 版..."
gqb313/bin/pyinstaller -F -w --clean --noconsole $FFPROBE_ARG musicdownload.py

echo "✅ 打包完成！输出目录: dist/"
