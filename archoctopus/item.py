#!/usr/bin/python3
# -*- coding: utf-8 -*-
# @Time    : 2026/1/24 23:56
# @Author  : CorttChan
# @Email   : cortt.me@gmail.com
# @File    : item.py


from typing import Dict, TypedDict, NotRequired


class ItemData(TypedDict):
    """
    解析对象类型: 字典类，其中必要项(name, url)
    """
    url:            str
    path:           str
    name:           NotRequired[str]
    sub_title:      NotRequired[str]
    index:          NotRequired[int]
    req:            NotRequired[str]
    req_url:        NotRequired[str]
    req_headers:    NotRequired[Dict]
    req_params:     NotRequired[str]
    is_abort:       NotRequired[bool]
    abort_msg:      NotRequired[str]
    index_reset:    NotRequired[bool]
    width:          NotRequired[int]
    height:         NotRequired[int]
    size:           NotRequired[int]
    type:           NotRequired[str]
