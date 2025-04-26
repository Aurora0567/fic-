# 导入必要的 Python 模块
import os  # 用于文件和目录操作
import json  # 用于处理 JSON 文件
import re  # 用于正则表达式处理
import requests  # 用于发送 HTTP 请求
import uuid  # 用于生成唯一文件名
import shutil  # 用于文件复制
from typing import List, Dict  # 用于类型注解

# 假设 WeChatMaterialManager 已定义在 Account_API.upload_picture 中
from Account_API.upload_picture import WeChatMaterialManager

# 定义获取微信 access_token 的函数
def get_access_token():
    """获取微信接口调用凭证（access_token）"""
    # 构造请求 URL，使用 appid 和 appsecret
    url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={appid}&secret={appsecret}"
    try:
        # 发送 GET 请求获取 token
        response = requests.get(url, timeout=10)
        # 解析响应 JSON
        result = response.json()
        # 检查是否成功获取 token
        if 'access_token' in result:
            return result['access_token']
        else:
            # 抛出异常，包含错误信息
            raise Exception(f"获取Token失败: {result.get('errmsg', '未知错误')}")
    except Exception as e:
        # 打印请求异常信息
        print(f"Token请求异常: {str(e)}")
        return None

# 定义上传图片到微信素材库的函数
def upload_image(access_token: str, image_path: str) -> Dict:
    """上传图片到微信素材库并返回 media_id 和 URL"""
    # 构造上传图片的 API URL
    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"
    try:
        # 打开图片文件以二进制模式读取
        with open(image_path, 'rb') as file:
            # 构造上传文件参数
            files = {'media': (os.path.basename(image_path), file)}
            # 发送 POST 请求上传图片
            response = requests.post(url, files=files)
        # 解析响应 JSON
        result = response.json()
        # 检查是否成功上传并返回 media_id 和 url
        if 'media_id' in result and 'url' in result:
            return {'media_id': result['media_id'], 'url': result['url']}
        else:
            # 抛出异常，包含错误信息
            raise Exception(f"图片上传失败: {result.get('errmsg', '未知错误')}")
    except Exception as e:
        # 打印上传失败信息
        print(f"上传图片 {image_path} 失败: {str(e)}")
        # 返回空结果
        return {'media_id': '', 'url': ''}

