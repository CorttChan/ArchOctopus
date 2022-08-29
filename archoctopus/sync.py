"""
ArchOctopus 同步模块
    SyncDownload -- 后台同步下载类
    Account -- 账户类
    AoSync -- 同步类

AoSync类初始化后自动开始检测指定的账户(_preload方法),判断系统浏览器是否登录,
并获取登录的账户信息,用于同步面板GUI显示信息.

同步启动后由GUI定时执行(默认间隔时间10*60000ms)_parser方法线程, 获取账户的画板、图片等信息.
在解析方法线程启动后延时一段时间(默认间隔60000ms)后, 执行后台下载线程.

延时执行是为了避免解析线程未完成时, 下载线程没有获取到有效数据推出后, 需要等待一个定时循环的时间.
"""

import re
import os
import threading
import logging
from http.cookiejar import CookieJar
from typing import Generator
import json
import base64
import time
from urllib.parse import urljoin

import wx
from bs4 import BeautifulSoup
from httpx import Client
from httpx import ProxyError, HTTPError, StreamError, InvalidURL, CookieConflict

import utils
import cookies

from database import AoDatabase


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:58.0) Gecko/20100101 Firefox/58.0',
}


class SyncDownload(threading.Thread):
    """账户同步下载器"""

    def __init__(self,
                 browser_cookies: CookieJar,
                 con: AoDatabase,
                 running_event: threading.Event,
                 sync_dir: str):
        super(SyncDownload, self).__init__()

        self.logger = logging.getLogger("sync")
        self.con = con
        self.running_event = running_event
        self.sync_dir = sync_dir
        self.session = Client(headers=HEADERS, cookies=browser_cookies)

    def _download(self, *args):
        """
        下载函数
        :param path:
        :param url:
        :return: tuple(file_type, file_bytes, file_size, tmp_file)
        """
        board_id, site, raw_name, url, sub_dir, board_name = args

        if raw_name:
            name, suffix = os.path.splitext(raw_name)
            suffix = suffix.lower() if suffix else ".jpeg"
        else:
            name, suffix = utils.get_name_from_url(url)
        folder = os.path.join(self.sync_dir, site.capitalize(), utils.cleanup(board_name), sub_dir or "")
        # 创建路径
        os.makedirs(folder, exist_ok=True)
        tmp_file = os.path.join(folder, name+'.tmp')

        # 判断文件是否已存在
        is_downloaded_file = utils.is_downloaded(folder, name, suffix=suffix)
        if is_downloaded_file:
            self.logger.debug("图片已下载: %s", is_downloaded_file)
            suffix = ".jpeg" if suffix == ".jpg" else suffix or ".jpeg"
            result = {"type": suffix, "name": name+suffix}
            return result

        # 请求响应内容
        tmp_file_size = utils.get_file_bytes(tmp_file)
        if tmp_file_size:
            self.logger.debug('tmp_file length: %s', tmp_file_size)
            headers = {'Range': f"bytes={tmp_file_size}-"}
        else:
            headers = None
        try:
            with self.session.stream("GET", url, headers=headers) as s:
                self.logger.info("请求状态 : %s, %s", s.status_code, url)
                if s.status_code == 200:
                    mode = "wb"
                elif s.status_code == 206:
                    mode = "ab"
                elif s.status_code == 416:
                    self.logger.error("416 错误 – 所请求的范围无法满足: %s", url)
                    os.remove(tmp_file)
                    return
                else:
                    raise ValueError("响应码错误: {}, {}".format(s.status_code, url))

                with open(tmp_file, mode) as f:
                    for chunk in s.iter_bytes(chunk_size=10240):
                        if chunk:
                            f.write(chunk)
                    f.flush()

                suffix = utils.get_img_format(tmp_file)
                file_path = re.sub("\\.tmp$", suffix, tmp_file)
                os.rename(tmp_file, file_path)
        except PermissionError as e:
            self.logger.error("权限错误: %s, %s", e, tmp_file)
        except FileExistsError as e:
            self.logger.error("文件已存在: %s", e)
            os.remove(tmp_file)
            result = {"type": suffix, "name": os.path.basename(file_path)}
            return result
        except FileNotFoundError as e:  # windows默认256个字符路径限制(MAX_PATH)
            self.logger.error("FileNotFoundError错误: %s", e)
        except ValueError as e:
            self.logger.error(e)
        except ProxyError as e:
            self.logger.info("ProxyError错误: %s", e)
        except (HTTPError, StreamError, InvalidURL, CookieConflict) as e:
            self.logger.error("网络请求错误: %s", e)
        except Exception as e:
            self.logger.error(e)
        else:
            result = {"type": suffix, "name": os.path.basename(file_path)}
            return result

    def run(self) -> None:
        select_sql = "SELECT " \
                     "sync_items.board_id, sync_items.site, sync_items.name, " \
                     "sync_items.url, sync_items.sub_dir, sync_boards.name " \
                     "FROM sync_items " \
                     "INNER JOIN sync_boards " \
                     "ON sync_items.board_id = sync_boards.board_id AND sync_items.site = sync_boards.site " \
                     "WHERE sync_items.state = 0 " \
                     "LIMIT 1 OFFSET ?"
        update_sql = "UPDATE sync_items SET name=?, state = 1, type = ? WHERE board_id = ? AND url = ?"

        # 通过比对前一次运行的item与本次查询的item的主键值,避免在某个出错的item上出现死循环.
        # 如果相同,说明此item在上次运行中已失败,则将查询参数offset+=1,获取下一个查询结果.
        # 如果不同,说明运行成功.
        pre_key = None
        offset = 0
        item_data = self.con.select_one(select_sql, (offset, ))
        while item_data and self.running_event.is_set():
            primary_key = (item_data[0], item_data[3])
            if primary_key == pre_key:
                offset += 1
            else:
                result = self._download(*item_data)
                if result:
                    self.con.execute(update_sql, (result.get("name"), result.get("type"), item_data[0], item_data[3]))
            pre_key = primary_key
            item_data = self.con.select_one(select_sql, (offset, ))
        # 退出时关闭请求连接
        self.session.close()


