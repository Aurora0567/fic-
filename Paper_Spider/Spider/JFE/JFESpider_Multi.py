#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/11/21 15:56
# @Author  : ys
# @File    : JFESpider_Multi.py
# @Software: PyCharm


import asyncio
import requests
from bs4 import BeautifulSoup
import json
import re
import os
import time
from selenium import webdriver
from selenium.common import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from concurrent.futures import ThreadPoolExecutor
from utils.logger import Logger
from utils.tools import GetFileName
from utils.tools import Config
import queue
import threading
import random
import yaml

# with open(r"C:\Users\winger\Desktop\新建文件夹\Growing the efficient frontier on panel trees - ScienceDirect.html",
#           encoding="utf-8") as file:
#     data = file.read()
logger = Logger(log_directory="./Spider/JFE/logs", log_filename="scrape_JFE.log").get_logger()
# logger = Logger(log_filename="scrape_JFE.log").get_logger()
lock = threading.Lock()
config = Config()


def Scrape_items(html_source, save_path="./"):
    soup = BeautifulSoup(html_source, 'html.parser')
    information = {}

    # 名称
    title = soup.find('meta', {'name': 'citation_title'})['content']
    if title == "Editorial Board":
        return
    else:
        information['title'] = title
        ##创建相应文件夹
        file_name = GetFileName(title)
        file_floder = os.path.join(save_path, file_name)
        # if os.path.exists(file_floder):
        #     return
        os.makedirs(file_floder, exist_ok=True)

    information['type'] = soup.find('meta', {'name': 'citation_journal_title'})['content']
    information['link'] = soup.find('link', {'rel': 'canonical'})['href']
    information['public'] = soup.find('meta', {'name': 'citation_publication_date'})['content']

    # 摘要
    abstract_item = soup.find('div', class_="abstract author")
    abstract_item = abstract_item.find('div', class_="u-margin-s-bottom")
    information['abstract'] = abstract_item.get_text()

    # 期数
    volume_section = soup.find('div', class_='publication-volume u-text-center')
    volume_section = soup.find('div', class_='text-xs')
    volume_section = volume_section.find('span', class_='anchor-text-container')
    volume = volume_section.text

    # 引用量
    citation_item = soup.find('li', {'class': 'plx-citation'})
    citation_count = citation_item.find('span', {'class': 'pps-count'}).get_text() if citation_item else None
    information["citation_count"] = citation_count

    # 关键字
    keywords_section = soup.find_all('div', class_="keywords-section")
    keywords = Handle_article_keywords(keywords_section)
    # keywords = soup.find_all('div', class_ = "keyword")
    # information['keys'] = [keyword.get_text() for keyword in keywords]
    information['keys'] = keywords

    # 作者
    authors_section = soup.find('div', class_="author-group")
    author_information = Handle_article_authors(authors_section)
    information['author'] = author_information

    # 检查是否有并处理原文内容
    full_text_section = soup.find('div', class_='Body u-font-serif')  # 示例类名
    if full_text_section:
        information['ifarticle'] = True
        # 解析每个部分内容
        information['article'] = Handle_article_sections(full_text_section)
    else:
        information['ifarticle'] = False
        information['article'] = {}

    # 检查是否有并处理图片内容
    if full_text_section:
        Handle_article_figures(full_text_section, save_path=file_floder)
        pass

    # 提取参考文献
    references = soup.find('ol', class_='references')  # 示例类名
    if references:
        information['references'] = [refer.get_text() for refer in references]

    # 保存为 JSON 文件
    with open(os.path.join(file_floder, 'information.json'), 'w', encoding='utf-8') as json_file:
        json.dump(information, json_file, ensure_ascii=False, indent=4)

    logger.info(title)


