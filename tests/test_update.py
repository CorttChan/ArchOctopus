import unittest
from subprocess import Popen

import wx
import wx.adv

from archoctopus.update import Update


class TempFrame(wx.Frame):

    def __init__(self, parent):
        wx.Frame.__init__(self, parent, -1, "TempFrame")

        check_update_thread = Update(parent=self, test=True)
        check_update_thread.setDaemon(True)
        check_update_thread.start()

    def call_update_notice(self, **kwargs):
        _icon = wx.NullIcon
        _icon.CopyFromBitmap(wx.Bitmap("../archoctopus/gui/resource/icons/profile-130x.png"))

        # link_btn_id = wx.NewIdRef()
        # self.Bind(wx.adv.EVT_NOTIFICATION_MESSAGE_ACTION, self.on_open_update_link, link_btn_id)

        notify = wx.adv.NotificationMessage(
            title="ArchOctopus 新版本可供更新！",
            message="最新版本: {}\n发布日期: {}".format(kwargs.get("version"), kwargs.get("date")),
            parent=None,
        )

        notify.SetIcon(_icon)

        # if wx.Platform == '__WXMSW__':  # only works on MSW
        #     notify.UseTaskBarIcon(self.tbicon)

        # print(notify.AddAction(link_btn_id, "现在更新"))
        notify.Show(timeout=notify.Timeout_Auto)

    def call_upgrade_notice(self, **kwargs):
        info = "-- 解析插件在线更新 --\n\n\n"

        update_plugins = []
        new_plugins = []
        for _name, _value in kwargs.items():
            _local_version, _new_version = _value
            if _local_version is None:
                new_plugins.append("   {}: ({})\n".format(_name, _new_version))
            else:
                update_plugins.append("   {}: ({}  -->  {})\n".format(_name, _local_version, _new_version))

        if new_plugins:
            info += "新增插件: \n"
            info += "".join(new_plugins)
        if update_plugins:
            info += "\n升级插件: \n"
            info += "".join(update_plugins)

        dlg = wx.MessageDialog(self, info, "插件更新成功", wx.OK | wx.ICON_INFORMATION)
        dlg.SetFont(wx.Font(13, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, 0, 'Apple Braille'))
        dlg.ShowModal()
        dlg.Destroy()


class MyTestCase(unittest.TestCase):

    def setUp(self) -> None:
        # 启动本地服务器子进程
        self.sub_p = Popen(["python", "-m", "http.server", "--directory", "./assets/"])

    def tearDown(self) -> None:
        # 关闭本地服务器子进程
        self.sub_p.kill()
        # self.tmp_frame.Destroy()

    def test_update(self):
        # 临时app实例
        tmp_app = wx.App()
        tmp_frame = TempFrame(None)
        tmp_app.SetTopWindow(tmp_frame)
        tmp_frame.Show()
        tmp_app.MainLoop()

        self.assertEqual(True, False)


if __name__ == '__main__':
    unittest.main()
