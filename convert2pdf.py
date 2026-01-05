import os
import comtypes.client
import time

def batch_word_to_pdf_flatten(input_root, output_root):
    # 转换为绝对路径
    input_root = os.path.abspath(input_root)
    output_root = os.path.abspath(output_root)

    # 创建输出根目录
    if not os.path.exists(output_root):
        os.makedirs(output_root)

    # 初始化 Word 应用
    try:
        word = comtypes.client.CreateObject('Word.Application')
        word.Visible = False
        word.DisplayAlerts = 0 
    except Exception as e:
        print(f"无法启动 Word，请检查是否已安装 Office。错误: {e}")
        return

    print(f"开始转换 (输出不保留目录结构)...")
    print(f"源目录: {input_root}")
    print(f"输出目录: {output_root}")
    print("-" * 50)

    count_success = 0
    count_fail = 0

    # 使用 os.walk 递归查找所有文件
    for root, dirs, files in os.walk(input_root):
        for file in files:
            # 过滤文件类型
            if file.endswith((".doc", ".docx")) and not file.startswith("~$"):
                
                # 1. 源文件完整路径
                in_file_path = os.path.join(root, file)
                
                # 2. 输出文件名 (扁平化，不包含子文件夹路径)
                file_name_no_ext = os.path.splitext(file)[0]
                out_file_name = file_name_no_ext + ".pdf"
                
                # 3. 拼接输出路径 (直接拼在 output_root 下)
                out_file_path = os.path.join(output_root, out_file_name)

                # --- 关键：重名处理逻辑 ---
                # 如果不同子文件夹下有同名文件 (例如 A\1.docx 和 B\1.docx)
                # 这个循环会把输出变成 1.pdf, 1_1.pdf, 1_2.pdf
                counter = 1
                while os.path.exists(out_file_path):
                    # 如果已存在，判断是否需要跳过（这里默认视为冲突，进行重命名）
                    # 如果你希望完全跳过转换，可以在这里加逻辑。
                    # 这里为了防止覆盖不同内容的同名文件，采用重命名策略。
                    out_file_name = f"{file_name_no_ext}_{counter}.pdf"
                    out_file_path = os.path.join(output_root, out_file_name)
                    counter += 1
                
                # --- 转换逻辑 ---
                doc = None
                try:
                    # 显示当前正在处理哪个子文件夹下的文件
                    # rel_path 用于显示源文件的相对位置，方便看进度
                    rel_src_path = os.path.relpath(in_file_path, input_root)
                    
                    doc = word.Documents.Open(in_file_path, ReadOnly=True, Visible=False)
                    doc.SaveAs(out_file_path, FileFormat=17) # 17 = PDF
                    
                    print(f"[成功] {rel_src_path} -> {out_file_name}")
                    count_success += 1
                    
                except Exception as e:
                    print(f"[失败] {rel_src_path}")
                    print(f"       原因: {e}")
                    count_fail += 1
                
                finally:
                    if doc:
                        try:
                            doc.Close(SaveChanges=0)
                        except:
                            pass

    # 退出 Word
    try:
        word.Quit()
    except:
        pass
        
    print("-" * 50)
    print(f"转换结束。成功: {count_success}, 失败: {count_fail}")
    print(f"所有文件已保存在: {output_root}")

if __name__ == '__main__':
    input_dir = r'C:\DeepSpec\3GPP_38_Series_Docs_Only'
    output_dir = r'C:\DeepSpec\3GPP_38_Series_Docs_Only_pdf'
    
    batch_word_to_pdf_flatten(input_dir, output_dir)
