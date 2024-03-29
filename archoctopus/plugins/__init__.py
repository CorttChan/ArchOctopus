"""
ArchOctopus页面对象解析模块
"""

# name: __init__.py
# version: 0.0.2
# date: 2022/04/03 17:50
# desc:

import threading
import re
import os
import shutil
import logging
from queue import Queue
from urllib.parse import urlparse, unquote, parse_qs, urlunparse, urljoin, parse_qsl

import typing
from http.cookiejar import CookieJar

import wx
import httpx
from bs4 import BeautifulSoup

from archoctopus.utils import retry, get_docs_dir
from archoctopus.constants import APP_NAME
# from archoctopus.pdf import PDF


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:58.0) Gecko/20100101 Firefox/58.0',
}


def get_domain_from_url(url: str):
    domain = unquote(urlparse(url).hostname)
    replacements = [('www\\.|\\.com|\\.cn', ''), ('\\.', '_')]
    for _old, _new in replacements:
        domain = re.sub(_old, _new, domain)
    return domain.capitalize()


def filter_duplicate(func):
    """解析条目去重装饰器"""
    item_index = 1

    def wrapper(self, *args, **kwargs):
        results = func(self, *args, **kwargs)
        nonlocal item_index

        for parse_result in results:
            # 主动中止,直接抛出,不做处理 - "is_abort: True
            if parse_result.get("is_abort"):
                yield parse_result

            # 添加序号信息
            _index_start_flag = parse_result.get("item_index_reset")
            if _index_start_flag:  # 图片序号重置信号
                item_index = 1
            parse_result["item_index"] = item_index

            # 读取数据库urls表, 根据(task_id, url)字段判断是否重复
            # 不用"INSERT OR IGNORE", 而是分为查询和插入两步是为了判断item_index值是否需要累加
            _item_url = parse_result["item_url"]
            is_duplicate = self.url_dedup(_item_url)
            if is_duplicate:
                self.logger.info("重复条目: %s", _item_url)
                continue
            else:
                _sub_dir = parse_result.get("sub_dir")
                self.update_urls_db(_item_url, _sub_dir)  # 更新数据库urls表
                yield parse_result
                item_index += 1
        item_index = 1

    return wrapper


# class Abort:
#     """主动中止类"""
#     def __init__(self, msg):
#         self.msg = msg
#
#     def __call__(self, *args, **kwargs):
#         item_data = {
#             "is_abort": True,
#             "abort_msg": self.msg
#         }
#         yield item_data


class UrlParser:
    """
    url解析类
    """

    def __init__(self, url):
        self.url = url
        self.parser = urlparse(self.url)

    def get_path(self) -> str:
        return self.parser.path

    def get_domain(self) -> str:
        domain = unquote(str(self.parser.hostname))
        replacements = [('www\\.|\\.com|\\.cn', ''), ('\\.', '_')]
        for _old, _new in replacements:
            domain = re.sub(_old, _new, domain)
        return domain.capitalize()

    def get_path_list(self) -> list:
        path = self.get_path()
        return list(filter(None, path.split("/")))

    def get_query(self) -> str:
        return self.parser.query

    def get_query_by_key(self, key) -> typing.Union[str, None]:
        query_dict = parse_qs(self.get_query())
        value = query_dict.get(key)
        if value:
            return value[0]
        else:
            return None

    def get_query_dict(self) -> dict:
        query_dict = dict(parse_qsl(self.get_query()))
        return query_dict

    def get_source_url(self):
        return urlunparse(("", "", self.get_path(), "", self.get_query(), ""))

    def get_base_url(self):
        return urlunparse((self.parser.scheme, self.parser.hostname, "", "", "", ""))

    def get_join_url(self, href):
        return urljoin(self.get_base_url(), href)


