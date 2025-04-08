import os
import sys
import logging
import socket
import signal
import psutil
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 设置日志
from config import LOG_DIR
log_file = os.path.join(LOG_DIR, 'app.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 导入配置
from config import current_config, HOST, PORT, DEBUG, DEEPSEEK_API_KEY

def check_port_in_use(port, host='0.0.0.0'):
    """
    检查端口是否被占用
    
    Args:
        port: 要检查的端口号
        host: 主机地址，默认为0.0.0.0
        
    Returns:
        bool: 如果端口被占用返回True，否则返回False
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, port))
        return False
    except socket.error:
        return True
    finally:
        s.close()

def find_process_by_port(port):
    """
    查找占用指定端口的进程
    
    Args:
        port: 端口号
        
    Returns:
        process: 如果找到进程则返回进程对象，否则返回None
    """
    # 使用推荐的net_connections代替已弃用的connections
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            for conn in psutil.net_connections(kind='inet'):
                if conn.laddr.port == port and conn.pid == proc.pid:
                    return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return None

def is_same_python_app(process):
    """
    判断给定进程是否是当前Python应用的一部分
    
    Args:
        process: psutil.Process对象
        
    Returns:
        bool: 如果是当前应用的一部分返回True，否则返回False
    """
    # 当前进程及其父进程ID
    current_pid = os.getpid()
    parent_pid = os.getppid()
    
    # 检查是否是当前进程
    if process.pid == current_pid:
        return True
    
    # 检查是否是父进程
    if process.pid == parent_pid:
        return True
    
    # 检查是否有相同的Python解释器路径和相似的命令行参数
    try:
        # 获取当前进程的命令行和可执行文件路径
        current_cmdline = " ".join(sys.argv)
        current_exe = sys.executable
        
        # 获取目标进程的命令行和可执行文件路径
        proc_cmdline = " ".join(process.cmdline())
        proc_exe = process.exe()
        
        # 如果是同一个Python解释器且命令行中包含相同的脚本名
        if proc_exe == current_exe and "run.py" in proc_cmdline:
            return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    
    return False

def kill_process_on_port(port):
    """
    终止占用指定端口的进程
    
    Args:
        port: 端口号
        
    Returns:
        bool: 如果成功终止进程返回True，否则返回False
    """
    process = find_process_by_port(port)
    if process:
        try:
            logger.info(f"正在终止占用端口 {port} 的进程 (PID: {process.pid}, 名称: {process.name()})")
            process.terminate()
            process.wait(timeout=3)  # 等待进程终止
            logger.info(f"进程已成功终止")
            return True
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            logger.warning(f"进程终止超时，尝试强制终止")
            try:
                process.kill()
                return True
            except psutil.NoSuchProcess:
                return True
    logger.warning(f"未找到占用端口 {port} 的进程")
    return False

def get_available_port(start_port, max_attempts=10):
    """
    从指定端口开始查找可用端口
    
    Args:
        start_port: 起始端口号
        max_attempts: 最大尝试次数
        
    Returns:
        int: 可用的端口号，如果没有找到则返回None
    """
    port = start_port
    for _ in range(max_attempts):
        if not check_port_in_use(port):
            return port
        port += 1
    return None

def create_project_structure():
    """
    确保项目目录结构存在
    """
    # 创建目录结构
    dirs = [
        'paper_library',
        'arxiv_crawler',
        'pdf_processor',
        'database',
        'web/templates',
        'web/static/css',
        'web/static/js',
        'web/static/img',
    ]
    
    for directory in dirs:
        os.makedirs(directory, exist_ok=True)
    
    logger.info("项目目录结构创建完成")

def check_dependencies():
    """
    检查关键依赖是否安装
    """
    try:
        import flask
        import sqlalchemy
        import openai
        import requests
        import PyPDF2
        import pandas
        logger.info("关键依赖检查通过")
        return True
    except ImportError as e:
        logger.error(f"缺少关键依赖: {str(e)}")
        logger.error("请运行 'pip install -r requirements.txt' 安装所有依赖")
        return False

def initialize_database():
    """
    初始化数据库
    """
    try:
        from database.models import init_db, get_engine
        engine = get_engine(current_config.DATABASE_URL)
        init_db(engine)
        logger.info("数据库初始化完成")
        return True
    except Exception as e:
        logger.error(f"数据库初始化失败: {str(e)}")
        return False

def check_arxiv_crawler():
    """
    检查arXiv爬虫是否存在
    """
    crawler_path = os.path.join('arxiv_crawler', 'arxiv_crawler_enhanced.py')
    if not os.path.exists(crawler_path):
        logger.warning(f"未找到arXiv爬虫脚本: {crawler_path}")
        return False
    return True

def check_api_key():
    """
    检查API密钥是否设置
    """
    if not DEEPSEEK_API_KEY:
        logger.warning("未设置DEEPSEEK_API_KEY环境变量，参数提取功能将不可用")
        return False
    return True

def run_app():
    """
    运行Flask应用
    """
    try:
        from web.app import app
        
        # 检查端口是否被占用
        target_port = PORT
        if check_port_in_use(target_port, HOST):
            logger.warning(f"端口 {target_port} 已被占用")
            
            # 策略1: 尝试终止占用端口的进程
            kill_option = os.environ.get('PORT_CONFLICT_STRATEGY', 'auto_change')
            
            if kill_option == 'kill_process':
                logger.info(f"尝试终止占用端口 {target_port} 的进程")
                process = find_process_by_port(target_port)
                
                # 判断是否是当前应用的一部分
                if process and not is_same_python_app(process):
                    logger.info(f"找到非本应用进程: PID={process.pid}, 名称={process.name()}")
                    if kill_process_on_port(target_port):
                        logger.info(f"已终止占用端口 {target_port} 的进程，继续使用此端口")
                    else:
                        logger.error(f"无法终止占用端口 {target_port} 的进程")
                        # 端口冲突且无法终止时自动换端口
                        new_port = get_available_port(target_port + 1)
                        if new_port:
                            logger.info(f"自动切换到可用端口 {new_port}")
                            target_port = new_port
                        else:
                            logger.error(f"无法找到可用端口，应用启动失败")
                            return False
                else:
                    # 如果是当前应用占用端口或未找到进程，改用自动切换端口策略
                    if process:
                        logger.warning(f"占用端口的是本应用进程 (PID={process.pid})，避免终止自己，改用自动切换端口策略")
                    else:
                        logger.warning(f"未找到占用端口的进程，改用自动切换端口策略")
                    
                    new_port = get_available_port(target_port + 1)
                    if new_port:
                        logger.info(f"自动切换到可用端口 {new_port}")
                        target_port = new_port
                    else:
                        logger.error(f"无法找到可用端口，应用启动失败")
                        return False
            
            # 策略2: 自动切换到其他可用端口
            else:  # auto_change 是默认策略
                new_port = get_available_port(target_port + 1)
                if new_port:
                    logger.info(f"自动切换到可用端口 {new_port}")
                    target_port = new_port
                else:
                    logger.error(f"无法找到可用端口，应用启动失败")
                    return False
        
        logger.info(f"启动Web应用，访问 http://{HOST}:{target_port}")
        
        if DEBUG:
            # 开发环境下直接使用Flask内置服务器
            app.run(host=HOST, port=target_port, debug=DEBUG)
        else:
            # 生产环境使用gunicorn
            try:
                import gunicorn
                logger.info("使用gunicorn启动应用")
                from gunicorn.app.base import BaseApplication
                
                class Application(BaseApplication):
                    def __init__(self, app, options=None):
                        self.options = options or {}
                        self.application = app
                        super().__init__()
                    
                    def load_config(self):
                        for key, value in self.options.items():
                            if key in self.cfg.settings and value is not None:
                                self.cfg.set(key.lower(), value)
                    
                    def load(self):
                        return self.application
                
                gunicorn_options = {
                    'bind': f"{HOST}:{target_port}",
                    'workers': 4,
                    'accesslog': os.path.join(LOG_DIR, 'access.log'),
                    'errorlog': os.path.join(LOG_DIR, 'error.log'),
                    'loglevel': 'info',
                }
                
                Application(app, gunicorn_options).run()
                
            except ImportError:
                logger.warning("未找到gunicorn，使用Flask内置服务器")
                app.run(host=HOST, port=target_port, debug=False)
                
    except Exception as e:
        logger.error(f"启动应用失败: {str(e)}")
        return False
    
    return True

def main():
    """
    主函数，负责整个应用的初始化和启动
    """
    logger.info("开始启动激光物理论文参数提取系统...")
    
    # 检查项目结构
    create_project_structure()
    
    # 检查依赖
    if not check_dependencies():
        logger.error("依赖检查失败，终止启动")
        return False
    
    # 检查arXiv爬虫
    if not check_arxiv_crawler():
        logger.warning("arXiv爬虫检查失败，论文爬取功能将不可用")
    
    # 检查API密钥
    if not check_api_key():
        logger.warning("API密钥检查失败，参数提取功能将不可用")
    
    # 初始化数据库
    if not initialize_database():
        logger.error("数据库初始化失败，终止启动")
        return False
    
    # 运行应用
    run_app()
    
    return True

if __name__ == '__main__':
    main() 