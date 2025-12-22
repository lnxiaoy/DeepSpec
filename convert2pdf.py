import os
import comtypes.client

def batch_word_to_pdf(input_dir, output_dir):
    # 创建输出文件夹
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    word = comtypes.client.CreateObject('Word.Application')
    word.Visible = False
    
    for file in os.listdir(input_dir):
        if file.endswith((".doc", ".docx")) and not file.startswith("~$"):
            in_file = os.path.abspath(os.path.join(input_dir, file))
            # 构建输出路径，将后缀改为 .pdf
            out_file = os.path.abspath(os.path.join(output_dir, os.path.splitext(file)[0] + ".pdf"))
            
            doc = word.Documents.Open(in_file)
            doc.SaveAs(out_file, FileFormat=17) # 17 为 PDF 格式代码
            doc.Close()
            print(f"完成: {file} -> {os.path.basename(out_file)}")
            
    word.Quit()

# 使用示例：替换为你的实际路径
batch_word_to_pdf(r'E:\000_3GPP_Download\tdocs\RAN1_123', r'E:\000_3GPP_Download\tdocs\RAN1_123_pdf')
