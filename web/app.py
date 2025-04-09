import os
import sys
import json
import logging
import csv
import io
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, flash
from werkzeug.utils import secure_filename
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # 非交互式后端
import matplotlib.pyplot as plt
from datetime import datetime
import subprocess
import threading

# 添加父目录到路径，以便导入其他模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入项目模块
from database.db_utils import DatabaseManager
from pdf_processor.pdf_extractor import extract_text_from_pdf, batch_process_pdfs
from pdf_processor.llm_processor import LLMProcessor

# 导入项目配置
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DEEPSEEK_API_KEY, UPLOAD_FOLDER, MAX_CONTENT_LENGTH, SECRET_KEY

# 将日志同时输出到控制台和文件
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'app.log')

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 创建Flask应用
app = Flask(__name__)
app.secret_key = SECRET_KEY

# 配置
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH  # 限制上传文件大小为50MB
app.config['DEEPSEEK_API_KEY'] = DEEPSEEK_API_KEY

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 初始化数据库管理器
db_manager = DatabaseManager()

# 初始化LLM处理器
try:
    llm_processor = LLMProcessor(api_key=app.config['DEEPSEEK_API_KEY'])
    app.config['LLM_AVAILABLE'] = True
except Exception as e:
    logger.warning(f"无法初始化LLM处理器: {str(e)}")
    app.config['LLM_AVAILABLE'] = False

# 添加模板全局函数
@app.context_processor
def utility_processor():
    def get_processing_records(paper_id, process_type, status=None):
        with db_manager.get_session() as session:
            from database.models import ProcessingRecord
            query = session.query(ProcessingRecord).filter_by(
                paper_id=paper_id, 
                process_type=process_type
            )
            if status:
                query = query.filter_by(status=status)
            return query.all()
    
    return dict(get_processing_records=get_processing_records)

# 首页路由
@app.route('/')
def index():
    """
    首页，显示系统概览
    """
    # 获取论文和参数统计
    paper_count = 0
    parameter_count = 0
    
    with db_manager.get_session() as session:
        from database.models import Paper, LaserParameter
        paper_count = session.query(Paper).count()
        parameter_count = session.query(LaserParameter).count()
    
    # 获取参数统计
    parameter_stats = db_manager.get_parameter_statistics() if parameter_count > 0 else {}
    
    # 最近处理的论文
    recent_papers = db_manager.get_papers(limit=5)
    
    return render_template('index.html', 
                          paper_count=paper_count,
                          parameter_count=parameter_count,
                          parameter_stats=parameter_stats,
                          recent_papers=recent_papers,
                          llm_available=app.config['LLM_AVAILABLE'])

