"""
解析测试结果，生成当前插件测试结果的json文件
"""
import os
import re
import json
from datetime import datetime, timedelta


os.chdir(os.path.dirname(__file__))


def get_plugins_name(plugins_path):
    """获取插件名称(不含扩展名)"""
    plugins_name_list = []
    for file in os.listdir(plugins_path):
        if not file.startswith("_") and file.endswith(".py"):
            plugins_name_list.append(file[:-3])
    return plugins_name_list


def get_test_result(result_file):
    test_result = {}

    status_pat = re.compile("(test_.*?) \\(__main__\\.ParseTestCase\\).*? \\.\\.\\. (ok|FAIL|ERROR)\n", flags=re.S)
    name_pat = re.compile("test_(.*)_")
    with open(result_file, 'r', encoding='utf-8') as f:
        result = status_pat.findall(f.read())
        for r in result:
            name = name_pat.match(r[0]).group(1)
            status = True if r[1] == "ok" else False
            if name in test_result:
                test_result[name]["status"] = status
                test_result[name]["tests"].append(r)
            else:
                test_result[name] = {"status": status, "tests": [r, ]}
    return test_result


def build_result_json():
    """"""
    plugins_path = "../archoctopus/plugins"
    test_result = get_test_result('./TestResult.txt')

    date_now = datetime.utcnow()+timedelta(hours=8)
    result_dict = {"date": date_now.strftime("%Y-%m-%d %H:%M:%S"), "result": {}}
    for name in get_plugins_name(plugins_path):
        if name in test_result:
            result_dict["result"][name] = test_result[name]
        else:
            result_dict["result"][name] = {"status": None, }

    with open("./test_plugin_result", "w", encoding="utf-8") as f:
        json.dump(result_dict, f)


if __name__ == '__main__':
    build_result_json()