def Handle_article_sections(article_section):
    """
    解析文章的章节和子章节，至多三级目录
    """
    article_content = {}
    # 全部一级目录
    ##sec+index结构
    try:
        sections = article_section.find_all('section', id=re.compile(r'^sec\d+$'), recursive=False)
        ##如果是另一结构
        if len(sections) == 0:
            sections = article_section.find('div')
            sections = sections.find_all('section', recursive=False)
            # sections = sections.find_elements(By.CSS_SELECTOR, '> section')
            del sections[-1]
        for section in sections:
            section_title = section.find('h2')
            title = section_title.text.strip()
            section_article = ''
            for element in section_title.find_next_siblings():
                section_article += element.text.strip()

                # if 'u-margin-s-bottom' in element.get('class', []):
                #     text += element.text.strip()
                #     continue
                # 二级目录
                # if element.name == 'section' and re.match(r'^sec\d.\d+$', element.get('id', '')):
                #     section_sub_title = element.find('h3')
                #     sub_title = section_sub_title.text.strip()
                #     for sub_element in section_sub_title.find_next_siblings():
                #         if 'u-margin-s-bottom' in sub_element.get('class', []):
                #             sub_text = sub_element.text.strip()
                #             continue
                #         # 三级目录
                #         if sub_element.name == 'section' and re.match(r'^sec\d.\d.\d+$', sub_element.get('id', '')):
                #             sub_sub_section_title = sub_element.find('h4').text.strip()
                #             for sub_sub_element in element.find_next_siblings():
                #                 if 'u-margin-s-bottom' in sub_sub_element.get('class', []):
                #                     sub_sub_text = sub_sub_element.text.strip()

            article_content[title] = section_article

        # append部分  暂不加入整体文本
        append_sections = article_section.find_all('div', class_='Appendices')
    except Exception as e:
        logger.error("Article error:", e)
        raise e
    return article_content


def Handle_article_figures(article_section, save_path="./"):
    # 创建保存图片目录
    os.makedirs(os.path.join(save_path, 'images'), exist_ok=True)
    # 查找所有img元素容器
    images_containers = article_section.find_all('figure', class_='figure text-xs')
    figure_information = {}
    # 防止过量访问
    pause_time = 0
    for image in images_containers:
        # if pause_time >= 15:
        #     time.sleep(random.randint(8,15))
        #     pause_time = 0
        id = image.get('id')
        pattern = r'^fig\d+$'
        if not re.match(pattern, id):
            continue
        start_time = time.time()
        # lable = re.findall(r'\d+', image.get('id'))
        lable_text = image.find('span', class_='captions text-s').find('span', class_='label').text
        lable = re.findall(r'\d+', lable_text)
        description = image.find('span', class_='captions text-s').text
        description = re.sub(r'^Fig\.\s*\d+\.\s*', '', description)
        # 保留图片信息
        figure_information[lable[0]] = {"description": [description], "correlation": []}
        # 下载图片
        image_url = image.find('img').get('src')
        if image_url:  # 确保图片 URL 存在
            # 处理相对路径
            if image_url.startswith('/'):
                img_url = url + img_url  # 拼接基网址

            # 构建图片文件名
            image_name = os.path.join(save_path, 'images', f"page_{00:02}_image_{int(lable[0]):02}.png")
            # 下载图片
            try:
                lock.acquire()
                img_data = requests.get(image_url).content
            except Exception as e:
                logger.error(f"图片下载失败: {image_name} - 错误: {e}")
                continue
            finally:
                lock.release()
                # time.sleep(random.randint(1, 3))

            try:
                with open(image_name, 'wb') as img_file:
                    img_file.write(img_data)
            except Exception as e:
                logger.error(f"图片保存失败: {image_name} - 错误: {e}")
                continue
            logger.info(f"图片保存成功: {image_name}")
        end_time = time.time()
        pause_time += end_time - start_time

    # 构建图片信息文件名
    image_information_name = os.path.join(save_path, "images_information.json")
    with open(image_information_name, 'w', encoding='utf-8') as file:
        json.dump(figure_information, file, ensure_ascii=False, indent=4)


