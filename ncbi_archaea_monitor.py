import os
import requests
import csv
import datetime
import shutil
from pathlib import Path

# 配置
# 这里使用 RefSeq 的古菌数据，如果需要 GenBank 数据，可以将链接中的 refseq 改为 genbank
URL = "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/archaea/assembly_summary.txt"
# URL = "https://ftp.ncbi.nlm.nih.gov/genomes/genbank/archaea/assembly_summary.txt"

DATA_DIR = Path("data")
LATEST_FILE = DATA_DIR / "latest_assembly_summary.txt"
PREVIOUS_FILE = DATA_DIR / "previous_assembly_summary.txt"
HISTORY_DIR = DATA_DIR / "history"

def setup_directories():
    """创建必要的数据目录"""
    if not DATA_DIR.exists():
        DATA_DIR.mkdir()
    if not HISTORY_DIR.exists():
        HISTORY_DIR.mkdir()

def download_file(url, local_path):
    """下载文件"""
    print(f"正在下载: {url} ...")
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"下载完成: {local_path}")
        return True
    except Exception as e:
        print(f"下载失败: {e}")
        return False

def parse_summary_file(file_path):
    """
    解析 assembly_summary.txt 文件
    返回一个字典，Key 为 assembly_accession, Value 为该行的详细信息(字典)
    """
    data = {}
    if not file_path.exists():
        return data

    with open(file_path, 'r', encoding='utf-8') as f:
        # 跳过前面的注释行，找到 header
        while True:
            pos = f.tell()
            line = f.readline()
            if not line:
                break
            if line.startswith('#'):
                # 检查是否是 header 行 (通常以 # assembly_accession 开头，或者类似)
                # NCBI 的 header 行通常是第二行注释，或者以 # assembly_accession 开头
                # 但是标准的 csv reader 处理带 # 的 header 可能需要手动处理
                # 我们这里简单的策略：如果是 # assembly_accession... 则去掉 # 作为 header
                if 'assembly_accession' in line:
                    header_line = line.strip().lstrip('# ').split('\t')
                    break
            else:
                # 如果没有找到 header 就遇到了数据，可能文件格式不对，或者回退
                f.seek(pos)
                break
        
        reader = csv.DictReader(f, fieldnames=header_line, delimiter='\t')
        
        for row in reader:
            if not row['assembly_accession']:
                continue
            data[row['assembly_accession']] = row
            
    return data

def compare_data(old_data, new_data):
    """比较新旧数据"""
    old_keys = set(old_data.keys())
    new_keys = set(new_data.keys())

    added = new_keys - old_keys
    removed = old_keys - new_keys
    
    # 检查版本更新 (accession 相同但其他字段变了的情况较少见，通常版本更新会有新的 accession version)
    # 但是 NCBI 有时会更新同一 accession 的某些元数据
    # 这里我们主要关注 accession 的增减
    
    return added, removed

def generate_report(added, removed, new_data, old_data):
    """生成简单的报告"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_file = HISTORY_DIR / f"update_report_{timestamp}.txt"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"NCBI Archaea Assembly 更新报告\n")
        f.write(f"生成时间: {timestamp}\n")
        f.write(f"--------------------------------------------------\n")
        
        if not added and not removed:
            f.write("没有检测到更新。\n")
        else:
            f.write(f"新增 Assembly: {len(added)} 个\n")
            for acc in added:
                info = new_data[acc]
                f.write(f"  [+] {acc} ({info.get('organism_name', 'Unknown')})\n")
            
            f.write(f"\n移除 Assembly: {len(removed)} 个\n")
            for acc in removed:
                # 旧数据里可能有 info
                info = old_data.get(acc, {})
                f.write(f"  [-] {acc} ({info.get('organism_name', 'Unknown')})\n")
    
    print(f"报告已生成: {report_file}")
    
    # 打印到控制台
    if added:
        print(f"发现 {len(added)} 个新增记录。")
    if removed:
        print(f"发现 {len(removed)} 个移除记录。")
    if not added and not removed:
        print("未发现变动。")

def main():
    setup_directories()
    
    # 1. 检查是否存在上一次的数据
    # 如果不存在 previous，但存在 latest，说明上次运行后没有归档，或者这是第一次运行
    # 我们逻辑如下：
    # - 总是下载到 temp 文件
    # - 如果 previous 存在，则与 previous 比较
    # - 如果 previous 不存在，但 latest 存在，则将 latest 视为 previous 并比较（或者提示这是第一次基准）
    
    temp_file = DATA_DIR / "temp_assembly_summary.txt"
    
    if not download_file(URL, temp_file):
        print("下载失败，程序终止。")
        return

    # 加载新数据
    print("解析新下载的数据...")
    new_data = parse_summary_file(temp_file)
    
    # 尝试加载旧数据
    old_data = {}
    if LATEST_FILE.exists():
        print(f"加载上次数据: {LATEST_FILE} ...")
        old_data = parse_summary_file(LATEST_FILE)
    else:
        print("未找到上次的数据文件，此次将作为基准数据。")

    # 比较
    added, removed = compare_data(old_data, new_data)
    
    # 生成报告
    generate_report(added, removed, new_data, old_data)
    
    # 更新文件
    # 将 temp 文件移动为 latest
    # 为了保留历史，可以将旧的 latest 备份到 history (可选)
    # 这里简单处理：temp -> latest. latest 覆盖旧的
    
    # 如果需要对比 "上次结果"，我们需要确保 LATEST_FILE 在被覆盖前是作为对比源的。
    # 现在的逻辑是：old_data 读取自 LATEST_FILE，然后我们将 temp_file 覆盖 LATEST_FILE
    # 这样下次运行时的 LATEST_FILE 就是现在的 new_data
    
    if LATEST_FILE.exists():
        # 备份一下旧的 latest 到 history，方便追溯
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = HISTORY_DIR / f"assembly_summary_{timestamp}.txt"
        shutil.copy2(LATEST_FILE, backup_path)
    
    shutil.move(temp_file, LATEST_FILE)
    print(f"已更新基准数据: {LATEST_FILE}")

if __name__ == "__main__":
    main()
