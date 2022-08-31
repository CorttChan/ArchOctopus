import unittest
from queue import Queue

from archoctopus.plugins import huaban


class MyTestCase(unittest.TestCase):

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
        self.assertEqual(board_count, 61)


if __name__ == '__main__':
    unittest.main()