def Handle_article_authors(authors_section):
    if authors_section:
        try:
            # #获取名字
            # first_name = authors_section.find_all('span', class_="given-name")
            # second_name = authors_section.find_all('span', class_="text surname")
            # second_name = [item for item in second_name if len(item.get_text()) > 0]
            # first_name_lsit = [item.get_text() for item in first_name]
            # second_name_lsit = [item.get_text() for item in second_name]
            # author_name = [first + ' ' + second for first, second in zip(first_name_lsit, second_name_lsit)]
            # #获取单位
            # place_sections = authors_section.find_all('dl', class_="affiliation")
            # place = [section.find('dd').text.split(',')[0] for section in place_sections]

            # 增设通讯标识与单位匹配
            authors = authors_section.find_all('button', class_='button-link')
            affiliations = authors_section.find_all('dl', class_='affiliation')
            authors_with_tag = {}
            authors_without_tag = []  # 无tag时
            # 找出作者与标号
            for author in authors:
                name_tag = author.find('span', class_='react-xocs-alternative-link')
                if name_tag:
                    first_name = name_tag.find('span', class_='given-name').get_text(strip=True)
                    last_name = name_tag.find('span', class_='text surname').get_text(strip=True)
                    author_name = f"{first_name} {last_name}"

                    # 获取小标号
                    tag_list = []
                    sup_tag_sections = author.find_all('sup')
                    if sup_tag_sections:
                        for sup_tag_section in sup_tag_sections:
                            index = sup_tag_section.get_text(strip=True)
                            tag_list.append(index)
                    else:
                        authors_without_tag.append(author_name)

                    # 判断通讯作者
                    svg_element = author.find('svg', {'title': 'Correspondence author icon'})
                    if svg_element:
                        author_name = author_name + "*"

                    authors_with_tag[author_name] = tag_list

            # 查找小标号对应的单位
            places = {}
            places_without_tag = []  # 当无tag时
            for affiliation in affiliations:
                sup_aff = affiliation.find('sup')
                if sup_aff:
                    tag = sup_aff.get_text(strip=True)
                    unit = affiliation.find('dd').get_text(strip=True)
                    places[tag] = unit
                else:
                    places_without_tag.append(affiliation.find('dd').get_text(strip=True))

            # 开始匹配拼接信息
            author_information = {}
            if authors_without_tag:
                if len(authors_without_tag) == len(places_without_tag):
                    for author, place in zip(authors_without_tag, places_without_tag):
                        author_information[author] = place
                else:
                    for author in authors_without_tag:
                        author_information[author] = places_without_tag[0]
            else:
                for author in authors_with_tag.keys():
                    place = ""
                    tag = authors_with_tag[author]
                    place += places[tag[0]]
                    del tag[0]
                    if tag:
                        for index in tag:
                            temp = places.get(index)
                            if temp:
                                place += "|||" + temp
                    author_information[author] = place

            return author_information
        except Exception as e:
            logger.error("author error:", e)
            raise e

    else:
        return {}


def Handle_article_keywords(keywords_section):
    if keywords_section:
        try:
            # 遍历所有section，根据section-title选择提取内容
            for section in keywords_section:
                title = section.find("h2").text
                if title == 'JEL classification':
                    # 检查JEL Classification部分是否有内容
                    jel_codes_list = [jel.text for jel in section.find_all("div", class_='keyword')]
                elif title == 'Keywords':
                    # 提取Keywords部分的内容
                    keywords_list = [keyword.text for keyword in section.find_all("div", class_='keyword')]

            # 拼接信息
            ##可能出现两中关键字section   排除掉JEL classifiction类型
            # jel_codes_list 关键字列表暂不使用
            return keywords_list
        except Exception as e:
            print("KeyWord error:", e)
            raise e

    else:
        return []


def Async_Scrape(task_queue, exit_event):
    while not exit_event.is_set():
        try:
            # 等待获取任务
            page_source, save_path, index, num, volumn, paper = task_queue.get(timeout=2)
            try:
                Scrape_items(page_source, save_path)
                logger.info("{} : <{}> have finished and saved({}/{})".format(volumn, paper, index, num))
            except Exception as e:
                logger.error("{} : <{}> have failed({}/{}).{}".format(volumn, paper, index, num, e))
            finally:
                task_queue.task_done()
        except queue.Empty:
            time.sleep(1)
            print("Waiting for task...")
            continue
    print("Source process thraed has stopped ")


