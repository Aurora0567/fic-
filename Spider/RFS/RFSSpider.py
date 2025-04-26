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

# logger = Logger(log_directory="./Spider/RFS/logs", log_filename="scrape_RFS.log").get_logger()
logger = Logger(log_directory="./Spider/logs", log_filename="clock.log").get_logger()

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
    return soup.find('h1',
                     class_='wi-article-title article-title-main accessible-content-title at-articleTitle').get_text(
        strip=True)


def get_public_date(soup):  # 提取出版日期
    return soup.find('div', class_='citation-date').get_text(strip=True)


def format_date(date_str):
    date_object = datetime.strptime(date_str, "%d %B %Y")
    formatted_date = date_object.strftime("%Y/%m/%d")
    return formatted_date


def get_authors_info(soup):  # 提取作者信息
    authors_info = {}
    # 找到所有的作者元素（包括可见的和隐藏的）
    author_elements = soup.find_all('span', class_='al-author-name js-flyout-wrap')
    more_author_elements = soup.find_all('span', class_='al-author-name-more js-flyout-wrap')
    # 处理可见的作者
    for author in author_elements:
        name_button = author.find('button', class_='linked-name')
        name = name_button.get_text(strip=True) if name_button else "Unknown"
        has_contact = author.find('i', class_='icon-general-mail') is not None
        if has_contact:
            name += '*'  # 如果有通讯方式，姓名后加 '*'
        affiliation_div = author.find('div', class_='info-card-affilitation')
        if affiliation_div:
            institution = affiliation_div.get_text(strip=True)
        else:
            institution = 'No affiliation'
        if name != "Unknown":
            authors_info[name] = institution
    # 处理隐藏的作者（需要点击查看的作者）
    for more_author in more_author_elements:
        name_button = more_author.find('button', class_='linked-name js-linked-name-trigger btn-as-link')
        name = name_button.get_text(strip=True) if name_button else "Unknown"
        has_contact = more_author.find('i', class_='icon-general-mail') is not None
        if has_contact:
            name += '*'  # 如果有通讯方式，姓名后加 '*'
        affiliation_div = more_author.find('div', class_='info-card-affilitation')
        if affiliation_div:
            institution = affiliation_div.get_text(strip=True)
        else:
            institution = 'No affiliation'
        if name != "Unknown":
            authors_info[name] = institution
    return authors_info


def get_abstract_text(soup):  # 提取摘要
    abstract_section = soup.find('section', class_='abstract')
    if abstract_section:
        abstract_text = abstract_section.find('p', class_='chapter-para')
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


def get_ref_list(soup):  # 提取参考文献列表，按顺序返回
    ref_list = []  # 存储所有参考文献
    # 查找参考文献列表容器
    ref_container = soup.find('div', class_='ref-list js-splitview-ref-list')
    if not ref_container:
        logger.error("没有找到参考文献列表容器")
        return ref_list
    # 按顺序获取所有引用条目
    ref_items = ref_container.find_all('div', class_='mixed-citation citation')
    if not ref_items:
        logger.error("没有找到任何引用条目")
        return ref_list
    # 遍历每一条引用
    for ref in ref_items:
        # 提取每条引用的相关信息
        citation = ref.get_text(separator=" ", strip=True)
        if citation:
            ref_list.append(citation)  # 添加到结果列表中
    # 清洗，删去'Google Scholar'及其后的内容
    cleaned_list = []
    for ref in ref_list:
        if 'Google Scholar' in ref:
            ref = ref.split('Google Scholar')[0].strip()
        cleaned_list.append(ref)
    return cleaned_list


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
    # 定位到目标区域
    content_div = soup.find('div', class_='widget-items', attrs={'data-widgetname': 'ArticleFulltext'})
    if not content_div:
        logger.error("未找到指定的内容区域")
        return ""
    full_text = []
    # 遍历所有下一级的直接子标签
    for child in content_div.find_all(recursive=False):
        if isinstance(child, NavigableString):
            continue
        # 检查是否是要忽略的元素
        if child.name == 'div' and 'role' in child.attrs and child['role'] == 'button':
            continue
        if child.has_attr('class') and 'article-metadata-panel clearfix at-ArticleMetadata' in child['class']:
            continue
        # 存储当前标签的文本内容
        current_text = []
        # 提取当前标签的文本内容
        if child.name in ['blockquote', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'ul', 'ol']:
            text = child.get_text(strip=True)
            if text:
                current_text.append(text)
                # 检测到 'References' 时停止
                if child.name == 'h2' and text == 'References':
                    break
        # 对于 div 标签，递归提取其内部的纯文本
        elif child.name == 'div':
            for desc in child.descendants:
                # button中的文本不提取
                if desc.name == 'a' and desc.get('role') == 'button':
                    continue
                if isinstance(desc, NavigableString) and desc.strip():
                    current_text.append(desc.strip())
        # 如果当前标签有文本，则将它们拼接，并添加到全局文本列表中
        if current_text:
            full_text.append(" ".join(current_text))
    # 拼接全文
    first_part = full_text[0] + "\n\n" + abstract_text
    middle_part = "\n\n".join(full_text[1:])
    refs = "\n\n".join(ref_list)
    full_text_result = first_part + "\n\n" + middle_part + "\n\n" + "References\n\n" + refs
    full_text_result = remove_duplicates(full_text_result)  ### 移除重复内容
    return full_text_result


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
    images = soup.find_all('img', class_='content-image')
    src_list = [img['src'] for img in images if 'src' in img.attrs]
    return src_list


