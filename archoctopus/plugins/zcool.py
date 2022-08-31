"""
站酷(ZCOOL)
url: https://www.zcool.com.cn/
"""

# name: zcool.py
# version: 0.0.2
# date: 2022/08/31 21:50
# desc:

import re
import json
from bs4 import BeautifulSoup

from archoctopus.plugins import BaseParser


API_URL = "https://www.zcool.com.cn/work/content/show"


# TODO  用户子域名解析
# https://guoguophoto.zcool.com.cn/
# https://janelee.zcool.com.cn/


class Parser(BaseParser):
    def __init__(self, *args, **kwargs):
        BaseParser.__init__(self, *args, **kwargs)

        self.friend_name = "站酷(ZCOOL)"

    def get_title(self, html):
        title = super(Parser, self).get_title(html)
        self.logger.debug("title: %s", title)
        title = re.sub(" - 原创作品 - 站酷 \\(ZCOOL\\)$| - 打开站酷，发现更好的设计！$|_原创作品-站酷ZCOOL", "", title)
        return title

    def api_parse(self, parse_id, title):
        params = {"objectId": parse_id}
        response = self.request("GET", API_URL, params=params)
        response_json = response.json()

        index_start_flag = True  # 图片序号重置信号
        for image in response_json["data"]["allImageList"]:
            item_data = {
                "sub_dir": title,
                "item_url": image["url"],
                "item_index_reset": index_start_flag,
                "size": (image["width"], image["height"])
            }
            yield item_data
            if index_start_flag:
                index_start_flag = False

    def parse_home(self, response):
        html = response.text
        html_bs = BeautifulSoup(html, 'lxml')
        articles = html_bs.find_all("div", class_="card-box")

        for article in articles:
            obj_type = article.get("data-obj-type")
            if obj_type == "3":         # type -> work
                article_id = article.get("data-obj-id")
                article_title = article.get("data-title")
                yield from self.api_parse(parse_id=article_id, title=self.cleanup(article_title))
            elif obj_type == "17":      # type -> activity
                pass

    def parse_article(self, response, title=""):
        html = response.text
        html_bs = BeautifulSoup(html, 'lxml')
        pws_data = html_bs.find("script", id="__NEXT_DATA__")
        pws_data_json = json.loads(pws_data.get_text())

        pat = re.compile("([^?]*)")

        index_start_flag = True  # 图片序号重置信号
        for image in pws_data_json["props"]["pageProps"]["data"]["productImages"]:
            item_data = {
                "sub_dir": title,
                "item_url": pat.match(image["url"]).group(1),
                "item_index_reset": index_start_flag,
                "size": (image["width"], image["height"])
            }
            self.logger.debug(item_data["item_url"])
            yield item_data
            if index_start_flag:
                index_start_flag = False

    def parse_discover(self, response):
        pass

    def parse_focus(self, response):
        pass

    def route(self, *args, **kwargs):
        response = kwargs.get("response")
        url_path = self.url_parser.get_path()

        # https://www.zcool.com.cn/
        # https://www.zcool.com.cn/home
        # https://www.zcool.com.cn/home?p=2#tab_anchor
        if re.match("(?:/home)?/?$", url_path):
            return self.call_parse(self.parse_home, response)

        # https://www.zcool.com.cn/work/ZNTczMTc0MDA=.html
        elif re.match("/work/\\w+?=\\.html$", url_path):
            return self.call_parse(self.parse_article, response)

        # https://www.zcool.com.cn/discover
        elif re.match("/discover", url_path):
            return self.call_parse(self.parse_discover, response)

        # https://www.zcool.com.cn/focus
        elif re.match("/focus", url_path):
            return self.call_parse(self.parse_focus, response)
