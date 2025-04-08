import os
from dotenv import load_dotenv

# 加载.env文件中的环境变量
load_dotenv()

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# API密钥配置 - 替换为您的实际密钥
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', 'your_deepseek_api_key_here')

# 数据库配置
DB_TYPE = os.environ.get('DB_TYPE', 'sqlite')  # 支持 sqlite, postgresql, mysql
DB_NAME = os.environ.get('DB_NAME', 'laser_papers.db')
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_USER = os.environ.get('DB_USER', '')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')

# 根据数据库类型构建连接URL
if DB_TYPE == 'sqlite':
    DATABASE_URL = f'sqlite:///{os.path.join(BASE_DIR, DB_NAME)}'
elif DB_TYPE == 'postgresql':
    DATABASE_URL = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
elif DB_TYPE == 'mysql':
    DATABASE_URL = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
else:
    DATABASE_URL = f'sqlite:///{os.path.join(BASE_DIR, "laser_papers.db")}'

# 文件存储配置
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(BASE_DIR, 'paper_library'))
MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 50 * 1024 * 1024))  # 默认50MB

# 应用配置
SECRET_KEY = os.environ.get('SECRET_KEY', 'change_this_to_a_strong_random_key_in_production')
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'

# Web服务器配置
HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', 5000))

# 端口冲突解决策略
PORT_CONFLICT_STRATEGY = os.environ.get('PORT_CONFLICT_STRATEGY', 'auto_change')  # 'auto_change' or 'kill_process'

# LLM模型配置
LLM_MODEL = os.environ.get('LLM_MODEL', 'deepseek-chat')
LLM_API_BASE = os.environ.get('LLM_API_BASE', 'https://api.deepseek.com')

# arXiv API配置
ARXIV_QUERY_DELAY = float(os.environ.get('ARXIV_QUERY_DELAY', 3.0))  # 请求之间的延迟（秒）
ARXIV_MAX_RESULTS = int(os.environ.get('ARXIV_MAX_RESULTS', 100))  # 每次搜索最大结果数

# 确保上传文件夹存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 开发环境配置
class DevelopmentConfig:
    DEBUG = True
    TESTING = False
    DATABASE_URL = DATABASE_URL
    SECRET_KEY = SECRET_KEY
    UPLOAD_FOLDER = UPLOAD_FOLDER
    MAX_CONTENT_LENGTH = MAX_CONTENT_LENGTH
    DEEPSEEK_API_KEY = DEEPSEEK_API_KEY

# 生产环境配置
class ProductionConfig:
    DEBUG = False
    TESTING = False
    DATABASE_URL = DATABASE_URL
    SECRET_KEY = SECRET_KEY
    UPLOAD_FOLDER = UPLOAD_FOLDER
    MAX_CONTENT_LENGTH = MAX_CONTENT_LENGTH
    DEEPSEEK_API_KEY = DEEPSEEK_API_KEY

# 测试环境配置
class TestingConfig:
    DEBUG = False
    TESTING = True
    DATABASE_URL = f'sqlite:///{os.path.join(BASE_DIR, "test.db")}'
    SECRET_KEY = 'test_secret_key'
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'test_uploads')
    MAX_CONTENT_LENGTH = MAX_CONTENT_LENGTH
    DEEPSEEK_API_KEY = DEEPSEEK_API_KEY

# 根据环境选择配置
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

# 默认配置
current_config = config[os.environ.get('FLASK_ENV', 'default')]

# 创建日志目录
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# 日志配置
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
LOG_FILE = os.path.join(LOG_DIR, 'app.log')

"""
使用说明:
1. 复制此文件为 config.py
2. 修改 DEEPSEEK_API_KEY 为您的实际API密钥
3. 根据需要修改数据库配置
4. 调整其他配置项适应您的环境

或者，您可以设置环境变量(推荐用于生产环境):
- DEEPSEEK_API_KEY: DeepSeek API密钥
- DB_TYPE: 数据库类型 (sqlite, postgresql, mysql)
- DB_NAME: 数据库名称
- DB_HOST: 数据库主机地址
- DB_PORT: 数据库端口
- DB_USER: 数据库用户名
- DB_PASSWORD: 数据库密码
- SECRET_KEY: Flask应用密钥
- DEBUG: 是否开启调试模式
- FLASK_ENV: 运行环境 (development, production, testing)
""" 