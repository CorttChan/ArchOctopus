"""
版本信息
"""

import json
import os
import glob
from datetime import datetime, timedelta

from archoctopus.version import VERSION


def update_plugin_version() -> None:
    """
    更新插件版本信息
    """
    info = dict()
    for name in glob.glob("./archoctopus/plugins/*.py"):
        with open(name, 'r', encoding="utf-8") as plugin_file:
            for line in plugin_file.readlines():
                if line.startswith("# version:"):
                    info[os.path.basename(name)] = line[10:].strip()
                    break
            else:
                info[os.path.basename(name)] = "0.0.1"

    with open('./update/plugin_version', 'w') as f:
        json.dump(info, f)


def update_release_version() -> None:
    """
    更新软件版本信息
    """
    date_now = datetime.utcnow() + timedelta(hours=8)
    release_version_info = {
        "version": VERSION,
        "date": date_now.strftime("%Y-%m-%d %H:%M:%S"),
        "desc": "",
        "url": "https://github.com/CorttChan/ArchOctopus/releases/latest",
        "notes": "",
    }

    with open('./update/release_version', 'w') as f:
        json.dump(release_version_info, f)


if __name__ == '__main__':
    if not os.path.exists("./update"):
        os.mkdir("./update")

    update_plugin_version()
    update_release_version()