class BaseParser(threading.Thread):
    """解析基类"""

    def __init__(self,
                 parent,
                 url: str,
                 task_id: int,
                 parse_queue: Queue,
                 pause_event: threading.Event,
                 running_event: threading.Event,
                 threads_count: int,
                 cookies: CookieJar = None,
                 proxies: [str, None] = None):

        super().__init__()
        self.url = url  # 解析地址
        self.task_id = task_id
        self.queue = parse_queue    # 解析队列
        self.parent = parent    # GUI对象

        if self.parent is None:
            from archoctopus.database import AoDatabase
            self.con = AoDatabase()
        else:
            self.con = wx.GetApp().con  # 数据库连接

        self.pause_event = pause_event  # 用于暂停线程的标识
        self.running_event = running_event  # 用于停止线程的标识
        self.count = 0  # 统计解析文件总数
        self.download_thread_count = threads_count  # 下载线程数

        self.task_name = url    # 初始化任务名(用于在TaskPanel面板显示任务名称)
        self.friend_name = get_domain_from_url(url)

        self.url_parser = UrlParser(self.url)   # url解析

        # ---- logger ----
        self.logger = logging.getLogger(APP_NAME)
        
        # ---- request ----
        self.session = httpx.Client(headers=HEADERS, cookies=cookies, proxies=proxies, follow_redirects=True)

        # ------ cfg ------
        if self.parent is None:
            self.loop_max = 3
            self.is_page = False
            self.root_dir = ""
            self.is_index = True
            self.is_pdf = False
        else:
            cfg = wx.GetApp().cfg
            self.loop_max = cfg.ReadInt("/General/loop_max", defaultVal=3)  # 异步加载页面加载最大次数
            self.is_page = cfg.ReadBool("/General/is_page", defaultVal=False)  # 自动加载下一页
            self.root_dir = cfg.Read("/General/download_dir", defaultVal=get_docs_dir())  # 下载根目录
            self.is_index = cfg.ReadBool("/Filter/is_index", defaultVal=True)  # 判断是否给图片添加序号的信号量
            self.is_pdf = cfg.ReadBool("/General/pdf_output", defaultVal=False)  # 判断是否输出页面PDF

    def get_json_headers(self, **kwargs):
        headers = {
            'Referer': self.url,
            'X-Requested-With': 'XMLHttpRequest',
        }
        headers.update(kwargs)
        return headers

    @retry(times=3)
    def request(self, method, url, headers=None, params=None, data=None):
        """网络请求"""
        response = self.session.request(method, url, headers=headers, params=params, data=data)
        response.raise_for_status()
        return response

    def route(self, *args, **kwargs) -> typing.Callable:
        """
        分类器: 根据建立的正则表达式匹配self.url,进行分类处理. 默认未None
        用法:

        def route(self):
            url_path = self.url_parser.get_path()

            if re.match("/?$", url_path):
                self.task_name = "HomeFeed"
                return self._parse

        :return: callable
        # """
        # return None
        raise NotImplementedError("'route' method should be implemented...")

    # @filter_duplicate
    # def parse(self, response, extractor: typing.Callable = None):
    #     """
    #             内容解析--生成器
    #     :param response: 响应对象
    #     :return: 生成器 'yield item_data: dict'
    #         item_data: dict {"sub_dir": str, "item_url": str, "item_index": int,                --> 必要键值
    #                          "size": (width, height), "bytes": int, "name": str, "type": str    --> 额外键值
    #                          "is_abort": bool, "abort_msg": str}                                --> 中止键值
    #     :param response:
    #     :param extractor:
    #     :return:
    #     """
    #     # extractor = self.route()
    #     if extractor:
    #         yield from extractor(response)
    #
    #     # raise NotImplementedError("'parse' method should be implemented...")

    @filter_duplicate
    def call_parse(self, func: typing.Callable, *args, **kwargs):
        """
        item_data: dict {
                "sub_dir": str, "item_url": str,                                   --> 必要键值
                "size": (width, height), "bytes": int, "name": str, "type": str    --> 额外键值
                "is_abort": bool, "abort_msg": str}                                --> 中止键值
        :param func:
        :param args:
        :param kwargs:
        :return:
        """
        if not callable(func):
            self.logger.error("类型错误: 传入对象非可调用对象")
            raise TypeError("'func' object is not callable")

        result = func(*args, **kwargs)
        return result

    @staticmethod
    def cleanup(title):
        """
        替换非法字符
        :param title: 初始输入标题
        :return: 符合windows目录命名要求的标题
        """
        if not title:
            return title
        title = title.strip()
        replacements = [("&#34;|&quot;|&#39;|&apos;|&#60;|&lt;|&#62;|&gt;", "\'"), ("&#38;|&amp;", "&"),
                        ("&#8211;", "–"),
                        ('[/:*?"<>|\\\\]', '_'), ('_{2,}', '_'), ('\\s{2,}', ' ')]
        for _old, _new in replacements:
            title = re.sub(_old, _new, title)
        return title

    def get_title(self, html):
        """
        获取页面标题
        :param html:        页面html源码
        :return:            解析页面标题
        """
        title = re.search("<title.*?>(.*?)</title>", html, flags=re.S)
        if title and title.group(1):
            task_name = self.cleanup(title.group(1))
            if task_name:
                return task_name

        title = re.search("property=[\"\']og:title[\"\']\\s+content=[\"\'](.*?)[\"\']|"
                          "content=[\"\'](.*?)[\"\']\\s+property=[\"\']og:title[\"\']", html)
        if title:
            name = title.group(1) or title.group(2)
            if name:
                task_name = self.cleanup(name)
                return task_name

        task_name = "No_Title"
        return task_name

    def is_url_exist(self, url):
        """通过查询数据库urls表判断url是否已存在"""
        sql = "SELECT * FROM urls WHERE task_id!=? AND url=?"
        result = self.con.select_one(sql, (self.task_id, url))
        return result

    def copy_local_exist_file(self, item_path, item_url, index=None):
        """直接拷贝本机已下载过的文件"""
        # 联合查询获取文件目录
        sql = "SELECT history.dir, urls.name, urls.type, urls.width, urls.height, urls.bytes " \
              "FROM urls " \
              "INNER JOIN history ON urls.task_id=history.id " \
              "WHERE urls.task_id!=? AND urls.url=?"
        result = self.con.select_one(sql, (self.task_id, item_url))
        if index:
            name = f"{index}_{result[1]}"
        else:
            name = result[1]
        exist_file = os.path.join(result[0], result[1])
        item_file = os.path.join(item_path, name)
        shutil.copyfile(exist_file, item_file)
        # 更新面板信息
        filter_result = (result[1:3], result[3:5], result[5])
        wx.CallAfter(self.parent.call_refresh_gauge, 1, item_url, filter_result)

    def url_dedup(self, url):
        """
        通过查询数据库urls表进行url去重.
        :param url:
        :return:
        """
        sql = "SELECT * FROM urls WHERE task_id=? AND url=?"
        result = self.con.select_one(sql, (self.task_id, url))
        return result

    def update_urls_db(self, url: str, sub_dir: typing.Union[str, None]):
        """注册更新数据库urls表函数"""
        sql = "INSERT INTO urls (task_id, url, sub_dir) VALUES (?, ?, ?)"
        self.con.execute(sql, (self.task_id, url, sub_dir))

    @staticmethod
    def abort(msg):
        """主动中止函数"""
        item_data = {
            "is_abort": True,
            "abort_msg": msg
        }
        yield item_data

    @filter_duplicate
    def parse_image_url(self, response):
        item_data = {
            "item_url": self.url,
            "bytes": int(response.headers.get("content-length", 0)),
        }
        yield item_data

    def run(self):
        self.logger.info("解析开始: %s --> %s", self.friend_name, self.url)
        try:
            response = self.request("GET", self.url)
            # 判断是否时图片链接
            content_type = response.headers.get('content-type')
            self.logger.debug("解析页面类型: %s", content_type)
            if re.match("image/", content_type):
                self.logger.info("单图任务: %s", self.url)
                self.task_name = "单图任务"
                self.friend_name = ""
                # 解析图片
                parse_results = self.parse_image_url(response)

            elif re.match("text/", content_type):
                # 解析标题
                html = response.text
                # with open("../debug/response.html", 'w', encoding="utf-8") as f:
                #     f.write(html)
                self.task_name = self.get_title(html)   # 默认解析获取的标题, 后续可以根据具体分类重新赋值(可选)

                # 选择提取器, 解析页面
                parse_results = self.route(html=html, response=response)

                # # 判断是否输出pdf文档
                # if self.is_pdf and not self.silence:
                #     pdf_thread = PDF(raw_html=html, raw_url=self.url, output_dir=task_dir, window=self.parent)
                #     pdf_thread.setDaemon(True)
                #     pdf_thread.run()

            else:
                raise TypeError(f"响应对象类型错误: {content_type}")

            # 更新面板信息
            task_dir = os.path.join(self.root_dir, self.friend_name, self.task_name)
            if self.parent is not None and parse_results is not None:
                os.makedirs(task_dir, exist_ok=True)
            if self.parent is not None:
                wx.CallAfter(self.parent.call_task_name, task_dir)

            # 解析结果加入下载任务队列
            if parse_results is None:
                raise ValueError("主动忽略或未解析到任何内容")

            for item_data in parse_results:
                # 主动取消任务
                if item_data.get("is_abort"):
                    msg = item_data.get("abort_msg", "")
                    self.logger.debug("任务中止: %s", msg)
                    if self.parent is not None:
                        wx.CallAfter(self.parent.call_abort, msg)
                    break
                # 判断是否含子文件夹:
                _sub_dir = item_data.get("sub_dir")
                if self.parent is not None and _sub_dir:
                    _item_dir = os.path.join(task_dir, _sub_dir)
                    os.makedirs(_item_dir, exist_ok=True)
                else:
                    _item_dir = task_dir
                item_data["task_dir"] = _item_dir
                # 判断是否需要添加图片序号:
                if not self.is_index:
                    del item_data["item_index"]

                self.logger.debug("解析项目: %s", item_data["item_url"])

                # # 通过查询urls表, 判断该条目是否已下载过, True:直接从之前下载的本地位置复制一份副本到新目录下.
                # is_exist_result = self.is_url_exist(_item_url)
                # if is_exist_result:     # 直接拷贝已下载的非相同task_id的url
                #     copyfile_thread = threading.Thread(target=self.copy_local_exist_file, args=item)
                #     copyfile_thread.setDaemon(True)
                #     copyfile_thread.run()
                # else:
                #     self.queue.put(item)

                self.queue.put(item_data)
                self.count += 1
                self.logger.debug("解析计数: %s", self.count)
        except Exception as e:
            # self.logger.error("解析错误: %s - %s", e, self.url, exc_info=True)
            self.logger.error("解析错误: %s - %s", e, self.url)
        finally:
            # 更新面板信息
            if self.parent is not None:
                wx.CallAfter(self.parent.call_imgs_sum, self.count)
            # 向任务队列中添加下载线程结束信号
            for _i in range(self.download_thread_count):
                self.queue.put(None)
            # 关闭请求连接
            self.session.close()

        self.logger.info('解析完成: %s', self.url)


