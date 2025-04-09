import os
import logging
import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc
import pandas as pd

from .models import Paper, LaserParameter, ProcessingRecord, ExtractedTable, get_engine, get_session_factory, init_db

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    数据库管理类，处理论文和参数的数据库操作
    """
    
    def __init__(self, db_url=None):
        """
        初始化数据库管理器
        
        参数:
            db_url (str, optional): 数据库URL，默认使用配置文件或环境变量中的值
        """
        # 使用默认的SQLite数据库
        self.db_url = db_url or os.environ.get('DB_URL', 'sqlite:///laser_papers.db')
        
        # 创建引擎和会话工厂
        self.engine = get_engine(self.db_url)
        self.SessionFactory = get_session_factory(self.engine)
        
        # 初始化数据库（如果需要）
        init_db(self.engine)
        
        logger.info(f"数据库管理器初始化完成，使用数据库: {self.db_url}")
    
    def get_session(self):
        """
        获取新的数据库会话
        
        返回:
            Session: SQLAlchemy会话
        """
        return self.SessionFactory()
    
    # 论文相关操作
    def add_paper(self, paper_data):
        """
        添加新论文到数据库
        
        参数:
            paper_data (dict): 论文数据
            
        返回:
            Paper: 添加的论文对象
        """
        with self.get_session() as session:
            # 检查是否已存在
            existing_paper = session.query(Paper).filter_by(arxiv_id=paper_data.get('id')).first()
            if existing_paper:
                logger.info(f"论文已存在: {paper_data.get('id')}")
                return existing_paper
            
            # 创建新论文对象
            new_paper = Paper(
                arxiv_id=paper_data.get('id'),
                title=paper_data.get('title', ''),
                authors=', '.join(paper_data.get('authors', [])) if isinstance(paper_data.get('authors', []), list) else paper_data.get('authors', ''),
                abstract=paper_data.get('abstract', ''),
                categories=', '.join(paper_data.get('categories', [])) if isinstance(paper_data.get('categories', []), list) else paper_data.get('categories', ''),
                published_date=self._parse_date(paper_data.get('published')),
                updated_date=self._parse_date(paper_data.get('updated')),
                pdf_url=paper_data.get('pdf_url', ''),
                local_pdf_path=paper_data.get('local_path', ''),
                doi=str(paper_data.get('doi', '')) if paper_data.get('doi') else None
            )
            
            # 添加到数据库
            session.add(new_paper)
            session.commit()
            
            logger.info(f"论文添加成功: {new_paper.arxiv_id}")
            return new_paper
    
    def add_papers_batch(self, papers_data):
        """
        批量添加论文到数据库
        
        参数:
            papers_data (list): 论文数据列表
            
        返回:
            list: 添加的论文ID列表
        """
        added_ids = []
        
        with self.get_session() as session:
            for paper_data in papers_data:
                # 检查是否已存在
                arxiv_id = paper_data.get('id')
                existing_paper = session.query(Paper).filter_by(arxiv_id=arxiv_id).first()
                
                if existing_paper:
                    logger.info(f"论文已存在，跳过: {arxiv_id}")
                    added_ids.append(existing_paper.id)
                    continue
                
                # 创建新论文对象
                new_paper = Paper(
                    arxiv_id=arxiv_id,
                    title=paper_data.get('title', ''),
                    authors=', '.join(paper_data.get('authors', [])) if isinstance(paper_data.get('authors', []), list) else paper_data.get('authors', ''),
                    abstract=paper_data.get('abstract', ''),
                    categories=', '.join(paper_data.get('categories', [])) if isinstance(paper_data.get('categories', []), list) else paper_data.get('categories', ''),
                    published_date=self._parse_date(paper_data.get('published')),
                    updated_date=self._parse_date(paper_data.get('updated')),
                    pdf_url=paper_data.get('pdf_url', ''),
                    local_pdf_path=paper_data.get('local_path', ''),
                    doi=str(paper_data.get('doi', '')) if paper_data.get('doi') else None
                )
                
                # 添加到数据库
                session.add(new_paper)
                session.flush()  # 获取ID而不提交
                
                added_ids.append(new_paper.id)
            
            # 提交所有更改
            session.commit()
            
        logger.info(f"批量添加论文完成，共添加 {len(added_ids)} 篇")
        return added_ids
    
    def update_paper(self, paper_id, update_data):
        """
        更新论文信息
        
        参数:
            paper_id (int): 论文ID
            update_data (dict): 要更新的字段和值
            
        返回:
            bool: 更新是否成功
        """
        with self.get_session() as session:
            paper = session.query(Paper).filter_by(id=paper_id).first()
            
            if not paper:
                logger.warning(f"论文不存在，无法更新: {paper_id}")
                return False
            
            # 更新字段
            for key, value in update_data.items():
                if hasattr(paper, key):
                    setattr(paper, key, value)
            
            # 更新时间戳
            paper.updated_at = datetime.datetime.utcnow()
            
            session.commit()
            logger.info(f"论文更新成功: {paper_id}")
            
            return True
    
    def get_paper_by_id(self, paper_id):
        """
        通过ID获取论文
        
        参数:
            paper_id (int): 论文ID
            
        返回:
            dict: 论文数据
        """
        with self.get_session() as session:
            paper = session.query(Paper).filter_by(id=paper_id).first()
            
            if not paper:
                return None
            
            # 转换为字典
            return {
                'id': paper.id,
                'arxiv_id': paper.arxiv_id,
                'title': paper.title,
                'authors': paper.authors,
                'abstract': paper.abstract,
                'categories': paper.categories,
                'published_date': paper.published_date,
                'updated_date': paper.updated_date,
                'pdf_url': paper.pdf_url,
                'local_pdf_path': paper.local_pdf_path,
                'doi': paper.doi,
                'created_at': paper.created_at,
                'updated_at': paper.updated_at,
                'processed': paper.processed
            }
    
    def get_paper_by_arxiv_id(self, arxiv_id):
        """
        通过arXiv ID获取论文
        
        参数:
            arxiv_id (str): arXiv ID
            
        返回:
            dict: 论文数据
        """
        with self.get_session() as session:
            paper = session.query(Paper).filter_by(arxiv_id=arxiv_id).first()
            
            if not paper:
                return None
            
            # 转换为字典
            return {
                'id': paper.id,
                'arxiv_id': paper.arxiv_id,
                'title': paper.title,
                'authors': paper.authors,
                'abstract': paper.abstract,
                'categories': paper.categories,
                'published_date': paper.published_date,
                'updated_date': paper.updated_date,
                'pdf_url': paper.pdf_url,
                'local_pdf_path': paper.local_pdf_path,
                'doi': paper.doi,
                'created_at': paper.created_at,
                'updated_at': paper.updated_at,
                'processed': paper.processed
            }
    
    def get_papers(self, limit=100, offset=0, sort_by='created_at', sort_direction='desc'):
        """
        获取论文列表
        
        参数:
            limit (int): 最大返回数量
            offset (int): 开始偏移量
            sort_by (str): 排序字段
            sort_direction (str): 排序方向，'asc' 或 'desc'
            
        返回:
            list: 论文列表
        """
        with self.get_session() as session:
            query = session.query(Paper)
            
            # 应用排序
            if hasattr(Paper, sort_by):
                if sort_direction.lower() == 'desc':
                    query = query.order_by(desc(getattr(Paper, sort_by)))
                else:
                    query = query.order_by(getattr(Paper, sort_by))
            
            # 应用分页
            papers = query.limit(limit).offset(offset).all()
            
            # 转换为字典列表
            result = []
            for paper in papers:
                result.append({
                    'id': paper.id,
                    'arxiv_id': paper.arxiv_id,
                    'title': paper.title,
                    'authors': paper.authors,
                    'abstract': paper.abstract,
                    'categories': paper.categories,
                    'published_date': paper.published_date,
                    'updated_date': paper.updated_date,
                    'pdf_url': paper.pdf_url,
                    'local_pdf_path': paper.local_pdf_path,
                    'doi': paper.doi,
                    'created_at': paper.created_at,
                    'updated_at': paper.updated_at,
                    'processed': paper.processed
                })
            
            return result
    
    def search_papers(self, query, field=None, limit=100):
        """
        搜索论文
        
        参数:
            query (str): 搜索关键词
            field (str): 搜索字段，如 'title', 'abstract' 等，默认搜索所有字段
            limit (int): 最大返回数量
            
        返回:
            list: 论文列表
        """
        with self.get_session() as session:
            q = session.query(Paper)
            
            # 添加搜索条件
            if field:
                if hasattr(Paper, field):
                    q = q.filter(getattr(Paper, field).like(f'%{query}%'))
            else:
                # 搜索多个字段
                from sqlalchemy import or_
                q = q.filter(or_(
                    Paper.title.like(f'%{query}%'),
                    Paper.abstract.like(f'%{query}%'),
                    Paper.authors.like(f'%{query}%'),
                    Paper.categories.like(f'%{query}%')
                ))
            
            # 应用限制
            papers = q.limit(limit).all()
            
            # 转换为字典列表
            result = []
            for paper in papers:
                result.append({
                    'id': paper.id,
                    'arxiv_id': paper.arxiv_id,
                    'title': paper.title,
                    'authors': paper.authors,
                    'abstract': paper.abstract,
                    'categories': paper.categories,
                    'published_date': paper.published_date,
                    'updated_date': paper.updated_date,
                    'pdf_url': paper.pdf_url,
                    'local_pdf_path': paper.local_pdf_path,
                    'doi': paper.doi,
                    'created_at': paper.created_at,
                    'updated_at': paper.updated_at,
                    'processed': paper.processed
                })
            
            return result
    
    def get_paper_by_doi(self, doi):
        """
        通过DOI获取论文
        
        参数:
            doi (str): 论文的DOI
            
        返回:
            dict: 论文数据，如果不存在则返回None
        """
        if not doi:
            return None
            
        with self.get_session() as session:
            # 先根据 DOI 字段查询
            from sqlalchemy import or_
            paper = session.query(Paper).filter(
                or_(
                    Paper.doi == doi,
                    # 有时候 DOI 存在于 abstract 或其他文本字段中
                    Paper.abstract.like(f"%{doi}%"),
                    Paper.title.like(f"%{doi}%")
                )
            ).first()
            
            if not paper:
                return None
            
            # 转换为字典
            return {
                'id': paper.id,
                'arxiv_id': paper.arxiv_id,
                'title': paper.title,
                'authors': paper.authors,
                'abstract': paper.abstract,
                'categories': paper.categories,
                'published_date': paper.published_date,
                'updated_date': paper.updated_date,
                'pdf_url': paper.pdf_url,
                'local_pdf_path': paper.local_pdf_path,
                'doi': paper.doi,
                'created_at': paper.created_at,
                'updated_at': paper.updated_at,
                'processed': paper.processed
            }
    
    # 参数相关操作
    def add_parameters(self, paper_id, parameters):
        """
        为论文添加参数
        
        参数:
            paper_id (int): 论文ID
            parameters (list): 参数列表，每个参数是一个字典
            
        返回:
            int: 添加的参数数量
        """
        with self.get_session() as session:
            # 检查论文是否存在
            paper = session.query(Paper).filter_by(id=paper_id).first()
            
            if not paper:
                logger.warning(f"论文不存在，无法添加参数: {paper_id}")
                return 0
            
            # 标记论文为已处理
            paper.processed = True
            
            # 添加参数
            added_count = 0
            for param_data in parameters:
                # 创建参数对象
                new_param = LaserParameter(
                    paper_id=paper_id,
                    parameter_name=param_data.get('parameter_name', ''),
                    value=param_data.get('value', ''),
                    unit=param_data.get('unit', ''),
                    context=param_data.get('context', ''),
                    confidence_score=float(param_data.get('confidence_score', 0)) if param_data.get('confidence_score') else None,
                    category=self._categorize_parameter(param_data.get('parameter_name', ''))
                )
                
                session.add(new_param)
                added_count += 1
            
            # 记录处理状态
            processing_record = ProcessingRecord(
                paper_id=paper_id,
                process_type="parameter_extraction",
                status="success",
                message=f"成功提取 {added_count} 个参数",
                result_count=added_count,
                updated_at=datetime.datetime.utcnow()
            )
            
            session.add(processing_record)
            session.commit()
            
            logger.info(f"成功为论文 {paper_id} 添加 {added_count} 个参数")
            return added_count
    
    def get_parameters_by_paper(self, paper_id):
        """
        获取论文的所有参数
        
        参数:
            paper_id (int): 论文ID
            
        返回:
            list: 参数列表
        """
        with self.get_session() as session:
            parameters = session.query(LaserParameter).filter_by(paper_id=paper_id).all()
            
            # 转换为字典列表
            result = []
            for param in parameters:
                result.append({
                    'id': param.id,
                    'paper_id': param.paper_id,
                    'parameter_name': param.parameter_name,
                    'value': param.value,
                    'unit': param.unit,
                    'context': param.context,
                    'confidence_score': param.confidence_score,
                    'category': param.category,
                    'created_at': param.created_at
                })
            
            return result
    
    def search_parameters(self, query, field=None, value=None, limit=100, offset=0):
        """
        搜索参数
        
        参数:
            query (str): 搜索关键词
            field (str): 搜索字段，如 'parameter_name', 'value' 等，默认搜索所有字段
            value (str): 当field指定时，可以提供精确匹配的值
            limit (int): 最大返回数量
            offset (int): 结果偏移量，用于分页
            
        返回:
            list: 参数列表
        """
        with self.get_session() as session:
            q = session.query(LaserParameter)
            
            # 添加搜索条件
            if field and value:
                # 精确匹配特定字段的值
                if hasattr(LaserParameter, field):
                    q = q.filter(getattr(LaserParameter, field) == value)
            elif field:
                # 模糊匹配特定字段
                if hasattr(LaserParameter, field):
                    q = q.filter(getattr(LaserParameter, field).like(f'%{query}%'))
            elif query:
                # 搜索多个字段
                from sqlalchemy import or_
                q = q.filter(or_(
                    LaserParameter.parameter_name.like(f'%{query}%'),
                    LaserParameter.value.like(f'%{query}%'),
                    LaserParameter.unit.like(f'%{query}%'),
                    LaserParameter.context.like(f'%{query}%'),
                    LaserParameter.category.like(f'%{query}%')
                ))
            
            # 应用分页
            q = q.offset(offset).limit(limit)
            
            # 执行查询
            parameters = q.all()
            
            # 转换为字典列表
            result = []
            for param in parameters:
                # 获取相关联的论文信息
                paper = None
                try:
                    paper = session.query(Paper).filter_by(id=param.paper_id).first()
                except:
                    pass
                
                param_dict = {
                    'id': param.id,
                    'paper_id': param.paper_id,
                    'parameter_name': param.parameter_name,
                    'value': param.value,
                    'unit': param.unit,
                    'context': param.context,
                    'confidence_score': param.confidence_score,
                    'category': param.category,
                    'created_at': param.created_at,
                    'paper': {
                        'title': paper.title if paper else None
                    } if paper else None
                }
                result.append(param_dict)
            
            return result
    
    def get_parameter_statistics(self):
        """
        获取参数统计信息
        
        返回:
            dict: 统计信息
        """
        with self.get_session() as session:
            # 总参数数量
            total_params = session.query(LaserParameter).count()
            
            # 按类别统计
            from sqlalchemy import func
            category_counts = session.query(
                LaserParameter.category, 
                func.count(LaserParameter.id)
            ).group_by(LaserParameter.category).all()
            
            # 按单位统计
            unit_counts = session.query(
                LaserParameter.unit, 
                func.count(LaserParameter.id)
            ).group_by(LaserParameter.unit).all()
            
            # 最常见的参数名称
            common_params = session.query(
                LaserParameter.parameter_name, 
                func.count(LaserParameter.id)
            ).group_by(LaserParameter.parameter_name).order_by(
                func.count(LaserParameter.id).desc()
            ).limit(10).all()
            
            # 构建统计结果
            stats = {
                'total_parameters': total_params,
                'by_category': {cat: count for cat, count in category_counts},
                'by_unit': {unit: count for unit, count in unit_counts},
                'common_parameters': {name: count for name, count in common_params}
            }
            
            return stats
    
    def export_parameters_to_csv(self, output_file, filter_criteria=None):
        """
        将参数导出到CSV文件
        
        参数:
            output_file (str): 输出文件路径
            filter_criteria (dict, optional): 过滤条件
            
        返回:
            str: 文件路径
        """
        with self.get_session() as session:
            # 构建查询
            query = session.query(
                LaserParameter.parameter_name,
                LaserParameter.value,
                LaserParameter.unit,
                LaserParameter.category,
                LaserParameter.confidence_score,
                Paper.title,
                Paper.authors,
                Paper.arxiv_id
            ).join(Paper)
            
            # 应用过滤条件
            if filter_criteria:
                if 'parameter_name' in filter_criteria:
                    query = query.filter(LaserParameter.parameter_name.like(f"%{filter_criteria['parameter_name']}%"))
                if 'category' in filter_criteria:
                    query = query.filter(LaserParameter.category == filter_criteria['category'])
                if 'paper_title' in filter_criteria:
                    query = query.filter(Paper.title.like(f"%{filter_criteria['paper_title']}%"))
            
            # 执行查询
            results = query.all()
            
            # 转换为DataFrame
            df = pd.DataFrame(results, columns=[
                'parameter_name', 'value', 'unit', 'category', 'confidence_score',
                'paper_title', 'authors', 'arxiv_id'
            ])
            
            # 保存到CSV
            df.to_csv(output_file, index=False)
            
            return output_file
    
    # 处理记录相关操作
    def add_processing_record(self, paper_id, process_type, status, message=None, parameters_count=0):
        """
        添加处理记录
        
        参数:
            paper_id (int): 论文ID
            process_type (str): 处理类型
            status (str): 状态
            message (str, optional): 消息
            parameters_count (int): 提取的参数数量
            
        返回:
            ProcessingRecord: 处理记录对象
        """
        with self.get_session() as session:
            # 创建记录
            record = ProcessingRecord(
                paper_id=paper_id,
                process_type=process_type,
                status=status,
                message=message,
                result_count=parameters_count,
                updated_at=datetime.datetime.utcnow() if status in ['success', 'failed'] else None
            )
            
            session.add(record)
            session.commit()
            
            return record
    
    def update_processing_record(self, record_id, status, message=None, parameters_count=None):
        """
        更新处理记录
        
        参数:
            record_id (int): 记录ID
            status (str): 新状态
            message (str, optional): 新消息
            parameters_count (int, optional): 参数数量
            
        返回:
            bool: 更新是否成功
        """
        with self.get_session() as session:
            record = session.query(ProcessingRecord).filter_by(id=record_id).first()
            
            if not record:
                return False
            
            # 更新字段
            record.status = status
            if message is not None:
                record.message = message
            if parameters_count is not None:
                record.result_count = parameters_count
            
            # 如果状态是完成或失败，设置完成时间
            if status in ['success', 'failed']:
                record.updated_at = datetime.datetime.utcnow()
            
            session.commit()
            return True
    
    # 辅助方法
    def _parse_date(self, date_str):
        """
        解析日期字符串
        
        参数:
            date_str (str): 日期字符串
            
        返回:
            datetime: 解析后的日期对象，解析失败则返回None
        """
        if not date_str:
            return None
        
        try:
            # 尝试不同的格式
            for fmt in ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
                try:
                    return datetime.datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
            
            # 所有格式都失败
            return None
        except Exception:
            return None
    
    def _categorize_parameter(self, parameter_name):
        """
        根据参数名称自动分类
        
        参数:
            parameter_name (str): 参数名称
            
        返回:
            str: 参数类别
        """
        parameter_name = parameter_name.lower()
        
        # 激光参数
        if any(term in parameter_name for term in ['laser', 'wavelength', 'pulse', 'intensity', 'power', 'energy', 'contrast', 'focal']):
            return 'laser'
        
        # 等离子体参数
        elif any(term in parameter_name for term in ['plasma', 'density', 'gas', 'ionization', 'temp']):
            return 'plasma'
        
        # 电子束参数
        elif any(term in parameter_name for term in ['electron', 'beam', 'charge', 'emittance', 'divergence', 'energy']):
            return 'electron_beam'
        
        # 加速场参数
        elif any(term in parameter_name for term in ['field', 'gradient', 'acceleration', 'electric']):
            return 'acceleration_field'
        
        # 实验装置参数
        elif any(term in parameter_name for term in ['setup', 'diagnostic', 'detector', 'camera', 'spectrometer']):
            return 'experimental_setup'
        
        # 默认分类
        return 'other'


# 主函数
if __name__ == "__main__":
    # 测试
    db_manager = DatabaseManager('sqlite:///test.db')
    
    # 添加测试论文
    paper_data = {
        'id': 'test123',
        'title': 'Test Paper on Laser Wakefield Acceleration',
        'authors': ['John Doe', 'Jane Smith'],
        'abstract': 'This is a test abstract.',
        'categories': ['physics.plasm-ph', 'physics.acc-ph'],
        'published': '2023-01-01',
        'updated': '2023-01-02',
        'pdf_url': 'https://arxiv.org/pdf/test123.pdf'
    }
    
    paper = db_manager.add_paper(paper_data)
    print(f"添加的论文ID: {paper.id}")
    
    # 添加测试参数
    parameters = [
        {
            'parameter_name': 'laser_wavelength',
            'value': '800',
            'unit': 'nm',
            'context': 'Ti:Sapphire laser system',
            'confidence_score': 0.95
        },
        {
            'parameter_name': 'plasma_density',
            'value': '1e18',
            'unit': 'cm^-3',
            'context': 'Gas jet',
            'confidence_score': 0.9
        }
    ]
    
    count = db_manager.add_parameters(paper.id, parameters)
    print(f"添加了 {count} 个参数")
    
    # 获取参数
    retrieved_params = db_manager.get_parameters_by_paper(paper.id)
    print("获取的参数:")
    for param in retrieved_params:
        print(f"  {param['parameter_name']}: {param['value']} {param['unit']}") 