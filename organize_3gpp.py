import os
import shutil
import re
import fitz  # PyMuPDF

def sanitize_folder_name(name):
    """
    清洗厂商名称，移除不能作为文件夹名的字符
    """
    # 移除换行符、回车符
    name = name.strip()
    # 将 / \ : * ? " < > | 替换为下划线
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    # 如果名字太长（比如多个联合厂商），截断一下，避免文件名过长报错
    if len(name) > 50:
        name = name[:50].strip() + "..."
    return name

def organize_pdfs_by_source(folder_path):
    print(f"正在扫描文件夹: {folder_path} ...")
    
    count_moved = 0
    count_unknown = 0

    # 遍历文件夹
    for filename in os.listdir(folder_path):
        if not filename.lower().endswith(".pdf"):
            continue
            
        file_path = os.path.join(folder_path, filename)
        
        try:
            # 打开 PDF
            with fitz.open(file_path) as doc:
                # 只读取第一页，通常 Source 都在第一页顶部
                if len(doc) < 1:
                    continue
                text = doc[0].get_text()

            # 使用正则表达式查找 Source 行
            # 匹配逻辑：找 "Source" 开头，忽略大小写，允许 "Source(s)"，匹配冒号后的内容
            # 3GPP 格式通常是 Source: COMPANY \n Title: ...
            match = re.search(r'Source\(?s?\)?\s*[:：]\s*(.*)', text, re.IGNORECASE)
            
            company_name = "Unknown_Source"
            
            if match:
                # 获取匹配到的厂商名
                raw_name = match.group(1).strip()
                # 有时候 Source 后面可能紧接着下一行的 Title，需要截断
                # 通常 Source 是一行，所以我们只取换行符之前的部分，或者遇到 "Title:" 之前的部分
                if "Title:" in raw_name:
                    raw_name = raw_name.split("Title:")[0]
                
                # 再次按换行符切割，确保只取第一行（防止读到下一行的无关信息）
                raw_name = raw_name.split('\n')[0]
                
                # 清洗文件夹名称
                company_name = sanitize_folder_name(raw_name)
            else:
                print(f"[未找到 Source] {filename}")
                count_unknown += 1
                # 如果你想把找不到厂商的文件也移到一个文件夹，取消下面这行的注释
                # company_name = "Unknown_Source" 
                continue # 如果没找到，就不移动，直接跳过

            # 创建厂商文件夹
            target_dir = os.path.join(folder_path, company_name)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
                
            # 移动文件
            new_file_path = os.path.join(target_dir, filename)
            
            # 防止同名文件覆盖，如果目标已存在，跳过或重命名（这里选择跳过）
            if not os.path.exists(new_file_path):
                shutil.move(file_path, new_file_path)
                print(f"[归档] {filename} -> /{company_name}/")
                count_moved += 1
            else:
                print(f"[跳过] 目标文件已存在: {filename}")

        except Exception as e:
            print(f"[错误] 处理 {filename} 时出错: {e}")

    print(f"\n整理完成！共归档 {count_moved} 个文件。")

# ==========================================
# 在这里修改你的文件夹路径
# ==========================================
target_folder = r'C:\DeepSpec\tdocs\RAN1_123_pdf' 

if os.path.exists(target_folder):
    organize_pdfs_by_source(target_folder)
else:
    print("路径不存在，请检查路径设置。")
