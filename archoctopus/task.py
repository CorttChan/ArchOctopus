"""
ArchOctopus 任务管理模块

"Plugin" -- 插件化加载管理器:
    -- 根据url域名自动加载对应的解析类，同时保持已有解析类的缓存，在传入含相同域名的url参数时，可以直接调用。
"""

import threading
from queue import Queue
import os
import re
import weakref
from urllib.parse import urlparse, unquote
import logging
from importlib import import_module

import wx

from archoctopus import cookies
from archoctopus.constants import APP_NAME
from archoctopus.download import Downloader
from archoctopus.plugins import GeneralParser


# Constant
ACTIVATING = 0              # 项目状态 -- 激活
COMPLETED = 1               # 项目状态 -- 完成
ABORTED = 2                 # 项目状态 -- 中止
ERROR = 4                   # 项目状态 -- 错误

regexps = {
    "archdaily": re.compile("(my|www).(archdaily|plataformaarquitectura)", re.I),
}
logger = logging.getLogger(APP_NAME)


def get_domain_from_url(url: str):
    domain = unquote(urlparse(url).hostname)
    for k, v in regexps.items():
        if v.match(domain):
            return k
    replacements = [('www\\.', ''),
                    ('(\\.com|\\.org|\\.info|\\.net|\\.biz|'
                     '\\.com\\.cn|\\.cn|\\.jp|\\.tw|\\.hk|\\.us|\\.es|\\.br|\\.fr|\\.it|\\.sg)$', ''),  # 常见顶级域名
                    ('\\.', '_')]
    for old, new in replacements:
        domain = re.sub(old, new, domain)
    return domain


# def get_custom_class(domain, rule):
#     """生成自定义解析类"""
#
#     @filter_duplicate
#     def parse(self, response):
#         html = response.text
#         result = re.findall(rule, html)
#         for _r in result:
#             yield "", _r
#
#     return type(domain, (BaseParser,), {"friend_name": domain, "parse": parse})


class Plugin:
    """插件化调用解析类"""
    manager = weakref.WeakValueDictionary()

    def __new__(cls, name, *args, **kwargs):
        if name in cls.manager:
            instance = cls.manager[name]
            logger.debug("cache_parser: %s", name)
        else:
            instance = cls._load(name)
            cls.manager[name] = instance
            logger.debug("new_parser: %s", name)

        return instance(*args, **kwargs)

    @staticmethod
    def _load(plugin_name):
        # # 自定义规则-----------------
        # cfg = wx.GetApp().cfg
        # cfg_path = f"/Rules/{plugin_name}"
        # if cfg.Exists(cfg_path):
        #     rule = cfg.Read(cfg_path)
        #     return get_custom_class(plugin_name, rule)     # 返回自定义规则解析类

        # 内置规则-----------------
        bundle_dir = wx.GetApp().get_install_dir()
        plugins_path = os.path.join(bundle_dir, "plugins")
        logger.debug("载入解析模块路径: %s", plugins_path)
        if plugin_name+".py" in os.listdir(plugins_path):
            plugin = import_module("plugins." + plugin_name)
            return plugin.Parser        # 返回预定义解析模块
        else:
            return GeneralParser        # 返回通用解析模块


class TaskItem:
    """
    任务类
    """

    def __init__(self, parent, download_thread_count=5):
        # GUI关联的任务面板
        self.parent = parent
        # 图片下载队列
        self.queue = Queue()
        # 下载线程数
        self.download_thread_count = download_thread_count
        # 线程控制信号
        self.pause_event = threading.Event()  # 用于暂停线程的标识
        self.pause_event.set()  # 设置为True
        self.running_event = threading.Event()  # 用于停止线程的标识
        self.running_event.set()  # 将running设置为True
        # 网络代理
        self.proxies = self.parent.GetTopLevelParent().proxies
        # 浏览器cookies
        try:
            self.cookies = cookies.load()
        except Exception as e:
            logger.error("浏览器cookies载入失败: %s", e)
            self.cookies = None
        # 线程池
        self.pool = []

    def is_running(self):
        """
        通过检查解析线程和下载线程来检测任务是否还在运行.
        :return: bool
        """
        return any(_thread.is_alive() for _thread in self.pool)

    def __getattr__(self, item):
        try:
            return self.parent.task_info[item]
        except KeyError:
            raise AttributeError(item)

    def run(self):
        """项目启动"""
        # 解析线程
        domain = get_domain_from_url(self.parent.task_info["url"])
        self.parent.task_info["domain"] = domain
        logger.debug("创建解析线程. \n任务参数: %s", self.parent.task_info)
        parse_thread = Plugin(domain,
                              self.parent,
                              self.parent.task_info["url"],
                              self.parent.task_info["id"],
                              self.queue,
                              self.pause_event,
                              self.running_event,
                              self.download_thread_count,
                              cookies=self.cookies,
                              proxies=self.proxies)
        parse_thread.setDaemon(True)
        parse_thread.start()
        self.pool.append(parse_thread)
        logger.debug("执行解析线程.")
        # 下载线程池
        for _download_thread in range(self.download_thread_count):
            _download_thread = Downloader(self.parent,
                                          self.queue,
                                          self.pause_event,
                                          self.running_event,
                                          cookies=self.cookies,
                                          proxies=self.proxies)
            _download_thread.setDaemon(True)
            _download_thread.start()
            self.pool.append(_download_thread)

    def pause(self):
        """项目暂定"""
        self.pause_event.clear()  # 设置为False, 让线程阻塞

    def resume(self):
        """项目继续"""
        self.pause_event.set()  # 设置为True, 让线程停止阻塞

    def stop(self):
        """项目停止&删除"""
        self.pause_event.set()  # 将线程从暂停状态恢复, 如何已经暂停的话
        self.running_event.clear()  # 设置为False
