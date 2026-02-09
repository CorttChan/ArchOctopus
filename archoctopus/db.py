#!/usr/bin/python3
# -*- coding: utf-8 -*-
# @Time    : 2024/2/22 18:14
# @Author  : CorttChan
# @Email   : cortt.me@gmail.com
# @File    : db.py

import os
import threading
import sqlite3
import logging
from queue import Queue
from typing import List

from archoctopus.constants import APP_NAME

# ----------------------------------------------------------------------
SCHEMA_SQL = """
--
-- SQLiteStudio v3.4.4 生成的文件，周一 5月 20 22:54:04 2024
--
-- 所用的文本编码：System
--
PRAGMA foreign_keys = off;
BEGIN TRANSACTION;

-- 表：history
CREATE TABLE IF NOT EXISTS history (
    id        INTEGER UNIQUE
                      NOT NULL,
    name      TEXT,
    state     INTEGER NOT NULL
                      DEFAULT (0),
    site_id   INTEGER NOT NULL,
    date      TEXT    DEFAULT (datetime(CURRENT_TIMESTAMP, 'localtime') ) 
                      NOT NULL,
    url       TEXT    UNIQUE
                      NOT NULL,
    path      TEXT,
    total_num INTEGER DEFAULT (0),
    done_num  INTEGER DEFAULT (0),
    is_folder INTEGER DEFAULT (0),
    is_show   INTEGER DEFAULT (1),
    PRIMARY KEY (
        id
    ),
    FOREIGN KEY (
        site_id
    )
    REFERENCES sites (id) ON DELETE NO ACTION
                          ON UPDATE NO ACTION
);


-- 表：history_tag
CREATE TABLE IF NOT EXISTS history_tag (
    history_id INTEGER,
    tag_id     INTEGER,
    PRIMARY KEY (
        history_id,
        tag_id
    ),
    FOREIGN KEY (
        history_id
    )
    REFERENCES history (id) ON DELETE NO ACTION
                            ON UPDATE NO ACTION,
    FOREIGN KEY (
        tag_id
    )
    REFERENCES tags (id) ON DELETE NO ACTION
                         ON UPDATE NO ACTION
);


-- 表：items
CREATE TABLE IF NOT EXISTS items (
    id         INTEGER,
    history_id INTEGER,
    board_id   INTEGER,
    user_id    INTEGER,
    site_id    INTEGER,
    url        TEXT    NOT NULL,
    name       TEXT,
    state      INTEGER DEFAULT (1),
    path       TEXT,
    file_type  TEXT,
    file_size  INTEGER DEFAULT (0),
    width      INTEGER,
    height     INTEGER,
    PRIMARY KEY (
        id
    ),
    FOREIGN KEY (
        site_id
    )
    REFERENCES sites (id) ON DELETE NO ACTION
                          ON UPDATE NO ACTION
);


-- 表：sites
CREATE TABLE IF NOT EXISTS sites (
    id   INTEGER UNIQUE
                 NOT NULL,
    name TEXT    UNIQUE
                 NOT NULL,
    slug TEXT    NOT NULL,
    PRIMARY KEY (
        id
    )
);


-- 表：sync_account
CREATE TABLE IF NOT EXISTS sync_account (
    id          INTEGER,
    site_id     INTEGER,
    name        TEXT    NOT NULL,
    slug        TEXT,
    email       TEXT,
    url         TEXT,
    avatar_url  TEXT,
    avatar_data BLOB,
    registry_t  TEXT,
    update_t    TEXT,
    state       INTEGER NOT NULL
                        DEFAULT (1),
    PRIMARY KEY (
        id
    ),
    FOREIGN KEY (
        site_id
    )
    REFERENCES sites (id) ON DELETE NO ACTION
                          ON UPDATE NO ACTION
);


-- 表：sync_boards
CREATE TABLE IF NOT EXISTS sync_boards (
    board_id  INTEGER UNIQUE
                      NOT NULL,
    user_id   INTEGER,
    site_id   INTEGER,
    name      TEXT    NOT NULL,
    state     INTEGER DEFAULT (0),
    url       TEXT    NOT NULL,
    desc      TEXT,
    total     INTEGER DEFAULT (0),
    created_t TEXT,
    updated_t TEXT,
    PRIMARY KEY (
        board_id
    ),
    FOREIGN KEY (
        user_id
    )
    REFERENCES sync_account (id) ON DELETE NO ACTION
                                 ON UPDATE NO ACTION,
    FOREIGN KEY (
        site_id
    )
    REFERENCES sites (id) ON DELETE NO ACTION
                          ON UPDATE NO ACTION
);


-- 表：tags
CREATE TABLE IF NOT EXISTS tags (
    id  INTEGER UNIQUE
                NOT NULL,
    tag TEXT    UNIQUE
                NOT NULL,
    PRIMARY KEY (
        id
    )
);


-- 视图：sync_state
CREATE VIEW IF NOT EXISTS sync_state AS
    SELECT sites.slug,
           sync_account.state
      FROM sites
           INNER JOIN
           sync_account ON sites.id = sync_account.site_id
     ORDER BY sites.id;


-- 视图：top_sites
CREATE VIEW IF NOT EXISTS top_sites AS
    SELECT sites.slug,
           count(history.id) AS num
      FROM sites
           INNER JOIN
           history ON sites.id = history.site_id
     GROUP BY site_id
     ORDER BY num DESC
     LIMIT 10;


COMMIT TRANSACTION;
PRAGMA foreign_keys = on;
"""


