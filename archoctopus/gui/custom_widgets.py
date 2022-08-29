"""
ArchOctopus 自定义Gui组件
    - MyBitmapToggleButton

"""

import os
import re

import wx
import wx.adv
from wx.svg import SVGimage
import wx.lib.mixins.listctrl as listmix


def resource_path(relative_path):
    base_path = wx.GetApp().get_resource_dir()
    return os.path.join(base_path, relative_path)


def svg_bitmap(name: str, width: int = 20, height: int = 20, colour: wx.Colour = None):
    bmp_size = wx.Size(width, height)
    svg_file = resource_path(name)
    # Change svg color
    if colour:
        colour_hex = colour.GetAsString(flags=wx.C2S_HTML_SYNTAX)
        with open(svg_file, 'rb') as f:
            svg_bytes = f.read()
            svg_bytes = re.sub(b"(fill=\")(#(?:[A-Fa-f0-9]{6}|[A-Fa-f0-9]{3}))(\")",
                               b"\\g<1>" + bytes(colour_hex, encoding="utf-8") + b"\\g<3>", svg_bytes, flags=re.I)
        image = SVGimage.CreateFromBytes(svg_bytes)
    else:
        image = SVGimage.CreateFromFile(svg_file)
    bitmap = image.ConvertToScaledBitmap(bmp_size)

    return bitmap


def get_bitmap(name: str, size: tuple = None):
    bitmap = MyBitmap(name)
    if size:
        image = bitmap.ConvertToImage().Scale(*size)
        bitmap = wx.Bitmap(image)
    return bitmap


class MyAnimation(wx.adv.Animation):
    def __init__(self, *args, **kwargs):
        try:
            kwargs["name"] = resource_path(kwargs["name"])
        except KeyError:
            args = list(args)
            args[0] = resource_path(args[0])
        wx.adv.Animation.__init__(self, *args, **kwargs)


class MyBitmap(wx.Bitmap):
    def __init__(self, *args, **kwargs):
        try:
            kwargs["name"] = resource_path(kwargs["name"])
        except KeyError:
            args = list(args)
            args[0] = resource_path(args[0])
        wx.Bitmap.__init__(self, *args, **kwargs)


class BasePopupCtrl(wx.PopupTransientWindow):
    """wxGlade添加时会额外添加'style'关键字参数，而wx.PopupTransientWindow不支持此参数，所以在此先初始化此类."""

    def __init__(self, parent, *args, **kwargs):
        wx.PopupTransientWindow.__init__(self, parent, flags=wx.SIMPLE_BORDER | wx.PU_CONTAINS_CONTROLS)


class HistoryListCtrl(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin):
    """Download history display list ctrl"""

    def __init__(self, *args, **kwargs):
        wx.ListCtrl.__init__(self, *args, **kwargs)
        listmix.ListCtrlAutoWidthMixin.__init__(self)

        head_attr = wx.ItemAttr()
        head_attr.SetTextColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        self.SetHeaderAttr(head_attr)

        self.AppendColumn(u"项目名", format=wx.LIST_FORMAT_LEFT, width=280)
        self.AppendColumn(u"文件数", format=wx.LIST_FORMAT_RIGHT, width=60)
        self.AppendColumn(u"网站", format=wx.LIST_FORMAT_LEFT, width=80)
        self.AppendColumn(u"日期", format=wx.LIST_FORMAT_LEFT, width=80)
