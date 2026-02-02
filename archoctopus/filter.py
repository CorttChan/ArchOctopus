#!/usr/bin/python3
# -*- coding: utf-8 -*-
# @Time    : 2026/2/2 19:45
# @Author  : CorttChan
# @Email   : cortt.me@gmail.com
# @File    : filter.py

"""
文件过滤模块
"""

import os
import logging
from typing import Callable, List, Dict, Tuple

import wx       # TODO: 使用configparser库替换掉wx.FileConfig
from PIL import Image, UnidentifiedImageError

from archoctopus.constants import APP_NAME

logger = logging.getLogger(APP_NAME)


_filter_registry: Dict[str, Callable[[str], bool]] = {}


def register_filter(filter_name: str) -> Callable:
    """
    装饰器：注册过滤条件与对应的处理函数
    :param filter_name: 过滤条件名称（需唯一，与配置文件中的名称一致）
    :return: 装饰器函数
    """
    def decorator(func: Callable[..., bool]) -> Callable[..., bool]:
        if filter_name in _filter_registry:
            logger.warning(f"过滤条件 [{filter_name}] 已存在，将被新函数覆盖")
        _filter_registry[filter_name] = func
        logger.info(f"过滤条件 [{filter_name}] 注册成功")
        return func
    return decorator


@register_filter("image_type")
def filter_type(file, types: str) -> bool:
    file_type = file.split(".")[-1]
    if file_type in types.split(","):
        return True
    return False


@register_filter("image_size")
def filter_size(file, width, height) -> bool:
    try:
        image = Image.open(file)
    except (UnidentifiedImageError, FileNotFoundError):
        return True

    f_width, f_height = image.size
    if f_width < width or f_height < height:
        return True

    return False


@register_filter("file_size")
def filter_file_size(file, size) -> bool:
    try:
        f_size = os.path.getsize(file)
    except FileNotFoundError:
        return True

    if f_size < size:
        return True
    return False


class Filter:

    def __init__(self):
        self.active_filters: List[Tuple[Callable, Tuple]] = []

        cfg = wx.FileConfig.Get()

        width: int = cfg.ReadInt("/Filter/min_width", defaultVal=0)
        height: int = cfg.ReadInt("/Filter/min_height", defaultVal=0)
        size: int = cfg.ReadInt("/Filter/min_size", defaultVal=0)
        types: str = cfg.Read("/Filter/type", defaultVal="")

        if width or height:
            self.active_filters.append((_filter_registry["image_size"], (width, height)))
        if size:
            self.active_filters.append((_filter_registry["file_size"], (size,)))
        if types:
            self.active_filters.append((_filter_registry["image_type"], (types,)))

    def __call__(self, file) -> bool:
        is_filtered = any(func(file, *args) for func, args in self.active_filters)
        return is_filtered
