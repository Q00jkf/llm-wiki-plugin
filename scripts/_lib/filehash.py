"""檔案 hash 的單一定義 —— 文字檔先正規化行尾再算。

🔴 為什麼不直接 hash 原始 bytes（2026-09-21 驗收 #19）：

Windows + git `core.autocrlf=true`（預設）下，任何 `checkout`／`clone`／新 worktree
都會把文字檔轉成 CRLF。內容一個字沒變，md5 卻變了 —— stale_check 於是把 raw/ 裡
所有文字正本報成「需要重新 ingest」，而 `git status` 比的是正規化後的內容、顯示乾淨，
使用者完全看不出發生了什麼。實測 `raw/manual/EVK-X20P_UserGuide.md`：
磁碟 CRLF 版 b3b53eef…、轉回 LF 後 b51deb00… ＝ manifest 記錄值。

hash 在這套系統裡代表「文件身分」，不是「磁碟位元組」，所以文字檔一律先 CRLF→LF。
二進位檔（PDF／Office）git 本來就不轉，照原樣分塊 hash，不進記憶體。

向後相容：既有 manifest 的 hash 多半是從 LF 內容算的（ingest 當下檔案還沒被 checkout
轉過），正規化後算出同一個值，不需要遷移。若某筆是在 CRLF 狀態下 ingest 的，
那一份會被報一次 stale，重新 ingest 後即歸位。
"""
import hashlib
from pathlib import Path

TEXT_EXT = {".md", ".txt", ".csv", ".tsv", ".json", ".yaml", ".yml", ".toml",
            ".ini", ".cfg", ".py", ".js", ".ts", ".html", ".htm", ".xml",
            ".css", ".sh", ".bat", ".ps1", ".canvas", ".base"}


def is_text(path) -> bool:
    """只認副檔名 —— 內容嗅探（NUL byte）對 PDF 不可靠，且要判斷得讀檔。"""
    return Path(path).suffix.lower() in TEXT_EXT


def md5_of(path) -> str:
    p = Path(path)
    if is_text(p):
        b = p.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        return hashlib.md5(b).hexdigest()
    h = hashlib.md5()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
