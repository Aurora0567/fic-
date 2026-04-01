import os
import time
import asyncio
from io import BytesIO

import requests
import random
from selenium import webdriver
from selenium.common import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup, NavigableString
import re
import json
import yaml
from datetime import datetime
from utils.logger import Logger
from utils.tools import GetFileName
from PIL import Image, ImageEnhance
from io import BytesIO

logger = Logger(log_directory="./Spider/JF/logs", log_filename="scrape_JF.log").get_logger()


def clear_oup_cookies(driver):
    # 获取所有Cookies
    cookies = driver.get_cookies()
    # 遍历并删除与 https://academic.oup.com 相关的Cookies
    for cookie in cookies:
        if 'oup.com' in cookie['domain']:
            driver.delete_cookie(cookie['name'])


######## 爬取 #########
###### 处理文本 ######
def get_paper_title(soup):  # 提取论文标题
    return soup.find('h1', class_='citation__title').get_text(strip=True)


def get_public_date(soup):  # 提取出版日期
    return soup.find('span', class_='epub-date').get_text(strip=True)


def format_date(date_str):
    date_object = datetime.strptime(date_str, "%d %B %Y")
    formatted_date = date_object.strftime("%Y/%m/%d")
    return formatted_date


def get_authors_info(soup):  # 提取作者信息
    # 找到所有的作者元素
    author_elements = soup.find('div', class_='comma__list')
    authors = {}
    if author_elements:
        # 提取所有作者标签，并去重生成字典
        author_tags = author_elements.find_all('p', class_='author-name')
        authors = {tag.get_text(strip=True): "" for tag in author_tags}

    return authors


def get_abstract_text(soup):  # 提取摘要
    # abstract_section = soup.find('section', class_='abstract')
    # if abstract_section:
    #     abstract_text = abstract_section.find('p', class_='chapter-para')
    #     if abstract_text:
    #         return abstract_text.get_text(strip=True)
    # return ""
    abstract_section = soup.find('div', class_='abstract-group')
    abstract = ""
    if abstract_section:
        abstract = "\n".join(p.get_text(strip=True) for p in abstract_section.find_all('p'))
    return abstract


def get_article_content(soup):  # 获取这篇文论的目录
    # article - section__title section__title section1
    article_content = []
    headers = soup.find_all('h2', class_=['abstract-title', 'section-title',
                                          'backacknowledgements-title js-splitscreen-backacknowledgements-title',
                                          'backreferences-title js-splitscreen-backreferences-title'])
    for header in headers:
        title_text = header.get_text(strip=True)  # 去除多余空格
        article_content.append(title_text)
    return article_content


def get_ref_list(soup):  # 提取参考文献列表，按顺序返回
    # 抓取参考文献
    references_section = soup.find('ul', class_='rlist separator')
    references = []
    if references_section:
        for li in references_section.find_all('li'):
            reference_text = []
            for element in li.children:
                if element.name == 'div' and 'extra-links' in element.get('class', []):
                    break
                if element.name == 'span' and 'hidden' in element.get('class', []):
                    continue
                if element.name == 'a' and any(kw in element.get_text() for kw in ['Web of Science', 'Google Scholar']):
                    continue
                text = element.get_text(strip=True)
                if text:
                    reference_text.append(text)
            reference_text = " ".join(reference_text)
            references.append(reference_text)
    return references


def remove_duplicates(text):
    seen = set()
    result = []
    segments = text.split("\n\n")
    for segment in segments:
        stripped_segment = segment.strip()
        if stripped_segment and stripped_segment not in seen:
            seen.add(stripped_segment)
            result.append(stripped_segment)
    return "\n\n".join(result)


