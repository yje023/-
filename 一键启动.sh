#!/bin/bash
# =============================================
#   考核评价系统 - 一键启动
#   右键 → 在终端中运行
#   兼容：统信 UOS / 银河麒麟 / Ubuntu / Debian
# =============================================

# 异常退出时暂停，避免终端闪退
trap 'echo ""; echo "启动异常，请检查上方错误信息。"; read -p "按回车退出..."' EXIT

# 获取脚本所在目录（项目根目录）
DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="${DIR}/frontend"
DIST_DIR="${FRONTEND_DIR}/dist"

# 提权命令（UOS 优先用 pkexec 弹图形密码框）
if command -v pkexec >/dev/null 2>&1; then
    ELEVATE="pkexec"
    ELEVATE_SH="pkexec bash -c"
else
    ELEVATE="sudo"
    ELEVATE_SH="sudo bash -c"
fi

echo "=========================================="
echo "  黔江区多维度精准考核评价系统 v1.1"
echo "  正在准备启动..."
echo "=========================================="
echo ""

# ---- 1. 检测/安装 Python ----
echo "[1/5] 检测 Python..."
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3.9 python3.8 python3; do
    if command -v $cmd >/dev/null 2>&1; then
        VER=$($cmd -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
        if [ -n "$VER" ] && [ "$VER" -ge 7 ] 2>/dev/null; then
            PYTHON=$cmd
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "  未找到 Python 3.7+，正在安装..."
    if command -v apt >/dev/null 2>&1; then
        echo "  即将弹出授权对话框，请输入管理员密码..."
        $ELEVATE_SH 'apt update && apt install python3 python3-pip -y'
    elif command -v yum >/dev/null 2>&1; then
        $ELEVATE yum install python38 python38-pip -y
    else
        echo "  错误：无法自动安装 Python，请手动安装 Python 3.8+"
        read -p "按回车退出..."
        exit 1
    fi
    PYTHON="python3"
fi
echo "  Python: $($PYTHON --version 2>/dev/null || echo 'python3')"

# ---- 2. 安装 Python 依赖 ----
echo "[2/5] 安装 Python 依赖..."
$PYTHON -m pip install --user flask flask-cors flask-jwt-extended flask-sqlalchemy werkzeug openpyxl xlrd 2>&1 | tail -3
if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo "  警告：pip install --user 失败，尝试提权安装..."
    $ELEVATE $PYTHON -m pip install flask flask-cors flask-jwt-extended flask-sqlalchemy werkzeug openpyxl xlrd 2>&1 | tail -3
fi
echo "  完成"

# 修复 UOS 系统 watchdog 版本过旧导致 Flask reloader 无法启动
$PYTHON -m pip install --user --upgrade watchdog 2>&1 | tail -1

# ---- 3. 检测/安装 Node.js 并构建前端 ----
echo "[3/5] 构建前端..."
NEED_BUILD=false
if [ ! -d "${DIST_DIR}" ] || [ ! -f "${DIST_DIR}/index.html" ]; then
    NEED_BUILD=true
fi

if [ "$NEED_BUILD" = true ]; then
    NODE_CMD=""
    for cmd in node nodejs node20 node18 node16; do
        if command -v $cmd >/dev/null 2>&1; then
            NODE_CMD=$cmd
            break
        fi
    done

    if [ -z "$NODE_CMD" ]; then
        echo "  未找到 Node.js，正在安装..."
        if command -v apt >/dev/null 2>&1; then
            $ELEVATE_SH 'apt update && apt install nodejs npm -y'
        elif command -v yum >/dev/null 2>&1; then
            $ELEVATE yum install nodejs npm -y
        fi
        # UOS/Debian 安装后命令可能是 nodejs 而非 node
        if command -v nodejs >/dev/null 2>&1; then
            NODE_CMD="nodejs"
        elif command -v node >/dev/null 2>&1; then
            NODE_CMD="node"
        else
            echo "  错误：Node.js 安装失败，请手动安装"
            read -p "按回车退出..."
            exit 1
        fi
    fi

    echo "  Node: $($NODE_CMD --version 2>/dev/null || echo 'unknown')"

    cd "${FRONTEND_DIR}"
    if [ ! -d "node_modules" ]; then
        echo "  安装前端依赖（首次需要几分钟）..."
        npm install
        if [ $? -ne 0 ]; then
            echo "  错误：npm install 失败"
            cd "${DIR}"
            read -p "按回车退出..."
            exit 1
        fi
    fi
    echo "  构建前端..."
    npm run build
    if [ $? -ne 0 ]; then
        echo "  错误：npm run build 失败"
        cd "${DIR}"
        read -p "按回车退出..."
        exit 1
    fi
    echo "  前端构建完成"
else
    echo "  前端已构建，跳过"
fi

# 回到项目根目录
cd "${DIR}"

# ---- 4. 检查端口 ----
echo "[4/5] 检查端口 5000..."

# 第一步：检测端口是否被占用（ss -tln 不需要 root）
PORT_IN_USE=false
if command -v ss >/dev/null 2>&1; then
    ss -tln 2>/dev/null | grep -q ":5000 " && PORT_IN_USE=true
elif command -v netstat >/dev/null 2>&1; then
    netstat -tln 2>/dev/null | grep -q ":5000 " && PORT_IN_USE=true
fi

if [ "$PORT_IN_USE" = true ]; then
    echo "  端口 5000 已被占用，正在释放..."

    # 尝试获取 PID
    PID=""
    if command -v ss >/dev/null 2>&1; then
        PID=$(ss -tlnp 2>/dev/null | grep ":5000 " | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -1)
    fi
    if [ -z "$PID" ] && command -v netstat >/dev/null 2>&1; then
        PID=$(netstat -tlnp 2>/dev/null | grep ":5000 " | awk '{print $NF}' | cut -d/ -f1 | head -1)
    fi

    # 尝试杀掉进程
    if [ -n "$PID" ]; then
        echo "  找到进程 PID: $PID，正在关闭..."
        kill $PID 2>/dev/null || $ELEVATE kill $PID 2>/dev/null
        sleep 1
        kill -9 $PID 2>/dev/null || $ELEVATE kill -9 $PID 2>/dev/null
        sleep 1
    fi

    # 用 fuser 兜底（需要 root 权限时用 sudo）
    if command -v fuser >/dev/null 2>&1; then
        fuser -k 5000/tcp 2>/dev/null || $ELEVATE fuser -k 5000/tcp 2>/dev/null
        sleep 1
    fi

    # 再次检查是否释放成功
    STILL_IN_USE=false
    if command -v ss >/dev/null 2>&1; then
        ss -tln 2>/dev/null | grep -q ":5000 " && STILL_IN_USE=true
    elif command -v netstat >/dev/null 2>&1; then
        netstat -tln 2>/dev/null | grep -q ":5000 " && STILL_IN_USE=true
    fi

    if [ "$STILL_IN_USE" = true ]; then
        echo "  警告：无法释放端口 5000，请重启系统后重试"
        echo "  或手动执行: fuser -k 5000/tcp"
    else
        echo "  端口已释放"
    fi
else
    echo "  端口空闲"
fi
echo "  完成"

# ---- 5. 启动 ----
echo "[5/5] 启动系统..."
cd "${DIR}"

echo ""
read -p "按回车键启动系统（确认上方进度无误后按回车）..."

# 清除 trap，正常启动后不需要暂停
trap - EXIT

# 后台启动后端
$PYTHON backend/app.py &
FLASK_PID=$!

# 等待 Flask 就绪（最多 15 秒）
echo "正在等待系统启动..."
WAITED=0
while [ $WAITED -lt 15 ]; do
    sleep 1
    WAITED=$((WAITED + 1))
    if command -v ss >/dev/null 2>&1; then
        if ss -tlnp 2>/dev/null | grep -q ":5000 "; then
            break
        fi
    elif command -v netstat >/dev/null 2>&1; then
        if netstat -tlnp 2>/dev/null | grep -q ":5000 "; then
            break
        fi
    fi
    echo "  ... ${WAITED}s"
done

# 检查是否启动成功
if kill -0 ${FLASK_PID} 2>/dev/null; then
    echo ""
    echo "系统已启动 (PID: ${FLASK_PID})"
    echo ""

    # 打开浏览器
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "http://localhost:5000" 2>/dev/null &
    elif command -v firefox >/dev/null 2>&1; then
        firefox "http://localhost:5000" 2>/dev/null &
    else
        echo "  提示：请手动打开浏览器访问 http://localhost:5000"
    fi

    echo ""
    echo "=========================================="
    echo "  系统已启动！"
    echo "  请打开浏览器访问: http://localhost:5000"
    echo "  关闭此终端窗口将停止系统。"
    echo "=========================================="
    echo ""

    # 等待 Flask 进程，保持脚本不退出
    wait ${FLASK_PID}
else
    echo ""
    echo "系统启动失败，请检查上方错误信息。"
    read -p "按回车退出..."
    exit 1
fi
