import os
import csv
import logging
import json
from openai import OpenAI
from .prompt_engineering import build_full_prompt, get_extraction_prompt
from .pdf_extractor import extract_text_from_pdf
import datetime

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LLMProcessor:
    """
    使用DeepSeek LLM API从论文中提取参数的处理器
    """
    
    def __init__(self, api_key=None, base_url="https://api.deepseek.com"):
        """
        初始化LLM处理器
        
        参数:
            api_key (str, optional): DeepSeek API密钥，如果未提供，将尝试从环境变量获取
            base_url (str, optional): DeepSeek API基础URL
        """
        # 获取API密钥
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        
        if not self.api_key:
            logger.error("DeepSeek API密钥未提供，请设置DEEPSEEK_API_KEY环境变量或在初始化时提供")
            raise ValueError("DeepSeek API密钥未提供，请设置DEEPSEEK_API_KEY环境变量或在初始化时提供")
        
        # 验证API密钥格式
        if not self.api_key.startswith("sk-"):
            logger.warning(f"DeepSeek API密钥格式可能不正确: {self.api_key[:5]}***")
        
        # 初始化DeepSeek客户端
        try:
            self.client = OpenAI(api_key=self.api_key, base_url=base_url)
            logger.info(f"成功初始化DeepSeek客户端，API基础URL: {base_url}")
        except Exception as e:
            logger.error(f"初始化DeepSeek客户端失败: {str(e)}")
            raise
        
        # 默认使用的模型
        self.model = "deepseek-chat"
        
        # 设置最大文本长度
        self.max_text_length = 10000
        
        logger.info("LLM处理器初始化完成")
    
    def extract_parameters(self, text, paper_info=None, topic=None):
        """
        从文本中提取参数
        
        参数:
            text (str): 论文文本内容
            paper_info (dict, optional): 论文元数据
            topic (str, optional): 论文主题，用于选择适当的提示
            
        返回:
            list: 提取的参数列表，每个参数是一个字典
        """
        # 构建完整提示
        prompt = build_full_prompt(text, paper_info, topic)
        
        try:
            logger.info("=== [DeepSeek API] 开始参数提取 ===")
            logger.info(f"[DeepSeek API] 使用模型: {self.model}")
            logger.info(f"[DeepSeek API] 论文标题: {paper_info.get('title', 'Unknown')}")
            logger.info(f"[DeepSeek API] 提示类型: {topic or '通用激光物理'}")
            logger.info(f"[DeepSeek API] 提示长度: {len(prompt)} 字符")
            logger.info(f"[DeepSeek API] 论文文本长度: {len(text)} 字符")
            
            # 记录API请求详情
            logger.info("[DeepSeek API] 发送请求...")
            request_start_time = datetime.datetime.now()
            
            try:
                # 调用DeepSeek API，添加超时处理
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant"},
                        {"role": "user", "content": prompt}
                    ],
                    stream=False,
                    timeout=60  # 添加60秒超时
                )
                
                # 记录响应时间
                request_end_time = datetime.datetime.now()
                elapsed_time = (request_end_time - request_start_time).total_seconds()
                logger.info(f"[DeepSeek API] 响应时间: {elapsed_time:.2f} 秒")
                
                # 获取响应文本
                response_text = response.choices[0].message.content
                
                # 记录响应状态
                logger.info(f"[DeepSeek API] 响应状态: 成功")
                logger.info(f"[DeepSeek API] 响应长度: {len(response_text)} 字符")
                
                # 记录完整响应，不再只是预览
                logger.info(f"[DeepSeek API] 响应内容: \n{response_text}")
                
                # 处理响应
                parameters = self.parse_csv_response(response_text)
                
                logger.info(f"[DeepSeek API] 参数提取完成，共提取 {len(parameters)} 个参数")
                
                # 记录前几个参数示例
                if parameters:
                    logger.info("[DeepSeek API] 参数示例:")
                    for i, param in enumerate(parameters[:3]):  # 只显示前3个
                        logger.info(f"[DeepSeek API] 参数 {i+1}: {param.get('parameter_name', 'Unknown')} = {param.get('value', 'Unknown')} {param.get('unit', '')}")
                
                logger.info("=== [DeepSeek API] 参数提取结束 ===")
                
                return parameters
                
            except TimeoutError:
                logger.error("[DeepSeek API] 请求超时，60秒内未收到响应")
                logger.error("=== [DeepSeek API] 参数提取异常终止 - 超时 ===")
                return []
                
            except Exception as api_error:
                logger.error(f"[DeepSeek API] API调用错误: {str(api_error)}")
                logger.error(f"[DeepSeek API] 错误类型: {type(api_error).__name__}")
                logger.error("=== [DeepSeek API] 参数提取异常终止 - API错误 ===")
                return []
            
        except Exception as e:
            logger.error(f"[DeepSeek API] 参数提取失败: {str(e)}")
            logger.error(f"[DeepSeek API] 错误类型: {type(e).__name__}")
            logger.error(f"[DeepSeek API] 错误详情: {str(e)}")
            logger.error("=== [DeepSeek API] 参数提取异常终止 ===")
            return []
    
    def parse_csv_response(self, response_text):
        """
        解析API返回的CSV格式响应
        
        参数:
            response_text (str): API返回的文本
            
        返回:
            list: 解析后的参数列表
        """
        parameters = []
        
        logger.info("[参数解析] 开始解析CSV格式响应")
        
        try:
            # 检查响应是否包含CSV格式数据
            if "```csv" in response_text or "```CSV" in response_text:
                logger.info("[参数解析] 检测到CSV格式数据块")
                
                # 提取CSV部分
                csv_parts = []
                in_csv_block = False
                for line in response_text.split("\n"):
                    if line.strip().startswith("```csv") or line.strip().startswith("```CSV"):
                        in_csv_block = True
                        continue
                    elif line.strip() == "```" and in_csv_block:
                        in_csv_block = False
                        continue
                    elif in_csv_block:
                        csv_parts.append(line)
                
                if csv_parts:
                    csv_text = "\n".join(csv_parts)
                    logger.info(f"[参数解析] 提取到CSV数据，长度: {len(csv_text)} 字符")
                else:
                    logger.warning("[参数解析] 找到CSV标记但无内容")
                    return parameters
            else:
                logger.info("[参数解析] 未检测到CSV标记，尝试直接解析为CSV")
                # 直接尝试将响应解析为CSV
                csv_text = response_text.strip()
            
            # 使用CSV模块解析
            import csv
            from io import StringIO
            
            # 确保第一行是标题行
            lines = csv_text.split('\n')
            if len(lines) > 0 and 'parameter_name' in lines[0].lower():
                logger.info("[参数解析] 找到CSV标题行")
            else:
                logger.warning("[参数解析] 未找到标准CSV标题行，这可能导致解析错误")
            
            csv_file = StringIO(csv_text)
            csv_reader = csv.DictReader(csv_file)
            
            # 检查表头
            fieldnames = csv_reader.fieldnames
            if fieldnames:
                logger.info(f"[参数解析] CSV表头: {', '.join(fieldnames)}")
            else:
                logger.warning("[参数解析] CSV没有表头")
            
            # 解析每一行
            row_count = 0
            error_count = 0
            confidence_field = next((f for f in fieldnames if 'confidence' in f.lower()), None) if fieldnames else None
            
            for row in csv_reader:
                row_count += 1
                try:
                    # 确定置信度字段名
                    confidence_value = None
                    if confidence_field and confidence_field in row:
                        try:
                            confidence_value = float(row[confidence_field])
                        except (ValueError, TypeError):
                            confidence_value = 0.8  # 默认值
                    
                    # 进行适当的列映射，更灵活地适应字段名
                    parameter = {
                        "parameter_name": self._get_field_value(row, ["parameter_name", "parameter name", "name", "参数名称", "参数名"]),
                        "value": self._get_field_value(row, ["value", "val", "值"]),
                        "unit": self._get_field_value(row, ["unit", "units", "单位"]),
                        "context": self._get_field_value(row, ["context", "source", "来源", "出处"]),
                        "confidence_score": confidence_value or 0.8,
                        "category": self._categorize_parameter(self._get_field_value(row, ["parameter_name", "name", "参数名称"]))
                    }
                    
                    # 验证参数有效性
                    if parameter["parameter_name"] and parameter["value"]:
                        parameters.append(parameter)
                        if row_count <= 5 or row_count % 10 == 0:  # 记录前5个和每10个参数的日志
                            logger.info(f"[参数解析] 解析参数 #{row_count}: {parameter['parameter_name']} = {parameter['value']} {parameter['unit']}")
                    else:
                        error_count += 1
                        logger.warning(f"[参数解析] 跳过无效参数 #{row_count}: 缺少参数名称或值: {row}")
                except Exception as e:
                    error_count += 1
                    logger.error(f"[参数解析] 解析行 #{row_count} 出错: {str(e)}, 行数据: {row}")
            
            logger.info(f"[参数解析] CSV解析完成，共 {row_count} 行，成功 {len(parameters)} 个参数，失败 {error_count} 个")
            
        except Exception as e:
            logger.error(f"[参数解析] 解析异常: {str(e)}")
            logger.error(f"[参数解析] 原始响应: {response_text[:500]}...")
        
        logger.info(f"[参数解析] 最终解析结果: {len(parameters)} 个参数")
        return parameters
    
    def _get_field_value(self, row, possible_names):
        """获取字段值，尝试多个可能的字段名"""
        for name in possible_names:
            # 检查原始名称
            if name in row and row[name]:
                return row[name]
            
            # 检查大写变体
            upper_name = name.upper()
            if upper_name in row and row[upper_name]:
                return row[upper_name]
            
            # 检查首字母大写变体
            title_name = name.title()
            if title_name in row and row[title_name]:
                return row[title_name]
        
        return ""
        
    def _categorize_parameter(self, parameter_name):
        """根据参数名称自动分类"""
        if not parameter_name:
            return "other"
            
        parameter_name = parameter_name.lower()
        
        # 激光参数
        laser_keywords = ['laser', 'wavelength', 'pulse', 'intensity', 'power', 'energy', 'fluence', 
                          'spot', 'focal', 'beam', 'contrast', 'duration', '激光', '波长', '脉冲']
        
        # 等离子体参数
        plasma_keywords = ['plasma', 'density', 'temperature', 'ionization', 'gas', 
                           'pressure', '等离子体', '密度']
        
        # 电子束参数
        electron_keywords = ['electron', 'beam', 'current', 'charge', 'emittance', 'divergence', 
                             'energy spread', '电子', '束流']
        
        # 分类
        for keyword in laser_keywords:
            if keyword in parameter_name:
                return "laser"
                
        for keyword in plasma_keywords:
            if keyword in parameter_name:
                return "plasma"
                
        for keyword in electron_keywords:
            if keyword in parameter_name:
                return "electron"
        
        return "other"
    
    def save_parameters_to_csv(self, parameters, output_file):
        """
        将参数保存到CSV文件
        
        参数:
            parameters (list): 参数列表
            output_file (str): 输出文件路径
            
        返回:
            bool: 操作是否成功
        """
        if not parameters:
            logger.warning("没有参数可保存")
            return False
        
        try:
            # 确保目录存在
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # 获取所有键作为标题
            all_keys = set()
            for param in parameters:
                all_keys.update(param.keys())
            
            # 按重要性排序键
            important_keys = ['parameter_name', 'value', 'unit', 'context', 'confidence_score']
            header = [key for key in important_keys if key in all_keys]
            header.extend([key for key in all_keys if key not in important_keys])
            
            # 写入CSV
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=header)
                writer.writeheader()
                writer.writerows(parameters)
            
            logger.info(f"参数已保存到: {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"保存参数到CSV失败: {str(e)}")
            return False
    
    def batch_process_papers(self, papers_data, output_dir, topic=None):
        """
        批量处理多篇论文
        
        参数:
            papers_data (list): 论文数据列表，每篇论文是一个字典
            output_dir (str): 输出目录
            topic (str, optional): 论文主题，用于选择提示
            
        返回:
            dict: 处理结果，包含每篇论文的参数和状态
        """
        results = {}
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        for paper in papers_data:
            paper_id = paper.get('id', '')
            filename = paper.get('filename', f"paper_{paper_id}")
            
            logger.info(f"处理论文: {filename}")
            
            try:
                # 获取论文文本
                text = ""
                if 'sections' in paper and 'full_text' in paper['sections']:
                    text = paper['sections']['full_text']
                elif 'text' in paper:
                    text = paper['text']
                
                if not text:
                    logger.warning(f"论文 {filename} 没有文本内容")
                    results[paper_id] = {"status": "error", "message": "没有文本内容"}
                    continue
                
                # 准备论文信息
                paper_info = {
                    "title": paper.get('title', ''),
                    "authors": paper.get('authors', []),
                    "categories": paper.get('categories', [])
                }
                
                # 提取参数
                parameters = self.extract_parameters(text, paper_info, topic)
                
                # 保存参数
                output_file = os.path.join(output_dir, f"{filename}_parameters.csv")
                self.save_parameters_to_csv(parameters, output_file)
                
                # 保存结果
                results[paper_id] = {
                    "status": "success",
                    "parameters_count": len(parameters),
                    "output_file": output_file
                }
                
            except Exception as e:
                logger.error(f"处理论文 {filename} 失败: {str(e)}")
                results[paper_id] = {"status": "error", "message": str(e)}
        
        # 保存汇总结果
        summary_file = os.path.join(output_dir, "processing_summary.json")
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        logger.info(f"批处理完成，结果已保存到: {summary_file}")
        return results

    def extract_parameters_from_file(self, pdf_path, paper_info=None, force_extract=False):
        """
        从PDF文件中提取参数
        
        参数:
            pdf_path (str): PDF文件路径
            paper_info (dict, optional): 论文信息, 默认为None
            force_extract (bool): 是否强制重新提取, 默认为False
            
        返回:
            dict: 包含参数列表和元数据的字典
        """
        try:
            if not os.path.exists(pdf_path):
                logger.error(f"[文件提取] PDF文件不存在: {pdf_path}")
                return {"parameters": [], "metadata": {}}
            
            # 生成输出文件名
            output_dir = os.path.join(os.path.dirname(pdf_path), "extracted")
            os.makedirs(output_dir, exist_ok=True)
            
            basename = os.path.basename(pdf_path)
            filename_no_ext = os.path.splitext(basename)[0]
            output_json = os.path.join(output_dir, f"{filename_no_ext}_parameters.json")
            
            logger.info(f"[文件提取] 处理PDF文件: {pdf_path}")
            logger.info(f"[文件提取] 参数将保存到: {output_json}")
            
            # 检查是否已存在处理结果
            if os.path.exists(output_json) and not force_extract:
                logger.info(f"[文件提取] 发现已有处理结果，加载现有参数: {output_json}")
                try:
                    with open(output_json, 'r', encoding='utf-8') as f:
                        result = json.load(f)
                    
                    params_count = len(result.get("parameters", []))
                    logger.info(f"[文件提取] 成功加载现有参数，共 {params_count} 个")
                    return result
                except Exception as e:
                    logger.warning(f"[文件提取] 加载现有参数文件失败: {str(e)}，将重新提取")
            
            if force_extract:
                logger.info("[文件提取] 强制重新提取参数")
            
            # 提取文本
            logger.info("[文件提取] 开始提取PDF文本内容")
            text = extract_text_from_pdf(pdf_path)
            text_length = len(text)
            
            logger.info(f"[文件提取] PDF文本提取完成，提取了 {text_length} 个字符")
            if text_length < 100:
                logger.warning(f"[文件提取] 提取的文本内容过短 ({text_length} 字符)，可能无法正确解析")
            
            # 准备元数据
            metadata = {
                "extracted_date": datetime.now().isoformat(),
                "pdf_path": pdf_path,
                "text_length": text_length
            }
            
            # 如果有论文信息，添加到元数据中
            if paper_info:
                metadata.update({
                    "title": paper_info.get("title", ""),
                    "authors": paper_info.get("authors", ""),
                    "abstract": paper_info.get("abstract", ""),
                    "arxiv_id": paper_info.get("arxiv_id", ""),
                    "doi": paper_info.get("doi", ""),
                    "year": paper_info.get("year", "")
                })
                logger.info(f"[文件提取] 使用论文信息: {paper_info.get('title', '未知标题')}")
            else:
                logger.info("[文件提取] 未提供论文信息，将仅使用PDF内容")
            
            # 分割长文本
            if text_length > self.max_text_length:
                logger.info(f"[文件提取] 文本超过最大长度 ({text_length} > {self.max_text_length})，将进行分块处理")
                texts = self._split_text(text)
                logger.info(f"[文件提取] 文本已分割为 {len(texts)} 个部分")
                
                # 对每个部分提取参数
                all_parameters = []
                for i, part_text in enumerate(texts):
                    logger.info(f"[文件提取] 处理第 {i+1}/{len(texts)} 部分 ({len(part_text)} 字符)")
                    part_params = self.extract_parameters(part_text, paper_info=paper_info)
                    logger.info(f"[文件提取] 第 {i+1} 部分提取了 {len(part_params)} 个参数")
                    all_parameters.extend(part_params)
                
                # 合并结果并删除重复项
                parameters = self._deduplicate_parameters(all_parameters)
                logger.info(f"[文件提取] 合并后共有 {len(parameters)} 个去重参数 (原始: {len(all_parameters)})")
            else:
                logger.info(f"[文件提取] 文本长度适中 ({text_length} 字符)，一次性处理")
                parameters = self.extract_parameters(text, paper_info=paper_info)
                logger.info(f"[文件提取] 提取了 {len(parameters)} 个参数")
            
            # 保存结果
            result = {
                "parameters": parameters,
                "metadata": metadata
            }
            
            try:
                with open(output_json, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                logger.info(f"[文件提取] 参数已保存到 {output_json}")
            except Exception as e:
                logger.error(f"[文件提取] 保存参数文件失败: {str(e)}")
            
            return result
            
        except Exception as e:
            logger.error(f"[文件提取] 处理PDF文件时出错: {str(e)}")
            import traceback
            logger.error(f"[文件提取] 错误详情: {traceback.format_exc()}")
            return {"parameters": [], "metadata": {"error": str(e)}}

    def _split_text(self, text):
        """
        将长文本分割成多个部分，每部分不超过最大长度
        
        参数:
            text (str): 需要分割的文本
            
        返回:
            list: 分割后的文本列表
        """
        logger.info(f"[文本分割] 开始分割文本，总长度: {len(text)} 字符")
        
        # 简单的按字符数分割
        parts = []
        chunk_size = self.max_text_length
        
        # 尝试按段落分割
        paragraphs = text.split('\n\n')
        logger.info(f"[文本分割] 文本包含 {len(paragraphs)} 个段落")
        
        current_chunk = ""
        
        for para in paragraphs:
            # 如果单个段落就超过了最大长度，需要进一步拆分
            if len(para) > chunk_size:
                logger.warning(f"[文本分割] 发现超长段落 ({len(para)} 字符)，将按句子拆分")
                # 如果当前块不为空，先保存
                if current_chunk:
                    parts.append(current_chunk)
                    current_chunk = ""
                
                # 按句子拆分长段落
                sentences = para.split('. ')
                temp_chunk = ""
                
                for sentence in sentences:
                    if len(temp_chunk) + len(sentence) + 2 <= chunk_size:  # +2 for '. '
                        temp_chunk += sentence + '. '
                    else:
                        if temp_chunk:
                            parts.append(temp_chunk)
                        temp_chunk = sentence + '. '
                
                if temp_chunk:
                    parts.append(temp_chunk)
            else:
                # 正常段落，检查是否加入会超出限制
                if len(current_chunk) + len(para) + 2 <= chunk_size:  # +2 for '\n\n'
                    current_chunk += para + '\n\n'
                else:
                    # 当前块已满，保存并创建新块
                    parts.append(current_chunk)
                    current_chunk = para + '\n\n'
        
        # 添加最后一个块
        if current_chunk:
            parts.append(current_chunk)
        
        logger.info(f"[文本分割] 分割完成，共生成 {len(parts)} 个文本块")
        for i, part in enumerate(parts):
            logger.debug(f"[文本分割] 块 {i+1}: {len(part)} 字符")
        
        return parts
    
    def _deduplicate_parameters(self, parameters):
        """
        删除重复的参数
        
        参数:
            parameters (list): 参数列表
            
        返回:
            list: 去重后的参数列表
        """
        if not parameters:
            logger.info("[参数去重] 没有参数需要去重")
            return []
        
        logger.info(f"[参数去重] 开始去重，原始参数数量: {len(parameters)}")
        
        # 使用参数名和单位作为唯一标识
        unique_params = {}
        duplicates_count = 0
        
        for param in parameters:
            # 创建参数的唯一标识
            name = param.get('parameter_name', '').strip().lower()
            unit = param.get('unit', '').strip().lower()
            value = param.get('value', '').strip().lower()
            
            # 如果没有名称，使用描述作为标识
            if not name and 'description' in param:
                name = param['description'].strip().lower()
            
            # 跳过无效参数
            if not name and not value:
                logger.warning(f"[参数去重] 跳过无效参数: {param}")
                continue
            
            key = f"{name}|{value}|{unit}"
            
            if key in unique_params:
                duplicates_count += 1
                # 保留置信度更高的，或者描述更详细的
                existing_param = unique_params[key]
                existing_confidence = float(existing_param.get('confidence', 0))
                new_confidence = float(param.get('confidence', 0))
                
                existing_desc_len = len(existing_param.get('description', ''))
                new_desc_len = len(param.get('description', ''))
                
                # 如果新参数置信度更高或描述更详细，替换旧参数
                if new_confidence > existing_confidence or (new_confidence == existing_confidence and new_desc_len > existing_desc_len):
                    logger.debug(f"[参数去重] 替换参数 '{name}': 新置信度={new_confidence}, 旧置信度={existing_confidence}")
                    unique_params[key] = param
            else:
                unique_params[key] = param
        
        # 转换回列表
        deduplicated = list(unique_params.values())
        
        # 记录去重结果
        removed_count = duplicates_count
        logger.info(f"[参数去重] 去重完成，移除了 {removed_count} 个重复参数，剩余 {len(deduplicated)} 个")
        
        # 按类别和置信度排序
        sorted_params = sorted(
            deduplicated, 
            key=lambda x: (
                x.get('category', 'other'),
                -float(x.get('confidence', 0))
            )
        )
        
        logger.info(f"[参数去重] 已对参数按类别和置信度排序")
        
        return sorted_params

# 测试函数
def test_parameter_extraction(api_key, text=None):
    """
    测试参数提取功能
    
    参数:
        api_key (str): DeepSeek API密钥
        text (str, optional): 测试文本，如果未提供，将使用默认文本
        
    返回:
        list: 提取的参数列表
    """
    from .prompt_engineering import get_example_prompt
    
    processor = LLMProcessor(api_key=api_key)
    
    if text:
        prompt = text
    else:
        # 使用示例提示
        prompt = get_example_prompt()
    
    response = processor.client.chat.completions.create(
        model=processor.model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": prompt}
        ],
        stream=False
    )
    
    print("API响应:")
    print(response.choices[0].message.content)
    
    # 解析参数
    parameters = processor.parse_csv_response(response.choices[0].message.content)
    
    return parameters

if __name__ == "__main__":
    # 示例用法
    import os
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    
    if api_key:
        parameters = test_parameter_extraction(api_key)
        print(f"提取了 {len(parameters)} 个参数:")
        for param in parameters:
            print(param)
    else:
        print("未设置DEEPSEEK_API_KEY环境变量") 