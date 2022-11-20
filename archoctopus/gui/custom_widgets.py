"""
ArchOctopus 自定义Gui组件
    - MyBitmapToggleButton

"""

import os
import re
from typing import Union

import wx
import wx.adv
import wx.lib.mixins.listctrl as listmix


def resource_path(relative_path):
    base_path = wx.GetApp().get_resource_dir()
    return os.path.join(base_path, relative_path)


def svg_bitmap(name: str, width: int = 20, height: int = 20, colour: wx.Colour = None):
    svg_file = resource_path(name)
    with open(svg_file, 'rb') as f:
        svg_bytes = f.read()
    if colour:
        colour_hex = colour.GetAsString(flags=wx.C2S_HTML_SYNTAX)
        svg_bytes = re.sub(b"(fill=\")(#(?:[A-Fa-f0-9]{6}|[A-Fa-f0-9]{3}))(\")",
                           b"\\g<1>" + bytes(colour_hex, encoding="utf-8") + b"\\g<3>", svg_bytes, flags=re.I)

    svg_bundle = wx.BitmapBundle.FromSVG(data=svg_bytes, sizeDef=wx.Size(width, height))
    return svg_bundle


def get_bitmap(name: Union[str, tuple], size: tuple = None):
    if isinstance(name, tuple):
        bundle = [MyBitmap(i) for i in name]
        return wx.BitmapBundle.FromBitmaps(bundle)

    bitmap = MyBitmap(name)
    if size:
        image = bitmap.ConvertToImage().Scale(*size)
        bitmap = wx.Bitmap(image)
    return bitmap


class MyAnimation(wx.adv.Animation):
    def __init__(self, *args, **kwargs):
        dpi_scale_factor: float = wx.Display().GetScaleFactor()
        if dpi_scale_factor <= 1:
            anim_index = 0
        elif 1 < dpi_scale_factor < 2:
            anim_index = 1
        else:
            anim_index = 2
        try:
            kwargs["name"] = resource_path(kwargs["name"][anim_index])
        except KeyError:
            args = list(args)
            args[0] = resource_path(args[0][anim_index])
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

        self.AppendColumn(u"项目名", format=wx.LIST_FORMAT_LEFT, width=self.FromDIP(280))
        self.AppendColumn(u"文件数", format=wx.LIST_FORMAT_RIGHT, width=self.FromDIP(60))
        self.AppendColumn(u"网站", format=wx.LIST_FORMAT_LEFT, width=self.FromDIP(100))
        self.AppendColumn(u"日期", format=wx.LIST_FORMAT_LEFT)

        # 创建临时条目,获取item在不同dip情况下高度值,用于后续计算显示条目数
        item = wx.ListItem()
        item.SetId(0)
        self.InsertItem(item)
        self.item_height = self.GetItemRect(0).GetHeight()
        # 清除临时条目
        self.DeleteAllItems()
