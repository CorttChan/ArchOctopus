#!/usr/bin/python3
# -*- coding: utf-8 -*-
# @Time    : 2026/2/8 05:09
# @Author  : CorttChan
# @Email   : cortt.me@gmail.com
# @File    : cli.py


from archoctopus.db import DataBase
from archoctopus.task import TasksManager
from archoctopus.utils import get_domain_from_url


SQL = {
    "get_history_id": "SELECT id FROM history WHERE url=?",
}


def cli(url):
    db = DataBase()
    result = db.read_one(SQL["get_history_id"], (url,))
    if result:
        task_id = result[0]

    else:
        domain, name, slug = get_domain_from_url(url)
        task_id = db.read_one(SQL["get_history_count"])[0] + 1

        db.write(SQL["insert_sites"], (domain, name, slug))
        db.write(SQL["insert_history"], (domain, url))

    TasksManager.get().task_create(task_id, url)