class AccountError(Exception):
    pass


class Account:
    """
    同步账户基类
    """
    def __init__(self, browser_cookies: CookieJar, con: AoDatabase):
        self.logger = logging.getLogger("sync")
        self.con = con or wx.GetApp().con
        self.session = Client(headers=HEADERS, cookies=browser_cookies)

        self.site = str()
        self.user_info = dict()
        self.is_connected = False

    def __str__(self):
        return self.site.capitalize()

    def _update_account_db(self):
        """更新sync_account表"""
        sql = "SELECT * FROM sync_account WHERE user_id = ? AND site = ?"
        exist_account = self.con.select_one(sql, (self.user_info["user_id"], self.user_info["site"],))

        if not exist_account or self.user_info["avatar_url"] != exist_account[6]:
            avatar_data = self._get_account_avatar()
        else:
            avatar_data = exist_account[7]

        if exist_account:
            sql = "UPDATE sync_account SET name =?, slug = ?, email = ?, url = ?, " \
                  "avatar_url = ?, avatar_data = ?, update_t = ? " \
                  "WHERE user_id = ? AND site = ?"
            info = (self.user_info["name"], self.user_info["slug"], self.user_info["email"], self.user_info["url"],
                    self.user_info["avatar_url"], avatar_data, self.user_info["update_t"], self.user_info["user_id"],
                    self.user_info["site"])
        else:
            sql = "INSERT INTO sync_account " \
                  "(user_id, site, name, slug, email, url, avatar_url, avatar_data, registry_t, update_t) " \
                  "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            info = (self.user_info["user_id"], self.user_info["site"], self.user_info["name"], self.user_info["slug"],
                    self.user_info["email"], self.user_info["url"], self.user_info["avatar_url"], avatar_data,
                    self.user_info["registry_t"], self.user_info["update_t"])
        self.con.execute(sql, arg=info)

    def _update_boards_db(self, board: dict):
        """更新sync_boards表"""
        sql = "INSERT OR REPLACE INTO " \
              "sync_boards (board_id, user_id, site, name, url, state, description, total, created_t, updated_t) " \
              "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        info = (board.get(k) for k in ("board_id", "user_id", "site", "name", "url", "state",
                                       "description", "total", "created_t", "updated_t"))
        self.con.execute(sql, arg=tuple(info))

    def _update_items_db(self, item: dict):
        """更新sync_items表"""
        sql = "INSERT OR IGNORE INTO " \
              "sync_items (board_id, user_id, site, name, url, sub_dir, type, width, height, bytes) " \
              "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        info = (item.get(k) for k in ("board_id", "user_id", "site", "name", "url",
                                      "sub_dir", "type", "width", "height", "bytes"))
        self.con.execute(sql, arg=tuple(info))

    def _get_account_avatar(self):
        """获取avatar_data"""
        url = self.user_info["avatar_url"]
        if not url:
            return None
        response = self.session.get(self.user_info["avatar_url"])
        response.raise_for_status()
        avatar_data = base64.b64encode(response.content)
        return avatar_data

    def login(self) -> dict:
        """
        账户登录
        :return: dict(is_connected=bool, raw_user_info=dict)
        """
        raise NotImplementedError

    def get_user_info(self, raw_user_info) -> dict:
        raise NotImplementedError

    def get_boards(self) -> Generator:
        raise NotImplementedError

    def get_board_info(self, board: dict) -> dict:
        """
        从原始响应内容中提取board信息
        :param board:
        :return:
        """
        raise NotImplementedError

    def get_items(self, board) -> Generator:
        raise NotImplementedError

    def get_item_info(self, item_data: dict) -> dict:
        """
        从原始响应内容中提取item信息
        :param item_data:
        :return:
        """
        item_info = dict()
        item_info["board_id"] = item_data.get("board_id")
        item_info["user_id"] = self.user_info.get("user_id")
        item_info["site"] = self.site
        item_info["name"] = item_data.get("name")
        item_info["url"] = item_data.get("url")
        item_info["sub_dir"] = item_data.get("sub_dir")
        item_info["type"] = item_data.get("type")
        item_info["width"] = item_data.get("width", 0)
        item_info["height"] = item_data.get("height", 0)
        item_info["bytes"] = item_data.get("bytes", 0)

        return item_info

    def run(self, preload=False):
        try:
            result = self.login()
            self.is_connected = result["is_connected"]
            if not self.is_connected:
                raise AccountError("账户无法连接")
            self.user_info = self.get_user_info(result["raw_user_info"])
            self.logger.debug("user_info: %s", self.user_info)
            self._update_account_db()
            if preload:      # 后台尝试读取账户信息
                self.logger.info("%s: preload finished.", self.site)
                return
            for board in self.get_boards():
                board_info = self.get_board_info(board)
                self._update_boards_db(board_info)
                for item in self.get_items(board):
                    item_info = self.get_item_info(item)
                    self._update_items_db(item_info)
        except Exception as e:
            self.logger.error("%s: %s", self.site, e, exc_info=True)


