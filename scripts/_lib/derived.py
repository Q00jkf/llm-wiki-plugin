"""衍生頁（多來源綜合頁）的過期偵測。

為什麼需要這支：
  catalog 卡的來源是**一個檔**，manifest 記一個 hash，正本改了 `stale_check` 就報。
  但「綜合頁」——把 N 份文件讀完寫成一頁結論——的來源是**一組檔**，manifest 沒有這種結構，
  所以來源改了**沒有任何東西會說**。

  實測某成熟 vault（2026-09-26）：`wiki/synthesis/` 8 頁全部宣告了 `sources:`，
  其中 7 頁超過 3 個月沒更新、1 頁已停用。對照組是有偵測的 catalog 卡，活著。
  ⇒ 綜合層會死不是因為綜合沒價值，是因為**沒有過期偵測**。

判準（只用既有資料，不需要事先登記）：
  頁的 `updated:` 日期 vs 每個來源的最後變動日。來源比頁新 = 那頁可能過期。

🔴 取最後變動日用 `git log -1`，**不要用 `--since`** ——
  git approxidate 會用「執行當下的時鐘」填缺少的時間欄位，純日期 `--since=2026-09-18`
  等同 `2026-09-18 <現在時刻>`，結果隨執行時刻漂移且不報錯（2026-09-26 實測）。
"""
import os
import re
import subprocess
from datetime import date, datetime
from pathlib import Path

# 只有「多來源」才算綜合頁；單一來源的是 catalog 卡，走 stale_check 的 hash 比對
MULTI_SOURCE_MIN = 2
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".obsidian", "folds"}
_FM = re.compile(r"\A---\n(.*?)\n---", re.S)
_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _frontmatter(text):
    m = _FM.match(text)
    return m.group(1) if m else ""


def _sources(fm):
    """取 frontmatter 的 sources 清單。支援區塊式與行內式，行內空陣列回 []。"""
    m = re.search(r"(?m)^sources:[ \t]*(.*)$", fm)
    if not m:
        return None                       # 沒宣告 sources：不是綜合頁，不管它
    inline = m.group(1).strip()
    if inline and inline not in ("|", ">"):
        if inline in ("[]", "[ ]"):
            return []                     # 宣告了但空的 —— 要報
        inner = inline.strip("[]")
        return [s.strip().strip("\"'") for s in inner.split(",") if s.strip()]
    out = []
    for line in fm[m.end():].splitlines():
        if re.match(r"^\s*-\s+", line):
            out.append(re.sub(r"^\s*-\s+", "", line).strip().strip("\"'"))
        elif line.strip() and not line.startswith((" ", "\t")):
            break                         # 下一個 frontmatter 鍵
    return out


# 本 vault 內、可用檔案系統檢查的路徑才比對。其餘（URL／LINE 對話／Superset 資料集／
# 外部 repo alias／別台機器的絕對路徑）是 R2 明文允許的來源型別，**報「不存在」是假陽性** ——
# 而穩定的假陽性會被當背景雜訊，連真的一起被忽略（該 vault 待裁示 #100 的教訓）。
_REPO_TOP = ("raw/", "wiki/", "scripts/", "skills/", "templates/", "commands/", "hooks/")


def _is_repo_path(s: str) -> bool:
    s = s.strip()
    if not s or s.startswith(("http://", "https://", "~", "/")):
        return False
    if "::" in s or re.match(r"^[A-Za-z]:[\/]", s):
        return False                      # 外部 repo key／絕對路徑
    if not s.startswith(_REPO_TOP):
        return False                      # 純敘述（「LINE 對話…」「Superset …」）
    return "（" not in s and "(" not in s.split("/")[-1][:1]


def _fm_date(fm, key):
    m = re.search(rf"(?m)^{key}:[ \t]*(.+)$", fm)
    if not m:
        return None
    d = _DATE.search(m.group(1))
    return d.group(1) if d else None


def _last_change(root: Path, rel: str, cache: dict):
    """來源最後變動日（YYYY-MM-DD）。git 優先，失敗回退 mtime。找不到檔回 None。"""
    if rel in cache:
        return cache[rel]
    p = root / rel
    out = None
    if p.exists():
        try:
            r = subprocess.run(
                ["git", "-C", str(root), "log", "-1", "--format=%cs", "--", rel],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0 and r.stdout.strip():
                out = r.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
        if out is None:
            try:
                out = date.fromtimestamp(p.stat().st_mtime).isoformat()
            except OSError:
                out = None
    cache[rel] = out
    return out


def scan(root: Path):
    """回 [(頁相對路徑, updated, [(來源, 變動日)…], [消失的來源], 是否空宣告)]。只列有問題的。"""
    root = Path(root)
    wiki = root / "wiki"
    if not wiki.is_dir():
        return []
    cache, hits = {}, []
    for p in sorted(wiki.rglob("*.md")):
        if any(part in SKIP_DIRS for part in p.parts) or p.name in ("log.md", "hot.md"):
            continue
        try:
            fm = _frontmatter(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if not fm:
            continue
        srcs = _sources(fm)
        if srcs is None:
            continue
        rel_page = p.relative_to(root).as_posix()
        if srcs == []:
            hits.append((rel_page, _fm_date(fm, "updated"), [], [], True))
            continue
        if len(srcs) < MULTI_SOURCE_MIN:
            continue                      # 單一來源＝catalog 卡，不是本支的守備範圍
        upd = _fm_date(fm, "updated") or _fm_date(fm, "created")
        newer, missing = [], []
        for s in srcs:
            if not _is_repo_path(s):
                continue                  # 非檔案來源（URL／對話／資料庫／外部 repo）——
                                          # R2 允許這些，報「不存在」是假陽性
            when = _last_change(root, s, cache)
            if when is None:
                missing.append(s)
            elif upd and when > upd:
                newer.append((s, when))
        if newer or missing:
            hits.append((rel_page, upd, newer, missing, False))
    return hits


def summarize(root: Path):
    """給 vault_state 用的一行摘要。沒問題回 None。"""
    hits = scan(root)
    if not hits:
        return None
    empty = [h for h in hits if h[4]]
    stale = [h for h in hits if h[2]]
    gone = [h for h in hits if h[3]]
    parts = []
    if stale:
        worst = max(stale, key=lambda h: len(h[2]))
        parts.append(f"{len(stale)} 頁的來源比它新（最多的是 {Path(worst[0]).stem}，"
                     f"{len(worst[2])} 個來源改過，該頁停在 {worst[1]}）")
    if gone:
        parts.append(f"{len(gone)} 頁引用了不存在的來源")
    if empty:
        parts.append(f"{len(empty)} 頁宣告了 sources 卻是空的")
    return "；".join(parts) + " — 綜合頁沒有 hash 對帳，來源改了不會有人告訴你"
