"""
Pinterest解析类
url: https://www.pinterest.com/
"""

# name: pinterest.py
# version: 0.0.4
# date: 2022/08/23 13:50
# desc:

import json
import time
import re
import typing
from bs4 import BeautifulSoup
from urllib.parse import urlunparse, unquote

from archoctopus.plugins import BaseParser


# Pinterest
HOME_PAGE = 'https://www.pinterest.com/'
LOGIN_PAGE = 'https://www.pinterest.com/login/?referrer=home_page/'

# home
USER_HOME_FEED_RESOURCE = 'https://www.pinterest.com/resource/UserHomefeedResource/get/'

# board
BOARD_RESOURCE = 'https://www.pinterest.com/resource/BoardResource/get/'
BOARD_FEED_RESOURCE = 'https://www.pinterest.com/resource/BoardFeedResource/get/'
BOARD_SECTION_PINS_RESOURCE = 'https://www.pinterest.com/resource/BoardSectionPinsResource/get/'

BOARDLESS_PINS_RESOURCE = 'https://www.pinterest.com/resource/BoardlessPinsResource/get/'

# search
BASE_SEARCH_RESOURCE = 'https://www.pinterest.com/resource/BaseSearchResource/get/'

# visual-search
VISUAL_LIVE_SEARCH_RESOURCE = 'https://www.pinterest.com/resource/VisualLiveSearchResource/get/'

# pin
RELATED_MODULES_RESOURCE = 'https://www.pinterest.com/resource/RelatedModulesResource/get/'

# user
USER_RESOURCE = 'https://www.pinterest.com/resource/UserResource/get/'
BOARDS_RESOURCE = 'https://www.pinterest.com/resource/BoardsResource/get/'
USER_ACTIVITY_PINS_RESOURCE = 'https://www.pinterest.com/resource/UserActivityPinsResource/get/'


def build_get_params(options, source_url="/", context=None):
    """
    合成GET请求参数
    :param options:
    :param source_url:
    :param context:
    :return:
    """
    if context is None:
        context = {}
    params = (
        ("source_url", source_url),
        ("data", json.dumps({'options': options, "context": context})),
        ("_", '%s' % int(time.time() * 1000))
    )
    return params


def build_post_params(options, source_url="/", context=None):
    """
    合成POST请求参数
    :param options:
    :param source_url:
    :param context:
    :return:
    """
    if context is None:
        context = {}
    params = (
        ("source_url", source_url),
        ("data", json.dumps({'options': options, "context": context}))
    )
    return params


