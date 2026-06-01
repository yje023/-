#!/bin/bash
# =============================================
#   考核评价系统 Linux 构建脚本
#   适用于：银河麒麟 V10 SP1
# =============================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=========================================="
echo "  考核评价系统 - Linux 构建"
echo "  目标平台：银河麒麟 V10 SP1"
echo "=========================================="
echo ""

# ---- 1. 检查 Python ----
echo -e "${YELLOW}[1/5] 检查 Python...${NC}"
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3.9 python3.8 python3; do
    if command -v $cmd &>/dev/null; then
        VER=$($cmd --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
        MAJOR=$(echo $VER | cut -d. -f1)
        MINOR=$(echo $VER | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 8 ]; then
            PYTHON=$cmd
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "${RED}错误：未找到 Python >= 3.8。${NC}"
    echo "请先安装 Python 3.8+："
    echo "  sudo yum install python38 python38-pip   # Kylin/CentOS"
    echo "  sudo apt install python3 python3-pip      # Debian/Ubuntu"
    exit 1
fi
echo -e "${GREEN}  使用: $PYTHON ($($PYTHON --version))${NC}"

# ---- 2. 安装 Python 依赖 ----
echo ""
echo -e "${YELLOW}[2/5] 安装 Python 依赖...${NC}"
REQ_FILE="${PROJECT_DIR}/requirements.txt"
if [ -f "${SCRIPT_DIR}/requirements.txt" ]; then
    REQ_FILE="${SCRIPT_DIR}/requirements.txt"
fi
$PYTHON -m pip install -r "${REQ_FILE}" --quiet 2>&1 | tail -1
$PYTHON -m pip install pyinstaller --quiet 2>&1 | tail -1
echo -e "${GREEN}  完成${NC}"

# ---- 3. 检查 Node.js 并构建前端 ----
echo ""
echo -e "${YELLOW}[3/5] 构建前端...${NC}"
NODE_CMD=""
for cmd in node20 node18 node16 node; do
    if command -v $cmd &>/dev/null; then
        NODE_CMD=$cmd
        break
    fi
done

if [ -n "$NODE_CMD" ]; then
    echo -e "${GREEN}  使用 Node: $($NODE_CMD --version)${NC}"
    cd "${PROJECT_DIR}/frontend"

    # 检查 node_modules
    if [ ! -d "node_modules" ]; then
        echo "  安装前端依赖..."
        npm install --silent 2>&1 | tail -3
    fi

    echo "  构建生产版本..."
    npm run build 2>&1 | tail -5
    echo -e "${GREEN}  前端构建完成${NC}"
else
    echo -e "${YELLOW}  警告：未找到 Node.js，跳过前端构建。${NC}"
    echo "  请确保 ${PROJECT_DIR}/frontend/dist 目录有已构建的前端文件。"
    echo "  安装 Node.js:"
    echo "    sudo yum install nodejs npm   # Kylin/CentOS"
    echo "    sudo apt install nodejs npm   # Debian/Ubuntu"

    if [ ! -d "${PROJECT_DIR}/frontend/dist" ]; then
        echo -e "${RED}  错误：frontend/dist 目录不存在，无法继续。${NC}"
        exit 1
    fi
fi

# ---- 4. 运行 PyInstaller 打包 ----
echo ""
echo -e "${YELLOW}[4/5] PyInstaller 打包...${NC}"
cd "${PROJECT_DIR}"

# 清理旧构建
rm -rf build/temp_linux dist_linux 2>/dev/null || true

$PYTHON -m PyInstaller \
    "${SCRIPT_DIR}/build_linux.spec" \
    --distpath "${PROJECT_DIR}/dist_linux" \
    --workpath "${PROJECT_DIR}/build/temp_linux" \
    --clean \
    2>&1 | tail -10

echo -e "${GREEN}  PyInstaller 打包完成${NC}"

# ---- 5. 整理部署目录 ----
echo ""
echo -e "${YELLOW}[5/5] 整理部署目录...${NC}"

DEPLOY_DIR="${PROJECT_DIR}/dist_linux/考核评价系统_linux"
mkdir -p "${DEPLOY_DIR}"

# 复制可执行文件
if [ -f "${PROJECT_DIR}/dist_linux/考核评价系统" ]; then
    cp "${PROJECT_DIR}/dist_linux/考核评价系统" "${DEPLOY_DIR}/"
    chmod +x "${DEPLOY_DIR}/考核评价系统"
    echo "  已复制: 考核评价系统"
fi

# 复制启动脚本
cp "${SCRIPT_DIR}/启动系统.sh" "${DEPLOY_DIR}/"
chmod +x "${DEPLOY_DIR}/启动系统.sh"
echo "  已复制: 启动系统.sh"

# 复制桌面文件
if [ -f "${SCRIPT_DIR}/考核评价系统.desktop" ]; then
    cp "${SCRIPT_DIR}/考核评价系统.desktop" "${DEPLOY_DIR}/"
    echo "  已复制: 考核评价系统.desktop"
fi

# 复制部署说明
if [ -f "${SCRIPT_DIR}/README.md" ]; then
    cp "${SCRIPT_DIR}/README.md" "${DEPLOY_DIR}/"
    echo "  已复制: README.md"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}  构建完成！${NC}"
echo ""
echo "  部署目录: ${DEPLOY_DIR}"
echo ""
echo "  部署到目标机器后执行:"
echo "    cd 考核评价系统_linux"
echo "    chmod +x 启动系统.sh"
echo "    ./启动系统.sh"
echo "=========================================="
