#!/usr/bin/python3
# -*- coding: utf-8 -*-
# @Time    : 2022/8/23 10:51
# @Author  : CorttChan
# @Email   : cortt.me@gmail.com
# @File    : __init__.py.py

import wx
from archoctopus.database import AoDatabase


class TestApp(wx.App):
    def OnInit(self):
        # self.mainFrame = MyFrame(None, wx.ID_ANY, "")
        # self.SetTopWindow(self.mainFrame)
        # self.mainFrame.Show()

        self.con = AoDatabase()

        return True
