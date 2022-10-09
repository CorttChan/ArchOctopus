"""
ArchOctopus readability 模块

raw_html --> readability --> css format(firefox reader mode likely) --> wkhtmltopdf --> pdf output

reference:
mozilla Reader mode: https://searchfox.org/mozilla-release/source/toolkit/components/reader/Readability.js#879
                     https://github.com/mozilla/readability
                     https://github.com/mozilla/readability/blob/master/Readability.js
how to the Reader works: https://newbedev.com/how-does-firefox-reader-view-operate

python wrapper for mozilla's Readability.js: https://github.com/alan-turing-institute/ReadabiliPy
python Readability: https://github.com/kingwkb/readability

"""

import os.path
import re
import logging
import json
# import copy
from pprint import pprint
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4 import element

logger = logging.getLogger(__file__)


class Readability:
    """
    Runs readability.

    Workflow:
        1. Prep the document by removing script tags, css, etc.
        2. Build readability's DOM tree.
        3. Grab the article content from the current dom tree.
        4. Replace the current DOM tree with the new one.
        5. Read peacefully.
    """

    def __init__(self, raw_html, raw_url, **kwargs):
        self.html = raw_html
        self.url = raw_url
        self.options = kwargs

    def parse(self):
        result = {
            "title": "",
            "byline": "",
            "dir": "",
            "content": "",
            "textContent": "",
            "length": "",
            "excerpt": "",
            "siteName": ""
        }
        return result

    def render(self) -> str:
        html = str()
        return html


if __name__ == '__main__':
    pass
