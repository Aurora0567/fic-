#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/7/3 11:39
# @Author  : ys
# @File    : tools.py
# @Software: PyCharm


from memory_profiler import memory_usage
from types import SimpleNamespace
from dotenv import load_dotenv
from tkinter import filedialog
from functools import wraps
import tkinter as tk

#import magic

import psutil
import time
import sys
import os
import re
import base64
import gzip

##装饰器，打印内存
def Count_Memory(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        mem_usage_before = memory_usage(max_usage=True)  # 获取调用函数前的内存使用情况
        result = await func(*args, **kwargs)
        mem_usage_after = memory_usage(max_usage=True)   # 获取调用函数后的内存使用情况
        mem_diff = mem_usage_after - mem_usage_before   # 计算内存消耗
        print(f"Function '{func.__name__}' used {mem_diff:.4f} MB of memory")
        return result
    return wrapper


##装饰器，打印时间
def Count_Time(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()  # 开始时间
        result = await func(*args, **kwargs)
        end_time = time.time()  # 结束时间
        elapsed_time = end_time - start_time  # 计算运行时间
        print(f"Function '{func.__name__}' executed in {elapsed_time:.4f} seconds")
        return result
    return wrapper

def Get_Resource_Usage(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        process = psutil.Process(os.getpid())
        mem_before = process.memory_info().rss / (1024 ** 2)  # Convert to MB
        cpu_before = process.cpu_percent(interval=None)
        time_start = time.time()

        result = func(*args, **kwargs)  # Call the function

        cpu_after = process.cpu_percent(interval=None)
        mem_after = process.memory_info().rss / (1024 ** 2)
        time_end = time.time()
        print(f"{func.__name__} : Memory used: {mem_after - mem_before:.2f} MB")
        print(f"{func.__name__} : CPU used: {cpu_after - cpu_before:.2f}%")
        print(f"{func.__name__} : Time elapsed: {time_end - time_start:.2f} seconds")

        return result

    return wrapper

# 假设你的某些函数或处理过程在这里执行
# 例如：处理数据或运行某个复杂算法

# 获取并打印资源使用情况
#memory_used, cpu_used = get_resource_usage()




def GetFileType(file_path):
    """
    Get file type based on the file extension and
    magic number (first few bytes)(cancel it now for dependent libraries)  .
    """
    if not file_path:
        raise ValueError("No file path provided")
    file_type = None
    #first try file extension method
    try:
        _, file_extension = os.path.splitext(file_path)
        if file_extension:
            file_type = file_extension.lower().lstrip('.')
        # else:
        #     return "Unknown or no extension"
    except:
    # second try magic number method
    #     try:
    #         mime = magic.Magic(mime=True)
    #         file_type = mime.from_file(file_path)
    #     except:
            raise ValueError("Form of file is not right")
    return file_type

def GetFileName(file_path):
    """
    不同系统适配
    Extract the file name without extension from the given file path,
    ensuring the result does not contain characters illegal in Windows file paths.
    Trims trailing dots and spaces which can cause issues in Windows.
    """
    if not file_path:
        raise ValueError("No file path provided")
    # Get the base name of the file
    file_name = os.path.splitext(os.path.basename(file_path))[0]
    if sys.platform.startswith('win'):
        # Windows-specific forbidden characters
        file_name = re.sub(r'[<>:"/\\|?*]', '', file_name)
    elif sys.platform.startswith(('linux', 'darwin')):
        # Linux and macOS only forbid null and '/' in filenames
        file_name = file_name.replace('/', '')
    # Remove trailing dots and spaces
    file_name = file_name.rstrip(". ")
    return file_name


def Decode_Text(base64_string,encoding = 'utf-8'):
    """
    Decode a Base64 string to bytes and decompress it.
    """
    if base64_string:
        compressed_data = base64.b64decode(base64_string)
        decompressed_data = gzip.decompress(compressed_data)
        # 获取压缩前的数据类型信息
        data_type = decompressed_data[:1]  # 假设第一个字节表示数据类型
        original_data = decompressed_data[1:]  # 去除类型信息后的原始数据
        if data_type == b'S':  # 字符串类型
            return original_data.decode(encoding)
        elif data_type == b'B':  # 字节对象类型
            return original_data
        else:
            raise ValueError("Invalid data type indicator")
    else:
        raise ValueError("NO data input to decode")
    # compressed_data = base64.b64decode(base64_string)
    # return gzip.decompress(compressed_data).decode(encoding)

def Encode(data,encoding = 'utf-8'):
    """
        Encode text  or type to bytes data ,then to a Base64 string suitable for JSON serialization.
    """
    if data:
        if isinstance(data, str):
            # 添加数据类型指示符 'S' 表示字符串
            data_to_compress = b'S' + data.encode(encoding)
        elif isinstance(data, bytes):
            # 添加数据类型指示符 'B' 表示字节对象
            data_to_compress = b'B' + data
        else:
            raise TypeError("Expected a string or bytes object")
        # 压缩数据
        compressed_data = gzip.compress(data_to_compress)
        # Base64 编码
        base64_string = base64.b64encode(compressed_data).decode(encoding)
        return base64_string
    else:
        raise ValueError("NO data input to encode")

    # compressed_data = gzip.compress(text.encode(encoding))
    # return base64.b64encode(compressed_data).decode(encoding)

import win32ui
def Choose_File(default = "../.."):
    print('打开文件对话框，选取文件')
    dlg = win32ui.CreateFileDialog(1)  # 0代表另存为对话框，1代表打开文件对话框
    dlg.SetOFNInitialDir(os.path.abspath(os.path.join(os.getcwd(), default)))  # 默认当前上级目录
    dlg.DoModal()  # 显示对话框
    filename = dlg.GetPathName()  # 获取用户选择的文件全路径
    return filename

def Choose_Folder(default = "../.."):
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    folder_path = filedialog.askdirectory(initialdir=default)  # 打开文件夹选择对话框
    return folder_path

class Config():
    def __init__(self, env_file=None):
        self.env_file = env_file
        self.load_config()
    def load_config(self):
        if self.env_file:
            load_dotenv(self.env_file)
        else:
            load_dotenv()

        config_dict = {key: os.getenv(key) for key in os.environ}

        # Convert boolean and numeric values
        for key, value in config_dict.items():
            if isinstance(value, str):  # Ensuring value is a string before calling lower
                if value.lower() in ('true', 'false'):
                    config_dict[key] = value.lower() == 'true'
                else:
                    try:
                        config_dict[key] = int(value)
                    except ValueError:
                        try:
                            config_dict[key] = float(value)
                        except ValueError:
                            pass

        # Set attributes dynamically
        for key, value in config_dict.items():
            setattr(self, key, value)

    def reload(self, env_file=None):
        self.env_file = env_file
        self.load_config()




if __name__ == "__main__":
    file_path = "sfhuahsfuh:afsasf"
    file_type = GetFileType(file_path)
    file_name = GetFileName(file_path)
    #selected_folder = Choose_Folder()

    config = Config()
    a = config.OPENAI_BASE_URL
