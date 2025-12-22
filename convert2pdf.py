import os
import comtypes.client
import time

def batch_word_to_pdf(input_dir, output_dir):
    # 创建输出文件夹
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 初始化 Word 应用
    word = comtypes.client.CreateObject('Word.Application')
    word.Visible = False
    word.DisplayAlerts = 0  # 关键：关闭 Word 的弹窗警告（如“是否保存修改”）
    
    print(f"开始转换，源目录: {input_dir}")
    
    count_success = 0
    count_fail = 0

    for file in os.listdir(input_dir):
        if file.endswith((".doc", ".docx")) and not file.startswith("~$"):
            in_file = os.path.abspath(os.path.join(input_dir, file))
            out_file = os.path.abspath(os.path.join(output_dir, os.path.splitext(file)[0] + ".pdf"))
            
            # 如果 PDF 已存在，跳过（可选，节省时间）
            if os.path.exists(out_file):
                print(f"[跳过] 已存在: {file}")
                continue

            doc = None
            try:
                # 关键修改：以只读模式打开，且不显示转换框，修复很多权限问题
                doc = word.Documents.Open(in_file, ReadOnly=True, Visible=False)
                
                doc.SaveAs(out_file, FileFormat=17) # 17 = PDF
                print(f"[成功] 完成: {file}")
                count_success += 1
                
            except Exception as e:
                # 捕获错误，打印文件名和具体原因，但不让程序崩溃
                print(f"[失败] 无法转换: {file}")
                print(f"       错误信息: {e}")
                count_fail += 1
            
            finally:
                # 无论成功失败，都要尝试关闭文档，释放内存
                if doc:
                    try:
                        doc.Close(SaveChanges=0) # 0 = 不保存修改
                    except:
                        pass
    
    # 退出 Word
    try:
        word.Quit()
    except:
        pass
        
    print(f"\n转换结束。成功: {count_success}, 失败: {count_fail}")

# 执行
batch_word_to_pdf(r'E:\000_3GPP_Download\tdocs\RAN1_123', r'E:\000_3GPP_Download\tdocs\RAN1_123_pdf')
