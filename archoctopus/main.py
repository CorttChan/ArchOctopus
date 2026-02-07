#!/usr/bin/python3
# -*- coding: utf-8 -*-
# @Time    : 2023/9/15 10:23
# @Author  : CorttChan
# @Email   : cortt.me@gmail.com
# @File    : tmp_main.py

import os
import sys
import logging.config

import wx

from archoctopus import constants
from archoctopus.usage import Usage
from archoctopus.db import DataBase
from archoctopus.ui import AuiMain
from archoctopus.task import TasksManager


# locale = None


def setup_install():
    import builtins
    builtins.__dict__['_'] = wx.GetTranslation


def setup_config():
    data_dir = wx.StandardPaths.Get().GetUserDataDir()
    if not os.path.exists(data_dir):
        os.mkdir(data_dir)

    wx.FileConfig.DontCreateOnDemand()
    config = wx.FileConfig(localFilename=os.path.join(data_dir, "config.ini"))
    wx.FileConfig.Set(config)


def setup_locale():
    # global locale
    config = wx.FileConfig.Get()
    lang_code = config.Read("/Lang/language")

    if lang_code and (lang_code in constants.SUP_LANGS):
        lang = constants.SUP_LANGS[lang_code]
    else:
        lang = wx.Locale.GetSystemLanguage()
        if lang not in constants.SUP_LANGS.values():
            lang = wx.LANGUAGE_CHINESE_CHINA

        config.Write("/Lang/language", value=wx.Locale.GetLanguageCanonicalName(lang))

    # if locale:
    #     assert sys.getrefcount(locale) <= 2
    #     del locale

    locale = wx.Locale(lang)
    locale.AddCatalogLookupPathPrefix('locale')
    if locale.IsOk():
        locale.AddCatalog(constants.LANG_DOMAIN)
    # else:
    #     locale = None


def setup_db():
    db_file = os.path.join(wx.StandardPaths.Get().GetUserDataDir(), f"{constants.APP_NAME}_new.db")
    print("db_file: ", db_file)
    DataBase().init(db_path=db_file)


def setup_taskmanager():
    TasksManager(max_workers=5)


def setup_logger():
    """"""
    if getattr(sys, 'frozen', False):
        level = "INFO"
    else:
        level = "DEBUG"

    print("Logger Level: ", level)

    # 日志配置
    log_file = os.path.join(os.path.dirname(__file__), constants.APP_NAME + ".log")
    log_conf = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "simple": {'format': '%(asctime)s - %(levelname)s - %(filename)s[:%(lineno)d] - %(message)s'},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "simple",
                "stream": "ext://sys.stdout"
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "simple",
                "filename": log_file,
                "maxBytes": 1024 * 1024 * 10,  # 10 MB
                "backupCount": 20,
                "encoding": "utf8"
            },
        },
        "loggers": {
            constants.APP_NAME: {
                "level": level,
                "handlers": ["file", "console"],
                "propagate": "no"
            },
            "sync": {
                "level": level,
                "handlers": ["file", "console"],
                "propagate": "no"
            }
        },
    }
    logging.config.dictConfig(log_conf)
    logger = logging.getLogger(constants.APP_NAME)

    logger.info('ArchOctopus start running...')


class App(wx.App):

    def OnInit(self):
        # Singleton
        instance = wx.SingleInstanceChecker(name="ArchOctopus-%s" % wx.GetUserId())
        if instance.IsAnotherRunning():
            wx.MessageBox("ArchOctopus 已经启动...", constants.APP_DISPLAY_NAME)
            return False

        # Properties
        self.SetAppName(constants.APP_NAME)
        self.SetAppDisplayName(constants.APP_DISPLAY_NAME)

        # Setup
        setup_install()
        setup_logger()
        setup_config()
        setup_locale()
        setup_db()
        setup_taskmanager()

        return True

    def OnExit(self):
        DataBase.close()
        wx.FileConfig.Get().Flush()

        if getattr(sys, 'frozen', False):
            usage_thread = Usage(self)
            usage_thread.start()
            usage_thread.join()

        return True


def run_cli(url):
    from archoctopus.cli import cli
    cli(url)


def run_gui():
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)      # Per-Monitor (V2) DPI Awareness
    except AttributeError:
        ctypes.windll.shcore.SetProcessDpiAware(2)

    app = App()
    frame = AuiMain(None)
    frame.Show()
    app.SetTopWindow(frame)

    if not getattr(sys, 'frozen', False):
        from wx.lib.inspection import InspectionTool
        wnd = wx.FindWindowAtPointer()
        if not wnd:
            wnd = frame
        InspectionTool().Show(wnd, True)

    app.MainLoop()


def main():
    import argparse
    from archoctopus.version import VERSION

    parser = argparse.ArgumentParser(description='')
    parser.add_argument('-c', '--cmd', dest="url", help='cmd mode')
    parser.add_argument('-v', '--version', action='version', version=VERSION, help='current version')

    args = parser.parse_args()

    if args.url:
        run_cli(url=args.url)
    else:
        run_gui()


if __name__ == '__main__':
    main()
