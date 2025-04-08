"""
激光物理论文参数提取的提示工程模块

此模块包含用于引导LLM从激光物理论文中提取参数的专业提示模板
"""

# 基本参数提取提示
PARAMETER_EXTRACTION_PROMPT = """
You are a specialized scientific assistant for laser physics papers.
Your task is to extract ALL physical parameters from the provided text and return them in EXACT CSV format.

VERY IMPORTANT: Format your ENTIRE response ONLY as a valid CSV with NO additional text:
parameter_name,value,unit,context,confidence_score

RULES FOR CSV OUTPUT:
1. First line MUST be the header row exactly as shown above
2. Each parameter must be on a separate line
3. If any field contains commas, enclose the ENTIRE field in double quotes
4. Confidence score must be a decimal between 0.0 and 1.0
5. DO NOT include any explanations, markdown formatting, or text before or after the CSV data
6. DO NOT include any ```csv or ``` tags

PARAMETERS TO EXTRACT:
- Laser parameters: wavelength, pulse duration, energy, power, intensity, spot size, contrast
- Plasma parameters: density, temperature, length, composition
- Electron beam parameters: energy, charge, emittance, divergence
- Target parameters: material, thickness, density
- Optical parameters: focal length, reflectivity, transmission
- ANY other measurable physical quantities

EXAMPLE OUTPUT:
parameter_name,value,unit,context,confidence_score
laser_wavelength,800,nm,"Ti:Sapphire laser, central wavelength",0.99
pulse_duration,30,fs,"measured with autocorrelator, FWHM",0.95
peak_intensity,1.2e19,W/cm²,"calculated at focal spot",0.85
electron_energy,2.3,GeV,"maximum energy measured at detector",0.9
plasma_density,1.8e18,cm⁻³,"hydrogen gas jet",0.95

Remember: I will ONLY parse the CSV data. Any text outside the CSV format will cause parsing errors.
"""

# 更专业的激光尾场加速参数提取提示
WAKEFIELD_EXTRACTION_PROMPT = """
You are a specialized scientific assistant for laser wakefield acceleration papers.
Your task is to extract ALL physical parameters from the provided text and return them in EXACT CSV format.

VERY IMPORTANT: Format your ENTIRE response ONLY as a valid CSV with NO additional text:
parameter_name,value,unit,context,confidence_score

RULES FOR CSV OUTPUT:
1. First line MUST be the header row exactly as shown above
2. Each parameter must be on a separate line
3. If any field contains commas, enclose the ENTIRE field in double quotes
4. Confidence score must be a decimal between 0.0 and 1.0
5. DO NOT include any explanations, markdown formatting, or text before or after the CSV data
6. DO NOT include any ```csv or ``` tags

PARAMETERS TO EXTRACT (including but not limited to):
- Laser: wavelength, pulse duration, energy, power, intensity, spot size, contrast, focal length
- Plasma: density, temperature, length, profile, composition, ionization state
- Electron beam: energy, energy spread, charge, emittance, divergence, profile
- Accelerating field: gradient, length, phase velocity, transformer ratio
- Experimental setup: target properties, diagnostic details, beam quality measurements

EXAMPLE OUTPUT:
parameter_name,value,unit,context,confidence_score
laser_wavelength,800,nm,"Ti:Sapphire laser system",0.99
pulse_duration,30,fs,"FWHM measured with autocorrelator",0.97
peak_intensity,3.2e18,W/cm²,"Calculated at focal spot",0.9
plasma_density,2e18,cm⁻³,"Gas jet with hydrogen",0.95
max_electron_energy,350,MeV,"Measured with magnetic spectrometer",0.98
electron_charge,10,pC,"Integrated from spectrometer data",0.85

Remember: I will ONLY parse the CSV data. Any text outside the CSV format will cause parsing errors.
"""

# 专门针对光学和激光系统参数的提取提示
LASER_SYSTEM_EXTRACTION_PROMPT = """
You are a specialized scientific assistant for optical and laser systems papers.
Your task is to extract ALL physical parameters from the provided text and return them in EXACT CSV format.

VERY IMPORTANT: Format your ENTIRE response ONLY as a valid CSV with NO additional text:
parameter_name,value,unit,context,confidence_score

RULES FOR CSV OUTPUT:
1. First line MUST be the header row exactly as shown above
2. Each parameter must be on a separate line
3. If any field contains commas, enclose the ENTIRE field in double quotes
4. Confidence score must be a decimal between 0.0 and 1.0
5. DO NOT include any explanations, markdown formatting, or text before or after the CSV data
6. DO NOT include any ```csv or ``` tags

PARAMETERS TO EXTRACT (including but not limited to):
- Laser source: wavelength, bandwidth, mode structure, polarization, coherence
- Temporal properties: pulse duration, repetition rate, timing jitter, stability
- Spatial properties: beam profile, M² factor, Rayleigh range, divergence, beam quality
- Energy metrics: pulse energy, average power, peak power, intensity, fluence
- Optical components: mirror reflectivity, lens focal length, grating specs, coating properties
- System performance: stability, noise characteristics, contrast ratio, efficiency

EXAMPLE OUTPUT:
parameter_name,value,unit,context,confidence_score
central_wavelength,1030,nm,"Yb:YAG laser output",0.99
pulse_duration,250,fs,"Compressed output measured with autocorrelator",0.95
repetition_rate,1,kHz,"System operating condition",0.99
pulse_energy,5,mJ,"After final amplifier",0.97
beam_diameter,8,mm,"Before focusing optic (1/e²)",0.9
focal_spot_size,20,μm,"FWHM at sample plane measured with camera",0.95

Remember: I will ONLY parse the CSV data. Any text outside the CSV format will cause parsing errors.
"""

