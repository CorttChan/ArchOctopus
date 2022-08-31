"""
ArchOctopus 下载模块
"""

import threading
import os
import re
from queue import Queue
import logging
from http.cookiejar import CookieJar

import wx
from httpx import Client

from utils import \
    retry, \
    get_name_from_url, \
    get_img_format, \
    get_file_type, \
    get_file_bytes, \
    get_file_size, \
    is_downloaded

from constants import APP_NAME


class Downloader(threading.Thread):
    """
    ArchOctopus 下载器
    """

    def __init__(self,
                 window,
                 download_queue: Queue,
                 pause_event: threading.Event,
                 running_event: threading.Event,
                 cookies: CookieJar = None,
                 proxies: [str, None] = None,):
        super(Downloader, self).__init__()

        self.window = window
        self.queue = download_queue
        self.pause_event = pause_event  # 用于暂停线程的标识
        self.running_event = running_event  # 用于停止线程的标识

        # ---- logger ----
        self.logger = logging.getLogger(APP_NAME)

        # ---- request ----
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:58.0) Gecko/20100101 Firefox/58.0',
        }
        self.session = Client(headers=headers, cookies=cookies, proxies=proxies)

        # ------ cfg ------
        cfg = wx.GetApp().cfg
        self.cfg_size = (cfg.ReadInt("/Filter/min_width", defaultVal=0),
                         cfg.ReadInt("/Filter/min_height", defaultVal=0))
        self.cfg_bytes = (cfg.ReadInt("/Filter/min_size", defaultVal=0),
                          cfg.ReadInt("/Filter/max_size", defaultVal=0))
        self.cfg_type = cfg.Read("/Filter/type", defaultVal="")

    def _filter_size(self, file_size: tuple):
        """过滤图片尺寸"""
        if file_size is None:
            return False
        if any(self.cfg_size) and not all([x[0] >= x[1] for x in zip(file_size, self.cfg_size)]):
            self.logger.debug("filter_size_True: %s", file_size)
            return True

    def _filter_type(self, file_type: tuple):
        """过滤图片类型"""
        if self.cfg_type and file_type not in self.cfg_type.split(","):
            self.logger.debug("filter_type_True: %s", file_type)
            return True

    def _filter_bytes(self, file_bytes: int):
        """过滤图片大小"""
        if file_bytes is None:
            return False
        if any(self.cfg_bytes):
            if file_bytes < self.cfg_bytes[0] or file_bytes > self.cfg_bytes[1]:
                self.logger.debug("filter_bytes_True: %s", file_bytes)
                return True

    def filter(self, result: tuple):
        """
        ArchOctopus 过滤器
        过滤图片尺寸, 类型以及文件大小。
        :param result:
        :return:
        """
        if not result:
            return
        else:
            tmp_file, file = result

        file_type: tuple = get_file_type(file)
        file_size: tuple = get_file_size(tmp_file)
        file_bytes = get_file_bytes(tmp_file)

        try:
            if self._filter_type(file_type[1]) or self._filter_size(file_size) or self._filter_bytes(file_bytes):
                self.logger.debug("过滤文件: %s", file)
                os.remove(tmp_file)
            else:
                os.rename(tmp_file, file)
        except (PermissionError, FileExistsError) as e:
            # os.remove(tmp_file)
            self.logger.error(e)

        return file_type, file_size, file_bytes

    @ retry(times=3)
    def _download(self, **kwargs):
        """
        下载函数
        :param path:
        :param url:
        :return: tuple(file_type, file_bytes, file_size, tmp_file)
        """
        url = kwargs["item_url"]
        # 链接内嵌图片 data:image, 暂做忽略处理。
        if url.startswith("data:image"):
            # self.embedded_img(url)
            return

        raw_name = kwargs.get("name")
        if raw_name:
            name, suffix = os.path.splitext(raw_name)
            suffix = suffix.lower() if suffix else ".jpeg"
        else:
            name, suffix = get_name_from_url(url)

        index = kwargs.get("item_index")
        name = f"{index}_{name}" if index else name

        folder = kwargs.get("task_dir", "")

        # 判断文件是否已存在
        is_downloaded_file = is_downloaded(folder, name, suffix=suffix)
        if is_downloaded_file:
            self.logger.debug("图片已下载: %s", is_downloaded_file)
            return

        # 请求响应内容
        tmp_file = os.path.join(folder, name + '.tmp')
        tmp_file_size = get_file_bytes(tmp_file)

        if tmp_file_size:
            self.logger.debug('tmp_file length: %s', tmp_file_size)
            headers = {'Range': f"bytes={tmp_file_size}-"}
        else:
            headers = None
        try:
            with self.session.stream("GET", url, headers=headers) as s:
                self.logger.debug("请求状态 : %s, %s", s.status_code, url)
                if s.status_code == 200:
                    mode = "wb"
                elif s.status_code == 206:
                    mode = "ab"
                elif s.status_code == 416:
                    self.logger.error("416 错误 – 所请求的范围无法满足: %s", url)
                    os.remove(tmp_file)
                    return
                else:
                    self.logger.error("响应码错误: %s, %s", s.status_code, url)
                    return

                with open(tmp_file, mode) as f:
                    for chunk in s.iter_bytes(chunk_size=10240):
                        if chunk:
                            f.write(chunk)
                    f.flush()

                # 获取正确的后缀名
                suffix = get_img_format(tmp_file)
                file = re.sub("\\.tmp$", suffix, tmp_file)
        except FileExistsError as e:
            self.logger.error("文件已存在: %s", e)
            os.remove(tmp_file)
        except FileNotFoundError as e:  # windows默认256个字符路径限制(MAX_PATH)
            self.logger.error("FileNotFoundError错误: %s", e)
        except AttributeError as e:
            self.logger.error("AttributeError错误: %s", e)
        else:
            return tmp_file, file

    def run(self):
        while self.running_event.is_set():
            self.pause_event.wait()  # 为True时立即返回, 为False时阻塞直到内部的标识位为True后返回
            data = self.queue.get()

            # 下载线程接受到退出信号,正常退出.
            if data is None:
                self.logger.info("download completed: 队列完成")
                self.queue.task_done()
                break

            # 下载前过滤
            item_size = data.get("size")
            item_bytes = data.get("bytes")

            if self._filter_size(item_size) or self._filter_bytes(item_bytes):
                self.queue.task_done()
                self.logger.info("download completed: %s", data["item_url"])
                wx.CallAfter(self.window.call_refresh_gauge, data["item_url"], None)  # 更新面板信息
                continue

            # 下载
            result = self._download(**data)

            # 下载后过滤
            filter_result = self.filter(result)
            wx.CallAfter(self.window.call_refresh_gauge, data["item_url"], filter_result)  # 更新面板信息

            self.queue.task_done()
            self.logger.info("download completed: %s", data["item_url"])

        # 退出时关闭请求连接
        self.session.close()
        # 更新任务线程计数
        wx.CallAfter(self.window.call_thread_done)