def get_full_text(soup, abstract_text, ref_list):  # 获取全文
    """
    从 <div class="widget-items" data-widgetname="ArticleFulltext"> 内提取所有下一级标签的文本内容，
    包括 p, h1-h2, h3, h4, h5, h6, li, ul, div 等。
    对于 div 标签，递归提取其内部的纯文本。
    """
    # 抓取正文
    full_text_section = soup.find('section', class_='article-section article-section__full')
    if full_text_section is None:
        print(f"未找到文章正文部分: {article_url}")
        return  # 如果没有正文部分，跳过此文章

    introduction, sections = [], {}
    current_section = ""
    in_introduction = True

    for element in full_text_section.find_all(['h2', 'p']):
        if element.name == 'h2':
            current_section = element.get_text(strip=True)
            if current_section == "REFERENCES":
                break
            sections[current_section] = ""
            in_introduction = False
        elif element.name == 'p':
            text = element.get_text(strip=True) + "\n"
            if in_introduction:
                introduction.append(text)
            else:
                sections[current_section] += text

    section_content = {"introduction": "".join(introduction)}
    section_content.update(sections)
    return section_content


def generate_article_dic(article_content, full_text, abstract_text):
    article_dict = {}
    # 遍历一级标题，提取对应内容
    for i in range(len(article_content)):
        start_key = article_content[i]
        end_key = article_content[i + 1] if i + 1 < len(article_content) else None

        # 查找当前标题在全文中的位置
        start_idx = full_text.find(start_key)
        if end_key:
            end_idx = full_text.find(end_key)
        else:
            end_idx = len(full_text)  # 如果没有下一个标题，设置为全文结束
        if start_idx != -1:
            # 提取当前标题下的内容
            content = full_text[start_idx + len(start_key):end_idx].strip()
            article_dict[start_key] = content
        else:
            # 如果标题在全文中找不到，赋值为空字符串
            article_dict[start_key] = ""

    # 找到 'Abstract' 后面的一个键，并修改其值
    abstract_index = article_content.index('Abstract')  # 找到 'Abstract' 的索引
    if abstract_index + 1 < len(article_content):  # 确保 'Abstract' 后面还有其他键
        next_key_value = article_content[abstract_index + 1]
        # 找到 abstract_text 在全文中的结束位置
        abstract_end_idx = full_text.find(abstract_text) + len(abstract_text)
        next_key_start_idx = full_text.find(next_key_value)
        # 从 'Abstract' 到 next_key_value 之间的文本
        new_text = full_text[abstract_end_idx:next_key_start_idx].strip()
        # 将 new_text 添加到 next_key_value 的原内容之前
        article_dict[next_key_value] = new_text + "\n" + article_dict[next_key_value]
    return article_dict


###### 处理图片 ######
def get_figures_links(soup):
    figure_sections = soup.find_all('img', class_='figure__image')
    src_list = []
    for img in figure_sections:
        img_url = img.get('src')
        if img_url and img_url.startswith('/'):
            img_url = "https://onlinelibrary.wiley.com" + img_url
        src_list.append(img_url)
    return src_list


def get_all_figures_info(soup):
    graphics = soup.find_all('section', class_='article-section__inline-figure')
    figures_info = {}
    for graphic in graphics:
        fig_name = graphic.find('strong', class_='figure__title').get_text(strip=True)
        fig_number_match = re.search(r'(?:Figure|Fig\.)\s*([A-Za-z0-9]+)', fig_name)  ##匹配“Fig."和"Figure "格式
        if fig_number_match:
            fig_number = fig_number_match.group(1)
            description_paragraphs = graphic.find('div', class_='figure__caption figure__caption-text').get_text()
            # 去掉 \xao 特殊字符
            if '\xa0' in description_paragraphs:
                description_paragraphs = description_paragraphs.replace('\xa0', ' ')
            # 检查是否包含特定句子，并去掉它
            if "[Color figure can be viewed at wileyonlinelibrary.com]" in description_paragraphs:
                description = description_paragraphs.replace("[Color figure can be viewed at wileyonlinelibrary.com]",
                                                             "").strip()
            else:
                description = description_paragraphs
            # description = '. '.join([p.text.strip() for p in description_paragraphs])
            figures_info[fig_number] = {
                "description": description,
                "correlation": []
            }
    return figures_info


