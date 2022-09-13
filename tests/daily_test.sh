#!/bin/bash

python ./tests/test_plugins.py 1>>./tests/log.txt 2>&1
python ./tests/daily_test.py 1>>./tests/log.txt 2>&1
