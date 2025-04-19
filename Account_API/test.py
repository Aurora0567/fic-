import os
import json
import re

import requests
from typing import List, Dict

from Account_API.upload_picture import WeChatMaterialManager

def get_access_token():
    """获取微信接口调用凭证"""
    url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={appid}&secret={appsecret}"
    try:
        response = requests.get(url, timeout=10)
        result = response.json()
        if 'access_token' in result:
            return result['access_token']
        else:
            raise Exception(f"获取Token失败: {result.get('errmsg', '未知错误')}")
    except Exception as e:
        print(f"Token请求异常: {str(e)}")
        return None


def upload_image(access_token: str, image_path: str) -> str:
    """上传封面图片并返回media_id"""
    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"
    with open(image_path, 'rb') as file:
        files = {'media': file}
        response = requests.post(url, files=files)
    result = response.json()
    if 'media_id' in result:
        return result['media_id']
    else:
        raise Exception(f"图片上传失败: {result.get('errmsg', '未知错误')}")


def parse_volume(volume_path: str) -> List[Dict]:
    """
    解析期刊目录结构，提取每个文章的information.json中的元数据。

    Args:
        volume_path (str): 期刊卷目录路径（如 "Periodicals_AI_Refined/JFE/Volume 163"）

    Returns:
        List[Dict]: 包含文章元数据的字典列表
    """
    articles = []

    # 确保路径存在
    if not os.path.isdir(volume_path):
        print(f"错误：路径 {volume_path} 不存在或不是文件夹")
        return articles

    # 遍历目录
    for root, dirs, files in os.walk(volume_path):
        # 跳过包含 "images" 的目录
        if "images" in root.split(os.sep):
            continue

        # 检查 information.json
        json_path = os.path.join(root, "information.json")
        if "information.json" in files:  # 更高效的检查
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    # 清洗 Highlights
                    highlights = data.get("Highlights", "")
                    if isinstance(highlights, str):
                        # 分割并移除“学术要点 X：”
                        highlights_list = [h.strip() for h in highlights.split("|||") if h.strip()]
                        # 移除“学术要点 X：”并规范化
                        cleaned_highlights = []
                        for hl in highlights_list:
                            # 使用正则移除“学术要点 X：”
                            hl_cleaned = re.sub(r'^学术要点\s*\d+：', '', hl).strip()
                            cleaned_highlights.append(hl_cleaned)
                        highlights = cleaned_highlights
                    else:
                        highlights = highlights if isinstance(highlights, list) else []

                    # 提取所需字段，使用默认值防止缺失
                    article = {
                        "AItitle": data.get("AItitle", ""),
                        "title": data.get("title", ""),
                        "link": data.get("link", ""),
                        "author": data.get("author", ""),
                        "AIkeys": data.get("AIkeys", []),
                        "AIsummary": data.get("AIsummary", ""),
                        "Highlights": highlights
                    }

                    # 可选：验证关键字段
                    if not article["title"]:
                        print(f"警告：{json_path} 中缺少 title 字段")
                        continue

                    articles.append(article)

            except json.JSONDecodeError as e:
                print(f"JSON解析失败 {json_path}: {str(e)}")
            except Exception as e:
                print(f"处理文件失败 {json_path}: {str(e)}")

    return articles


