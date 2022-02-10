"""
ArchOctopus main

"""
from urllib.parse import urlparse
import os
import logging.config
import string
from queue import Queue

from distutils.version import LooseVersion

import wx
import wx.adv
import wx.lib.newevent

import utils
import version
import constants

if wx.Platform == '__WXMSW__':
    from gui import msw_gui as wx_gui
else:
    from gui import mac_gui as wx_gui

from gui import custom_outlinebtn, MyBitmap, TagsPopupCtl, svg_bitmap
from gui import SYNC, SYNC_DISABLE, PAUSE, RESTART
from task import TaskItem
from database import AoDatabase
from update import Update, PluginUpdate
import sync
from utils import get_bitmap_from_embedded, get_docs_dir


def is_url(url: str):
    """
    Validate available url format str.
    """
    result = urlparse(url)
    return all(result[:3])


def get_data_dir():
    """
    Return the standard location on this platform for application data.
    """
    sp = wx.StandardPaths.Get()
    return sp.GetUserDataDir()


def get_config():
    data_dir = get_data_dir()
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    config = wx.FileConfig(
        appName=constants.APP_NAME,
        localFilename=os.path.join(data_dir, "config.ini")
    )
    return config


class DebugFrameHandler(logging.StreamHandler):
    """"""

    # ----------------------------------------------------------------------
    def __init__(self, textctrl):
        """"""
        logging.StreamHandler.__init__(self)
        self.textctrl = textctrl
        fmt = logging.Formatter(fmt='%(asctime)s [%(levelname)s]-> %(message)s')
        self.setFormatter(fmt)

    # ----------------------------------------------------------------------
    def emit(self, record):
        """Constructor"""
        msg = self.format(record)
        self.textctrl.WriteText(msg + "\n")
        self.flush()


class SettingValidator(wx.Validator):
    """
    设置面板验证器
    """

    def __init__(self, cfg, path, value_type="str", flag="", default=None):
        wx.Validator.__init__(self)
        self.flag = flag
        self.cfg = cfg
        self.path = path
        self.value_type = value_type
        self.default = default
        self.Bind(wx.EVT_CHAR, self.on_char)

    def Clone(self):
        return SettingValidator(self.cfg, self.path, self.value_type, self.flag)

    def Validate(self, parent):
        return True

    def TransferToWindow(self):
        win = self.GetWindow()
        if self.value_type == "str":
            value = self.cfg.Read(self.path)
        elif self.value_type == "int":
            value = self.cfg.ReadInt(self.path)
        elif self.value_type == "bool":
            value = self.cfg.ReadBool(self.path)
        else:
            return True

        value = self.default if not value and self.default else value
        win.SetValue(value)
        return True

    def TransferFromWindow(self):
        win = self.GetWindow()
        value = win.GetValue()
        if self.value_type == "str":
            self.cfg.Write(self.path, value)
        elif self.value_type == "int":
            self.cfg.WriteInt(self.path, value)
        elif self.value_type == "bool":
            self.cfg.WriteBool(self.path, value)
        return True

    def on_char(self, event):
        key = chr(event.GetKeyCode())
        if self.flag == "digit" and key in string.ascii_letters + string.punctuation:
            return
        if self.flag == "ip" and key in string.ascii_letters + string.punctuation.replace(".", ""):
            return
        event.Skip()


