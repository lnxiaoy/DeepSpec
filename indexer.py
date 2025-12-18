import os
import chromadb
from chromadb.utils import embedding_functions
from docx import Document
from tqdm import tqdm
from colorama import init, Fore

init(autoreset=True)

# === 配置 ===
DOC_FOLDER = "./tdocs/RAN1_123"
DB_PATH = "./ran1_knowledge_base" # 向量数据库路径
CHUNK_SIZE = 800  # 每个切片约 800 字符 (一段话左右)
OVERLAP = 100     # 重叠，防止切断句子

def read_docx(file_path):
    try:
        doc = Document(file_path)
        # 清洗：去掉太短的行，保留核心文本
        text = "\n".join([p.text.strip() for p in doc.paragraphs if len(p.text.strip()) > 10])
        return text
    except:
        return ""

def split_text(text, chunk_size, overlap):
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += (chunk_size - overlap)
    return chunks

def build_index():
    print(f"{Fore.CYAN}=== DeepSpec RAG: 构建全量知识库 ===")
    
    # 1. 初始化 ChromaDB (本地向量库)
    client = chromadb.PersistentClient(path=DB_PATH)
    
    # 使用轻量级 Embedding 模型 (不用跑 Ollama，速度快)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2" # 或者 "paraphrase-multilingual-MiniLM-L12-v2" 支持多语言
    )
    
    # 创建集合 (如果存在先删除，确保干净)
    try: client.delete_collection("ran1_docs")
    except: pass
    collection = client.create_collection(name="ran1_docs", embedding_function=ef)
    
    files = [f for f in os.listdir(DOC_FOLDER) if f.endswith(".docx")]
    print(f"扫描到 {len(files)} 份文档，准备入库...")
    
    batch_ids = []
    batch_docs = []
    batch_metas = []
    
    total_chunks = 0
    
    for filename in tqdm(files):
        # 简单分类
        doc_type = "TDoc"
        if "report" in filename.lower() or "minutes" in filename.lower(): doc_type = "Report"
        elif "summary" in filename.lower(): doc_type = "FLS"
        
        # 提取厂商 (简单规则，文件名通常包含厂商)
        vendor = "Unknown"
        # 这里可以加更多规则提取厂商...
        
        content = read_docx(os.path.join(DOC_FOLDER, filename))
        if not content: continue
        
        chunks = split_text(content, CHUNK_SIZE, OVERLAP)
        
        for i, chunk in enumerate(chunks):
            chunk_id = f"{filename}_part{i}"
            
            batch_ids.append(chunk_id)
            batch_docs.append(chunk)
            batch_metas.append({
                "filename": filename,
                "type": doc_type,
                "part": i
            })
            
            # 批量写入 (每 500 条写一次)
            if len(batch_ids) >= 500:
                collection.add(documents=batch_docs, ids=batch_ids, metadatas=batch_metas)
                total_chunks += len(batch_ids)
                batch_ids, batch_docs, batch_metas = [], [], []

    # 写入剩余的
    if batch_ids:
        collection.add(documents=batch_docs, ids=batch_ids, metadatas=batch_metas)
        total_chunks += len(batch_ids)
        
    print(f"{Fore.GREEN}✅ 入库完成！共索引了 {total_chunks} 个文本切片。")
    print(f"知识库保存在: {DB_PATH}")

if __name__ == "__main__":
    build_index()