def Handle_figures(soup, save_path="./", chromedriver_excute_path=None):
    # 配置浏览器选项
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # 无头模式（后台运行）
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    # 初始化浏览器
    # driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    if chromedriver_excute_path:
        service = Service(executable_path=chromedriver_excute_path)
    else:
        service = Service(executable_path=ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    # 创建保存图片目录
    os.makedirs(os.path.join(save_path, 'images'), exist_ok=True)
    ### 保存为 information.json 文件
    figures_info = get_all_figures_info(soup)
    image_information_name = os.path.join(save_path, "images_information.json")
    with open(image_information_name, 'w', encoding='utf-8') as file:
        json.dump(figures_info, file, ensure_ascii=False, indent=4)
    ### 下载图片
    fig_url_list = get_figures_links(soup)
    for n, fig_url in enumerate(fig_url_list, start=1):
        # 构建图片文件名
        image_name = os.path.join(save_path, 'images', f"page_{00:02}_image_{n:02}.jpg")
        # header = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        #           'Referer': 'https://onlinelibrary.wiley.com'}
        # 下载图片
        max_retries = 5  # 最大重试次数
        retry_delay = random.randint(5, 8)  # 每次重试的间隔时间（秒）
        for attempt in range(max_retries):
            try:
                driver.set_window_size(2400, 1800)
                driver.get(fig_url)
                # 等待Cloudflare验证完成（可能需要手动调整时间）
                time.sleep(random.randint(3, 6))  # 若验证未完成，需延长等待时间

                # 获取放大后的位置与尺寸（像素）
                rect = driver.execute_script("""
                    const img = document.querySelector("img");
                    const rect = img.getBoundingClientRect();
                    return {
                        left: rect.left,
                        top: rect.top,
                        width: rect.width,
                        height: rect.height
                    };
                """)

                img_element = driver.find_element("tag name", "img")

                # # 获取图像的大小和位置
                # location = img_element.location
                # size = img_element.size

                # 获取 DPR（设备像素比）用于缩放位置和尺寸
                dpr = driver.execute_script("return window.devicePixelRatio")

                # 获取真实图片内容
                screenshot_png = driver.get_screenshot_as_png()
                image = Image.open(BytesIO(screenshot_png))

                # 计算图像在截图中的实际像素位置
                left = int(rect['left'] * dpr)
                top = int(rect['top'] * dpr)
                right = int((rect['left'] + rect['width']) * dpr)
                bottom = int((rect['top'] + rect['height']) * dpr)

                # 进行裁剪
                im_cropped = image.crop((left, top, right, bottom))

                # 提升对比度
                enhancer = ImageEnhance.Contrast(im_cropped)
                im_contrast = enhancer.enhance(1.5)

                # 锐化图像
                sharpener = ImageEnhance.Sharpness(im_contrast)
                im_sharper = sharpener.enhance(2)

                buffer = BytesIO()

                im_sharper.save(buffer, format='PNG')

                img_data = buffer.getvalue()

                # img_data = requests.get(fig_url).content
                with open(image_name, 'wb') as img_file:
                    img_file.write(img_data)
                print(f"已下载: {image_name}")
                break
            except Exception as e:
                logger.error(f"下载失败: {fig_url}(Attempt {attempt + 1}/{max_retries}) - 错误: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Max retries reached. Failed to load image:{fig_url}")


###### 爬取单篇论文 ######
def Scrape_items(html_source, save_path="./", chromedriver_excute_path=None):
    soup = BeautifulSoup(html_source, 'html.parser')
    information = {}

    public_date = get_public_date(soup)  ### 出版日期
    authors_info = get_authors_info(soup)  ### 作者信息
    # article_content = get_article_content(soup)  ### 一级目录
    paper_title = get_paper_title(soup)  ### 论文标题
    target_title = {"ISSUE INFORMATION", "ANNOUNCEMENTS", "AMERICAN FINANCE ASSOCIATION"}
    if paper_title in target_title:
        return
    abstract_text = get_abstract_text(soup)  ### 摘要文本内容
    ref_list = get_ref_list(soup)  ### 参考文献列表
    full_text = get_full_text(soup, abstract_text, ref_list)  ### 论文全文，长文本
    # article_dict =  generate_article_dic(article_content, full_text, abstract_text) ### 论文全文，结构化字典

    information['type'] = 'The Review of Financial Studies'

    information['link'] = soup.find('a', class_='epub-doi').get('href')  ### 论文链接
    information['public'] = format_date(public_date)
    information['title'] = paper_title
    information['abstract'] = abstract_text
    information['citation_count'] = None
    information['keys'] = None
    information['author'] = authors_info
    information['article'] = full_text
    information['ifarticle'] = True
    information['references'] = ref_list

    ## 创建相应文件夹
    file_name = GetFileName(paper_title)
    file_floder = os.path.join(save_path, file_name)
    os.makedirs(file_floder, exist_ok=True)
    logger.info(f"已经创建{file_name}文件")

    # 如果只有 Abstract 一个键，说明没有获取全文
    if list(full_text.keys()) == ['Abstract']:
        information['ifarticle'] = False

    information['article'].pop("Abstract", None)
    information['article'].pop("References", None)
    information['article'].pop("Supporting Information", None)

    # 保存为 information.json 文件
    with open(os.path.join(file_floder, 'information.json'), 'w', encoding='utf-8') as json_file:
        json.dump(information, json_file, ensure_ascii=False, indent=4)
    logger.info(f"已将{paper_title}的information保存为json文件")
    # 处理图片
    Handle_figures(soup, save_path=file_floder, chromedriver_excute_path=chromedriver_excute_path)
    logger.info(f"已将{paper_title}的图片保存")

    logger.info(paper_title)


# 异步爬取函数
async def Async_Scrape(page_source, save_path, chromedriver_excute_path=None):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(ThreadPoolExecutor(), Scrape_items, page_source, save_path, chromedriver_excute_path)


###### 获取期刊页面、本期的论文列表 ######
async def get_original_article_links(driver, save_path="./", chromedriver_excute_path=None,
                                     driver_log_path='chromedriver.log', is_intact='False', config_path="./config.yaml"):
    """抓取 Original Article 部分的论文全文链接。"""

    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'html.parser')

    parent_item_div = soup.find('div', class_='cover-image__parent-item')
    volume_issue = "volume_issue"
    if parent_item_div:
        h1_tag = parent_item_div.find('h1')
        if h1_tag:
            text = h1_tag.get_text(strip=True)

            match = re.search(r'Volume (\d+),\s*Issue (\d+)', text)
            if match:
                volume = f"Volume {match.group(1)},"
                issue = f"Issue {match.group(2)}"
                volume_issue = f"{volume} {issue}"
    folder_path = os.path.join(save_path, volume_issue)
    # 判断之前是否已经爬取过
    if os.path.exists(folder_path) and "True" in is_intact:
        logger.info(f"{folder_path} 已经爬取完毕!")
        return

    os.makedirs(folder_path, exist_ok=True)
    logger.info(f"Scrape {volume_issue}")

    # containers = soup.find_all('div', class_='issue-items-container bulkDownloadWrapper')
    # print(f"找到 {len(containers)} 个 bulkDownloadWrapper 容器")
    # original_article_container = None
    # for container in containers:
    #     h4_tag = container.find('h4', class_='title articleClientType act-header')
    #     if h4_tag and h4_tag.get_text().strip() == 'Articles':
    #         original_article_container = container
    #         break
    # if not original_article_container:
    #     print("未找到 'Articles' 部分")
    #     driver.quit()
    #     return []

    # articles = driver.find_elements(By.CSS_SELECTOR, ".al-article-item-wrap")
    # print(f"找到 {len(articles)} 篇论文")
    article_links_old = soup.find_all('a', class_='issue-item__title visitable')
    # 定义要排除的标题
    exclude_titles = ["ISSUE INFORMATION", "ANNOUNCEMENTS", "AMERICAN FINANCE ASSOCIATION", "AWARDS AND PRIZES",
                      "REPORTS OF THE AMERICAN FINANCE ASSOCIATION"]
    # 要添加的url前缀
    url_prefix = "https://onlinelibrary.wiley.com"

    article_links = []
    for article in article_links_old:
        # 获取标题文本
        title = article.find_next('h2').get_text(strip=True)
        if title not in exclude_titles:
            href = article.get('href')
            full_url = url_prefix + href
            article_links.append(full_url)
    # logger.info(f"找到 {len(article_links)} 篇论文")
    # tasks = []
    max_retries = 10  # 设置最大重试次数
    retry_count = 0  # 当前重试次数
    # 未处理成功的文章链接
    untreated_article_links = article_links.copy()
    while untreated_article_links and retry_count < max_retries:
        logger.info(f"开始第 {retry_count + 1} 次处理，共 {len(untreated_article_links)} 篇文章")
        current_links = untreated_article_links.copy()
        untreated_article_links.clear()
        # 遍历每个文章项
        for idx, article_link in enumerate(current_links, start=1):
            options = webdriver.ChromeOptions()
            options.add_argument("--headless")  # 无头模式（后台运行）
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument(
                "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            # driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            try:
                if chromedriver_excute_path:
                    service = Service(executable_path=chromedriver_excute_path, log_path=driver_log_path)
                else:
                    service = Service(executable_path=ChromeDriverManager().install(), log_path=driver_log_path)
                logger.info(f"start to open chrome {article_link}({idx}/{len(current_links)})")
                driver = webdriver.Chrome(service=service, options=options)
                driver.get(article_link)

                # 等待Cloudflare验证完成（可能需要手动调整时间）
                # time.sleep(10)  # 若验证未完成，需延长等待时间

                # 等待页面完全加载
                WebDriverWait(driver, 60).until(
                    lambda driver: driver.execute_script("return document.readyState") == "complete")
                logger.info(f"{article_link} 加载完成!")

                # 尝试获取页面源代码并进行爬取
                try:
                    task = asyncio.create_task(Async_Scrape(driver.page_source, folder_path))
                    await task
                    # tasks.append(task)
                except Exception as e:
                    logger.error(f"爬取文章时发生错误: {e}")
                    untreated_article_links.append(article_link)

            except Exception as e:
                logger.error(f"加载页面失败: {e}")
                untreated_article_links.append(article_link)

            finally:
                driver.quit()

        retry_count += 1

    if untreated_article_links:
        logger.warning(f"以下文章仍未成功处理（共 {len(untreated_article_links)} 篇）:")
        for link in untreated_article_links:
            logger.warning(link)
    else:
        logger.info("所有文章处理成功。")
        is_intact = 'True'
        update_state(config_path, is_intact)


def Find_Next_url(driver):
    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'html.parser')

    next_url = soup.find("a", class_="content-navigation__btn--next")
    if next_url:
        next_url = next_url["href"]
    if next_url and "https://onlinelibrary.wiley.com" not in next_url:
        next_url = "https://onlinelibrary.wiley.com" + next_url
    return next_url