class AoMainFrame(wx_gui.MyFrame):
    """
    ArchOctopus GUI主界面
    """

    def __init__(self, *args, **kwds):
        wx_gui.MyFrame.__init__(self, *args, **kwds)

        self.logger = logging.getLogger(constants.APP_NAME)

        self.cfg = wx.GetApp().cfg          # 全局配置对象
        self.con = wx.GetApp().con          # 数据库连接对象

        sync_dir = self.cfg.Read("/Sync/sync_dir")
        self.sync = sync.AoSync(sync_dir)           # 同步对象
        self.sync_timer = wx.Timer(self)    # 同步定时器
        self.sync_cover_cache = {}
        if self.cfg.ReadBool("/Sync/sync_status", defaultVal=False):
            self.sync_status_ctrl.SetBitmap(svg_bitmap(SYNC, 24, 24, colour=wx.WHITE))
            interval = self.cfg.ReadInt("/Sync/sync_interval", defaultVal=600000)
            self.sync.start()
            self.sync_timer.Start(interval)
        else:
            wx.CallLater(3000, self.sync.start_preload)     # 延时执行账户信息检测, 避免启动等待时间过长
            # self.sync.start_preload()   # 账户信息检测

        self.is_auto_clip = False   # 自动粘贴板
        self.previous_url = ""  # 用于判断系统粘贴板中的url是否已使用过
        self.running_task_count = 0  # 用于判断是否存在正在运行的Task实例
        self.proxies = None

        self.available_update_url = ""  # 可用更新链接
        self.available_update_version = ""  # 可用更新版本

        self.tbicon = TBicon(self)
        self.url_ctrl.SetHint("输入收集网址...")
        self.url_ctrl.SetFocus()

        self.init_load_history()
        self.config_effect()

        # 更新插件
        check_plugin_thread = PluginUpdate(self)
        check_plugin_thread.setDaemon(True)
        check_plugin_thread.start()

        # event
        self.Bind(wx.EVT_MOVE, self.on_move)
        self.Bind(wx.EVT_HELP, self.on_help)
        self.Bind(wx.EVT_ACTIVATE, self.on_activate_clip)

        if wx.Platform == '__WXMSW__':
            self.Bind(wx.EVT_ICONIZE, self.on_iconize)
        # elif wx.Platform == '__WXMAC__':

        self.start_ctrl.Bind(wx.EVT_LEFT_DOWN, self.on_start)
        self.url_ctrl.Bind(wx.EVT_TEXT_ENTER, self.on_start)
        self.sync_btn.Bind(wx.EVT_BUTTON, self.on_open_sync_dlg)
        self.setup_btn.Bind(wx.EVT_BUTTON, self.on_open_setup_dlg)
        self.history_btn.Bind(wx.EVT_BUTTON, self.on_open_history_dlg)
        self.donate_btn.Bind(wx.EVT_BUTTON, self.on_open_donate_link)
        self.author_st.Bind(wx.EVT_LEFT_DCLICK, self.on_about)

        self.Bind(wx.EVT_TIMER, self.on_sync_timer, self.sync_timer)

    def init_load_history(self):
        """初始化载入历史记录"""
        display_limit = self.cfg.ReadInt("/General/display_limit", defaultVal=15)
        sql = """
            SELECT h.*, GROUP_CONCAT(t.tag,', ') AS TagsList
            FROM history as h 
            LEFT OUTER JOIN history_related_tag as hrt ON h.id = hrt.history_id 
            LEFT OUTER JOIN tags as t ON hrt.tag_id = t.id
            WHERE h.is_show = 1
            GROUP BY h.id 
            ORDER BY h.id desc
            LIMIT {}
        """.format(display_limit)
        result = self.con.select(sql)
        info_key = ("id", "name", "status", "date", "domain", "url", "dir", "total_count", "download_count",
                    "is_folder", "is_show", "tags")
        for _r in result:
            task_info = dict(zip(info_key, _r))
            self.create_task_panel(1, **task_info)

    def refresh_logo(self, update: int):
        self.running_task_count += update
        self.running_task_count = 0 if self.running_task_count < 0 else self.running_task_count
        if self.running_task_count == 0 and self.anim_ctrl.IsPlaying():
            self.anim_ctrl.Stop()
        elif self.running_task_count != 0 and not self.anim_ctrl.IsPlaying():
            self.anim_ctrl.Play()

    def create_task_panel(self, position, **kwargs):
        """创建任务面板"""
        self.Freeze()  # WindowUpdateLocker-- Freeze panel without flicker
        task_panel = AoTaskPanel(self.panel_5, wx.ID_ANY, **kwargs)
        task_panel.SetMinSize((-1, 65))
        self.Thaw()  # Re-enables window updating

        if position:    # 1 --> sizer末尾位置
            self.sizer_8.Add(task_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        else:           # 0 --> sizer起始位置
            self.sizer_8.Prepend(task_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.sizer_7.Layout()

        return task_panel

    def check_update(self, **kwargs):
        self.available_update_url = kwargs.get("url")
        self.available_update_version = kwargs.get("version")

        _icon = wx.NullIcon
        _icon.CopyFromBitmap(MyBitmap(wx_gui.APP_ABOUT_ICON))

        # link_btn_id = wx.NewIdRef()
        # self.Bind(wx.adv.EVT_NOTIFICATION_MESSAGE_ACTION, self.on_open_update_link, link_btn_id)

        notify = wx.adv.NotificationMessage(
            title="ArchOctopus 新版本可供更新！",
            message="最新版本: {}\n发布日期: {}".format(kwargs.get("version"), kwargs.get("date")),
            parent=None)

        notify.SetIcon(_icon)
        # notify.UseTaskBarIcon(self.tbicon)

        # notify.AddAction(link_btn_id, "现在更新")

        notify.Show(timeout=notify.Timeout_Never)

    def config_effect(self):
        # 检查自动粘贴板设置
        self.is_auto_clip = self.cfg.ReadBool("/General/auto_clip", defaultVal=False)
        # 判断是否开启日志面板
        if self.cfg.ReadBool("/Privacy/debug", defaultVal=False):
            if not hasattr(self, "debug_dlg"):
                main_frame_pos = self.GetPosition()
                main_frame_size = self.GetSize()
                debug_frame_pos = wx.Point(main_frame_pos[0], main_frame_pos[1] + main_frame_size[1])
                debug_frame_size = wx.Size(main_frame_size[0], 200)
                self.debug_dlg = wx_gui.DebugFrame(self, pos=debug_frame_pos)
                self.debug_dlg.SetSize(debug_frame_size)
                self.debug_dlg.Show()
                # 添加DebugFrameHandler
                self.frame_handler = DebugFrameHandler(self.debug_dlg.log_tc)
                self.logger.addHandler(self.frame_handler)

        else:
            if hasattr(self, "debug_dlg"):
                self.logger.removeHandler(self.frame_handler)
                self.debug_dlg.Destroy()
                del self.debug_dlg
                del self.frame_handler
        # 检查更新
        if self.cfg.ReadBool("/General/auto_update", defaultVal=False):
            check_update_thread = Update(self)
            check_update_thread.setDaemon(True)
            check_update_thread.start()
        # 检查刷新代理信息
        proxy_host = self.cfg.Read("/Proxy/host", defaultVal="")
        proxy_port = self.cfg.Read("/Proxy/port", defaultVal="")
        if proxy_host and proxy_port:
            is_proxy_auth = self.cfg.ReadBool("/Proxy/auth", defaultVal=False)
            if is_proxy_auth:
                proxy_user = self.cfg.Read("/Proxy/user", defaultVal="")
                proxy_password = self.cfg.Read("/Proxy/pwd", defaultVal="")
                self.proxies = f"http://{proxy_user}:{proxy_password}@{proxy_host}:{proxy_port}"
            else:
                self.proxies = f"http://{proxy_host}:{proxy_port}"

    def on_iconize(self, event):
        is_minimized = self.cfg.ReadBool("/General/minimized", defaultVal=True)
        if is_minimized:
            self.Hide()
            self.tbicon.ShowBalloon(title='ArchOctopus', text='ArchOctopus 正在最小化运行', msec=500)
        event.Skip()

    def on_move(self, event):
        if hasattr(self, "debug_dlg"):
            pos = self.GetPosition()
            size = self.GetSize()
            self.debug_dlg.Move(pos[0], pos[1]+size[1])
        event.Skip()

    def on_about(self, event):
        about_dlg = AoAbout(self)
        about_dlg.ShowModal()

    def on_activate_clip(self, event):
        """窗口激活时, 自动从剪贴板中拷贝url到输入控件"""
        if event.GetActive() and self.is_auto_clip:
            url_data = wx.URLDataObject()
            if wx.TheClipboard.Open() and wx.TheClipboard.GetData(url_data):
                url = url_data.GetURL().strip(" \'\"[]<>")
                if self.url_ctrl.IsEmpty() and is_url(url):
                    if url != self.previous_url:
                        self.url_ctrl.SetValue(url)
                        self.previous_url = url
                wx.TheClipboard.Close()
            self.url_ctrl.SetFocus()
        event.Skip()

    def on_close(self, event):
        """正常退出"""
        # 任务栏图标退出
        self.tbicon.RemoveIcon()
        self.tbicon.Destroy()
        # 配置内容写入
        self.cfg.Flush()

        self.Destroy()

    def on_start(self, event):
        """启动新项目"""
        raw_url = self.url_ctrl.GetValue().strip(" \'\"[]<>")
        self.url_ctrl.Clear()
        if not (raw_url and is_url(raw_url)):
            wx.MessageBox("错误的网址格式！", "输入错误", wx.OK | wx.ICON_ERROR, parent=self)
            return

        # 查询数据库,判断是否重复下载
        sql = "SELECT * FROM history WHERE url = ?"
        result = self.con.select_one(sql, (raw_url,))
        if result:
            task_id = result[0]
            ask_dlg = wx.MessageDialog(self,
                                       "当前网址已下载，是否打开下载文件夹？",
                                       constants.APP_DISPLAY_NAME,
                                       wx.YES_NO | wx.CANCEL | wx.CANCEL_DEFAULT | wx.ICON_INFORMATION)
            ask_dlg.SetYesNoLabels(yes="打开文件夹", no="重新下载")
            ask_result = ask_dlg.ShowModal()

            if ask_result == wx.ID_NO:
                # 重新下载时, 清除url表中的下载记录, 用于后续解析过程中的去重操作.
                sql = "DELETE FROM urls WHERE task_id=?"
                self.con.execute(sql, (result[0],))
                # 重新下载时, 初始化history表中的total_count, download_count字段
                sql = "UPDATE history SET total_count=0, download_count=0, is_show=1 WHERE id=?"
                self.con.execute(sql, (result[0],))
                ask_dlg.Destroy()
            else:
                if ask_result == wx.ID_YES:
                    target = result[6] or result[5]
                    wx.LaunchDefaultBrowser(target, flags=0)
                ask_dlg.Destroy()
                return
        else:
            sql = "INSERT INTO history (url) VALUES (?)"
            self.con.execute(sql, (raw_url,))
            sql = "SELECT id FROM history WHERE url=?"
            task_id = self.con.select_one(sql, (raw_url,))[0]

        # 判断重复下载时, 任务面板是否已创建
        for _item in self.sizer_8.GetChildren():
            _task_panel = _item.GetWindow()
            if _task_panel.task_info["id"] == task_id:
                # 重新下载时, 初始化进度条
                _task_panel.gauge.SetBarColor(wx.Colour(0, 174, 239))
                _task_panel.gauge_value = 0
                _task_panel.gauge.SetValue(0)
                _task_panel.run()
                break
        # 创建任务面板
        else:
            _task_panel = self.create_task_panel(0, id=task_id, url=raw_url)
            _task_panel.run()

    def on_sync_timer(self, event):
        """同步定时"""
        self.sync.start()

    def on_open_sync_dlg(self, event):
        sync_dlg = AoSyncDlg(self)
        sync_dlg.ShowModal()
        sync_dlg.Destroy()

    def on_open_setup_dlg(self, event):
        setup_dlg = AoSettingDlg(self)
        result = setup_dlg.ShowModal()
        if result == wx.ID_OK:
            for _k, _v in setup_dlg.change.items():
                if isinstance(_v, bool):
                    self.cfg.WriteBool(_k, _v)
                elif isinstance(_v, int):
                    self.cfg.WriteInt(_k, _v)
                elif isinstance(_v, float):
                    self.cfg.WriteFloat(_k, _v)
                else:
                    self.cfg.Write(_k, _v)
            self.cfg.Flush()

            # 生效配置
            self.config_effect()

        setup_dlg.Destroy()

    def on_open_history_dlg(self, event):
        history_dlg = AoHistoryDlg(self)
        history_dlg.ShowModal()
        history_dlg.Destroy()

    def on_open_donate_link(self, event):
        donate_dlg = AoDonateDlg(self)
        donate_dlg.Show()

    def on_help(self, event):
        wx.LaunchDefaultBrowser(constants.HELP_URL, flags=0)
        event.Skip()


class AoAbout(wx_gui.MyAbout):

    def __init__(self, *args, **kwargs):
        super(AoAbout, self).__init__(*args, **kwargs)
        info = "版本：{} 64bit\n日期：{}".format(version.VERSION, version.RELEASE_DATA)
        self.release_info.SetLabel(info)

        self.links = {
            self.home_page.GetId(): constants.HOME_URL,
            self.donate_page.GetId(): constants.DONATE_URL,
            self.feedback_page.GetId(): constants.FEEDBACK_URL,
            self.source_page.GetId(): constants.SOURCE_URL,
        }

        # Bind event handler
        for st in (self.home_page, self.donate_page, self.feedback_page, self.source_page):
            st.Bind(wx.EVT_ENTER_WINDOW, self.on_enter_hand)
            st.Bind(wx.EVT_LEAVE_WINDOW, self.on_leave_hand)
            st.Bind(wx.EVT_LEFT_DOWN, self.on_click_link)

    def on_enter_hand(self, event):
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        event.Skip()

    def on_leave_hand(self, event):
        self.SetCursor(wx.NullCursor)
        event.Skip()

    def on_click_link(self, event):
        url = self.links.get(event.GetId())
        wx.LaunchDefaultBrowser(url, flags=0)
        event.Skip()


class AoDonateDlg(wx_gui.DonateDialog):

    def __init__(self, parent):
        super(AoDonateDlg, self).__init__(parent)

        # Setting properties
        self.pre_activate = self.btn_rmb_50
        self.pre_activate.SetValue(True)
        self.pre_activate.SetBackgroundColour(wx.Colour(0, 174, 239))

        # Binding custom event
        self.Bind(wx.EVT_ACTIVATE, self.on_show_close_btn)

        if wx.Platform == '__WXMSW__':
            self.donation_list_btn.Bind(wx.EVT_ENTER_WINDOW, self.on_mouse_over)
            self.donation_list_btn.Bind(wx.EVT_LEAVE_WINDOW, self.on_mouse_leave)

    def on_close(self, event):
        self.Destroy()

    def on_show_close_btn(self, event):
        is_activate = event.GetActive()
        self.close_btn.Show(is_activate)
        event.Skip()

    def on_change_qr(self, event):
        self.pre_activate.SetValue(False)
        self.pre_activate.SetBackgroundColour(wx.WHITE)

        self.pre_activate = btn = event.GetEventObject()
        btn.SetBackgroundColour(wx.Colour(0, 174, 239))

        bitmap_name = self.id_pair[event.GetId()]
        self.payment_qr.SetBitmap(MyBitmap(bitmap_name))

    def on_mouse_over(self, event):
        btn = event.GetEventObject()
        btn.SetBackgroundColour(wx.Colour(71, 71, 71))
        event.Skip()

    def on_mouse_leave(self, event):
        btn = event.GetEventObject()
        btn.SetBackgroundColour(wx.Colour(85, 85, 85))
        event.Skip()

    def on_open_donation_list_page(self, event):
        wx.LaunchDefaultBrowser(constants.DONATION_URL, flags=0)


class AoSettingDlg(wx_gui.SettingDialog):
    def __init__(self, *args, **kwds):
        self.cfg = wx.GetApp().cfg
        super(AoSettingDlg, self).__init__(*args, **kwds)

        # 判断是否有可用更新
        if self.GetParent().available_update_url:
            # available_version = self.GetParent().available_update_version
            # info = "更新可用: " + available_version
            self.available_update_link.SetLabel("更新可用: v{}".format(self.GetParent().available_update_version))
            self.available_update_link.SetURL(self.GetParent().available_update_url)

            # available_update_link = wx.adv.HyperlinkCtrl(
            #     self.general_panel,
            #     label="更新可用: {}".format(self.GetParent().available_update_version),
            #     url=self.GetParent().available_update_url)
            # # sizer = self.update_toggle_ctrl.GetContainingSizer()
            # self.sizer_17.Add(available_update_link, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 140)

            # self.sizer_17.Layout()

        # 设置验证器Validator
        self.download_dir_display.SetValidator(SettingValidator(self.cfg, "/General/download_dir",
                                                                default=get_docs_dir()))
        # self.loop_slider.SetValidator(SettingValidator(self.cfg, "/General/loop_max", value_type="int"))
        self.loop_max_ctrl.SetValidator(SettingValidator(self.cfg, "/General/loop_max", value_type="str",
                                                         flag="digit", default="5"))
        self.clip_toggle_ctrl.SetValidator(SettingValidator(self.cfg, "/General/auto_clip", value_type="bool",
                                                            default=True))
        self.pdf_toggle_ctrl.SetValidator(SettingValidator(self.cfg, "/General/pdf_output", value_type="bool"))
        self.taskbar_toggle_ctrl.SetValidator(SettingValidator(self.cfg, "/General/minimized", value_type="bool",
                                                               default=True))
        self.update_toggle_ctrl.SetValidator(SettingValidator(self.cfg, "/General/auto_update", value_type="bool",
                                                              default=True))

        self.privacy_tag_ctrl.SetValidator(SettingValidator(self.cfg, "/Privacy/tag", value_type="bool"))
        # 显示日志面板(吸附于主界面左侧)
        self.privacy_debug_ctrl.SetValidator(SettingValidator(self.cfg, "/Privacy/debug", value_type="bool"))

        self.proxy_host_text_ctrl.SetValidator(SettingValidator(self.cfg, "/Proxy/host",
                                                                value_type="str", flag="ip"))
        self.proxy_port_text_ctrl.SetValidator(SettingValidator(self.cfg, "/Proxy/port",
                                                                value_type="str", flag="digit"))
        self.proxy_auth_toggle_ctrl.SetValidator(SettingValidator(self.cfg, "/Proxy/auth", value_type="bool"))
        self.proxy_user_text_ctrl.SetValidator(SettingValidator(self.cfg, "/Proxy/user", value_type="str"))
        self.proxy_pwd_text_ctrl.SetValidator(SettingValidator(self.cfg, "/Proxy/pwd", value_type="str"))

        self.min_width_text_ctrl.SetValidator(SettingValidator(self.cfg, "/Filter/min_width",
                                                               value_type="str", flag="digit", default="0"))
        self.min_height_text_ctrl.SetValidator(SettingValidator(self.cfg, "/Filter/min_height",
                                                                value_type="str", flag="digit", default="0"))
        self.min_size_text_ctrl.SetValidator(SettingValidator(self.cfg, "/Filter/min_size",
                                                              value_type="str", flag="digit", default="0"))
        self.max_size_text_ctrl.SetValidator(SettingValidator(self.cfg, "/Filter/max_size",
                                                              value_type="str", flag="digit", default="0"))

        self.default_checkbox.SetValidator(SettingValidator(self.cfg, "/Filter/default_jpg", value_type="bool"))
        self.prefix_index.SetValidator(SettingValidator(self.cfg, "/Filter/is_index", value_type="bool"))

        #
        self.change = {}
        self.checkboxes = []
        self.filter_images = {".jpeg": self.jpg_checkbox,
                              ".png": self.png_checkbox,
                              ".gif": self.gif_checkbox,
                              ".bmp": self.bmp_checkbox,
                              ".webp": self.webp_checkbox}

        self.init_set_properties()

    def init_set_properties(self):
        """
        Set properties from config file or default value
        :return:
        """
        # Custom_Rule Page
        self.cfg.SetPath("/Rules/")
        more, value, index = self.cfg.GetFirstEntry()

        while more:
            self.creat_sub_rule_boxsizer(value, self.cfg.Read(value))
            more, value, index = self.cfg.GetNextEntry(index)

        self.cfg.SetPath("/")

        # # Filter Page
        image_type = self.cfg.Read("/Filter/type", defaultVal="")
        if image_type:
            self.filter_image_type.SetValue(True)
            for _type in image_type.split(","):
                self.checkboxes.append(_type)
                self.filter_images[_type].SetValue(True)
        else:
            self.image_all_type.SetValue(True)
            for _check in self.filter_images.values():
                _check.Disable()

    def on_select_dir(self, event):
        dlg = wx.DirDialog(self, "选择下载文件夹:",
                           style=wx.DD_DEFAULT_STYLE
                           | wx.DD_DIR_MUST_EXIST
                           # | wx.DD_CHANGE_DIR
                           )
        if dlg.ShowModal() == wx.ID_OK:
            self.download_dir_display.SetValue(dlg.GetPath())
        dlg.Destroy()

    def creat_sub_rule_boxsizer(self, domain="", reg_exp=""):
        bs_sub = wx.BoxSizer(wx.HORIZONTAL)

        self.Freeze()
        tc_site = wx.TextCtrl(self.rule_panel, -1, domain)
        tc_rule = wx.TextCtrl(self.rule_panel, -1, reg_exp)
        btn_edit = wx.BitmapToggleButton(self.rule_panel, -1, MyBitmap(wx_gui.CHECK_BTN),
                                         style=wx.BORDER_NONE | wx.BU_EXACTFIT)
        btn_edit.SetBackgroundColour(wx.WHITE)

        btn_edit.SetBitmapPressed(MyBitmap(wx_gui.EDIT_BTN))
        btn_del = wx.BitmapButton(self.rule_panel, -1, MyBitmap(wx_gui.CLOSE_BTN),
                                  style=wx.BORDER_NONE | wx.BU_EXACTFIT)
        btn_del.SetBackgroundColour(wx.WHITE)
        if domain:
            tc_site.Disable()
            tc_rule.Disable()
            btn_edit.SetValue(True)

        bs_sub.AddMany([
            (tc_site, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5),
            (tc_rule, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5),
            (btn_edit, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5),
            (btn_del, 0, wx.ALIGN_CENTER_VERTICAL, 0),
        ])
        self.sizer_21.Add(bs_sub, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        self.Thaw()

        self.sizer_21.Layout()
        self.sizer_11.Layout()

        btn_edit.Bind(wx.EVT_TOGGLEBUTTON, self.on_rule_edit)
        btn_del.Bind(wx.EVT_BUTTON, self.on_rule_del)

    def on_rule_del(self, event):
        bs = event.GetEventObject().GetContainingSizer()
        for sub_obj in bs.GetChildren():
            sub_obj.DeleteWindows()
        self.sizer_21.Remove(bs)
        self.sizer_21.Layout()
        self.sizer_11.Layout()

    def on_rule_edit(self, event):
        tc_rule = event.GetEventObject().GetPrevSibling()
        tc_site = tc_rule.GetPrevSibling()
        tc_rule.Enable(not event.IsChecked())
        tc_site.Enable(not event.IsChecked())
        if event.IsChecked():
            tc_rule_value = tc_rule.GetValue()
            tc_site_value = tc_site.GetValue()
            if all((tc_rule_value, tc_site_value)):
                self.change.update({"/Rules/{}".format(tc_site_value): tc_rule_value})

    # Override the method "on_add_rule"
    def on_add_rule(self, event):
        self.creat_sub_rule_boxsizer()

    # Override the method "on_image_all_type"
    def on_image_all_type(self, event):
        self.change.update({"/Filter/type": ""})
        self.checkboxes.clear()
        for _check in self.filter_images.values():
            _check.Disable()

    # Override the method "on_filter_image_type"
    def on_filter_image_type(self, event):
        for _check in self.filter_images.values():
            _check.Enable()
            if _check.IsChecked():
                self.checkboxes.append(_check.GetLabel())

    # Override the method "on_filter_checkbox"
    def on_filter_checkbox(self, event):
        if event.IsChecked():
            self.checkboxes.append(event.GetEventObject().GetLabel())
        else:
            self.checkboxes.remove(event.GetEventObject().GetLabel())
        self.change.update({"/Filter/type": ",".join(self.checkboxes)})


class AoHistoryDlg(wx_gui.HistoryDialog):

    if wx.Platform == '__WXMAC__':
        PRE_PAGE_ITEM_COUNT = 20
    else:
        PRE_PAGE_ITEM_COUNT = 15

    NORMAL_SQL = "SELECT dir, url, name, download_count, domain, date " \
                 "FROM history " \
                 "ORDER BY id desc " \
                 "LIMIT ?, ?"

    NORMAL_COUNT_SQL = "SELECT COUNT(id) FROM history"

    SEARCH_SQL = "SELECT dir, url, name, download_count, domain, date " \
                 "FROM history " \
                 "WHERE name LIKE '%{}%' " \
                 "LIMIT ?, ?"

    TAG_SQL = "SELECT h.dir, h.url, h.name, h.download_count, h.domain, h.date " \
              "FROM history AS h " \
              "INNER JOIN history_related_tag AS r ON h.id = r.history_id " \
              "INNER JOIN tags AS t ON r.tag_id = t.id " \
              "WHERE t.tag IN ({}) " \
              "GROUP BY h.id " \
              "ORDER BY h.id desc " \
              "LIMIT ?, ?"

    TAG_COUNT_SQL = "SELECT COUNT(DISTINCT h.id) " \
                    "FROM history AS h " \
                    "INNER JOIN history_related_tag AS r ON h.id = r.history_id " \
                    "INNER JOIN tags AS t ON r.tag_id = t.id " \
                    "WHERE t.tag IN ({})"

    def __init__(self, parent):
        super(AoHistoryDlg, self).__init__(parent)
        self.con = wx.GetApp().con

        self.cur_page = 1
        self.selected_tags = []
        self.history_dir = {}
        self.history_url = {}

        self.total_items = 0
        self.sql = ""
        self.is_search = False

        # Populate the tags.
        self.init_tag()
        self.init_history()

    def init_history(self):
        self.sql = self.NORMAL_SQL
        self.cur_page = 1
        self.total_items = self.get_total_items(self.NORMAL_COUNT_SQL)
        self.history_populate()
        self.refresh_page()

    def init_tag(self):
        """初始化标签栏面板"""
        tags_data = self.con.select("SELECT tag FROM tags")
        tag_bitmap = wx_gui.svg_bitmap(wx_gui.TAG)
        for tag in tags_data:
            tag_btn = custom_outlinebtn.PlateButton(self.panel_1, label=tag[0]+" ", bmp=tag_bitmap,
                                                    style=custom_outlinebtn.PB_STYLE_TOGGLE)
            self.sizer_tags.Add(tag_btn, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
            tag_btn.Bind(wx.EVT_TOGGLEBUTTON, self.on_tag)

    def get_total_items(self, sql: str, *args):
        result = self.con.select_one(sql, *args)
        if not result:
            return 0
        return result[0]

    def refresh_page(self):
        domain_start = (self.cur_page - 1) * self.PRE_PAGE_ITEM_COUNT + 1
        domain_end = self.cur_page * self.PRE_PAGE_ITEM_COUNT
        if self.total_items < domain_start:
            self.next_btn.Disable()
            cur_items = "0-0"
        elif domain_end >= self.total_items >= domain_start:
            self.next_btn.Disable()
            cur_items = f"{domain_start}-{self.total_items}"
        else:
            self.next_btn.Enable()
            cur_items = f"{domain_start}-{domain_end}"

        if self.cur_page > 1:
            self.prev_btn.Enable()
        else:
            self.prev_btn.Disable()

        self.total_items_st.SetLabel(str(self.total_items))
        self.cur_items_st.SetLabel(cur_items)
        self.history_listctrl.SetFocus()

    def history_populate(self):
        data = self.con.select(self.sql, ((self.cur_page-1)*self.PRE_PAGE_ITEM_COUNT, self.PRE_PAGE_ITEM_COUNT))
        self.history_listctrl.DeleteAllItems()
        self.history_dir.clear()
        self.history_url.clear()

        for _index, _value in enumerate(data):
            name = _value[2] or _value[1]
            self.history_listctrl.InsertItem(_index, name)
            self.history_dir[_index] = _value[0]
            self.history_url[_index] = _value[1]
            for col, _sub_value in enumerate(_value[3:], start=1):
                self.history_listctrl.SetItem(_index, col, str(_sub_value))

            if _index % 2:
                self.history_listctrl.SetItemBackgroundColour(_index, "white")
            else:
                self.history_listctrl.SetItemBackgroundColour(_index, wx.Colour(245, 245, 245))

    def clip(self, item_index):
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self.history_url[item_index]))
            wx.TheClipboard.Close()

    def on_next(self, event):
        self.cur_page += 1
        self.history_populate()
        self.refresh_page()

    def on_prev(self, event):
        self.cur_page -= 1
        self.history_populate()
        self.refresh_page()

    def on_tag(self, event):
        tag_btn = event.GetEventObject()
        value = event.GetString().strip()
        if self.is_search:
            self.search_ctrl.Clear()
            self.is_search = False
        if tag_btn.IsPressed():
            self.selected_tags.append("'{}'".format(value))
        else:
            self.selected_tags.remove("'{}'".format(value))
        if len(self.selected_tags) == 0:
            self.sql = self.NORMAL_SQL
            count_sql = self.NORMAL_COUNT_SQL
        else:
            self.sql = self.TAG_SQL.format(', '.join(self.selected_tags))
            count_sql = self.TAG_COUNT_SQL.format(', '.join(self.selected_tags))

        self.cur_page = 1
        self.total_items = self.get_total_items(sql=count_sql)
        self.history_populate()
        self.refresh_page()

    def on_folder(self, event):
        index = event.Index
        folder = self.history_dir[index]
        if folder:
            if os.path.exists(folder):
                wx.LaunchDefaultBrowser(folder, flags=0)
            else:
                wx.MessageBox("目标文件夹被删除或移动", "目录错误", wx.OK | wx.ICON_ERROR, parent=self)
        else:
            wx.MessageBox("该记录下载失败, 目标文件夹不存在", "目录错误", wx.OK | wx.ICON_ERROR, parent=self)

    def on_text(self, event):
        value = event.GetString()
        if self.is_search and not value:
            self.is_search = False
            self.init_history()

    def on_search(self, event):
        self.cur_page = 1
        self.is_search = True
        # 清除选择的tag
        self.selected_tags.clear()
        for item in self.sizer_tags.GetChildren():
            tag_btn = item.GetWindow()
            tag_btn._SetState(custom_outlinebtn.PLATE_NORMAL)

        value = event.GetString()
        if not value:
            return
        sql = "SELECT COUNT(*) " \
              "FROM history " \
              "WHERE name LIKE '%{}%'".format(value)
        self.total_items = self.get_total_items(sql)

        self.sql = self.SEARCH_SQL.format(value)
        self.history_populate()
        self.refresh_page()

    def on_right_click(self, event):
        popup_clip_id = wx.NewIdRef()
        self.Bind(wx.EVT_MENU, lambda evt: self.clip(event.Index), id=popup_clip_id)

        menu = wx.Menu()
        menu.Append(popup_clip_id, "复制历史网址到剪贴板")
        self.PopupMenu(menu)
        menu.Destroy()


class AoSyncDlg(wx_gui.SyncDialog):

    def __init__(self, parent):
        super(AoSyncDlg, self).__init__(parent)
        self.cfg = wx.GetApp().cfg
        self.con = wx.GetApp().con

        self.sync_dir = self.cfg.Read("/Sync/sync_dir")
        self.tabs = ("Archdaily", "Huaban", "Pinterest")

        self.cover_queue = Queue()
        self.init_properties()

    def load_account_info(self, site: str):
        """从数据库载入账户信息"""
        user_id = self.GetParent().sync.account_state.get(site)
        if user_id:
            sql = "SELECT * FROM sync_account WHERE user_id = ? AND site = ?"
            result = self.con.select_one(sql, (user_id, site.lower()))
        else:
            sql = "SELECT * FROM sync_account WHERE site = ?"
            result = self.con.select_one(sql, (site.lower(), ))
        return result

    def load_boards_info(self, user_id: int, site: str):
        """从数据库载入Board信息"""
        sql = "SELECT board_id, site, name, state, total FROM sync_boards WHERE user_id = ? AND site = ?"
        result = self.con.select(sql, (user_id, site.lower()))
        return result

    def init_properties(self):
        # 判断同步状态
        status = self.cfg.ReadBool("/Sync/sync_status", defaultVal=False)
        if status:
            self.status_label_1.SetLabel("同步开启")
        else:
            self.status_label_1.SetLabel("同步关闭")
        self.sync_toggle_ctrl.SetValue(status)
        self.status_label_2.Show(status)

        # 初始化同步面板
        # board封面更新线程启动
        update_cover_thread = utils.UpdateCover(self, self.cover_queue, self.con)
        update_cover_thread.setDaemon(True)
        update_cover_thread.start()

        for site in self.tabs:
            account_panel = AoAccountPanel(self.account_nb)

            account_panel.site = site

            # 载入账户信息
            account_info = self.load_account_info(site)
            # (user_id, site, name, slug, email, url, avatar_url, avatar_data, registry_t, update_t)
            if account_info:
                # avatar图片
                if account_info[7]:
                    avatar_bitmap = get_bitmap_from_embedded(account_info[7], scale=(100, 100))
                    account_panel.avatar.SetBitmap(avatar_bitmap)
                # 账户名称
                account_panel.user_name.SetLabel(account_info[2] or "NnllUser")
                # 账户邮箱/其他
                account_panel.email.SetLabel(account_info[4] or "")
            else:
                account_panel.email.SetLabel(f"没有检测到{site}账户信息, \n请确认是否已正常登录")
                self.account_nb.AddPage(account_panel, site)
                continue

            # 载入收藏board信息
            user_id = account_info[0]
            for board_info in self.load_boards_info(user_id, site):
                # (board_id, site, name, state, total)
                board_panel = AoBoardPanel(account_panel.boards_panel)
                board_panel.SetMinSize((176, 176))

                # board封面: 单独线程更新board封面,避免Sync_dlg界面载入时间过长和卡顿
                cache_cover_bitmap = self.GetParent().sync_cover_cache.get((board_info[0], board_info[1]))
                if cache_cover_bitmap:      # 存在封面缓存
                    board_panel.board_cover.SetBitmap(cache_cover_bitmap)
                else:                       # 没有封面缓存
                    self.cover_queue.put((board_panel.GetId(), board_info))

                # board名称
                board_panel.board_name.SetLabel(str(board_info[2]))

                # board细节
                board_panel.board_detail.SetLabel(f"{board_info[4]} 收藏")

                # board开放状态
                if not board_info[3]:
                    board_panel.state_sb.Show()
                account_panel.items_sizer.Add(board_panel, 0, wx.ALL | wx.EXPAND, 5)

            self.account_nb.AddPage(account_panel, site)
        # 封面更新线程退出信号: None
        self.cover_queue.put(None)

    def call_update_cover(self, board_panel_id, cover_bitmap, cache_key: tuple):
        board_panel = self.FindWindowById(board_panel_id)
        try:
            board_panel.board_cover.SetBitmap(cover_bitmap)
        except AttributeError:  # 同步GUI界面在完成封面之前,被关闭,会导致AttributeError错误
            pass
        else:
            self.GetParent().sync_cover_cache[cache_key] = cover_bitmap

    def on_sync(self, event):
        status = event.IsChecked()

        if status and not self.sync_dir:
            dlg = wx.DirDialog(self, "选择同步文件夹:",
                               style=wx.DD_DEFAULT_STYLE
                                     | wx.DD_DIR_MUST_EXIST
                                     # | wx.DD_CHANGE_DIR
                               )
            dlg.ShowModal()
            self.sync_dir = dlg.GetPath()
            dlg.Destroy()
            if self.sync_dir:
                self.cfg.Write("/Sync/sync_dir", self.sync_dir)
            else:
                event.GetEventObject().SetValue(False)
                return

        if status:
            self.status_label_1.SetLabel("同步开启")
            # Sync对象定时运行
            interval = self.cfg.ReadInt("/Sync/sync_interval", defaultVal=600000)
            self.GetParent().sync.start()
            self.GetParent().sync_timer.Start(interval)
            self.GetParent().sync_status_ctrl.SetBitmap(svg_bitmap(SYNC, 24, 24, colour=wx.WHITE))
        else:
            self.status_label_1.SetLabel("同步关闭")
            self.GetParent().sync.stop()
            self.GetParent().sync_timer.Stop()
            self.GetParent().sync_status_ctrl.SetBitmap(svg_bitmap(SYNC_DISABLE, 24, 24, colour=wx.WHITE))
        self.status_label_2.Show(status)

        self.cfg.WriteBool("/Sync/sync_status", status)


class AoAccountPanel(wx_gui.AccountPanel):
    def __init__(self, *args, **kwargs):
        super(AoAccountPanel, self).__init__(*args, **kwargs)

        self.cfg = wx.GetApp().cfg
        self.site = ""

    def on_open_site_dir(self, event):
        site_dir = os.path.join(self.GetTopLevelParent().sync_dir, self.site)
        if not os.path.isdir(site_dir):
            os.makedirs(site_dir)
        if wx.Platform == '__WXMAC__':
            os.system(f"open '{site_dir}'")
        else:
            wx.LaunchDefaultBrowser(site_dir, flags=0)


class AoBoardPanel(wx_gui.BoardPanel):
    def __init__(self, *args, **kwargs):
        super(AoBoardPanel, self).__init__(*args, **kwargs)

        self.board_cover.Bind(wx.EVT_LEFT_DCLICK, self.on_folder)
        self.board_cover.Bind(wx.EVT_ENTER_WINDOW, self.on_enter_hand)
        self.board_cover.Bind(wx.EVT_LEAVE_WINDOW, self.on_leave_hand)

    def on_folder(self, event):
        site = self.GetGrandParent().site
        sync_dir = self.GetTopLevelParent().sync_dir

        board_dir = os.path.join(sync_dir, site, self.board_name.GetLabel())
        if os.path.exists(board_dir):
            wx.LaunchDefaultBrowser(board_dir, flags=0)

    def on_enter_hand(self, event):
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        event.Skip()

    def on_leave_hand(self, event):
        self.SetCursor(wx.NullCursor)
        event.Skip()


class AoTaskPanel(wx_gui.TaskPanel):
    """
    任务面板
        task_info = {
            "id": int,
            "name": str,  # 项目标题
            "status": int,  # 状态
            "date": str,  # 启动时间
            "domain": str,  # 域名
            "url": str,  # 项目url
            "dir": str,  # 下载目录
            "total_count": int,  # 解析总数
            "download_count": int,  # 实际下载数
            "is_folder": bool,  # 是否为单图片
            "is_show": bool,  # 是否显示历史
            "tags": str,  # 标签
            # ...
        }
    """
    def __init__(self, *args, **kwargs):
        super(AoTaskPanel, self).__init__(*args, style=wx.BORDER_NONE)
        self.task_info = kwargs
        self.con = wx.GetApp().con

        self.is_range_set = False  # 判断进度条Range是否已设置
        self.download_thread_count = 0

        # 任务对象
        self.task = None

        # 初始化任务名称
        task_name = self.task_info.get("name") or self.task_info.get("url")
        self.task_name.SetLabel(task_name)

        # 初始化进度条
        self.gauge_value = self.task_info.get("download_count", 0)
        if self.task_info.get("total_count"):
            self.gauge.SetRange(self.task_info["total_count"])
            if self.gauge_value != self.gauge.GetRange():
                self.gauge.SetBarColor(wx.Colour(244, 84, 63))
            self.gauge.SetValue(self.gauge_value)

        # 初始化标签
        if self.task_info.get("tags"):
            tags = self.task_info["tags"].split(", ")
        else:
            tags = ("未分类",)
        for tag in tags:
            tag_btn = custom_outlinebtn.PlateButton(self, label=" {} ".format(tag))
            tag_btn.SetLabelColor(normal=wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT), hlight=wx.WHITE)
            self.sizer_tags.Add(tag_btn, 0, wx.ALIGN_CENTER_VERTICAL, 0)

        # # 初始化文件数
        self.imgs_sum.SetLabel("[{} / {}]".format(self.gauge_value, self.task_info.get("total_count", "解析中...")))

        # 事件绑定
        self.Bind(wx.EVT_SIZE, self.on_size)

    def run(self):
        self.task_info["status"] = 0

        # GUI更新
        self.pause_btn.Enable()
        self.GetTopLevelParent().refresh_logo(update=1)
        self.imgs_sum.SetLabel("[0 / 解析中...]")

        self.download_thread_count = wx.GetApp().cfg.ReadInt("/General/download_thread_count", defaultVal=5)
        self.task = TaskItem(parent=self, download_thread_count=self.download_thread_count)
        self.task.run()

    def call_imgs_sum(self, imgs_sum: int):
        """注册解析后得到的图像总数"""
        self.imgs_sum.SetLabel("[{} / {}]".format(self.gauge_value, imgs_sum))
        if imgs_sum:
            self.gauge.SetRange(imgs_sum)
            self.gauge.Refresh()
            self.is_range_set = True

        sql = "UPDATE history SET status=?, total_count=? WHERE url=?"
        self.con.execute(sql, (1, imgs_sum, self.task_info["url"]))

    def call_task_name(self, task_dir: str):
        """注册解析后得到的任务友好名称"""
        task_name = os.path.basename(task_dir)
        self.task_info["name"] = task_name
        self.task_name.SetLabel(task_name)
        # 更新数据库
        sql = "UPDATE history SET name=?, domain=?, dir=? WHERE url=?"
        self.con.execute(sql, (task_name, self.task_info["domain"], task_dir, self.task_info["url"]))

        # 根据任务名称设置下载目录
        self.task_info["dir"] = task_dir
        self.folder_btn.Enable()

    # def call_preview(self, html, css):
    #     """预览阅读器, 测试用途"""
    #     preview = wx_gui.PreviewPanel(self, )

    def call_abort(self, msg):
        """任务主动中止"""
        abort_dlg = wx.MessageDialog(self, msg, "任务中止", wx.OK | wx.OK_DEFAULT | wx.ICON_INFORMATION)
        abort_dlg.ShowModal()
        abort_dlg.Destroy()

    def call_thread_done(self):
        """注册所有download线程正常结束事件"""
        self.download_thread_count -= 1
        if self.download_thread_count == 0:
            if self.task_info.get("is_delete"):
                self.Destroy()
                return
            if self.gauge_value != self.gauge.GetRange():
                self.gauge.SetBarColor(wx.Colour(244, 84, 63))
            self.pause_btn.Disable()
            self.GetTopLevelParent().refresh_logo(update=-1)

    def call_refresh_gauge(self, url: str, prop: tuple):
        """注册刷新进度条"""
        self.gauge_value += 1

        if prop:
            sql = "UPDATE urls SET status=1, name=?, type=?, width=?, height=?, bytes=? " \
                  "WHERE task_id=? AND url=?"
            self.con.execute(sql, (*prop[0], *prop[1], prop[2], self.task_info["id"], url))
        else:
            sql = "UPDATE urls SET status=2 WHERE task_id=? AND url=?"
            self.con.execute(sql, (self.task_info["id"], url))

        sql = "UPDATE history SET download_count=? WHERE url=?"
        self.con.execute(sql, (self.gauge_value, self.task_info["url"]))

        if self.is_range_set:
            self.gauge.SetValue(self.gauge_value)
            self.gauge.Refresh()
            self.imgs_sum.SetLabel("[{} / {}]".format(self.gauge_value, self.gauge.GetRange()))
        else:
            self.imgs_sum.SetLabel("[{} / {}]".format(self.gauge_value, "解析中..."))

    def on_size(self, event):
        self.gauge.Refresh()
        event.Skip()

    def on_pause(self, event):
        if self.task.pause_event.is_set():
            self.task.pause()
            svg = RESTART
        else:
            self.task.resume()
            svg = PAUSE
        self.pause_btn.SetBitmap(svg_bitmap(svg, colour=wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT)))
        self.pause_btn.SetBitmapCurrent(svg_bitmap(svg))

    def on_delete(self, event):
        # 删除task任务面板
        parent_sizer = self.GetContainingSizer()
        parent_sizer.Detach(self)
        self.Hide()
        parent_sizer.Layout()
        self.GetTopLevelParent().sizer_7.Layout()
        # 更新数据库history表is_show字段
        sql = "UPDATE history SET is_show=0 WHERE id=?"
        self.con.execute(sql, (self.task_info["id"],))
        # 中止任务并更新运行任务计数: -1
        # if hasattr(self, "task") and self.task.is_running():
        if self.task and self.task.is_running():
            self.task.stop()
            self.GetTopLevelParent().refresh_logo(update=-1)
            self.task_info["is_delete"] = True
        else:
            self.Destroy()

    def on_folder(self, event):
        folder_dir = self.task_info.get("dir")
        # if not (folder_dir and os.path.exists(folder_dir)):
        if not os.path.exists(folder_dir):
            folder_dir = self.task_info["url"]
        if wx.Platform == '__WXMAC__':
            os.system(f"open '{folder_dir}'")
        else:
            wx.LaunchDefaultBrowser(folder_dir, flags=0)

    def on_tags_popup(self, event):
        btn = event.GetEventObject()
        pos = btn.ClientToScreen((0, 0))

        if self.task_info.get("tags"):
            pre_tags = self.task_info["tags"].split(", ")
            popup_win = TagsPopupCtl(self, *pre_tags)
            popup_win.tags_edit_ctrl.SetValue(self.task_info["tags"])
        else:
            popup_win = TagsPopupCtl(self)

        btn_size = btn.GetSize()
        popup_size = popup_win.GetSize()

        popup_win.Position(pos, (0, btn_size[1]-popup_size[1]))
        popup_win.Popup()

    def update_tags(self, tags: list):
        # 更新任务信息
        self.task_info["tags"] = ", ".join(tags)
        # 删除旧标签
        self.sizer_tags.Clear(delete_windows=True)
        self.sizer_tags.Layout()

        for tag in tags:
            tag_btn = custom_outlinebtn.PlateButton(self, label=" {} ".format(tag))
            tag_btn.SetLabelColor(normal=wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT), hlight=wx.WHITE)
            self.sizer_tags.Add(tag_btn, 0, wx.ALIGN_CENTER_VERTICAL, 0)
        self.sizer_7.Layout()

    def update_tags_db(self, tags: list, pre_tags):
        add_tags = set(tags).difference(set(pre_tags))
        delete_tags = set(pre_tags).difference(set(tags))

        insert_sql = "INSERT OR IGNORE INTO tags (tag) VALUES (?)"
        select_sql = "SELECT id FROM tags WHERE tag = ?"
        related_insert_sql = "INSERT INTO history_related_tag VALUES (?, ?)"
        for tag in add_tags:
            self.con.execute(insert_sql, (tag,))
            tag_id = self.con.select_one(select_sql, (tag,))
            self.con.execute(related_insert_sql, (self.task_info["id"], tag_id[0]))

        related_delete_sql = """
        DELETE FROM 
            history_related_tag 
        WHERE 
            history_id = ? AND tag_id = (SELECT id FROM tags WHERE tag = ?)
        """
        for tag in delete_tags:
            self.con.execute(related_delete_sql, (self.task_info["id"], tag))


