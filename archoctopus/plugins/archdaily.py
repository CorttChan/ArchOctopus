"""
ArchDaily解析类
url: https://www.archdaily.com
"""

# name: archdaily.py
# version: 0.0.1
# date: 2022/2/9 21:16
# desc:

import os.path
import re
from bs4 import BeautifulSoup

from archoctopus.plugins import BaseParser


class Parser(BaseParser):
    def __init__(self, *args, **kwargs):
        super(Parser, self).__init__(*args, **kwargs)

        self.friend_name = "ArchDaily"

    def get_title(self, html):
        title = super(Parser, self).get_title(html)
        title = re.sub("( _ ArchDaily| \\| ArchDaily)$", "", title)
        return title

    @staticmethod
    def url_replace(url):
        return re.sub(r'thumb_jpg|newsletter|medium_jpg', 'large_jpg', url)

    @staticmethod
    def tag_map(tag):
        if tag.name == 'a':
            tag = tag.img
        return tag['data-src'] if tag.has_attr('data-src') else tag['src']

    @staticmethod
    def filter_tags(tag):
        attr_classes = {'a': ('gallery-thumbs-link', 'thumbs__link', 'js-image-size__link', 'js-image-size'),
                        'img': ('b-lazy', 'nr-image', 'nr-picture')}
        if tag.name in attr_classes.keys():
            tag_class_attr = tag.get('class')
            return tag_class_attr and any(_i in tag_class_attr for _i in attr_classes[tag.name])

    def get_headers(self, token=""):
        headers = {
            'Referer': self.url,
            'X-Requested-With': 'XMLHttpRequest',
            "X-CSRF-Token": token,
        }
        return headers

    @staticmethod
    def get_token(response):
        html = response.text
        html_bs = BeautifulSoup(html, 'lxml')
        meta = html_bs.find("meta", attrs={"name": "csrf-token"})
        if meta:
            return meta["content"]

    @staticmethod
    def get_folder_id(response):
        html = response.text
        html_bs = BeautifulSoup(html, 'lxml')
        folder_selected = html_bs.find("option", attrs={"selected": "selected"})
        if folder_selected:
            folder_id = folder_selected["value"]
            return folder_id

    def parse_gallery(self, response, title=""):
        """解析画廊页面"""
        html = response.text
        pat = "<meta property=\"og:image\" content=\"(.*?)\""
        single_pic = re.search(pat, html).group(1)

        item_data = {
            "sub_dir": title,
            "item_url": self.url_replace(single_pic),
            "item_index_reset": True,
        }
        yield item_data

    def parse_article(self, response, title=""):
        """解析普通页面"""
        index_start_flag = True  # 图片序号重置信号

        html = response.text
        html_bs = BeautifulSoup(html, 'lxml')
        pic_gallery = html_bs.find_all(self.filter_tags)
        urls = map(self.tag_map, pic_gallery)

        for _url in urls:
            item_data = {
                "sub_dir": title,
                "item_url": self.url_replace(_url),
                "item_index_reset": index_start_flag,
            }
            yield item_data
            if index_start_flag:
                index_start_flag = False

    def parse_common(self, response):
        """首页"""
        html = response.text
        html_bs = BeautifulSoup(html, 'lxml')
        articles = html_bs.find_all("div", itemtype="http://schema.org/Article")

        if not articles:
            articles = html_bs.find_all("li", class_="afd-search-list__item")

        for _article in articles:
            _a = _article.find("a")
            _article_url = self.url_parser.get_join_url(href=_a["href"])
            _article_title = self.cleanup(_a.get_text())
            response = self.request("GET", _article_url)
            yield from self.parse_article(response, title=_article_title)

    def parse_folders(self, response):
        path = re.search("/@[^/]*?/folders/?$", self.url_parser.get_path()).group()
        api_url = self.url_parser.get_join_url(path)
        token = self.get_token(response)

        page = 0
        while True:
            page += 1
            params = {"page_info": True, "per_page": 14, "page": page}
            response = self.request("GET", api_url, headers=self.get_headers(token=token), params=params)
            response_json = response.json()

            page_json = response_json["data"]
            for folder in page_json:
                folder_name = folder["name"]
                for fav in folder["favs"]:
                    title = self.cleanup(fav["title"])
                    fav_sub_dir = os.path.join(folder_name, title)
                    fav_response = self.request("GET", fav["url"])
                    if fav["meta_type"] == "Photo":
                        yield from self.parse_gallery(fav_response, title=fav_sub_dir)
                    else:
                        yield from self.parse_article(fav_response, title=fav_sub_dir)
            # 退出条件
            is_last_page = response_json["pagination"]["last_page"]
            if is_last_page:
                break

    def parse_bookmarks(self, response):
        user_slug = re.search("@([^/]*)", self.url_parser.get_path()).group(1)
        api_url = self.url_parser.get_join_url("/api/v1/users/favs")
        token = self.get_token(response)
        folder_id = self.get_folder_id(response)

        page = 0
        while True:
            page += 1
            params = {"user_slug": user_slug, "folder_id": folder_id, "page": page}
            response = self.request("GET", api_url, headers=self.get_headers(token=token), params=params)
            response_json = response.json()

            page_json = response_json["bookmarks"]
            for bookmark in page_json:
                title = self.cleanup(bookmark["title"])
                fav_response = self.request("GET", bookmark["url"])
                if bookmark["meta_type"] == "Photo":
                    yield from self.parse_gallery(fav_response, title=title)
                else:
                    yield from self.parse_article(fav_response, title=title)
            # 退出条件
            next_page = response_json["pagination"]["next_page"]
            if not next_page:
                break

    def parse_search(self):
        path_match = re.match("/search/?((cl|us|mx|br|cn|co|pe|)/((all|projects|folders|articles|products)/?.*$))",
                              self.url_parser.get_path())
        if path_match.group(2):
            sub_path = path_match.group(1)
        else:
            sub_path = f"us/{path_match.group(3)}"
        api_url = self.url_parser.get_join_url(f"/search/api/v1/{sub_path}")

        q = self.url_parser.get_query_by_key("q")
        if q:
            search_title = f"Search-{path_match.group(4)}_{q}"
        else:
            search_title = f"Search-{path_match.group(4)}"

        page = 0
        while True:
            params = {"q": q, "page": page}
            response = self.request("GET", api_url, params=params)
            response_json = response.json()
            page_json = response_json["results"]
            for project in page_json:
                title = self.cleanup(project["title"])
                fav_sub_dir = os.path.join(search_title, title)
                project_response = self.request("GET", project["url"])
                yield from self.parse_article(project_response, title=fav_sub_dir)
            # 退出条件
            page += 1
            if page > 2 or not page_json:
                break

    def parse_tag(self, response):
        pass

    def route(self, *args, **kwargs):
        response = kwargs.get("response")
        url_path = self.url_parser.get_path()

        # https://www.archdaily.cn/cn
        if re.match("/?(cl|us|mx|br|cn|co|pe|)?/?$", url_path):
            self.task_name = "Home"
            return self.call_parse(self.parse_common, response)

        # https://my.archdaily.cn/cn/@xiao-yi-xiao-yi/folders/
        elif re.match("/(cl|us|mx|br|cn|co|pe)/@[^/]*?/folders/?$", url_path):
            return self.call_parse(self.parse_folders, response)

        # https://my.archdaily.cn/cn/@xiao-yi-xiao-yi/folders/zong-he-ti/
        elif re.match("/(cl|us|mx|br|cn|co|pe)/@[^/]*?/folders/[^/]*?/?$", url_path):
            return self.call_parse(self.parse_bookmarks, response)

        # https://my.archdaily.cn/cn/@cortt-dot-me/bookmarks
        elif re.match("/(cl|us|mx|br|cn|co|pe)/@[^/]*?/bookmarks/?$", url_path):
            return self.call_parse(self.parse_bookmarks, response)

        # https://my.archdaily.cn/cn/@xiao-yi-xiao-yi
        elif re.match("/(cl|us|mx|br|cn|co|pe)/@[^/]*?/?$", url_path):
            return self.call_parse(self.parse_bookmarks, response)

        # https://www.archdaily.cn/cn/973005/zhe-jiang-da-xue-jian-zhu-she-ji-yan-jiu-yuan-zi-jin-yuan-qu-zhe
        # -jiang-da-xue-jian-zhu-she-ji-yan-jiu-yuan
        elif re.match("/?(cl|us|mx|br|cn|co|pe|)/\\d+/[\\w-]+/?$", url_path):
            return self.call_parse(self.parse_article, response)

        # https://www.archdaily.cn/cn/973122/jst-ha-li-si-bao-sheng-chan-gong-cheng-zhong-xin-lu-ze-long-shi-
        # wu-suo-plus-arcari-plus-iovino-shi-wu-suo/61a79152cdec110164d79b34-jst-harrisburg-production-engine
        # ering-center-ryuichi-ashizawa-architects-and-associates-photo
        elif re.match("/?(cl|us|mx|br|cn|co|pe|)/\\d+(/[\\w-]+){2}/?$", url_path):
            return self.call_parse(self.parse_gallery, response)

        # https://www.archdaily.cn/search/cn/all?q=%E5%AD%A6%E6%A0%A1&ad_source=jv-header
        elif re.match("/search/?(cl|us|mx|br|cn|co|pe|)/all/?$", url_path):
            return self.call_parse(self.parse_search)

        # https://www.archdaily.cn/search/cn/projects?q=%E7%BB%BC%E5%90%88%E4%BD%93%20%E5%95%86%E4%B8%9A&ad_s
        # ource=search&ad_medium=projects_tab
        elif re.match("/search/?(cl|us|mx|br|cn|co|pe|)/projects/?$", url_path):
            return self.call_parse(self.parse_search)

        # https://www.archdaily.cn/search/cn/projects/categories/shang-ye-jian-zhu-yu-ban-gong-jian-zhu/count
        # ry/de-guo?q=%E7%BB%BC%E5%90%88%E4%BD%93%20%E5%95%86%E4%B8%9A&ad_medium=filters
        elif re.match("/search/?(cl|us|mx|br|cn|co|pe|)/projects/categories/", url_path):
            return self.call_parse(self.parse_search)

        elif re.match("/search/?(cl|us|mx|br|cn|co|pe|)/folders/?$", url_path):
            return self.call_parse(self.parse_search)

        elif re.match("/search/(cn|mx|br|)/folders/[^/]*?/?$", url_path):
            pass

        elif re.match("/search/?(cl|us|mx|br|cn|co|pe|)/products/?$", url_path):
            pass

        elif re.match("/search/(cn|mx|br|)/(xin-wen|architecture-news|noticias-de-arquitectura|)/?$", url_path):
            pass

        # https://www.archdaily.cn/cn/search/competitions/text/%E4%B8%8A%E6%B5%B7/year/2018
        elif re.match("/?(cl|us|mx|br|cn|co|pe|)/search/competitions/", url_path):
            return self.call_parse(self.parse_common, response)

        # https://www.archdaily.cn/cn/tag/aedasjian-zhu-shi-wu-suo?ad_source=search&ad_medium=search_result_all
        elif re.match("/?(cl|us|mx|br|cn|co|pe|)/tag/", url_path):
            return self.call_parse(self.parse_common, response)
