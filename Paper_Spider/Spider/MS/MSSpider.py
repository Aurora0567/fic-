import os
import time
import asyncio
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
from dateutil import parser
from PIL import Image, ImageEnhance
from io import BytesIO

# logger = Logger(log_directory="./Spider/MS/logs", log_filename="scrape_MS.log").get_logger()
logger = Logger(log_directory="./logs", log_filename="scrape_MS.log").get_logger()

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
    return soup.find('span', class_='epub-section__date').get_text(strip=True)


def format_date(date_str):
    date_obj = parser.parse(date_str)
    formatted_date = date_obj.strftime("%Y/%m/%d")
    return formatted_date


def get_authors_info(soup):  # 提取作者信息
    authors_info = {}
    # 找到所有的作者元素（包括可见的和隐藏的）
    author_elements = soup.find_all('div', class_='accordion-tabbed__tab-mobile')
    # 处理可见的作者
    for author in author_elements:
        name = author.find("p", class_="author-name").get_text(strip=True)
        p_tags = author.find_all("p")
        affiliation_div = None
        for p_tag in p_tags:
            if not p_tag.find():
                affiliation_div = p_tag.get_text(strip=True)
        if affiliation_div:
            institution = affiliation_div
        else:
            institution = 'No affiliation'
        authors_info[name] = institution
    return authors_info


def get_abstract_text(soup):  # 提取摘要
    abstract_section = soup.find('div', class_='abstractSection abstractInFull')
    if abstract_section:
        abstract_text = abstract_section.find('p')
        if abstract_text:
            return abstract_text.get_text(strip=True)
    return ""


def get_article_content(soup):  # 获取这篇文论的目录
    article_content = []
    headers = soup.find_all('h2', class_=['abstract-title', 'section-title',
                                          'backacknowledgements-title js-splitscreen-backacknowledgements-title',
                                          'backreferences-title js-splitscreen-backreferences-title'])
    for header in headers:
        title_text = header.get_text(strip=True)  # 去除多余空格
        article_content.append(title_text)
    return article_content

def get_paper_link(soup):
    a_tag = soup.find("a", class_="epub-section__doi__text")
    doi_link = None
    if a_tag:
        doi_link = a_tag.get("href")
    return doi_link

def extract_reference(reference_note):
    # 用来存放拼接的文献内容
    reference_parts = []

    for element in reference_note.contents:
        if isinstance(element, str):
            text = element.strip()
            if text:
                text = text.replace('\n', '')
                reference_parts.append(text)

        elif element.name == "contrib-group":
            reference_parts.append(element.get_text(strip=True))

        elif element.name == "span":
            classes = element.get("class", [])
            text = element.get_text(strip=True)
            if text:
                text = text.replace('\n', '')
                if "references__year" in classes:
                    reference_parts.append(text)
                elif "references__authors" in classes:
                    reference_parts.append(text)
                elif "references__article-title" in classes:
                    reference_parts.append(text)
                elif "references__source" in classes:
                    reference_parts.append(text)

    return " ".join(reference_parts)