class TBicon(wx.adv.TaskBarIcon):
    TBMENU_SETUP = wx.NewIdRef()
    TBMENU_BUG = wx.NewIdRef()
    TBMENU_DONATE = wx.NewIdRef()
    TBMENU_HELP = wx.NewIdRef()
    TBMENU_ABOUT = wx.NewIdRef()
    TBMENU_CLOSE = wx.NewIdRef()

    def __init__(self, frame):
        # wx.adv.TaskBarIcon.__init__(self, wx.adv.TBI_DOCK)
        wx.adv.TaskBarIcon.__init__(self)
        self.frame = frame

        _icon = wx.NullIcon
        _icon.CopyFromBitmap(MyBitmap(wx_gui.APP_TB_ICON))
        self.SetIcon(_icon, f'{constants.APP_DISPLAY_NAME}\n发行版本: {LooseVersion(version.VERSION)}')

        self.Bind(wx.EVT_MENU, self.on_taskbar_setup, id=self.TBMENU_SETUP)
        self.Bind(wx.EVT_MENU, self.on_open_url, id=self.TBMENU_HELP)
        self.Bind(wx.EVT_MENU, self.on_open_url, id=self.TBMENU_BUG)
        self.Bind(wx.EVT_MENU, self.on_taskbar_donate, id=self.TBMENU_DONATE)
        self.Bind(wx.EVT_MENU, self.on_taskbar_about, id=self.TBMENU_ABOUT)
        self.Bind(wx.EVT_MENU, self.on_taskbar_close, id=self.TBMENU_CLOSE)

        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, self.on_show)

    def CreatePopupMenu(self):
        menu = wx.Menu()
        menu.Append(self.TBMENU_SETUP, "设置")
        menu.AppendSeparator()
        menu.Append(self.TBMENU_HELP, "获取帮助")
        menu.Append(self.TBMENU_BUG, "提交Bug")
        menu.Append(self.TBMENU_ABOUT, "关于")
        menu.AppendSeparator()
        menu.Append(self.TBMENU_DONATE, "赞赏")
        menu.Append(self.TBMENU_CLOSE, "退出")

        return menu

    def on_taskbar_setup(self, event):
        setup_dlg = AoSettingDlg(self.frame)
        setup_dlg.ShowModal()

    def on_open_url(self, event):
        object_id = event.GetId()
        if object_id == self.TBMENU_HELP:
            wx.LaunchDefaultBrowser(constants.HELP_URL, flags=0)
        elif object_id == self.TBMENU_BUG:
            wx.LaunchDefaultBrowser(constants.FEEDBACK_URL, flags=0)

    def on_taskbar_donate(self, event):
        donate_dlg = AoDonateDlg(self.frame)
        donate_dlg.Show()

    def on_taskbar_about(self, event):
        about_dlg = AoAbout(self.frame)
        about_dlg.ShowModal()

    def on_taskbar_close(self, event):
        """Destroy the taskbar icon and frame from the taskbar icon itself"""
        wx.CallAfter(self.frame.Close)

    def on_show(self, event):
        if self.frame.IsIconized():
            self.frame.Iconize(False)
        if not self.frame.IsShown():
            self.frame.Show(True)
        self.frame.Raise()


