"""
ArchOctopus pdf 模块
"""

import threading
import logging
import os

import pdfkit
import wx

from .readability import Readability


logger = logging.getLogger(__file__)

WK_PATH = "../bin/wkhtmltopdf.exe"
PDF_OPTIONS = {
    'encoding': 'utf-8',
    'footer-left': 'auto-generated by ArchOctopus',
    'footer-right': '[page] - [toPage]',
    'footer-font-size': '9',
    'disable-javascript': '',
    'load-error-handling': 'ignore',
    'load-media-error-handling': 'ignore',
    'quiet': ''
}
DEFAULT_CSS = "default.css"


def is_available() -> bool:
    """检测wkhtmltopdf"""
    # 判断执行文件是否存在
    if not os.path.exists(WK_PATH):
        return False
    # 判断文件是否正确
    ret = os.system(f"{WK_PATH} -V")
    if ret != 0:
        return False
    return True


class PDF(threading.Thread):
    """pdf output"""

    def __init__(self, raw_html, raw_url, output_dir, window=None):
        super(PDF, self).__init__()

        self.html = raw_html
        self.url = raw_url
        self.output_dir = output_dir
        self.window = window
        # ------ cfg ------
        self.is_preview = wx.GetApp().cfg.ReadBool("/General/pdf_preview", defaultVal=False)

        self.config = pdfkit.configuration(wkhtmltopdf=WK_PATH)

    def __call__(self, *args, **kwargs):
        pass

    def _readability(self):
        parser = Readability(raw_html=self.html, raw_url=self.url)
        status, html = parser.render()
        return status, html

    def run(self) -> None:
        if not is_available():
            if self.window:
                wx.CallAfter(wx.MessageBox,
                             "wkhtmltopdf执行文件未找到或已损坏。",
                             "PDF错误",
                             wx.OK | wx.ICON_ERROR,
                             parent=self.window)
            return

        status, html = self._readability()
        if not status:
            if self.window:
                wx.CallAfter(wx.MessageBox,
                             "页面阅读模式渲染失败, 该页面可能不支持阅读模式。",
                             "PDF错误",
                             wx.OK | wx.ICON_ERROR,
                             parent=self.window)
            return

        css = DEFAULT_CSS
        # 查找并载入用户自定义css样式表文件
        # Debug--预览解析结果
        if self.is_preview and self.window:
            wx.CallAfter(self.window.reader, html, css)
        try:
            pdfkit.from_string(
                input=html,
                output_path=self.output_dir,
                configuration=self.config,
                options=PDF_OPTIONS,
                css=css)
        except OSError as e:
            if self.window:
                wx.CallAfter(wx.MessageBox, e, "PDF错误", wx.OK | wx.ICON_ERROR, parent=self.window)