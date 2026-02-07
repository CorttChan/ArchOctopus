#!/usr/bin/python3
# -*- coding: utf-8 -*-
# @Time    : 2026/1/24 03:35
# @Author  : CorttChan
# @Email   : cortt.me@gmail.com
# @File    : plugin.py

import os, re
from functools import wraps
import logging
import importlib
from urllib.parse import urlparse
from typing import Dict, Generator, Tuple, Callable, ParamSpec

from bs4 import BeautifulSoup
from httpx import Response

from archoctopus.item import ItemData
from archoctopus.constants import APP_NAME
from archoctopus.utils import cleanup

logger = logging.getLogger(APP_NAME)

# TODO: 检查优化正则表达式
REGEXPS = {
    # 匹配srcset属性中多个图片值
    'SRCSET_URLS': re.compile("(\\S+)(\\s+([\\d.]+)[xw])?(\\s*(?:,|$))"),
    # 匹配一般性缩小图格式
    'RAW_URL': re.compile("[-_]\\d+x\\d+"),
    # 匹配img标签中包含原始图或是延时加载属性的标签名
    # (e.g., data-src|data-original|data-original-src|data-lazyload)
    'ATTR_KEY': re.compile("data-(src|original|lazy|load)"),
    'TITLE': re.compile("<title.*?>(.+?)</title>", flags=re.S),
    "PROPERTY_TITLE": re.compile("property=[\"\']og:title[\"\']\\s+content=[\"\'](.+?)[\"\']|content=[\"\'](.+?)[\"\']\\s+property=[\"\']og:title[\"\']"),
}

P = ParamSpec('P')

# 内置插件名
DEFAULT_EXTRACT: Dict[str, str] = {
    r"car\.autohome\.com\.cn": "autohome",
    r".*?\.archdaily\..*?": "archdaily",
    r"www\.archcollege\.com": "archcollege",
    r"www\.gooood\.cn": "gooood",
    r"(www\.)?huaban\.com": "huaban",
}


def get_title(html: str) -> str:
    title = ""
    for i in (REGEXPS["TITLE"], REGEXPS["PROPERTY_TITLE"],):
        result = i.search(html)
        if result:
            title = result.group(1)
            break
    return title

def default_extract(html: str) -> Generator[ItemData, Response, None]:
    html_bs = BeautifulSoup(html, 'lxml')
    images = html_bs.find_all(["img", "picture"])
    for image in images:
        src: str = image.get("src")
        srcset: str = image.get("srcset")
        # 判断是否包含srcset,并提取最大尺寸图片链接
        if srcset:
            result = REGEXPS["SRCSET_URLS"].findall(srcset)
            result.sort(key=lambda x: int(x[2]) if x[2] else 0)
            uri = result[-1][0]
        # 判断是否包含延迟加载图片
        else:
            # 优先匹配data-*标签内容
            for k, v in image.attrs.items():
                if REGEXPS["ATTR_KEY"].search(k):
                    uri = v
                    break
            # 若未匹配到则最后使用src内容
            else:
                if not src or src.startswith("data:image"):  # 若src为空或者使用编码图片则忽略
                    continue
                else:
                    uri = src

        uri = REGEXPS["RAW_URL"].sub("", uri)  # 默认规则
        yield ItemData(url=uri, path="")


class Extractor:
    """
    图片提取器:
    route装饰器注册url正则表达式,用于匹配特定的url.匹配到url后,调用注册的提取函数,返回包含ItemDate类型的生成器.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.title = ""
        self.handlers: Dict[str, Tuple[Callable, str]] = {}

    def __call__(self, url: str, response: Response, loop_max: int) -> Generator[ItemData, Response, None]:
        html = response.text
        self.title = get_title(html)
        url_path = urlparse(url).path
        for pattern in self.handlers.keys():
            args = [pattern, ]
            match = re.match(pattern, url_path)
            if match:
                func, title = self.handlers[pattern]
                args.extend(match.groups())
                kwargs = match.groupdict()
                result = func(url, response, loop_max=loop_max, **kwargs)
                break
        else:
            result = default_extract(html)
        return result

    def route(self, pattern: str, title: str=""):
        """
        路由装饰器
        :param pattern: 匹配的正则表达式字符串
        :param title: 可选的匹配的标题,默认为空
        :return: 返回生成器对象
        """
        def decorator(func: Callable[[str, str, P], Generator[ItemData, Response, None]]) -> Callable[[str, str, P], Generator[ItemData, Response, None]]:

            @wraps(func)
            def wrapper(url: str, response: str, **kwargs: P.kwargs) -> Generator[ItemData, Response, None]:
                return func(url, response, **kwargs)

            self.handlers.update({pattern: (wrapper, title)})
            return wrapper

        return decorator

    @property
    def path(self) -> str:
        path = os.path.join(self.name, cleanup(self.title))
        return path


class Plugin:
    loaded_plugins: Dict[str, Extractor] = {}
    plugin_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "plugins")

    def __new__(cls, name):
        if name in cls.loaded_plugins:
            instance = cls.loaded_plugins[name]
            logger.debug("cache_parser: %s", name)
        else:
            instance = cls._load(name)
            cls.loaded_plugins[name] = instance
            logger.debug("new_parser: %s", name)

        return instance

    @classmethod
    def _load(cls, hostname):
        """
        动态加载域名相关插件
        :param hostname: 域名
        :return:
        """
        import sys
        if cls.plugin_dir not in sys.path:
            sys.path.insert(0, cls.plugin_dir)

        plugin_file_path = os.path.join(cls.plugin_dir, hostname+".py")
        if os.path.exists(plugin_file_path):
            plugin_module = importlib.import_module(hostname)
            plugin = getattr(plugin_module, "extractor")
            if isinstance(plugin, Extractor):
                cls.loaded_plugins[hostname] = plugin
            else:
                logger.error(f"'{hostname}'插件中未找到Extractor对象实例")
                plugin = None
        else:
            plugin = cls.loaded_plugins.get("")

        if plugin is None:
            cls.loaded_plugins[""] = (plugin := Extractor(""))

        return plugin
