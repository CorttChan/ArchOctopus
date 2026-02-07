"""
ArchOctopus 下载模块
"""

import threading
import os
import logging
from http.cookiejar import CookieJar
from collections import namedtuple
from urllib.parse import urlsplit
from queue import Queue

from httpx import Client, ConnectError, TimeoutException

from archoctopus.filter import Filter
from archoctopus.utils import retry
from archoctopus.constants import APP_NAME, UserAgent


logger = logging.getLogger(APP_NAME)


class Downloader(threading.Thread):
    """
    ArchOctopus 下载器
    """

    def __init__(self,
                 task_id: int,
                 tasks_queue: Queue,
                 msgs_queue: Queue,
                 event: threading.Event,
                 item_filter: Filter,
                 cookies: CookieJar = None,
                 proxies: str = None,):
        super(Downloader, self).__init__()

        self.task_id = task_id
        self.tasks_queue = tasks_queue
        self.msgs_queue = msgs_queue
        self.event = event
        self.filter = item_filter
        self.session = Client(headers={'User-Agent': UserAgent}, cookies=cookies, proxy=proxies)

    @retry(max_attempts=3, delay=1.0, exceptions=(ValueError, ConnectError, TimeoutException))
    def _download(self, item: dict) -> bool:
        """
        下载函数
        :param item:
        :return: None
        """
        url = item["url"]
        # 链接内嵌图片 data:image, 暂做忽略处理。
        if url.startswith("data:image"):
            # self.embedded_img(url)
            return False

        name = item.get("name") or os.path.basename(urlsplit(url).path)
        name = f"{index}_{name}" if (index:=item.get("index")) else name

        # 判断文件是否已存在
        file = os.path.join(item["path"], name)
        if os.path.exists(file):
            logger.debug("图片已下载: %s", file)
            return True
        else:
            os.makedirs(item["path"], exist_ok=True)

        # 请求响应内容
        tmp_file = file + '.tmp'
        if os.path.isfile(tmp_file):
            tmp_file_size = os.path.getsize(file)
        else:
            tmp_file_size = 0
        headers = {'Range': f"bytes={tmp_file_size}-"}

        with self.session.stream("GET", url, headers=headers) as s:
            logger.debug("请求状态 : %s, %s", s.status_code, url)
            if s.status_code == 200:
                mode = "wb"
            elif s.status_code == 206:
                mode = "ab"
            elif s.status_code == 416:
                logger.error("416 错误 – 所请求的范围无法满足: %s", url)
                os.remove(tmp_file)
                raise ValueError("416请求错误: 临时文件大小(tmp_file_size)数据超出请求范围")
            else:
                logger.error("响应码错误: %s, %s", s.status_code, url)
                return False

            with open(tmp_file, mode) as f:
                for chunk in s.iter_bytes(chunk_size=10240):
                    if chunk:
                        f.write(chunk)
                f.flush()

            item["path"] = tmp_file

        return True

    def run(self):
        Msg = namedtuple("Msg", "msg_type msg task_id", defaults=(self.task_id, ))

        while True:
            self.event.wait()
            item = self.tasks_queue.get()

            # 下载线程接受到退出信号,正常退出.
            if item is None:
                logger.info(f"下载线程{self.name} -- 关闭")
                self.tasks_queue.task_done()
                break

            # 下载前过滤
            if self.filter(item):
                logger.info("download completed: %s", item["url"])
                self.msgs_queue.put(Msg("task_download_filtered", (item["url"], )))
                self.tasks_queue.task_done()
                continue

            # 下载
            result = self._download(item)

            if result:
                if self.filter(item):
                    os.remove(item["path"])
                    self.msgs_queue.put(Msg("task_download_filtered", (item["url"],)))
                else:
                    os.rename(item["path"], item["path"][:-4])
                    self.msgs_queue.put(Msg("task_download_success", (item["url"], )))
            else:
                self.msgs_queue.put(Msg("task_download_failed", (item["url"],)))

            self.tasks_queue.task_done()

        self.msgs_queue.put(Msg("task_download_finish", (self.name, )))

        self.session.close()
