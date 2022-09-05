import unittest
from queue import Queue

import sys
import os

os.chdir(os.path.dirname(__file__))
sys.path.extend(["../", ])

from archoctopus.plugins import huaban, archdaily, zcool, pinterest


def run_parser(url, parser) -> tuple:
    """运行解析线程"""
    tmp_queue = Queue()
    parse_thread = parser(
        parent=None,
        url=url,
        task_id=0,
        parse_queue=tmp_queue,
        pause_event=None,
        running_event=None,
        threads_count=1,
        cookies=None,
        proxies=None
    )
    parse_thread.setDaemon(True)
    parse_thread.start()
    parse_thread.join()

    name = parse_thread.task_name
    count = parse_thread.count

    return name, count


class ParseTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self.queue = Queue()

    def test_huaban_board(self):
        """
        测试'huaban.py'解析board函数
        测试链接: https://huaban.com/boards/17902481
        测试时间: 2022/09/01
        board信息:
            名称: Board-'娉小小-建筑之美'
            文件数: 439
        """
        url = "https://huaban.com/boards/17902481"
        name, count = run_parser(url=url, parser=huaban.Parser)

        self.assertEqual(name, "Board-'娉小小-建筑之美'")
        self.assertGreaterEqual(count, 439)

    def test_huaban_pin(self):
        """
        测试'huaban.py'解析pin函数
        测试链接: https://huaban.com/pins/4946795412
        测试时间: 2022/09/01
        board信息:
            名称: Pin-4946795412
            文件数: 61
        """
        url = "https://huaban.com/pins/4946795412"
        name, count = run_parser(url=url, parser=huaban.Parser)

        self.assertEqual(name, "Pin-4946795412")
        self.assertGreaterEqual(count, 41)

    def test_archdaily_article(self):
        """
        测试'archdaily.py'解析article函数
        测试链接: https://www.archdaily.cn/cn/973005/zhe-jiang-da-xue-jian-zhu-she-ji-yan-jiu-
                 yuan-zi-jin-yuan-qu-zhe-jiang-da-xue-jian-zhu-she-ji-yan-jiu-yuan
        测试时间: 2022/09/02
        board信息:
            名称: 浙江大学建筑设计研究院紫金院区 / 浙江大学建筑设计研究院
            文件数: 28
        """
        url = "https://www.archdaily.cn/cn/973005/zhe-jiang-da-xue-jian-zhu-she-ji-yan-jiu-" \
              "yuan-zi-jin-yuan-qu-zhe-jiang-da-xue-jian-zhu-she-ji-yan-jiu-yuan"
        name, count = run_parser(url=url, parser=archdaily.Parser)

        self.assertEqual(name, "浙江大学建筑设计研究院紫金院区 _ 浙江大学建筑设计研究院")
        self.assertGreaterEqual(count, 28)

    def test_zcool_article(self):
        """
        测试'zcool.py'解析article函数
        测试链接: https://www.zcool.com.cn/work/ZNTM5NjI3MzY=.html
        测试时间: 2022/09/02
        board信息:
            名称: 新中式！_空间_家装设计_金该画图壹哥
            文件数: 16
        """
        url = "https://www.zcool.com.cn/work/ZNTM5NjI3MzY=.html"
        name, count = run_parser(url=url, parser=zcool.Parser)

        self.assertEqual(name, "新中式！_空间_家装设计_金该画图壹哥")
        self.assertEqual(count, 16)

    def test_pinterest_pin(self):
        """
        测试'pinterest.py'解析pin函数
        测试链接: https://www.zcool.com.cn/work/ZNTM5NjI3MzY=.html
        测试时间: 2022/09/02
        board信息:
            名称: 新中式！_空间_家装设计_金该画图壹哥
            文件数: 16
        """
        pass

    def test_pinterest_board(self):
        """
        测试'pinterest.py'解析board函数
        测试链接: https://www.zcool.com.cn/work/ZNTM5NjI3MzY=.html
        测试时间: 2022/09/02
        board信息:
            名称: 新中式！_空间_家装设计_金该画图壹哥
            文件数: 16
        """
        pass


if __name__ == '__main__':
    # unittest.main()

    with open('./TestResult.txt', 'w') as f:
        runner = unittest.TextTestRunner(stream=f, verbosity=2)
        unittest.main(testRunner=runner)

        # suite = unittest.TestSuite()
        # suite.addTest(ParseTestCase("test_zcool_article"))
        # runner.run(suite)
