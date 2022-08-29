"""
Vogue
url: https://www.vogue.com/fashion-shows
"""

# name: vogue.py
# version: 0.0.1
# author  : CorttChan
# date: 2022/2/21 18:39
# desc:

import re
import os
import json
from bs4 import BeautifulSoup

from plugins import BaseParser


class Parser(BaseParser):
    def __init__(self, *args, **kwargs):
        BaseParser.__init__(self, *args, **kwargs)

        self.friend_name = "Vogue"

    def get_title(self, html):
        title = super(Parser, self).get_title(html)
        for s1, s2 in ((" | Vogue", ""),):
            title = re.sub(s1, s2, title)
        return title.strip()

    def parse_show(self, response):
        html = response.text
        html_bs = BeautifulSoup(html, 'lxml')

        data_scripts = html_bs.find_all("script")
        for data in data_scripts:
            result = re.match("window.__PRELOADED_STATE__ = (.*);", data.get_text())
            if result:
                data_json = json.loads(result.group(1))
                break
        else:
            return

        data_galleries = data_json["transformed"]["runwayShowGalleries"]["galleries"]
        for gallery in data_galleries:
            if gallery["title"] == "Collection":
                for picture in gallery["items"]:
                    img_url = picture["image"]["sources"]["xxl"]["url"]
                    img_width = picture["image"]["sources"]["xxl"]["width"]
                    img_height = picture["image"]["sources"]["xxl"]["height"]
                    name_match = re.match("(\\d+)-", os.path.basename(img_url))
                    item_name = name_match.group(1) if name_match else None

                    item_data = {
                        "item_url": img_url,
                        "name": item_name,
                        "size": (img_width, img_height)
                    }
                    yield item_data

    def route(self, *args, **kwargs):
        response = kwargs.get("response")
        url_path = self.url_parser.get_path()

        # https://www.vogue.com/fashion-shows/fall-2022-ready-to-wear/nensi-dojaka
        if re.match("/fashion-shows/[^/]+/[^/]+/?$", url_path):
            return self.call_parse(self.parse_show, response)

        # https://www.vogue.com/fashion-shows/fall-2022-ready-to-wear/simone-rocha/slideshow/collection#1
        elif re.match("/fashion-shows/[^/]+/[^/]+/slideshow/collection/?$", url_path):
            self.url = re.match("(.*?)/slideshow", self.url).group(1)
            response = self.request("GET", self.url)
            return self.call_parse(self.parse_show, response)

        else:
            return self.call_parse(self.abort, "当前版本仅提供解析秀场图册.\n其他需求请提交反馈")


if __name__ == '__main__':
    from plugins import UrlParser

    myurl = "https://www.vogue.com/fashion-shows/fall-2022-ready-to-wear/simone-rocha/slideshow/collection#1"
    myurl_parser = UrlParser(myurl)
    myurl_path = myurl_parser.get_path()

    print(myurl_path)

    print(re.match("/fashion-shows/[^/]+/[^/]+/slideshow/collection/?$", myurl_path).group())
