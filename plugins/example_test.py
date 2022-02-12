"""
example_test
url: https://www.example_test.com/
"""

# name: example_test.py
# version: 0.0.1
# date: 2022/2/9 21:17
# desc:

from plugins import BaseParser


class Parser(BaseParser):
    def __init__(self, *args, **kwargs):
        BaseParser.__init__(self, *args, **kwargs)

        self.friend_name = "Example_test"

    def route(self, *args, **kwargs):
        return None