class GeneralParser(BaseParser):
    """通用解析类"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger.info(self.friend_name)

        self.regexps = {
            'srcset_urls': re.compile("(\\S+)(\\s+([\\d.]+)[xw])?(\\s*(?:,|$))"),
            'raw_url': re.compile("[-_]\\d+x\\d+")
        }

    def get_absolute_url(self, uri: str):
        uri = uri.split("?")[0]
        return self.url_parser.get_join_url(uri)

    def get_raw_url(self, uri):
        """
        获取原始图url
        example_01: https://afasiaarchzine.com/wp-content/uploads/2021/12/Reiulf-Ramstad-.-Statens-Museum-
                    for-Kunst-.-Thy-afasia-2-250x250.jpg
        example_02:
        :param uri:
        :return:
        """
        url = self.regexps["raw_url"].sub("", uri)
        return url

    def parse_general(self, response):
        html = response.text
        html_bs = BeautifulSoup(html, 'lxml')
        images = html_bs.find_all(["img", "picture"])
        for image in images:
            src = image.get("src")
            srcset = image.get("srcset")
            data_src = image.get("data-src")
            data_original = image.get("data-original")
            data_original_src = image.get("data-original-src")

            if data_original:
                uri = data_original
            elif data_original_src:
                uri = data_original_src
            elif data_src:
                uri = data_src
            elif srcset:
                result = self.regexps["srcset_urls"].findall(srcset)
                result.sort(key=lambda x: int(x[2]) if x[2] else 0)
                uri = result[-1][0]
            elif src:
                uri = src
            else:
                continue

            url = self.get_absolute_url(uri)
            raw_url = self.get_raw_url(url)
            yield {"item_url": raw_url}

    def route(self, *args, **kwargs):
        response = kwargs.get("response")
        return self.call_parse(self.parse_general, response)
