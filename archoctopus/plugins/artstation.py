"""
ArtStation
url: https://www.artstation.com/
"""

# name: artstation.py
# version: 0.0.1
# date: 2022/2/9 21:17
# desc:

from archoctopus.plugins import BaseParser


class Parser(BaseParser):
    def __init__(self, *args, **kwargs):
        BaseParser.__init__(self, *args, **kwargs)

        self.friend_name = "ArtStation"

    def route(self, *args, **kwargs):
        return None
