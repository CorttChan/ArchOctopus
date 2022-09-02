import unittest
from queue import Queue

import sys
sys.path.extend(["../"])

from archoctopus.plugins import huaban, archdaily, zcool


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
        parse_thread = huaban.Parser(
            parent=None,
            url=url,
            task_id=0,
            parse_queue=self.queue,
            pause_event=None,
            running_event=None,
            threads_count=1,
            cookies=None,
            proxies=None
        )
        parse_thread.setDaemon(True)
        parse_thread.start()
        parse_thread.join()

        board_title = parse_thread.task_name
        board_count = parse_thread.count

        self.assertEqual(board_title, "Board-'娉小小-建筑之美'")
        self.assertEqual(board_count, 439)

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
        parse_thread = huaban.Parser(
            parent=None,
            url=url,
            task_id=0,
            parse_queue=self.queue,
            pause_event=None,
            running_event=None,
            threads_count=1,
            cookies=None,
            proxies=None
        )
        parse_thread.setDaemon(True)
        parse_thread.start()
        parse_thread.join()

        board_title = parse_thread.task_name
        board_count = parse_thread.count

        self.assertEqual(board_title, "Pin-4946795412")
        self.assertGreaterEqual(board_count, 41)

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
        parse_thread = archdaily.Parser(
            parent=None,
            url=url,
            task_id=0,
            parse_queue=self.queue,
            pause_event=None,
            running_event=None,
            threads_count=1,
            cookies=None,
            proxies=None
        )
        parse_thread.setDaemon(True)
        parse_thread.start()
        parse_thread.join()

        board_title = parse_thread.task_name
        board_count = parse_thread.count

        self.assertEqual(board_title, "浙江大学建筑设计研究院紫金院区 _ 浙江大学建筑设计研究院")
        self.assertGreaterEqual(board_count, 28)

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
        parse_thread = zcool.Parser(
            parent=None,
            url=url,
            task_id=0,
            parse_queue=self.queue,
            pause_event=None,
            running_event=None,
            threads_count=1,
            cookies=None,
            proxies=None
        )
        parse_thread.setDaemon(True)
        parse_thread.start()
        parse_thread.join()

        board_title = parse_thread.task_name
        board_count = parse_thread.count

        self.assertEqual(board_title, "新中式！_空间_家装设计_金该画图壹哥")
        self.assertEqual(board_count, 16)


if __name__ == '__main__':
    unittest.main()

    # suite = unittest.TestSuite()
    # suite.addTest(ParseTestCase("test_huaban_pin"))
    # suite.addTest(ParseTestCase("test_archdaily_article"))
    # runner = unittest.TextTestRunner()
    # runner.run(suite)

    # with open('TestResult.txt', 'w') as f:
    #     runner = unittest.TextTestRunner(stream=f, verbosity=2)
    #     unittest.main(testRunner=runner)
