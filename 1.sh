#!/bin/bash

# ===== 1. 安装依赖 =====
echo ">>> 安装依赖中..."

# Debian / Ubuntu
if command -v apt >/dev/null 2>&1; then
    sudo apt update
    sudo apt install -y curl unzip nodejs npm
# CentOS / RHEL
elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y curl unzip nodejs npm
else
    echo "不支持的系统，请手动安装 curl / unzip / nodejs"
    exit 1
fi

# ===== 2. 使用 curl 下载项目 ZIP =====
echo ">>> 下载项目 ZIP..."
curl -L https://github.com/jfjdjdhsj/jb/archive/refs/heads/main.zip -o jb.zip

# ===== 3. 解压 ZIP =====
echo ">>> 解压..."
unzip -o jb.zip

# 解压后的目录名称通常是 jb-main
cd jb-main || exit

# ===== 4. 安装 npm 依赖 =====
echo ">>> 安装 npm 依赖..."
npm install

# ===== 5. 后台运行 =====
echo ">>> 后台运行项目..."
nohup npm start > app.log 2>&1 &

echo "部署完成！日志在 app.log"
echo "后台进程 PID: $!"
