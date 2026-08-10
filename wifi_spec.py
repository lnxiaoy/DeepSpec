import os
import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import win32com.client
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import urllib3
import time

# 禁用安全请求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

YEAR = "2026"
MONTH = "07"
GROUP = "00bn"  # TGbn 7月会
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

def sanitize_filename(filename):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    filename = re.sub(r'\s+', " ", filename).strip()
    return filename

def get_latest_tasks():
    print(f"正在分析 IEEE Mentor 页面 (组别: {GROUP}, 年月: {YEAR}-{MONTH}) ...")
    latest_docs_dict = {}
    
    page_count = 1
    last_page_first_doc = None  # 【新增】用来记录上一页的第一个文档，防止死循环
    
    while True:
        print(f" -> 正在抓取第 {page_count} 页...")
        
        current_url = f"https://mentor.ieee.org/802.11/documents?is_year={YEAR}&is_month={MONTH}&is_group={GROUP}&n={page_count}"
        
        try:
            response = session.get(current_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            valid_exts = ('.ppt', '.pptx', '.doc', '.docx', '.pdf', '.zip')
            found_on_this_page = 0
            current_page_first_doc = None  # 【新增】本页的第一个文档
            
            for row in soup.find_all('tr'):
                doc_link = None
                for a in row.find_all('a', href=True):
                    href = a['href']
                    if '/dcn/' in href.lower() and any(href.lower().endswith(ext) for ext in valid_exts):
                        doc_link = href
                        break
                
                if not doc_link: continue
                
                found_on_this_page += 1
                
                # 【新增】记录本页首个抓取到的链接指纹
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

                cols = row.find_all('td')
                vendor = "Unknown_Vendor"
                if len(cols) >= 6:
                    v_text = cols[5].text.strip()
                    if v_text: vendor = sanitize_filename(v_text)[:40]
                elif len(cols) >= 2: 
                    v_text = cols[-1].text.strip()
                    if v_text and len(v_text) < 40 and "2026" not in v_text:
                        vendor = sanitize_filename(v_text)

                raw_path = os.path.join(RAW_DIR, safe_raw_name)
                pdf_filename = f"[{vendor}] {os.path.splitext(safe_raw_name)[0]}.pdf"
                pdf_path = os.path.join(PDF_DIR, pdf_filename)
                
                task_info = {
                    'url': download_url, 'raw': raw_path, 'pdf': pdf_path,
                    'vendor': vendor, 'doc_num': doc_num, 'rev': doc_rev
                }
                
                if doc_num not in latest_docs_dict or doc_rev > latest_docs_dict[doc_num]['rev']:
                    latest_docs_dict[doc_num] = task_info
            
            # 退出机制 1：这一页真的一无所有
            if found_on_this_page == 0:
                print(f"    当前第 {page_count} 页未发现提案，触底结束。")
                break
                
            # 【核心退出机制 2】：这一页的第一个提案和上一页一模一样，说明掉进 Mentor 系统的无限循环 Bug 了！
            if current_page_first_doc == last_page_first_doc:
                print(f"    检测到第 {page_count} 页数据与上一页循环重复，已到达真实最后一页，强制刹车！")
                break
                
            last_page_first_doc = current_page_first_doc
            page_count += 1
            time.sleep(1) # 礼貌延时防封
            
        except Exception as e:
            print(f"❌ 获取第 {page_count} 页失败: {e}")
            break

    tasks = list(latest_docs_dict.values())
    print(f"✅ 全部分页解析完成！共提取 {len(tasks)} 个最新版独立提案。")
    return tasks

def process_download(task):
    url = task['url']
    raw_path = task['raw']
    pdf_path = task['pdf']
    
    if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
        return True, "PDF已就绪", task
    
    if os.path.exists(raw_path):
        if os.path.getsize(raw_path) > 5120: return True, "Raw已就绪", task
        else: os.remove(raw_path)

    try:
        response = session.get(url, stream=True, timeout=(15, 30))
        if response.status_code != 200:
            return False, f"HTTP {response.status_code}", task
            
        with open(raw_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk: f.write(chunk)
        return True, "下载成功", task
    except Exception as e:
        if os.path.exists(raw_path): os.remove(raw_path)
        return False, str(e), task

def convert_to_pdf_classified(ready_tasks):
    print("\n" + "="*30)
    print("开始调用本地 Office 引擎转换为 PDF (平铺模式) ...")
    
    tasks_to_convert = [t for t in ready_tasks if t['raw'].lower().endswith(('.ppt', '.pptx', '.doc', '.docx'))]
    if not tasks_to_convert: return

    powerpoint = word = None
    try:
        for task in tqdm(tasks_to_convert, unit="file", desc="转换 PDF"):
            raw_path, pdf_path = task['raw'], task['pdf']
            if not os.path.exists(raw_path) or os.path.getsize(raw_path) < 5120 or os.path.exists(pdf_path):
                continue

            os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
            input_path_abs, output_path_abs = os.path.abspath(raw_path), os.path.abspath(pdf_path)

            try:
                ext = raw_path.lower().split('.')[-1]
                if ext in ['ppt', 'pptx']:
                    if not powerpoint: powerpoint = win32com.client.DispatchEx("Powerpoint.Application")
                    presentation = powerpoint.Presentations.Open(input_path_abs, WithWindow=False)
                    presentation.SaveAs(output_path_abs, 32)
                    presentation.Close()
                elif ext in ['doc', 'docx']:
                    if not word: word = win32com.client.DispatchEx("Word.Application")
                    doc = word.Documents.Open(input_path_abs, Visible=False)
                    doc.SaveAs(output_path_abs, FileFormat=17)
                    doc.Close()
            except Exception: pass 
    finally:
        if powerpoint: powerpoint.Quit()
        if word: word.Quit()

def main():
    for d in [RAW_DIR, PDF_DIR]:
        if not os.path.exists(d): os.makedirs(d)

    tasks = get_latest_tasks()
    if not tasks: return

    print(f"\n开始使用 {MAX_WORKERS} 个线程并发下载 (带代理自动重试护甲)...")
    ready_tasks = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_task = {executor.submit(process_download, task): task for task in tasks}
        
        for future in tqdm(as_completed(future_to_task), total=len(tasks), unit="file", desc="处理文档"):
            try:
                success, msg, task = future.result()
                if success: 
                    ready_tasks.append(task)
                else:
                    tqdm.write(f"❌ 失败 [{task['vendor']}_{task['doc_num']}]: {msg}")
            except Exception as e:
                tqdm.write(f"❌ 严重异常: {e}")

    if ready_tasks:
        convert_to_pdf_classified(ready_tasks)
        
    print("\n" + "="*30)
    print(f"🎯 处理完毕！所有平铺 PDF 存放于: {os.path.abspath(PDF_DIR)}")
    print("="*30)

if __name__ == "__main__":
    main()
