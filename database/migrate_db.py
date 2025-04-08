"""
数据库结构迁移脚本

这个脚本用于在模型变更后更新数据库结构
"""

import os
import sys
import logging
import sqlite3
import datetime

# 添加父目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def migrate_processing_records_table():
    """
    迁移处理记录表，更新字段名称
    """
    # 数据库路径
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../laser_papers.db')
    
    if not os.path.exists(db_path):
        logger.error(f"数据库文件不存在: {db_path}")
        return False
    
    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='processing_records'")
        if not cursor.fetchone():
            logger.warning("processing_records表不存在，无需迁移")
            conn.close()
            return True
        
        # 获取表结构
        cursor.execute("PRAGMA table_info(processing_records)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # 检查是否需要迁移
        needs_migration = ('started_at' in columns or 'completed_at' in columns or 'parameters_count' in columns)
        
        if not needs_migration:
            logger.info("表结构已是最新，无需迁移")
            conn.close()
            return True
        
        # 创建备份表
        logger.info("开始迁移处理记录表...")
        
        # 创建新表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS processing_records_new (
            id INTEGER PRIMARY KEY,
            paper_id INTEGER NOT NULL,
            process_type TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            result_count INTEGER DEFAULT 0,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY (paper_id) REFERENCES papers (id)
        )
        """)
        
        # 迁移数据
        if 'started_at' in columns and 'completed_at' in columns and 'parameters_count' in columns:
            cursor.execute("""
            INSERT INTO processing_records_new (id, paper_id, process_type, status, message, result_count, created_at, updated_at)
            SELECT id, paper_id, process_type, status, message, parameters_count, started_at, completed_at FROM processing_records
            """)
        elif 'started_at' in columns and 'completed_at' in columns:
            cursor.execute("""
            INSERT INTO processing_records_new (id, paper_id, process_type, status, message, result_count, created_at, updated_at)
            SELECT id, paper_id, process_type, status, message, 0, started_at, completed_at FROM processing_records
            """)
        elif 'parameters_count' in columns:
            cursor.execute("""
            INSERT INTO processing_records_new (id, paper_id, process_type, status, message, result_count, created_at, updated_at)
            SELECT id, paper_id, process_type, status, message, parameters_count, created_at, updated_at FROM processing_records
            """)
        
        # 重命名表
        cursor.execute("DROP TABLE processing_records")
        cursor.execute("ALTER TABLE processing_records_new RENAME TO processing_records")
        
        # 提交更改
        conn.commit()
        conn.close()
        
        logger.info("处理记录表迁移完成")
        return True
        
    except Exception as e:
        logger.error(f"迁移失败: {str(e)}")
        return False

def migrate_papers_add_doi():
    """
    迁移papers表，添加doi字段
    """
    # 数据库路径
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../laser_papers.db')
    
    if not os.path.exists(db_path):
        logger.error(f"数据库文件不存在: {db_path}")
        return False
    
    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='papers'")
        if not cursor.fetchone():
            logger.warning("papers表不存在，无需迁移")
            conn.close()
            return True
        
        # 检查doi列是否已存在
        cursor.execute("PRAGMA table_info(papers)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'doi' in columns:
            logger.info("doi字段已存在，无需迁移")
            conn.close()
            return True
        
        # 添加doi列
        logger.info("开始添加doi字段到papers表...")
        cursor.execute("ALTER TABLE papers ADD COLUMN doi TEXT")
        
        # 提交更改
        conn.commit()
        conn.close()
        
        logger.info("papers表添加doi字段完成")
        return True
        
    except Exception as e:
        logger.error(f"迁移失败: {str(e)}")
        return False

if __name__ == "__main__":
    # 运行迁移
    print("开始执行数据库迁移...")
    
    # 迁移处理记录表
    processing_records_success = migrate_processing_records_table()
    
    # 迁移papers表添加doi字段
    papers_doi_success = migrate_papers_add_doi()
    
    if processing_records_success and papers_doi_success:
        print("迁移成功完成")
    else:
        print("迁移失败，请检查日志") 