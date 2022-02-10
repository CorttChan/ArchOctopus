"""
花瓣解析类
url: https://www.huaban.com
"""

# name: huaban.py
# version: 0.0.1
# date: 2022/2/9 21:14
# desc:

import re
import json
from plugins import BaseParser, UrlParser

PIN_RECOMMEND = "https://huaban.com/pins/{_id}/recommendweb/"
PIN_RECOMMEND_V2 = "https://api.huaban.com/pins/{_id}/recommendweb/"
BOARD_URL = "https://huaban.com/boards/{_id}/"

# new version ui API
API_URL = "https://api.huaban.com"


def get_pin_url(pin):
    """合成图片url"""
    pin_key = pin['file']['key']
    pin_url = 'https://hbimg.huabanimg.com/{}'.format(pin_key)
    return pin_url


def get_page_json(html, contain):
    """获取页面指定部分的json数据"""
    pat = r'app.page\["{}"] = (.*);'.format(contain)
    result = re.search(pat, html).group(1)
    result = re.sub("(:)(?!null|false|true)([A-Za-z]\\w*?)([,}])",
                    lambda m: m.group(1) + "\"" + m.group(2) + "\"" + m.group(3),
                    result)
    page_json = json.loads(result)
    return page_json


class Parser(BaseParser):
    def __init__(self, *args, **kwargs):
        super(Parser, self).__init__(*args, **kwargs)

        self.friend_name = "花瓣网"

    def get_title(self, html):
        task_name = super(Parser, self).get_title(html)
        task_name = re.sub("收集_花瓣|_花瓣_采集|_花瓣网|_采集你喜欢的美好事物|的花瓣个人主页", "", task_name)
        return task_name

    def parse_board(self, response, **kwargs):
        """花瓣Board页面解析"""
        index_start_flag = True  # 图片序号重置信号

        board_url = kwargs.get("board_url", self.url)
        html = response.text
        page_json = get_page_json(html, contain="board")
        if page_json["pins"]:
            for pin in page_json['pins']:
                item_data = {
                    "sub_dir": kwargs.get("board_title", ""),
                    "name": pin["pin_id"],
                    "size": (pin["file"]["width"], pin["file"]["height"]),
                    "item_url": get_pin_url(pin),
                    "item_index_reset": index_start_flag,
                }
                yield item_data
                if index_start_flag:
                    index_start_flag = False
        else:
            return

        while True:
            last_item = page_json['pins'][-1]
            _max = last_item["pin_id"]
            params = {'max': _max, 'limit': 20, 'wfl': 1}
            response = self.request("GET", board_url, headers=self.get_json_headers(), params=params)
            page_json = response.json()['board']
            # 循环退出条件
            if page_json["pins"]:
                for pin in page_json['pins']:
                    item_data = {
                        "sub_dir": kwargs.get("board_title", ""),
                        "name": pin["pin_id"],
                        "size": (pin["file"]["width"], pin["file"]["height"]),
                        "item_url": get_pin_url(pin),
                        "item_index_reset": index_start_flag,
                    }
                    yield item_data
            else:
                break

    def parse_board_v2(self, **kwargs):
        """花瓣Board页面解析"""
        index_start_flag = True  # 图片序号重置信号

        board_url = kwargs.get("board_url", self.url)
        url_parser = UrlParser(board_url)
        url = API_URL + url_parser.get_path() + "/pins"
        _max = None

        while True:
            params = {"limit": 20, "max": _max}
            response = self.request("GET", url, headers=self.get_json_headers(), params=params)
            page_json = response.json()['pins']

            if page_json:
                for pin in page_json:
                    item_data = {
                        "sub_dir": kwargs.get("board_title", ""),
                        "name": str(pin["pin_id"]),
                        "size": (pin["file"]["width"], pin["file"]["height"]),
                        "item_url": get_pin_url(pin),
                        "item_index_reset": index_start_flag,
                    }
                    yield item_data

                    if index_start_flag:
                        index_start_flag = False

                _max = page_json[-1]["pin_id"]
            else:
                break

    def parse_pin(self, response):
        """
        单图解析
        :param response:
        :return:
        """
        index_start_flag = True  # 图片序号重置信号

        html = response.text
        page_json = get_page_json(html, contain="pin")
        item_data = {
            "name": page_json["pin_id"],
            "size": (page_json["file"]["width"], page_json["file"]["height"]),
            "item_url": get_pin_url(page_json),
        }
        yield item_data

        related_url = PIN_RECOMMEND.format(_id=page_json["pin_id"])
        load_max = 0
        while True:
            # 退出条件
            load_max += 1
            if load_max > self.loop_max:
                break

            params = {"page": load_max, "per_page": 20, "wfl": 1}
            response = self.request("GET", related_url, headers=self.get_json_headers(), params=params)
            page_json = response.json()['pins']
            if page_json:
                for pin in page_json:
                    item_data = {
                        "sub_dir": "related-类似图片",
                        "name": str(pin["pin_id"]),
                        "size": (pin["file"]["width"], pin["file"]["height"]),
                        "item_url": get_pin_url(pin),
                        "item_index_reset": index_start_flag,
                    }
                    yield item_data

                    if index_start_flag:
                        index_start_flag = False
            else:
                break

    def parse_pin_v2(self):
        """新版本请求"""
        index_start_flag = True  # 图片序号重置信号

        source_url = self.url_parser.get_path()
        url = API_URL + source_url

        response = self.request("GET", url, headers=self.get_json_headers())
        page_json = response.json()["pin"]
        item_data = {
            "name": str(page_json["pin_id"]),
            "size": (page_json["file"]["width"], page_json["file"]["height"]),
            "item_url": get_pin_url(page_json),
        }
        yield item_data

        related_url = url + "/recommendweb"
        load_max = 0
        while True:
            # 退出条件
            load_max += 1
            if load_max > self.loop_max:
                break

            params = {"page": load_max, "per_page": 20}
            response = self.request("GET", related_url, headers=self.get_json_headers(), params=params)

            page_json = response.json()['pins']
            if page_json:
                for pin in page_json:
                    item_data = {
                        "sub_dir": "related-类似图片",
                        "name": str(pin["pin_id"]),
                        "size": (pin["file"]["width"], pin["file"]["height"]),
                        "item_url": get_pin_url(pin),
                        "item_index_reset": index_start_flag,
                    }
                    yield item_data

                    if index_start_flag:
                        index_start_flag = False
            else:
                break

    def parse_search(self, response):
        """花瓣Search页面解析"""
        html = response.text
        page_json = get_page_json(html, contain="pins")
        for pin in page_json:
            item_data = {
                "name": str(pin["pin_id"]),
                "size": (pin["file"]["width"], pin["file"]["height"]),
                "item_url": get_pin_url(pin),
            }
            yield item_data

        cur_page = 1
        # while cur_page <= self.loop_max+1:
        while True:
            # 退出条件
            cur_page += 1
            if cur_page > self.loop_max:
                break

            payload = (('page', cur_page), ('per_page', 20), ('wfl', 1))
            response = self.request("GET", self.url, headers=self.get_json_headers(), params=payload)
            page_json = response.json()['pins']
            if page_json:
                for pin in page_json:
                    item_data = {
                        "name": str(pin["pin_id"]),
                        "size": (pin["file"]["width"], pin["file"]["height"]),
                        "item_url": get_pin_url(pin),
                    }
                    yield item_data
            else:
                break

    def parse_search_v2(self):
        """v2-花瓣Search页面解析"""

        # https://huaban.com/search?q=%E9%87%91%E6%99%A8&category=photography&sort=created_at&color=blue&file_type=image%2Fgif
        _type = re.search("type=my", self.url)

        if _type:
            url = API_URL + "/search/self_pins"
        else:
            url = API_URL + "/search"

        query_dict = self.url_parser.get_query_dict()
        query = query_dict.get("q")
        category = query_dict.get("category")
        sort = query_dict.get("sort", "all")
        color = query_dict.get("color")
        file_type = query_dict.get("file_type")

        cur_page = 0
        while True:
            # 退出条件
            cur_page += 1
            if cur_page > self.loop_max:
                break

            params = {"q": query,
                      "sort": sort,
                      "colors": color,
                      "category": category,
                      "file_type": file_type,
                      "per_page": 20,
                      "page": cur_page}
            response = self.request("GET", url, headers=self.get_json_headers(), params=params)
            page_json = response.json()['pins']
            if page_json:
                for pin in page_json:
                    item_data = {
                        "name": str(pin["pin_id"]),
                        "size": (pin["file"]["width"], pin["file"]["height"]),
                        "item_url": get_pin_url(pin),
                    }
                    yield item_data
            else:
                break

    def parse_common(self, response):
        """
        all|home|following|from|popular|favorite 页面解析
        """
        html = response.text
        page_json = get_page_json(html, contain="pins")
        for pin in page_json:
            item_data = {
                "name": str(pin["pin_id"]),
                "size": (pin["file"]["width"], pin["file"]["height"]),
                "item_url": get_pin_url(pin),
            }
            yield item_data

        load_max = 0
        while True:
            # 退出条件
            load_max += 1
            if load_max > self.loop_max:
                break

            last_item = page_json[-1]
            _max = last_item.get("seq") or last_item["pin_id"]
            params = {"max": _max, "limit": 20, "wfl": 1}
            response = self.request("GET", self.url, headers=self.get_json_headers(), params=params)
            page_json = response.json()['pins']
            if page_json:
                for pin in page_json:
                    item_data = {
                        "name": str(pin["pin_id"]),
                        "size": (pin["file"]["width"], pin["file"]["height"]),
                        "item_url": get_pin_url(pin),
                    }
                    yield item_data
            else:
                break

    def parse_common_v2(self, name):
        """
        all|home|following|from|popular|favorite 页面解析
        """
        if name == "follow":
            source_url = "/home/"
        else:
            source_url = self.url_parser.get_path()
        url = API_URL + source_url
        _max = None

        load_max = 0
        while True:
            # 退出条件
            load_max += 1
            if load_max > self.loop_max:
                break

            params = {"limit": 20, "max": _max}
            response = self.request("GET", url, headers=self.get_json_headers(), params=params)
            page_json = response.json()['pins']
            if page_json:
                for pin in page_json:
                    item_data = {
                        "name": str(pin["pin_id"]),
                        "size": (pin["file"]["width"], pin["file"]["height"]),
                        "item_url": get_pin_url(pin),
                    }
                    yield item_data

                if name == "follow":  # discovery|follow 页面请求参数"max"数据不同
                    _max = str(page_json[-1]["created_at"]) + str(page_json[-1]["file_id"])
                else:
                    _max = page_json[-1]["pin_id"]
            else:
                break

    def parse_user_boards(self, response):
        """
        用户画板页面解析
        """
        html = response.text
        page_json = get_page_json(html, contain="user")
        if page_json["boards"]:
            for _board in page_json["boards"]:
                board_id = _board["board_id"]
                board_url = BOARD_URL.format(_id=board_id)
                response = self.request("GET", board_url)
                yield from self.parse_board(response, board_url=board_url, board_title=_board["title"])
        else:
            return

        while True:
            last_item = page_json["boards"][-1]
            _max = last_item["board_id"]
            params = {"max": _max, "limit": 10, "wfl": 1}
            response = self.request("GET", self.url, headers=self.get_json_headers(), params=params)
            self.logger.debug("request_url: %s", response.url)
            page_json = response.json()['user']
            # 循环退出条件
            if page_json["boards"]:
                for _board in page_json["boards"]:
                    board_id = _board["board_id"]
                    board_url = BOARD_URL.format(_id=board_id)
                    response = self.request("GET", board_url)
                    yield from self.parse_board(response, board_url=board_url, board_title=_board["title"])
            else:
                break

    def parse_user_boards_v2(self, urlname):
        """
        用户画板页面解析
        """
        url = API_URL + f"/{urlname}/boards"
        _max = None

        while True:
            params = {"max": _max, "limit": 30, "order_by_updated": 0}
            response = self.request("GET", url, headers=self.get_json_headers(), params=params)
            page_json = response.json()['boards']

            if page_json:
                for board in page_json:
                    board_id = board["board_id"]
                    board_url = BOARD_URL.format(_id=board_id)
                    yield from self.parse_board_v2(board_url=board_url, board_title=board["title"])
                _max = page_json[-1]["board_id"]
            else:
                break

    def parse_user_pins(self, response):
        """
        用户采集页面解析
        """
        html = response.text
        page_json = get_page_json(html, contain="user")
        _max = 0
        if page_json["pins"]:
            for pin in page_json['pins']:
                item_data = {
                    "name": str(pin["pin_id"]),
                    "item_url": get_pin_url(pin),
                    "size": (pin["file"]["width"], pin["file"]["height"]),
                }
                yield item_data
                _max = page_json["pin_id"]
        else:
            return

        while True:
            params = {"max": _max, "limit": 20, "wfl": 1}
            response = self.request("GET", self.url, headers=self.get_json_headers(), params=params)
            self.logger.debug("request_url: %s", response.url)
            page_json = response.json()['user']
            if page_json["pins"]:
                for pin in page_json['pins']:
                    item_data = {
                        "name": str(pin["pin_id"]),
                        "item_url": get_pin_url(pin),
                        "size": (pin["file"]["width"], pin["file"]["height"]),
                    }
                    yield item_data
                    _max = page_json["pin_id"]
            else:
                break

    def parse_user_pins_v2(self, urlname):
        """
        用户采集页面解析
        """
        url = API_URL + f"/{urlname}/pins"
        _max = None

        while True:
            params = {"max": _max, "limit": 30}
            response = self.request("GET", url, headers=self.get_json_headers(), params=params)
            page_json = response.json()['pins']

            if page_json:
                for pin in page_json:
                    item_data = {
                        "name": str(pin["pin_id"]),
                        "item_url": get_pin_url(pin),
                        "size": (pin["file"]["width"], pin["file"]["height"]),
                    }
                    yield item_data
                _max = page_json[-1]["pin_id"]
            else:
                break

    def route(self, *args, **kwargs):
        html = kwargs.get("html")
        response = kwargs.get("response")

        is_new_version = re.search("\"切换旧版\"", html)
        url_path = self.url_parser.get_path()
        # 新版页面
        if is_new_version:
            # https://huaban.com/discovery/
            if re.match("/(discovery|follow)/?", url_path):
                name = re.match("/(discovery|follow)/?", url_path).group(1)
                self.task_name = f"{name.capitalize()}"
                return self.call_parse(self.parse_common_v2, name)

            elif re.search("/search\\?(type=pin)?", self.url):
                keyword = self.url_parser.get_query_dict().get("q")
                self.task_name = f"Search-Pin-{self.cleanup(keyword)}"
                return self.call_parse(self.parse_search_v2)

            elif re.search("/search\\?type=my", self.url):
                keyword = self.url_parser.get_query_dict().get("q")
                self.task_name = f"Search-MyPin-{self.cleanup(keyword)}"
                return self.call_parse(self.parse_search_v2)

            elif re.search("/search\\?type=board", self.url):
                return self.call_parse(self.abort, "画板搜索解析文件过多,请选择具体的<画板>下载")

            elif re.search("/search\\?type=user", self.url):
                return self.call_parse(self.abort, "用户搜索解析文件过多,请选择具体的<用户>下载")

            elif re.match("/boards/\\d+/?$", url_path):
                url = API_URL + self.url_parser.get_path()
                response = self.request("GET", url, headers=self.get_json_headers())
                page_json = response.json()['board']
                username = page_json["user"]["username"]
                slug = page_json["title"]
                self.task_name = f"Board-\'{self.cleanup(username)}-{self.cleanup(slug)}\'"
                return self.call_parse(self.parse_board_v2)

            elif re.match("/pins/\\d+(/similar)?/?$", url_path):
                pin_id = re.match("/pins/(\\d+)/?", url_path).group(1)
                self.task_name = f"Pin-{pin_id}"
                return self.call_parse(self.parse_pin_v2)

            # https://huaban.com/user/n8oq4raf7vw
            elif re.match("/user/[a-z0-9-_.]+/?$", url_path):
                urlname = re.match("/user/([a-z0-9-_.]+)/?", url_path).group(1)
                url = API_URL + f"/{urlname}/likes/boards"
                response = self.request("GET", url, headers=self.get_json_headers())
                page_json = response.json()
                username = page_json['user']["username"]
                self.task_name = f"People-画板-\'{self.cleanup(username)}\'"
                return self.call_parse(self.parse_user_boards_v2, urlname)

            # https://huaban.com/user/n8oq4raf7vw/pins
            elif re.match("/user/[a-z0-9-_.]+/pins/?$", url_path):
                urlname = re.match("/user/([a-z0-9-_.]+)/pins/?", url_path).group(1)
                url = API_URL + f"/{urlname}/likes/boards"
                response = self.request("GET", url, headers=self.get_json_headers())
                page_json = response.json()
                username = page_json['user']["username"]
                self.task_name = f"People-采集-\'{self.cleanup(username)}\'"
                return self.call_parse(self.parse_user_pins_v2, urlname)

        # 旧版页面
        else:
            if re.match("/(all|home|following|discovery|from|popular|favorite)", url_path):
                name = re.match("/(all|home|following|discovery|from|popular|favorite)", url_path).group(1)
                self.task_name = f"{name.capitalize()}"
                return self.call_parse(self.parse_common, response)

            elif re.match("/search/?$", url_path):
                keyword = self.url_parser.get_query_dict().get("q")
                self.task_name = f"Search-采集-{self.cleanup(keyword)}"
                return self.call_parse(self.parse_search, response)

            elif re.match("/search/boards/?$", url_path):
                return self.call_parse(self.abort, "画板搜索解析文件过多,请选择具体的<画板>下载")

            elif re.match("/search/people/?$", url_path):
                return self.call_parse(self.abort, "用户搜索解析文件过多,请选择具体的<用户>下载")

            elif re.match("/pins/\\d+(/similar)?/?$", url_path):
                pin_id = re.match("/pins/(\\d+)/?", url_path).group(1)
                self.task_name = f"Pin-{pin_id}"
                return self.call_parse(self.parse_pin, response)

            elif re.match("/boards/\\d+/?$", url_path):
                page_json = get_page_json(html, contain="board")
                username = page_json["user"]["username"]
                slug = page_json["title"]
                self.task_name = f"Board-\'{self.cleanup(username)}-{self.cleanup(slug)}\'"
                return self.call_parse(self.parse_board, response)

            elif re.match("/boards/?(all|favorite|popular)/?", url_path):
                return self.call_parse(self.abort, "解析文件过多,请选择具体的board下载")

            elif re.match("/[a-z0-9-_.]+(/about|/boards)?/?$", url_path):
                page_json = get_page_json(html, contain="board")
                username = page_json["user"]["username"]
                self.task_name = f"People-画板-\'{username}\'"
                return self.call_parse(self.parse_user_boards, response)

            elif re.match("/[a-z0-9-_.]+/pins/?$", url_path):
                page_json = get_page_json(html, contain="board")
                username = page_json["user"]["username"]
                self.task_name = f"People-采集-\'{username}\'"
                return self.call_parse(self.parse_user_pins, response)
