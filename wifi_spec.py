import os
import re
import shutil
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import win32com.client
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import urllib3
import time

try:
    from pypdf import PdfReader
except ImportError:
    print("❌ 缺少 pypdf 库，请先运行: python.exe -m pip install pypdf")
    exit()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

YEAR = "2026"
MONTH = "07"
GROUP = "0wng"  # 测试 WNG 组
BASE_DIR = f"C:\\DeepSpec\\IEEE_80211_{GROUP}_{YEAR}_{MONTH}"

RAW_DIR = os.path.join(BASE_DIR, "Raw_Documents")
PDF_DIR = os.path.join(BASE_DIR, "PDF_Classified")

MAX_WORKERS = 4

# ================= 核心防御引擎 =================
session = requests.Session()
session.verify = False
session.trust_env = True  

retry_strategy = Retry(
    total=5,  
    backoff_factor=1,
    status_forcelist=[418, 429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
    'Connection': 'close' 
})
# ================================================

KNOWN_VENDORS = [
    "Huawei", "HiSilicon", "Qualcomm", "MediaTek", "Intel", "Broadcom", "Apple", 
    "Samsung", "ZTE", "Ericsson", "Nokia", "NXP", "LG Electronics", "LGE", 
    "OPPO", "vivo", "Sony", "InterDigital", "Cisco", "Xiaomi", "Realtek", "Beken",
    "TCL", "Sharp", "Transsion", "Spreadtrum", "Unisoc", "MaxLinear", "Marvell",
    "Renesas", "Panasonic", "NVIDIA", "Lenovo", "ASUS", "Canon"
]

def sanitize_filename(filename):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    filename = re.sub(r'\s+', " ", filename).strip()
    return filename

def is_pdf_already_exists(raw_name):
    base_name = os.path.splitext(raw_name)[0]
    for root, dirs, files in os.walk(PDF_DIR):
        for file in files:
            if base_name in file and file.endswith(".pdf"):
                return True
    return False

