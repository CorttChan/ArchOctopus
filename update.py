"""
ArchOctopus 更新检查模块
"""
import os.path
import threading
import httpx
from distutils.version import LooseVersion
import logging

import wx

from constants import APP_NAME
from utils import retry

# local test
TEST_UPDATE_URL = "http://192.168.11.12/release"

# github.com
GITHUB_UPDATE_URL = "https://github.com/CorttChan/ArchOctopus/raw/main/release_version"
GITHUB_PLUGIN_VERSION_URL = "https://github.com/CorttChan/ArchOctopus/raw/main/plugin_version"
GITHUB_PLUGIN_UPDATE_URL = "https://github.com/CorttChan/ArchOctopus/raw/main/plugins/{plugin_name}"

# gitee.com
GITEE_UPDATE_URL = "https://gitee.com/CorttChan/ArchOctopus/raw/master/release_version"
GITEE_PLUGIN_VERSION_URL = "https://gitee.com/CorttChan/ArchOctopus/raw/master/plugin_version"
GITEE_PLUGIN_UPDATE_URL = "https://gitee.com/CorttChan/ArchOctopus/raw/master/plugins/{plugin_name}"


class Update(threading.Thread):
    """
    程序更新提醒
    """

    def __init__(self, parent, *args, **kwargs):
        threading.Thread.__init__(self, *args, **kwargs)
        self.parent = parent

        self.logger = logging.getLogger(APP_NAME)

    @retry(times=3)
    def run(self):
        for url in (GITEE_UPDATE_URL, GITHUB_UPDATE_URL):
            req = httpx.get(url)
            req.raise_for_status()

            info = req.json()
            if LooseVersion(info["version"]) > LooseVersion(wx.GetApp().version):
                update_info = {
                    "version": info.get("version"),
                    "description": info.get("description"),
                    "url": info.get("url"),
                    "notes_link": info.get("notes_link"),
                    "date": info.get("date"),
                }
                wx.CallAfter(self.parent.check_update, **update_info)
            break


def load_plugin_version(plugin_file):
    with open(plugin_file, 'r', encoding="utf-8") as pf:
        for line in pf.readlines():
            if line.startswith("# version:"):
                return line[10:].strip()
        else:
            return "0.0.1"


class PluginUpdate(threading.Thread):
    """
    解析插件自动下载与更新
    启动时自动检查插件配置文件, 从服务器端(gitee/github)下载与更新解析py文件.
    """

    def __init__(self, parent, *args, **kwargs):
        threading.Thread.__init__(self, *args, **kwargs)
        self.parent = parent

        self.logger = logging.getLogger(APP_NAME)

    @retry(times=3)
    def download_plugin(self, plugin_name, plugin_file):
        gitee_url = GITEE_PLUGIN_UPDATE_URL.format(plugin_name=plugin_name)
        github_url = GITHUB_PLUGIN_UPDATE_URL.format(plugin_name=plugin_name)

        for url in (gitee_url, github_url):
            req = httpx.get(url)
            req.raise_for_status()

            try:
                with open(plugin_file, 'w', encoding="utf-8") as f:
                    f.write(req.text)
            except PermissionError:
                break
            else:
                break

    @retry(times=3)
    def run(self):
        for url in (GITEE_PLUGIN_VERSION_URL, GITHUB_PLUGIN_VERSION_URL):
            req = httpx.get(url)
            req.raise_for_status()

            info: dict = req.json()

            for _name, _version in info.items():
                plugin_file = os.path.join("plugins", _name)
                # 更新旧解析文件
                if os.path.isfile(plugin_file):
                    plugin_version = load_plugin_version(plugin_file)
                    if LooseVersion(_version) > LooseVersion(plugin_version):
                        self.logger.debug("插件更新: %s v%s -> v%s", _name, plugin_version, _version)
                        self.download_plugin(_name, plugin_file)
                # 下载新解析文件
                else:
                    self.logger.debug("插件下载: %s v%s", _name, _version)
                    self.download_plugin(_name, plugin_file)

            break
