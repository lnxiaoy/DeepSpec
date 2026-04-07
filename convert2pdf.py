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

    print(f"开始转换 (输出不保留目录结构，已存在的文件将跳过)...")
    print(f"源目录: {input_root}")
    print(f"输出目录: {output_root}")
    print("-" * 50)

    count_success = 0
    count_fail = 0
    count_skip = 0  # 新增跳过计数

    # 使用 os.walk 递归查找所有文件
    for root, dirs, files in os.walk(input_root):
        for file in files:
            # 过滤文件类型
            if file.endswith((".doc", ".docx")) and not file.startswith("~$"):
                
                # 1. 源文件完整路径
                in_file_path = os.path.join(root, file)
                
                # 2. 预期的输出文件名
                file_name_no_ext = os.path.splitext(file)[0]
                out_file_name = file_name_no_ext + ".pdf"
                
                # 3. 拼接输出路径
                out_file_path = os.path.join(output_root, out_file_name)

                # --- 新增功能：如果已存在则跳过 ---
                if os.path.exists(out_file_path):
                    print(f"[跳过] {out_file_name} 已存在")
                    count_skip += 1
                    continue  # 直接处理下一个文件
                
                # --- 转换逻辑 ---
                doc = None
                try:
                    rel_src_path = os.path.relpath(in_file_path, input_root)
                    
                    doc = word.Documents.Open(in_file_path, ReadOnly=True, Visible=False)
                    doc.SaveAs(out_file_path, FileFormat=17) # 17 = PDF
                    
                    print(f"[成功] {rel_src_path} -> {out_file_name}")
                    count_success += 1
                    
                except Exception as e:
                    print(f"[失败] {rel_src_path}")
                    print(f"      原因: {e}")
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
    print(f"转换结束。成功: {count_success}, 跳过: {count_skip}, 失败: {count_fail}")
    print(f"所有文件已保存在: {output_root}")

if __name__ == '__main__':
    input_dir = r'C:\DeepSpec\tdocs\RAN1_124b'
    output_dir = r'C:\DeepSpec\tdocs\RAN1_124b_pdf'
    
    batch_word_to_pdf_flatten(input_dir, output_dir)
