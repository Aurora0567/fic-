#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/7/3 15:00
# @Author  : ys
# @File    : logger.py
# @Software: PyCharm


import logging
from logging.handlers import RotatingFileHandler
import os

class Logger:
    def __init__(self, name=__name__, log_directory='logs', log_filename='app.log',
                 max_bytes=10*1024*1024, backup_count=3, level=logging.INFO,
                 format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                 datefmt='%Y-%m-%d %H:%M:%S'):
        self.logger = logging.getLogger(name)

        if not self.logger.handlers:  # 检查是否已经有处理器防止重复添加
            self.logger.setLevel(level)

            # 创建日志目录（如果不存在）
            if not os.path.exists(log_directory):
                os.makedirs(log_directory)

            # 创建控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)

            # 创建文件处理器
            file_handler = RotatingFileHandler(os.path.join(log_directory, log_filename),
                                               maxBytes=max_bytes, backupCount=backup_count,encoding='utf-8')
            file_handler.setLevel(level)

            # 创建日志格式器并添加到处理器
            formatter = logging.Formatter(format, datefmt)
            console_handler.setFormatter(formatter)
            file_handler.setFormatter(formatter)

            # 添加处理器到记录器
            self.logger.addHandler(console_handler)
            self.logger.addHandler(file_handler)

    def get_logger(self):
        return self.logger


if __name__ == "__main__":
    pass
