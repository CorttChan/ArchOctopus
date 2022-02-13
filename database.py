"""
AO数据库类
数据表:
1. history -- 历史任务表
2. tags -- 标签分类表
3. account -- 同步账户表
4. urls -- 历史图片表
5. ...
"""


import threading
import sqlite3
import logging
import os
from queue import Queue

from constants import APP_NAME

# ----------------------------------------------------------------------
INIT_TAGS_SQL = """
CREATE TABLE IF NOT EXISTS tags (
    id      INTEGER,
    tag     TEXT NOT NULL UNIQUE,
    PRIMARY KEY(id AUTOINCREMENT)
)"""

INIT_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS history (
    id                  INTEGER NOT NULL UNIQUE,
    name                TEXT DEFAULT '',
    status              INTEGER NOT NULL DEFAULT 0,
    date                TEXT NOT NULL DEFAULT (datetime(CURRENT_TIMESTAMP, 'localtime')),
    domain              TEXT DEFAULT '',
    url                 TEXT NOT NULL UNIQUE,
    dir                 TEXT DEFAULT '',
    total_count         INTEGER DEFAULT 100,
    download_count      INTEGER DEFAULT 0,
    is_folder           INTEGER DEFAULT 1,
    is_show             INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY(id AUTOINCREMENT)
)"""

# history和tag的关联表
INIT_HISTORY_RELATED_TO_TAGS_SQL = """
CREATE TABLE IF NOT EXISTS history_related_tag (
    history_id          INTEGER,
    tag_id              INTEGER,
    PRIMARY KEY(history_id, tag_id)
)"""

# status: 0 -- 未下载(默认值); 1 -- 已下载; 2 -- 被过滤; 3 -- 下载错误; 4 -- 重新下载
INIT_URLS_SQL = """
CREATE TABLE IF NOT EXISTS urls (
    "task_id"   INTEGER NOT NULL,
    "url"       INTEGER NOT NULL,
    "status"    INTEGER NOT NULL DEFAULT 0,
    "name"      TEXT,
    "sub_dir"   TEXT,
    "type"	    TEXT,
    "width"	    INTEGER,
    "height"	INTEGER,
    "bytes"	    INTEGER,
    PRIMARY KEY("task_id","url")
)"""

# ----------------------------------------------------------------------
INIT_ACCOUNT_SQL = """
CREATE TABLE IF NOT EXISTS "sync_account" (
    "user_id"	INTEGER NOT NULL,
    "site"	TEXT NOT NULL,
    "name"	TEXT,
    "slug"	TEXT,
    "email"	TEXT,
    "url"	TEXT,
    "avatar_url"	TEXT,
    "avatar_data"	BLOB,
    "registry_t"	TEXT,
    "update_t"	TEXT,
    PRIMARY KEY("user_id","site")
)
"""

INIT_SYNC_BOARDS_SQL = """
CREATE TABLE IF NOT EXISTS "sync_boards" (
    "board_id"	INTEGER NOT NULL,
    "user_id"	INTEGER NOT NULL,
    "site"	TEXT NOT NULL,
    "name"	TEXT,
    "url"	TEXT,
    "state"	INTEGER DEFAULT 1 CHECK("state" IN (0, 1)),
    "description"	TEXT,
    "total"	INTEGER,
    "created_t"	INTEGER,
    "updated_t"	INTEGER,
    PRIMARY KEY("board_id","site")
)
"""

INIT_SYNC_URLS_SQL = """
CREATE TABLE IF NOT EXISTS "sync_items" (
    "board_id"	INTEGER NOT NULL,
    "user_id"	INTEGER NOT NULL,
    "site"	TEXT NOT NULL,
    "name"	TEXT,
    "url"	TEXT NOT NULL,
    "state"	INTEGER DEFAULT 0 CHECK("state" IN (0, 1)),
    "sub_dir"	TEXT,
    "type"	TEXT,
    "width"	INTEGER,
    "height"	INTEGER,
    "bytes"	INTEGER,
    PRIMARY KEY("url","board_id")
)
"""


class AoDatabase(threading.Thread):

    def __init__(self, db=":memory:"):
        super(AoDatabase, self).__init__()
        self.logger = logging.getLogger(APP_NAME)

        self.db = db        # 如果未提供数据路径，则使用临时内存数据库
        self.autocommit = True
        self.reqs = Queue()  # 查询语句队列

        if os.path.exists(self.db) and os.path.isfile(self.db):
            self.con = sqlite3.connect(self.db,
                                       isolation_level=None,
                                       check_same_thread=False,
                                       detect_types=sqlite3.PARSE_DECLTYPES)
            self.cur = self.con.cursor()
        else:
            self.con = sqlite3.connect(self.db,
                                       isolation_level=None,
                                       check_same_thread=False,
                                       detect_types=sqlite3.PARSE_DECLTYPES)
            self.cur = self.con.cursor()

            self.cur.execute(INIT_TAGS_SQL)
            self.cur.execute(INIT_HISTORY_SQL)
            self.cur.execute(INIT_HISTORY_RELATED_TO_TAGS_SQL)
            self.cur.execute(INIT_URLS_SQL)

            self.cur.execute(INIT_ACCOUNT_SQL)
            self.cur.execute(INIT_SYNC_BOARDS_SQL)
            self.cur.execute(INIT_SYNC_URLS_SQL)

        self.setDaemon(True)
        self.start()

    def run(self):
        cursor = self.con.cursor()
        cursor.execute('PRAGMA synchronous=OFF')
        while True:
            req, arg, res = self.reqs.get()
            if req == '--close--':
                break
            elif req == '--commit--':
                self.con.commit()
            else:
                try:
                    cursor.execute(req, arg)
                except (sqlite3.OperationalError, sqlite3.IntegrityError, sqlite3.ProgrammingError, ValueError) as e:
                    self.logger.error("数据库错误: %s", e)
                    if res:
                        res.put(tuple())
                        res.put('--no more--')
                else:
                    if res:
                        for rec in cursor:
                            res.put(rec)
                        res.put('--no more--')
        self.con.close()

    def execute(self, req, arg=None, res=None):
        """
        `execute` calls are non-blocking: just queue up the request and return immediately.
        """
        self.reqs.put((req, arg or tuple(), res))

    def executemany(self, req, items):
        for item in items:
            self.execute(req, item)

    def select(self, req, arg=None):
        """
        Unlike sqlite's native select, this select doesn't handle iteration efficiently.

        The result of `select` starts filling up with values as soon as the
        request is dequeued, and although you can iterate over the result normally
        (`for res in self.select(): ...`), the entire result will be in memory.

        """
        res = Queue()   # results of the select will appear as items in this queue
        self.execute(req, arg, res)
        while True:
            rec = res.get()
            if rec == '--no more--':
                break
            yield rec

    def select_one(self, req, arg=None):
        """Return only the first row of the SELECT, or None if there are no matching rows."""
        try:
            return next(self.select(req, arg))
        except StopIteration:
            return None

    def on_commit(self):
        self.execute('--commit--')

    def on_close(self):
        self.execute('--close--')
