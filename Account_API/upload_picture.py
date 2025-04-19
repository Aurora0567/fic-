"""
微信公众平台素材管理系统（JSON版）
功能：上传素材、避免重复、本地JSON记录、自动清理
"""

import os
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import requests



# JSON文件配置
MATERIAL_JSON = "wechat_materials.json"
DEFAULT_DATA = {"materials": []}


class WeChatMaterialManager:
    def __init__(self, access_token: str):
        """
        初始化素材管理器
        :param access_token: 微信接口调用凭证
        """
        self.access_token = access_token
        self._init_json_file()

    def _init_json_file(self):
        """初始化JSON文件（如果不存在则创建）"""
        if not os.path.exists(MATERIAL_JSON):
            with open(MATERIAL_JSON, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_DATA, f, ensure_ascii=False, indent=2)

    def _load_materials(self) -> List[Dict]:
        """加载所有素材记录"""
        try:
            with open(MATERIAL_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)["materials"]
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_materials(self, materials: List[Dict]):
        """保存素材记录到JSON文件"""
        with open(MATERIAL_JSON, 'w', encoding='utf-8') as f:
            json.dump({"materials": materials}, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _calculate_file_md5(file_path: str) -> str:
        """
        计算文件的MD5哈希值(用于文件内容去重)
        :param file_path: 文件路径
        :return: 16进制MD5字符串
        """
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def _find_existing_media(self, file_md5: str, is_permanent: bool) -> Optional[str]:
        """
        检查是否已存在相同文件的上传记录
        :return: 已存在的media_id 或 None
        """
        materials = self._load_materials()
        for item in materials:
            if item["file_md5"] == file_md5 and item["is_permanent"] == is_permanent:
                return item["media_id"]
        return None

    def _add_material_record(self, new_item: Dict):
        """添加新记录到JSON文件"""
        materials = self._load_materials()
        materials.append(new_item)
        self._save_materials(materials)

    def upload_material(self, file_path: str, material_type: str = 'image',
                        is_permanent: bool = True, title: str = None,
                        introduction: str = None) -> Optional[str]:
        """
        上传素材到微信平台(带重复检查)
        :param file_path: 本地文件路径
        :param material_type: 素材类型(image/voice/video/thumb)
        :param is_permanent: 是否为永久素材
        :param title: 视频素材标题(仅video类型需要)
        :param introduction: 视频素材描述(仅video类型需要)
        :return: media_id 或 None
        """
        # 参数校验
        if not os.path.exists(file_path):
            print(f"文件不存在：{file_path}")
            return None

        # 计算文件指纹
        file_md5 = self._calculate_file_md5(file_path)

        # 检查是否已上传
        existing_media_id = self._find_existing_media(file_md5, is_permanent)
        if existing_media_id:
            print(f"文件已存在，直接使用现有media_id: {existing_media_id}")
            return existing_media_id

        # 调用微信上传接口
        url = f"https://api.weixin.qq.com/cgi-bin/{'material' if is_permanent else 'media'}/add_material"
        params = {
            'access_token': self.access_token,
            'type': material_type
        }

        try:
            with open(file_path, 'rb') as file:
                files = {'media': file}
                # 视频素材需要额外参数
                if material_type == 'video' and is_permanent:
                    description = {
                        'title': title,
                        'introduction': introduction
                    }
                    response = requests.post(
                        url,
                        params=params,
                        files=files,
                        data={'description': json.dumps(description)}
                    )
                else:
                    response = requests.post(url, params=params, files=files)

                response.raise_for_status()
                result = response.json()

                if 'media_id' in result:
                    # 构建记录信息
                    new_record = {
                        "file_name": os.path.basename(file_path),
                        "file_md5": file_md5,
                        "media_id": result['media_id'],
                        "media_type": material_type,
                        "upload_time": datetime.now().isoformat(),
                        "expires_time": (datetime.now() + timedelta(days=3)).isoformat() if not is_permanent else None,
                        "is_permanent": is_permanent
                    }

                    # 保存记录
                    self._add_material_record(new_record)
                    return result['media_id']
                else:
                    print(f"上传失败: {result.get('errmsg', '未知错误')}")
                    return None

        except Exception as e:
            print(f"上传过程中发生异常: {str(e)}")
            return None

    def clean_expired_materials(self):
        """清理过期临时素材"""
        now = datetime.now()
        materials = self._load_materials()
        valid_materials = []
        expired_count = 0

        for item in materials:
            # 永久素材直接保留
            if item["is_permanent"]:
                valid_materials.append(item)
                continue

            # 检查临时素材是否过期
            expires_time = datetime.fromisoformat(item["expires_time"])
            if expires_time > now:
                valid_materials.append(item)
            else:
                try:
                    # 调用微信删除接口
                    url = f"https://api.weixin.qq.com/cgi-bin/material/del_material?access_token={self.access_token}"
                    response = requests.post(url, json={'media_id': item["media_id"]})
                    response.raise_for_status()
                    expired_count += 1
                except Exception as e:
                    print(f"删除素材 {item['media_id']} 失败: {str(e)}")
                    # 删除失败则保留记录
                    valid_materials.append(item)

        # 保存有效记录
        self._save_materials(valid_materials)
        print(f"已清理 {expired_count} 个过期素材")


# 单独上传素材时将以下代码解开注释

# from Account_API.test import get_access_token
#
# # 使用示例
# if __name__ == "__main__":
#     # 初始化
#     token = get_access_token()  # 替换为实际token
#     manager = WeChatMaterialManager(token)
#
#     # 示例：上传永久图片素材
#     media_id = manager.upload_material(
#         file_path=r"../Material/page_00_image_01.jpg",
#         material_type='image',
#         is_permanent=True
#     )
#     if media_id:
#         print(f"上传成功，media_id: {media_id}")
#
#     # 示例：清理过期素材
#     manager.clean_expired_materials()