#!/usr/bin/python3
# -*- coding: utf-8 -*-
# @Time    : 2022/9/6 21:59
# @Author  : CorttChan
# @Email   : cortt.me@gmail.com
# @File    : update_nsi.py

"""
更新dist/ArchOctopus目录中的文件列表到 'nsis-setup.nsi' 配置文件中, 生成 'build.nsi'.
'build.nsi'用于makensis打包
"""

import os

os.chdir(os.path.dirname(__file__))

APPDIR = "..\\dist\\ArchOctopus"
BASIC_NSI = "nsis-setup.nsi"
BUILD_NSI = "build.nsi"


def build_nsi():
    with open(BASIC_NSI, "r", encoding="utf-8") as tf:
        with open(BUILD_NSI, "w", encoding="utf-8") as bf:
            for line in tf.readlines():
                bf.write(line)
                # 添加安装文件
                if line.startswith("  ;ADD INSTALL FILES HERE"):
                    for root, dirs, files in os.walk(APPDIR):
                        inst_dir = root.replace(APPDIR, "$INSTDIR")
                        bf.write("  SetOutPath \"{}\"\n".format(inst_dir))
                        for file in files:
                            bf.write("  File \"{}\"\n".format(os.path.join(root, file)))
                # 添加卸载文件
                elif line.startswith("  ;ADD UNINSTALL FILES HERE"):
                    for file in os.listdir(APPDIR):
                        file_path = os.path.join(APPDIR, file)
                        if os.path.isfile(file_path):
                            bf.write("  Delete \"{}\"\n".format(os.path.join("$INSTDIR", file)))
                        elif os.path.isdir(file_path):
                            bf.write("  RMDir /r \"{}\"\n".format(os.path.join("$INSTDIR", file)))


if __name__ == '__main__':
    build_nsi()