# 定义通过 media_id 获取素材 URL 的函数
def get_material_url(access_token: str, media_id: str) -> str:
    """通过 media_id 从微信获取素材的 URL"""
    # 构造获取素材的 API URL
    url = f"https://api.weixin.qq.com/cgi-bin/material/get_material?access_token={access_token}"
    try:
        # 发送 POST 请求，包含 media_id
        response = requests.post(url, json={"media_id": media_id})
        # 解析响应 JSON
        result = response.json()
        # 返回素材 URL（如果存在）
        return result.get("url", "")
    except Exception as e:
        # 打印获取 URL 失败信息
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
    # 初始化文章列表
    articles = []
    # 检查路径是否存在且为目录
    if not os.path.isdir(volume_path):
        print(f"错误：路径 {volume_path} 不存在或不是文件夹")
        return articles

    # 遍历目录结构
    for root, dirs, files in os.walk(volume_path):
        # 初始化第一张图片路径
        first_image = None
        # 检查是否有 images 文件夹
        if "images" in dirs:
            # 获取 images 文件夹路径
            images_path = os.path.join(root, "images")
            # 确认 images 文件夹存在
            if os.path.isdir(images_path):
                # 获取所有图片文件（支持 jpg、jpeg、png）
                image_files = [f for f in os.listdir(images_path) if f.lower().endswith(('jpg', 'jpeg', 'png'))]
                # 如果有图片文件，取第一张
                if image_files:
                    first_image = os.path.join(images_path, image_files[0])
        # 检查是否有 information.json 文件
        json_path = os.path.join(root, "information.json")
        if "information.json" in files:
            try:
                # 读取 information.json 文件
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 处理 Highlights 字段
                highlights = data.get("Highlights", "")
                if isinstance(highlights, str):
                    # 分割 Highlights 字符串并清理
                    highlights_list = [h.strip() for h in highlights.split("|||") if h.strip()]
                    cleaned_highlights = [re.sub(r'^学术要点\s*\d+：', '', hl).strip() for hl in highlights_list]
                    highlights = cleaned_highlights
                else:
                    # 如果 Highlights 已为列表，直接使用
                    highlights = highlights if isinstance(highlights, list) else []

                # 上传第一张图片（重命名为唯一名称）
                image_info = {'media_id': '', 'url': ''} if first_image else {'media_id': '', 'url': ''}
                renamed_image_path = None
                if first_image:
                    # 获取文件扩展名
                    file_ext = os.path.splitext(first_image)[1].lower()
                    # 生成唯一文件名
                    unique_name = f"{uuid.uuid4().hex}{file_ext}"
                    # 构造重命名后的文件路径
                    renamed_image_path = os.path.join(os.path.dirname(first_image), unique_name)
                    # 复制原始图片到新文件名
                    shutil.copy2(first_image, renamed_image_path)
                    # 上传重命名后的图片
                    image_info = upload_image(access_token, renamed_image_path)
                    # 删除临时重命名文件（可选，注释掉以便调试）
                    # os.remove(renamed_image_path)

                # 构造文章元数据字典
                article = {
                    "AItitle": data.get("AItitle", ""),  # AI 标题
                    "title": data.get("title", ""),  # 原文标题
                    "link": data.get("link", ""),  # 原文链接
                    "author": data.get("author", ""),  # 作者信息
                    "AIkeys": data.get("AIkeys", []),  # AI 关键词
                    "AIsummary": data.get("AIsummary", ""),  # AI 摘要
                    "Highlights": highlights,  # 学术要点
                    "AIfig": data.get("AIfig", []),  # AI 图片描述
                    "first_image": renamed_image_path if renamed_image_path else first_image,  # 重命名后的图片路径
                    "image_url": image_info['url']  # 微信素材 URL
                }

                # 检查标题是否为空
                if not article["title"]:
                    print(f"警告：{json_path} 中缺少 title 字段")
                    continue

                # 添加文章到列表
                articles.append(article)

            except json.JSONDecodeError as e:
                # 打印 JSON 解析错误
                print(f"JSON解析失败 {json_path}: {str(e)}")
            except Exception as e:
                # 打印其他处理错误
                print(f"处理文件失败 {json_path}: {str(e)}")

    # 返回文章列表
    return articles

