# -*- coding: utf-8 -*-
"""快速检查项目产物（开发用）"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
sys.path.insert(0, BASE)

print("=== 文件结构 ===")
for root, dirs, files in os.walk(BASE):
    # 跳过隐藏目录
    dirs[:] = [d for d in dirs if not d.startswith(".")]
    for f in files:
        rel = os.path.relpath(os.path.join(root, f), BASE)
        print(" ", rel)

print()
print("=== config.json ===")
cfg_path = os.path.join(BASE, "config", "config.json")
if os.path.exists(cfg_path):
    with open(cfg_path, "r", encoding="utf-8") as f:
        print(f.read())
else:
    print("(不存在)")

print("=== 数据库 ===")
import sqlite3
db_path = os.path.join(BASE, "data", "word_lib.db")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )]
    print("tables:", tables)
    if "words" in tables:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(words)")]
        print("words 字段:", cols)
        cnt = conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]
        print("单词数:", cnt)
    conn.close()
else:
    print("(不存在)")

print()
print("=== 词典 API 实测 ===")
from src.dict_api import DictAPI
api = DictAPI()
for w in ("abandon", "IELTS", "persistent"):
    print(w, "->", api.query(w))
