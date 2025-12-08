import sqlite3
import pandas as pd
import os

# 配置
DB_NAME = "ran1_knowledge_cloud.db"
OUTPUT_FILE = "RAN1_Review_Report.xlsx"

def export_to_excel():
    conn = sqlite3.connect(DB_NAME)
    
    # 提取关键字段，按厂商和话题排序
    query = """
    SELECT 
        filename,
        vendor,
        topic,
        stance,
        key_argument as 'AI Summary (论点)',
        evidence_quote as 'Original Text (原文证据)',
        proposed_parameter,
        is_verified
    FROM document_insights
    ORDER BY topic, vendor
    """
    
    try:
        df = pd.read_sql_query(query, conn)
        
        # 增加一列人工打分 (空着给你填)
        df['Human_Check (OK/Fail)'] = ''
        df['Comments'] = ''

        # 导出 Excel
        df.to_excel(OUTPUT_FILE, index=False)
        print(f"✅ 导出成功！请打开 {OUTPUT_FILE} 进行人工抽检。")
        print("建议操作：对比 'AI Summary' 和 'Original Text' 两列，看意思是否反了。")
        
    except Exception as e:
        print(f"导出失败: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    if os.path.exists(DB_NAME):
        export_to_excel()
    else:
        print("数据库不存在，请先运行分析脚本。")