# 定义生成微信草稿内容的函数
def generate_content(articles: List[Dict], title: str, periodical: str, material_file: str, access_token: str) -> Dict:
    """
    生成微信公众号草稿的 HTML 内容，在开头插入 JF_Top.png

    Args:
        articles (List[Dict]): 文章元数据列表
        title (str): 草稿标题
        periodical (str): 期刊名称（如 'JF'）
        material_file (str): wechat_materials.json 文件路径
        access_token (str): 微信 access_token

    Returns:
        Dict: 包含草稿内容的字典
    """
    # 初始化 media_id 和 url
    top_fig_media_id = ""
    top_fig_url = ""
    # 初始化 WeChatMaterialManager
    manager = WeChatMaterialManager(access_token)

    # 加载 wechat_materials.json
    try:
        # 打开并读取 JSON 文件
        with open(material_file, 'r', encoding='utf-8') as f:
            materials = json.load(f)
        # 检查 materials 键是否存在
        if 'materials' not in materials:
            raise KeyError("JSON 缺少 'materials' 键")
        # 查找 JF_Top.png 的记录
        for item in materials['materials']:
            if item.get('file_name') == f"{periodical}_Top.png":
                top_fig_media_id = item.get('media_id', '')
                top_fig_url = item.get('url', '')
                break
        # 如果 media_id 或 url 缺失，尝试补救
        if top_fig_media_id and not top_fig_url:
            # 通过 media_id 获取 url
            top_fig_url = get_material_url(access_token, top_fig_media_id)
            if top_fig_url:
                # 更新 wechat_materials.json
                for item in materials['materials']:
                    if item.get('file_name') == f"{periodical}_Top.png":
                        item['url'] = top_fig_url
                        break
                with open(material_file, 'w', encoding='utf-8') as f:
                    json.dump(materials, f, ensure_ascii=False, indent=4)
                print(f"已通过 media_id 获取 {periodical}_Top.png 的 url 并更新 {material_file}")
        # 如果仍然没有有效 media_id 或 url，尝试重新上传
        if not top_fig_media_id or not top_fig_url:
            print(f"警告：在 {material_file} 中未找到 {periodical}_Top.png 的有效 media_id 或 url")
            # 构造图片路径
            top_fig_path = f"../Material/{periodical}_Top.png"
            # 检查图片文件是否存在
            if os.path.exists(top_fig_path):
                # 上传图片
                image_info = upload_image(access_token, top_fig_path)
                top_fig_media_id = image_info['media_id']
                top_fig_url = image_info['url']
                # 如果上传成功，更新 wechat_materials.json
                if top_fig_media_id and top_fig_url:
                    materials['materials'].append({
                        "file_name": f"{periodical}_Top.png",
                        "file_md5": "",  # 可选：计算 MD5
                        "media_id": top_fig_media_id,
                        "media_type": "image",
                        "upload_time": "",  # 可选：添加当前时间
                        "expires_time": None,
                        "is_permanent": True,
                        "url": top_fig_url
                    })
                    with open(material_file, 'w', encoding='utf-8') as f:
                        json.dump(materials, f, ensure_ascii=False, indent=4)
                    print(f"已重新上传 {periodical}_Top.png 并更新 {material_file}")
                else:
                    print(f"上传 {top_fig_path} 失败")
            else:
                print(f"错误：{top_fig_path} 不存在，无法上传")
    except FileNotFoundError:
        # 打印文件不存在错误
        print(f"错误：{material_file} 文件不存在")
    except json.JSONDecodeError:
        # 打印 JSON 格式错误
        print(f"错误：{material_file} 不是有效的 JSON 文件")
    except KeyError as e:
        # 打印缺少键错误
        print(f"错误：{material_file} 格式错误，缺少 {e} 键")
    except Exception as e:
        # 打印其他读取错误
        print(f"读取 {material_file} 失败: {str(e)}")

    # 初始化 HTML 内容
    content = ""
    # 如果有有效的 url，插入图片
    if top_fig_url:
        content += f"""
            <p style="text-align: center;">
                <img src="{top_fig_url}" alt="Top Image" style="max-width: 100%; height: auto; display: block; margin: 0 auto;" />
            </p>
            <p></p>
        """
    else:
        # 如果没有图片，插入占位符
        content += f"""
            <p style="text-align: center; color: red;">未找到 {periodical}_Top.png 的有效图片</p>
            <p></p>
        """

    # 生成文章标题列表
    title_list = f'<h2 style="font-size: 20px; font-weight: bold; font-family: SimSun, serif; color: rgb(0, 63, 182);">本期看点</h2>\n<ul>'
    for idx, article in enumerate(articles, 1):
        # 添加每篇文章的标题（去除括号内容）
        title_list += f'<li style="font-size: 17px; color: rgb(98, 98, 98);">{re.sub(r"（.*?）", "", article["AItitle"]).strip()}</li>'
    title_list += "</ul>"

    # 将标题列表添加到内容
    content += title_list
    # 遍历每篇文章，生成详细内容
    for idx, article in enumerate(articles, 1):
        # 初始化作者 HTML
        authors_html = ""
        # 检查是否有作者信息
        if article["author"]:
            # 生成作者和机构信息
            authors_html = "".join(
                f'<p style="text-align: center; font-size: 16px; color: rgb(62, 62, 62)"><strong>{name.strip()}</strong></p>'
                f'<p style="margin-left: 10px; margin-bottom: 10px; text-align: center;">{institution}</p>'
                for name, institution in article["author"].items()
            )
        else:
            # 如果没有作者信息，显示默认文本
            authors_html = '<p>未知作者</p>'

        # 初始化学术要点 HTML
        highlights_html = ""
        # 遍历学术要点
        for hl in article["Highlights"]:
            # 使用正则表达式匹配要点格式
            match = re.match(r'^(.*?）)\s*(.*)$', hl)
            if match:
                # 提取加粗部分和描述
                bold_content = match.group(1).strip()
                description = match.group(2).strip() if match.group(2) else ''
                # 生成要点 HTML
                highlights_html += f'<p style="margin-bottom: 8px; font-size: 14px; font-family: SimSun, serif; color: rgb(98, 98, 98);"><span style="display: inline;"><strong style="display: inline;">{bold_content}</strong> {description}</span></p>'
            else:
                # 如果不匹配，直接生成普通文本
                highlights_html += f'<p style="margin-bottom: 8px; font-size: 14px; font-family: SimSun, serif; color: rgb(98, 98, 98);">{hl}</p>'

        # 生成文章内容 HTML
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

        # 如果文章有图片，插入图片
        if article["image_url"]:
            content += f"""
                <p style="text-align: center;">
                    <img src="{article['image_url']}" alt="First Image" style="max-width: 100%; height: auto; display: block; margin: 0 auto;" />
                </p>
            """
            # 如果有图片 AI 描述，添加描述
            if article["AIfig"]:
                AIfig = article["AIfig"][0]
                content += f"""
                    <p style="font-size: 16px; font-family: SimSun, serif; color: rgb(62, 62, 62);">图片AI描述：</p>
                    <p style="font-size: 16px; font-family: SimSun, serif; color: rgb(62, 62, 62);">{AIfig}</p>
                """
            content += "<p></p>"

        # 添加学术要点和分隔线
        content += f"""
            <p style="text-align: center; font-size: 16px; font-weight: bold; color: rgb(30, 30, 30);">4、学术要点</p>
            {highlights_html}
            <p></p>
            <hr style="width: 50%; margin: 20px auto;"/>
        """

    # 添加尾部声明和编辑信息
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

    # 返回草稿内容字典
    return {
        "title": title,  # 草稿标题
        "author": "",  # 作者（留空）
        "content": content,  # HTML 内容
        "digest": f"本期收录{len(articles)}篇前沿论文，涵盖...",  # 摘要
        "thumb_media_id": top_fig_media_id  # 使用 JF_Top.png 作为封面
    }

