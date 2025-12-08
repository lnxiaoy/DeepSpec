import os
import json
import sqlite3
import urllib3
import requests
import time
import google.generativeai as genai
from docx import Document
from concurrent.futures import ThreadPoolExecutor, as_completed
from colorama import init, Fore
from google.api_core import retry

init(autoreset=True)
# ==========================================
# 🛑 核心修复区：全局禁用 SSL 验证
# ==========================================
# 1. 禁用警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 2. 暴力打补丁：强制所有 requests 请求都不验证证书
# 这是解决 SSLCertVerificationError 的终极方案
old_merge_environment_settings = requests.Session.merge_environment_settings

def merge_environment_settings(self, url, proxies, stream, verify, cert):
    # 无论原来要求什么，这里强制把 verify 设为 False
    return old_merge_environment_settings(self, url, proxies, stream, False, cert)

requests.Session.merge_environment_settings = merge_environment_settings
# ==========================================


# --- 配置区域 ---
# 替换为你自己的 Google AI Studio API Key
API_KEY = ""

# 使用 Flash 模型，速度最快，且免费额度高
MODEL_NAME = "gemini-2.5-flash" 

DOC_FOLDER = "E:/000_3GPP_Download/tdocs/RAN1_123" # 指向你下载好的文件夹
DB_NAME = "ran1_knowledge_cloud.db" # 新数据库名
MAX_WORKERS = 1 # Google 免费层级限制并发，建议 2-5 之间

# 配置 API
genai.configure(api_key=API_KEY, transport="rest")

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
    print(f"{Fore.CYAN}[{filename}] 正在连接 Google API...", end="\r") # 增加调试打印
    
    # --- 核心修改 2: 强制使用 REST 协议 ---
    # 这能解决 99% 的“卡住”问题
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
        print(f"{Fore.BLUE}[{filename}] API 响应成功！      ") # 空格是为了覆盖之前的打印
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

    print(f"{Fore.YELLOW}[{filename}] 冷却中 (等待API配额)...")
    time.sleep(5)
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
    
    # 获取所有 .docx 文件
    all_files = [f for f in os.listdir(DOC_FOLDER) if f.endswith(".docx")]
    
    # --- 修改点：只取前 10 个文件进行测试 ---
    # 如果文件少于 10 个，它会自动取全部，不会报错
    files_to_process = all_files[:10] 
    
    print(f"{Fore.GREEN}=== 启动云端分析引擎 (Gemini Flash) ===")
    print(f"模式: 快速验证 (测试前 10 篇)") # 提示一下当前是测试模式
    print(f"目标文件数: {len(files_to_process)} | 并发线程: {MAX_WORKERS}")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_file = {
            executor.submit(worker, os.path.join(DOC_FOLDER, f), f): f 
            for f in files_to_process
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
