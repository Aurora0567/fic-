import os.path

from Paper_Database.Load_Data.load_data import process_volume
from Paper_Database.update_ai_refine import update_ai_refine_to_database
from Paper_Refine.AI_Refine import refine_data

if __name__ == '__main__':

    # 找到最开始的论文路径
    root = r'Periodicals' # 期刊总路径
    periodical = r'MS'  # JF/JFE/RFS 中的一个
    volume = r'Volume 71, Issue 3' # 哪一期
    run_date = '2025-03-18 02:00:00' # 定时时间

    volume_path = os.path.join(root, periodical, volume)
    destination_path = os.path.join('Periodicals_AI_Refined', periodical, volume)  # 精炼之后的位置

    # 先存入数据库
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