class AoApp(wx_gui.MyApp):

    def OnInit(self):

        # Single app instance.
        self.instance = wx.SingleInstanceChecker(name="ArchOctopus-%s" % wx.GetUserId())
        if self.instance.IsAnotherRunning():
            wx.MessageBox("ArchOctopus 已经启动...", constants.APP_DISPLAY_NAME)
            return False

        # --------------

        self.locale = wx.Locale(wx.LANGUAGE_DEFAULT)

        self.SetAppName(constants.APP_NAME)
        self.SetAppDisplayName(constants.APP_DISPLAY_NAME)
        self.version = version.VERSION

        self.installDir = os.path.abspath(os.path.dirname(__file__))

        self.cfg = get_config()

        self.con = AoDatabase(db=self.get_database_file())
        # self.con = AoDatabase()

        mainFrame = AoMainFrame(None, wx.ID_ANY, constants.APP_DISPLAY_NAME)
        self.SetTopWindow(mainFrame)
        mainFrame.Show()

        return True

    def OnExit(self):
        self.con.on_close()
        return True

    def get_install_dir(self):
        """
        Returns the installation directory for ArchOctopus.
        """
        return self.installDir

    def get_resource_dir(self):
        """
        Returns the bitmaps directory for ArchOctopus.
        """
        bitmaps_dir = os.path.join(self.installDir, "gui", "resource")
        return bitmaps_dir

    def get_database_file(self):
        """
        Returns the database file for ArchOctopus.
        """
        database_file = os.path.join(self.installDir, "data", "{}.db".format(constants.APP_NAME))
        return database_file