class Parser(BaseParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.friend_name = "Pinterest"
        self.logger.info("%s: %s", __file__.split("/")[-1], self.__class__.__name__)

    def parse_home(self, response):
        """
        首页解析
        :param response:
        :return:
        """
        html = response.text
        html_bs = BeautifulSoup(html, 'lxml')

        pws_data = html_bs.find("script", id="__PWS_DATA__")
        pws_data_json = json.loads(pws_data.get_text())

        # pins = pws_data_json["props"]["initialReduxState"]["pins"]

        user_home_feed_resource = pws_data_json["props"]["initialReduxState"]["resources"]["UserHomefeedResource"]
        params_key, resource = user_home_feed_resource.popitem()

        # params_key = "field_set_key=\"hf_grid\",in_news_hub=false,prependPartner=false,static_feed=false"
        # params = dict((tuple(i.split("=")) for i in params_key.split(",")))

        pins = resource["data"]
        bookmarks = [resource["nextBookmark"], ]

        for pin in pins:
            if pin["type"] == "pin" and pin["ad_match_reason"] == 0:    # 避免广告pin
                item_data = {
                    "sub_dir": "",
                    "item_url": pin["images"]["orig"]["url"],
                    "size": (pin["images"]["orig"]["width"], pin["images"]["orig"]["height"])
                }
                yield item_data

        source_url = self.url_parser.get_path()

        load_max = 0
        while True:
            # 退出条件
            load_max += 1
            if load_max > self.loop_max:
                break
            if bookmarks and bookmarks[0] == '-end-':
                break

            options = {
                "field_set_key": "hf_grid",
                "in_nux": False,
                "in_news_hub": False,
                "prependPartner": False,
                "static_feed": False,
                "bookmarks": bookmarks,
                "no_fetch_context_on_resource": False
            }
            params = build_get_params(options=options, source_url=source_url)
            req = self.request("GET", USER_HOME_FEED_RESOURCE, headers=self.get_json_headers(), params=params)
            resp = req.json()
            bookmarks = resp['resource']['options']['bookmarks']
            result = resp['resource_response']['data']

            # 循环退出条件
            if result:
                for pin in result:
                    if pin["type"] == "pin" and pin["ad_match_reason"] == 0:  # 避免广告pin
                        item_data = {
                            "sub_dir": "",
                            "item_url": pin["images"]["orig"]["url"],
                            "size": (pin["images"]["orig"]["width"], pin["images"]["orig"]["height"])
                        }
                        yield item_data
            else:
                break

    def parse_pin(self, response):
        """
        单图解析
        :param response:
        :return:
        """
        index_start_flag = True  # 图片序号重置信号
        pin_id = re.search("/pin/(\\d+)/?", self.url).group(1)

        html = response.text
        html_bs = BeautifulSoup(html, 'lxml')
        resp = html_bs.find('script', id='__PWS_DATA__')
        if resp:
            data_json = json.loads(resp.get_text())
            data = data_json["props"]["initialReduxState"]["pins"][pin_id]
            url = data["images"]["orig"]["url"]
            width = data["images"]["orig"]["width"]
            height = data["images"]["orig"]["height"]
        else:
            match = re.search("\"orig\":\\s*{\"width\":(\\d*),\"height\":(\\d*),\"url\":\"(.*?)\"}", html)
            width = match.group(1)
            height = match.group(2)
            url = match.group(3)

        item_data = {
            "item_url": url,
            "size": (width, height),
            "item_index_reset": index_start_flag,
        }
        yield item_data

        source_url = self.url_parser.get_path()
        bookmarks = []

        load_max = 0
        while True:
            load_max += 1
            if load_max > self.loop_max:
                break
            if bookmarks and bookmarks[0] == '-end-':
                break
            options = {
                "pin_id": pin_id,
                "context_pin_ids": [],
                "search_query": "",
                "source": "deep_linking",
                "top_level_source": "deep_linking",
                "top_level_source_depth": 1,
                "is_pdp": False,
                "bookmarks": bookmarks,
                "no_fetch_context_on_resource": False
            }
            params = build_get_params(options=options, source_url=source_url)
            req = self.request("GET", RELATED_MODULES_RESOURCE, headers=self.get_json_headers(), params=params)
            resp = req.json()
            bookmarks = resp['resource']['options']['bookmarks']
            result = resp['resource_response']['data']
            # 循环退出条件
            if result:
                for pin in result:
                    if pin["type"] == "pin" and pin["ad_match_reason"] == 0:  # 避免广告pin
                        item_data = {
                            "sub_dir": "related-类似图片",
                            "item_url": pin["images"]["orig"]["url"],
                            "size": (pin["images"]["orig"]["width"], pin["images"]["orig"]["height"]),
                            "item_index_reset": index_start_flag,
                        }
                        yield item_data

                        if index_start_flag:
                            index_start_flag = False
            else:
                break

    def parse_visual_search(self, response):
        """
        视觉化搜索
        :param response:
        :return:
        """
        index_start_flag = 1  # 图片序号重置信号
        padding = 16

        # 获取图片尺寸
        html = response.text
        match = re.search("\"orig\":\\s*{\"width\":(\\d*),\"height\":(\\d*),\"url\":\"(.*?)\"}", html)
        width = int(match.group(1))
        height = int(match.group(2))
        url = match.group(3)

        item_data = {
            "sub_dir": "",
            "item_url": url,
            "size": (width, height),
            "item_index_reset": index_start_flag,
        }
        yield item_data

        query_dict = self.url_parser.get_query_dict()
        x = query_dict.get("x")
        x = int(x) if x else padding

        y = query_dict.get("y")
        y = int(y) if y else padding

        w = query_dict.get("w")
        w = int(w) if w else width - padding * 2

        h = query_dict.get("h")
        h = int(h) if h else height - padding * 2

        crop_source = query_dict.get("cropSource")
        crop_source = int(crop_source) if crop_source else 5

        image_signature = query_dict.get("imageSignature")

        source_url = urlunparse(("", "", self.url_parser.get_path(), "", self.url_parser.get_query(), ""))
        crop_x = x / width
        crop_y = y / height
        crop_w = w / width
        crop_h = h / height
        pin_id = re.search("/pin/(\\d+)/?", self.url).group(1)

        bookmarks = []
        load_max = 0
        while True:
            # 循环退出条件
            load_max += 1
            if load_max > self.loop_max:
                break
            if bookmarks and bookmarks[0] == '-end-':
                break
            options = {
                "pin_id": pin_id,
                "image_signature": image_signature,
                "crop": {"x": crop_x, "y": crop_y, "w": crop_w, "h": crop_h},
                "crop_source": crop_source,
                "bookmarks": bookmarks,
                "no_fetch_context_on_resource": False
            }
            params = build_get_params(options=options, source_url=source_url)
            req = self.request("GET", VISUAL_LIVE_SEARCH_RESOURCE, headers=self.get_json_headers(), params=params)
            self.logger.debug("visual_url: %s", req.url)
            resp = req.json()
            bookmarks = resp['resource']['options']['bookmarks']
            result = resp['resource_response']['data']["results"]
            # 循环退出条件
            if result:
                for pin in result:
                    if pin["type"] == "pin" and pin["ad_match_reason"] == 0:  # 避免广告pin
                        item_data = {
                            "sub_dir": "related-视觉化搜索",
                            "item_url": pin["images"]["orig"]["url"],
                            "size": (pin["images"]["orig"]["width"], pin["images"]["orig"]["height"]),
                            "item_index_reset": index_start_flag,
                        }
                        yield item_data

                        if index_start_flag:
                            index_start_flag = False
            else:
                break

    def parse_search_pins(self):
        """
        搜索所有钉图解析
        :return:
        """
        index_start_flag = 1  # 图片序号重置信号

        scope = "pins"
        query_dict = self.url_parser.get_query_dict()
        query = query_dict.get("q")
        source_url = self.url_parser.get_source_url()

        bookmarks = []
        load_max = 0
        while True:
            # 循环退出条件
            load_max += 1
            if load_max > self.loop_max:
                break
            if bookmarks and bookmarks[0] == '-end-':
                break

            options = {
                "appliedProductFilters": "---",
                "auto_correction_disabled": False,
                "query": query,
                "redux_normalize_feed": True,
                "rs": "rs",
                "scope": scope,
                "bookmarks": bookmarks,
                "no_fetch_context_on_resource": False
            }
            params = build_get_params(options=options, source_url=source_url)
            req = self.request("GET", BASE_SEARCH_RESOURCE, headers=self.get_json_headers(), params=params)
            resp = req.json()

            # with open(f"pinterest_{load_max}.json", "w", encoding="utf-8") as f:
            #     json.dump(resp, f)

            bookmarks = resp['resource']['options']['bookmarks']
            result = resp['resource_response']['data']['results']
            # 循环退出条件
            if result:
                for pin in result:
                    if pin["type"] == "pin" and pin["ad_match_reason"] == 0:  # 避免广告pin
                        item_data = {
                            "sub_dir": "",
                            "item_url": pin["images"]["orig"]["url"],
                            "size": (pin["images"]["orig"]["width"], pin["images"]["orig"]["height"]),
                            "item_index_reset": index_start_flag,
                        }
                        yield item_data

                        if index_start_flag:
                            index_start_flag = False
            else:
                break

    def parse_search_mypins(self):
        """
        搜索我的钉图解析
        :return:
        """
        index_start_flag = 1  # 图片序号重置信号

        scope = "my_pins"
        query_dict = self.url_parser.get_query_dict()
        query = query_dict.get("q")
        source_url = self.url_parser.get_source_url()

        bookmarks = []
        while True:
            # 循环退出条件, 此分类不做循环限制.
            if bookmarks and bookmarks[0] == '-end-':
                break

            options = {
                "appliedProductFilters": "---",
                "auto_correction_disabled": False,
                "query": query,
                "redux_normalize_feed": True,
                "rs": "ac",
                "scope": scope,
                "bookmarks": bookmarks,
                "no_fetch_context_on_resource": False
            }
            params = build_get_params(options=options, source_url=source_url)
            req = self.request("GET", BASE_SEARCH_RESOURCE, headers=self.get_json_headers(), params=params)
            resp = req.json()

            # with open(f"pinterest_{load_max}.json", "w", encoding="utf-8") as f:
            #     json.dump(resp, f)

            bookmarks = resp['resource']['options']['bookmarks']
            result = resp['resource_response']['data']['results']
            # 循环退出条件
            if result:
                for pin in result:
                    if pin["type"] == "pin" and pin["ad_match_reason"] == 0:  # 避免广告pin
                        item_data = {
                            "sub_dir": "",
                            "item_url": pin["images"]["orig"]["url"],
                            "size": (pin["images"]["orig"]["width"], pin["images"]["orig"]["height"]),
                            "item_index_reset": index_start_flag,
                        }
                        yield item_data

                        if index_start_flag:
                            index_start_flag = False
            else:
                break

    def parse_board(self, **kwargs):
        """
        画板解析
        :param kwargs:
        :return:
        """
        index_start_flag = 1  # 图片序号重置信号

        board_id = kwargs.get("id")
        source_url = kwargs.get("url", self.url_parser.get_path())
        if not board_id:
            options = {
                "username": kwargs.get("username"),
                "slug": kwargs.get("slug"),
                "field_set_key": "detailed",
                "no_fetch_context_on_resource": False,
            }
            params = build_get_params(options=options, source_url=self.url_parser.get_path())
            req = self.request("GET", BOARD_RESOURCE, headers=self.get_json_headers(), params=params)
            resp = req.json()
            board_id = resp['resource_response']['data']["id"]

        sub_dir = kwargs.get("title", "")
        bookmarks = []
        while True:
            options = {
                "board_id": board_id,
                "board_url": source_url,
                "currentFilter": -1,
                "field_set_key": "react_grid_pin",
                "filter_section_pins": True,
                "sort": "default",
                "layout": "default",
                "page_size": 25,
                "redux_normalize_feed": True,
                "bookmarks": bookmarks,
                "no_fetch_context_on_resource": False,
            }
            params = build_get_params(options=options, source_url=source_url)
            req = self.request("GET", BOARD_FEED_RESOURCE, headers=self.get_json_headers(), params=params)
            resp = req.json()
            bookmarks = resp['resource']['options']['bookmarks']
            result = resp['resource_response']['data']
            # 循环退出条件
            if result:
                for pin in result:
                    if pin["type"] == "pin":  # 避免广告pin
                        item_data = {
                            "sub_dir": sub_dir,
                            "item_url": pin["images"]["orig"]["url"],
                            "size": (pin["images"]["orig"]["width"], pin["images"]["orig"]["height"]),
                            "item_index_reset": index_start_flag,
                        }
                        yield item_data

                        if index_start_flag:
                            index_start_flag = False
            else:
                break

    def parse_people_saved(self):
        """
        用户保存的所有画板解析
        :return:
        """
        source_url = self.url_parser.get_path()
        username = self.url_parser.get_path_list()[0]

        bookmarks = []
        while True:
            if bookmarks and bookmarks[0] == '-end-':
                break
            options = {
                "privacy_filter": "all",
                "sort": "last_pinned_to",
                "field_set_key": "profile_grid_item",
                "filter_stories": False,
                "username": username,
                "page_size": 25,
                "group_by": "visibility",
                "include_archived": True,
                "redux_normalize_feed": True,
                "bookmarks": bookmarks,
                "no_fetch_context_on_resource": False
            }
            params = build_get_params(options=options, source_url=source_url)
            req = self.request("GET", BOARDS_RESOURCE, headers=self.get_json_headers(), params=params)
            resp = req.json()
            bookmarks = resp['resource']['options']['bookmarks']
            result = resp['resource_response']['data']
            # 循环退出条件
            if result:
                for board in result:
                    if board["type"] == "board":  # 排除首个"所有釘圖"画板type=story
                        yield from self.parse_board(id=board["id"],
                                                    url=board["url"],
                                                    title=self.cleanup(board["name"]))
            else:
                # TODO 当第一次请求为空时，存在未保存到任何画板的图片时 - BoardlessPinsResource
                break

    def parse_boardless(self):
        """
        BoardLess
        """
        pass

    def parse_people_created(self):
        """
        用户建立的所有钉图解析
        :return:
        """
        index_start_flag = 1  # 图片序号重置信号

        result = re.search("/([^/]+)/_created/?", self.url)
        source_url = result.group()
        username = result.group(1)

        options = {
            "username": username,
            "field_set_key": "profile",
            "no_fetch_context_on_resource": False
        }

        params = build_get_params(options=options, source_url=source_url)
        req = self.request("GET", USER_RESOURCE, params=params)
        resp = req.json()

        user_id = resp["resource_response"]["data"]["id"]

        bookmarks = []
        while True:
            if bookmarks and bookmarks[0] == '-end-':
                break

            options = {
                "data": {"filter_version": 1},
                "exclude_add_pin_rep": True,
                "field_set_key": "grid_item",
                "is_own_profile_pins": False,
                "redux_normalize_feed": True,
                "user_id": user_id,
                "username": username,
                "bookmarks": bookmarks,
                "no_fetch_context_on_resource": False
            }
            params = build_get_params(options=options, source_url=source_url)
            req = self.request("GET", USER_ACTIVITY_PINS_RESOURCE, headers=self.get_json_headers(), params=params)
            resp = req.json()
            bookmarks = resp['resource']['options']['bookmarks']
            result = resp['resource_response']['data']
            # 循环退出条件
            if result:
                for pin in result:
                    if pin["type"] == "pin":  # 避免广告pin
                        item_data = {
                            "sub_dir": "",
                            "item_url": pin["images"]["orig"]["url"],
                            "size": (pin["images"]["orig"]["width"], pin["images"]["orig"]["height"]),
                            "item_index_reset": index_start_flag,
                        }
                        yield item_data

                        if index_start_flag:
                            index_start_flag = False
            else:
                break

    def parse_section(self, response):
        """
        用户画板下选择的钉图解析
        :param response:
        :return:
        """
        index_start_flag = 1  # 图片序号重置信号

        html = response.text
        html_bs = BeautifulSoup(html, 'lxml')

        pws_data = html_bs.find("script", id="__PWS_DATA__")
        pws_data_json = json.loads(pws_data.get_text())

        data = pws_data_json["props"]["initialReduxState"]["sections"]
        section_data = data.popitem()[1]

        section_id = section_data["id"]
        source_url = self.url_parser.get_path()

        bookmarks = []
        while True:
            if bookmarks and bookmarks[0] == '-end-':
                break

            options = {
                "currentFilter": -1,
                "field_set_key": "react_grid_pin",
                "is_own_profile_pins": True,
                "page_size": 25,
                "redux_normalize_feed": True,
                "section_id": section_id,
                "bookmarks": bookmarks,
                "no_fetch_context_on_resource": False
            }

            params = build_get_params(options=options, source_url=source_url)
            req = self.request("GET", BOARD_SECTION_PINS_RESOURCE, headers=self.get_json_headers(), params=params)
            resp = req.json()
            bookmarks = resp['resource']['options']['bookmarks']
            result = resp['resource_response']['data']
            # 循环退出条件
            if result:
                for pin in result:
                    if pin["type"] == "pin":  # 避免广告pin
                        item_data = {
                            "sub_dir": "",
                            "item_url": pin["images"]["orig"]["url"],
                            "size": (pin["images"]["orig"]["width"], pin["images"]["orig"]["height"]),
                            "item_index_reset": index_start_flag,
                        }
                        yield item_data

                        if index_start_flag:
                            index_start_flag = False
            else:
                break

    def route(self, *args, **kwargs) -> [typing.Callable, None]:
        # 分类判断
        url_path = self.url_parser.get_path()
        response = kwargs.get("response")

        # https://www.pinterest.com/
        if re.match("/?$", url_path):
            self.task_name = "HomeFeed"
            return self.call_parse(self.parse_home, response)

        # https://www.pinterest.com/pin/1477812365363581/
        elif re.match("/pin/\\d+/?$", url_path):
            pin_id = re.search("/pin/(\\d+)/?", self.url).group(1)
            self.task_name = f"Pin-{pin_id}"
            return self.call_parse(self.parse_pin, response)

        # https://www.pinterest.com/pin/1477812365363581/visual-search/?imageSignature=2eae751e02edf8208b8278f8e3292c11
        elif re.match("/pin/\\d+/visual-search/?", url_path):
            pin_id = re.search("/pin/(\\d+)/?", self.url).group(1)
            self.task_name = f"Pin-{pin_id}"
            return self.call_parse(self.parse_visual_search, response)

        # https://www.pinterest.com/search/pins/?q=%E5%BB%BA%E7%AD%91%20%E5%AE%A4%E5%86%85%20inner&rs=rs&eq=&etslf=6681&term_meta[]=%E5%BB%BA%E7%AD%91%7Crecentsearch%7C2&term_meta[]=%E5%AE%A4%E5%86%85%7Crecentsearch%7C2&term_meta[]=inner%7Crecentsearch%7C2
        elif re.match("/search/pins/?$", url_path):
            keyword = self.url_parser.get_query_dict().get("q")
            self.task_name = "Search-所有钉图-\'{}\'".format(self.cleanup(keyword))
            return self.call_parse(self.parse_search_pins)

        # https://www.pinterest.com/search/my_pins/?q=%E5%BB%BA%E7%AD%91&rs=typed&term_meta[]=%E5%BB%BA%E7%AD%91%7Ctyped
        elif re.match("/search/my_pins/?$", url_path):
            keyword = self.url_parser.get_query_dict().get("q")
            self.task_name = f"Search-我的钉图-\'{self.cleanup(keyword)}\'"
            return self.call_parse(self.parse_search_mypins)

        # https://www.pinterest.com/search/boards/?q=%E5%BB%BA%E7%AD%91&rs=filter
        elif re.match("/search/boards/?$", url_path):
            return self.call_parse(self.abort, "解析文件过多,请选择具体的board下载")

        # https://www.pinterest.com/search/videos/?q=%E5%BB%BA%E7%AD%91&rs=filter
        elif re.match("/search/videos/?$", url_path):
            return self.call_parse(self.abort, "暂不支持视频下载")

        # https://www.pinterest.com/kane8616/_saved/
        elif re.match("/(?!search|pin)[^/]*/_saved/?$", url_path):
            result = re.search("/([^/]*)/_saved/?", self.url)
            username = result.group(1)
            self.task_name = f"People-\'{username}\'"
            return self.call_parse(self.parse_people_saved)

        # https://www.pinterest.com/corttchan/render/
        elif re.match("/(?!search|pin)[^/]*/[^/]+/?$", url_path):
            result = re.search("/([^/]*)/([^/]+)/?$", self.url)
            username = result.group(1)
            slug = unquote(result.group(2))
            self.task_name = f"Board-\'{username}-{slug}\'"
            return self.call_parse(self.parse_board, username=username, slug=slug)

        # https://www.pinterest.com/kane8616/_created/
        elif re.match("/(?!search|pin)[^/]+/_created/?$", url_path):
            result = re.search("/([^/]*)/_saved/?", self.url)
            username = result.group(1)
            self.task_name = f"People-\'{username}-创建钉图\'"
            return self.call_parse(self.parse_people_created)

        # https://www.pinterest.com/corttchan/shopping-mall-facade/modern/
        elif re.match("/(?!search|pin)[^/]*/[^/]+/[^/]+/?$", url_path):
            result = re.search("/([^/]*)/([^/]+)/([^/]+)/?$", self.url)
            username = result.group(1)
            slug = result.group(2)
            section_slug = result.group(3)
            self.task_name = f"Section-\'{username}-{slug}-{section_slug}\'"
            return self.call_parse(self.parse_section, response)

        # # https://www.pinterest.com/corttchan/shopping-mall-facade/modern/_tools/more-ideas/?ideas_referrer=24
        # # https://www.pinterest.com/corttchan/design-tmp/_tools/more-ideas/?ideas_referrer=23
        # elif re.match(".*?/_tools/more-ideas/?$", url_path):
        #     return self.parse_more

        # # https://www.pinterest.com/corttchan/shopping-mall-facade/modern/_tools/organize/?organization_feed=False
        # # https://www.pinterest.com/corttchan/design-tmp/_tools/organize/?organization_feed=False
        # elif re.match(".*?/_tools/organize/?$", url_path):
        #     return self.parse_organize


if __name__ == '__main__':
    pass
