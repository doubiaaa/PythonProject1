#!/bin/bash

# 执行夜间复盘脚本
cd "$(dirname "$0")"
python scripts/nightly_replay.py
