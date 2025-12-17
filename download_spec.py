import os
import requests
import zipfile
import time
import re  # 引入正则模块
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote
import urllib3

# ================= 配置区域 =================
BASE_URL = "https://www.3gpp.org/ftp/Specs/archive/38_series/"
DOWNLOAD_ROOT = "./3GPP_38_Series_Docs_Only"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
VERIFY_SSL = False 

def get_soup(url):
    try:
        response = requests.get(url, headers=HEADERS, verify=VERIFY_SSL, timeout=30)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"[Error] 连接失败 {url}: {e}")
        return None

def unzip_and_clean(zip_path, extract_to):
    try:
        if not zipfile.is_zipfile(zip_path):
            os.remove(zip_path)
            return
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        os.remove(zip_path) # 删除源文件
    except Exception:
        pass

def process_spec_folder(spec_url, spec_name):
    soup = get_soup(spec_url)
    if not soup: return

    zip_links = []
    for link in soup.find_all('a'):
        href = link.get('href')
        if href and href.lower().endswith('.zip'):
            zip_links.append(href)
    
    if not zip_links: return

    # 排序取最新
    zip_links.sort()
    latest_href = zip_links[-1]
    latest_filename = unquote(latest_href.split('/')[-1])
    
    target_folder = os.path.join(DOWNLOAD_ROOT, spec_name)
    if not os.path.exists(target_folder):
        os.makedirs(target_folder)
    
    # 检查是否已有文件
    if len(os.listdir(target_folder)) > 0:
        return

    full_url = urljoin(spec_url, latest_href)
    local_zip_path = os.path.join(target_folder, latest_filename)

    print(f"--> [{spec_name}] 下载: {latest_filename}")

    try:
        with requests.get(full_url, headers=HEADERS, stream=True, verify=VERIFY_SSL, timeout=60) as r:
            r.raise_for_status()
            with open(local_zip_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        unzip_and_clean(local_zip_path, target_folder)
    except Exception as e:
        print(f"    [Failed]: {e}")
        if os.path.exists(local_zip_path): os.remove(local_zip_path)

def main():
    if not os.path.exists(DOWNLOAD_ROOT):
        os.makedirs(DOWNLOAD_ROOT)
    
    print(f"正在连接: {BASE_URL}")
    soup = get_soup(BASE_URL)
    if not soup: return

    links = soup.find_all('a')
    
    # === 调试：打印链接总数 ===
    print(f"页面共找到 {len(links)} 个链接对象")
    
    # 定义正则表达式：匹配 "38." 后面跟着数字
    # 例如 38.211, 38.101-1
    pattern = re.compile(r'38\.\d+')

    target_folders = []
    
    print("\n--- [Debug] 分析前 15 个链接 ---")
    
    for i, link in enumerate(links):
        raw_href = link.get('href')
        text = link.text.strip()
        
        if not raw_href: continue
        
        # 1. 解码 (关键步骤，处理 %2E 等符号)
        decoded_href = unquote(raw_href)
        
        # 调试打印前15个，看看长什么样
        if i < 15:
            print(f"[{i}] Text='{text}' | Href='{raw_href}' | Decoded='{decoded_href}'")

        # 2. 核心判断逻辑
        # 只要 href 或 text 里包含 "38.xxx" 这种模式，我们就认为是目标
        # 并且排除 zip 文件 (那是最终文件，不是目录)
        match = pattern.search(decoded_href) or pattern.search(text)
        
        is_zip = decoded_href.lower().endswith('.zip')
        is_pdf = decoded_href.lower().endswith('.pdf')
        
        if match and not is_zip and not is_pdf:
            # 提取纯净的名字
            spec_name = match.group() # 获取匹配到的 '38.211'
            
            # 如果名字带短横线后缀 (如 38.101-1)，我们尝试从链接里提取更完整的名字
            # 这里简单处理：直接用 decoded_href 去掉末尾斜杠后的名字
            clean_name = decoded_href.strip('/')
            # 如果 clean_name 包含 spec_name，就用 clean_name (更完整)
            if spec_name in clean_name:
                final_name = clean_name.split('/')[-1]
            else:
                final_name = spec_name

            full_url = urljoin(BASE_URL, raw_href)
            target_folders.append((final_name, full_url))

    # 去重
    target_folders = list(set(target_folders))
    target_folders.sort(key=lambda x: x[0])

    print("-" * 30)
    print(f"成功识别到 {len(target_folders)} 个协议系列文件夹！")
    
    if len(target_folders) == 0:
        print("错误：依然未找到文件夹。请检查上方 Debug 日志中 'Decoded' 列的内容格式。")
        return

    print("开始下载处理...")
    print("-" * 30)

    for i, (spec_name, spec_url) in enumerate(target_folders):
        # 打印进度
        if i % 10 == 0:
            print(f"进度 [{i}/{len(target_folders)}] ...")
        process_spec_folder(spec_url, spec_name)

    print("-" * 30)
    print("所有任务完成！")

if __name__ == "__main__":
    main()
