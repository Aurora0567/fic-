#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/10/26 21:13
# @Author  : ys
# @File    : JFESpider.py
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
from ..utils.logger import Logger
from utils.tools import GetFileName
import base64

# with open(r"C:\Users\pp\Desktop\Refinancing cross-subsidies in the mortgage market - ScienceDirect.html",encoding="utf-8") as file:
#     data = file.read()


logger = Logger(log_filename="scrape_JFE.log").get_logger()


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
    return article_content


async def Handle_article_figures(article_section, save_path="./"):
    # 创建保存图片目录
    os.makedirs(os.path.join(save_path, 'images'), exist_ok=True)
    # 查找所有img元素容器
    images_containers = article_section.find_all('figure', class_='figure text-xs')
    figure_information = {}
    for image in images_containers:
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
            # if img_url.startswith('/'):
            #      img_url = url + img_url  # 拼接基网址

            # 构建图片文件名
            image_name = os.path.join(save_path, 'images', f"page_{00:02}_image_{int(lable[0]):02}.png")
            # 下载图片
            try:
                img_data = requests.get(image_url).content

                # 将二进制数据编码为 Base64
                # img_base64 = base64.b64encode(img_data).decode('utf-8')
                with open(image_name, 'wb') as img_file:
                    img_file.write(img_data)
                print(f"已下载: {image_name}")
            except Exception as e:
                print(f"下载失败: {image_url} - 错误: {e}")

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

    else:
        return []


async def Find_Volume_article_page(driver, save_path="./"):
    # 获取部件与链接
    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'html.parser')
    margin_section = soup.find("div", class_="row u-margin-l-top")
    volume_section = margin_section.find('div', class_="col-md-16 u-padding-l-right-from-md u-margin-l-bottom")
    previous_section = driver.find_elements(By.XPATH,
                                            "//div[@class='u-padding-xs u-text-center navigation-pre u-bg-grey1']")
    next_section = driver.find_elements(By.XPATH,
                                        "//div[@class='u-padding-xs u-text-center navigation-next u-bg-grey1']")

    # 获取期数
    volume = volume_section.find("h2", class_="u-text-light js-vol-issue").text
    ##创建相应期数文件夹
    folder_path = os.path.join(save_path, volume)
    os.makedirs(folder_path, exist_ok=True)
    logger.info(f"Scrape {volume}")

    # 获取期数切换链接
    if next_section:
        next_link = next_section[0].find_element(By.XPATH, ".//a[@navname='prev-next-issue']")
    if previous_section:
        prev_link = previous_section[0].find_element(By.XPATH, ".//a[@navname='prev-next-issue']")

    # 切换期数
    # if next_section:
    #     next_link.click()
    #     time.sleep(2)
    # if previous_section:
    #     prev_link.click()
    #     time.sleep(2)

    # 找到所有的文章项
    articles = driver.find_elements(By.CSS_SELECTOR, ".js-article-list-item")

    tasks = []
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
        article = articles_new[index]

        # 获取链接点击
        # link = article.find_element(By.CSS_SELECTOR, ".article-content-title a").get_attribute("href")
        # ActionChains(driver).move_to_element(article).click(
        #     article.find_element(By.CSS_SELECTOR, ".article-content-title a")).perform()

        link_element = article.find_element(By.CSS_SELECTOR, '.anchor.article-content-title')
        link_element.click()

        # 等待页面加载
        time.sleep(5)  # 等待3秒，可以根据需要调整
        # 打开作者介绍
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.ID, 'show-more-btn'))
            )
        except TimeoutException:
            logger.error("页面超时未加载展示按钮")

        button = driver.find_element(By.ID, 'show-more-btn')
        button.click()
        time.sleep(2)
        # 尝试获取页面源代码并进行爬取
        try:
            tasks.append(asyncio.create_task(Async_Scrape(driver.page_source, folder_path)))
            # Scrape_items(driver.page_source,save_path=folder_path)
        except Exception as e:
            logger.error(e)

        # 返回到列表页面
        volume_link = driver.find_element(By.CSS_SELECTOR, ".text-xs a.anchor")
        volume_link.click()  # 点击链接以跳转
    await asyncio.gather(*tasks)


# 异步爬取函数
async def Async_Scrape(page_source, save_path):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(ThreadPoolExecutor(), Scrape_items, page_source, save_path)


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
                asyncio.run(Find_Volume_article_page(driver, save_path=save_path))

        input("Press Enter to close the browser...")
    finally:
        # 关闭浏览器
        driver.quit()


def Scrape_JFE(url, save_path="./", chromedriver_excute_path=None):
    '''
    :param url: JFE网址
    :param save_path: 保存下载信息的文件地址
    :param chromedriver_excute_path: 本机chromedriver的下载地址(默认会自动下载运行)
    :return:
    '''
    try:
        Get_Web(url, save_path=save_path, chromedriver_excute_path=chromedriver_excute_path)
    except Exception as e:
        print(e)


if __name__ == "__main__":
    save_path = "./"
    url = "https://www.sciencedirect.com/journal/journal-of-financial-economics/vol/151/suppl/C"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36',
        'Cookie': 'your_cookie_here'
    }
    driver_path = r"C:\Users\pp\.wdm\drivers\chromedriver\win64\130.0.6723.91\chromedriver-win32/chromedriver.exe"
    # Scrape_items(data)
    # Get_Web(url,save_path=save_path,chromedriver_excute_path=driver_path)
    Scrape_JFE(url, save_path=save_path, chromedriver_excute_path=driver_path)

    # Southwest University of Finance and Economics
