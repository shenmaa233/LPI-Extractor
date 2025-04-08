#!/bin/bash

# 默认设置
export PORT_CONFLICT_STRATEGY=${PORT_CONFLICT_STRATEGY:-auto_change}

# 处理命令行参数
for arg in "$@"; do
    case $arg in
        --kill-process)
            export PORT_CONFLICT_STRATEGY=kill_process
            shift
            ;;
        --auto-change)
            export PORT_CONFLICT_STRATEGY=auto_change
            shift
            ;;
        --force-kill)
            echo "警告: 正在强制关闭所有Python进程..."
            pkill -9 python
            sleep 1
            echo "所有Python进程已终止"
            shift
            ;;
        --install)
            echo "安装依赖..."
            pip install -r requirements.txt
            shift
            ;;
        --help)
            echo "使用方法: ./start.sh [选项]"
            echo "选项:"
            echo "  --auto-change    自动更换端口策略（默认）"
            echo "  --kill-process   终止占用进程策略"
            echo "  --force-kill     强制终止所有Python进程"
            echo "  --install        安装依赖"
            echo "  --help           显示此帮助信息"
            exit 0
            ;;
    esac
done

# 显示当前设置
echo "启动配置："
echo "- 端口冲突策略: $PORT_CONFLICT_STRATEGY"

# 运行应用
echo "启动应用..."
python run.py 