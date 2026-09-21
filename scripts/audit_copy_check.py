#!/usr/bin/env python3
"""取用副本夾 vs 正本 一致性檢查。

副本夾（為某次稽核／交付集中取用多份正本的資料夾）靠 `_manifest.json` 記每份副本的正本路徑。
正本改了沒人同步副本，就會出現「副本過期」「正本消失但副本還在」誤導後人。
本腳本比對 md5，只判斷「副本是不是正本的真實副本」，不判斷內容對錯。

_manifest.json 兩種寫法都吃：
    [["群組", "副本檔名", "正本路徑"], ...]
    {"files": [{"copy": "副本檔名", "source": "正本路徑", "group": "可選"}, ...]}
正本路徑相對 vault 根，或絕對路徑；副本路徑相對副本夾。

用法：
    python audit_copy_check.py <副本夾路徑>

退出碼：FAIL（正本或副本消失）→ 1；只有 WARN（過期／未登記）或全過 → 0。
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import filehash as _filehash  # noqa: E402
from _lib.vaultpaths import find_vault_root  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

META = {"_README.md", "_manifest.json"}


def md5(path: Path) -> str:
    """文字檔正規化行尾 —— 副本只差行尾不算「過期」（#19）。"""
    return _filehash.md5_of(path)


def entries(manifest):
    """統一成 (group, copy, source) 三元組。"""
    if isinstance(manifest, dict):
        manifest = manifest.get("files") or manifest.get("entries") or []
    out = []
    for e in manifest:
        if isinstance(e, dict):
            out.append((str(e.get("group", "")), str(e.get("copy", "")), str(e.get("source", ""))))
        elif isinstance(e, (list, tuple)) and len(e) >= 3:
            out.append((str(e[0]), str(e[1]), str(e[2])))
        elif isinstance(e, (list, tuple)) and len(e) == 2:
            out.append(("", str(e[0]), str(e[1])))
    return out


def main():
    if len(sys.argv) < 2:
        print("用法：python audit_copy_check.py <副本夾路徑>")
        return 2
    folder = Path(sys.argv[1]).expanduser()
    root = find_vault_root(Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
    if not folder.is_absolute() and root:
        folder = root / folder
    folder = folder.resolve()
    if root is None:
        root = find_vault_root(folder) or folder
    mf = folder / "_manifest.json"
    if not mf.is_file():
        print(f"🔴 找不到 {mf}")
        return 1
    try:
        manifest = json.loads(mf.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"🔴 _manifest.json 不是合法 JSON：{e}")
        return 1

    fail = warn = 0
    covered = set()
    print(f"=== audit_copy_check: {folder} ===\n")

    for group, copy_name, src in entries(manifest):
        g = f"[{group}] " if group else ""
        covered.add(Path(copy_name).as_posix())
        copy_path = folder / copy_name
        if not src.strip():
            print(f"🟡 WARN  {g}正本路徑空白（資訊列？）：{copy_name}")
            warn += 1
            continue
        src_path = Path(src)
        if not src_path.is_absolute():
            src_path = root / src_path
        if not src_path.is_file():
            print(f"🔴 FAIL  {g}正本已消失／搬移：{src}\n        副本：{copy_name}")
            fail += 1
            continue
        if not copy_path.is_file():
            print(f"🔴 FAIL  {g}副本消失但 manifest 還登記著：{copy_name}")
            fail += 1
            continue
        if md5(copy_path) != md5(src_path):
            print(f"🟡 WARN  {g}副本已過期，正本已更新：{copy_name}")
            warn += 1

    for f in sorted(folder.rglob("*")):
        rel = f.relative_to(folder).as_posix()
        if not f.is_file() or f.name in META or f.name == ".gitkeep" or rel in covered:
            continue
        print(f"🟡 WARN  未登記的副本，來源不明：{rel}")
        warn += 1

    print("\n" + "-" * 60)
    if fail:
        print(f"verdict: 🔴 FAIL — {fail} 項正本／副本消失，{warn} 項待辦")
        return 1
    if warn:
        print(f"verdict: 🟡 WARN — {warn} 項待辦（副本過期或未登記）")
        return 0
    print("verdict: 🟢 CLEAN — 所有副本與正本一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
