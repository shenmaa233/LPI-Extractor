# 激光物理论文参数提取系统

一个基于机器学习的系统，用于自动从激光物理学领域的论文中提取关键参数。

## 功能介绍

- 从arXiv等来源爬取激光物理领域的论文
- 自动解析PDF文件并提取文本内容
- 使用DeepSeek API进行参数识别与提取
- 存储和分类激光、等离子体、电子束等不同类别的参数
- 提供Web界面用于搜索、查看和导出参数

## 技术栈

- Python 3.10+
- Flask (Web框架)
- SQLAlchemy (ORM)
- DeepSeek API (LLM处理)
- Bootstrap 5 (前端界面)

## 项目结构

- `pdf_processor`: PDF处理和文本提取
- `database`: 数据库模型和管理
- `web`: Web应用和接口
- `config`: 配置文件

## 安装说明

1. 克隆仓库

```bash
git clone https://github.com/[YOUR_USERNAME]/laser-physics-param-extractor.git
cd laser-physics-param-extractor
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 设置环境变量

复制示例配置文件并根据需要修改

```bash
cp config.example.py config.py
# 编辑config.py，添加DeepSeek API密钥等信息
```

4. 初始化数据库

```bash
python initialize_db.py
```

5. 运行Web服务

```bash
cd web
python app.py
```

服务器将在http://localhost:5000运行

## 使用方法

1. 论文搜索：输入关键词搜索并下载激光物理领域的论文
2. 参数提取：对下载的论文进行自动参数提取
3. 参数查看：按类别浏览提取出的参数
4. 数据导出：将筛选后的参数导出为CSV格式

## 系统说明

本系统用于从激光物理领域的学术论文中提取关键物理参数，主要功能包括：

1. 从arXiv等学术网站搜索和下载激光物理领域的论文
2. 从PDF论文中提取关键物理参数（激光参数、等离子体参数、电子束参数等）
3. 对提取的参数进行分类、管理和可视化
4. 提供友好的Web界面进行参数查询和分析

## 系统架构

系统由以下几个核心模块组成：

- `arxiv_crawler`: arXiv论文搜索与下载
- `pdf_processor`: PDF解析与参数提取（基于LLM）
- `database`: 数据库管理
- `web`: Web界面

## 端口冲突解决方案

系统支持两种端口冲突解决策略：

1. **自动更换端口**（默认策略）：
   - 当指定端口被占用时，系统会自动寻找下一个可用端口
   - 从原端口号开始逐一尝试，最多尝试10次
   - 找到可用端口后自动使用该端口启动应用

2. **终止占用进程**：
   - 通过设置环境变量 `PORT_CONFLICT_STRATEGY=kill_process` 启用
   - 系统会识别占用指定端口的进程并尝试终止它
   - 先尝试正常终止，等待3秒，如果失败则强制终止
   - 系统自动避免终止自己的进程

设置方式：
- 在`.env`文件中添加 `PORT_CONFLICT_STRATEGY=auto_change`（默认）或 `PORT_CONFLICT_STRATEGY=kill_process`
- 或者在启动应用前设置环境变量：`export PORT_CONFLICT_STRATEGY=kill_process`
- 或使用启动脚本，其中已包含相应设置

如果遇到顽固的端口占用问题，可以使用强制模式关闭所有Python进程：
```bash
./start.sh --force-kill
```

## 使用方法

1. **搜索论文**：使用搜索页面从arXiv搜索相关论文
2. **上传论文**：手动上传论文PDF文件
3. **参数提取**：对论文进行参数提取
4. **参数查询**：浏览和查询已提取的参数

## 开发指南

### 代码结构

- `run.py`：主程序入口
- `config.py`：配置管理
- `arxiv_crawler/`：论文爬虫模块
- `pdf_processor/`：PDF处理模块
- `database/`：数据库模块
- `web/`：Web界面
  - `web/app.py`：Flask应用
  - `web/templates/`：HTML模板
  - `web/static/`：静态资源

### 添加新参数类型

如需添加新的参数类型，需要：

1. 在`pdf_processor/parameter_types.py`中定义新参数类型
2. 在`pdf_processor/llm_prompts.py`中更新提取指令
3. 在`web/templates/parameters.html`中添加对应的UI元素

## 项目结构

```
laser-parameter-extraction/
│
├── arxiv_crawler/
│   ├── arxiv_crawler_enhanced.py  # arXiv 论文爬虫
│
├── pdf_processor/
│   ├── pdf_extractor.py           # PDF 文本提取
│   ├── llm_processor.py           # LLM 参数提取
│   ├── prompt_engineering.py      # LLM 提示工程
│
├── database/
│   ├── models.py                  # 数据库模型
│   ├── db_utils.py                # 数据库工具函数
│
├── web/
│   ├── app.py                     # Flask Web 应用
│   ├── templates/                 # HTML 模板
│   │   ├── index.html
│   │   ├── papers.html
│   │   ├── parameters.html
│   │   └── search.html
│   └── static/                    # CSS、JS 文件
│
├── config.py                      # 配置文件
├── requirements.txt               # 依赖包
└── run.py                         # 主程序入口
```

## 功能特点

1. **论文自动爬取**：利用 arXiv API 爬取激光物理领域相关论文
2. **智能参数提取**：使用 DeepSeek API 对论文进行智能解析，提取激光参数和实验数据
3. **数据库存储**：将提取的参数和原始论文元数据存入数据库
4. **Web 可视化界面**：提供直观的 Web 界面进行论文检索和参数查看
5. **完整处理流程**：从论文爬取到数据展示的全流程自动化处理

## 详细实现步骤

### 1. 论文爬取模块

基于 `arxiv_crawler_enhanced.py`