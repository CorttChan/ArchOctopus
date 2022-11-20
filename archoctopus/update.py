"""
ArchOctopus 更新检查模块
"""
import os.path
import threading
import httpx
from distutils.version import LooseVersion
import logging

import wx

from archoctopus.constants import APP_NAME
from archoctopus.version import VERSION

# local test
TEST_UPDATE_URL = "http://127.0.0.1:8000/test_release_version"
TEST_PLUGIN_VERSION_URL = "http://127.0.0.1:8000/test_plugin_version"

# #### v2.0.1 ####

# # GitHub
# GITHUB_UPDATE_URL = "https://github.com/CorttChan/ArchOctopus/raw/main/release_version"
# GITHUB_PLUGIN_VERSION_URL = "https://github.com/CorttChan/ArchOctopus/raw/main/plugin_version"
# GITHUB_PLUGIN_UPDATE_URL = "https://github.com/CorttChan/ArchOctopus/raw/main/plugins/{plugin_name}"
#
# # Gitee
# GITEE_UPDATE_URL = "https://gitee.com/CorttChan/ArchOctopus/raw/main/release_version"
# GITEE_PLUGIN_VERSION_URL = "https://gitee.com/corttchan/ArchOctopus/raw/main/plugin_version"
# GITEE_PLUGIN_UPDATE_URL = "https://gitee.com/CorttChan/ArchOctopus/raw/main/plugins/{plugin_name}"

# #### end ####

# Github
GITHUB_UPDATE_URL = "https://github.com/CorttChan/ArchOctopus/raw/main/update/release_version"
GITHUB_PLUGIN_VERSION_URL = "https://github.com/CorttChan/ArchOctopus/raw/main/update/plugin_version"
GITHUB_PLUGIN_UPDATE_URL = "https://github.com/CorttChan/ArchOctopus/raw/main/archoctopus/plugins/{plugin_name}"

# Gitee
GITEE_UPDATE_URL = "https://gitee.com/CorttChan/ArchOctopus/raw/main/update/release_version"
GITEE_PLUGIN_VERSION_URL = "https://gitee.com/corttchan/ArchOctopus/raw/main/update/plugin_version"
GITEE_PLUGIN_UPDATE_URL = "https://gitee.com/CorttChan/ArchOctopus/raw/main/archoctopus/plugins/{plugin_name}"


class Update(threading.Thread):
    """
    程序更新提醒
    """

    def __init__(self, parent, test=False, *args, **kwargs):
        threading.Thread.__init__(self, *args, **kwargs)
        self.parent = parent
        self.test = test

        self.logger = logging.getLogger(APP_NAME)

    def run(self):
        urls = (TEST_UPDATE_URL,) if self.test else (GITEE_UPDATE_URL, GITHUB_UPDATE_URL)
        for url in urls:
            try:
                req = httpx.get(url, follow_redirects=True)
                req.raise_for_status()
            except (httpx.HTTPStatusError, httpx.ConnectTimeout, httpx.ConnectError):
                self.logger.error("update访问失败: %s", url, exc_info=True)
                continue

            info = req.json()
            if LooseVersion(info["version"]) > LooseVersion(VERSION):
                update_info = {
                    "version": info.get("version"),
                    "desc": info.get("desc"),
                    "url": info.get("url"),
                    "notes": info.get("notes"),
                    "date": info.get("date"),
                }
                wx.CallAfter(self.parent.call_update_notice, **update_info)
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

    def __init__(self, parent, test=False, *args, **kwargs):
        threading.Thread.__init__(self, *args, **kwargs)
        self.parent = parent
        self.test = test

        self.logger = logging.getLogger(APP_NAME)

    def download_plugin(self, plugin_name, plugin_file) -> bool:
        gitee_url = GITEE_PLUGIN_UPDATE_URL.format(plugin_name=plugin_name)
        github_url = GITHUB_PLUGIN_UPDATE_URL.format(plugin_name=plugin_name)

        for url in (gitee_url, github_url):
            try:
                req = httpx.get(url, follow_redirects=True)
                req.raise_for_status()
            except (httpx.HTTPStatusError, httpx.ConnectTimeout):
                self.logger.error("update访问失败: %s", url, exc_info=True)
                continue

            try:
                with open(plugin_file, 'w', encoding="utf-8") as f:
                    f.write(req.text)
            except PermissionError:
                break
            else:
                return True

    def run(self):
        bundle_dir = wx.GetApp().get_install_dir()
        plugins_path = os.path.join(bundle_dir, "plugins")
        self.logger.debug("update_plugins_path: %s", plugins_path)

        plugins_update_result = {}

        urls = (TEST_PLUGIN_VERSION_URL,) if self.test else (GITEE_PLUGIN_VERSION_URL, GITHUB_PLUGIN_VERSION_URL)
        for url in urls:
            try:
                req = httpx.get(url, follow_redirects=True)
                req.raise_for_status()
            except (httpx.HTTPStatusError, httpx.ConnectTimeout):
                self.logger.error("update访问失败: %s", url, exc_info=True)
                continue

            info: dict = req.json()

            for _name, _version in info.items():
                plugin_file = os.path.join(plugins_path, _name)
                # 更新旧解析文件
                if os.path.isfile(plugin_file):
                    plugin_version = load_plugin_version(plugin_file)
                    if LooseVersion(_version) > LooseVersion(plugin_version):
                        self.logger.debug("插件更新: %s v%s -> v%s", _name, plugin_version, _version)
                        if self.download_plugin(_name, plugin_file):
                            plugins_update_result[_name] = (plugin_version, _version)
                        else:
                            self.logger.debug("插件下载失败: %s v%s -> v%s", _name, plugin_version, _version)
                # 下载新解析文件
                else:
                    self.logger.debug("新插件下载: %s (v%s)", _name, _version)
                    if self.download_plugin(_name, plugin_file):
                        plugins_update_result[_name] = (None, _version)
                    else:
                        self.logger.debug("新插件下载失败: %s (v%s)", _name, _version)

            break

        # 插件更新信息提示
        if plugins_update_result:
            wx.CallAfter(self.parent.call_upgrade_notice, **plugins_update_result)
