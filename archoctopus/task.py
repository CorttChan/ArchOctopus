"""
ArchOctopus 任务管理模块

"Plugin" -- 插件化加载管理器:
    -- 根据url域名自动加载对应的解析类，同时保持已有解析类的缓存，在传入含相同域名的url参数时，可以直接调用。
"""

import queue
import weakref
import logging
import threading
from collections import UserDict
from queue import Queue, Full
from urllib.parse import urlparse, unquote
from enum import Enum
from typing import Optional, Callable, Tuple

import wx

from archoctopus.constants import APP_NAME
from archoctopus.download import Downloader
from archoctopus.db import DataBase
from archoctopus.parser import Parser
from archoctopus.plugin import Plugin
from archoctopus.filter import Filter


DOWNLOAD_THREAD_COUNT = 5

db = DataBase()

# SQL
SQL = {
    "task_start" : (),
    "task_completed": "UPDATE history SET status=?, done_num=?, total_num=? WHERE id=?",
    "task_parse_title": "UPDATE history SET name=?, path=? WHERE id=?",
    "task_parse_item": "INSERT INTO items (url, path, history_id) VALUES (?, ?, ?)",
    "task_parse_error": "",
    "task_parse_abort": "",
    "task_parse_finish": "UPDATE history SET total_num=? WHERE id=?",
    "task_download_filter": "",
    "task_download_success": "UPDATE items SET state=1, name=?, file_type=?, width=?, height=?, file_size=? WHERE url=? and history_id=?",
    "task_download_filtered": "",
    "task_download_failed": "",
    "task_download_finish": "",
}

logger = logging.getLogger(APP_NAME)


def get_hostname(url: str):
    """获取域名"""
    return unquote(urlparse(url).hostname)


class MyQueue(Queue):
    def __init__(self):
        super().__init__()
        self._flag = False

    def put(self, item, block = True, timeout = None):
        if self._flag and item is not None:
            raise Full("active quit")
        super().put(item, block=block, timeout=timeout)

    def set_full(self):
        self._flag = True


class State(Enum):
    # State
    PENDING = "pending"             # 项目状态 -- 等待中
    RUNNING = "downloading"         # 项目状态 -- 运行中
    PAUSED = "paused"               # 项目状态 -- 已暂停
    COMPLETED = "completed"         # 项目状态 -- 已完成
    CANCELLED = "cancelled"         # 项目状态 -- 已取消
    FAILED = "failed"               # 项目状态 -- 下载失败

    def __str__(self):
        return f"{self.name}"


class TaskInfo(UserDict):
    """任务信息类"""

    def __init__(self, task_id, url):
        super().__init__()
        self.data = dict(
            id=task_id,     # 任务id
            url=url,        # 任务url
            name=url,       # 任务名称
            status=0,       # 任务状态(0, 1)
            date="",        # 任务创建日期
            path="",        # 任务路径
            total_num=0,    # 任务解析总数
            done_num=0,     # 任务完成总数
            is_folder=0,    # 目录flag
            is_shown=1,     # 显示flag
            tag=[],         # 标签
            error=""        # 错误信息
        )

    def __setitem__(self, key, value):
        if key in ("id", "url"):
            print(f"id, url键值不可修改")
        if key in self.keys():
            super().__setitem__(key, value)
        else:
            print(f"此键值不存在 -- {key}")

    def __getitem__(self, key):
        if key not in self.keys():
            raise KeyError("")
        return super().__getitem__(key)

    @property
    def task_id(self):
        return self["id"]

    @property
    def url(self):
        return self["url"]


class Task:
    """任务类"""

    def __init__(self, task_id: int, url: str):
        self._state: State = State.PENDING
        self._id: int = task_id
        self._panel = None
        self._callback = None

        self.info = TaskInfo(task_id, url)
        self.url: str = url
        self.works = None
        self.event = None

    def clean(self):
        self.works = None
        self.event = None

    def __str__(self):
        return f"Task ({self._id}:({self.state}) -- {self.url})"

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, state):
        if state not in list(State):
            raise ValueError
        self._state = state

    @property
    def task_id(self):
        return self._id

    @property
    def panel(self):
        return self._panel

    @panel.setter
    def panel(self, panel: wx.Panel):
        self._panel = weakref.proxy(panel)

    def set_done_callback(self, callback: Callable[[int], None]):
        self._callback = callback

    def call_msg(self, msg_type: str, msg: tuple) -> None:
        logger.info("消息类型: %s, \n消息参数: %s", msg_type, msg)

        default = lambda x: logger.error("处理函数不存在: %s", msg_type)
        func = getattr(self, f"_on_{msg_type}", default)
        func(msg)

        try:
            func = getattr(self.panel, f"_call_{msg_type}", default)
            wx.CallAfter(func, self.info)
        except ReferenceError:
            logger.error("目标对象已被垃圾回收")
        except AttributeError:
            logger.error("CLI模式")

    def _on_task_completed(self, msg: tuple) -> None:
        """

        :param msg: (total_num, )
        :return:
        """
        self.state = State.COMPLETED
        self.info["total_num"] = msg[0]
        if self.info["total_num"] == 0:
            logger.info("任务解析结果为0.")
        elif self.info["total_num"] != self.info["done_num"]:
            logger.info("任务下载失败, 未能完整下载全部图片")
        else:
            self.info["status"] = 1

        db.write(SQL["task_completed"], (self.info["status"], self.info["done_num"], self.info["total_num"], self.info["url"]))

        if self._callback:
            self._callback(self.task_id)

    def _on_task_start(self, msg: tuple) -> None:
        pass

    def _on_task_parse_title(self, msg: tuple) -> None:
        """
        任务解析: 任务路径, 任务标题
        :param msg: (task_name, task_path)
        :return:
        """
        self.info.update({"name": msg[0], "path": msg[1]})
        db.write(SQL["task_parse_title"], (*msg, self.task_id))

    def _on_task_parse_item(self, msg: tuple) -> None:
        """
        任务解析: 解析完成条目，
        :param msg: (item_url, item_dir)
        :return:
        """
        self.info["total_num"] += 1
        db.write(SQL["task_parse_item"], (*msg, self.task_id))

    def _on_task_parse_finish(self, msg: tuple) -> None:
        """

        :param msg: (total_num, )
        :return:
        """
        db.write(SQL["task_parse_finish"], (*msg, self.task_id))

    def _on_task_download_success(self, msg: tuple) -> None:
        """

        :param msg: (file_name, file_type, file_width, file_height, file_bytes, item_url)
        :return:
        """
        self.info["done_num"] += 1
        db.write(SQL["task_download_success"], (*msg, self.task_id))

    def _on_task_download_filtered(self, msg: Tuple) -> None:
        pass
        # db.write(SQL["task_download_filter"], (*msg, self.task_id))

    def _on_task_download_failed(self, msg: Tuple) -> None:
        pass

    def _on_task_download_finish(self, msg: Tuple) -> None:
        pass


