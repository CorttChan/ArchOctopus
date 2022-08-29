"""
站酷(ZCOOL)
url: http://www.archcollege.com/
"""

# name: archcollege.py
# version: 0.0.1
# date: 2022/2/9 21:12
# desc:

import re
from bs4 import BeautifulSoup

from plugins import BaseParser


CATEGORY_API_URL = "http://www.archcollege.com/cat/{}/"


class Parser(BaseParser):
    def __init__(self, *args, **kwargs):
        BaseParser.__init__(self, *args, **kwargs)

        self.friend_name = "建筑学院archcollege"
        self.regexps = {
            'srcset_urls': re.compile("(\\S+)(\\s+([\\d.]+)[xw])?(\\s*(?:,|$))"),
        }

    def get_title(self, html):
        title = super(Parser, self).get_title(html)
        title = re.sub("( _ 建筑学院|——为建筑师而打造的高品质平台)$", "", title)
        return title

    def get_absolute_url(self, uri: str):
        uri = uri.split("?")[0]
        return self.url_parser.get_join_url(uri)

    def parse_article(self, response, title=""):
        """
        文章页面解析
        解析地址:
            1. http://www.archcollege.com/archcollege/2022/01/50433.html
        数据位置:
            <script type="application/json" id="beconfig-store_state">json_data</script>
        :param response:
        :param title:
        :return:
        """
        html = response.text
        html_bs = BeautifulSoup(html, 'lxml')
        images = html_bs.find("div", class_="atcl_extend").find_all("img")

        index_start_flag = True  # 图片序号重置信号
        for image in images:
            src = image.get("src")
            if src:
                uri = src
                url = self.get_absolute_url(uri)
                item_data = {
                    "sub_dir": self.cleanup(title),
                    "item_url": url,
                    "item_index_reset": index_start_flag,
                }
                yield item_data

    def parse_category(self):
        # http://www.archcollege.com/cat/experience
        # http://www.archcollege.com/cat/experience?cname=02cad
        # pat = re.compile("/cat/(?P<category>\\w+)?\\??(?P<cname>\\w+)?/?$")
        pat = re.compile("/cat/(\\w+)/?")
        category = pat.search(self.url).group(1)
        url = CATEGORY_API_URL.format(category)

        params = self.url_parser.get_query_dict()
        if "cname" not in params.keys():
            params["cname"] = category
        params.update({"t": "a"})

        load_max = 0
        while True:
            # 退出条件
            load_max += 1
            if load_max > self.loop_max:
                break

            params.update({"page": load_max})
            response = self.request("GET", url, headers=self.get_json_headers(), params=params)
            html = response.text
            html_bs = BeautifulSoup(html, 'lxml')
            items = html_bs.find_all("li", class_="cat-post-item")
            for item in items:
                item_url = item.a.get("href")
                item_title = item.a.get("title")
                response = self.request("GET", item_url)
                yield from self.parse_article(response, title=item_title)

    def parse_home(self, response):
        pass

    def route(self, *args, **kwargs):
        response = kwargs.get("response")
        url_path = self.url_parser.get_path()

        # http://www.archcollege.com/archcollege/2022/01/50433.html
        if re.match("/?$", url_path):
            return self.call_parse(self.parse_home, response)

        # http://www.archcollege.com/archcollege/2022/01/50433.html
        elif re.match("/archcollege/\\d{4}/\\d{2}/\\d+\\.html$", url_path):
            return self.call_parse(self.parse_article, response)

        # http://www.archcollege.com/cat/experience
        # http://www.archcollege.com/cat/experience?cname=02cad
        elif re.match("/cat/", url_path):
            return self.call_parse(self.parse_category)
