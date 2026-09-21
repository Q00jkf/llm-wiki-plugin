#!/usr/bin/env python3
"""ingest 前的 delta／stale 一鍵檢查：raw/ 哪些檔的 hash 不在 manifest。

把「逐檔算 hash + grep manifest」的幾十次往返壓成一次執行。
🔴 只用 hash 比對，絕不用路徑比對 —— 舊 manifest 的 key 可能有 mojibake 或格式不一。
只掃本 vault 自己的 raw/；外部 repo 用 repo.py scan。

用法：
    stale_check.py [raw/子路徑] [--ext .txt]...   # 預設掃整個 raw/，副檔名 .md/.pdf
    stale_check.py --hash <file>                   # 只印單檔 MD5
exit：0 正常；2 路徑／manifest 不存在。
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _guard_status  # noqa: E402
from _lib import filehash as _filehash  # noqa: E402
from _lib.vaultpaths import find_vault_root, manifest_path  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_EXTS = {".md", ".pdf"}
SKIP_NAMES = {".manifest.json", "_README.md", "_manifest.json"}


def md5_of(path: Path) -> str:
    """文字檔正規化行尾後再 hash —— 定義見 _lib/filehash（#19）。"""
    return _filehash.md5_of(path).lower()


def manifest_hashes(p: Path) -> set:
    """遞迴收集所有 "hash" 值 —— 同時容忍 sources 子字典與 legacy 頂層 raw/... key。"""
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = p.read_text(encoding="latin-1")
    hashes = set()

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "hash" and isinstance(v, str):
                    hashes.add(v.strip().lower())
                else:
                    walk(v)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(json.loads(text))
    return hashes


def main():
    ap = argparse.ArgumentParser(description="wiki ingest delta/stale check")
    ap.add_argument("path", nargs="?", default="raw", help="要掃的子路徑（相對 vault root）")
    ap.add_argument("--hash", metavar="FILE", help="只印單一檔案的 MD5")
    ap.add_argument("--ext", action="append", default=[], help="追加副檔名，可重複")
    a = ap.parse_args()

    root = find_vault_root(Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
    if root is None:
        print("error   : 找不到 vault")
        return 2

    def resolve(s):
        p = Path(s)
        return p if p.is_absolute() else root / p

    if a.hash:
        t = resolve(a.hash)
        if not t.is_file():
            print(f"error   : 檔案不存在 — {a.hash}")
            return 2
        print(md5_of(t))
        return 0

    scan = resolve(a.path)
    if not scan.exists():
        print(f"error   : 路徑不存在 — {a.path}")
        return 2
    mf = manifest_path(root)
    if not mf.is_file():
        print("error   : 找不到 raw/.manifest.json")
        return 2

    exts = DEFAULT_EXTS | {e.lower() if e.startswith(".") else "." + e.lower() for e in a.ext}
    known_hashes = manifest_hashes(mf)

    scanned, known, pending = 0, 0, []
    for p in sorted(scan.rglob("*")):
        if not p.is_file() or p.name in SKIP_NAMES or p.suffix.lower() not in exts:
            continue
        scanned += 1
        if md5_of(p) in known_hashes:
            known += 1
        else:
            pending.append(p.relative_to(root).as_posix())

    try:
        rel = scan.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        rel = str(scan)
    print(f"=== stale-check {rel} ===")
    print(f"scanned : {scanned} files ({'/'.join(sorted(exts))})")
    print(f"known   : {known}（hash 已在 manifest）")
    print(f"pending : {len(pending)}（hash 不在 manifest → 新檔或已修改，需 ingest）")
    for path in pending:
        print(f"  - {path}")
    if pending:
        print(f"verdict : PENDING — {len(pending)} 個檔案需要 ingest（含新檔與修改過的 stale 檔）")
    else:
        print("verdict : CLEAN — 此路徑下所有檔案 hash 皆已在 manifest，wiki 與 raw/ 同步")
    _guard_status.record("stale-check", f"PENDING {len(pending)}" if pending else "CLEAN", 0, scope=rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
