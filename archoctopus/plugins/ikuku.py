"""
Ikuku
url: http://www.ikuku.cn/
"""

# name: ikuku.py
# version: 0.0.1
# author: CorttChan
# date: 2022/2/22 11:31
# desc:

import re

from plugins import BaseParser


AJAX_API = "http://www.ikuku.cn/wp-admin/admin-ajax.php"


class Parser(BaseParser):
    def __init__(self, *args, **kwargs):
        BaseParser.__init__(self, *args, **kwargs)

        self.friend_name = "在库言库"

    def get_title(self, html):
        title = super(Parser, self).get_title(html)
        for s1, s2 in (("_ikuku.cn_在库言库", ""),):
            title = re.sub(s1, s2, title)
        return title.strip()

    def parse_article(self, html):
        result = re.search("postid=(\\d+)", html)
        if result:
            postid = result.group(1)
        else:
            return

        page = 0
        while True:
            page += 1
            params = {
                "action": "waterfall",
                "image_data": "pics",
                "p": page,
                "pagenum": 0,
                "t": None,
                "ID": postid,
                "personid": 0
            }

            resp = self.request("GET", AJAX_API, headers=self.get_json_headers(), params=params)
            data_json = resp.json()['result']

            if data_json:
                for img in data_json:
                    img_url = re.sub("-\\d+x\\d+", "", img["image"])
                    # img_name = str(img["id"])

                    item_data = {
                        "item_url": img_url,
                        # "name": img_name
                    }
                    yield item_data
            else:
                break

    def route(self, *args, **kwargs):
        html = kwargs.get("html")

        url_path = self.url_parser.get_path()

        # http://www.ikuku.cn/project/baisuigongyu
        # http://www.ikuku.cn/photography/qingdaohuanyushidaiyangbanjian
        # http://www.ikuku.cn/concept/shenzhenshidisanshisangaojizhongxuezhongbiaohouxuanfangan
        # http://www.ikuku.cn/photography/chengshigengxin-shanghaiguopinlengdongcangkugaijian
        if re.match("/(project|photography|concept)/[\\w-]+/?$", url_path):
            return self.call_parse(self.parse_article, html)

        else:
            return self.call_parse(self.abort, "当前版本仅提供解析文章功能.\n其他需求请提交反馈")