def generate_content(articles: List[Dict], title: str) -> Dict:
    """
    生成微信公众号草稿的 HTML 内容，确保作者和学术要点一条一行。

    Args:
        articles (List[Dict]): 文章元数据列表

    Returns:
        str: HTML 内容字符串
    """
    # 生成标题列表
    title_list = f'<h2 style="font-size: 20px; font-family: SimSun, serif; color: rgb(0, 63, 182);">本期看点</h2>\n<ul>'
    for idx, article in enumerate(articles, 1):
        title_list += f'<li style="font-size: 17px; color: rgb(98, 98, 98);">{article["title"]}</li>'
    title_list += "</ul>"

    content = title_list + f"\n<hr style=\"width: 50%; margin: 20px auto;\"/>\n"
    for idx, article in enumerate(articles, 1):
        # 处理作者：姓名和机构分开，每人一行
        authors_html = ""
        if article["author"]:
            authors_html = "".join(
                f'<p style="text-align: center; font-size: 16px; color: rgb(62, 62, 62)"><strong>{name.strip()}</strong></p>'
                f'<p style="margin-left: 10px; margin-bottom: 10px; text-align: center;">{institution}</p>'
                for name, institution in article["author"].items()
            )
        else:
            authors_html = '<p>未知作者</p>'

        # 处理学术要点：每条一行
        highlights_html = ""
        for hl in article["Highlights"]:
            # 提取直到第一个右括号的内容
            match = re.match(r'^(.*?）)\s*(.*)$', hl)
            if match:
                bold_content = match.group(1).strip()  # 第一个右括号及之前的内容
                description = match.group(2).strip() if match.group(2) else ''  # 剩余描述
                highlights_html += f'<p style="margin-bottom: 8px; font-size: 14px; font-family: SimSun, serif; color: rgb(98, 98, 98);"><span style="display: inline;"><strong style="display: inline;">{bold_content}</strong> {description}</span></p>'
            else:
                # 如果没有右括号，直接显示
                highlights_html += f'<p style="margin-bottom: 8px; font-size: 14px; font-family: SimSun, serif; color: rgb(98, 98, 98);">{hl}</p>'

        # 生成 HTML
        content += f"""
            <p style="text-align: center; font-size: 36px; font-weight: bold; color: rgb(0, 63, 182);">{idx:02d}</p>
            <p style="text-align: center; font-size: 20px; font-weight: bold; color: rgb(0, 63, 182);">{article['AItitle']}</p>
            <p style="text-align: center; font-size: 20px; font-weight: bold; color: rgb(0, 63, 182);">{article['title']}</p>
            <p style="text-align: center; font-size: 12px; color: blue; font-style: italic;">原文链接：<a href="{article['link']}">{article['link']}</a></p>
            <p style="text-align: center; font-size: 16px; font-weight: bold; color: rgb(30, 30, 30);">1、作者</p>
            {authors_html}
            <p style="text-align: center; font-size: 16px; font-weight: bold; color: rgb(30, 30, 30);">2、Keywords</p>
            <p style="text-align: center;">{'；'.join(article['AIkeys'])}</p>
            <p style="text-align: center; font-size: 16px; font-weight: bold; color: rgb(30, 30, 30);">3、AI精炼/Abstract</p>
            <p style="text-align: center; font-size: 16px; font-family: SimSun, serif; color: rgb(98, 98, 98);">{article['AIsummary']}</p>
            <p style="text-align: center; font-size: 16px; font-weight: bold; color: rgb(30, 30, 30);">4、学术要点</p>
            {highlights_html}
            <hr style="width: 50%; margin: 20px auto;"/>
        """

    return {
        "title": title,
        "author": "",
        "content": content,
        "digest": f"本期收录{len(articles)}篇前沿论文，涵盖...",  # 自定义摘要
        "thumb_media_id": ""  # 将在后续填充
    }


def create_draft(access_token: str, content_json: Dict):
    """创建微信草稿"""
    url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={access_token}"
    headers = {"Content-Type": "application/json"}
    wx_data = {
        "articles": [{
            "title": content_json["title"],
            "author": content_json["author"],
            "content": content_json["content"],
            "thumb_media_id": content_json["thumb_media_id"],
            "digest": content_json["digest"],
            "content_source_url": ""  # 可添加原文链接
        }]
    }
    response = requests.post(url, data=json.dumps(wx_data, ensure_ascii=False).encode('utf-8'), headers=headers)
    return response.json()


if __name__ == "__main__":

    # 配置参数
    appid = "wxd032abb0d3611a05"
    appsecret = "fe3c450952beb3f4b114c1bff7d9899c"
    volume_path = r"../Periodicals_AI_Refined/MS/Volume 71, Issue 3"  # 请修改为实际路径

    cover_name = r'../Material/MS.jpg'
    title = r'【MS 71-3 第一期】西财人的专属学术外挂！每天1 分钟，AI 帮你读完三大顶刊！'
    material_type = 'image'

    # 获取访问凭证
    token = get_access_token()
    if not token:
        exit("获取Token失败")

    try:
        # 初始化
        manager = WeChatMaterialManager(token)

        # 封面图片，没有就上传，有就直接用文件名
        media_id = manager.upload_material(
            file_path=cover_name,
            material_type=material_type
        )
        if not media_id:
            print(f"没找到 media_id")

        # 清理过期素材
        manager.clean_expired_materials()

        # 解析期刊内容
        print(volume_path)
        articles = parse_volume(volume_path)
        if not articles:
            print(articles)
            exit("未找到有效论文数据")
        # print(articles)

        # 生成内容
        content_data = generate_content(articles, title)
        content_data["thumb_media_id"] = media_id

        # 创建草稿
        result = create_draft(token, content_data)
        if "errcode" not in result:
            print("草稿创建成功！")
            print(f"草稿ID: {result.get('media_id')}")
        else:
            print("草稿创建失败:", result)

    except Exception as e:
        print("运行出错:", str(e))