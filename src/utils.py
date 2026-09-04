# -*- coding: utf-8 -*-
"""全局路径与通用工具模块

提供项目根目录定位、配置/数据库/资源路径、目录初始化、
开机自启（Windows 注册表）、隐藏任务栏图标等通用能力。
所有路径均基于代码所在位置动态计算，保证打包后仍可正常使用。
"""
import os
import sys

# 项目根目录：本文件位于 <根目录>/src/utils.py，向上两级即根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 开机自启在 Windows 注册表中的条目名称
AUTO_LAUNCH_APP_NAME = "IELTSWordReminder"


def get_config_path() -> str:
    """返回配置文件 config/config.json 的绝对路径"""
    return os.path.join(BASE_DIR, "config", "config.json")


def get_db_path() -> str:
    """返回数据库文件 data/word_lib.db 的绝对路径"""
    return os.path.join(BASE_DIR, "data", "word_lib.db")


def get_data_dir() -> str:
    """返回数据目录 data（单词库、每日文章等），不存在则创建"""
    path = os.path.join(BASE_DIR, "data")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path



def get_asset_path(name: str) -> str:
    """返回 assets 目录下指定资源文件的绝对路径"""
    return os.path.join(BASE_DIR, "assets", name)


def get_backgrounds_dir() -> str:
    """返回背景图目录 assets/backgrounds 的绝对路径（不存在则创建）"""
    path = os.path.join(BASE_DIR, "assets", "backgrounds")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def resolve_asset_rel(path: str) -> str:
    """把配置里存储的背景图路径解析为绝对路径

    兼容两种存储形式：
    - 相对路径（相对项目根，如 "assets/backgrounds/xxx.png"，打包后仍可用）
    - 绝对路径（旧版本或外部路径）
    文件不存在或为空时返回空字符串。
    """
    if not path:
        return ""
    if os.path.isabs(path):
        return path if os.path.exists(path) else ""
    full = os.path.join(BASE_DIR, path)
    return full if os.path.exists(full) else ""


def copy_file_to_backgrounds(src: str) -> str:
    """把用户选择的图片复制到 assets/backgrounds，返回相对路径

    复制到项目内而非直接引用原路径，保证打包/移动项目后背景图不失效。
    失败返回空字符串。
    """
    try:
        import shutil
        import time
        import uuid
        ext = os.path.splitext(src)[1].lower() or ".png"
        name = "{}_{}{}".format(int(time.time()), uuid.uuid4().hex[:6], ext)
        dest = os.path.join(get_backgrounds_dir(), name)
        shutil.copy2(src, dest)
        return os.path.relpath(dest, BASE_DIR)
    except Exception:
        return ""


def get_main_py_path() -> str:
    """返回主程序 main.py 的绝对路径（用于开机自启）"""
    return os.path.join(BASE_DIR, "main.py")


def ensure_dirs() -> None:
    """确保 config / data / assets 目录存在（不存在则创建）"""
    for name in ("config", "data", "assets"):
        path = os.path.join(BASE_DIR, name)
        try:
            if not os.path.isdir(path):
                os.makedirs(path, exist_ok=True)
        except Exception:
            # 目录创建失败不致命，交由后续使用方处理
            pass


def condense_meaning(text: str, max_len: int = 40) -> str:
    """精简中文释义：只保留第一个义项，过长截断

    词典返回的释义常包含多个义项（用中文分号「；」连接），
    悬浮面板展示时只保留首个义项，避免大段文字遮挡面板。

    Args:
        text: 完整释义文本
        max_len: 单个义项允许的最大长度
    Returns:
        str: 精简后的释义（空文本原样返回）
    """
    if not text:
        return ""
    first = str(text).split("；")[0].strip()
    if len(first) > max_len:
        first = first[:max_len].rstrip() + "…"
    return first


def hide_from_taskbar(win_id) -> None:
    """通过 Windows 扩展样式 WS_EX_TOOLWINDOW 将窗口从任务栏隐藏

    适用于需要获取输入焦点、但又不想出现在任务栏的悬浮/录入窗口。
    使用 ctypes 调用 user32，失败时静默忽略。
    """
    try:
        import ctypes
        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x00000080
        hwnd = int(win_id)
        user32 = ctypes.windll.user32
        ex_style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_TOOLWINDOW)
    except Exception:
        # 非 Windows 环境或调用失败时忽略，不影响功能
        pass


def _get_pythonw() -> str:
    """返回无控制台窗口的 pythonw.exe 路径（找不到则退回当前解释器）"""
    exe = sys.executable
    lower = exe.lower()
    if lower.endswith("pythonw.exe"):
        return exe
    # python.exe -> pythonw.exe
    candidate = exe[:-4] + "w.exe" if lower.endswith("python.exe") else ""
    if candidate and os.path.exists(candidate):
        return candidate
    return exe


def set_auto_launch(enabled: bool) -> bool:
    """设置/取消开机自启（写入 HKCU 注册表 Run 键）

    使用 pythonw.exe 启动，避免开机自启时弹出黑色控制台窗口。

    Args:
        enabled: True 写入自启项；False 删除自启项
    Returns:
        bool: 是否操作成功（非 Windows 环境返回 False）
    """
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        try:
            if enabled:
                # 用 pythonw.exe 运行 main.py（无控制台窗口）
                command = '"{}" "{}"'.format(_get_pythonw(), get_main_py_path())
                winreg.SetValueEx(key, AUTO_LAUNCH_APP_NAME, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, AUTO_LAUNCH_APP_NAME)
                except FileNotFoundError:
                    pass  # 原本就没有自启项，视为成功
        finally:
            winreg.CloseKey(key)
        return True
    except Exception:
        return False


def get_auto_launch_enabled() -> bool:
    """查询开机自启当前是否已开启"""
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, AUTO_LAUNCH_APP_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False
