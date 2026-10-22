"""Per-process configuration; importing this module does not create user files."""

import os
import sys
from pathlib import Path

APP_NAME = "wechat-emoji-to-feishu"
APP_DIR = str(Path(__file__).resolve().parents[3] / "runtime")
DATA_DIR = os.environ.get(
    "WECHAT_EMOJI_HOME", str(Path.home() / "Library/Application Support" / APP_NAME)
)
WECHAT_FILES_ROOT = os.environ.get(
    "WECHATEMOJI_WECHAT_ROOT",
    str(Path.home() / "Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"),
)
FEISHU_HOME_URL = "https://www.feishu.cn/"
FEISHU_MESSENGER_URL = "https://www.feishu.cn/messenger/"
FEISHU_EMOJI_MAX_SIZE_KB = 800
FEISHU_EMOJI_DIMENSION = 400
FEISHU_EMOJI_FORMATS = (".png", ".gif", ".jpg", ".jpeg", ".webp")
PAGE_TIMEOUT = 30000
UPLOAD_TIMEOUT = 10000
LOGIN_TIMEOUT = 600000
PLAYWRIGHT_BUNDLE_DIR = str(Path(APP_DIR) / "ms-playwright")
PLAYWRIGHT_VENDOR_DIR = str(Path(APP_DIR) / "ms-playwright")
PLAYWRIGHT_USER_DIR = str(
    Path.home()
    / ("Library/Caches/ms-playwright" if sys.platform == "darwin" else ".cache/ms-playwright")
)


def configure(home=None, wechat_root=None):
    global DATA_DIR, WECHAT_FILES_ROOT, OUTPUT_DIR, EMOJI_OUTPUT_DIR, DEBUG_DIR, TMP_DIR
    if home:
        DATA_DIR = str(Path(home).expanduser().resolve())
    if wechat_root:
        WECHAT_FILES_ROOT = str(Path(wechat_root).expanduser().resolve())
    OUTPUT_DIR = str(Path(DATA_DIR) / "output")
    EMOJI_OUTPUT_DIR = str(Path(OUTPUT_DIR) / "emojis")
    DEBUG_DIR = str(Path(DATA_DIR) / "debug")
    TMP_DIR = str(Path(DATA_DIR) / "tmp")


configure()