def get_latest_tasks():
    print(f"正在分析 IEEE Mentor 页面 (带分页死循环检测) ...")
    latest_docs_dict = {}
    page_count = 1
    last_page_first_doc = None  
    
    while True:
        print(f" -> 正在抓取第 {page_count} 页...")
        current_url = f"https://mentor.ieee.org/802.11/documents?is_year={YEAR}&is_month={MONTH}&is_group={GROUP}&n={page_count}"
        
        try:
            response = session.get(current_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 【优化点 1】: 彻底踢除 .zip 压缩包，只收核心文档
            valid_exts = ('.ppt', '.pptx', '.doc', '.docx', '.pdf')
            found_on_this_page = 0
            current_page_first_doc = None
            
            for row in soup.find_all('tr'):
                doc_link = None
                for a in row.find_all('a', href=True):
                    href = a['href']
                    if '/dcn/' in href.lower() and any(href.lower().endswith(ext) for ext in valid_exts):
                        doc_link = href
                        break
                
                if not doc_link: continue
                
                found_on_this_page += 1
                if not current_page_first_doc:
                    current_page_first_doc = doc_link

                download_url = doc_link if doc_link.startswith('http') else "https://mentor.ieee.org" + doc_link
                original_filename = doc_link.split('/')[-1].split('?')[0]
                safe_raw_name = sanitize_filename(original_filename)
                
                parts = original_filename.split('-')
                if len(parts) >= 4 and parts[2].isdigit() and parts[3].isdigit():
                    doc_num = parts[2]
                    doc_rev = int(parts[3])
                else:
                    doc_num = safe_raw_name.split('.')[0]
                    doc_rev = 0

                html_vendor = "Unknown_Vendor"
                cols = row.find_all('td')
                if len(cols) >= 6 and cols[5].text.strip():
                    html_vendor = sanitize_filename(cols[5].text.strip())[:40]

                raw_path = os.path.join(RAW_DIR, safe_raw_name)
                
                task_info = {
                    'url': download_url, 'raw': raw_path, 
                    'raw_name': safe_raw_name, 'fallback_vendor': html_vendor, 
                    'doc_num': doc_num, 'rev': doc_rev
                }
                
                if doc_num not in latest_docs_dict or doc_rev > latest_docs_dict[doc_num]['rev']:
                    latest_docs_dict[doc_num] = task_info
            
            if found_on_this_page == 0 or current_page_first_doc == last_page_first_doc:
                print(f"    分页抓取触底，共解析 {page_count} 页。")
                break
                
            last_page_first_doc = current_page_first_doc
            page_count += 1
            time.sleep(1) 
            
        except Exception as e:
            print(f"❌ 获取第 {page_count} 页失败: {e}")
            break

    tasks = list(latest_docs_dict.values())
    print(f"✅ 解析完成！共提取 {len(tasks)} 个最新版独立提案。")
    return tasks

def process_download(task):
    url = task['url']
    raw_path = task['raw']
    raw_name = task['raw_name']
    
    if is_pdf_already_exists(raw_name):
        return True, "PDF已归档", task
    
    if os.path.exists(raw_path):
        if os.path.getsize(raw_path) > 5120: return True, "Raw已就绪", task
        else: os.remove(raw_path)

    try:
        response = session.get(url, stream=True, timeout=(15, 30))
        if response.status_code != 200:
            return False, f"HTTP {response.status_code}", task
        
        # 【优化点 2】: 超大文件（大于 100MB）熔断机制
        content_length = response.headers.get('Content-Length')
        if content_length and int(content_length) > 100 * 1024 * 1024:
            return False, "文件体积过大(>100MB)，已自动拦截", task
            
        with open(raw_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk: f.write(chunk)
        return True, "下载成功", task
    except Exception as e:
        if os.path.exists(raw_path): os.remove(raw_path)
        return False, str(e), task

def classify_and_move_pdf(temp_pdf_path, task):
    raw_name = task['raw_name']
    lower_name = raw_name.lower()
    
    is_cr_lb = False
    vendor = "Unknown_Vendor"

    if re.search(r'(?i)(-|_)(cr|lb\d*|comment|resolution)(s)?(-|_|\.)', lower_name):
        is_cr_lb = True
        
    try:
        reader = PdfReader(temp_pdf_path)
        if len(reader.pages) > 0:
            first_page_text = reader.pages[0].extract_text()
            clean_text = re.sub(r'\s+', ' ', first_page_text)
            
            if "change request" in lower_name or "comment resolution" in lower_name:
                is_cr_lb = True
                
            vendor_positions = []
            for kv in KNOWN_VENDORS:
                for match in re.finditer(r'\b' + re.escape(kv) + r'\b', clean_text, re.IGNORECASE):
                    vendor_positions.append((match.start(), kv))
                    break 
            
            vendor_positions.sort(key=lambda x: x[0])
            
            unique_ordered_vendors = []
            for pos, v in vendor_positions:
                if v not in unique_ordered_vendors:
                    unique_ordered_vendors.append(v)
            
            if unique_ordered_vendors:
                if len(unique_ordered_vendors) == 1:
                    vendor = unique_ordered_vendors[0]
                elif len(unique_ordered_vendors) == 2:
                    vendor = f"{unique_ordered_vendors[0]}_{unique_ordered_vendors[1]}_Joint"
                else:
                    vendor = f"{unique_ordered_vendors[0]}_{unique_ordered_vendors[1]}_etc_Joint"
            else:
                fallback = task['fallback_vendor']
                if fallback and len(fallback.split()) > 3:
                    vendor = "Unknown_Vendor"
                elif fallback and fallback != "Unknown_Vendor":
                    vendor = sanitize_filename(fallback)[:30]

    except Exception:
        fallback = task['fallback_vendor']
        if fallback and len(fallback.split()) > 3:
            vendor = "Unknown_Vendor"
        elif fallback and fallback != "Unknown_Vendor":
            vendor = sanitize_filename(fallback)[:30]

    vendor = sanitize_filename(vendor)
    
    if is_cr_lb:
        target_dir = os.path.join(PDF_DIR, "CR_and_LB")
        target_filename = f"{os.path.splitext(raw_name)[0]}.pdf"
    else:
        target_dir = os.path.join(PDF_DIR, vendor)
        target_filename = f"[{vendor}] {os.path.splitext(raw_name)[0]}.pdf"
        
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, target_filename)
    
    if os.path.exists(target_path):
        os.remove(target_path)
    shutil.move(temp_pdf_path, target_path)

def convert_to_pdf_classified(ready_tasks):
    print("\n" + "="*30)
    print("开始调用本地 Office 引擎转换，并执行智能防沉余分类 ...")
    
    tasks_to_convert = [t for t in ready_tasks if t['raw'].lower().endswith(('.ppt', '.pptx', '.doc', '.docx'))]
    if not tasks_to_convert: return

    powerpoint = word = None
    try:
        for task in tqdm(tasks_to_convert, unit="file", desc="解析与分类"):
            raw_path = task['raw']
            
            if is_pdf_already_exists(task['raw_name']):
                continue

            if not os.path.exists(raw_path) or os.path.getsize(raw_path) < 5120:
                continue

            input_path_abs = os.path.abspath(raw_path)
            temp_pdf_abs = os.path.abspath(os.path.join(RAW_DIR, f"temp_{task['doc_num']}.pdf"))

            try:
                ext = raw_path.lower().split('.')[-1]
                if ext in ['ppt', 'pptx']:
                    if not powerpoint: powerpoint = win32com.client.DispatchEx("Powerpoint.Application")
                    presentation = powerpoint.Presentations.Open(input_path_abs, WithWindow=False)
                    presentation.SaveAs(temp_pdf_abs, 32)
                    presentation.Close()
                elif ext in ['doc', 'docx']:
                    if not word: word = win32com.client.DispatchEx("Word.Application")
                    doc = word.Documents.Open(input_path_abs, Visible=False)
                    doc.SaveAs(temp_pdf_abs, FileFormat=17)
                    doc.Close()
                
                if os.path.exists(temp_pdf_abs):
                    classify_and_move_pdf(temp_pdf_abs, task)
                    
            except Exception:
                if os.path.exists(temp_pdf_abs): os.remove(temp_pdf_abs)
    finally:
        if powerpoint: powerpoint.Quit()
        if word: word.Quit()

def main():
    for d in [RAW_DIR, PDF_DIR]:
        if not os.path.exists(d): os.makedirs(d)

    tasks = get_latest_tasks()
    if not tasks: return

    print(f"\n开始并发下载 (智能跳过已归档提案，已开启 100MB 体积熔断)...")
    ready_tasks = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_task = {executor.submit(process_download, task): task for task in tasks}
        
        for future in tqdm(as_completed(future_to_task), total=len(tasks), unit="file", desc="下载文档"):
            try:
                success, msg, task = future.result()
                if success: 
                    ready_tasks.append(task)
                else:
                    # 如果被拦截或失败，打印出来让你心里有数
                    tqdm.write(f"ℹ️ 跳过 [{task['doc_num']}]: {msg}")
            except Exception as e:
                pass

    if ready_tasks:
        convert_to_pdf_classified(ready_tasks)
        
    print("\n" + "="*30)
    print(f"🎯 整理完毕！打开你的 {os.path.abspath(PDF_DIR)} 看看全新的分类吧！")
    print("="*30)

if __name__ == "__main__":
    main()
