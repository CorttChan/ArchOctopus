# import unittest
#
#
# class MyTestCase(unittest.TestCase):
#     def test_something(self):
#         self.assertEqual(True, False)  # add assertion here
#
#
# if __name__ == '__main__':
#     unittest.main()

from archoctopus import usage
from . import TestApp


def test_usage():
    tmp_usage = usage.Usage(parent=TestApp())
    print(tmp_usage._build_data())


test_usage()