def get_all_figures_info(soup):
    figures_info = {}
    graphics = soup.find_all('div', class_='graphic-bottom')
    for graphic in graphics:
        fig_name = graphic.find('div', class_='label fig-label').text.strip()
        fig_number_match = re.search(r'(?:Figure|Fig\.)\s*([A-Za-z0-9]+)', fig_name)  ##匹配“Fig."格式，需要修改
        if fig_number_match:
            fig_number = fig_number_match.group(1)
            description_paragraphs = graphic.find('div', class_='caption fig-caption').find_all('p',
                                                                                                class_='chapter-para')
            description = '. '.join([p.text.strip() for p in description_paragraphs])
            figures_info[fig_number] = {
                "description": description,
                "correlation": []
            }
    return figures_info


def Handle_figures(soup, save_path="./"):
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
        try:
            img_data = requests.get(fig_url).content
            with open(image_name, 'wb') as img_file:
                img_file.write(img_data)
            print(f"已下载: {image_name}")
        except Exception as e:
            logger.error(f"下载失败: {fig_url} - 错误: {e}")


###### 爬取单篇论文 ######
def Scrape_items(html_source, save_path="./"):
    soup = BeautifulSoup(html_source, 'html.parser')
    information = {}

    public_date = get_public_date(soup)  ### 出版日期
    authors_info = get_authors_info(soup)  ### 作者信息
    article_content = get_article_content(soup)  ### 一级目录
    paper_title = get_paper_title(soup)  ### 论文标题
    abstract_text = get_abstract_text(soup)  ### 摘要文本内容
    ref_list = get_ref_list(soup)  ### 参考文献列表
    full_text = get_full_text(soup, abstract_text, ref_list)  ### 论文全文，长文本
    article_dict = generate_article_dic(article_content, full_text, abstract_text)  ### 论文全文，结构化字典

    information['type'] = 'The Review of Financial Studies'
    information['link'] = soup.find('link', {'rel': 'canonical'})['href']  ### 论文链接
    information['public'] = format_date(public_date)
    information['title'] = paper_title
    information['abstract'] = abstract_text
    information['citation_count'] = None
    information['keys'] = None
    information['author'] = authors_info
    information['article'] = article_dict
    information['ifarticle'] = True
    information['references'] = ref_list

    ## 创建相应文件夹
    file_name = GetFileName(paper_title)
    file_floder = os.path.join(save_path, file_name)
    os.makedirs(file_floder, exist_ok=True)
    logger.info(f"已经创建{file_name}文件")

    # 如果只有 Abstract 一个键，说明没有获取全文
    if list(article_dict.keys()) == ['Abstract']:
        information['ifarticle'] = False

    information['article'].pop("Abstract", None)
    information['article'].pop("References", None)
    information['article'].pop("Supplementary data", None)

    # 保存为 information.json 文件
    with open(os.path.join(file_floder, 'information.json'), 'w', encoding='utf-8') as json_file:
        json.dump(information, json_file, ensure_ascii=False, indent=4)
    logger.info(f"已将{paper_title}的information保存为json文件")
    # 处理图片
    Handle_figures(soup, save_path=file_floder)
    logger.info(f"已将{paper_title}的图片保存")

    logger.info(f"{paper_title}爬取完毕！")