def Find_Volume_article_page(driver, task_queue, save_path="./"):
    # 获取部件与链接
    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'html.parser')

    text_section = None
    section = soup.find('div', class_='text-s js-issue-in-progress-description')
    if section:
        text_section = section.text
    if text_section == "This issue is in progress but contains articles that are final and fully citable.":
        return None
    margin_section = soup.find("div", class_="row u-margin-l-top")
    volume_section = margin_section.find('div', class_="col-md-16 u-padding-l-right-from-md u-margin-l-bottom")
    # 获取期数
    volume = volume_section.find("h2", class_="u-text-light js-vol-issue").text
    ##创建相应期数文件夹
    folder_path = os.path.join(save_path, volume)
    os.makedirs(folder_path, exist_ok=True)
    logger.info(f"Scrape {volume}")
    # 找到所有的文章项
    articles = driver.find_elements(By.CSS_SELECTOR, ".js-article-list-item")
    if len(articles) == 0:
        return None

    lock.acquire()
    # 遍历每个文章项
    for index in range(len(articles)):
        # 加载文章列表
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".js-article-list-item"))
            )
            articles_new = driver.find_elements(By.CSS_SELECTOR, ".js-article-list-item")
        except TimeoutException:
            logger.error("页面超时未加载所需文章")
            raise TimeoutException
        article = articles_new[index]

        paper = article.find_element(By.CSS_SELECTOR, 'span.js-article-title.text-l').text
        if paper == "Editorial Board":
            continue
        link_element = article.find_element(By.CSS_SELECTOR, '.anchor.article-content-title')
        link_element.click()
        # 等待页面加载
        time.sleep(5)  # 等待3秒，可以根据需要调整
        # 打开作者介绍
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.ID, 'show-more-btn')))
        except TimeoutException:
            driver.refresh()
            WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.ID, 'show-more-btn')))
        try:
            button = driver.find_element(By.ID, 'show-more-btn')
            button.click()
        except Exception as e:
            logger.error("页面超时未加载展示按钮")
            raise e
        time.sleep(2)

        # 尝试获取页面源代码并进行爬取
        try:
            task_queue.put((driver.page_source, folder_path, index + 1, len(articles), volume, paper))
            time.sleep(random.randint(1, 3))
        except Exception as e:
            logger.error(e)
            raise e

        # 返回到列表页面
        volume_link = driver.find_element(By.CSS_SELECTOR, ".text-xs a.anchor")
        volume_link.click()  # 点击链接以跳转
        time.sleep(0.5)

    # 返回当前网页上一级链接
    # previous_section = driver.find_elements(By.XPATH,
    #                                         "//div[@class='u-padding-xs u-text-center navigation-pre u-bg-grey1']")
    # 返回当前网页下一级链接
    previous_section = driver.find_elements(By.XPATH,
                                            "//div[@class='u-padding-xs u-text-center navigation-next u-bg-grey1']")
    # next_section = driver.find_elements(By.XPATH, "//div[@class='u-padding-xs u-text-center navigation-next u-bg-grey1']")
    # # 获取期数切换链接
    # if next_section:
    #     next_link = next_section[0].find_element(By.XPATH, ".//a[@navname='prev-next-issue']")
    if previous_section:
        prev_link = previous_section[0].find_element(By.XPATH, ".//a[@navname='prev-next-issue']")
    # 切换期数
    # if next_section:
    #     next_link.click()
    #     time.sleep(2)
    if previous_section:
        prev_link.click()
        time.sleep(2)
        current_url = driver.current_url
    else:
        current_url = None
    lock.release()
    return current_url


def Get_Web(url, save_path="./", chromedriver_excute_path=None, driver_log_path='chromedriver.log'):
    print("Try to Start Chrome")
    # 启动浏览器
    driver = None
    try:
        if chromedriver_excute_path:
            service = Service(executable_path=chromedriver_excute_path, log_path=driver_log_path)
        else:
            service = Service(executable_path=ChromeDriverManager().install(), log_path=driver_log_path)
        print("start to open chrome")
        driver = webdriver.Chrome(service=service)
    except Exception as e:
        print("Start Chrome Failly", e)
    print("Start Chrome Successfully")

    # 创建线程安全的任务队列并开始处理线程
    task_queue = queue.Queue()
    exit_event = threading.Event()
    handle_thread = threading.Thread(target=Async_Scrape, args=(task_queue, exit_event))
    handle_thread.start()

    # task_queue = asyncio.Queue()
    # exit_event = asyncio.Event()
    # asyncio.create_task(Async_Scrape(task_queue, exit_event,save_path))
    try:
        # 请求获取网页内容
        # response = requests.get(url,headers=headers)
        # if response.status_code != 200:
        #     print("无法获取网页内容。",response.content)

        # 打开网页
        driver.get(url)
        time.sleep(3)

        # 等待手动登录确认
        input("Press Enter to ensure have login")

        # 模拟点击地址栏
        # driver.execute_script("window.focus();")
        # body = driver.find_element("tag name", "body")
        # # 按下回车键以重新加载页面
        # body.send_keys(Keys.RETURN)
        # time.sleep(3)

        while True:
            sign = input("continue to scrape?")
            if sign == "q":
                break
            else:
                # 异步爬取
                # asyncio.run(Find_Volume_article_page(driver,save_path = save_path))
                Find_Volume_article_page(driver, task_queue, save_path=save_path)

        # 等待队列任务完成
        task_queue.join()
        print("Tasks have finished,Process ready to shut down")
        input("Press Enter to close the browser...")
    finally:
        # 关闭浏览器
        driver.quit()


