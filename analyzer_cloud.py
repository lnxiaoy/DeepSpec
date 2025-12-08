import os
import json
import sqlite3
import time
import google.generativeai as genai
from docx import Document
from concurrent.futures import ThreadPoolExecutor, as_completed
from colorama import init, Fore
from google.api_core import retry

init(autoreset=True)

# --- 配置区域 ---
# 替换为你自己的 Google AI Studio API Key
API_KEY = "YOUR_GOOGLE_API_KEY_HERE"

# 使用 Flash 模型，速度最快，且免费额度高
MODEL_NAME = "gemini-1.5-flash" 

DOC_FOLDER = "./tdocs/RAN1_123" # 指向你下载好的文件夹
DB_NAME = "ran1_knowledge_cloud.db" # 新数据库名
MAX_WORKERS = 5 # Google 免费层级限制并发，建议 2-5 之间

# 配置 API
genai.configure(api_key=API_KEY)

# --- 数据库初始化 (一对多结构) ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # 注意：这里的 id 是自增主键，filename 不再唯一
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS document_insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            vendor TEXT,
            topic TEXT,             -- 新增：具体的讨论话题
            stance TEXT,
            key_argument TEXT,
            proposed_parameter TEXT,
            evidence_quote TEXT,
            is_verified BOOLEAN,
            analysis_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    return conn

# --- 读取 Docx ---
def read_docx(file_path):
    try:
        doc = Document(file_path)
        full_text = [p.text for p in doc.paragraphs if len(p.text) > 10]
        # Gemini 1.5 Flash 上下文很大，可以直接丢进去 3-5万字没问题
        # 这里限制一下只是为了节省流量，30000字符通常够了
        return "\n".join(full_text)[:30000]
    except Exception:
        return None

# --- 云端分析核心函数 ---
@retry.Retry() # 自动重试机制，应对网络波动
def analyze_with_gemini(text, filename):
    model = genai.GenerativeModel(MODEL_NAME)
    
    # 强制让模型输出 JSON 数组
    prompt = f"""
    You are a 3GPP RAN1 Standard Expert. 
    Analyze the following TDoc text from file '{filename}'.
    
    Task: Identify ALL distinct technical proposals/observations in this document.
    
    Output Format: return a standard JSON LIST (Array) of objects.
    
    JSON Schema for each object:
    {{
        "topic": "Specific technical topic (e.g. 'DMRS density', 'CSI overhead', 'AI Model generalization')",
        "vendor": "Company Name",
        "stance": "Support / Object / Neutral",
        "key_argument": "Technical reasoning (max 20 words)",
        "proposed_parameter": "Any specific values (e.g. '4 ports', '3dB') or null",
        "evidence_quote": "Exact sentence from text supporting this point"
    }}

    Text content:
    {text}
    """
    
    try:
        # 设置响应类型为 JSON，Gemini 专属功能
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        return response.text
    except Exception as e:
        print(f"{Fore.RED}API Error ({filename}): {e}")
        return None

# --- 校验逻辑 ---
def verify_and_parse(original_text, json_str):
    valid_records = []
    try:
        data_list = json.loads(json_str)
        # 兼容性处理：如果模型只返回了一个对象而不是数组，把它包成数组
        if isinstance(data_list, dict):
            data_list = [data_list]
            
        for item in data_list:
            quote = item.get('evidence_quote', '')
            if quote:
                # 简化校验：去除空格后查找
                clean_quote = quote.replace(" ", "").strip()[:50] # 只匹配前50个字符增加容错
                clean_original = original_text.replace(" ", "").replace("\n", "")
                
                if clean_quote in clean_original:
                    valid_records.append(item)
    except json.JSONDecodeError:
        pass
        
    return valid_records

# --- 线程工作函数 ---
def worker(file_path, filename):
    # 1. 读取
    content = read_docx(file_path)
    if not content: return None

    # 2. 调用 API
    # 免费版 API 限制每分钟请求数 (RPM)，加一点延迟防止 429 错误
    time.sleep(2) 
    json_result = analyze_with_gemini(content, filename)
    
    if json_result:
        # 3. 校验
        valid_data = verify_and_parse(content, json_result)
        return (filename, valid_data)
    return None

# --- 主程序 ---
def main():
    conn = init_db()
    cursor = conn.cursor()
    
    files = [f for f in os.listdir(DOC_FOLDER) if f.endswith(".docx")]
    # 过滤掉已经分析过的文件（为了演示，这里先简单全量跑，实际建议做去重）
    
    print(f"{Fore.GREEN}=== 启动云端分析引擎 (Gemini Flash) ===")
    print(f"目标文件数: {len(files)} | 并发线程: {MAX_WORKERS}")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_file = {
            executor.submit(worker, os.path.join(DOC_FOLDER, f), f): f 
            for f in files
        }
        
        success_count = 0
        total_points = 0
        
        for future in as_completed(future_to_file):
            filename = future_to_file[future]
            try:
                result = future.result()
                if result:
                    name, points_list = result
                    
                    if points_list:
                        # 批量入库
                        for pt in points_list:
                            cursor.execute('''
                                INSERT INTO document_insights 
                                (filename, vendor, topic, stance, key_argument, proposed_parameter, evidence_quote, is_verified)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                name, 
                                pt.get('vendor'),
                                pt.get('topic'), # 重点：现在有了具体话题
                                pt.get('stance'),
                                pt.get('key_argument'),
                                pt.get('proposed_parameter'),
                                pt.get('evidence_quote'),
                                True
                            ))
                        conn.commit()
                        print(f"{Fore.GREEN}✅ {name}: 提取到 {len(points_list)} 个观点")
                        success_count += 1
                        total_points += len(points_list)
                    else:
                        print(f"{Fore.YELLOW}⚠️ {name}: API返回有效但无通过校验的观点")
                else:
                    print(f"{Fore.RED}❌ {filename}: 分析失败")
            except Exception as e:
                print(f"系统异常: {e}")

    conn.close()
    print("="*40)
    print(f"分析完成！共处理 {success_count} 个文件，入库 {total_points} 个技术观点。")
    print(f"数据库: {DB_NAME}")

if __name__ == "__main__":
    main()
