
from pathlib import Path

file_path = Path("data/latest_assembly_summary.txt")

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 第一行是 README，第二行是 header，第三行是第一条数据
# 我们删除第三行 (index 2)
if len(lines) > 2:
    removed_line = lines.pop(2)
    print(f"已移除行: {removed_line.strip()}")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print("文件已更新。")
else:
    print("文件行数不足。")
