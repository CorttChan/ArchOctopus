"""
ArchOctopus 通用工具
"""

import re
import os
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse, unquote
import base64
from io import BytesIO
import imghdr

import wx
from httpx import ProxyError, HTTPError, StreamError, InvalidURL, CookieConflict, TimeoutException


def get_docs_dir():
    """
    Return the standard location on this platform for application data.
    """
    sp = wx.StandardPaths.Get()
    return os.path.join(sp.GetDocumentsDir(), wx.GetApp().GetAppName())


def get_bitmap_from_embedded(data: bytes, scale: tuple = tuple(), isBase64: bool = True) -> wx.Bitmap:
    """
    从字节码中获取wx.Bitmap图片对象
    :param data:
    :param scale:
    :param isBase64:
    :return:
    """
    if isBase64:
        data = base64.b64decode(data)
    stream = BytesIO(data)
    image = wx.Image()
    image.SetLoadFlags(0)       # 忽略 'iCCP: known incorrect sRGB profile' 警告
    image.LoadFile(stream)
    if scale:
        image = image.Scale(*scale, quality=wx.IMAGE_QUALITY_BOX_AVERAGE)
    return wx.Bitmap(image)


def embedded_img(url):
    """从链接内嵌base64编码图片获取图片"""
    pat = re.compile("data:image/(?P<img_type>.*?);(?P<img_encoding>base64|utf8),(?P<img_content>.*?)$")
    result = pat.search(url).groupdict()
    # svg编码
    if result["img_type"] == "utf8":
        if result["img_type"] == "svg+xml":
            pass
    # base64编码
    elif result["img_type"] == "base64":
        pass


def cleanup(title):
    """
    替换非法字符
    :param title: 初始输入标题
    :return: 符合windows目录命名要求的标题
    """
    if not title:
        return title
    title = title.strip()
    replacements = [("&#34;|&quot;|&#39;|&apos;|&#60;|&lt;|&#62;|&gt;", "\'"), ("&#38;|&amp;", "&"),
                    ("&#8211;", "–"),
                    ('[/:*?"<>|\\\\]', '_'), ('_{2,}', '_'), ('\\s{2,}', ' ')]
    for _old, _new in replacements:
        title = re.sub(_old, _new, title)
    return title


def time_to_date(timestamp: int):
    """将时间戳转换为本地日期文本格式"""
    isofmt = "%Y-%m-%d %H:%M:%S"
    time_local = time.localtime(timestamp)
    return time.strftime(isofmt, time_local)


def utc_to_local(utc: str, fmt: str):
    """
    将标准时区格式转为本地日期文本格式
    :param utc: %Y-%m-%dT%H:%M:%S.%fZ
    :param fmt: date-format
    :return:
    """
    ts = time.time()
    utc_offset = int((datetime.fromtimestamp(ts) - datetime.utcfromtimestamp(ts)).total_seconds()/3600)
    # UTC_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
    utcTime = datetime.strptime(utc, fmt)
    localtime = utcTime + timedelta(hours=utc_offset)
    return localtime


def retry(times=3):
    """重试装饰器"""

    def retry_func(func):

        def request(self, *args, **kwargs):
            for i in range(times):
                try:
                    result = func(self, *args, **kwargs)
                except TimeoutException as e:       # 仅超时错误重试
                    self.logger.info("<请求次数 - %s>: %s", i, e)
                    time.sleep(1)
                except ProxyError as e:             # 单独捕捉代理错误
                    self.logger.info("ProxyError错误: %s", e)
                    break
                except (HTTPError, StreamError, InvalidURL, CookieConflict) as e:
                    self.logger.info("<请求次数: %s>网络请求错误: %s", i, e)
                    break
                else:
                    return result

        return request

    return retry_func


def is_downloaded(path, name, suffix=None) -> [str, None]:
    """判断图片文件是否已存在"""
    suffix = ".jpeg" if suffix == ".jpg" else suffix or ".jpeg"
    file = os.path.join(path, name+suffix)
    if os.path.isfile(file):
        return file


def get_file_type(file: str) -> tuple:
    """
    从文件路径获取文件名和后缀名
    :param file: 文件路径
    :return: tuple(name, suffix)
    """
    file_type = os.path.splitext(file)[-1].lower()
    file_name = os.path.basename(file)
    return file_name, file_type


def get_file_bytes(file) -> int:
    """获取文件大小"""
    if os.path.exists(file) and os.path.isfile(file):
        file_bytes = os.path.getsize(file)
    else:
        file_bytes = 0
    return file_bytes


def get_file_size(file) -> tuple:
    """获取文件尺寸大小"""
    image = wx.Image()
    image.SetLoadFlags(0)  # 屏蔽 'iCCP: known incorrect sRGB profile' Warning

    # True if the operation succeeded, False otherwise.
    # If the optional index parameter is out of range, False is returned and a call to wx.LogError takes place.
    # dummy_log = wx.LogNull() 避免弹出的wx.LogError引发的错误窗口
    dummy_log = wx.LogNull()
    if image.LoadFile(file):
        file_size = image.GetSize().Get()
    else:
        file_size = (0, 0)
    del dummy_log
    return file_size


