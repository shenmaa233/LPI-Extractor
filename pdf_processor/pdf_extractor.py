import os
import PyPDF2
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path):
    """
    从PDF文件中提取文本
    
    参数:
        pdf_path (str): PDF文件的路径
        
    返回:
        str: 提取的文本内容
    """
    if not os.path.exists(pdf_path):
        logger.error(f"PDF文件不存在: {pdf_path}")
        return ""
    
    try:
        text = ""
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            num_pages = len(reader.pages)
            
            logger.info(f"开始提取PDF文本，共 {num_pages} 页: {pdf_path}")
            
            # 遍历所有页面并提取文本
            for page_num in range(num_pages):
                page = reader.pages[page_num]
                page_text = page.extract_text()
                
                if page_text:
                    text += page_text + "\n\n"
                    
            logger.info(f"PDF文本提取完成: {pdf_path}")
            
        return text
    except Exception as e:
        logger.error(f"PDF文本提取失败 {pdf_path}: {str(e)}")
        return ""

def extract_sections(text):
    """
    尝试从论文文本中提取不同的章节
    
    参数:
        text (str): 论文文本
        
    返回:
        dict: 包含不同章节的字典，如摘要、引言、方法、结果、讨论等
    """
    sections = {
        "abstract": "",
        "introduction": "",
        "methods": "",
        "experimental_setup": "",
        "results": "",
        "discussion": "",
        "conclusion": "",
        "full_text": text  # 始终包含完整文本
    }
    
    # 查找常见章节标题
    section_keywords = {
        "abstract": ["abstract"],
        "introduction": ["introduction", "1. introduction", "i. introduction"],
        "methods": ["methods", "methodology", "experimental method", "2. methods", "ii. methods"],
        "experimental_setup": ["experimental setup", "setup", "apparatus", "experimental details"],
        "results": ["results", "3. results", "iii. results", "measurements", "experimental results"],
        "discussion": ["discussion", "4. discussion", "iv. discussion"],
        "conclusion": ["conclusion", "conclusions", "summary", "5. conclusion", "v. conclusion"]
    }
    
    # 尝试查找章节并提取
    lines = text.split('\n')
    current_section = None
    
    for i, line in enumerate(lines):
        # 检查当前行是否是章节标题
        line_lower = line.lower().strip()
        
        for section_name, keywords in section_keywords.items():
            if any(keyword == line_lower or line_lower.startswith(f"{keyword}:") for keyword in keywords):
                current_section = section_name
                break
        
        # 如果找到章节标题，提取该章节内容
        if current_section and i < len(lines) - 1:
            # 从当前行开始，到下一个章节标题之前
            section_text = []
            j = i + 1
            while j < len(lines):
                next_line_lower = lines[j].lower().strip()
                is_next_section = False
                
                for keywords in section_keywords.values():
                    if any(keyword == next_line_lower or next_line_lower.startswith(f"{keyword}:") for keyword in keywords):
                        is_next_section = True
                        break
                
                if is_next_section:
                    break
                
                section_text.append(lines[j])
                j += 1
            
            # 将提取的内容添加到相应章节
            sections[current_section] = "\n".join(section_text).strip()
    
    return sections

def batch_process_pdfs(pdf_dir):
    """
    批量处理指定目录中的所有PDF文件
    
    参数:
        pdf_dir (str): 包含PDF文件的目录
        
    返回:
        list: 每个PDF文件的文本内容和元数据的列表
    """
    if not os.path.exists(pdf_dir):
        logger.error(f"目录不存在: {pdf_dir}")
        return []
    
    results = []
    pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith('.pdf')]
    
    logger.info(f"开始批量处理 {len(pdf_files)} 个PDF文件")
    
    for pdf_file in pdf_files:
        pdf_path = os.path.join(pdf_dir, pdf_file)
        
        # 提取文本
        text = extract_text_from_pdf(pdf_path)
        
        if text:
            # 提取章节
            sections = extract_sections(text)
            
            # 收集结果
            result = {
                "filename": pdf_file,
                "path": pdf_path,
                "sections": sections,
                "text_length": len(text)
            }
            
            results.append(result)
    
    logger.info(f"批量处理完成，成功处理 {len(results)} 个PDF文件")
    return results

if __name__ == "__main__":
    # 测试
    import sys
    
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        text = extract_text_from_pdf(pdf_path)
        print(f"提取的文本长度: {len(text)} 字符")
        print("文本前500个字符:")
        print(text[:500] + "...")
    else:
        print("请提供PDF文件路径作为参数") 