# 提示模板选择函数
def get_extraction_prompt(paper_topic=None):
    """
    根据论文主题选择最适合的提示模板
    
    参数:
        paper_topic (str, optional): 论文主题或关键词，如 'wakefield', 'laser system' 等
        
    返回:
        str: 选择的提示模板
    """
    if paper_topic:
        paper_topic = paper_topic.lower()
        
        if any(kw in paper_topic for kw in ['wakefield', 'lwfa', 'plasma acceleration']):
            return WAKEFIELD_EXTRACTION_PROMPT
            
        elif any(kw in paper_topic for kw in ['laser system', 'optical', 'amplifier', 'ultrafast']):
            return LASER_SYSTEM_EXTRACTION_PROMPT
    
    # 默认返回基本的参数提取提示
    return PARAMETER_EXTRACTION_PROMPT

# 构建完整提示的函数
def build_full_prompt(text, paper_info=None, topic=None, max_text_length=10000):
    """
    构建完整的提示，包括论文文本和元数据
    
    参数:
        text (str): 论文文本内容
        paper_info (dict, optional): 论文元数据，包括标题、作者等
        topic (str, optional): 论文主题，用于选择提示模板
        max_text_length (int, optional): 最大文本长度，默认10000字符
        
    返回:
        str: 完整的提示
    """
    # 选择提示模板
    extraction_prompt = get_extraction_prompt(topic)
    
    # 截断文本以适应token限制
    if len(text) > max_text_length:
        text = text[:max_text_length] + "...[text truncated due to length]"
    
    # 构建论文元数据部分
    metadata_section = ""
    if paper_info:
        metadata_section = "Paper Information:\n"
        
        if 'title' in paper_info:
            metadata_section += f"Title: {paper_info['title']}\n"
            
        if 'authors' in paper_info:
            if isinstance(paper_info['authors'], list):
                authors_str = ", ".join(paper_info['authors'])
            else:
                authors_str = paper_info['authors']
            metadata_section += f"Authors: {authors_str}\n"
            
        if 'categories' in paper_info:
            if isinstance(paper_info['categories'], list):
                categories_str = ", ".join(paper_info['categories'])
            else:
                categories_str = paper_info['categories']
            metadata_section += f"Categories: {categories_str}\n"
            
        metadata_section += "\n"
    
    # 构建完整提示
    full_prompt = f"{extraction_prompt}\n\n{metadata_section}Paper Text:\n{text}"
    
    return full_prompt

# 提供一个用于测试的示例函数
def get_example_prompt():
    """
    返回一个示例提示，用于测试
    
    返回:
        str: 示例提示
    """
    example_text = """
    Abstract
    We demonstrate laser wakefield acceleration of electrons to multi-GeV energies using a 0.3 PW laser with 30 fs pulse duration. The laser was focused to a peak intensity of 10^19 W/cm^2 onto a 2 cm long hydrogen gas jet with a density of 2×10^18 cm^-3. Electron beams with energies up to 3 GeV were observed, with beam charges of approximately 50 pC. The electron beam had a divergence of 1 mrad and an energy spread of 15%.
    
    Introduction
    Laser wakefield acceleration (LWFA) has made significant progress in recent years as a potential technology for compact particle accelerators. The high accelerating gradients, on the order of 100 GeV/m, allow for the acceleration of electrons to GeV energies over centimeter distances.
    
    Experimental Setup
    The experiment was performed using the Ti:Sapphire laser system operating at a central wavelength of 800 nm. The laser delivered 10 J of energy in a 30 fs pulse (FWHM), resulting in a peak power of 0.3 PW. The laser beam was focused using an f/20 off-axis parabolic mirror to a spot size of 20 μm (FWHM), resulting in a calculated peak intensity of 10^19 W/cm^2.
    """
    
    paper_info = {
        "title": "Multi-GeV Electron Beams from Laser Wakefield Acceleration",
        "authors": ["A. Researcher", "B. Scientist", "C. Physicist"],
        "categories": ["physics.acc-ph", "physics.plasm-ph"]
    }
    
    return build_full_prompt(example_text, paper_info, "wakefield") 