class Archdaily(Account):

    def __init__(self, *args, **kwargs):
        Account.__init__(self, *args, **kwargs)
        self.site = "archdaily"

        # 账户请求信息
        self.home_url = "https://www.archdaily.cn/cn"
        self.account_url = "https://www.archdaily.cn/cn/accounts/profile?site=cn&minimal=true"      # account_cn
        # self.account_url = "https://www.archdaily.cn/cn/accounts/profile/"      # account_cn
        # self.account_url = "https://www.archdaily.com/accounts/profile/"        # account_us
        self.csrf_token = ""

    @staticmethod
    def _get_csrf(response):
        html = response.text
        html_bs = BeautifulSoup(html, 'lxml')
        meta = html_bs.find("meta", attrs={"name": "csrf-token"})
        if meta:
            return meta.get("content")

    @staticmethod
    def url_replace(url):
        return re.sub(r'thumb_jpg|newsletter|medium_jpg', 'large_jpg', url)

    @staticmethod
    def tag_map(tag):
        if tag.name == 'a':
            tag = tag.img
        return tag['data-src'] if tag.has_attr('data-src') else tag['src']

    @staticmethod
    def filter_tags(tag):
        attr_classes = {'a': ('gallery-thumbs-link', 'thumbs__link', 'js-image-size__link', 'js-image-size'),
                        'img': ('b-lazy', 'nr-image', 'nr-picture')}
        if tag.name in attr_classes.keys():
            tag_class_attr = tag.get('class')
            return tag_class_attr and any(_i in tag_class_attr for _i in attr_classes[tag.name])

    def _article(self, response, board_id, title=""):
        """解析普通页面"""
        html = response.text
        html_bs = BeautifulSoup(html, 'lxml')
        pic_gallery = html_bs.find_all(self.filter_tags)
        urls = map(self.tag_map, pic_gallery)

        for url in urls:
            item_data = {
                "board_id": board_id,
                "sub_dir": title,
                "url": self.url_replace(url),
            }
            yield item_data

    def _gallery(self, response, board_id, title=""):
        """解析画廊页面"""
        html = response.text
        pat = "<meta property=\"og:image\" content=\"(.*?)\""
        single_pic = re.search(pat, html).group(1)

        item_data = {
            "board_id": board_id,
            "sub_dir": title,
            "url": self.url_replace(single_pic),
        }
        yield item_data

    @staticmethod
    def _utc_to_local(utc: str) -> [str, None]:
        # 原始格式:(ISO-Format): 2018-12-20T05:40:34.000Z
        dt = wx.DateTime()
        localtime = None
        if dt.ParseISOCombined(utc[:-5]):  # 解析格式"YYYY-MM-DDTHH:MM:SS", 不包含时区
            dt.MakeFromTimezone(wx.DateTime.TimeZone())  # 修正时区
            localtime = dt.Format(format="%Y-%m-%d %H:%M:%S")
        return localtime

    @utils.retry(times=3)
    def login(self):
        """
        登录
        :return: dict(is_connected=bool, raw_user_info=dict)
        full_info: .\\archdaily_json\\full_account.json
        mini_info: .\\archdaily_json\\mini_account.json
        """

        result = {
            "is_connected": False,
        }

        response = self.session.request("GET", self.home_url)
        self.csrf_token = self._get_csrf(response)
        self.logger.debug("csrf_token: %s", self.csrf_token)
        headers = {
            'Referer': self.home_url,
            'X-CSRF-Token': self.csrf_token,
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:58.0) Gecko/20100101 Firefox/58.0',
        }
        # params = {'site': 'cn', 'minimal': 'true'}     # mini_account.json
        # params = {'site': 'cn'}      # full_account.json
        self.logger.debug("post_header: %s", headers)
        response = self.session.request("POST", self.account_url, headers=headers)
        response.raise_for_status()
        raw_user_info = response.json()

        if raw_user_info is None:
            raise AccountError("登录失败")

        result["raw_user_info"] = raw_user_info
        result["is_connected"] = True
        return result

    def get_user_info(self, raw_user_info: dict) -> dict:
        """
        :param raw_user_info:
        :return:
        """
        self.logger.debug("raw_user_info: %s", raw_user_info)
        user_info = {
            "user_id": raw_user_info.get("id"),
            "site": self.site,
            "name": raw_user_info.get("full_name"),
            "slug": self.user_info.get("slug"),
            "email": raw_user_info.get("email"),
            "url": "https://my.archdaily.cn/cn/@{}/folders".format(self.user_info.get("slug")),
            "avatar_url": raw_user_info.get("avatar"),
            # wxpython wx.Locale设置导致local无法正常解析格式化时间字符串
            # "registry_t": utils.utc_to_local(raw_user_info.get("accepted_at"), fmt="%Y-%m-%dT%H:%M:%S.%fZ"),
            "registry_t": self._utc_to_local(raw_user_info.get("accepted_at")),
            "update_t": utils.time_to_date(raw_user_info.get("updated_at"))
        }
        return user_info

    def get_boards(self):
        """
        获取收藏夹信息
        :return:
        """
        url = "https://my.archdaily.cn/cn/"

        # 正常重定向到用户链接: https://my.archdaily.cn/cn/{@user_name}
        # 失败重定向到登录链接: https://my.archdaily.cn/cn/signin?redirect_to=https%3A%2F%2Fmy.archdaily.cn%2Fcn%2F
        # response = self.session.request("GET", url, follow_redirects=False)
        response = self.session.request("GET", url)
        redirect_url = response.headers.get("location")     # 获取重定向url
        self.logger.debug("重定向链接: %s", redirect_url)

        if re.search("/signin", redirect_url):
            raise AccountError("登录信息过期, 请重新在浏览器上登录后继续.")
        if not re.search("@", redirect_url):
            raise AccountError("获取收藏夹信息出错.")

        # 获取
        slug = re.search("@(.*)$", redirect_url).group(1)
        # 更新slug
        if slug and slug != self.user_info["slug"]:
            self.user_info["slug"] = slug
            self.con.execute("UPDATE sync_account SET slug = ?, url = ? WHERE user_id = ? AND site = ?",
                             (slug, f"https://my.archdaily.cn/cn/@{slug}/folders",
                              self.user_info["user_id"], self.site))

        api_url = "https://my.archdaily.cn/@{}/folders".format(slug)

        headers = {
            'Referer': api_url,
            'X-CSRF-Token': self.csrf_token,
            'Accept': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:58.0) Gecko/20100101 Firefox/58.0',
        }
        page = 0
        while True:
            page += 1
            params = {"page_info": True, "per_page": 14, "page": page}
            response = self.session.request("GET", api_url, headers=headers, params=params)
            self.logger.debug("%s - status_code: %s", response.url, response.status_code)
            response_json = response.json()
            page_json = response_json["data"]
            for board in page_json:
                yield board
            # 退出条件
            is_last_page = response_json["pagination"]["last_page"]
            if is_last_page:
                break

    def get_board_info(self, board: dict) -> dict:
        board_data = {
            "board_id": board.get("id"),
            "user_id": self.user_info.get("user_id"),
            "site": self.site,
            "name": board["name"],
            "url": board["url"]["cn"],
            "state": 1 if board.get("state") == "open" else 0,  # 0: 私密; 1: 公开
            "description": board.get("description"),
            "total": len(board.get("favs")),
            "created_t": self._utc_to_local(board.get("created_at")),
            "updated_t": self._utc_to_local(board.get("updated_at"))
        }
        return board_data

    def get_items(self, board) -> Generator:
        for fav in board["favs"]:
            response = self.session.request("GET", fav["url"])
            title = utils.cleanup(fav["title"])
            if fav["meta_type"] == "Photo":
                yield from self._gallery(response, board_id=board["id"], title=title)
            else:
                yield from self._article(response, board_id=board["id"], title=title)