def get_ref_list(soup):  # 提取参考文献列表，按顺序返回
    # 找到所有参考文献条目
    reference_items = soup.find_all("li", class_="references__item")
    all_references = []
    for item in reference_items:
        note = item.find("span", class_="references__note")
        if note:
            ref_text = extract_reference(note)
            all_references.append(ref_text)
    return all_references


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
    # 定位到全文部分的容器
    fulltext_div = soup.find("div", class_="hlFld-Fulltext")
    if not fulltext_div:
        return None
    # 获取所有元素（包括标题和段落），保持顺序
    elements = fulltext_div.find_all(["h2", "h3", "h4", "h5", "h6", "p"], recursive=True)
    full_text = []
    current_section = None
    conclusion_mode = False  # 用来标记是否进入 Conclusion 特殊处理模式
    exit_mode = False  # 标记是否要退出
    for element in elements:
        if exit_mode:
            break

        if element.name == "h2":
            # 每次遇到新的 h2，都要重置 conclusion mode
            conclusion_mode = False

            title_text = element.get_text(strip=True)

            # 检查是否是 Conclusion
            if "Conclusion" in title_text:
                conclusion_mode = True

            current_section = {
                "title": element.get_text(strip=True),
                "content": []
            }
            full_text.append(current_section)

            # 如果是 Conclusion，开始往后检查紧跟的内容
            if conclusion_mode:
                next_sibling = element.find_next_sibling()
                while next_sibling:
                    # 处理所有内容，包含 <p>, <h3>, <div> 等标签
                    if next_sibling.name == "p":
                        text = next_sibling.get_text(strip=True)
                        if text:
                            current_section["content"].append(text)

                    elif next_sibling.name == "div":
                        class_attr = next_sibling.get("class", [])
                        if "ack" in class_attr or "notes" in class_attr or "NLM_app-group" in class_attr:
                            exit_mode = True
                            break

                        # 处理 div 标签内容
                        div_content = next_sibling.get_text(strip=True)
                        if div_content:
                            current_section["content"].append(div_content)

                    elif next_sibling:
                        text = next_sibling.get_text(strip=True)
                        if text:
                            current_section["content"].append(text)

                    # 继续查找下一个兄弟元素
                    next_sibling = next_sibling.find_next_sibling()

        elif current_section and not conclusion_mode:
            text = element.get_text(strip=True)
            if text:
                current_section["content"].append(text)

    final_result = {}

    for section in full_text:
        title = section['title']
        content = " ".join(section['content'])
        final_result[title] = content

    return final_result


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
    image_links = []
    # 找到所有 figure，遍历里面的 img
    figures = soup.find_all("figure", class_="article__inlineFigure")
    prefix_link = "https://pubsonline.informs.org"
    for figure in figures:
        img_tag = figure.find("img", class_="figure__image")
        if img_tag:
            src = img_tag.get("src")
            if src:
                full_url = prefix_link + src
                image_links.append(full_url)
    return image_links


