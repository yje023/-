#!/bin/bash
# =============================================
#   黔江区多维度精准考核评价系统 v1.1 (Linux)
#   兼容：统信 UOS / 银河麒麟 / Ubuntu / Debian
# =============================================

# 异常退出时暂停，避免终端闪退
trap 'echo ""; echo "启动异常，请检查上方错误信息。"; read -p "按回车退出..."' EXIT

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT=5000
APP_URL="http://localhost:${PORT}"

echo "=========================================="
echo "  黔江区多维度精准考核评价系统 v1.1"
echo "=========================================="
echo ""
echo "正在启动系统，请稍候..."
echo ""

# 检查端口是否已被占用（ss + netstat 双回退）
check_port() {
    if command -v ss >/dev/null 2>&1; then
        ss -tlnp 2>/dev/null | grep -q ":${PORT} "
    elif command -v netstat >/dev/null 2>&1; then
        netstat -tlnp 2>/dev/null | grep -q ":${PORT} "
    else
        return 1
    fi
}

if check_port; then
    echo "系统已在运行中 (端口 ${PORT})，无需重复启动。"
    echo ""
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "${APP_URL}" 2>/dev/null &
    fi
    trap - EXIT
    exit 0
fi

# 确定可执行文件路径
EXE_PATH="${SCRIPT_DIR}/考核评价系统"
if [ ! -f "${EXE_PATH}" ]; then
    echo "错误：未找到可执行文件「考核评价系统」"
    echo "请确保该文件与启动脚本在同一目录下。"
    echo "当前目录: ${SCRIPT_DIR}"
    read -p "按回车退出..."
    exit 1
fi

# 启动系统
chmod +x "${EXE_PATH}" 2>/dev/null || true
"${EXE_PATH}" &
SYSTEM_PID=$!

sleep 2

# 检查是否启动成功
if kill -0 ${SYSTEM_PID} 2>/dev/null; then
    echo "系统已启动 (PID: ${SYSTEM_PID})，浏览器将自动打开。"
    echo "如未自动打开，请手动访问: ${APP_URL}"

    # 打开浏览器
    if command -v xdg-open >/dev/null 2>&1; then
        sleep 1
        xdg-open "${APP_URL}" 2>/dev/null &
    elif command -v firefox >/dev/null 2>&1; then
        firefox "${APP_URL}" 2>/dev/null &
    else
        echo "提示：请手动打开浏览器访问 ${APP_URL}"
    fi
else
    echo "系统启动失败，请检查日志。"
    read -p "按回车退出..."
    exit 1
fi

echo ""
echo "=========================================="
echo "提示：关闭浏览器不会停止系统。"
echo "要停止系统，请在终端执行: kill ${SYSTEM_PID}"
echo "或者在浏览器中点击左下角「退出系统」。"
echo "=========================================="
echo ""

# 清除 trap，正常运行中不需要暂停
trap - EXIT
