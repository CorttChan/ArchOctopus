#!/usr/bin/python3
# -*- coding: utf-8 -*-
# @Time    : 2024/11/9 11:19
# @Author  : CorttChan
# @Email   : cortt.me@gmail.com
# @File    : parser.py

import configparser
import threading
import os
import logging
from http.cookiejar import CookieJar
from queue import Queue
from collections import namedtuple
from typing import Optional, Callable, Generator
from urllib.parse import urljoin

from httpx import Response, Client, HTTPError

from archoctopus.constants import APP_NAME, UserAgent
from archoctopus.plugin import Extractor
from archoctopus.item import ItemData

logger = logging.getLogger(APP_NAME)


def get_default_root_dir() -> str:
    docs_dir = os.path.expanduser("~\\Documents")
    return os.path.join(docs_dir, APP_NAME)


class Parser(threading.Thread):

    def __init__(self,
                 url: str,
                 task_id: int,
                 works_queue: Queue,
                 msgs_queue: Queue,
                 event: threading.Event,
                 extractor: Extractor,
                 cookies: CookieJar = None,
                 proxies: str = None,
                 call_back: Optional[Callable[[int], None]] = None):

        threading.Thread.__init__(self)
        self.url = url
        self.task_id = task_id
        self.works_queue = works_queue
        self.msgs_queue = msgs_queue
        self.event = event
        self.extractor = extractor
        self.call_back = call_back

        self.total = 0  # 解析文件总数
        self.index = 1  # 文件序号数值
        self.session = Client(headers={'User-Agent': UserAgent}, cookies=cookies, proxies=proxies, follow_redirects=True)

    def join_url(self, href):
        href = "/" + href.lstrip("/")  # 确保相对href为根路径,合并时覆盖原url中的整个路径部分.
        return urljoin(self.url, href)

    def run(self):
        Msg = namedtuple("Msg", "msg_type msg task_id", defaults=(self.task_id,))
        self.msgs_queue.put(Msg("task_start", ()))

        # TODO: 变量名优化
        cfg = configparser.ConfigParser()
        cfg.read("../config.ini")
        loop_max = cfg.ReadInt("/General/loop_max", defaultVal=3)                           # 加载页面加载最大次数
        root_dir = cfg.Read("/General/download_dir", defaultVal=get_default_root_dir())     # 下载根目录
        is_index = cfg.ReadBool("/Filter/is_index", defaultVal=True)                        # 判断是否给图片添加序号的信号量
        # is_page = cfg.ReadBool("/General/is_page", defaultVal=False)                      # 自动加载下一页
        # is_pdf = cfg.ReadBool("/General/pdf_output", defaultVal=False)                    # 判断是否输出页面PDF

        try:
            response = self.session.request("GET", self.url)
            content_type = response.headers.get('content-type')
            logger.debug("解析页面类型: %s", content_type)

            if content_type.startswith("image/"):  # 图片类型页面
                logger.info("单图任务: %s", self.url)

                parse_result: Generator[ItemData, Response, None] = (ItemData(url=i, path="") for i in (self.url,))
                title = f"单图任务: {self.url}"
                path = ""

            elif content_type.startswith("text/"):  # 网页类型页面
                if logger.level == logging.DEBUG:
                    with open("../debug/response.html", 'w', encoding="utf-8") as f:
                        f.write(response.text)

                parse_result: Generator[ItemData, Response, None] = self.extractor(self.url, response, loop_max)
                title = self.extractor.title
                path = self.extractor.path

            else:
                raise TypeError(f"响应对象类型错误: {content_type}")

            task_path = os.path.join(root_dir, path)
            self.msgs_queue.put(Msg("task_parse_title", (title, task_path)))

            # if is_pdf:
            #     pdf_thread = PDF(html, self.url, self.task_name, task_path, window=self.win)
            #     pdf_thread.setDaemon(True)
            #     pdf_thread.run()

            # 解析结果加入下载任务队列
            if parse_result is None:
                raise ValueError("主动忽略或未解析到任何内容")

            for item in parse_result:
                self.event.wait()

                # 主动取消任务
                if item.get("is_abort"):
                    abort_msg = item.get("abort_msg", "")
                    logger.debug("任务中止: %s", abort_msg)
                    self.msgs_queue.put(Msg("task_parse_abort", (abort_msg,)))
                    break

                while item.get("req"):
                    logger.debug("item req: %s", item)
                    response = self.session.request(item["req"],
                                                    item["req_url"],
                                                    headers=item.get("req_headers"),
                                                    params=item.get("req_params"))
                    item = parse_result.send(response)

                # 合并可能的Relative URL
                item["url"] = self.join_url(item["url"])

                # 添加序号信息
                if is_index:
                    if item.get("index_reset"):
                        self.index = 1
                    item["index"] = self.index
                    self.index += 1

                # 添加保存路径信息:
                item["path"] = os.path.join(task_path, item.get("sub_title", ""))

                self.works_queue.put(item)
                self.total += 1
                # 解析条目详情消息
                self.msgs_queue.put(Msg("task_parse_item", (item["url"], item["path"])))

        except HTTPError as e:
            self.msgs_queue.put(Msg("task_parse_error", (str(e),)))

        finally:
            # 关闭请求连接
            self.session.close()
            # 向任务队列中添加下载线程结束信号
            for t in threading.enumerate():
                if t.name.startswith(f"{self.task_id}"):
                    self.works_queue.put(None)
            # 解析完成消息
            self.msgs_queue.put(Msg("task_parse_finish", (self.total,)))

        # 任务队列阻塞等待
        self.works_queue.join()
        # 任务结束消息
        self.msgs_queue.put(Msg("task_completed", (self.total,)))
        logger.info('解析完成: %s', self.url)

        # 执行回调函数
        if callable(self.call_back):
            self.call_back(self.task_id)
