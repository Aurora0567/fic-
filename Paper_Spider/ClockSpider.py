#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/12/09 15:21
# @Author  : ys
# @File    : ClockSpider.py
# @Software: PyCharm

#from JFE.JFESpider_Multi import Scrape_JFE
import functools
import traceback
import time
from apscheduler.schedulers.background import BackgroundScheduler
from utils.logger import Logger
from Spider.RFS import RFSSpider
from Spider.JF import JFSpider
from Spider.JFE import JFESpider_Multi
from Spider.MS import MSSpider

logger = Logger(log_directory="./logs", log_filename="clock.log").get_logger()

def scheduled(interval, unit='hours'):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger.info(f"任务 {func.__name__} 已启动，将每 {interval} {unit} 执行")
            if unit == 'hours':
                scheduler.add_job(func, 'interval', hours=interval, args=args, kwargs=kwargs)
            elif unit == 'minutes':
                scheduler.add_job(func, 'interval', minutes=interval, args=args, kwargs=kwargs)
            elif unit == 'seconds':
                scheduler.add_job(func, 'interval', seconds=interval, args=args, kwargs=kwargs)
            return func(*args, **kwargs)
        return wrapper
    return decorator

def error_handler(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"函数 {func.__name__} 执行出错: {str(e)}")
            logger.error(f"错误:\n{traceback.format_exc()}")
            return None
    return wrapper


@error_handler
@scheduled(interval=24, unit='hours')
def Task():
    # try:
    #     logger.info("任务JFE执行中...")
    #     JFESpider_Multi.start_JFESprider()
    #     logger.info("任务JFE执行完毕")
    # except Exception as e:
    #     raise e
    # try:
    #     logger.info("任务JF执行中...")
    #     JFSpider.start_JFSprider()
    #     logger.info("任务JF执行完毕")
    # except Exception as e:
    #     raise e
    try:
        logger.info("任务RFS执行中...")
        RFSSpider.start_RFSSprider()
        logger.info("任务RFS执行完毕")
    except Exception as e:
        raise e
    # try:
    #     logger.info("任务MS执行中...")
    #     MSSpider.start_MSSprider()
    #     logger.info("任务MS执行完毕")
    # except Exception as e:
    #     raise e


if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.start()
    Task()
    try:
        while True:
            time.sleep(10)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()