def main():
    """

    :return:
    """
    # logging config
    log_file = os.path.join(os.path.dirname(__file__), "log", constants.APP_NAME+".log")
    log_conf = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "simple": {'format': '%(asctime)s [%(name)s:%(lineno)d] [%(levelname)s]-> %(message)s'},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                # "level": "INFO",
                # "level": "DEBUG",
                "formatter": "simple",
                "stream": "ext://sys.stdout"
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                # "level": "INFO",
                "formatter": "simple",
                "filename": log_file,
                "maxBytes": 1024 * 1024 * 10,  # 10 MB
                "backupCount": 20,
                "encoding": "utf8"
            },
        },
        "loggers": {
            constants.APP_NAME: {
                "level": "INFO",
                "handlers": ["file", "console"],
                "propagate": "no"
            },
            "sync": {
                "level": "DEBUG",
                "handlers": ["file", "console"],
                "propagate": "no"
            }
        },

    }
    logging.config.dictConfig(log_conf)
    logger = logging.getLogger(constants.APP_NAME)

    logger.info('ArchOctopus start running...')
    ArchOctopus = AoApp()
    ArchOctopus.MainLoop()


if __name__ == "__main__":
    main()

    # import sys
    #
    # if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    #     print('running in a PyInstaller bundle')
    # else:
    #     print('running in a normal Python process')
