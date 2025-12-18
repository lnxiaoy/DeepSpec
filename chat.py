import chromadb
import ollama
from chromadb.utils import embedding_functions
from colorama import init, Fore

init(autoreset=True)

DB_PATH = "./ran1_knowledge_base"
MODEL_NAME = "qwen2.5:14b" 

def chat_loop():
    print(f"{Fore.CYAN}=== DeepSpec 全栈专家系统 (Spec + TDoc) ===")
    
    client = chromadb.PersistentClient(path=DB_PATH)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    
    # 获取两个集合
    try:
        coll_specs = client.get_collection(name="ran1_specs", embedding_function=ef)
        coll_tdocs = client.get_collection(name="ran1_docs", embedding_function=ef)
    except:
        print(f"{Fore.RED}错误：请确保你已经分别运行了 indexer.py (TDoc) 和 indexer_specs.py (Spec)！")
        return

    while True:
        query = input(f"\n{Fore.YELLOW}请提问 (e.g. 38.211里DMRS怎么定义的? 各家想怎么改?): {Fore.RESET}")
        if query.lower() in ["exit", "quit"]: break
        
        print(f"{Fore.CYAN}🔍 1. 正在查阅 3GPP 法律条文 (Specs)...")
        res_specs = coll_specs.query(query_texts=[query], n_results=3)
        
        print(f"{Fore.CYAN}🔍 2. 正在查阅 厂商提案 (TDocs)...")
        res_tdocs = coll_tdocs.query(query_texts=[query], n_results=5)
        
        # 组装上下文
        context_str = "【Part 1: 现有标准定义 (Ground Truth)】\n"
        for doc in res_specs['documents'][0]:
            context_str += f"{doc}\n---\n"
            
        context_str += "\n【Part 2: 本次会议的提案与争议 (Debate)】\n"
        for i, doc in enumerate(res_tdocs['documents'][0]):
            fname = res_tdocs['metadatas'][0][i]['filename']
            context_str += f"Source: {fname}\nContent: {doc}\n---\n"

        # 让模型综合
        prompt = f"""
        你是一位 3GPP 标准架构师。请根据以下资料回答问题。
        
        【资料结构】：
        1. **现有标准**：来自 38.211/38.213 等 Spec，这是当前的法律基准。
        2. **会议提案**：来自各厂商的 TDoc，这是他们想修改或增强的地方。
        
        【用户问题】：
        {query}
        
        【回答逻辑】：
        1. 先引用 Spec，简述**当前标准**是如何规定的（引用章节号）。
        2. 再引用 TDoc，阐述**各厂商**提出了什么新观点或修改建议。
        3. 用中文回答，专业、准确。
        
        【参考资料】：
        {context_str}
        """
        
        print(f"{Fore.GREEN}🤖 Qwen 正在思考...")
        stream = ollama.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': prompt}], stream=True)
        
        print(f"{Fore.WHITE}", end="")
        for chunk in stream:
            print(chunk['message']['content'], end="", flush=True)
        print("\n")

if __name__ == "__main__":
    chat_loop()