def get_all_figures_info(soup):
    figures_info = {}
    graphics = soup.find_all('figure', class_='article__inlineFigure')
    for graphic in graphics:
        figcaption = graphic.find("figcaption")
        if not figcaption:
            continue

        caption_label = figcaption.find("span", class_="captionLabel")
        if caption_label:
            match = re.search(r'\d+', caption_label.get_text())
            if match:
                figure_number = match.group()
            else:
                continue
        else:
            continue

        strong_tag = figcaption.find("strong")
        if strong_tag:
            description = strong_tag.get_text(separator=" ", strip=True).replace(caption_label.get_text(strip=True), "").strip()
        else:
            description = ""

        figures_info[figure_number] = {
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
        image_name = os.path.join(save_path, 'images', f"page_{00:02}_image_{n:02}.png")
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
    abstract_text = get_abstract_text(soup)  ### 摘要文本内容
    ref_list = get_ref_list(soup)  ### 参考文献列表
    full_text = get_full_text(soup, abstract_text, ref_list)  ### 论文全文
    # article_dict = generate_article_dic(article_content, full_text, abstract_text)  ### 论文全文，结构化字典

    if full_text:
        information['ifarticle'] = True
    else:
        information['ifarticle'] = False
    information['type'] = 'Management Science'
    information['link'] = get_paper_link(soup)
    information['public'] = format_date(public_date)
    information['title'] = paper_title
    information['abstract'] = abstract_text
    information['citation_count'] = None
    information['keys'] = None
    information['author'] = authors_info
    information['article'] = full_text
    information['references'] = ref_list

    ## 创建相应文件夹
    file_name = GetFileName(paper_title)
    file_floder = os.path.join(save_path, file_name)
    os.makedirs(file_floder, exist_ok=True)
    logger.info(f"已经创建{file_name}文件")

    # 保存为 information.json 文件
    with open(os.path.join(file_floder, 'information.json'), 'w', encoding='utf-8') as json_file:
        json.dump(information, json_file, ensure_ascii=False, indent=4)
    logger.info(f"已将{paper_title}的information保存为json文件")
    # 处理图片
    Handle_figures(soup, save_path=file_floder, chromedriver_excute_path=chromedriver_excute_path)
    logger.info(f"已将{paper_title}的图片保存")

    logger.info(f"{paper_title}处理完毕！")


# 异步爬取函数
async def Async_Scrape(page_source, save_path, chromedriver_excute_path=None):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(ThreadPoolExecutor(), Scrape_items, page_source, save_path, chromedriver_excute_path)


###### 获取期刊页面、本期的论文列表 ######
async def get_original_article_links(driver, chromedriver_excute_path=None, save_path="./",
                                     driver_log_path='chromedriver.log', is_intact='False', config_path="./config.yaml"):
    """抓取 Original Article 部分的论文全文链接。"""

    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'html.parser')

    buttons = driver.find_elements(By.ID, 'hs-eu-confirmation-button')
    if buttons:
        # 等待并点击“Accept”按钮
        button = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.ID, 'hs-eu-confirmation-button'))
        )
        button.click()
        time.sleep(1)

    volume = soup.find('h2', class_="volume--title").text
    # volume = "".join(c for c in volume if c.isalnum() or c in " _-").strip()
    folder_path = os.path.join(save_path, volume)
    # 判断之前是否已经爬取过并且该卷是否爬完整
    if os.path.exists(folder_path) and "True" in is_intact:
        logger.info(f"{folder_path} 已经爬取完毕!")
        return

    os.makedirs(folder_path, exist_ok=True)
    logger.info(f"Scrape {volume}")

    # 找到第一个h2标题
    h2_tags = soup.find_all("h2", class_="toc__heading section__title to-section")
    research_heading = None

    for h2 in h2_tags:
        if "Research Articles" in h2.get_text():
            research_heading = h2
            break

    if not research_heading:
        logger.error(f"未找到 Research Articles 分区")

    # 遍历 “Research Articles” 分区下的每篇文章
    articles = []
    for sibling in research_heading.find_next_siblings():
        # 如果再遇到一个 h2，说明已经到下一个大分区，停止
        if sibling.name == "h2":
            break
        # 如果是 <div class="issue-item">，则属于当前分区的文章
        if sibling.name == "div" and "issue-item" in sibling.get("class", []):
            articles.append(sibling)

    # 要添加的url前缀
    url_prefix = "https://pubsonline.informs.org"
    # 保存每篇文章的链接
    article_links = []
    for item in articles:
        title_tag = item.find("h5", class_="issue-item__title")
        if title_tag:
            a_tag = title_tag.find("a")
            if a_tag:
                href = a_tag.get("href")
                full_url = url_prefix + href
                article_links.append(full_url)
    # 收集所有任务
    # tasks = []

    max_retries = 5  # 设置最大重试次数
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

    a_tag = None
    next_url = None
    url_prefix = 'https://pubsonline.informs.org'
    span_tag = soup.find("div", class_="content-navigation clearfix")
    if span_tag:
        a_tag = span_tag.find("a", class_="content-navigation__btn--next")
    if a_tag:
        href = a_tag.get("href")
        if href:
            next_url = url_prefix + href
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