# 定义创建微信草稿的函数
def create_draft(access_token: str, content_json: Dict):
    """创建微信公众号草稿"""
    # 构造创建草稿的 API URL
    url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={access_token}"
    # 设置请求头
    headers = {"Content-Type": "application/json"}
    # 构造草稿数据
    wx_data = {
        "articles": [{
            "title": content_json["title"],  # 草稿标题
            "author": content_json["author"],  # 作者
            "content": content_json["content"],  # HTML 内容
            "thumb_media_id": content_json["thumb_media_id"],  # 封面 media_id
            "digest": content_json["digest"],  # 摘要
            "content_source_url": ""  # 原文链接（留空）
        }]
    }
    # 发送 POST 请求创建草稿
    response = requests.post(url, data=json.dumps(wx_data, ensure_ascii=False).encode('utf-8'), headers=headers)
    # 返回响应 JSON
    return response.json()

# 主程序入口
if __name__ == "__main__":
    # 配置参数
    appid = "wxd032abb0d3611a05"  # 微信公众号 appid
    appsecret = "fe3c450952beb3f4b114c1bff7d9899c"  # 微信公众号 appsecret
    periodical = 'JF'  # 期刊名称
    volume_path = r"../Periodicals_AI_Refined/JF/Volume 80 Issue 1"  # 期刊目录路径
    material_file = r'wechat_materials.json'  # wechat_materials.json 路径
    title = r'【JF 80-1】西财人的专属学术外挂！每天1 分钟，AI 帮你读完三大顶刊！'  # 草稿标题
    material_type = 'image'  # 素材类型

    # 获取微信 access_token
    token = get_access_token()
    # 检查是否成功获取 token
    if not token:
        print("获取Token失败，程序退出")
        exit()

    try:
        # 初始化 WeChatMaterialManager
        manager = WeChatMaterialManager(token)

        # 解析期刊内容并上传文章图片
        articles = parse_volume(volume_path, token)
        # 检查是否找到有效文章
        if not articles:
            print("未找到有效论文数据，程序退出")
            exit()

        # 生成草稿内容
        content_data = generate_content(articles, title, periodical, material_file, token)

        # 创建草稿
        result = create_draft(token, content_data)
        # 检查草稿创建是否成功
        if "errcode" not in result:
            print("草稿创建成功！")
            print(f"草稿ID: {result.get('media_id')}")
        else:
            print("草稿创建失败:", result)

        # 清理过期素材
        manager.clean_expired_materials()

    except Exception as e:
        # 打印运行时错误
        print("运行出错:", str(e))