def get_name_from_url(url: str) -> tuple:
    """
    从图片url连接获取文件名和后缀
    :param url: 图片url
    :return: tuple(name, suffix)
    """
    url_path = urlparse(url).path
    basename = os.path.basename(url_path)
    filename = os.path.splitext(unquote(basename))
    return filename[0], filename[1].lower()


def get_img_format(file: [str, bytes]) -> str:
    """获取图片类型"""
    if isinstance(file, str) and os.path.exists(file):
        suffix = imghdr.what(file)
    elif isinstance(file, bytes):
        suffix = imghdr.what(None, h=file)
    else:
        raise ValueError("参数错误: 文件路径字符串或文件字节bytes数据")

    suffix = "."+suffix if suffix else ".jpeg"
    return suffix


def gen_match_image(image: wx.Image, width: int, height: int) -> wx.Image:
    """
    居中缩放图片到指定尺寸
    :param image:
    :param width:
    :param height:
    :return:
    """
    raw_size = image.GetSize().Get()

    x_scale_factor = width / raw_size[0]
    y_scale_factor = height / raw_size[1]

    if raw_size[1] * x_scale_factor > height:
        new_size = (width, int(raw_size[1] * x_scale_factor))
        rect = wx.Rect(0, (new_size[1] - height)//2, width, height)
    elif raw_size[1] * x_scale_factor < height:
        new_size = (int(raw_size[0] * y_scale_factor), height)
        rect = wx.Rect((new_size[0] - width)//2, 0, width, height)
    else:
        new_size = (width, height)
        rect = wx.Rect(0, 0, width, height)
    scaled_image = image.Scale(*new_size, quality=wx.IMAGE_QUALITY_BOX_AVERAGE)
    match_image = scaled_image.GetSubImage(rect)
    return match_image


def gen_cover_image(files: tuple):
    """
    生成同步面板中Board封面图片
    :param files:
    :return:
    """
    if not tuple:
        return None

    # # GUI board_cover组件尺寸计算
    # gap = 2
    # size = (176, 126)
    #
    # part_01 = (size[0]*2//3 - gap, size[1], 0, 0)
    # part_02 = (size[0] - size[0]*2//3, (size[1]-gap)//2, size[0]*2//3, 0)
    # part_03 = (part_02[0], size[1]-part_02[1]-gap, part_02[2], part_02[1]+gap)

    part_01 = (115, 126, 0, 0)
    part_02 = (59, 62, 117, 0)
    part_03 = (59, 62, 117, 64)

    cover_img = wx.Image(176, 126)
    cover_img.Replace(0, 0, 0, 255, 255, 255)

    new_files = [None, None, None]
    for i, f in enumerate(files):
        new_files[i] = f

    for part, file in zip((part_01, part_02, part_03), new_files):
        if file is None or not os.path.isfile(file):
            match_image = wx.Image(*part[:2])
            match_image.Replace(0, 0, 0, 220, 220, 220)
        else:
            raw_img = wx.Image(file, wx.BITMAP_TYPE_ANY)
            if raw_img.IsOk():
                match_image = gen_match_image(raw_img, *part[:2])
            else:
                match_image = wx.Image(*part[:2])
                match_image.Replace(0, 0, 0, 200, 200, 200)
        cover_img.Paste(match_image, *part[2:])

    return wx.Bitmap(cover_img)


class UpdateCover(threading.Thread):
    """异步更新board封面,避免GUI载入时间过长和卡顿"""

    def __init__(self, parent, queue, con):
        super(UpdateCover, self).__init__()

        self.parent = parent
        self.queue = queue
        self.con = con

    def load_conver_files(self, board_id: int, site: str) -> tuple:
        sql = "SELECT sub_dir, name " \
              "From sync_items " \
              "WHERE board_id = ? AND site = ? AND state = 1 AND type IN ('.jpeg', '.png') " \
              "LIMIT 3"
        result = self.con.select(sql, (board_id, site))
        return result

    def run(self):
        while True:
            data = self.queue.get()
            if data is None:
                break
            board_panel_id, board_info = data
            cover_files = self.load_conver_files(board_info[0], board_info[1])
            cover_files = tuple(os.path.join(self.parent.sync_dir,
                                             board_info[1],
                                             cleanup(board_info[2]),
                                             item[0] or "",
                                             item[1])
                                for item in cover_files)
            cover_bitmap = gen_cover_image(cover_files)
            if cover_bitmap is None:
                continue
            wx.CallAfter(self.parent.call_update_cover, board_panel_id, cover_bitmap, (board_info[0], board_info[1]))


# if __name__ == '__main__':
#     app = wx.App()
#     app.MainLoop()
#     cover_bitmap = gen_cover_image(tuple())
#     cover_bitmap.SaveFile("cover.png", type=wx.BITMAP_TYPE_PNG)
