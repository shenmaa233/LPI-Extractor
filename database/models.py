from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import datetime

Base = declarative_base()

class Paper(Base):
    """
    论文信息表
    """
    __tablename__ = 'papers'
    
    id = Column(Integer, primary_key=True)
    arxiv_id = Column(String(50), unique=True, nullable=False)
    title = Column(String(500), nullable=False)
    authors = Column(Text)
    abstract = Column(Text)
    categories = Column(String(255))
    published_date = Column(DateTime)
    updated_date = Column(DateTime)
    pdf_url = Column(String(255))
    local_pdf_path = Column(String(500))
    doi = Column(String(100))  # 添加DOI字段
    
    # 元数据
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.datetime.utcnow)
    processed = Column(Boolean, default=False)
    
    # 关系
    parameters = relationship("LaserParameter", back_populates="paper", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Paper(arxiv_id='{self.arxiv_id}', title='{self.title[:30]}...')>"


class LaserParameter(Base):
    """
    激光参数表
    """
    __tablename__ = 'laser_parameters'
    
    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id'), nullable=False)
    
    # 参数基本信息
    parameter_name = Column(String(100), nullable=False)
    value = Column(String(50), nullable=False)  # 使用字符串以支持各种格式如1e18，10^19等
    unit = Column(String(50))
    context = Column(Text)
    
    # 置信度
    confidence_score = Column(Float)
    
    # 分类信息
    category = Column(String(50))  # 如激光参数、等离子体参数、电子束参数等
    
    # 元数据
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # 关系
    paper = relationship("Paper", back_populates="parameters")
    
    def __repr__(self):
        return f"<LaserParameter(name='{self.parameter_name}', value='{self.value}', unit='{self.unit}')>"


class ExtractedTable(Base):
    """
    提取的表格数据
    """
    __tablename__ = 'extracted_tables'
    
    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id'), nullable=False)
    
    # 表格内容
    table_name = Column(String(100))
    table_content = Column(Text, nullable=False)  # JSON格式的表格内容
    table_context = Column(Text)  # 表格在论文中的上下文描述
    
    # 元数据
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    def __repr__(self):
        return f"<ExtractedTable(paper_id={self.paper_id}, table_name='{self.table_name}')>"


class ProcessingRecord(Base):
    """
    处理记录表，用于跟踪处理状态
    """
    __tablename__ = 'processing_records'
    
    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id'), nullable=False)
    
    # 处理信息
    process_type = Column(String(50), nullable=False)  # 如"text_extraction"、"parameter_extraction"
    status = Column(String(20), nullable=False)  # 如"success"、"failed"、"pending"
    message = Column(Text)
    result_count = Column(Integer, default=0)  # 重命名以保持一致
    
    # 时间信息
    created_at = Column(DateTime, default=datetime.datetime.utcnow)  # 从started_at改为created_at
    updated_at = Column(DateTime)  # 从completed_at改为updated_at
    
    def __repr__(self):
        return f"<ProcessingRecord(paper_id={self.paper_id}, type='{self.process_type}', status='{self.status}')>"


# 创建数据库引擎和会话工厂
def get_engine(db_url='sqlite:///laser_papers.db'):
    """
    创建数据库引擎
    
    参数:
        db_url (str): 数据库URL，默认使用SQLite
        
    返回:
        Engine: SQLAlchemy引擎
    """
    return create_engine(db_url)


def get_session_factory(engine):
    """
    创建会话工厂
    
    参数:
        engine: SQLAlchemy引擎
        
    返回:
        sessionmaker: 会话工厂
    """
    return sessionmaker(bind=engine)


def init_db(engine):
    """
    初始化数据库，创建所有表
    
    参数:
        engine: SQLAlchemy引擎
    """
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    # 创建测试数据库
    engine = get_engine('sqlite:///test_laser_papers.db')
    init_db(engine)
    print("测试数据库初始化完成") 