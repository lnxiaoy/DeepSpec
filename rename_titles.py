import os
import fitz  # PyMuPDF
import re

def sanitize_filename(name):
    """
    清洗文件名，移除非法字符，并限制长度
    """
    # 替换换行符为空格
    name = name.replace('\n', ' ').replace('\r', ' ')
    # 移除多余空格
    name = re.sub(r'\s+', ' ', name).strip()
    # 移除非法字符 \ / : * ? " < > |
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    # 限制长度（Windows路径限制），保留前80个字符，留点给Tdoc号
    if len(name) > 80:
        name = name[:80] + "..."
    return name

def extract_title_from_pdf(file_path):
    try:
        with fitz.open(file_path) as doc:
            if len(doc) < 1:
                return None
            
            # 获取第一页文本
            text = doc[0].get_text()
            
            # === 3GPP 标题提取逻辑 ===
            
            # 1. 寻找 Title 的开始位置
            match_start = re.search(r'Title\s*[:：]', text, re.IGNORECASE)
            if not match_start:
                return None
            
            start_index = match_start.end()
            remaining_text = text[start_index:]
            
            # 2. 定义结束关键词
            stop_words = [
                r'Document\s+for\s*[:：]', 
                r'Agenda\s+Item\s*[:：]', 
                r'Source\s*[:：]', 
                r'Contact\s*[:：]'
            ]
            
            min_end_index = len(remaining_text)
            
            # 寻找最近的一个结束关键词
            for pattern in stop_words:
                match_end = re.search(pattern, remaining_text, re.IGNORECASE)
                if match_end:
                    if match_end.start() < min_end_index:
                        min_end_index = match_end.start()
            
            # 3. 截取并清洗
            raw_title = remaining_text[:min_end_index]
            return sanitize_filename(raw_title)
            
    except Exception as e:
        print(f"[读取错误] {os.path.basename(file_path)}: {e}")
        return None

def recursive_batch_rename(root_folder):
    print(f"🚀 开始递归扫描文件夹: {root_folder}")
    count_success = 0
    count_skipped = 0
    
    # os.walk 实现递归：root是当前目录，dirs是子文件夹，files是文件
    for root, dirs, files in os.walk(root_folder):
        print(f"📂 正在处理目录: {root}")
        
        for filename in files:
            # 只处理 PDF
            if not filename.lower().endswith(".pdf"):
                continue
            
            file_path = os.path.join(root, filename)
            
            # 提取标题
            extracted_title = extract_title_from_pdf(file_path)
            
            if extracted_title:
                # 简单的查重逻辑：如果提取的标题已经在文件名里了，大概率是处理过了
                # 忽略大小写比较
                if extracted_title.lower() in filename.lower():
                    # print(f"   [跳过] 似乎已重命名: {filename}")
                    count_skipped += 1
                    continue

                # 构造新文件名
                original_name_no_ext = os.path.splitext(filename)[0]
                new_filename = f"{original_name_no_ext} {extracted_title}.pdf"
                new_path = os.path.join(root, new_filename)
                
                # 再次检查目标文件是否存在
                if os.path.exists(new_path):
                    # print(f"   [跳过] 目标文件已存在: {new_filename}")
                    count_skipped += 1
                    continue
                
                try:
                    os.rename(file_path, new_path)
                    print(f"   ✅ [重命名] {filename}")
                    print(f"       -> {new_filename}")
                    count_success += 1
                except OSError as e:
                    print(f"   ❌ [失败] 无法重命名 {filename}: {e}")
            else:
                # 没找到标题的情况
                # print(f"   [未找到标题] {filename}")
                pass

    print(f"\n🎉 全部完成！")
    print(f"   - 成功重命名: {count_success} 个")
    print(f"   - 跳过(已存在/已处理): {count_skipped} 个")

# ==========================================
# 这里填你包含所有子文件夹的总目录路径
# ==========================================
target_folder = r'C:\DeepSpec\tdocs\RAN1_123_pdf' 

if os.path.exists(target_folder):
    recursive_batch_rename(target_folder)
else:
    print("❌ 路径不存在，请检查代码最后一行。")
