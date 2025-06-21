import os.path
from datetime import time

from apscheduler.schedulers.background import BackgroundScheduler

from Account_API.tweet_generate import wechat_draft_creator
from Paper_Database.Load_Data.load_data import process_volume
from Paper_Database.update_ai_refine import update_ai_refine_to_database
from Paper_Refine.AI_Refine import refine_data
# from Paper_Spider.ClockSpider import Task

# 定义项目根目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


if __name__ == '__main__':

    # # 执行爬虫
    # scheduler = BackgroundScheduler()
    # scheduler.start()
    # Task()
    # try:
    #     while True:
    #         time.sleep(10)
    # except (KeyboardInterrupt, SystemExit):
    #     scheduler.shutdown()

    # 找到最开始的论文路径
    root = r'Periodicals' # 期刊总路径
    periodical = r'MS'  # JF/JFE/RFS 中的一个
    volume = r'Volume 71, Issue 1' # 哪一期
    run_date = '2025-03-18 02:00:00' # 定时时间
    title = r'【JF 80-1】西财人的专属学术外挂！每天1 分钟，AI 帮你读完三大顶刊！' # 推文标题

    volume_path = os.path.join(root, periodical, volume)
    destination_path = os.path.join('Periodicals_AI_Refined', periodical, volume)  # 精炼之后的位置

    # 先存入数据库
    print('存数据库')
    process_volume(volume_path)

    # 从出数据库读取数据（待开发）

    # 从原来的本地文件夹进行精炼
    print('精炼')
    refine_data(volume_path, destination_path)



    # # 是否要定时进行精炼
    # scheduler = BlockingScheduler() # 创建调度器
    # scheduler.add_job(refine_data, 'date', run_date=run_date) # 在指定时间运行任务
    # scheduler.start()# 启动调度器

    # 精炼后的文件存入数据库
    print('精炼之后存')
    update_ai_refine_to_database(volume_path)

    print(volume_path)

    # 将直接生成推文内容至草稿箱
    config = {
        "appid": "wxd032abb0d3611a05",
        "appsecret": "fe3c450952beb3f4b114c1bff7d9899c",
        "periodical": periodical,
        "volume_path": volume_path,
        "material_file": r'Account_API\wechat_materials.json',
        "title": title
    }

    response = wechat_draft_creator(**config)
    print("最终响应:", response)