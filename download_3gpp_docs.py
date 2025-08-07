import requests
from bs4 import BeautifulSoup
import os
import zipfile
from urllib.parse import urljoin, urlparse
import concurrent.futures
import threading
import shutil # 新增导入，用于可能创建的临时目录
import sys
import io 

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
# 抑制 InsecureRequestWarning (如果需要)
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 定义 User-Agent 头部，模拟浏览器
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# 用于保护打印输出，防止多线程同时打印造成混乱
print_lock = threading.Lock()

def download_and_extract_single_zip(file_info, download_dir, verify_ssl=False):
    """
    下载并解压单个ZIP文件。
    :param file_info: 包含 file_url 和 file_name 的字典。
    :param download_dir: 下载和解压文件的目标目录（所有文件将解压到这里）。
    :param verify_ssl: 是否验证SSL证书。
    """
    file_url = file_info['url']
    file_name = file_info['name']
    file_path = os.path.join(download_dir, file_name)
    
    # 所有的文件最终都将解压到这个目录
    final_extract_dir = download_dir 

    with print_lock:
        print(f"\n开始下载: {file_name}")

    try:
        # 下载文件
        file_response = requests.get(file_url, stream=True, headers=HEADERS, verify=verify_ssl)
        file_response.raise_for_status()

        with open(file_path, 'wb') as f:
            for chunk in file_response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        with print_lock:
            print(f"下载完成: {file_name}")

        # 解压文件
        if zipfile.is_zipfile(file_path):
            # 创建一个临时目录用于解压，以便我们可以处理内部结构
            temp_extract_dir = os.path.join(download_dir, "temp_zip_extract_" + os.path.splitext(file_name)[0])
            if not os.path.exists(temp_extract_dir):
                os.makedirs(temp_extract_dir)

            with print_lock:
                print(f"开始解压 {file_name} 到临时目录 {temp_extract_dir}")
            try:
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    # 首先解压到临时目录
                    zip_ref.extractall(temp_extract_dir) 
                
                # 遍历临时目录中的所有文件和文件夹
                for root, _, files in os.walk(temp_extract_dir):
                    for f in files:
                        source_file_path = os.path.join(root, f)
                        destination_file_path = os.path.join(final_extract_dir, f) # 直接复制到最终目标目录

                        # 避免覆盖同名文件，可以添加一些处理逻辑，例如重命名
                        # 对于 3GPP 提案，通常不会有同名文件，但这里可以加一个检查
                        if os.path.exists(destination_file_path):
                            with print_lock:
                                print(f"警告: 目标目录已存在文件 '{f}'，跳过或考虑重命名。")
                            # 例如，重命名为 'original_name_from_zip_X.ext'
                            # destination_file_path = os.path.join(final_extract_dir, f"{os.path.splitext(f)[0]}_from_{os.path.splitext(file_name)[0]}{os.path.splitext(f)[1]}")
                            # shutil.move(source_file_path, destination_file_path)
                        else:
                            shutil.move(source_file_path, destination_file_path) # 将文件移动到最终目录

                # 删除临时目录及其内容
                shutil.rmtree(temp_extract_dir)

                with print_lock:
                    print(f"解压完成并清理临时文件: {file_name}")
                
                # 解压后删除原始ZIP文件
                os.remove(file_path)
                with print_lock:
                    print(f"已删除源文件: {file_name}")

            except zipfile.BadZipFile:
                with print_lock:
                    print(f"错误: 文件 {file_name} 不是有效的ZIP文件或已损坏。")
                # 如果解压失败，也要尝试清理临时目录
                if os.path.exists(temp_extract_dir):
                    shutil.rmtree(temp_extract_dir)
            except Exception as e:
                with print_lock:
                    print(f"解压 {file_name} 时发生错误: {e}")
                # 如果解压失败，也要尝试清理临时目录
                if os.path.exists(temp_extract_dir):
                    shutil.rmtree(temp_extract_dir)
        else:
            with print_lock:
                print(f"文件 {file_name} 不是一个有效的ZIP文件，跳过解压。")

    except requests.exceptions.RequestException as e:
        with print_lock:
            print(f"下载 {file_name} 时发生错误: {e}")
    except Exception as e:
        with print_lock:
            print(f"处理 {file_name} 时发生未知错误: {e}")

# download_and_extract_zips 函数保持不变
def download_and_extract_zips(url, download_dir="3GPP_TSGR1_121", max_workers=10, verify_ssl=False):
    print(f"尝试从 {url} 获取文件列表...")

    try:
        response = requests.get(url, headers=HEADERS, verify=verify_ssl)
        response.raise_for_status()  
    except requests.exceptions.RequestException as e:
        print(f"访问URL时发生错误: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    zip_links = [a['href'] for a in soup.find_all('a', href=True) if a['href'].endswith('.zip')]

    if not zip_links:
        print("未找到任何 .zip 文件链接。")
        return

    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
        print(f"创建目录: {download_dir}")

    print(f"找到 {len(zip_links)} 个ZIP文件。")

    files_to_download = []
    for link in zip_links:
        file_url = urljoin(url, link) 
        file_name = os.path.basename(urlparse(file_url).path)
        files_to_download.append({'url': file_url, 'name': file_name})

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(download_and_extract_single_zip, file_info, download_dir, verify_ssl) 
                   for file_info in files_to_download]
        
        for future in concurrent.futures.as_completed(futures):
            pass

# 要下载的URL
target_url = "https://www.3gpp.org/ftp/tsg_ran/WG1_RL1/TSGR1_121/Docs"

# 根据你之前的调试，这里设置为 False。如果你解决了代理证书问题，可以将其设为 True。
# 如果你已经配置了CA_BUNDLE_PATH，可以将其值传入这里。
verify_ssl_setting = False 

if __name__ == "__main__":
    download_and_extract_zips(target_url, max_workers=8, verify_ssl=verify_ssl_setting)
    print("\n所有文件处理完毕。")