class Pinterest(Account):

    def __init__(self, *args, **kwargs):
        Account.__init__(self, *args, **kwargs)
        self.site = "pinterest"

        # 账户信息
        self.home_url = "https://www.pinterest.com/"
        self.account_url = "https://www.pinterest.com/resource/UserResource/get/"
        self.board_url = "https://www.pinterest.com/resource/BoardsResource/get/"
        self.pin_url = "https://www.pinterest.com/resource/BoardFeedResource/get/"

    @staticmethod
    def _build_get_params(options, source_url="/", context=None):
        if context is None:
            context = {}
        params = (
            ("source_url", source_url),
            ("data", json.dumps({'options': options, "context": context})),
            ("_", '%s' % int(time.time() * 1000))
        )
        return params

    @staticmethod
    def _utc_to_local(utc: str) -> [str, None]:
        # 原始格式:(RFC822-Format): Wed, 01 Apr 2015 03:38:16 +0000
        dt = wx.DateTime()
        localtime = None
        if dt.ParseRfc822Date(utc):  # 解析格式"Sat, 18 Dec 1999 00:48:30 +0100", 包含时区
            # dt.MakeFromTimezone(wx.DateTime.TimeZone())  # 不需要修正时区
            localtime = dt.Format(format="%Y-%m-%d %H:%M:%S")
        return localtime

    def login(self) -> dict:
        result = {
            "is_connected": False,
        }

        response = self.session.request("GET", self.home_url)
        html = response.text
        html_bs = BeautifulSoup(html, 'lxml')

        pws_data = html_bs.find("script", id="__PWS_DATA__")
        pws_data_json = json.loads(pws_data.get_text())

        # 调试片段
        # with open("pinterest_login.json", 'w', encoding="utf-8") as f:
        #     f.write(pws_data.get_text())

        if not pws_data_json.get("isAuthenticated"):
            raise AccountError(f"登录失败: {self.home_url}")

        # try:
        #     raw_user_info = pws_data_json["props"]["initialReduxState"]["viewer"]
        # except KeyError:
        #     raw_user_info = pws_data_json["props"]["initialReduxState"]["viewerDeprecatedUseContextInstead"]

        raw_user_info = pws_data_json["props"]["context"]["user"]

        result["raw_user_info"] = raw_user_info
        result["is_connected"] = True
        return result

    def get_user_info(self, raw_user_info) -> dict:
        self.logger.debug("raw_user_info: %s", raw_user_info)
        user_info = {
            "user_id": raw_user_info.get("id"),
            "site": self.site,
            "name": raw_user_info.get("full_name"),
            "slug": raw_user_info.get("username"),
            "email": raw_user_info.get("email"),
            "url": self.home_url + raw_user_info.get("username"),
            "avatar_url": raw_user_info.get("image_xlarge_url"),
            # # wxpython wx.Locale设置导致local无法正常解析格式化时间字符串
            # ValueError: time data 'Wed, 01 Apr 2015 03:38:16 +0000' does not match format '%a, %d %b %Y %H:%M:%S %z'
            # "registry_t": utils.utc_to_local(raw_user_info.get("created_at"), fmt="%a, %d %b %Y %H:%M:%S %z"),
            "registry_t": self._utc_to_local(raw_user_info.get("created_at")),
            "update_t": None,
        }
        return user_info

    def get_boards(self) -> Generator:
        source_url = "/{}/".format(self.user_info["slug"])
        username = self.user_info["slug"]

        bookmarks = []
        while True:
            # 循环退出条件
            if bookmarks and bookmarks[0] == '-end-':
                break
            options = {
                "privacy_filter": "all",
                "sort": "last_pinned_to",
                "field_set_key": "profile_grid_item",
                "filter_stories": False,
                "username": username,
                "page_size": 25,
                "group_by": "visibility",
                "include_archived": True,
                "redux_normalize_feed": True,
                "bookmarks": bookmarks,
                "no_fetch_context_on_resource": False
            }
            params = self._build_get_params(options=options, source_url=source_url)
            req = self.session.request("GET", self.board_url, params=params)
            resp = req.json()
            bookmarks = resp['resource']['options']['bookmarks']
            result = resp['resource_response']['data']
            # 循环退出条件
            if result:
                for board in result:
                    if board["type"] == "board":
                        yield board
            else:
                break

    def get_board_info(self, board: dict) -> dict:
        board_data = {
            "board_id": board.get("id"),
            "user_id": self.user_info.get("user_id"),
            "site": self.site,
            "name": board.get("name"),
            "url": urljoin(self.home_url, board.get("url")),
            "state": 1 if board.get("privacy") == "public" else 0,  # 0: 私密; 1: 公开   secret/public
            "description": board.get("description"),
            "total": board.get("pin_count"),
            "created_t": self._utc_to_local(board.get("created_at")),
            "updated_t": self._utc_to_local(board.get("board_order_modified_at"))
        }
        return board_data

    def get_items(self, board) -> Generator:
        board_id = board.get("id")
        board_url = board.get("url")

        bookmarks = []
        while True:
            # 循环退出条件
            if bookmarks and bookmarks[0] == '-end-':
                break
            options = {
                "board_id": board_id,
                "board_url": board_url,
                "currentFilter": -1,
                "field_set_key": "react_grid_pin",
                "filter_section_pins": True,
                "sort": "default",
                "layout": "default",
                "page_size": 25,
                "redux_normalize_feed": True,
                "bookmarks": bookmarks,
                "no_fetch_context_on_resource": False,
            }
            params = self._build_get_params(options=options, source_url=board_url)
            req = self.session.request("GET", self.pin_url, params=params)
            resp = req.json()
            bookmarks = resp['resource']['options']['bookmarks']
            result = resp['resource_response']['data']
            # 循环退出条件
            if result:
                for pin in result:
                    if pin["type"] == "pin":    # 避免广告pin
                        item_data = {
                            "board_id": board_id,
                            "url": pin["images"]["orig"]["url"],
                            "width": pin["images"]["orig"]["width"],
                            "height": pin["images"]["orig"]["height"],
                        }
                        yield item_data
            else:
                break