# 自定义 Dumper 来强制 value 使用单引号
class SingleQuotedValueDumper(yaml.SafeDumper):
    def represent_scalar(self, tag, value, style=None):
        # 强制为字符串类型的值使用单引号
        if isinstance(value, str):
            style = "'"
        return super().represent_scalar(tag, value, style)


def update_state(config_path, new_state):
    # 读取yaml文件
    with open(config_path, 'r', encoding='utf-8') as file:
        config_data = yaml.safe_load(file)

    # 更新is_intact
    config_data['is_intact'] = new_state

    # 写回yaml文件
    with open(config_path, 'w', encoding='utf-8') as file:
        yaml.dump(config_data, file, Dumper=SingleQuotedValueDumper, default_flow_style=False, allow_unicode=True)


def update_issue_url(config_path, new_issue_url):
    # 读取yaml文件
    with open(config_path, 'r', encoding='utf-8') as file:
        config_data = yaml.safe_load(file)

    # 更新issue_url
    config_data['issue_url'] = new_issue_url
    config_data['is_intact'] = 'False'

    # 写回yaml文件
    with open(config_path, 'w', encoding='utf-8') as file:
        yaml.dump(config_data, file, Dumper=SingleQuotedValueDumper, default_flow_style=False, allow_unicode=True)