# 异步爬取函数
async def Async_Scrape(page_source, save_path):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(ThreadPoolExecutor(), Scrape_items, page_source, save_path)


###### 获取期刊页面、本期的论文列表 ######
async def get_original_article_links(driver, chromedriver_excute_path=None, save_path="./",
                                     driver_log_path='chromedriver.log', is_intact='False', config_path="./config.yml"):
    """抓取 Original Article 部分的论文全文链接。"""

    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'html.parser')

    volume = soup.find("div", class_="issue-info-pub").text
    # volume = "".join(c for c in volume if c.isalnum() or c in " _-").strip()
    folder_path = os.path.join(save_path, volume)
    # 判断之前是否已经爬取过
    if os.path.exists(folder_path) and is_intact:
        logger.info(f"{folder_path} 已经爬取完毕!")
        return

    os.makedirs(folder_path, exist_ok=True)
    logger.info(f"Scrape {volume}")

    containers = soup.find_all('div', class_='section-container')
    logger.info(f"找到 {len(containers)} 个 section-container 容器")
    original_article_container = None
    for container in containers:
        h4_tag = container.find('h4', class_='title articleClientType act-header')
        if h4_tag and h4_tag.get_text().strip() == 'Articles':
            original_article_container = container
            break
    if not original_article_container:
        logger.error("未找到 'Articles' 部分")
        driver.quit()
        return []

    articles = driver.find_elements(By.CSS_SELECTOR, ".al-article-item-wrap")
    # logger.info(f"找到 {len(articles)} 篇论文")
    article_links_old = soup.find_all('a', class_='at-articleLink')
    url_prefix = 'https://academic.oup.com'
    article_links = [f"{url_prefix}{article.get('href')}" for article in article_links_old]
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
    url_prefix = 'https://academic.oup.com'
    span_tag = soup.find("span", class_="issue-link--next")
    if span_tag:
        a_tag = span_tag.find("a")
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


######### RFS总爬取函数 ########

def Scrape_RFS(RFS_url, save_path="./", chromedriver_excute_path=None, config_path="./config.yml", is_intact='False'):
    '''
    :param RFS_url: RFS网址
    :param save_path: 保存下载信息的文件地址
    :param chromedriver_excute_path: 本机chromedriver的下载地址(默认会自动下载运行)
    :return:
    '''
    try:
        Get_Web(RFS_url, save_path=save_path, chromedriver_excute_path=chromedriver_excute_path, config_path=config_path, is_intact=is_intact)
    except Exception as e:
        print(e)


#####爬取单篇论文####

def start_RFSSprider():
    # save_path = "./Spider/RFS"
    # issue_url = "https://academic.oup.com/rfs/issue/38/2"
    # article_url = "https://academic.oup.com/rfs/article-abstract/38/2/507/7918340"
    #
    # # chromedriver路径，如果没有将chromedriver_excute_path设为None即可
    # driver_path = r"C:\Users\winger\.wdm\drivers\chromedriver\win64\133.0.6943.141/chromedriver.exe"

    with open("./Spider/RFS/config.yml", "r") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)

    save_path = config["save_path"]
    issue_url = config["issue_url"]
    driver_path = config["driver_path"]
    config_path = config["config_path"]
    is_intact = config["is_intact"]
    # Scrape_RFS(issue_url, save_path, chromedriver_excute_path=driver_path, config_path=config_path, is_intact=is_intact)
    Scrape_RFS(issue_url, save_path, config_path=config_path, is_intact=is_intact)

if __name__ == "__main__":
    save_path = "./"
    issue_url = "https://academic.oup.com/rfs/issue/38/4"
    article_url = "https://academic.oup.com/rfs/article-abstract/38/2/507/7918340"

    driver_path = r"C:\Users\winger\.wdm\drivers\chromedriver\win64\133.0.6943.141/chromedriver.exe"
    Scrape_RFS(issue_url, save_path, chromedriver_excute_path=driver_path)

    # TEST_one(article_url, save_path, chromedriver_excute_path = driver_path)

    print("爬取完毕")
