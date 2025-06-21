# 导入必要的 Python 模块
import os  # 用于文件和目录操作
import json  # 用于处理 JSON 文件
import re  # 用于正则表达式处理
import requests  # 用于发送 HTTP 请求
import uuid  # 用于生成唯一文件名
import shutil  # 用于文件复制
from typing import List, Dict  # 用于类型注解
import logging  # 用于日志记录

# 假设 WeChatMaterialManager 已定义在 Account_API.upload_picture 中
from Account_API.upload_picture import WeChatMaterialManager

# 配置日志记录，保存到 upload.log 文件
logging.basicConfig(filename='upload.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 定义获取微信 access_token 的函数
def get_access_token(appid: str, appsecret: str) -> str:
    """获取微信接口调用凭证（access_token）

    Args:
        appid (str): 微信公众号 appid
        appsecret (str): 微信公众号 appsecret

    Returns:
        str: access_token，若失败返回空字符串
    """
    url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={appid}&secret={appsecret}"
    try:
        response = requests.get(url, timeout=10)
        result = response.json()
        if 'access_token' in result:
            logging.info("成功获取 access_token")
            return result['access_token']
        else:
            logging.error(f"获取Token失败: {result.get('errmsg', '未知错误')}")
            raise Exception(f"获取Token失败: {result.get('errmsg', '未知错误')}")
    except Exception as e:
        logging.error(f"Token请求异常: {str(e)}")
        print(f"Token请求异常: {str(e)}")
        return ""

# 定义上传图片到微信素材库的函数
def upload_image(access_token: str, image_path: str) -> Dict:
    """上传图片到微信素材库并返回 media_id 和 URL

    Args:
        access_token (str): 微信 access_token
        image_path (str): 图片文件路径

    Returns:
        Dict: 包含 media_id 和 url 的字典
    """
    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"
    try:
        with open(image_path, 'rb') as file:
            files = {'media': (os.path.basename(image_path), file)}
            response = requests.post(url, files=files, timeout=10)
        result = response.json()
        if 'media_id' in result and 'url' in result:
            logging.info(f"图片 {image_path} 上传成功，media_id: {result['media_id']}")
            return {'media_id': result['media_id'], 'url': result['url']}
        else:
            logging.error(f"图片上传失败 {image_path}: {result.get('errmsg', '未知错误')}")
            raise Exception(f"图片上传失败: {result.get('errmsg', '未知错误')}")
    except Exception as e:
        logging.error(f"上传图片 {image_path} 失败: {str(e)}")
        print(f"上传图片 {image_path} 失败: {str(e)}")
        return {'media_id': '', 'url': ''}

# 定义通过 media_id 获取素材 URL 的函数
def get_material_url(access_token: str, media_id: str) -> str:
    """通过 media_id 从微信获取素材的 URL

    Args:
        access_token (str): 微信 access_token
        media_id (str): 素材的 media_id

    Returns:
        str: 素材的 URL，若失败返回空字符串
    """
    url = f"https://api.weixin.qq.com/cgi-bin/material/get_material?access_token={access_token}"
    try:
        response = requests.post(url, json={"media_id": media_id}, timeout=10)
        result = response.json()
        if "errcode" in result:
            logging.error(f"获取素材 URL 失败 (media_id: {media_id}): {result['errmsg']}")
            return ""
        url = result.get("url", "")
        logging.info(f"成功获取素材 URL (media_id: {media_id}): {url}")
        return url
    except Exception as e:
        logging.error(f"获取素材 URL 失败 (media_id: {media_id}): {str(e)}")
        print(f"获取素材 URL 失败 (media_id: {media_id}): {str(e)}")
        return ""

# 定义解析期刊目录的函数
def parse_volume(volume_path: str, access_token: str) -> List[Dict]:
    """
    解析期刊目录结构，提取文章元数据并上传每篇文章的第一张图片（重命名为唯一名称）

    Args:
        volume_path (str): 期刊卷目录路径
        access_token (str): 微信 access_token

    Returns:
        List[Dict]: 包含文章元数据和图片 URL 的字典列表
    """
    articles = []
    if not os.path.isdir(volume_path):
        logging.error(f"路径 {volume_path} 不存在或不是文件夹")
        print(f"错误：路径 {volume_path} 不存在或不是文件夹")
        return articles

    for root, dirs, files in os.walk(volume_path):
        first_image = None
        if "images" in dirs:
            images_path = os.path.join(root, "images")
            if os.path.isdir(images_path):
                image_files = [f for f in os.listdir(images_path) if f.lower().endswith(('jpg', 'jpeg', 'png'))]
                if image_files:
                    first_image = os.path.join(images_path, image_files[0])
        json_path = os.path.join(root, "information.json")
        if "information.json" in files:
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                highlights = data.get("Highlights", "")
                if isinstance(highlights, str):
                    highlights_list = [h.strip() for h in highlights.split("|||") if h.strip()]
                    cleaned_highlights = [re.sub(r'^学术要点\s*\d+：', '', hl).strip() for hl in highlights_list]
                    highlights = cleaned_highlights
                else:
                    highlights = highlights if isinstance(highlights, list) else []

                image_info = {'media_id': '', 'url': ''} if first_image else {'media_id': '', 'url': ''}
                renamed_image_path = None
                if first_image:
                    file_ext = os.path.splitext(first_image)[1].lower()
                    unique_name = f"{uuid.uuid4().hex}{file_ext}"
                    renamed_image_path = os.path.join(os.path.dirname(first_image), unique_name)
                    shutil.copy2(first_image, renamed_image_path)
                    image_info = upload_image(access_token, renamed_image_path)
                    # os.remove(renamed_image_path)  # 注释掉以便调试

                article = {
                    "AItitle": data.get("AItitle", ""),
                    "title": data.get("title", ""),
                    "link": data.get("link", ""),
                    "author": data.get("author", ""),
                    "AIkeys": data.get("AIkeys", []),
                    "AIsummary": data.get("AIsummary", ""),
                    "Highlights": highlights,
                    "AIfig": data.get("AIfig", []),
                    "first_image": renamed_image_path if renamed_image_path else first_image,
                    "image_url": image_info['url']
                }

                if not article["title"]:
                    logging.warning(f"{json_path} 中缺少 title 字段")
                    print(f"警告：{json_path} 中缺少 title 字段")
                    continue

                articles.append(article)
                logging.info(f"成功解析文章: {article['title']}")

            except json.JSONDecodeError as e:
                logging.error(f"JSON解析失败 {json_path}: {str(e)}")
                print(f"JSON解析失败 {json_path}: {str(e)}")
            except Exception as e:
                logging.error(f"处理文件失败 {json_path}: {str(e)}")
                print(f"处理文件失败 {json_path}: {str(e)}")

    return articles

# 定义生成微信草稿内容的函数
def generate_content(articles: List[Dict], title: str, periodical: str, material_file: str, access_token: str) -> Dict:
    """
    生成微信公众号草稿的 HTML 内容，在开头插入 JF_Top.png，封面使用 JF.png

    Args:
        articles (List[Dict]): 文章元数据列表
        title (str): 草稿标题
        periodical (str): 期刊名称（如 'JF'）
        material_file (str): wechat_materials.json 文件路径
        access_token (str): 微信 access_token

    Returns:
        Dict: 包含草稿内容的字典
    """
    top_fig_url = ""
    thumb_media_id = ""
    logging.info(f"开始生成草稿内容，期刊: {periodical}，标题: {title}")
    logging.info(f"当前工作目录: {os.getcwd()}")

    try:
        with open(material_file, 'r', encoding='utf-8') as f:
            materials = json.load(f)
        if 'materials' not in materials:
            materials['materials'] = []
            logging.warning(f"{material_file} 缺少 'materials' 键，已初始化为空列表")

        for item in materials['materials']:
            if item.get('file_name') == f"{periodical}.png":
                thumb_media_id = item.get('media_id', '')

        logging.info(f"JF.png media_id: {thumb_media_id}")

        # 使用基于脚本位置的路径
        script_dir = os.path.dirname(os.path.abspath(__file__))
        material_dir = os.path.normpath(os.path.join(script_dir, "..", "Material"))
        top_fig_path = os.path.join(material_dir, f"{periodical}_Top.png")
        logging.info(f"JF_Top.png 路径: {top_fig_path}")

        if os.path.exists(top_fig_path):
            logging.info(f"正在上传 {periodical}_Top.png")
            image_info = upload_image(access_token, top_fig_path)
            top_fig_url = image_info['url']
            if image_info['media_id']:
                logging.info(f"成功上传 {periodical}_Top.png，media_id: {image_info['media_id']}")
                print(f"成功上传 {periodical}_Top.png")
            else:
                logging.error(f"上传 {top_fig_path} 失败")
                print(f"上传 {top_fig_path} 失败")
        else:
            logging.error(f"图片 {top_fig_path} 不存在")
            print(f"错误：{top_fig_path} 不存在，无法上传")

        thumb_fig_path = os.path.join(material_dir, f"{periodical}.png")
        if not thumb_media_id and os.path.exists(thumb_fig_path):
            logging.info(f"在 {material_file} 中未找到 {periodical}.png 的 media_id，尝试上传")
            image_info = upload_image(access_token, thumb_fig_path)
            thumb_media_id = image_info['media_id']
            if thumb_media_id:
                materials['materials'].append({
                    "file_name": f"{periodical}.png",
                    "media_id": thumb_media_id,
                    "media_type": "image",
                    "upload_time": "",
                    "expires_time": None,
                    "is_permanent": True
                })
                with open(material_file, 'w', encoding='utf-8') as f:
                    json.dump(materials, f, ensure_ascii=False, indent=4)
                logging.info(f"已上传 {periodical}.png，media_id: {thumb_media_id}")
                print(f"已上传 {periodical}.png 并更新 {material_file}")
            else:
                logging.error(f"上传 {thumb_fig_path} 失败")
                print(f"上传 {thumb_fig_path} 失败")
        elif not thumb_media_id:
            logging.error(f"图片 {thumb_fig_path} 不存在")
            print(f"错误：{thumb_fig_path} 不存在，无法上传")

    except FileNotFoundError:
        logging.error(f"{material_file} 文件不存在")
        print(f"错误：{material_file} 文件不存在")
        materials = {'materials': []}
        with open(material_file, 'w', encoding='utf-8') as f:
            json.dump(materials, f, ensure_ascii=False, indent=4)
    except json.JSONDecodeError:
        logging.error(f"{material_file} 不是有效的 JSON 文件")
        print(f"错误：{material_file} 不是有效的 JSON 文件")
        raise
    except Exception as e:
        logging.error(f"读取 {material_file} 失败: {str(e)}")
        print(f"读取 {material_file} 失败: {str(e)}")
        raise

    content = ""
    if top_fig_url:
        content += f"""
            <p style="text-align: center;">
                <img src="{top_fig_url}" alt="Top Image" style="max-width: 100%; height: auto; display: block; margin: 0 auto;" />
            </p>
            <p></p>
        """
        logging.info(f"成功插入 {periodical}_Top.png，URL: {top_fig_url}")
    else:
        content += f"""
            <p style="text-align: center; color: red;">未找到 {periodical}_Top.png 的有效图片</p>
            <p></p>
        """
        logging.warning(f"未插入 {periodical}_Top.png，因缺少有效 URL")

    # 生成文章标题列表
    title_list = f'<h2 style="font-size: 20px; font-weight: bold; font-family: SimSun, serif; color: rgb(0, 63, 182);">本期看点</h2>\n<ul>'
    for idx, article in enumerate(articles, 1):
        title_list += f'<li style="font-size: 17px; color: rgb(98, 98, 98);">{re.sub(r"（.*?）", "", article["AItitle"]).strip()}</li>'
    title_list += "</ul>"

    content += title_list
    for idx, article in enumerate(articles, 1):
        authors_html = ""
        if article["author"]:
            authors_html = "".join(
                f'<p style="text-align: center; font-size: 16px; color: rgb(62, 62, 62)"><strong>{name.strip()}</strong></p>'
                f'<p style="margin-left: 10px; margin-bottom: 10px; text-align: center;">{institution}</p>'
                for name, institution in article["author"].items()
            )
        else:
            authors_html = '<p>未知作者</p>'

        highlights_html = ""
        for hl in article["Highlights"]:
            match = re.match(r'^(.*?）)\s*(.*)$', hl)
            if match:
                bold_content = match.group(1).strip()
                description = match.group(2).strip() if match.group(2) else ''
                highlights_html += f'<p style="margin-bottom: 8px; font-size: 14px; font-family: SimSun, serif; color: rgb(98, 98, 98);"><span style="display: inline;"><strong style="display: inline;">{bold_content}</strong> {description}</span></p>'
            else:
                highlights_html += f'<p style="margin-bottom: 8px; font-size: 14px; font-family: SimSun, serif; color: rgb(98, 98, 98);">{hl}</p>'

        content += f"""
            <p></p>
            <p style="text-align: center; font-size: 36px; font-weight: bold; color: rgb(0, 63, 182);">{idx:02d}</p>
            <p style="text-align: center; font-size: 20px; font-weight: bold; color: rgb(0, 63, 182);">{re.sub(r"（.*?）", "", article["AItitle"]).strip()}</p>
            <p style="text-align: center; font-size: 20px; font-weight: bold; color: rgb(0, 63, 182);">{article['title']}</p>
            <p style="text-align: center; font-size: 12px; font-style: italic; color: rgba(0, 163, 182, 0.85)">原文链接：<a href="{article['link']}">{article['link']}</a></p>
            <p></p>
            <p style="text-align: center; font-size: 16px; font-weight: bold; color: rgb(30, 30, 30);">1、作者</p>
            {authors_html}
            <p></p>
            <p style="text-align: center; font-size: 16px; font-weight: bold; color: rgb(30, 30, 30);">2、Keywords</p>
            <p style="text-align: center; font-size: 16px; font-family: SimSun, serif; color: rgb(62, 62, 62);">{'；'.join(article['AIkeys'])}</p>
            <p></p>
            <p style="text-align: center; font-size: 16px; font-weight: bold; color: rgb(30, 30, 30);">3、AI精炼/Abstract</p>
            <p style="text-align: center; font-size: 16px; font-family: SimSun, serif; color: rgb(98, 98, 98);">{article['AIsummary']}</p>
            <p></p>
        """

        if article["image_url"]:
            content += f"""
                <p style="text-align: center;">
                    <img src="{article['image_url']}" alt="First Image" style="max-width: 100%; height: auto; display: block; margin: 0 auto;" />
                </p>
            """
            if article["AIfig"]:
                AIfig = article["AIfig"][0]
                content += f"""
                    <p style="font-size: 16px; font-family: SimSun, serif; color: rgb(62, 62, 62);">图片AI描述：</p>
                    <p style="font-size: 16px; font-family: SimSun, serif; color: rgb(62, 62, 62);">{AIfig}</p>
                """
            content += "<p></p>"

        content += f"""
            <p style="text-align: center; font-size: 16px; font-weight: bold; color: rgb(30, 30, 30);">4、学术要点</p>
            {highlights_html}
            <p></p>
            <hr style="width: 50%; margin: 20px auto;"/>
        """

    content += f'''
        <p style="text-align: center; font-size: 14px; font-weight: bold; color: rgb(0, 59, 169);">本推文基于FIC论文智能解析系统</p>
        <p style="text-align: center; font-size: 14px; font-weight: bold; color: rgb(0, 59, 169);">利用爬虫、RAG、LLM agent等AI技术</p>
        <p style="text-align: center; font-size: 14px; font-weight: bold; color: rgb(0, 59, 169);">完成西财顶级学术期刊全流程自动化获取、解析与推文生成</p>
        <p style="text-align: center; font-size: 14px; font-weight: bold; color: rgb(0, 59, 169);">仅限于读者交流学习。如有侵权，请联系删除。</p>
        <p style="text-align: center; font-size: 22px; font-weight: bold; color: rgb(0, 59, 169); font-style: italic;">END</p>
        <hr style="width: 20%; margin: 20px auto;"/>
        <p style="text-align: center; font-size: 13px; font-weight: bold; color: rgba(0, 163, 182, 0.5);">指导老师 | 李庆</p>
        <p style="text-align: center; font-size: 13px; font-weight: bold; color: rgba(0, 163, 182, 0.5);">AI解析 | FIC论文智能解析项目组</p>
        <p style="text-align: center; font-size: 13px; font-weight: bold; color: rgba(0, 163, 182, 0.5);">责任编辑 | 张林</p>
        <p style="text-align: center; font-size: 13px; font-weight: bold; color: rgba(0, 163, 182, 0.5);">执行编辑 | 曾馨熠</p>
        <p style="text-align: center; font-size: 13px; font-weight: bold; color: rgba(0, 163, 182, 0.5);">校对 | 李知微</p>
    '''

    return {
        "title": title,
        "author": "",
        "content": content,
        "digest": f"本期收录{len(articles)}篇前沿论文，涵盖...",
        "thumb_media_id": thumb_media_id  # 优先使用 JF.png，缺失时回退到 JF_Top.png
    }

# 定义创建微信草稿的函数
def create_draft(access_token: str, content_json: Dict) -> Dict:
    """创建微信公众号草稿

    Args:
        access_token (str): 微信 access_token
        content_json (Dict): 草稿内容字典

    Returns:
        Dict: 微信 API 响应结果
    """
    url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={access_token}"
    headers = {"Content-Type": "application/json"}
    wx_data = {
        "articles": [{
            "title": content_json["title"],
            "author": content_json["author"],
            "content": content_json["content"],
            "thumb_media_id": content_json["thumb_media_id"],
            "digest": content_json["digest"],
            "content_source_url": ""
        }]
    }
    try:
        response = requests.post(url, data=json.dumps(wx_data, ensure_ascii=False).encode('utf-8'), headers=headers, timeout=10)
        result = response.json()
        if "errcode" not in result:
            logging.info(f"草稿创建成功，媒体ID: {result.get('media_id')}")
        else:
            logging.error(f"草稿创建失败: {result.get('errmsg', '未知错误')}")
        return result
    except Exception as e:
        logging.error(f"创建草稿失败: {str(e)}")
        print(f"创建草稿失败: {str(e)}")
        return {"error": str(e)}

# 定义微信草稿创建主流程函数
def wechat_draft_creator(appid: str, appsecret: str, periodical: str, volume_path: str,
                         material_file: str, title: str, material_type: str = 'image') -> Dict:
    """
    微信草稿创建主流程函数

    Args:
        appid (str): 微信公众号 appid
        appsecret (str): 微信公众号 appsecret
        periodical (str): 期刊名称（如 'JF'）
        volume_path (str): 期刊内容目录路径
        material_file (str): 素材记录文件路径
        title (str): 草稿标题
        material_type (str): 素材类型，默认 'image'

    Returns:
        Dict: 微信 API 响应结果（包含 media_id 或错误信息）
    """
    import sys

    try:
        token = get_access_token(appid, appsecret)
        if not token:
            logging.error("获取Token失败，程序退出")
            print("获取Token失败，程序退出")
            return {"error": "获取Token失败"}

        manager = WeChatMaterialManager(token)

        articles = parse_volume(volume_path, token)
        if not articles:
            logging.error("未找到有效论文数据，程序退出")
            print("未找到有效论文数据，程序退出")
            return {"error": "无有效论文数据"}

        content_data = generate_content(
            articles=articles,
            title=title,
            periodical=periodical,
            material_file=material_file,
            access_token=token
        )

        result = create_draft(token, content_data)
        if "errcode" not in result:
            print(f"草稿创建成功！媒体ID: {result.get('media_id')}")
        else:
            print(f"草稿创建失败: {result.get('errmsg', '未知错误')}")

        manager.clean_expired_materials()
        return result

    except Exception as e:
        logging.error(f"运行出错: {str(e)}")
        print(f"运行出错: {str(e)}", file=sys.stderr)
        return {"error": str(e)}

# 使用示例
if __name__ == "__main__":
    config = {
        "appid": "wxd032abb0d3611a05",
        "appsecret": "fe3c450952beb3f4b114c1bff7d9899c",
        "periodical": "JF",
        "volume_path": r"../Periodicals_AI_Refined/JF/Volume 80 Issue 1",
        "material_file": r'wechat_materials.json',
        "title": r'【JF 80-1】西财人的专属学术外挂！每天1 分钟，AI 帮你读完三大顶刊！'
    }

    response = wechat_draft_creator(**config)
    print("最终响应:", response)
