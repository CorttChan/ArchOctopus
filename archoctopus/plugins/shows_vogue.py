"""
Vogue
url: http://shows.vogue.com.cn
"""

# name: shows_vogue.py
# version: 0.0.1
# author  : CorttChan
# date: 2022/2/21 15:23
# desc:

import re
import os
from bs4 import BeautifulSoup

from plugins import BaseParser


class Parser(BaseParser):
    def __init__(self, *args, **kwargs):
        BaseParser.__init__(self, *args, **kwargs)

        self.friend_name = "VOGUE时尚网"

    @ staticmethod
    def _url_extractor(tag):
        url = tag.get("src")
        full_url = re.match("(.*?)\\.\\d+X\\d+\\.(jpg|jpeg|png|gif|webp)", url)
        return full_url.group(1)

    def get_title(self, html):
        title = super(Parser, self).get_title(html)
        for s1, s2 in (("【多图】", ""), ("_VOGUE时尚网", ""), ("_T台展示", ""), ("图片\\d+", "")):
            title = re.sub(s1, s2, title)
        return title

    def parse_show(self, response):
        html = response.text
        html_bs = BeautifulSoup(html, 'lxml')

        data_gallery = html_bs.find("div", class_="content")
        all_imgs = data_gallery.find_all("img")

        for img in all_imgs:
            item_url = self._url_extractor(img)
            name_match = re.match("(\\d+)-", os.path.basename(item_url))
            item_name = name_match.group(1) if name_match else None

            item_data = {
                "item_url": item_url,
                "name": item_name
            }
            yield item_data

        page = 1
        while True:
            page += 1
            url = self.url + "page-{}.html".format(page)
            response = self.request("GET", url)

            html = response.text
            html_bs = BeautifulSoup(html, 'lxml')

            data_gallery = html_bs.find("div", class_="content")
            all_imgs = data_gallery.find_all("img")

            if not all_imgs:
                break

            for img in all_imgs:
                item_url = self._url_extractor(img)
                name_match = re.match("(\\d+)-", os.path.basename(item_url))
                item_name = name_match.group(1) if name_match else None

                item_data = {
                    "item_url": item_url,
                    "name": item_name
                }
                yield item_data

    def route(self, *args, **kwargs):
        url_path = self.url_parser.get_path()

        # http://shows.vogue.com.cn/Adam-Lippes/2022-ss-RTW/
        if re.match("/[^/]+/[^/]+/?$", url_path):
            self.url = re.subn("(/?)$", "/runway/", self.url, 1)[0]
            response = self.request("GET", self.url)
            return self.call_parse(self.parse_show, response)

        # http://shows.vogue.com.cn/2022-ss-RTW/Altuzarra/runway/page-2.html
        # http://shows.vogue.com.cn/2022-ss-RTW/Altuzarra/runway/
        elif re.match("/[^/]+/[^/]+/runway(/page-\\d+\\.html)?/?$", url_path):
            self.url = re.sub("page-\\d\\.html", "", self.url)
            response = self.request("GET", self.url)
            return self.call_parse(self.parse_show, response)

        # http://shows.vogue.com.cn/Sandro/2021-aw-RTW/runway/photo-778065.html
        elif re.match("/[^/]+/[^/]+/runway/photo-\\d+\\.html", url_path):
            self.url = re.sub("photo-\\d+\\.html", "", self.url)
            response = self.request("GET", self.url)
            return self.call_parse(self.parse_show, response)

        else:
            return self.call_parse(self.abort, "当前版本仅提供解析秀场图册.\n其他需求请提交反馈")


if __name__ == '__main__':
    from plugins import UrlParser

    myurl = "http://shows.vogue.com.cn/2022-ss-RTW/Altuzarra/runway/page-2.html"
    myurl_parser = UrlParser(myurl)
    myurl_path = myurl_parser.get_path()

    print(myurl_path)

    print(re.match("/[^/]+/[^/]+/runway(/page-\\d+\\.html)?/?$", myurl_path).group())
