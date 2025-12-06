import os
import requests
import datetime
import shutil
from pathlib import Path
import logging
import polars as pl

log_level = os.getenv("LOG_LEVEL", "INFO")  # 默认 INFO
logging.basicConfig(
    level=log_level,   # 可以是 DEBUG/INFO/WARNING/ERROR
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

database = "refseq"
type  = "archaea"
out_directory = "out"
# 配置
# 这里使用 RefSeq 的古菌数据，如果需要 GenBank 数据，可以将链接中的 refseq 改为 genbank
URL = f"https://ftp.ncbi.nlm.nih.gov/genomes/{database}/{type}/assembly_summary.txt"
# URL = "https://ftp.ncbi.nlm.nih.gov/genomes/genbank/archaea/assembly_summary.txt"

DATA_DIR = os.path.join(out_directory, f"{database}_{type}")
LATEST_FILE = os.path.join(DATA_DIR, "latest_assembly_summary.txt")
PREVIOUS_FILE = os.path.join(DATA_DIR, "previous_assembly_summary.txt")
HISTORY_DIR = os.path.join(DATA_DIR, "history")

def setup_directories():
    """创建必要的数据目录"""
    if not DATA_DIR.exists():
        DATA_DIR.mkdir()
    if not HISTORY_DIR.exists():
        HISTORY_DIR.mkdir()

def download_file(url, local_path):
    f"""下载{database} {type} 数据"""
    logging.info(f"正在下载: {url} ...")
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        logging.info(f"{database} {type} 数据下载完成: {local_path}")
        return True
    except Exception as e:
        logging.error(f"下载失败: {e}")
        return False

def parse_summary_file(old_file_path, new_file_path):
    df_old = pl.read_csv(old_file_path, separator="\t", skip_rows=1)
    df_new = pl.read_csv(new_file_path, separator="\t", skip_rows=1)

    # 提取两个文件的accession集合
    accession_old = set(df_old["assembly_accession"].to_list())
    accession_new = set(df_new["assembly_accession"].to_list())

    # 计算增减
    added_accessions = accession_new - accession_old  # 新增的accession
    removed_accessions = accession_old - accession_new  # 删除的accession
    
    data_old = {
        row["assembly_accession"]: row
        for row in df_old.to_dicts()  # to_dicts() 直接返回每行的字典列表
    }

    # 方式2（更简洁）：Polars 0.20+ 支持按行转字典后构建
    data_new = {
        row["assembly_accession"]: row
        for row in df_new_clean.to_dicts()  # to_dicts() 直接返回每行的字典列表
    }

    return added_accessions, removed_accessions, data_old, data_new

def generate_report(added, removed, new_data, old_data):
    """生成简单的报告"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_file = HISTORY_DIR / f"{database}_{type}_update_report_{timestamp}.txt"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"NCBI {database} {type} Assembly 更新报告\n")
        f.write(f"生成时间: {timestamp}\n")
        f.write(f"--------------------------------------------------\n")
        
        if not added and not removed:
            f.write("没有检测到更新。\n")
        else:
            f.write(f"新增 Assembly: {len(added)} 个\n")
            for acc in added:
                info = new_data[acc]
                f.write(f"  [+] {acc} ({info.get('organism_name', 'Unknown')} | taxid: {info.get('taxid', 'Unknown')})\n")
            
            f.write(f"\n移除 Assembly: {len(removed)} 个\n")
            for acc in removed:
                # 旧数据里可能有 info
                info = old_data.get(acc, {})
                f.write(f"  [-] {acc} ({info.get('organism_name', 'Unknown')} | taxid: {info.get('taxid', 'Unknown')})\n")
    
    logging.info(f"{database} {type} 报告已生成: {report_file}")
    
    # 打印到控制台
    if added:
        logging.debug(f"发现 {len(added)} 个新增记录。")
    if removed:
        logging.debug(f"发现 {len(removed)} 个移除记录。")
    if not added and not removed:
        logging.debug("未发现变动。")

def main():
    setup_directories()
    
    # 1. 检查是否存在上一次的数据
    # 如果不存在 previous，但存在 latest，说明上次运行后没有归档，或者这是第一次运行
    # 我们逻辑如下：
    # - 总是下载到 temp 文件
    # - 如果 previous 存在，则与 previous 比较
    # - 如果 previous 不存在，但 latest 存在，则将 latest 视为 previous 并比较（或者提示这是第一次基准）
    
    temp_file = os.path.join(DATA_DIR, "temp_assembly_summary.txt")
    
    if not download_file(URL, temp_file):
        print("下载失败，程序终止。")
        return

    # 加载新数据
    print("解析新下载的数据...")
    added_accessions, removed_accessions, data_old, data_new = parse_summary_file(PREVIOUS_FILE, temp_file)
    
    # 生成报告
    generate_report(added_accessions, removed_accessions, data_new, data_old)
    
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
        backup_path = os.path.join(HISTORY_DIR, f"assembly_summary_{timestamp}.txt")
        shutil.copy2(LATEST_FILE, backup_path)
    shutil.move(temp_file, LATEST_FILE)
    logging.info(f"已更新基准数据: {LATEST_FILE}")

if __name__ == "__main__":
    main()
