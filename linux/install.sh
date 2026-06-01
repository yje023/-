#!/bin/bash
# =============================================
#   考核评价系统 - 安装脚本（目标机器上执行）
#   适用于：银河麒麟 V10 SP1
# =============================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="/opt/assessment-system"

echo "=========================================="
echo "  考核评价系统 v1.1 - 安装"
echo "=========================================="
echo ""

if [ "$(id -u)" -ne 0 ]; then
    echo "请使用 sudo 运行安装脚本："
    echo "  sudo bash install.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 1. 创建安装目录
echo -e "${YELLOW}[1/4] 创建安装目录...${NC}"
mkdir -p "${INSTALL_DIR}"
echo -e "${GREEN}  ${INSTALL_DIR}${NC}"

# 2. 复制文件
echo -e "${YELLOW}[2/4] 复制程序文件...${NC}"
cp -f "${SCRIPT_DIR}/考核评价系统" "${INSTALL_DIR}/" 2>/dev/null || true
cp -f "${SCRIPT_DIR}/启动系统.sh" "${INSTALL_DIR}/"
chmod +x "${INSTALL_DIR}/启动系统.sh"
chmod +x "${INSTALL_DIR}/考核评价系统" 2>/dev/null || true
echo -e "${GREEN}  完成${NC}"

# 3. 安装桌面快捷方式
echo -e "${YELLOW}[3/4] 安装桌面快捷方式...${NC}"
DESKTOP_FILE="${SCRIPT_DIR}/考核评价系统.desktop"
if [ -f "${DESKTOP_FILE}" ]; then
    # 更新路径
    sed -i "s|Exec=.*|Exec=bash ${INSTALL_DIR}/启动系统.sh|" "${DESKTOP_FILE}"
    sed -i "s|Path=.*|Path=${INSTALL_DIR}|" "${DESKTOP_FILE}"

    # 安装到系统
    cp -f "${DESKTOP_FILE}" "/usr/share/applications/考核评价系统.desktop"

    # 也复制到用户桌面
    for USER_HOME in /home/*; do
        if [ -d "${USER_HOME}/Desktop" ]; then
            cp -f "${DESKTOP_FILE}" "${USER_HOME}/Desktop/"
            chown $(stat -c '%U' "${USER_HOME}") "${USER_HOME}/Desktop/考核评价系统.desktop" 2>/dev/null || true
        fi
    done
    echo -e "${GREEN}  完成${NC}"
else
    echo -e "${YELLOW}  跳过（未找到 .desktop 文件）${NC}"
fi

# 4. 防火墙放行端口
echo -e "${YELLOW}[4/4] 配置防火墙...${NC}"
if command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-port=5000/tcp 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
    echo -e "${GREEN}  已放行端口 5000${NC}"
elif command -v ufw &>/dev/null; then
    ufw allow 5000/tcp 2>/dev/null || true
    echo -e "${GREEN}  已放行端口 5000${NC}"
else
    echo -e "${YELLOW}  未检测到防火墙，跳过。如需远程访问请手动放行端口 5000。${NC}"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}  安装完成！${NC}"
echo ""
echo "  启动方式："
echo "    方式1：在程序菜单中搜索「考核评价系统」"
echo "    方式2：终端执行 ${INSTALL_DIR}/启动系统.sh"
echo "    方式3：双击桌面快捷方式"
echo ""
echo "  访问地址：http://localhost:5000"
echo "=========================================="
