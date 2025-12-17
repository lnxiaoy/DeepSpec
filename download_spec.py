import os
import requests
import zipfile
import time
import re
import concurrent.futures
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote
import urllib3
import random

# ================= 配置区域 =================
BASE_URL = "https://www.3gpp.org/ftp/Specs/archive/38_series/"
DOWNLOAD_ROOT = "./3GPP_38_Series_Docs_Only"
MAX_WORKERS = 8  # 建议 4-10 之间，太高会被服务器 Ban
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
VERIFY_SSL = False 

def get_soup(url, retries=3):
    """请求网页并返回Soup对象 (带重试机制)"""
    for i in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, verify=VERIFY_SSL, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except Exception:
            if i == retries - 1: return None
            time.sleep(1) # 等一秒重试
    return None

def unzip_and_clean(zip_path, extract_to):
    """解压并删除压缩包"""
    try:
        if not zipfile.is_zipfile(zip_path):
            os.remove(zip_path)
            return False
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        os.remove(zip_path)
        return True
    except Exception:
        return False

def process_single_spec(task_info):
    """
    单个线程的工作函数
    task_info: (spec_name, spec_url)
    返回: 处理结果字符串
    """
    spec_name, spec_url = task_info
    
    # 随机休眠一小会儿，避免所有线程瞬间同时发起请求
    time.sleep(random.uniform(0.1, 1.0))

    try:
        # 1. 目标文件夹检查
        target_folder = os.path.join(DOWNLOAD_ROOT, spec_name)
        if not os.path.exists(target_folder):
            os.makedirs(target_folder)
        
        # 如果已存在文件，直接跳过
        if len(os.listdir(target_folder)) > 0:
            return f"[{spec_name}] 跳过 (已存在)"

        # 2. 获取文件列表
        soup = get_soup(spec_url)
        if not soup:
            return f"[{spec_name}] 失败 (无法访问目录)"

        zip_links = []
        for link in soup.find_all('a'):
            href = link.get('href')
            if href and href.lower().endswith('.zip'):
                zip_links.append(href)
        
        if not zip_links:
            return f"[{spec_name}] 跳过 (无 zip 文件)"

        # 3. 排序取最新
        zip_links.sort()
        latest_href = zip_links[-1]
        latest_filename = unquote(latest_href.split('/')[-1])
        full_url = urljoin(spec_url, latest_href)
        local_zip_path = os.path.join(target_folder, latest_filename)

        # 4. 下载
        with requests.get(full_url, headers=HEADERS, stream=True, verify=VERIFY_SSL, timeout=120) as r:
            r.raise_for_status()
            with open(local_zip_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        # 5. 解压
        if unzip_and_clean(local_zip_path, target_folder):
            return f"[{spec_name}] 成功下载: {latest_filename}"
        else:
            return f"[{spec_name}] 解压失败"

    except Exception as e:
        return f"[{spec_name}] 异常: {str(e)[:50]}"

def get_spec_list_v4():
    """使用 V4 版本的正则逻辑获取所有协议目录"""
    print(f"正在扫描主目录: {BASE_URL}")
    soup = get_soup(BASE_URL)
    if not soup: return []

    links = soup.find_all('a')
    pattern = re.compile(r'38\.\d+') # 匹配 38.xxx
    target_folders = []

    for link in links:
        raw_href = link.get('href')
        text = link.text.strip()
        if not raw_href: continue
        
        decoded_href = unquote(raw_href)
        match = pattern.search(decoded_href) or pattern.search(text)
        
        is_zip = decoded_href.lower().endswith('.zip')
        is_pdf = decoded_href.lower().endswith('.pdf')
        
        if match and not is_zip and not is_pdf:
            spec_name = match.group()
            clean_name = decoded_href.strip('/')
            if spec_name in clean_name:
                final_name = clean_name.split('/')[-1]
            else:
                final_name = spec_name
            
            full_url = urljoin(BASE_URL, raw_href)
            target_folders.append((final_name, full_url))
    
    # 去重
    target_folders = list(set(target_folders))
    target_folders.sort(key=lambda x: x[0])
    return target_folders

def main():
    if not os.path.exists(DOWNLOAD_ROOT):
        os.makedirs(DOWNLOAD_ROOT)
    
    # 1. 获取任务列表
    specs = get_spec_list_v4()
    total_specs = len(specs)
    
    if total_specs == 0:
        print("未找到任何目录，请检查网络或调试信息。")
        return
    
    print(f"识别到 {total_specs} 个协议系列。启用 {MAX_WORKERS} 线程开始极速下载...")
    print("-" * 50)

    # 2. 线程池并发执行
    completed_count = 0
    
    # 使用 ThreadPoolExecutor 管理线程
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交所有任务
        future_to_spec = {executor.submit(process_single_spec, spec): spec for spec in specs}
        
        # 当有任务完成时立即处理结果
        for future in concurrent.futures.as_completed(future_to_spec):
            result = future.result()
            completed_count += 1
            
            # 打印进度 (覆盖式打印或换行打印)
            print(f"[{completed_count}/{total_specs}] {result}")

    print("-" * 50)
    print("所有下载任务已完成！")

if __name__ == "__main__":
    main()
