# -*- coding: utf-8 -*-
"""配置管理模块 - ConfigManager

负责 config/config.json 的读写，提供统一的 get / set 方法（支持点号路径，如 "panel.opacity"）。
配置文件不存在或损坏时，自动备份损坏文件并生成默认配置，保证程序可正常启动。
"""
import copy
import json
import os

from .utils import get_config_path, ensure_dirs


class ConfigManager:
    """配置管理器（单例风格的通用配置封装）

    用法：
        cfg = ConfigManager()
        cfg.get("panel.opacity", 0.85)   # 读取
        cfg.set("panel.opacity", 0.9)    # 写入（内存）
        cfg.save()                       # 落盘
    """

    # 默认配置项（与需求保持一致）
    DEFAULT_CONFIG = {
        "panel": {
            "x": 100, "y": 100, "width": 320, "height": 120,
            "opacity": 0.85, "background": "", "pet_enabled": True,
            "house": True,
        },
        "review": {"interval": 10, "auto_start": True},
        "shortcut": {"input": "Ctrl+Alt+W", "toggle": "Ctrl+Alt+S"},
        "auto_launch": False,
    }

    def __init__(self, path: str = None):
        """初始化配置管理器

        Args:
            path: 配置文件路径，默认使用 <根目录>/config/config.json
        """
        self._path = path or get_config_path()
        self._data = {}
        self._load()

    # ------------------------------------------------------------------ #
    # 内部：加载 / 合并默认值
    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        """加载配置文件；文件不存在或损坏时自动备份并回退到默认配置"""
        ensure_dirs()
        loaded = {}
        exists = os.path.exists(self._path)
        if exists:
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict):
                    raise ValueError("配置根节点不是对象")
            except Exception:
                # 配置文件损坏：先备份旧文件，再回退到默认配置
                self._backup_broken_file()
                loaded = {}
        # 与默认配置深合并，保证任何缺失项都有默认值
        self._data = self._deep_merge(
            copy.deepcopy(self.DEFAULT_CONFIG), loaded
        )
        if not exists:
            # 配置文件不存在：自动生成默认配置文件到磁盘
            self.save()

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """将 override 递归合并进 base（override 优先），返回合并后的新 dict"""
        result = copy.deepcopy(base)
        for key, value in (override or {}).items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = ConfigManager._deep_merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    def _backup_broken_file(self) -> None:
        """将损坏的配置文件重命名为 .bak 以便排查"""
        try:
            if os.path.exists(self._path):
                os.rename(self._path, self._path + ".bak")
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # 对外：读取 / 写入 / 保存
    # ------------------------------------------------------------------ #
    def get(self, key: str, default=None):
        """按点号路径读取配置，如 get("panel.opacity")；缺失返回 default"""
        cur = self._data
        for part in key.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return default
        return cur

    def set(self, key: str, value) -> None:
        """按点号路径写入配置（仅写内存，需调用 save() 落盘）"""
        keys = key.split(".")
        cur = self._data
        for part in keys[:-1]:
            if part not in cur or not isinstance(cur.get(part), dict):
                cur[part] = {}
            cur = cur[part]
        cur[keys[-1]] = value

    def save(self) -> bool:
        """将当前配置写入文件；失败返回 False，不抛出异常"""
        try:
            ensure_dirs()
            tmp_path = self._path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            # 先写临时文件再原子替换，避免写入中断导致配置损坏
            os.replace(tmp_path, self._path)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # 其它
    # ------------------------------------------------------------------ #
    def get_data(self) -> dict:
        """返回完整配置副本（供需要整体读取的场景使用）"""
        return copy.deepcopy(self._data)