INIT_TAGS_SQL = """
CREATE TABLE IF NOT EXISTS tags (
    id      INTEGER,
    tag     TEXT NOT NULL UNIQUE,
    PRIMARY KEY(id AUTOINCREMENT)
);
"""

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
);
"""

# history和tag的关联表
INIT_HISTORY_RELATED_TO_TAGS_SQL = """
CREATE TABLE IF NOT EXISTS history_related_tag (
    history_id          INTEGER,
    tag_id              INTEGER,
    PRIMARY KEY(history_id, tag_id)
);
"""

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
);
"""

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
);
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
);
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
);
"""


# ----------------------------------------------------------------------

logger = logging.getLogger(APP_NAME)


def dict_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(fields, row)}


class DataBase:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls, *args, **kwargs)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = False
        self._thread_local = threading.local()
        self._db_write_queue = Queue()
        self.db_path = ""

    @classmethod
    def close(cls):
        if isinstance(cls._instance, cls):
            cls._instance.db.close()

    @classmethod
    def get(cls):
        if cls._instance is None:
            raise NotImplementedError("DataBase Error!!")
        return cls._instance

    @property
    def db(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接"""
        if not hasattr(self._thread_local, "conn"):
            conn = sqlite3.connect(self.db_path, check_same_thread=True)
            self._thread_local.conn = conn

        return self._thread_local.conn

    def _execute(self):
        db = self.db
        while True:
            sql, params, script = self._db_write_queue.get()
            try:
                if script:
                    db.executescript(sql)
                else:
                    db.execute(sql, params)
                db.commit()
            except sqlite3.Error as e:
                logger.error("错误指令: %s", sql)
                logger.error(e, exc_info=True)

    def init(self, db_path: str = ":memory:"):
        if self._initialized:
            return

        self.db_path = db_path
        if not os.path.exists(db_path):
            self.db.executescript(SCHEMA_SQL)
            self.db.commit()

        db_write_thread = threading.Thread(target=self._execute, name="db_write_thread")
        db_write_thread.daemon = True
        db_write_thread.start()

        self._initialized = True

    def read(self, sql: str, params: tuple = ()) -> List[tuple]:
        result = self.db.execute(sql, params)
        return result.fetchall()

    def read_one(self, sql: str, params: tuple = ()) -> tuple:
        result = self.db.execute(sql, params)
        return result.fetchone()

    def read_dict(self, sql: str, params: tuple = ()) -> List[dict]:
        cur = self.db.cursor()
        cur.row_factory = dict_factory
        result = cur.execute(sql, params)
        return result.fetchall()

    def write(self, sql: str, params: tuple = (), script=False) -> None:
        self._db_write_queue.put((sql, params, script))
