import os
import requests
import zipfile
import shutil
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import time
import urllib3 # 新增

# --- 核心修改：禁用 SSL 警告 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 配置区域 ---

# 这里填你要下载的会议 URL
TARGET_URL = "https://www.3gpp.org/ftp/tsg_ran/WG1_RL1/TSGR1_123/Docs"

# 本地保存路径
SAVE_DIR = "./tdocs/RAN1_123"

# 并发线程数
MAX_WORKERS = 8

# ----------------

def get_zip_links(url):
    """解析页面，获取所有 zip 文件的链接"""
    print(f"正在分析页面: {url} ...")
    try:
        # --- 修改点 1: 增加 verify=False ---
        response = requests.get(url, timeout=30, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        links = []
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if href.lower().endswith('.zip'):
                full_url = urljoin(url, href)
                links.append(full_url)
        
        print(f"✅ 找到 {len(links)} 个文档。")
        return links
    except Exception as e:
        print(f"❌ 获取页面失败: {e}")
        return []

def process_file(url, save_dir):
    """
    单个文件的处理逻辑：下载 -> 解压 -> 删除压缩包
    """
    filename = url.split('/')[-1]
    zip_path = os.path.join(save_dir, filename)
    
    # 获取解压后的预期文件名（假设解压后是 .docx/.doc/.pdf）
    # 3GPP 的命名规则通常是 R1-xxxxx.zip -> R1-xxxxx.docx
    # 我们用这一步来做简单的断点续传跳过
    base_name = os.path.splitext(filename)[0]
    
    # 检查是否已经存在同名的 docx/doc/pdf 文件，如果存在则跳过
    potential_files = [
        os.path.join(save_dir, base_name + ".docx"),
        os.path.join(save_dir, base_name + ".doc"),
        os.path.join(save_dir, base_name + ".pdf")
    ]
    
    for f in potential_files:
        if os.path.exists(f):
            # 如果解压后的文件已经存在，直接返回成功，跳过下载
            return True, "Skipped (Exists)"

    try:
        # 1. 下载
        # --- 修改点 2: 增加 verify=False ---
        response = requests.get(url, stream=True, timeout=60, verify=False)
        
        if response.status_code != 200:
            return False, f"HTTP Error {response.status_code}"
        
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # 2. 解压
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(save_dir)
        except zipfile.BadZipFile:
            os.remove(zip_path)
            return False, "文件损坏 (Bad Zip)"
        except Exception as e:
            # 有些文件可能是非标准zip，忽略错误
            return False, f"解压失败: {e}"
        
        # 3. 清理 (删除 zip)
        if os.path.exists(zip_path):
            os.remove(zip_path)
        
        return True, "Success"

    except Exception as e:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        return False, str(e)

def main():
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)
        print(f"创建目录: {SAVE_DIR}")

    # 1. 获取链接列表
    zip_links = get_zip_links(TARGET_URL)
    if not zip_links:
        return

    print(f"开始下载并处理，使用 {MAX_WORKERS} 个线程并发...")
    print("注意：下载 -> 自动解压 -> 自动删除ZIP")

    # 2. 多线程下载
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(process_file, url, SAVE_DIR): url for url in zip_links}
        
        success_count = 0
        fail_count = 0
        skipped_count = 0
        
        for future in tqdm(as_completed(future_to_url), total=len(zip_links), unit="file"):
            url = future_to_url[future]
            try:
                success, msg = future.result()
                if success:
                    if "Skipped" in msg:
                        skipped_count += 1
                    else:
                        success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                fail_count += 1
                tqdm.write(f"异常: {url} -> {e}")

    print("\n" + "="*30)
    print(f"处理完成！")
    print(f"成功下载: {success_count}")
    print(f"跳过已存在: {skipped_count}")
    print(f"失败: {fail_count}")
    print(f"文件保存在: {os.path.abspath(SAVE_DIR)}")
    print("="*30)

if __name__ == "__main__":
    main()