# 论文搜索和爬取路由
@app.route('/search', methods=['GET', 'POST'])
def search():
    """
    论文搜索和爬取页面
    """
    if request.method == 'POST':
        # 构建爬虫参数
        args = []
        
        if request.form.get('title'):
            args.append('--title')
            args.append(request.form.get('title'))
        
        if request.form.get('abstract'):
            args.append('--abstract')
            args.append(request.form.get('abstract'))
        
        if request.form.get('category'):
            args.append('--category')
            args.append(request.form.get('category'))
        
        # 设置最大下载数量
        max_papers = request.form.get('max', '10')
        args.append('--max')
        args.append(max_papers)
        
        # 设置输出目录
        output_dir = os.path.join(app.config['UPLOAD_FOLDER'], 
                                  f"arxiv_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        args.append('--output')
        args.append(output_dir)
        
        # 如果只需要元数据，添加对应参数
        if request.form.get('metadata_only') == 'on':
            args.append('--metadata-only')
        
        # 添加数据库查重参数
        if request.form.get('check_duplicates', 'on') == 'on':
            args.append('--database-check')
            args.append('--skip-existing')
            logger.info("启用论文查重功能，跳过已存在的论文")
        else:
            logger.info("未启用论文查重功能，可能会下载已存在的论文")
        
        # 构建完整命令
        crawler_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                    'arxiv_crawler', 'arxiv_crawler_enhanced.py')
        
        cmd = [sys.executable, crawler_path] + args
        
        # 在后台运行爬虫
        def run_crawler(cmd, output_dir):
            try:
                logger.info(f"运行爬虫: {' '.join(cmd)}")
                
                # 创建进度记录目录
                os.makedirs(output_dir, exist_ok=True)
                
                # 初始化进度文件
                progress_file = os.path.join(output_dir, "crawler_progress.json")
                with open(progress_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        "total": 0,
                        "processed": 0,
                        "skipped": 0,
                        "completed": 0,
                        "percent_complete": 0,
                        "status": "starting",
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "current_paper": None
                    }, f, ensure_ascii=False, indent=2)
                
                # 运行爬虫
                subprocess.run(cmd, check=True)
                
                # 爬取完成后，将论文导入数据库
                try:
                    metadata_file = os.path.join(output_dir, 'papers_metadata.csv')
                    if os.path.exists(metadata_file):
                        imported_count = import_papers_from_csv(metadata_file, output_dir)
                        logger.info(f"论文导入数据库完成，共导入 {imported_count} 篇")
                        
                        # 更新进度文件，标记导入完成
                        if os.path.exists(progress_file):
                            with open(progress_file, 'r', encoding='utf-8') as f:
                                progress_data = json.load(f)
                            
                            progress_data["status"] = "imported"
                            progress_data["imported_count"] = imported_count
                            progress_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
                            with open(progress_file, 'w', encoding='utf-8') as f:
                                json.dump(progress_data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    logger.error(f"导入论文到数据库失败: {str(e)}")
                    
                    # 更新进度文件，标记导入失败
                    if os.path.exists(progress_file):
                        with open(progress_file, 'r', encoding='utf-8') as f:
                            progress_data = json.load(f)
                        
                        progress_data["status"] = "import_failed"
                        progress_data["error"] = str(e)
                        progress_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        with open(progress_file, 'w', encoding='utf-8') as f:
                            json.dump(progress_data, f, ensure_ascii=False, indent=2)
                
            except subprocess.CalledProcessError as e:
                logger.error(f"爬虫运行失败: {str(e)}")
                
                # 更新进度文件，标记爬取失败
                progress_file = os.path.join(output_dir, "crawler_progress.json")
                if os.path.exists(progress_file):
                    with open(progress_file, 'r', encoding='utf-8') as f:
                        progress_data = json.load(f)
                    
                    progress_data["status"] = "failed"
                    progress_data["error"] = str(e)
                    progress_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    with open(progress_file, 'w', encoding='utf-8') as f:
                        json.dump(progress_data, f, ensure_ascii=False, indent=2)
        
        # 启动后台线程运行爬虫
        thread = threading.Thread(target=run_crawler, args=(cmd, output_dir))
        thread.daemon = True
        thread.start()
        
        # 设置会话变量，用于前端显示进度
        session = {}
        session['crawler_output_dir'] = output_dir
        session['crawler_start_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        flash(f"开始爬取论文，请稍后在论文库中查看结果。你可以在此页面查看爬取进度。", "info")
        return redirect(url_for('crawler_progress', output_dir=os.path.basename(output_dir)))
    
    return render_template('search.html')

# 爬虫进度页面
@app.route('/crawler_progress/<output_dir>')
def crawler_progress(output_dir):
    """
    显示爬虫进度页面
    """
    # 构建完整输出目录路径
    full_output_dir = os.path.join(app.config['UPLOAD_FOLDER'], output_dir)
    
    # 检查目录是否存在
    if not os.path.exists(full_output_dir):
        flash("爬虫任务不存在", "error")
        return redirect(url_for('search'))
    
    # 获取爬虫进度
    progress_file = os.path.join(full_output_dir, "crawler_progress.json")
    progress_data = {}
    
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
        except Exception as e:
            logger.error(f"读取爬虫进度文件失败: {str(e)}")
            progress_data = {
                "status": "unknown",
                "error": f"读取进度文件失败: {str(e)}"
            }
    else:
        progress_data = {
            "status": "initializing",
            "message": "爬虫正在初始化，请稍候..."
        }
    
    # 读取元数据文件，获取论文信息
    papers = []
    metadata_file = os.path.join(full_output_dir, "papers_metadata.json")
    
    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                papers = json.load(f)
        except Exception as e:
            logger.error(f"读取论文元数据文件失败: {str(e)}")
    
    return render_template('crawler_progress.html',
                          progress=progress_data,
                          papers=papers,
                          output_dir=output_dir)

# API: 获取爬虫进度
@app.route('/api/crawler_progress/<output_dir>', methods=['GET'])
def api_crawler_progress(output_dir):
    """
    获取爬虫进度的API
    """
    # 构建完整输出目录路径
    full_output_dir = os.path.join(app.config['UPLOAD_FOLDER'], output_dir)
    
    # 检查目录是否存在
    if not os.path.exists(full_output_dir):
        return jsonify({"error": "爬虫任务不存在"}), 404
    
    # 获取爬虫进度
    progress_file = os.path.join(full_output_dir, "crawler_progress.json")
    
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
            return jsonify(progress_data)
        except Exception as e:
            return jsonify({"error": f"读取进度文件失败: {str(e)}"}), 500
    else:
        return jsonify({"status": "initializing", "message": "爬虫正在初始化，请稍候..."}), 200

# 论文库页面
@app.route('/papers')
def papers():
    """
    显示论文库
    """
    # 获取分页参数
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    offset = (page - 1) * limit
    
    # 获取排序参数
    sort_by = request.args.get('sort_by', 'created_at')
    sort_direction = request.args.get('sort_direction', 'desc')
    
    # 获取搜索参数
    search_query = request.args.get('q', '')
    
    # 获取论文列表
    if search_query:
        papers_list = db_manager.search_papers(search_query, limit=limit)
        total_count = len(papers_list)  # 简化处理，实际应该单独查询总数
    else:
        papers_list = db_manager.get_papers(limit=limit, offset=offset, 
                                           sort_by=sort_by, sort_direction=sort_direction)
        
        # 获取总论文数
        with db_manager.get_session() as session:
            from database.models import Paper
            total_count = session.query(Paper).count()
    
    # 计算总页数
    total_pages = (total_count + limit - 1) // limit
    
    return render_template('papers.html', 
                          papers=papers_list,
                          page=page,
                          limit=limit,
                          total_pages=total_pages,
                          total_count=total_count,
                          search_query=search_query,
                          sort_by=sort_by,
                          sort_direction=sort_direction)

# 论文详情页面
@app.route('/paper/<int:paper_id>')
def paper_detail(paper_id):
    """
    显示论文详情
    """
    # 获取论文信息
    paper = db_manager.get_paper_by_id(paper_id)
    
    if not paper:
        flash("论文不存在", "error")
        return redirect(url_for('papers'))
    
    # 获取论文参数
    parameters = db_manager.get_parameters_by_paper(paper_id)
    
    # 按类别分组参数
    parameters_by_category = {}
    for param in parameters:
        category = param.get('category', 'other')
        if category not in parameters_by_category:
            parameters_by_category[category] = []
        parameters_by_category[category].append(param)
    
    return render_template('paper_detail.html', 
                          paper=paper,
                          parameters=parameters,
                          parameters_by_category=parameters_by_category)

# 参数提取页面
@app.route('/extract/<int:paper_id>', methods=['GET', 'POST'])
def extract_parameters(paper_id):
    """
    提取论文参数
    """
    # 获取论文信息
    paper = db_manager.get_paper_by_id(paper_id)
    if not paper:
        flash('论文不存在', 'error')
        return redirect(url_for('papers'))
    
    # 检查是否有PDF文件
    if not paper['local_pdf_path'] or not os.path.exists(paper['local_pdf_path']):
        flash('没有可用的PDF文件', 'error')
        return redirect(url_for('paper_detail', paper_id=paper_id))
    
    # 检查是否有正在进行的处理
    with db_manager.get_session() as session:
        from database.models import ProcessingRecord
        pending_records = session.query(ProcessingRecord).filter_by(
            paper_id=paper_id,
            status="pending"
        ).all()
        
        if pending_records:
            flash('已有参数提取任务正在进行', 'warning')
            return redirect(url_for('paper_detail', paper_id=paper_id))
    
    # 检查DeepSeek API密钥是否设置
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        flash('DeepSeek API密钥未设置，请设置环境变量DEEPSEEK_API_KEY', 'error')
        return redirect(url_for('paper_detail', paper_id=paper_id))
    
    if not api_key.startswith("sk-"):
        flash(f'DeepSeek API密钥格式可能不正确: {api_key[:5]}***，正确的密钥应以sk-开头', 'warning')
    
    # 尝试初始化API客户端
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        logger.info("成功初始化DeepSeek API客户端")
    except Exception as e:
        flash(f'初始化DeepSeek API客户端失败: {str(e)}', 'error')
        logger.error(f"初始化DeepSeek API客户端失败: {str(e)}")
        return redirect(url_for('paper_detail', paper_id=paper_id))
    
    # 表单提交处理
    if request.method == 'POST':
        force = request.form.get('force', False) == 'on'
        pdf_path = paper['local_pdf_path']
        
        # 添加处理记录并获取ID
        with db_manager.get_session() as session:
            from database.models import ProcessingRecord
            
            # 创建记录
            record = ProcessingRecord(
                paper_id=paper_id,
                process_type="parameter_extraction",
                status="pending",
                message="参数提取中..."
            )
            
            session.add(record)
            session.commit()
            
            # 获取ID（在session内部）
            record_id = record.id
        
        # 更新处理记录，保存详细的提取进度和日志
        def save_extraction_progress(record_id, step, message, progress_pct=None):
            """记录提取进度并更新处理记录"""
            progress_info = {
                "step": step,
                "message": message,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "progress_pct": progress_pct
            }
            with db_manager.get_session() as session:
                from database.models import ProcessingRecord
                record = session.query(ProcessingRecord).filter_by(id=record_id).first()
                if record:
                    # 更新进度信息
                    try:
                        progress_data = json.loads(record.message) if record.message.startswith('{') else {}
                    except:
                        progress_data = {}
                    
                    # 添加新进度信息
                    if not "progress_log" in progress_data:
                        progress_data["progress_log"] = []
                    progress_data["progress_log"].append(progress_info)
                    progress_data["current_step"] = step
                    progress_data["current_message"] = message
                    progress_data["progress_pct"] = progress_pct
                    
                    # 保存到数据库
                    record.message = json.dumps(progress_data)
                    session.commit()
            
            # 记录到日志
            logger.info(f"[提取进度] 记录ID: {record_id}, 步骤: {step}, 进度: {progress_pct}%, 信息: {message}")
        
        # 启动后台提取任务
        def extract_task(paper_id, pdf_path, record_id):
            try:
                # 更详细的日志记录
                logger.info(f"[提取任务启动] 论文ID: {paper_id}, 记录ID: {record_id}")
                save_extraction_progress(record_id, "start", "开始提取任务", 0)
                
                # 重新获取论文信息（避免使用外部闭包变量）
                paper_data = db_manager.get_paper_by_id(paper_id)
                if not paper_data:
                    logger.error(f"[提取任务失败] 无法找到论文 ID: {paper_id}")
                    save_extraction_progress(record_id, "error", f"无法找到论文 ID: {paper_id}", 0)
                    db_manager.update_processing_record(record_id, "failed", f"无法找到论文 ID: {paper_id}")
                    return
                
                # 提取PDF文本
                logger.info(f"[PDF提取开始] 路径: {pdf_path}")
                save_extraction_progress(record_id, "pdf_extraction", "开始提取PDF文本", 10)
                
                text = extract_text_from_pdf(pdf_path)
                
                if not text:
                    logger.error(f"[PDF提取失败] 路径: {pdf_path}")
                    save_extraction_progress(record_id, "pdf_extraction_failed", "从PDF提取文本失败", 0)
                    db_manager.update_processing_record(record_id, "failed", "从PDF提取文本失败")
                    return
                
                logger.info(f"[PDF提取成功] 提取文本长度: {len(text)} 字符")
                save_extraction_progress(record_id, "pdf_extraction_completed", f"成功提取文本，长度: {len(text)} 字符", 30)
                
                # 构建论文信息
                logger.info(f"[构建论文信息] 标题: {paper_data['title']}")
                save_extraction_progress(record_id, "build_paper_info", "构建论文元数据", 40)
                
                paper_info = {
                    "title": paper_data['title'],
                    "authors": paper_data['authors'].split(', ') if paper_data['authors'] else [],
                    "categories": paper_data['categories'].split(', ') if paper_data['categories'] else []
                }
                
                # 推断主题
                topic = None
                if paper_data['categories']:
                    if any('plasma' in cat.lower() for cat in paper_info['categories']):
                        topic = 'wakefield'
                        logger.info(f"[主题推断] 识别为等离子体/尾场加速主题")
                        save_extraction_progress(record_id, "topic_inference", "识别为等离子体/尾场加速主题", 50)
                    elif any('optic' in cat.lower() for cat in paper_info['categories']):
                        topic = 'laser system'
                        logger.info(f"[主题推断] 识别为激光系统主题")
                        save_extraction_progress(record_id, "topic_inference", "识别为激光系统主题", 50)
                    else:
                        logger.info(f"[主题推断] 使用通用激光物理主题")
                        save_extraction_progress(record_id, "topic_inference", "使用通用激光物理主题", 50)
                
                # 提取参数
                logger.info(f"[参数提取开始] 使用主题: {topic or '通用激光物理'}")
                save_extraction_progress(record_id, "parameter_extraction", f"开始参数提取，使用主题: {topic or '通用激光物理'}", 60)
                
                # 记录LLM API调用
                save_extraction_progress(record_id, "llm_api_call", "正在调用DeepSeek API进行参数提取...", 70)
                
                parameters = llm_processor.extract_parameters(text, paper_info, topic)
                
                if not parameters:
                    logger.warning(f"[参数提取失败] 未能提取到任何参数")
                    save_extraction_progress(record_id, "parameter_extraction_failed", "未能提取到任何参数", 0)
                    db_manager.update_processing_record(record_id, "failed", "未能提取到任何参数")
                    return
                
                logger.info(f"[参数提取成功] 提取到 {len(parameters)} 个参数")
                save_extraction_progress(record_id, "parameter_extraction_completed", f"成功提取 {len(parameters)} 个参数", 80)
                
                # 保存参数到数据库
                logger.info(f"[参数保存开始] 正在保存到数据库...")
                save_extraction_progress(record_id, "save_parameters", "正在保存参数到数据库", 90)
                
                added_count = db_manager.add_parameters(paper_id, parameters)
                logger.info(f"[参数保存完成] 成功保存 {added_count} 个参数")
                save_extraction_progress(record_id, "save_parameters_completed", f"成功保存 {added_count} 个参数", 100)
                
                # 更新处理记录
                progress_data = {"completed": True, "parameters_count": added_count, "progress_pct": 100}
                db_manager.update_processing_record(
                    record_id, "success", json.dumps(progress_data), added_count
                )
                
                logger.info(f"[提取任务完成] 论文ID: {paper_id}, 参数数量: {added_count}")
                
            except Exception as e:
                logger.error(f"[提取任务异常] 错误信息: {str(e)}")
                save_extraction_progress(record_id, "error", f"发生错误: {str(e)}", 0)
                db_manager.update_processing_record(record_id, "failed", f"参数提取失败: {str(e)}")
        
        # 启动提取线程
        thread = threading.Thread(target=extract_task, args=(paper_id, pdf_path, record_id))
        thread.daemon = True
        thread.start()
        
        flash("参数提取任务已启动，请稍后刷新页面查看结果", "info")
        return redirect(url_for('paper_detail', paper_id=paper_id))
    
    return render_template('extract_parameters.html', paper=paper)

# API: 获取参数提取进度
@app.route('/api/extraction_progress/<int:record_id>', methods=['GET'])
def api_extraction_progress(record_id):
    """
    获取参数提取进度
    """
    with db_manager.get_session() as session:
        from database.models import ProcessingRecord
        record = session.query(ProcessingRecord).filter_by(id=record_id).first()
        
        if not record:
            return jsonify({"error": "记录不存在"}), 404
        
        try:
            # 解析进度信息
            progress_data = json.loads(record.message) if record.message and record.message.startswith('{') else {}
            
            # 构建响应
            response = {
                "record_id": record.id,
                "paper_id": record.paper_id,
                "status": record.status,
                "current_step": progress_data.get("current_step", "unknown"),
                "current_message": progress_data.get("current_message", record.message),
                "progress_pct": progress_data.get("progress_pct", 0 if record.status == "pending" else 100),
                "progress_log": progress_data.get("progress_log", []),
                "result_count": record.result_count,
                "created_at": record.created_at.strftime("%Y-%m-%d %H:%M:%S") if record.created_at else None,
                "updated_at": record.updated_at.strftime("%Y-%m-%d %H:%M:%S") if record.updated_at else None
            }
            
            return jsonify(response)
        except:
            # 如果解析失败，返回原始信息
            return jsonify({
                "record_id": record.id,
                "paper_id": record.paper_id,
                "status": record.status,
                "message": record.message,
                "result_count": record.result_count,
                "created_at": record.created_at.strftime("%Y-%m-%d %H:%M:%S") if record.created_at else None,
                "updated_at": record.updated_at.strftime("%Y-%m-%d %H:%M:%S") if record.updated_at else None
            })

# 参数页面
@app.route('/parameters')
def parameters():
    """
    显示所有参数
    """
    # 获取搜索参数
    search_query = request.args.get('q', '')
    category = request.args.get('category', '')
    format_type = request.args.get('format', '')  # HTML格式或完整页面
    
    # 获取分页参数
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    offset = (page - 1) * limit
    
    # 构建过滤条件
    filter_criteria = {}
    if search_query:
        filter_criteria['query'] = search_query
    if category:
        filter_criteria['category'] = category
    
    # 构建SQL查询
    with db_manager.get_session() as session:
        from database.models import LaserParameter, Paper
        from sqlalchemy import func
        
        # 基本查询
        query = session.query(
            LaserParameter.parameter_name,
            func.count(LaserParameter.id).label('count')
        ).group_by(LaserParameter.parameter_name)
        
        # 应用过滤
        if 'query' in filter_criteria:
            query = query.filter(LaserParameter.parameter_name.like(f"%{filter_criteria['query']}%"))
        if 'category' in filter_criteria:
            query = query.filter(LaserParameter.category == filter_criteria['category'])
        
        # 执行查询
        parameter_counts = query.order_by(func.count(LaserParameter.id).desc()).all()
        
        # 获取类别统计
        categories = session.query(
            LaserParameter.category,
            func.count(LaserParameter.id).label('count')
        ).group_by(LaserParameter.category).all()
        
        # 获取参数总数和特定类别的参数数
        if category:
            # 如果有类别过滤，只计算该类别的参数数
            total_count = session.query(LaserParameter).filter(LaserParameter.category == category).count()
        else:
            # 否则计算所有参数
            total_count = session.query(LaserParameter).count()
    
    # 计算总页数
    total_pages = (total_count + limit - 1) // limit if total_count > 0 else 1
    
    # 获取参数列表
    if category:
        # 使用类别过滤
        parameters_list = db_manager.search_parameters('', field='category', value=category, limit=limit, offset=offset)
    elif search_query:
        # 使用关键字搜索
        parameters_list = db_manager.search_parameters(query=search_query, field=None, value=None, limit=limit, offset=offset)
    else:
        # 获取所有参数，分页
        parameters_list = db_manager.search_parameters(query='', field=None, value=None, limit=limit, offset=offset)
    
    # 如果是请求HTML片段（用于标签加载）
    if format_type == 'html':
        if not parameters_list:
            return f"<div class='alert alert-info'><i class='bi bi-info-circle'></i> 没有找到{category}参数</div>"
        
        # 返回只包含表格的HTML片段
        return render_template('parameter_table_fragment.html',
                              parameters=parameters_list,
                              page=page,
                              limit=limit,
                              total_pages=total_pages,
                              total_count=total_count,
                              search_query=search_query,
                              category=category,
                              format='html')
    
    # 否则返回完整页面
    return render_template('parameters.html',
                          parameter_counts=parameter_counts,
                          categories=categories,
                          parameters=parameters_list,
                          search_query=search_query,
                          selected_category=category,
                          page=page,
                          limit=limit,
                          total_pages=total_pages,
                          total_count=total_count)

# 上传PDF文件
@app.route('/upload', methods=['GET', 'POST'])
def upload_pdf():
    """
    上传PDF文件页面
    """
    if request.method == 'POST':
        # 检查是否有文件
        if 'file' not in request.files:
            flash('没有上传文件', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        
        # 如果用户没有选择文件
        if file.filename == '':
            flash('没有选择文件', 'error')
            return redirect(request.url)
        
        if file and file.filename.lower().endswith('.pdf'):
            # 安全的文件名
            filename = secure_filename(file.filename)
            
            # 保存文件
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # 获取论文元数据
            title = request.form.get('title', filename)
            authors = request.form.get('authors', '')
            abstract = request.form.get('abstract', '')
            
            # 添加到数据库
            paper_data = {
                'id': f"manual_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                'title': title,
                'authors': authors.split(',') if authors else [],
                'abstract': abstract,
                'categories': request.form.get('categories', ''),
                'local_path': file_path
            }
            
            paper = db_manager.add_paper(paper_data)
            
            flash(f'文件上传成功: {filename}', 'success')
            return redirect(url_for('paper_detail', paper_id=paper.id))
    
    return render_template('upload.html')

# 导出参数到CSV
@app.route('/export', methods=['GET', 'POST'])
def export_parameters():
    """
    导出参数到CSV
    """
    if request.method == 'POST':
        # 获取过滤条件
        filter_criteria = {}
        
        if request.form.get('parameter_name'):
            filter_criteria['parameter_name'] = request.form.get('parameter_name')
        
        if request.form.get('category'):
            filter_criteria['category'] = request.form.get('category')
        
        if request.form.get('paper_title'):
            filter_criteria['paper_title'] = request.form.get('paper_title')
        
        # 创建临时文件
        import tempfile
        output_file = os.path.join(tempfile.gettempdir(), 'parameters_export.csv')
        
        # 导出参数
        db_manager.export_parameters_to_csv(output_file, filter_criteria)
        
        # 返回文件
        return send_file(output_file, 
                         as_attachment=True, 
                         download_name='laser_parameters.csv',
                         mimetype='text/csv')
    
    # 获取参数类别
    with db_manager.get_session() as session:
        from database.models import LaserParameter
        from sqlalchemy import distinct
        categories = [cat[0] for cat in session.query(distinct(LaserParameter.category)).all()]
    
    return render_template('export.html', categories=categories)

# API: 获取统计图表数据
@app.route('/api/stats/chart', methods=['GET'])
def api_stats_chart():
    """
    获取统计图表数据
    """
    chart_type = request.args.get('type', 'category')
    
    with db_manager.get_session() as session:
        from database.models import LaserParameter
        from sqlalchemy import func
        
        if chart_type == 'category':
            # 按类别统计
            data = session.query(
                LaserParameter.category,
                func.count(LaserParameter.id)
            ).group_by(LaserParameter.category).all()
            
            labels = [item[0] for item in data]
            values = [item[1] for item in data]
            
            return jsonify({
                'labels': labels,
                'values': values,
                'title': '按参数类别统计'
            })
            
        elif chart_type == 'unit':
            # 按单位统计
            data = session.query(
                LaserParameter.unit,
                func.count(LaserParameter.id)
            ).group_by(LaserParameter.unit).all()
            
            # 过滤空单位并限制数量
            data = [(unit, count) for unit, count in data if unit]
            data.sort(key=lambda x: x[1], reverse=True)
            data = data[:10]  # 只取前10个
            
            labels = [item[0] for item in data]
            values = [item[1] for item in data]
            
            return jsonify({
                'labels': labels,
                'values': values,
                'title': '常见参数单位统计'
            })
            
        elif chart_type == 'parameter':
            # 按参数名称统计
            data = session.query(
                LaserParameter.parameter_name,
                func.count(LaserParameter.id)
            ).group_by(LaserParameter.parameter_name).order_by(
                func.count(LaserParameter.id).desc()
            ).limit(10).all()
            
            labels = [item[0] for item in data]
            values = [item[1] for item in data]
            
            return jsonify({
                'labels': labels,
                'values': values,
                'title': '最常见的10个参数'
            })
    
    return jsonify({'error': '无效的图表类型'})

# 工具函数: 导入论文从CSV
def import_papers_from_csv(csv_file, pdf_dir):
    """
    从CSV文件导入论文到数据库
    
    参数:
        csv_file (str): CSV文件路径
        pdf_dir (str): PDF目录路径
        
    返回:
        int: 成功导入的论文数量
    """
    try:
        # 读取CSV
        df = pd.read_csv(csv_file)
        
        # 转换为字典列表
        papers_data = []
        duplicates_count = 0
        
        # 第一阶段：一次性检查所有论文是否存在，避免导入过程中的时序问题
        existing_arxiv_ids = set()
        existing_dois = set()
        
        # 收集所有可能存在的DOI和arXiv ID
        doi_list = [row.get('doi', '') for _, row in df.iterrows() if row.get('doi')]
        arxiv_id_list = [row.get('id', '') for _, row in df.iterrows() if row.get('id')]
        
        # 使用批量查询获取已存在的论文ID
        with db_manager.get_session() as session:
            from database.models import Paper
            from sqlalchemy import or_
            
            if doi_list:
                # 确保所有DOI都是字符串类型
                doi_list = [str(doi) for doi in doi_list if doi]
                try:
                    existing_doi_records = session.query(Paper.doi).filter(Paper.doi.in_(doi_list)).all()
                    existing_dois = set([r[0] for r in existing_doi_records if r[0]])
                except Exception as e:
                    logger.error(f"DOI查询失败: {str(e)}")
                    existing_dois = set()
            
            if arxiv_id_list:
                try:
                    existing_arxiv_records = session.query(Paper.arxiv_id).filter(Paper.arxiv_id.in_(arxiv_id_list)).all()
                    existing_arxiv_ids = set([r[0] for r in existing_arxiv_records if r[0]])
                except Exception as e:
                    logger.error(f"arXiv ID查询失败: {str(e)}")
                    existing_arxiv_ids = set()
        
        # 第二阶段：准备需要导入的论文数据
        for _, row in df.iterrows():
            # 构建论文数据
            paper_data = {
                'id': row.get('id', ''),
                'title': row.get('title', ''),
                'authors': row.get('authors', '').split(', '),
                'abstract': row.get('abstract', ''),
                'categories': row.get('categories', '').split(', '),
                'published': row.get('published', ''),
                'updated': row.get('updated', ''),
                'pdf_url': row.get('pdf_url', ''),
                'doi': row.get('doi', '')  # 添加DOI支持
            }
            
            # 使用之前收集的集合快速检查是否存在
            paper_exists = False
            if paper_data['doi'] and paper_data['doi'] in existing_dois:
                paper_exists = True
            elif paper_data['id'] and paper_data['id'] in existing_arxiv_ids:
                paper_exists = True
            
            if paper_exists:
                logger.info(f"论文已存在，跳过: {paper_data['id']}")
                duplicates_count += 1
                continue
            
            # 查找本地PDF文件
            arxiv_id = paper_data['id']
            pdf_files = [f for f in os.listdir(pdf_dir) 
                        if f.lower().endswith('.pdf') and arxiv_id in f]
            
            if pdf_files:
                paper_data['local_path'] = os.path.join(pdf_dir, pdf_files[0])
            
            papers_data.append(paper_data)
        
        # 批量添加到数据库
        if papers_data:
            added_ids = db_manager.add_papers_batch(papers_data)
            imported_count = len(added_ids)
            logger.info(f"成功从CSV导入 {imported_count} 篇新论文")
        else:
            logger.info(f"没有新论文需要导入，{duplicates_count}篇论文已在数据库中")
            imported_count = 0
        
        return imported_count
    
    except Exception as e:
        logger.error(f"从CSV导入论文失败: {str(e)}")
        return 0

@app.route('/view_pdf/<int:paper_id>')
def view_pdf(paper_id):
    """
    提供PDF文件预览
    """
    try:
        # 从数据库获取论文信息
        paper = db_manager.get_paper_by_id(paper_id)
        if not paper or 'local_pdf_path' not in paper or not paper['local_pdf_path']:
            return "PDF文件不存在", 404
        
        # 检查文件是否存在
        if not os.path.exists(paper['local_pdf_path']):
            return "PDF文件不存在或已被移除", 404
        
        # 清理文件名，移除换行符
        clean_title = paper['title'].replace('\n', ' ').replace('\r', ' ')
        
        # 返回PDF文件
        return send_file(
            paper['local_pdf_path'],
            mimetype='application/pdf',
            as_attachment=False,
            download_name=f"{clean_title}.pdf"
        )
    except Exception as e:
        logging.error(f"PDF预览错误: {str(e)}")
        return f"无法加载PDF: {str(e)}", 500

# 添加新的处理状态查看页面
@app.route('/processing_status/<int:paper_id>')
def processing_status(paper_id):
    """
    显示论文参数提取的处理状态
    """
    paper = db_manager.get_paper_by_id(paper_id)
    
    if not paper:
        flash("论文不存在", "error")
        return redirect(url_for('papers'))
    
    # 获取处理记录
    with db_manager.get_session() as session:
        from database.models import ProcessingRecord
        records = session.query(ProcessingRecord).filter_by(
            paper_id=paper_id
        ).order_by(ProcessingRecord.created_at.desc()).all()
    
    # 读取日志文件最后50行
    log_lines = []
    try:
        import subprocess
        result = subprocess.run(['tail', '-n', '50', 'app.log'], capture_output=True, text=True)
        if result.returncode == 0:
            log_text = result.stdout
            log_lines = log_text.split('\n')
            # 过滤出与此论文相关的日志
            paper_id_str = str(paper_id)
            log_lines = [line for line in log_lines if paper_id_str in line or paper['title'] in line]
    except Exception as e:
        log_lines = [f"无法读取日志: {str(e)}"]
    
    return render_template('processing_status.html', 
                          paper=paper,
                          records=records,
                          log_lines=log_lines)

# 取消参数提取
@app.route('/cancel_extraction/<int:paper_id>', methods=['POST'])
def cancel_extraction(paper_id):
    """
    取消正在进行的参数提取任务
    """
    try:
        # 获取论文信息
        paper = db_manager.get_paper_by_id(paper_id)
        if not paper:
            flash("论文不存在", "error")
            return redirect(url_for('papers'))
        
        # 查找并更新所有处于pending状态的处理记录
        with db_manager.get_session() as session:
            from database.models import ProcessingRecord
            import datetime
            
            pending_records = session.query(ProcessingRecord).filter_by(
                paper_id=paper_id, 
                status="pending"
            ).all()
            
            if not pending_records:
                flash("没有进行中的提取任务", "warning")
                return redirect(url_for('paper_detail', paper_id=paper_id))
            
            # 更新所有pending记录
            for record in pending_records:
                record.status = "failed"
                record.message = "用户手动取消提取"
                record.updated_at = datetime.datetime.utcnow()
            
            # 提交更改
            session.commit()
        
        # 清除可能的时间戳问题
        # 运行修复脚本
        import subprocess
        try:
            fix_script = os.path.join(app.root_path, "..", "fix_pending_records.py")
            subprocess.call(["python", fix_script], timeout=10)
        except:
            pass
        
        flash("已成功取消提取任务", "success")
        return redirect(url_for('paper_detail', paper_id=paper_id))
        
    except Exception as e:
        flash(f"取消任务失败: {str(e)}", "error")
        return redirect(url_for('paper_detail', paper_id=paper_id))

# API: 获取论文元数据
@app.route('/api/papers_metadata/<output_dir>', methods=['GET'])
def api_papers_metadata(output_dir):
    """
    获取论文元数据API
    """
    # 构建完整输出目录路径
    full_output_dir = os.path.join(app.config['UPLOAD_FOLDER'], output_dir)
    
    # 检查目录是否存在
    if not os.path.exists(full_output_dir):
        return jsonify({"error": "目录不存在"}), 404
    
    # 获取元数据文件
    metadata_file = os.path.join(full_output_dir, "papers_metadata.json")
    csv_metadata_file = os.path.join(full_output_dir, "papers_metadata.csv")
    
    # 尝试从JSON文件获取论文元数据
    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                papers = json.load(f)
            return jsonify(papers)
        except Exception as e:
            logger.error(f"读取JSON元数据文件失败: {str(e)}")
    
    # 如果JSON文件不存在，尝试从CSV文件读取
    if os.path.exists(csv_metadata_file):
        try:
            papers = []
            with open(csv_metadata_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 转换CSV行为字典
                    paper = {
                        "id": row.get("id", ""),
                        "title": row.get("title", ""),
                        "authors": row.get("authors", "").split(","),
                        "categories": row.get("categories", "").split(","),
                        "abstract": row.get("abstract", ""),
                        "url": row.get("url", ""),
                        "pdf_url": row.get("pdf_url", ""),
                        "status": "completed"
                    }
                    papers.append(paper)
            return jsonify(papers)
        except Exception as e:
            logger.error(f"读取CSV元数据文件失败: {str(e)}")
            return jsonify({"error": f"读取元数据文件失败: {str(e)}"}), 500
    
    # 如果两种文件都不存在，返回空列表
    return jsonify([])

if __name__ == '__main__':
    # 在开发环境中运行
    app.run(debug=True, port=5000) 