# 自定义 Dumper 来强制 value 使用单引号
class SingleQuotedValueDumper(yaml.SafeDumper):
    def represent_scalar(self, tag, value, style=None):
        # 强制为字符串类型的值使用单引号
        if isinstance(value, str):
            style = "'"
        return super().represent_scalar(tag, value, style)


def update_issue_url(config_path, new_issue_url):
    # 读取yaml文件
    with open(config_path, 'r', encoding='utf-8') as file:
        config_data = yaml.safe_load(file)

    # 更新issue_url
    config_data['issue_url'] = new_issue_url

    # 写回yaml文件
    with open(config_path, 'w', encoding='utf-8') as file:
        yaml.dump(config_data, file, Dumper=SingleQuotedValueDumper, default_flow_style=False, allow_unicode=True)


def Get_Web_Auto(url, save_path="./", chromedriver_excute_path=None, task_queue=None,
                 driver_log_path='chromedriver.log', retry=3, config_path='./config.yml'):
    print("Try to Start Chrome")
    print(f"try {retry}")
    # 启动浏览器
    driver = None
    try:
        if chromedriver_excute_path:
            service = Service(executable_path=chromedriver_excute_path, log_path=driver_log_path)
        else:
            service = Service(executable_path=ChromeDriverManager().install(), log_path=driver_log_path)
        print("start to open chrome")
        driver = webdriver.Chrome(service=service)
    except Exception as e:
        print("Start Chrome Failly", e)
    print("Start Chrome Successfully")

    try:
        # 打开网页
        driver.get(url)
        time.sleep(3)
        # 登录
        # Handle_Login(driver)
        # flag = input("input:")
        # if flag == "q":
        #     driver.quit()
        #     return

        # Find_Volume_article_page(driver, task_queue, save_path=save_path)
        next_url = Find_Volume_article_page(driver, task_queue=task_queue, save_path=save_path)
        if next_url:
            update_issue_url(config_path, next_url)
            logger.info(f"Updated issue url in config.yml to {next_url}")
            driver.quit()
            while not task_queue.empty():
                time.sleep(1)
            time.sleep(random.randint(10, 30))
            Get_Web_Auto(next_url, save_path, chromedriver_excute_path=chromedriver_excute_path, task_queue=task_queue,
                         driver_log_path=driver_log_path, config_path=config_path)

        print("Tasks have finished,Process ready to shut down")
    except Exception as e:
        if retry > 0:
            print(f"Retrying... {retry} attempts remaining.")
            # 在重试前显式关闭浏览器
            driver.quit()  # 关闭浏览器
            return Get_Web_Auto(url, save_path, chromedriver_excute_path=chromedriver_excute_path,
                                task_queue=task_queue, driver_log_path=driver_log_path, retry=retry - 1)
        else:
            print("Max retries reached. Exiting.")
            raise e
    finally:
        if driver:
            driver.quit()


