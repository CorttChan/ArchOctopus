#!/usr/bin/python3
# -*- coding: utf-8 -*-
# @Time    : 2022/2/18 0:03
# @Author  : CorttChan
# @Email   : cortt.me@gmail.com
# @File    : usage_report.py

"""
匿名使用报告模块
"""

import uuid
import getpass
import threading
import logging

import httpx
import wx

from archoctopus.version import VERSION
from archoctopus.constants import APP_NAME, USAGE_API_URL


def _platform():
    platinfo = wx.PlatformInformation.Get()
    platform_name = platinfo.GetOperatingSystemFamilyName()
    platform_version = "{}.{}.{}".format(platinfo.GetOSMajorVersion(),
                                         platinfo.GetOSMicroVersion(),
                                         platinfo.GetOSMinorVersion())
    return platform_name, platform_version


def _unique_id():
    user_name = getpass.getuser()
    user_id = uuid.uuid3(uuid.NAMESPACE_DNS, user_name).hex
    return user_id


class Usage(threading.Thread):
    """使用统计"""

    def __init__(self, parent, *args, **kwargs):
        threading.Thread.__init__(self, *args, **kwargs)

        self.logger = logging.getLogger(APP_NAME)
        self.con = parent.con
        self.netloc = parent.netloc

    def _num_history(self):
        sql = "SELECT COUNT(id) FROM history"
        result = self.con.select_one(sql)
        return result[0]

    def _sync_status(self):
        sql = "SELECT DISTINCT site FROM sync_account"
        result = self.con.select(sql)
        status = [i[0] for i in result]
        return status

    def _top_history(self):
        sql = "SELECT domain, count(*) num from history GROUP by domain ORDER by num DESC LIMIT 10"
        result = self.con.select(sql)
        return result

    def _build_data(self):
        platform_name, platform_version = _platform()
        status = self._sync_status()
        usage_data = {
            "uniqueID": _unique_id(),
            "version": VERSION,
            "platformName": platform_name,
            "platformVersion": platform_version,
            "numHistory": self._num_history(),
            "sync": {
                "archdaily": "archdaily" in status,
                "huaban": "huaban" in status,
                "pinterest": "pinterest" in status
            },
            "netloc": self.netloc
        }
        return usage_data

    def run(self) -> None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:58.0) Gecko/20100101 Firefox/58.0',
        }
        try:
            data = self._build_data()
            r = httpx.post(USAGE_API_URL, headers=headers, json=data)
            self.logger.debug("status: %s", r.status_code)
            r.raise_for_status()
            self.logger.debug(r.text)
        except Exception as e:
            self.logger.error(str(e))