class Huaban(Account):

    def __init__(self, *args, **kwargs):
        Account.__init__(self, *args, **kwargs)
        self.site = "huaban"

        # 账户请求信息
        self.api_url = "https://api.huaban.com"
        self.account_url = "https://huaban.com/user/{_slug}/"

        self.home_url = "https://huaban.com/"
        # self.account_url = "https://huaban.com/{_slug}/"
        self.board_url = "https://huaban.com/boards/{_id}/"
        self.csrf_token = ""

    @staticmethod
    def get_pin_url(pin):
        pin_key = pin['file']['key']
        pin_url = 'https://hbimg.huabanimg.com/{}'.format(pin_key)
        return pin_url

    @staticmethod
    def get_page_json(html, contain: str):
        pat = "app\\[\"{}\"] = (.*);".format(contain)
        result = re.search(pat, html).group(1)
        result = re.sub("(:)(?!null|false|true)([A-Za-z]\\w*?)([,}])",
                        lambda m: m.group(1) + "\"" + m.group(2) + "\"" + m.group(3),
                        result)
        page_json = json.loads(result)
        return page_json

    # def login(self) -> dict:
    #     result = {
    #         "is_connected": False,
    #     }
    #
    #     response = self.session.request("GET", self.home_url, follow_redirects=True)
    #     html = response.text
    #     req_json = self.get_page_json(html, "req")
    #
    #     if not req_json or not req_json.get("user"):
    #         raise AccountError(f"登录失败: {self.home_url}")
    #
    #     account_url = "https://huaban.com/{}/".format(req_json["user"].get("urlname"),)
    #     headers = {
    #         'Referer': "https://huaban.com/home/",
    #         'X-Requested-With': 'XMLHttpRequest',
    #     }
    #     response = self.session.request("GET", account_url, headers=headers)
    #     response_json = response.json()
    #
    #     if not response_json and not response_json.get("user"):
    #         raise AccountError(f"登录失败: {account_url}")
    #
    #     result["raw_user_info"] = response_json
    #     result["is_connected"] = True
    #     return result

    def login(self) -> dict:
        result = {
            "is_connected": False,
        }

        url = self.api_url + "/users/me"
        headers = {
            'Referer': self.home_url,
            'X-Requested-With': 'XMLHttpRequest',
        }
        req = self.session.request("GET", url, headers=headers)
        resp = req.json()

        if not resp or resp.get("err") == 404:
            raise AccountError(f"登录失败: {self.home_url}")

        result["raw_user_info"] = resp
        result["is_connected"] = True
        return result

    # def get_user_info(self, raw_user_info) -> dict:
    #     self.logger.debug("raw_user_info: %s", raw_user_info.get("user"))
    #     user_info = {
    #         "user_id": raw_user_info["user"].get("user_id"),
    #         "site": self.site,
    #         "name": raw_user_info["user"].get("username"),
    #         "slug": raw_user_info["user"].get("urlname"),
    #         "email": raw_user_info["user"].get("email"),
    #         "url": self.account_url.format(_slug=raw_user_info["user"].get("urlname"),),
    #         "avatar_url": 'https://hbimg.huabanimg.com/{}'.format(raw_user_info["user"]["avatar"]["key"]),
    #         "registry_t": utils.time_to_date(raw_user_info["user"].get("created_at")),
    #         "update_t": None,
    #     }
    #     return user_info

    def get_user_info(self, raw_user_info) -> dict:
        self.logger.debug("raw_user_info: %s", raw_user_info.get("user"))
        user_info = {
            "user_id": raw_user_info["user"]["user_id"],
            "site": self.site,
            "name": raw_user_info["user"]["username"],
            "slug": raw_user_info["user"]["urlname"],
            "email": raw_user_info["user"]["email"],
            "url": self.account_url.format(_slug=raw_user_info["user"]["urlname"],),
            "avatar_url": 'https://hbimg.huabanimg.com/{}'.format(raw_user_info["user"]["avatar"]["key"]),
            "registry_t": utils.time_to_date(raw_user_info["user"]["created_at"]),
            "update_t": None,
        }
        return user_info

    # def get_boards(self) -> Generator:
    #     account_url = self.account_url.format(_slug=self.user_info["slug"])
    #     _max = None
    #     headers = {
    #         'Referer': account_url,
    #         'X-Requested-With': 'XMLHttpRequest',
    #     }
    #     while True:
    #         params = {"max": _max, "limit": 10, "wfl": 1}
    #         response = self.session.request("GET", account_url, headers=headers, params=params)
    #         self.logger.debug("%s <board_url>: %s", self.site, response.url)
    #         page_json = response.json()['user']
    #         # 循环退出条件
    #         if page_json["boards"]:
    #             for board in page_json["boards"]:
    #                 yield board
    #         else:
    #             break
    #         last_item = page_json["boards"][-1]
    #         _max = last_item["board_id"]

    def get_boards(self) -> Generator:
        urlname = self.user_info["slug"]
        url = self.api_url + f"/{urlname}/boards"
        _max = None

        headers = {
            'Referer': self.user_info["url"],
            'X-Requested-With': 'XMLHttpRequest',
        }

        while True:
            params = {"max": _max, "limit": 30, "order_by_updated": 0}
            response = self.session.request("GET", url, headers=headers, params=params)
            self.logger.debug("%s <board_url>: %s", self.site, response.url)
            page_json = response.json()['boards']

            if page_json:
                for board in page_json:
                    yield board
                _max = page_json[-1]["board_id"]
            else:
                break

    def get_board_info(self, board: dict) -> dict:
        board_data = {
            "board_id": board["board_id"],
            "user_id": self.user_info["user_id"],
            "site": self.site,
            "name": board["title"],
            "url": self.board_url.format(_id=board["board_id"]),
            "state": 1 if board["is_private"] == 0 else 0,  # 0: 私密; 1: 公开   board.get("is_private")
            "description": board["description"],
            "total": board["pin_count"],
            "created_t": utils.time_to_date(board["created_at"]),
            "updated_t": utils.time_to_date(board["updated_at"])
        }
        return board_data

    # def get_items(self, board) -> Generator:
    #     board_url = self.board_url.format(_id=board.get("board_id"))
    #     headers = {
    #         'Referer': board_url,
    #         'X-Requested-With': 'XMLHttpRequest',
    #     }
    #     _max = None
    #     while True:
    #         params = {"max": _max, "limit": 10, "wfl": 1}
    #         response = self.session.request("GET", board_url, headers=headers, params=params)
    #         page_json = response.json()["board"]['pins']
    #         if page_json:
    #             for pin in page_json:
    #                 item_data = {
    #                     "board_id": pin["board_id"],
    #                     "url": self.get_pin_url(pin),
    #                     "width": pin["file"]["width"],
    #                     "height": pin["file"]["height"],
    #                 }
    #                 yield item_data
    #         else:
    #             break
    #         _max = page_json[-1]["pin_id"]

    def get_items(self, board) -> Generator:
        url = self.api_url + "/boards/{}/pins".format(board["board_id"])
        _max = None
        headers = {
            'Referer': self.board_url.format(_id=board["board_id"]),
            'X-Requested-With': 'XMLHttpRequest',
        }

        while True:
            params = {"limit": 20, "max": _max}
            response = self.session.request("GET", url, headers=headers, params=params)
            page_json = response.json()['pins']

            if page_json:
                for pin in page_json:
                    item_data = {
                        "name": str(pin["pin_id"]),
                        "board_id": pin["board_id"],
                        "url": self.get_pin_url(pin),
                        "width": pin["file"]["width"],
                        "height": pin["file"]["height"],
                    }
                    yield item_data
                _max = page_json[-1]["pin_id"]
            else:
                break