def Handle_Login(driver):
    try:
        # 等待cookie按钮的可点击状态
        button = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.ID, 'onetrust-accept-btn-handler'))
        )
        # 模拟点击按钮
        button.click()
        time.sleep(1)

        # 等待登录按钮可点击
        sign_in_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "gh-institutionalsignin-btn")))
        # 模拟点击
        ActionChains(driver).move_to_element(sign_in_button).click().perform()

        # 等待cookie按钮的可点击状态
        button = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.ID, 'onetrust-accept-btn-handler'))
        )
        # 模拟点击按钮
        button.click()
        time.sleep(1)

        # 等待元素加载并检查可见性
        input_element = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "bdd-email")))
        input_element.send_keys("Southwest University of Finance and Economics")

        # 等待搜索结果加载，确保结果列表出现,使用XPath定位按钮，并等待按钮可点击
        institution_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), '西南财经大学')]"))
        )
        institution_button.click()

        # 显式等待直到用户名密码输入框加载出来
        username_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "username"))
        )
        username_input.send_keys(config.USER_NAME)
        password_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "password"))
        )
        password_input.send_keys(config.PASSWORD)
        # 显式等待直到登录按钮加载出来模拟点击登录按钮
        login_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "login_submit"))
        )
        time.sleep(1)
        login_button.click()

        WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".js-article-list-item"))
        )
        print("Login successfully")
    except Exception as e:
        print(f"Login Failed: {e}")
        raise e


def Scrape_JFE(url, save_path="./", chromedriver_excute_path=None, config_path='./config.yml'):
    '''
    :param url: JFE网址
    :param save_path: 保存下载信息的文件地址
    :param chromedriver_excute_path: 本机chromedriver的下载地址(默认会自动下载运行)
    :return:
    '''
    try:
        # 创建线程安全的任务队列并开始处理线程
        task_queue = queue.Queue()
        exit_event = threading.Event()
        handle_thread = threading.Thread(target=Async_Scrape, args=(task_queue, exit_event))
        handle_thread.start()

        # Get_Web(url, save_path=save_path, chromedriver_excute_path=chromedriver_excute_path)
        Get_Web_Auto(url, save_path=save_path, task_queue=task_queue, chromedriver_excute_path=chromedriver_excute_path, config_path=config_path)
    except Exception as e:
        print(e)
        print("Ready to close all threading")
        # 等待队列任务完成
        exit_event.set()
        task_queue.join()
        handle_thread.join()
    finally:
        exit_event.set()
        task_queue.join()
        handle_thread.join()


def start_JFESprider():
    # save_path = "./Spider/JFE"
    # url = "https://www.sciencedirect.com/journal/journal-of-financial-economics/vol/167/suppl/C"
    # # url = "https://webvpn.swufe.edu.cn/"
    # # url = "https://webvpn.swufe.edu.cn/https/77726476706e69737468656265737421e7e056d234336155700b8ca891472636a6d29e640e/journal/journal-of-financial-economics/vol/163/suppl/C"
    #
    # driver_path = r"C:\Users\winger\.wdm\drivers\chromedriver\win64\134.0.6998.88\chromedriver-win32/chromedriver.exe"
    # Scrape_items(data)
    # Get_Web(url,save_path=save_path,chromedriver_excute_path=driver_path)
    with open("./Spider/JFE/config.yml", "r") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)

    save_path = config["save_path"]
    issue_url = config["issue_url"]
    driver_path = config["driver_path"]
    config_path = config['config_path']
    # Scrape_JFE(issue_url, save_path=save_path, chromedriver_excute_path=driver_path, config_path=config_path)
    Scrape_JFE(issue_url, save_path=save_path, config_path=config_path)

if __name__ == "__main__":
    save_path = "./"
    # url = "https://www.sciencedirect.com/journal/journal-of-financial-economics/vol/167/suppl/C"
    url = "https://www.sciencedirect.com/journal/journal-of-financial-economics/vol/168/suppl/C"
    # url = "https://webvpn.swufe.edu.cn/"
    # url = "https://webvpn.swufe.edu.cn/https/77726476706e69737468656265737421e7e056d234336155700b8ca891472636a6d29e640e/journal/journal-of-financial-economics/vol/163/suppl/C"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36',
        'Cookie': 'your_cookie_here'
    }
    driver_path = r"C:\Users\winger\.wdm\drivers\chromedriver\win64\134.0.6998.88\chromedriver-win32/chromedriver.exe"
    # Scrape_items(data)
    # Get_Web(url,save_path=save_path,chromedriver_excute_path=driver_path)
    Scrape_JFE(url, save_path=save_path, chromedriver_excute_path=driver_path)

    # Southwest University of Finance and Economics