class TasksManager:
    """
    任务管理器 - 管理任务调度, 任务解析, 任务下载, 任务消息, 任务状态等
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not isinstance(cls._instance, cls):
            cls._instance = super(TasksManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, max_workers=5, parser=Parser, downloader=Downloader):
        self.tasks = dict()
        self.messages = Queue()
        self.db = DataBase()

        self.max_workers: int = max_workers
        self.parser = parser
        self.downloader = downloader

        msg_handle_thread = threading.Thread(target=self._msg_handle, name="msg_handle_thread")
        msg_handle_thread.daemon = True
        msg_handle_thread.start()

    def _msg_handle(self):
        while True:
            msg_type, msg, task_id = self.messages.get()
            task: Task = self.get_task(task_id)
            task.call_msg(msg_type, msg)

    def _running_num(self) -> int:
        """查询正在运行任务数"""
        num = 0
        for i in self.tasks.values():
            if i.state is State.RUNNING:
                num += 1
        return num

    def _tasks_num(self) -> int:
        """任务总数"""
        return len(self.tasks)

    def _on_task_done(self, task_id: int):
        task = self.get_task(task_id)
        task.clean()
        self._run()

    def _start(self, task) -> None:
        hostname = get_hostname(task.url)

        task.works = MyQueue()
        task.event = threading.Event()
        task.event.set()

        parse_thread = self.parser(task.url,
                                   task.task_id,
                                   task.works,
                                   self.messages,
                                   task.event,
                                   cookies=None,
                                   extractor=Plugin(name=hostname))
        parse_thread.daemon = True
        parse_thread.start()

        item_filter = Filter()
        for i in range(DOWNLOAD_THREAD_COUNT):
            _download_thread = self.downloader(task.task_id,
                                               task.works,
                                               self.messages,
                                               task.event,
                                               item_filter=item_filter,
                                               cookies=None,)
            _download_thread.name = f"{task.task_id}--{i}"
            _download_thread.daemon = True
            _download_thread.start()

        task.state = State.RUNNING

    @classmethod
    def get(cls):
        if cls._instance is None:
            raise NotImplementedError("TasksManager Error!!")
        return cls._instance

    def _run(self) -> None:
        if self._running_num() < self.max_workers:
            for i in sorted(self.tasks.keys()):
                task: Task = self.tasks[i]
                if task.state is State.PENDING:
                    self._start(task)
                    break

    def task_create(self, task_id, url, panel=None) -> None:
        if task_id in self.tasks:
            task = self.tasks[task_id]
            if task.panel is None:
                task.panel = panel
        else:
            task = Task(task_id, url)
            task.panel = panel
            task.set_done_callback(self._on_task_done)
            self.tasks[task_id] = task
        self._run()

    def task_start(self, task_id) -> bool:
        task = self.get_task(task_id)
        if task.state is State.RUNNING:
            logger.error("任务状态错误")
            return False
        if self._running_num() >= self.max_workers:
            logger.error("运行数已满")
            return False
        self._start(task)
        return True

    def task_cancel(self, task_id) -> None:
        task = self.get_task(task_id)
        if task is None:
            logger.info("任务管理器不存在该任务.")
        else:
            if task.state is State.PAUSED:
                task.event.set()
                task.state = State.RUNNING

            if task.state is State.RUNNING:
                task.works.set_full()
                while not task.works.empty():
                    try:
                        task.works.get(block=False)
                    except queue.Empty:
                        continue
                    task.works.task_done()

            task.state = State.CANCELLED
            task.clean()
            self._run()

    def task_pause(self, task_id) -> None:
        task = self.get_task(task_id)
        if task.state is State.RUNNING:
            task.event.clear()
            task.state = State.PAUSED
        else:
            logger.error("任务状态错误,当前状态: %s", task.state)

    def task_resume(self, task_id) -> None:
        task = self.get_task(task_id)
        if task.state is State.PAUSED:
            if self._running_num() < self.max_workers:
                task.event.set()
                task.state = State.RUNNING
            else:
                logger.error("当前运行数已达到最大运行数,无法继续启动任务, id: %s", task_id)
        else:
            logger.error("任务状态错误,当前状态: %s", task.state)

    def get_task(self, task_id: int) -> Optional[Task]:
        task = self.tasks.get(task_id, None)
        if task is None:
            logger.debug(f"任务未找到. id: {task_id}")
        return task

    def print_tasks(self) -> None:
        for t in self.tasks.values():
            print(t)

    def is_all_completed(self) -> bool:
        return all(map(lambda x: x.state is not State.RUNNING, self.tasks.values()))