def Get_Web(issue_url, save_path="./", chromedriver_excute_path=None, driver_log_path='chromedriver.log',
            config_path='./config.yml', is_intact='False'):
    print("Try to Start Chrome")
    # 启动浏览器
    # 配置浏览器选项
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")  # 无头模式（后台运行）
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    driver = None
    # try:
    #     if chromedriver_excute_path:
    #         service = Service(executable_path=chromedriver_excute_path, log_path=driver_log_path)
    #     else:
    #         service = Service(executable_path=ChromeDriverManager().install(), log_path=driver_log_path)
    #     print("start to open chrome")
    #     driver = webdriver.Chrome(service=service, options=options)
    # except Exception as e:
    #     print("Start Chrome Failly", e)
    # print("Start Chrome Successfully")

    # 尝试打开网页，超时则重试
    max_retries = 10  # 最大重试次数
    retry_delay = random.randint(5, 8)  # 每次重试的间隔时间（秒）
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting to open {issue_url} (Attempt {attempt + 1}/{max_retries})...")
            if chromedriver_excute_path:
                service = Service(executable_path=chromedriver_excute_path, log_path=driver_log_path)
            else:
                service = Service(executable_path=ChromeDriverManager().install(), log_path=driver_log_path)
            print("start to open chrome")
            driver = webdriver.Chrome(service=service, options=options)
            driver.get(issue_url)
            WebDriverWait(driver, 60).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete")
            logger.info(f"{issue_url} loaded successfully.")
            break
        except Exception as e:
            logger.error(f"Failed to load {issue_url} (Attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error("Max retries reached. Failed to load page.")
                # 如果达到最大重试次数，关闭浏览器并退出
                if driver:
                    driver.quit()
                exit()

    try:
        asyncio.run(get_original_article_links(driver, save_path, chromedriver_excute_path=chromedriver_excute_path,
                                               driver_log_path=driver_log_path,is_intact=is_intact, config_path=config_path))
        next_url = Find_Next_url(driver)
        if next_url:
            update_issue_url(config_path, next_url)
            logger.info(f"Updated issue url in config.yml to {next_url}")
            driver.quit()
            time.sleep(random.randint(10, 30))
            Get_Web(next_url, save_path, chromedriver_excute_path, driver_log_path, config_path=config_path,is_intact=is_intact)
    finally:
        if driver:
            driver.quit()


######### RFS总爬取函数 ########
def Scrape_RFS(RFS_url, save_path="./", chromedriver_excute_path=None, config_path='./config.yml', is_intact='False'):
    '''
    :param RFS_url: RFS网址
    :param save_path: 保存下载信息的文件地址
    :param chromedriver_excute_path: 本机chromedriver的下载地址(默认会自动下载运行)
    :return:
    '''
    try:
        Get_Web(RFS_url, save_path=save_path, chromedriver_excute_path=chromedriver_excute_path,
                config_path=config_path, is_intact=is_intact)
    except Exception as e:
        print(e)


def Get_Web_One(issue_url, save_path="./", chromedriver_excute_path=None, driver_log_path='chromedriver.log'):
    print("Try to Start Chrome")
    # 启动浏览器
    # 配置浏览器选项
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")  # 无头模式（后台运行）
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    driver = None
    # try:
    #     if chromedriver_excute_path:
    #         service = Service(executable_path=chromedriver_excute_path, log_path=driver_log_path)
    #     else:
    #         service = Service(executable_path=ChromeDriverManager().install(), log_path=driver_log_path)
    #     print("start to open chrome")
    #     driver = webdriver.Chrome(service=service, options=options)
    # except Exception as e:
    #     print("Start Chrome Failly", e)
    # print("Start Chrome Successfully")

    # 尝试打开网页，超时则重试
    max_retries = 5  # 最大重试次数
    retry_delay = random.randint(5, 8)  # 每次重试的间隔时间（秒）
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting to open {issue_url} (Attempt {attempt + 1}/{max_retries})...")

            if chromedriver_excute_path:
                service = Service(executable_path=chromedriver_excute_path, log_path=driver_log_path)
            else:
                service = Service(executable_path=ChromeDriverManager().install(), log_path=driver_log_path)
            print("start to open chrome")
            driver = webdriver.Chrome(service=service, options=options)
            driver.get(issue_url)
            WebDriverWait(driver, 60).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete")
            print(f"{issue_url} loaded successfully.")
            break
        except Exception as e:
            print(f"Failed to load {issue_url} (Attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print("Max retries reached. Failed to load page.")
                # 如果达到最大重试次数，关闭浏览器并退出
                if driver:
                    driver.quit()
                exit()

    # 爬取单篇论文
    # 尝试获取页面源代码并进行爬取
    try:
        Scrape_items(driver.page_source, save_path="./", chromedriver_excute_path=chromedriver_excute_path)
    except Exception as e:
        logger.error(e)

    finally:
        driver.quit()


def Scrape_RFS_One(RFS_url, save_path="./", chromedriver_excute_path=None):
    '''
    :param RFS_url: RFS网址
    :param save_path: 保存下载信息的文件地址
    :param chromedriver_excute_path: 本机chromedriver的下载地址(默认会自动下载运行)
    :return:
    '''
    try:
        Get_Web_One(RFS_url, save_path=save_path, chromedriver_excute_path=chromedriver_excute_path)
    except Exception as e:
        print(e)


def start_JFSprider():
    # save_path = "./Spider/JF"
    # issue_url = "https://onlinelibrary.wiley.com/toc/15406261/2024/79/6"
    # article_url = "https://onlinelibrary.wiley.com/doi/10.1111/jofi.13411"
    #
    # # chromedriver路径，如果没有将chromedriver_excute_path设为None即可
    # driver_path = r"C:\Users\winger\.wdm\drivers\chromedriver\win64\133.0.6943.141/chromedriver.exe"
    with open("./Spider/JF/config.yml", "r") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)

    save_path = config["save_path"]
    issue_url = config["issue_url"]
    driver_path = config["driver_path"]
    config_path = config["config_path"]
    is_intact = config["is_intact"]
    # Scrape_RFS(issue_url, save_path, chromedriver_excute_path=driver_path, config_path=config_path, is_intact=is_intact)
    Scrape_RFS(issue_url, save_path, config_path=config_path, is_intact=is_intact)
    print("爬取完毕")


if __name__ == "__main__":
    save_path = "./"
    issue_url = "https://onlinelibrary.wiley.com/toc/15406261/2024/79/6"
    article_url = "https://onlinelibrary.wiley.com/doi/10.1111/jofi.13411"

    driver_path = r"C:\Users\winger\.wdm\drivers\chromedriver\win64\135.0.7049.42\chromedriver-win32/chromedriver.exe"
    # Scrape_RFS(issue_url, save_path, chromedriver_excute_path=driver_path)
    Scrape_RFS_One(article_url, save_path, chromedriver_excute_path=driver_path)

    print("爬取完毕")
