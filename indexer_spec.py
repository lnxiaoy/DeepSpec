import os
import chromadb
from chromadb.utils import embedding_functions
from docx import Document
from tqdm import tqdm
from colorama import init, Fore
import re

init(autoreset=True)

# === 配置 ===
SPEC_FOLDER = "./specs"  # 请新建这个文件夹，把 38.211, 38.212 等放进去
DB_PATH = "./ran1_knowledge_base"
COLLECTION_NAME = "ran1_specs" # 专门存 Spec，和 TDoc 分开

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip()

def parse_spec_structure(file_path):
    """
    智能解析 Spec 结构，保留章节层级 (Breadcrumbs)。
    """
    doc = Document(file_path)
    filename = os.path.basename(file_path)
    
    chunks = []
    # 标题栈：['TS 38.211', '5. Physical Resources', '5.1 Antenna ports']
    header_stack = [filename] 
    current_content = []
    
    # 3GPP 标题的特征正则 (例如 "5.1.2", "6.3.1.4")
    heading_pattern = re.compile(r'^\d+(\.\d+)*\s+')

    for para in doc.paragraphs:
        text = clean_text(para.text)
        if not text: continue
        
        style_name = para.style.name.lower()
        
        # 判断是否为标题 (通过 Word 样式 或 正则特征)
        is_heading = 'heading' in style_name or heading_pattern.match(text)
        
        if is_heading:
            # 1. 结算上一章节的内容
            if current_content:
                # 拼接面包屑：[38.211] > [5. Phy] > [5.1 Antenna]
                context_str = " > ".join(header_stack)
                full_body = "\n".join(current_content)
                
                # 如果内容太长，还要再切一下（防止超过 Embedding 限制）
                if len(full_body) > 1000:
                    # 简单二分，实际可以做得更细
                    mid = len(full_body) // 2
                    chunks.append(f"【Context: {context_str}】\n{full_body[:mid]}")
                    chunks.append(f"【Context: {context_str}】\n{full_body[mid:]}")
                else:
                    chunks.append(f"【Context: {context_str}】\n{full_body}")
                
                current_content = []

            # 2. 更新标题栈
            # 简单的逻辑：直接用当前标题作为最新的上下文
            # (如果要完美还原树状结构比较复杂，这里简化处理，只保留最近的一个大标题)
            if len(header_stack) > 2:
                header_stack = [header_stack[0], header_stack[1], text] # 保留文件名+一级标题+当前标题
            else:
                header_stack.append(text)
        else:
            # 普通正文
            current_content.append(text)
            
    # 处理最后一段
    if current_content:
        context_str = " > ".join(header_stack)
        chunks.append(f"【Context: {context_str}】\n" + "\n".join(current_content))
        
    return chunks

def build_spec_index():
    print(f"{Fore.CYAN}=== DeepSpec RAG: 构建标准文档库 (Structure-Aware) ===")
    
    if not os.path.exists(SPEC_FOLDER):
        os.makedirs(SPEC_FOLDER)
        print(f"{Fore.RED}请先创建 {SPEC_FOLDER} 文件夹，并放入 Word 版 Spec (如 38211-h00.docx)")
        return

    client = chromadb.PersistentClient(path=DB_PATH)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    
    # 重建集合
    try: client.delete_collection(COLLECTION_NAME)
    except: pass
    collection = client.create_collection(name=COLLECTION_NAME, embedding_function=ef)
    
    files = [f for f in os.listdir(SPEC_FOLDER) if f.endswith(".docx")]
    
    total_count = 0
    batch_docs, batch_ids, batch_metas = [], [], []
    
    for filename in tqdm(files):
        chunks = parse_spec_structure(os.path.join(SPEC_FOLDER, filename))
        
        for i, chunk in enumerate(chunks):
            batch_docs.append(chunk)
            batch_ids.append(f"SPEC_{filename}_{i}")
            batch_metas.append({"filename": filename, "type": "Spec"})
            
            if len(batch_ids) >= 200:
                collection.add(documents=batch_docs, ids=batch_ids, metadatas=batch_metas)
                total_count += len(batch_ids)
                batch_docs, batch_ids, batch_metas = [], [], []

    if batch_ids:
        collection.add(documents=batch_docs, ids=batch_ids, metadatas=batch_metas)
        total_count += len(batch_ids)

    print(f"{Fore.GREEN}✅ Spec 入库完成！索引了 {total_count} 个法律条文。")

if __name__ == "__main__":
    build_spec_index()
