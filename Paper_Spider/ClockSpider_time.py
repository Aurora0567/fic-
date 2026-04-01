from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
import os
from datetime import datetime
from main import process_volume, refine_data, update_ai_refine_to_database  # 导入 pipeline 函数

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='crawler.log'
)

def has_new_journal_data(journal, data_path):
    """
    检查指定期刊是否有新数据
    :param journal: 期刊名称（JF、RFS、JFE、MS）
    :param data_path: 爬取数据存储路径
    :return: 如果有新数据返回 True，否则返回 False
    """
    # 示例：检查期刊文件是否在今天修改
    journal_file = os.path.join(data_path, f"{journal}_data.json")
    if os.path.exists(journal_file):
        file_mtime = datetime.fromtimestamp(os.path.getmtime(journal_file))
        return file_mtime.date() == datetime.now().date()
    return False

def run_crawler(spider_name):
    """
    运行指定爬虫
    :param spider_name: 爬虫名称（例如 'JFESpider_Multi'）
    :return: 成功返回 True，失败返回 False
    """
    try:
        logging.info(f"运行爬虫: {spider_name}")
        # 替换为实际的爬虫执行逻辑（例如使用 Scrapy）
        # 例如：subprocess.run(['scrapy', 'crawl', spider_name])
        return True
    except Exception as e:
        logging.error(f"爬虫 {spider_name} 运行失败: {e}")
        return False

def run_pipeline(journal):
    """
    为指定期刊运行 pipeline
    :param journal: 期刊名称（JF、RFS、JFE、MS）
    """
    try:
        logging.info(f"运行 {journal} 的 pipeline")
        process_volume(journal)  # 处理期刊数据
        refine_data(journal)     # 精炼数据
        update_ai_refine_to_database(journal)  # 更新数据库
        logging.info(f"{journal} 的 pipeline 完成")
    except Exception as e:
        logging.error(f"{journal} 的 pipeline 出错: {e}")

def Task():
    """
    执行爬虫任务并触发新数据的 pipeline
    """
    logging.info("开始爬虫任务")
    data_path = r"C:\path\to\crawled\data"  # 替换为实际数据路径

    # 爬虫与期刊的对应关系
    crawlers = [
        ("JFESpider_Multi", "JFE"),
        ("JFSpider", "JF"),
        ("RFSSpider", "RFS"),
        ("MSSpider", "MS")
    ]

    for spider_name, journal in crawlers:
        # 运行爬虫
        if run_crawler(spider_name):
            # 检查是否有新数据
            if has_new_journal_data(journal, data_path):
                logging.info(f"检测到 {journal} 的新数据，触发 pipeline")
                run_pipeline(journal)
            else:
                logging.info(f"{journal} 无新数据，跳过 pipeline")
        else:
            logging.warning(f"爬虫 {spider_name} 失败，跳过 {journal} 的 pipeline")

if __name__ == "__main__":
    # 初始化调度器
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")  # 设置时区

    # 设置每天早上8点运行 Task()
    scheduler.add_job(
        Task,
        trigger=CronTrigger(hour=8, minute=0),
        id='crawler_task',
        name='每天8点爬虫任务'
    )

    logging.info("启动调度器")
    scheduler.start()

    try:
        # 保持脚本运行
        while True:
            pass
    except (KeyboardInterrupt, SystemExit):
        logging.info("关闭调度器")
        scheduler.shutdown()
