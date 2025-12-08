import os
import requests
import zipfile
import shutil
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import time
import urllib3

# 禁用安全请求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# --- 配置区域 ---

# 这里填你要下载的会议 URL (RAN1, RAN2, RAN4 都可以)
# 例如 RAN1 #123: https://www.3gpp.org/ftp/tsg_ran/WG1_RL1/TSGR1_123/Docs
TARGET_URL = "https://www.3gpp.org/ftp/tsg_ran/WG1_RL1/TSGR1_123/Docs"

# 本地保存路径 (脚本会自动创建)
# 建议按会议命名，比如 ./tdocs/RAN1_123
SAVE_DIR = "E:/000_3GPP_Download/tdocs/RAN1_123"

# 并发线程数 (建议 5-10，太高可能会被 3GPP 服务器封 IP)
MAX_WORKERS = 8

# ----------------

def get_zip_links(url):
    """解析页面，获取所有 zip 文件的链接"""
    print(f"正在分析页面: {url} ...")
    try:
        # 3GPP 服务器有时响应慢，设置超时
        response = requests.get(url, timeout=30, verify=False) # 加上 verify=False
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        links = []
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            # 只下载 zip 文件，忽略其他链接
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
    
    # 简单的去重判断：
    # 如果对应解压后的 docx/doc/pdf 已经存在，就不下载了
    # 注意：这里假设 zip 包里的文件名和 zip 本身类似（R1-xxxxx.zip -> R1-xxxxx.docx）
    # 为了保险，我们还是下载，除非 zip 包本身还在
    
    base_name = os.path.splitext(filename)[0]
    # 检查目录下是否已经有同名的 docx/zip，如果有，可能说明已经下过了
    # (这一步根据需求可精细化，这里为了简单，不做强力去重，覆盖下载)

    try:
        # 1. 下载
        response = requests.get(url, stream=True, timeout=60, verify=False) # 加上 verify=False
        if response.status_code != 200:
            return False, f"HTTP Error {response.status_code}"
        
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # 2. 解压
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # 3GPP 的 zip 包有时候里面是一个文件夹，有时候直接是文件
                # 我们直接解压到当前目录
                zip_ref.extractall(save_dir)
        except zipfile.BadZipFile:
            os.remove(zip_path) # 坏的文件删掉
            return False, "文件损坏 (Bad Zip)"
        
        # 3. 清理 (删除 zip)
        os.remove(zip_path)
        
        return True, "Success"

    except Exception as e:
        # 出错了也要尝试清理残余的 zip
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
    # 使用 tqdm 显示进度条
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交所有任务
        future_to_url = {executor.submit(process_file, url, SAVE_DIR): url for url in zip_links}
        
        success_count = 0
        fail_count = 0
        
        # 进度条
        for future in tqdm(as_completed(future_to_url), total=len(zip_links), unit="file"):
            url = future_to_url[future]
            try:
                success, msg = future.result()
                if success:
                    success_count += 1
                else:
                    fail_count += 1
                    # 可以取消注释下面这行来查看具体失败原因
                    # tqdm.write(f"失败: {url.split('/')[-1]} -> {msg}")
            except Exception as e:
                fail_count += 1
                tqdm.write(f"异常: {url} -> {e}")

    print("\n" + "="*30)
    print(f"处理完成！")
    print(f"成功: {success_count}")
    print(f"失败: {fail_count}")
    print(f"文件保存在: {os.path.abspath(SAVE_DIR)}")
    print("="*30)

if __name__ == "__main__":
    main()
