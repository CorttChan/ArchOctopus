"""
Behance
url: https://www.behance.net/
"""

# name: behance.py
# version: 0.0.1
# date: 2022/2/10 4:09
# desc:

import re
import json
from bs4 import BeautifulSoup

from archoctopus.plugins import BaseParser


SEARCH_API_URL = "https://www.behance.net/search/"
GRAPHQL_API_URL = "https://www.behance.net/v3/graphql/"
DISCOVER_API_URL = "https://www.behance.net/v2/discover/{}"


class Parser(BaseParser):
    def __init__(self, *args, **kwargs):
        BaseParser.__init__(self, *args, **kwargs)

        self.friend_name = "Behance"

        self.regexps = {
            'srcset': re.compile("srcset=\"(.*?)\""),
            'srcset_urls': re.compile("(\\S+)(\\s+([\\d.]+)[xw])?(\\s*(?:,|$))"),
            'raw_url': re.compile("[-_]\\d+x\\d+")
        }

    def get_title(self, html):
        title = super(Parser, self).get_title(html)
        title = re.sub("Photos, videos, logos, illustrations and branding on ", "", title)
        return title

    def parse_gallery(self, response, **kwargs):
        """
        解析地址:
            1. https://www.behance.net/gallery/121139619/825-3rd/
            2. https://www.behance.net/gallery/131366969/CENTRAL-ONE-C1/
        数据位置:
            <script type="application/json" id="beconfig-store_state">json_data</script>
        :param response:    响应(bytes)
        :return:    item_data(dict)
        """
        html = response.text
        html_bs = BeautifulSoup(html, 'lxml')

        data_script = html_bs.find("script", id="beconfig-store_state")

        if not data_script:
            return
        data_json = json.loads(data_script.get_text())
        modules = data_json["project"]["project"]["modules"]

        urls = []
        for module in modules:
            if module["type"] == "image":
                urls.append(module["sizes"]["original"])
            elif module["type"] == "media_collection":
                for component in module["components"]:
                    urls.append(component["sizes"]["source"])

        index_start_flag = True
        for url in urls:
            item_data = {
                "sub_dir": self.cleanup(kwargs.get("title", "")),
                "item_url": url,
                "item_index_reset": index_start_flag,
            }
            yield item_data
            if index_start_flag:
                index_start_flag = False

    def parse_discover(self):
        """
        解析地址:
            1. https://www.behance.net/galleries/
            2. https://www.behance.net/galleries/graphic-design/
            3. https://www.behance.net/galleries/architecture/architecture-visualization
        请求格式:
            method: GET
            url: "https://www.behance.net/v2/discover/"
            params: {"content": "projects", "ordinal": int, "color_hex": str, ...}
        :return:
        """
        cookies_bcp = self.session.cookies.get("bcp", domain="www.behance.net")
        bcp = {"X-BCP": cookies_bcp}

        url_path = self.url_parser.get_path()
        pat = re.compile("/galleries/?(.*)$")
        sub_path = pat.match(url_path).group(1)
        discover_url = DISCOVER_API_URL.format(sub_path)

        load_max = 0
        params = {}
        ordinal = 0

        new_headers = self.get_json_headers(**bcp)
        while True:
            params.update({"ordinal": ordinal})
            response = self.request("GET", discover_url, headers=new_headers, params=params)
            response_json = response.json()

            # with open(f"behance_{load_max}.json", "w", encoding="utf-8") as f:
            #     json.dump(response_json, f)

            for project in response_json["category_projects"]:
                title = self.cleanup(project["slug"])
                project_url = project["url"]
                response = self.request("GET", project_url)
                yield from self.parse_gallery(response=response, title=title)

            ordinal = response_json["ordinal"]

            # 退出条件
            load_max += 1
            if load_max > self.loop_max:
                break

    def parse_search(self):
        """
        解析地址:
            1. https://www.behance.net/
            2. https://www.behance.net/search/projects/
        请求格式:
            method: GET
            url: "https://www.behance.net/search"
            params: {"content": "projects", "ordinal": int, "color_hex": str, ...}
        :return:
        """
        params = self.url_parser.get_query_dict()
        params["content"] = "projects"
        load_max = 0
        while True:
            params.update({"ordinal": load_max*48})
            response = self.request("GET", SEARCH_API_URL, headers=self.get_json_headers(), params=params)
            response_json = response.json()

            for project in response_json["search"]["content"]["projects"]:
                title = self.cleanup(project["slug"])
                url = project["url"]
                response = self.request("GET", url)
                yield from self.parse_gallery(response=response, title=title)

            # 退出条件
            load_max += 1
            if load_max > self.loop_max:
                break

    def parse_graphql(self, response):
        """
        解析地址:
            1. https://www.behance.net/search/images
            2. https://www.behance.net/search/prototypes
            3. https://www.behance.net/search/users
            4. https://www.behance.net/search/moodboards
        请求格式:
            method: POST
            url: "https://www.behance.net/v3/graphql"
            payload: {"query": "", variables: {"after": Base64(index),"filter": {}, "first": 48}
        :param response:
        :return:
        """
        pass

    def parse_user(self, response):
        pass

    def parse_modules(self, response):
        """
        解析地址:
            1. https://www.behance.net/gallery/121139619/825-3rd/
            2. https://www.behance.net/gallery/131366969/CENTRAL-ONE-C1/
        数据位置:
            <script type="application/json" id="beconfig-store_state">json_data</script>
        :param response:
        :return:
        """
        html = response.text
        html_bs = BeautifulSoup(html, 'lxml')

        data_script = html_bs.find("script", id="beconfig-store_state")

        if not data_script:
            return
        data_json = json.loads(data_script.get_text())
        project_url = data_json["projectModule"]["projectModule"]["project"]["url"]
        response = self.request("GET", project_url)
        yield from self.parse_gallery(response=response, title="")

    def route(self, *args, **kwargs):
        response = kwargs.get("response")
        url_path = self.url_parser.get_path()

        # https://www.behance.net/
        # https://www.behance.net/search/projects/
        if re.match("(/search/projects)?/?$", url_path):
            return self.call_parse(self.parse_search)

        # https://www.behance.net/gallery/103583549/Amanda-Health-Coaching-and-Body-Esteem
        elif re.match("/gallery/\\d+/[\\w-]+/?$", url_path):
            return self.call_parse(self.parse_gallery, response)

        # https://www.behance.net/gallery/102008003/Ascender/modules/587753187
        elif re.match("/gallery/\\d+/[\\w-]+/modules/\\d+/?$", url_path):
            return self.call_parse(self.parse_modules, response)

        # https://www.behance.net/galleries/
        elif re.match("/galleries/?", url_path):
            return self.call_parse(self.parse_discover)

        # https://www.behance.net/search/images/
        # https://www.behance.net/search/prototypes/
        # https://www.behance.net/search/users/
        # https://www.behance.net/search/moodboards/
        elif re.match("/search/(images|prototypes|users|moodboards)/?$", url_path):
            return self.call_parse(self.parse_graphql, response)

        # https://www.behance.net/inkar-gazizoff?tracking_source=search_users
        elif re.match("/[\\w-]+/?", url_path):
            return self.call_parse(self.parse_user, response)
