import os
import shutil
from docx import Document
import sys
import io 
import re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
# 1. 设置文件夹路径
source_dir = 'E:\\000_3GPP_Download\\3GPP_TSGR1_121'  # 存放原始Word文档的文件夹
dest_dir = 'E:\\000_3GPP_Download\\3GPP_TSGR1_121_Vendor_point'     # 存放分类后的文档的文件夹

# 1. 设置文件夹路径
# source_dir = 'E:\\000_3GPP_Download\\3GPP_TSGR_108'  # 存放原始Word文档的文件夹
# dest_dir = 'E:\\000_3GPP_Download\\3GPP_TSGR_108_Vendor_point'     # 存放分类后的文档的文件夹

# 2. 定义用于匹配“Source:”的正则表达式
source_pattern = re.compile(r'Source:\s*(.+)', re.IGNORECASE)

# 3. 定义文件名匹配的正则表达式
filename_pattern = re.compile(r'^R1-\d{7}\s*-?.*$', re.IGNORECASE)
# filename_pattern = re.compile(r'^RP-?\d{6}\s*-?.*$', re.IGNORECASE)

# 4. 从图片中提取的静态厂商列表（全部小写）
# 这是所有有效厂商的“原始”列表
raw_vendors_from_image = [
    'huawei', 'ericsson', 'nokia', 'zte', 'catt', 'samsung',
    'qualcomm', 'mediatek', 'intel', 'nvidia',
    'apple', 'oppo', 'vivo', 'xiaomi','telstra ',
    'ntt dcm', 'cmcc', 'vdf', 'dt'
]
# 5. 构建厂商名称的映射表
# 键是所有可能的名称（小写），值是标准化后的文件夹名
vendor_mapping = {}

# 自动填充映射表，确保所有静态列表中的厂商都能被正确处理
for vendor in raw_vendors_from_image:
    # 标准化为文件夹名（首字母大写，移除空格）
    standardized_name = vendor.title().replace(' ', '')
    # 建立小写名称到标准化名称的映射
    vendor_mapping[vendor] = standardized_name

# 手动添加别名或其他不规范的名称到映射表
# 确保所有别名都是小写，并映射到正确的标准化名称
vendor_mapping['hisilicon'] = 'Huawei'
vendor_mapping['nttdcm'] = 'NttDcm'
vendor_mapping['china mobile'] = 'CMCC' # 举例，如果文档中出现China Mobile

# 6. 定义一个用于清理非法字符的函数
def sanitize_filename(name):
    """
    清理字符串中的非法字符，使其能作为有效的文件名或文件夹名。
    """
    invalid_chars = r'[<>:"/\\|?*\t\n\r]'
    sanitized_name = re.sub(invalid_chars, '', name)
    sanitized_name = sanitized_name.strip()
    if not sanitized_name:
        return 'Unknown_Vendor'
    return sanitized_name

# 7. 遍历并处理Word文档
def process_documents_with_static_list(source_folder, dest_folder):
    """
    处理指定文件夹中文件名符合"RP-123456.docx"格式的文档，并根据静态列表分类。
    """
    if not os.path.exists(dest_folder):
        os.makedirs(dest_dir, exist_ok=True)
        
    for filename in os.listdir(source_folder):
        if filename_pattern.match(filename):
            file_path = os.path.join(source_folder, filename)
            found_vendors = set()

            try:
                doc = Document(file_path)
                
                content = ""
                for i, para in enumerate(doc.paragraphs):
                    if i >= 10:
                        break
                    content += para.text + " "
                
                match = source_pattern.search(content)
                
                if match:
                    vendors_str = match.group(1)
                    vendor_names = re.findall(r'[a-zA-Z0-9]+', vendors_str)
                    
                    for vendor_name in vendor_names:
                        vendor_name_lower = vendor_name.lower()
                        
                        final_vendor_name = vendor_mapping.get(vendor_name_lower)
                        
                        if final_vendor_name:
                            found_vendors.add(final_vendor_name)
                        else:
                            print(f"警告: 在文档 '{filename}' 中发现未知的厂商或格式错误: '{vendor_name}'。")

            except Exception as e:
                print(f"处理文档 '{filename}' 时出错: {e}")
                found_vendors.clear()
            
            if found_vendors:
                for vendor in found_vendors:
                    vendor_dest_dir = os.path.join(dest_folder, vendor)
                    os.makedirs(vendor_dest_dir, exist_ok=True)
                    shutil.copy(file_path, vendor_dest_dir)
                    print(f"文档 '{filename}' 包含厂商 '{vendor}'，已复制到 '{vendor_dest_dir}'")
            else:
                unknown_dir = os.path.join(dest_dir, 'Unknown')
                os.makedirs(unknown_dir, exist_ok=True)
                shutil.copy(file_path, unknown_dir)
                print(f"文档 '{filename}' 未找到匹配厂商，已复制到 '{unknown_dir}'")
        else:
            print(f"跳过文件 '{filename}'，因为它不符合 'RP-123456.docx' 的格式。")

# 8. 运行脚本
if __name__ == '__main__':
    if not os.path.exists(source_dir):
        os.makedirs(source_dir, exist_ok=True)
        print(f"已创建源文件夹 '{source_dir}'。请将Word文档放入其中，然后再次运行脚本。")
    else:
        print(f"开始处理文件夹 '{source_dir}' 中的文档...")
        process_documents_with_static_list(source_dir, dest_dir)
        print("\n文档分类完成！")