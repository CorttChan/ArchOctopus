"""
谷德设计网
url: https://www.gooood.cn/
"""

# name: gooood.py
# version: 0.0.2
# date: 2022/2/21 19:38
# desc:

import re
from plugins import BaseParser


API_URL = "https://dashboard.gooood.cn/api/wp/v2/{}"


class Parser(BaseParser):
    def __init__(self, *args, **kwargs):
        BaseParser.__init__(self, *args, **kwargs)

        self.friend_name = "谷德设计网"

    def parse_filter(self):
        filter_pat = re.compile("/type/(?P<type>.*?)/country/(?P<country>.*?)/"
                                "material/(?P<material>.*?)/office/(?P<office>.*?)(/page/(?P<page>\\d+))?/?$")
        result = filter_pat.search(self.url)
        filter_dict = result.groupdict()

        posts_params = {"page": filter_dict["page"] or "1"}

        for k, v in filter_dict.items():
            if k != "page" and v != "all":
                url = API_URL.format(k)
                params = {"slug": v}
                response = self.request("GET", url, params=params)
                response_json = response.json()
                _id = response_json[0]["id"]
                posts_params[k] = _id

        page = 0
        url = API_URL.format("posts")
        while True:
            # 退出条件
            page += 1
            if page > 1:
                break

            posts_params.update({"page": page, "per_page": 20})
            response = self.request("GET", url, params=posts_params)
            response_json = response.json()
            for post in response_json:
                title = post["title"]["rendered"]
                index_start_flag = True  # 图片序号重置信号
                for image in post["gallery"]:
                    item_data = {
                        "sub_dir": self.cleanup(title),
                        "item_url": image["full_url"],
                        "item_index_reset": index_start_flag,
                    }
                    yield item_data
                    if index_start_flag:
                        index_start_flag = False

    def parse_by_slug(self):
        slug_pat = re.compile("/(?P<slug>[a-z0-9-]+?)\\.htm")
        result = slug_pat.search(self.url)
        params = result.groupdict()
        url = API_URL.format("posts/byslug")
        response = self.request("GET", url, params=params)
        response_json = response.json()

        index_start_flag = True  # 图片序号重置信号
        for image in response_json["gallery"]:
            item_data = {
                "item_url": image["full_url"],
                "item_index_reset": index_start_flag,
            }
            yield item_data
            if index_start_flag:
                index_start_flag = False

    def parse_type(self):
        slug_match = re.search("/type/(.*?)/?$", self.url)
        slug = slug_match.group(1)
        url = "https://dashboard.gooood.cn/api/wp/v2/type"
        params = {"slug": slug}
        response = self.request("GET", url, params=params)
        response_json = response.json()
        type_id = response_json[0]["id"]

        url = "https://dashboard.gooood.cn/api/wp/v2/posts"
        page = 0
        while True:
            # 退出条件
            page += 1
            if page > 1:
                break

            params = {"type": type_id, "page": page, "per_page": 18}
            response = self.request("GET", url, params=params)
            response_json = response.json()
            for post in response_json:
                title = post["title"]["rendered"]
                index_start_flag = True  # 图片序号重置信号
                for image in post["gallery"]:
                    item_data = {
                        "sub_dir": self.cleanup(title),
                        "item_url": image["full_url"],
                        "item_index_reset": index_start_flag,
                    }
                    yield item_data
                    if index_start_flag:
                        index_start_flag = False

    def parse_index(self):
        index_pat = re.compile("(?:/page/(\\d+))?/?$")
        result = index_pat.match(self.url_parser.get_path())

        page = int(result.group(1)) if result.group(1) else 1
        url = API_URL.format("fetch-posts")
        params = {"page": page, "per_page": 18, "post_type[0]": "post"}
        response = self.request("GET", url, params=params)
        response_json = response.json()
        for post in response_json:
            title = post["title"]["rendered"]
            index_start_flag = True  # 图片序号重置信号
            for image in post["gallery"]:
                item_data = {
                    "sub_dir": self.cleanup(title),
                    "item_url": image["full_url"],
                    "item_index_reset": index_start_flag,
                }
                yield item_data
                if index_start_flag:
                    index_start_flag = False

    def parse_category(self):
        # https://www.gooood.cn/category/series/material-and-detail
        # https://www.gooood.cn/category/series
        # https://www.gooood.cn/category/series/page/2
        # https://www.gooood.cn/category/type
        # https://www.gooood.cn/category/type/page/2
        # https://www.gooood.cn/category/type/architecture
        # https://www.gooood.cn/category/type/architecture/2
        series_pat = re.compile("/category/(series|type)(?:/([a-z0-9-]+))?(?:(?:/page/|/)(\\d+))?/?$")
        result = series_pat.search(self.url)

        slug = result.group(2) or result.group(1)
        page = int(result.group(3)) if result.group(3) else 1
        url = API_URL.format("categories")
        params = {"slug": slug}
        response = self.request("GET", url, params=params)
        response_json = response.json()
        _id = response_json[0]["id"]
        _parent_id = response_json[0]["parent"]

        if not _parent_id:
            params = {"parent": _id, "per_page": 100}
            response = self.request("GET", url, params=params)
            response_json = response.json()
            all_id = [str(_id), ]
            for _child in response_json:
                _child_id = _child["id"]
                all_id.append(str(_child_id))
            _id = ",".join(all_id)

        url = API_URL.format("posts")
        params = {"categories": _id, "page": page, "per_page": 18}
        response = self.request("GET", url, params=params)
        response_json = response.json()
        for post in response_json:
            title = post["title"]["rendered"]
            index_start_flag = True  # 图片序号重置信号
            for image in post["gallery"]:
                item_data = {
                    "sub_dir": self.cleanup(title),
                    "item_url": image["full_url"],
                    "item_index_reset": index_start_flag,
                }
                yield item_data
                if index_start_flag:
                    index_start_flag = False

    def route(self, *args, **kwargs):
        url_path = self.url_parser.get_path()

        # https://www.gooood.cn/
        if re.match("(?:/page/\\d+?)?/?$", url_path):
            return self.call_parse(self.parse_index)

        # https://www.gooood.cn/teviot-house-sao-paulo-by-casa100-architecture.htm
        # https://www.gooood.cn/cornell-tech-hotel-and-education-center-by-snohetta.htm
        elif re.match("/[a-z0-9-]+?\\.htm$", url_path):
            return self.call_parse(self.parse_by_slug)

        # https://www.gooood.cn/filter/type/all/country/all/material/all/office/all
        # https://www.gooood.cn/filter/type/kindergarten/country/all/material/all/office/all/page/2
        elif re.match("/filter/", url_path):
            return self.call_parse(self.parse_filter)

        # https://www.gooood.cn/type/kindergarten
        elif re.match("/type/\\w+?/?$", url_path):
            return self.call_parse(self.parse_type)

        # https://www.gooood.cn/category/series
        # https://www.gooood.cn/category/series/material-and-detail
        # https://www.gooood.cn/category/type
        # https://www.gooood.cn/category/type/landscape
        elif re.match("/category/(series|type)", url_path):
            return self.call_parse(self.parse_category)