class AoSync:

    def __init__(self, sync_dir):
        self.logger = logging.getLogger("sync")

        self.sync_parser_thread = None          # 同步解析线程
        self.sync_download_thread = None        # 同步下载线程

        self.account_state = {}                 # 账户登录状态
        self.sync_dir = sync_dir                # 同步目录
        self.running_event = threading.Event()  # 线程事件
        self.con = wx.GetApp().con              # 数据库连接

    def _parser(self, browser_cookies: CookieJar):
        """
        同步解析线程
        :return:
        """
        for site in [Archdaily, Huaban, Pinterest]:
            if not self.running_event.is_set():
                break
            try:
                parser = site(browser_cookies, con=self.con)
                parser.run()
                self.account_state[parser.site] = parser.user_info.get("user_id")
            except Exception as e:
                self.logger.error(e)
                continue

    def _preload(self, browser_cookies: CookieJar):
        """账户信息检测线程函数"""
        # for site in [Archdaily, Huaban, Pinterest]:
        for site in [Huaban, Archdaily, Pinterest]:
            loader = site(browser_cookies, con=self.con)
            loader.run(preload=True)
            self.account_state[loader.site] = loader.user_info.get("user_id")

    def _parser_thread(self, browser_cookies):
        if self.sync_parser_thread is None or not self.sync_parser_thread.is_alive():
            self.sync_parser_thread = threading.Thread(target=self._parser,
                                                       args=(browser_cookies,),
                                                       name="sync_parser_thread")
            self.sync_parser_thread.setDaemon(True)
            self.sync_parser_thread.start()
            self.logger.info("同步解析线程启动")

    def _download_thread(self, browser_cookies):
        self.sync_download_thread = SyncDownload(browser_cookies=browser_cookies,
                                                 con=self.con,
                                                 running_event=self.running_event,
                                                 sync_dir=self.sync_dir)
        self.sync_download_thread.setDaemon(True)
        self.sync_download_thread.start()
        self.logger.info("同步下载线程启动")

    def start_preload(self):
        # 账户信息检测线程
        try:
            browser_cookies = cookies.load()
        except Exception as e:
            self.logger.error(e)
            self.logger.error("浏览器cookies载入失败.")
        else:
            preload_thread = threading.Thread(target=self._preload,
                                              args=(browser_cookies,),
                                              name="preload_thread")
            preload_thread.setDaemon(True)
            preload_thread.start()
            self.logger.info("账户信息检测线程启动")

    def start(self, sync_dir=None):
        """
        开启同步
        :return:
        """
        # 首次同步时，配置文件中没有sync_dir值, 通过参数传入
        self.sync_dir = sync_dir if sync_dir else self.sync_dir
        # 线程事件初始化为True
        self.running_event.set()
        try:
            browser_cookies = cookies.load()
        except Exception as e:
            self.logger.error(e)
            self.logger.error("浏览器cookies载入失败.")
            return False

        # 创建并执行同步解析线程
        self._parser_thread(browser_cookies)

        # 创建并执行同步下载线程(延时3分钟)
        wx.CallLater(60000, self._download_thread, browser_cookies)

    def stop(self):
        """
        关闭同步
        :return:
        """
        self.running_event.clear()      # 设置为False
