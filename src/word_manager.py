# -*- coding: utf-8 -*-
"""单词数据管理模块 - WordManager

负责 SQLite 数据库的增删改查、复习单词列表生成、熟悉度管理。
复习列表严格遵循「昨日新词 → 近5天 → 历史随机」优先级算法。
数据库损坏时自动备份旧文件并重建新库，保证程序不因数据问题崩溃。
"""
import os
import shutil
import sqlite3
from datetime import date, timedelta

from .utils import get_db_path, ensure_dirs


class WordManager:
    """单词数据库管理器

    数据结构（表 words）：
        id            自增主键
        word          英文单词（唯一）
        phonetic      音标
        meaning       中文释义
        example       英文例句
        familiar      熟悉度 0-100（认识 +20，不认识 -20）
        review_count  复习次数
        created_at    录入时间（本地时间 "YYYY-MM-DD HH:MM:SS"）
        last_review   最近复习时间
    """

    # 熟悉度每次增减的步长
    FAMILIAR_STEP = 20

    def __init__(self, db_path: str = None):
        """初始化数据库连接并建表

        Args:
            db_path: 数据库文件路径，默认 <根目录>/data/word_lib.db
        """
        self._db_path = db_path or get_db_path()
        self._conn = None
        self._init_db()

    # ------------------------------------------------------------------ #
    # 内部：初始化 / 连接
    # ------------------------------------------------------------------ #
    def _connect(self) -> sqlite3.Connection:
        """建立数据库连接（配置行工厂为字典）"""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_table(self, conn: sqlite3.Connection) -> None:
        """创建 words 表（若不存在）"""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS words (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                word         TEXT NOT NULL UNIQUE,
                phonetic     TEXT NOT NULL DEFAULT '',
                meaning      TEXT NOT NULL DEFAULT '',
                example      TEXT NOT NULL DEFAULT '',
                familiar     INTEGER NOT NULL DEFAULT 0,
                review_count INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                last_review  TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.commit()

    def _init_db(self) -> None:
        """初始化数据库；连接失败或损坏时备份并重建"""
        ensure_dirs()
        self._close()
        try:
            self._conn = self._connect()
            # 执行一条查询验证数据库文件可用
            self._conn.execute("SELECT COUNT(*) FROM sqlite_master")
            self._create_table(self._conn)
        except Exception:
            # 数据库损坏：先备份旧文件，再重建空库
            self._backup_broken_db()
            self._rebuild_db()

    def _close(self) -> None:
        """关闭当前数据库连接（释放文件占用）"""
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:
            pass
        self._conn = None

    def _rebuild_db(self) -> None:
        """重建空数据库：优先删除旧文件，被占用时直接清空文件内容"""
        self._close()
        removed = False
        try:
            if os.path.exists(self._db_path):
                os.remove(self._db_path)
                removed = True
        except Exception:
            pass
        if not removed:
            # 文件被其它连接占用无法删除时，直接截断文件再重建
            try:
                with open(self._db_path, "wb") as f:
                    f.truncate(0)
            except Exception:
                pass
        self._conn = self._connect()
        self._create_table(self._conn)

    def _backup_broken_db(self) -> None:
        """备份损坏的数据库文件为 .bak"""
        try:
            if os.path.exists(self._db_path):
                shutil.copyfile(self._db_path, self._db_path + ".bak")
        except Exception:
            pass

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行写操作并自动提交；任何异常都做安全兜底"""
        try:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur
        except sqlite3.Error:
            # 连接失效时尝试重连一次
            try:
                self._conn.close()
            except Exception:
                pass
            self._init_db()
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    # ------------------------------------------------------------------ #
    # 对外：增删改查
    # ------------------------------------------------------------------ #
    def add_word(self, word: str, phonetic: str = "", meaning: str = "",
                 example: str = "") -> bool:
        """添加单词

        Args:
            word: 英文单词
            phonetic: 音标
            meaning: 中文释义
            example: 英文例句
        Returns:
            bool: 添加成功返回 True；单词已存在返回 False
        """
        word = (word or "").strip()
        if not word:
            return False
        try:
            self._execute(
                "INSERT INTO words (word, phonetic, meaning, example) VALUES (?, ?, ?, ?)",
                (word, phonetic, meaning, example),
            )
            return True
        except sqlite3.IntegrityError:
            # 单词唯一约束冲突：已存在
            return False
        except sqlite3.Error:
            return False

    def update_word(self, word_id: int, data: dict) -> bool:
        """修改单词信息

        Args:
            word_id: 单词 id
            data: 需要更新的字段字典，如 {"meaning": "...", "phonetic": "..."}
        Returns:
            bool: 是否更新成功
        """
        allowed = {"word", "phonetic", "meaning", "example"}
        fields = {k: v for k, v in (data or {}).items() if k in allowed}
        if not fields:
            return False
        try:
            sets = ", ".join("{} = ?".format(k) for k in fields)
            params = list(fields.values()) + [word_id]
            self._execute("UPDATE words SET {} WHERE id = ?".format(sets), tuple(params))
            return True
        except sqlite3.Error:
            return False

    def delete_word(self, word_id: int) -> bool:
        """删除单词

        Args:
            word_id: 单词 id
        Returns:
            bool: 是否删除成功
        """
        try:
            self._execute("DELETE FROM words WHERE id = ?", (word_id,))
            return True
        except sqlite3.Error:
            return False

    def delete_words(self, word_ids) -> bool:
        """批量删除单词

        Args:
            word_ids: 单词 id 列表
        Returns:
            bool: 是否删除成功
        """
        ids = [int(i) for i in (word_ids or []) if i]
        if not ids:
            return False
        try:
            placeholders = ",".join("?" * len(ids))
            self._execute(
                "DELETE FROM words WHERE id IN ({})".format(placeholders), tuple(ids)
            )
            return True
        except sqlite3.Error:
            return False

    def get_word_by_id(self, word_id: int):
        """按 id 查询单词，返回字典或 None"""
        try:
            row = self._conn.execute(
                "SELECT * FROM words WHERE id = ?", (word_id,)
            ).fetchone()
            return dict(row) if row else None
        except sqlite3.Error:
            return None

    def get_word_by_word(self, word: str):
        """按单词原文查询（用于查重），返回字典或 None"""
        word = (word or "").strip()
        if not word:
            return None
        try:
            row = self._conn.execute(
                "SELECT * FROM words WHERE word = ?", (word,)
            ).fetchone()
            return dict(row) if row else None
        except sqlite3.Error:
            return None

    # ------------------------------------------------------------------ #
    # 复习列表生成
    # ------------------------------------------------------------------ #
    def get_review_word_list(self) -> list:
        """按优先级生成复习单词列表

        算法（严格遵循需求）：
            1. 昨日新词：昨天录入的单词（生词优先、复习次数少优先）
            2. 近5天：近 5 天内（不含昨日）录入的单词（同样按熟悉度优先）
            3. 历史随机：录入超过 5 天的历史单词，随机打乱

        Returns:
            list[dict]: 复习单词列表（已按优先级排序）
        """
        rows = []
        try:
            # 1. 昨日新词（date('now','localtime','-1 day') = 昨天）
            rows += self._fetch_review_batch(
                "date(created_at) = date('now','localtime','-1 day')"
            )
            # 2. 近5天（不含昨日，含今天）：创建时间 >= 5天前 且 不是昨天
            rows += self._fetch_review_batch(
                "date(created_at) >= date('now','localtime','-5 day') "
                "AND date(created_at) <> date('now','localtime','-1 day')"
            )
            # 3. 历史随机：创建时间 < 5天前，随机顺序
            rows += self._fetch_review_batch(
                "date(created_at) < date('now','localtime','-5 day')",
                order_by="RANDOM()",
            )
        except sqlite3.Error:
            rows = []
        return rows

    def _fetch_review_batch(self, where: str, order_by: str = None) -> list:
        """按条件批量查询复习单词

        Args:
            where: WHERE 条件片段
            order_by: 排序片段，默认「熟悉度升序、复习次数升序、id 倒序」
                      （生词、少复习的优先）
        """
        if not order_by:
            order_by = "familiar ASC, review_count ASC, id DESC"
        sql = (
            "SELECT * FROM words WHERE {} ORDER BY {}".format(where, order_by)
        )
        rows = self._conn.execute(sql).fetchall()
        return [dict(r) for r in rows]

    def mark_familiar(self, word_id: int, is_known: bool) -> bool:
        """标记认识 / 不认识，更新熟悉度与复习次数

        Args:
            word_id: 单词 id
            is_known: True 认识（熟悉度 +20）；False 不认识（熟悉度 -20）
        Returns:
            bool: 是否更新成功
        """
        try:
            row = self._conn.execute(
                "SELECT familiar, review_count FROM words WHERE id = ?", (word_id,)
            ).fetchone()
            if not row:
                return False
            old_familiar = row["familiar"] or 0
            new_familiar = min(100, max(0, old_familiar + (
                self.FAMILIAR_STEP if is_known else -self.FAMILIAR_STEP
            )))
            new_count = (row["review_count"] or 0) + 1
            self._execute(
                "UPDATE words SET familiar = ?, review_count = ?, "
                "last_review = datetime('now','localtime') WHERE id = ?",
                (new_familiar, new_count, word_id),
            )
            return True
        except sqlite3.Error:
            return False

    # ------------------------------------------------------------------ #
    # 单词库查询（供管理窗口使用）
    # ------------------------------------------------------------------ #
    def get_all_words(self, keyword: str = "", date_from: str = None,
                      date_to: str = None) -> list:
        """按条件查询单词库全部记录（按录入时间倒序）

        Args:
            keyword: 单词关键词（模糊匹配）
            date_from: 起始日期 "YYYY-MM-DD"（含）
            date_to: 结束日期 "YYYY-MM-DD"（含）
        Returns:
            list[dict]: 匹配的单词列表
        """
        conditions = []
        params = []
        if keyword:
            conditions.append("word LIKE ?")
            params.append("%{}%".format(keyword.strip()))
        if date_from:
            conditions.append("date(created_at) >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("date(created_at) <= ?")
            params.append(date_to)

        sql = "SELECT * FROM words"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY id DESC"
        try:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error:
            return []

    def count_all(self) -> int:
        """统计单词总数"""
        try:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM words").fetchone()
            return int(row["c"] or 0)
        except sqlite3.Error:
            return 0

    # ------------------------------------------------------------------ #
    # 导入导出
    # ------------------------------------------------------------------ #
    def export_to_json(self, file_path: str) -> bool:
        """将全部单词导出为 JSON 文件

        Returns:
            bool: 是否导出成功
        """
        rows = self.get_all_words()
        data = [
            {
                "word": r["word"],
                "phonetic": r["phonetic"],
                "meaning": r["meaning"],
                "example": r["example"],
            }
            for r in rows
        ]
        try:
            import json
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def import_from_json(self, file_path: str) -> dict:
        """从 JSON 文件导入单词库

        Returns:
            dict: {"added": 新增数, "skipped": 已存在跳过数}
        """
        added = 0
        skipped = 0
        try:
            import json
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return {"added": 0, "skipped": 0}
            for item in data:
                if not isinstance(item, dict):
                    continue
                word = (item.get("word") or "").strip()
                if not word:
                    continue
                ok = self.add_word(
                    word,
                    phonetic=str(item.get("phonetic") or ""),
                    meaning=str(item.get("meaning") or ""),
                    example=str(item.get("example") or ""),
                )
                if ok:
                    added += 1
                else:
                    skipped += 1
            return {"added": added, "skipped": skipped}
        except Exception:
            return {"added": added, "skipped": skipped}