def Get_Web(issue_url, save_path="./", chromedriver_excute_path=None, driver_log_path='chromedriver.log', config_path="./config.yml", is_intact='False'):
    print("Try to Start Chrome")
    # 启动浏览器
    # 配置浏览器选项
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # 无头模式（后台运行）
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
            logger.info("start to open chrome")
            driver = webdriver.Chrome(service=service, options=options)
            driver.get(issue_url)
            WebDriverWait(driver, 60).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete")
            logger.info(f"{issue_url} loaded successfully.")
            break
        except Exception as e:
            logger.error(f"Failed to load {issue_url} (Attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error("Max retries reached. Failed to load page.")
                # 如果达到最大重试次数，关闭浏览器并退出
                if driver:
                    driver.quit()
                exit()

    try:
        asyncio.run(get_original_article_links(driver, chromedriver_excute_path, save_path, driver_log_path, is_intact=is_intact, config_path=config_path))
        next_url = Find_Next_url(driver)
        if next_url:
            update_issue_url(config_path, next_url)
            logger.info(f"Updated issue url in config.yml to {next_url}")
            driver.quit()
            time.sleep(random.randint(10, 30))
            Get_Web(next_url, save_path, chromedriver_excute_path, driver_log_path, config_path=config_path)
    finally:
        if driver:
            driver.quit()
    # try:
    #     # 打开网页
    #     driver.get(issue_url)
    #     WebDriverWait(driver, 60).until(
    #         lambda driver: driver.execute_script("return document.readyState") == "complete")
    #
    #     asyncio.run(get_original_article_links(driver, chromedriver_excute_path, save_path, driver_log_path))
    #
    #     # # 爬取单篇论文
    #     # # 尝试获取页面源代码并进行爬取
    #     # try:
    #     #     Scrape_items(driver.page_source, save_path="./")
    #     # except Exception as e:
    #     #     logger.error(e)
    #
    #     # input("Press Enter to close the browser...")
    # except Exception as e:
    #     print(f"等待页面完全加载时发生错误: {e}")
    # finally:
    #     driver.quit()


######### MS总爬取函数 ########

def Scrape_MS(MS_url, save_path="./", chromedriver_excute_path=None, config_path="./config.yml", is_intact='False'):
    '''
    :param MS_url: MS网址
    :param save_path: 保存下载信息的文件地址
    :param chromedriver_excute_path: 本机chromedriver的下载地址(默认会自动下载运行)
    :return:
    '''
    try:
        Get_Web(MS_url, save_path=save_path, chromedriver_excute_path=chromedriver_excute_path, config_path=config_path, is_intact=is_intact)
    except Exception as e:
        print(e)

def Get_Web_One(article_url, save_path="./", chromedriver_excute_path=None, driver_log_path='chromedriver.log', config_path="./config.yml"):
    print("Try to Start Chrome")
    # 启动浏览器
    # 配置浏览器选项
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")  # 无头模式（后台运行）
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    driver = None
    if chromedriver_excute_path:
        service = Service(executable_path=chromedriver_excute_path, log_path=driver_log_path)
    else:
        service = Service(executable_path=ChromeDriverManager().install(), log_path=driver_log_path)

    driver = webdriver.Chrome(service=service, options=options)

    try:
        # 打开网页
        driver.get(article_url)
        WebDriverWait(driver, 60).until(
            lambda driver: driver.execute_script("return document.readyState") == "complete")

        Scrape_items(driver.page_source, save_path, chromedriver_excute_path=chromedriver_excute_path)

        # # 爬取单篇论文
        # # 尝试获取页面源代码并进行爬取
        # try:
        #     Scrape_items(driver.page_source, save_path="./")
        # except Exception as e:
        #     logger.error(e)

        # input("Press Enter to close the browser...")
    except Exception as e:
        print(f"等待页面完全加载时发生错误: {e}")
    finally:
        driver.quit()


def start_MSSprider():
    # save_path = "./Spider/MS"
    # # chromedriver路径，如果没有将chromedriver_excute_path设为None即可
    # driver_path = r"C:\Users\winger\.wdm\drivers\chromedriver\win64\133.0.6943.141/chromedriver.exe"

    with open("./Spider/MS/config.yml", "r") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)

    save_path = config["save_path"]
    issue_url = config["issue_url"]
    driver_path = config["driver_path"]
    config_path = config["config_path"]
    is_intact = config["is_intact"]
    # Scrape_MS(issue_url, save_path, chromedriver_excute_path=driver_path, config_path=config_path, is_intact=is_intact)
    Scrape_MS(issue_url, save_path, config_path=config_path, is_intact=is_intact)


if __name__ == "__main__":
    save_path = "./"
    issue_url = "https://pubsonline.informs.org/toc/mnsc/71/3"
    article_url = "https://pubsonline.informs.org/doi/10.1287/mnsc.2021.02781"

    driver_path = r"C:\Users\winger\.wdm\drivers\chromedriver\win64\135.0.7049.42\chromedriver-win32/chromedriver.exe"
    # Scrape_MS(issue_url, save_path, chromedriver_excute_path=driver_path)

    Get_Web_One(article_url, chromedriver_excute_path=driver_path, save_path=save_path)

    print("爬取完毕")
