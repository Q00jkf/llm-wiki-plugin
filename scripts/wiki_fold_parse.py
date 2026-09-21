#!/usr/bin/env python3
"""/wiki-fold 的解析與封存後端。skill 只負責寫摘要，切片與搬移全部走這支。

為什麼：log.md 設計上會長到被 big_read_guard 擋整份讀，摺疊不能靠 Read；
且條目在檔內兩種順序並存（早期 append、近期 prepend），「最舊＝檔尾」不成立，必須按日期排。

  list      列全部條目：序號（1＝最舊）、行號、日期、標題、大小
  batch     從最舊端取 2^k 條（或 --range A-B），印 fold_id、children JSON、原文 —— 給 skill 寫摘要
  archive   把該批原文原封搬到 wiki/folds/raw/{fold_id}.md 並從 log.md 移除；需 --yes 且摘要頁已存在

exit：0 正常；非 0＝前置條件不符（條目不足、摘要頁不存在、raw 檔已存在），且不改任何檔。
"""
import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib.logparse import load_entries, log_path  # noqa: E402
from _lib.vaultpaths import find_vault_root  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

WIKILINK = re.compile(r"\[\[([^\]|#]+)")
PATHREF = re.compile(r"`((?:wiki|raw|scripts|skills|commands)/[^`\n]+?)`")
COMMIT = re.compile(r"`([0-9a-f]{7,8})`")

ROOT = LOG = FOLDS = None


def pick(entries, k=None, offset=0, rng=None):
    by_idx = {e["idx"]: e for e in entries}
    if rng:
        a, b = rng
        want = [by_idx[i] for i in range(a, b + 1) if i in by_idx]
        if len(want) != b - a + 1:
            sys.exit(f"error: --range {a}-{b} 超出範圍（共 {len(entries)} 條）")
        edge = date_edge(entries, a, b)
        if edge != b:                    # 手動指定的範圍照樣不得切開同一天，但不默默改
            sys.exit(f"error: --range {a}-{b} 切開了 {entries[b - 1]['date']} 這一天 —— "
                     f"同日條目先後不可靠，fold 以日期為邊界。改用 --range {a}-{edge}")
        return want
    n, lo = 2 ** k, 1 + offset
    hi = lo + n - 1
    if hi > len(entries):
        sys.exit(f"error: 條目不足：需要 idx {lo}..{hi}，但只有 {len(entries)} 條（offset={offset}, 2^{k}={n}）。"
                 f" 依 skill 規則不摺疊不足批次。")
    hi = date_edge(entries, lo, hi)
    return [by_idx[i] for i in range(lo, hi + 1)]


def date_edge(entries, lo, hi):
    """把批次結尾 hi 對齊到日期邊界 —— 不切開同一天（1-based，回傳新的 hi）。

    🔴 同日條目的先後在 log 裡不可靠：早期 append（行號小＝舊）、近期 prepend（行號小＝新）
    兩種順序並存，位置無法判先後，所以 load_entries 同日只能退回用位置排，必定有一種寫法被排反。
    切在同一天中間，會讓 fold_id 宣稱的日期範圍與 log 殘留條目重疊
    （實測：fold 宣稱涵蓋到 2026-09-21，log 卻還留著兩條 2026-09-21）。
    以日期為邊界就完全避開這個歧義 —— 代價是每批不再剛好 2^k。
    先退到前一天的結尾；若整批都在同一天（退了會變 0 條），改為吃滿那一天。
    （2026-09-21 驗收 #17）
    """
    if hi >= len(entries):
        return hi
    d = entries[hi - 1]["date"]
    if entries[hi]["date"] != d:              # 已在日期邊界
        return hi
    back = hi
    while back >= lo and entries[back - 1]["date"] == d:
        back -= 1
    if back >= lo:
        return back
    fwd = hi
    while fwd < len(entries) and entries[fwd]["date"] == d:
        fwd += 1
    return fwd


def fold_id(batch, k):
    return f"fold-k{k}-from-{batch[0]['date']}-to-{batch[-1]['date']}-n{len(batch)}"


def children(lines, batch):
    out = []
    for e in batch:
        body = "\n".join(lines[e["start"]:e["end"]])
        out.append({
            "idx": e["idx"], "date": e["date"], "title": e["title"],
            "lines": f"{e['start'] + 1}-{e['end']}",
            "wikilinks": sorted(set(WIKILINK.findall(body)))[:12],
            "paths": sorted(set(PATHREF.findall(body)))[:12],
            "commits": sorted(set(COMMIT.findall(body)))[:12],
            "bytes": len(body.encode("utf-8")),
        })
    return out


def cmd_list(a):
    lines, entries = load_entries(LOG)
    total = len(entries)
    print(f"=== wiki-fold-parse list ===\nlog.md: {len(lines)} 行／{total} 條（1＝最舊）\n")
    show = entries[:a.tail] if a.tail else entries
    for e in show:
        size = sum(len(l) for l in lines[e["start"]:e["end"]])
        print(f"{e['idx']:4d}  L{e['start'] + 1:>5}-{e['end']:<5} {e['date']}  {size:6d}c  {e['title'][:60]}")
    if a.tail and total > a.tail:
        print(f"... 另 {total - a.tail} 條（--tail 0 看全部）")


def cmd_batch(a):
    lines, entries = load_entries(LOG)
    rng = None
    if a.range:
        m = re.match(r"^(\d+)-(\d+)$", a.range)
        if not m:
            sys.exit("error: --range 格式為 A-B（1＝最舊）")
        rng = (int(m.group(1)), int(m.group(2)))
        k = max(1, (rng[1] - rng[0] + 1).bit_length() - 1)
    else:
        k = a.k
    batch = pick(entries, k=k, offset=a.offset, rng=rng)
    fid = fold_id(batch, k)
    print("=== wiki-fold-parse batch ===")
    print(f"fold_id : {fid}")
    print(f"exists  : {'YES — 摘要頁已存在，重跑前先確認' if (FOLDS / (fid + '.md')).exists() else 'no'}")
    print(f"range   : idx {batch[0]['idx']}..{batch[-1]['idx']}（{batch[0]['date']} → {batch[-1]['date']}）, {len(batch)} 條")
    print("children: (JSON)")
    print(json.dumps(children(lines, batch), ensure_ascii=False, indent=1))
    if not a.no_body:
        print("\n--- 原文（由舊到新）---")
        for e in batch:
            print("\n".join(lines[e["start"]:e["end"]]).rstrip())
            print()


def cmd_archive(a):
    if not a.yes:
        sys.exit("error: archive 會改 wiki/log.md，必須加 --yes")
    lines, entries = load_entries(LOG)
    batch = pick(entries, k=a.k, offset=a.offset)
    fid = fold_id(batch, a.k)
    summary = FOLDS / (fid + ".md")
    if not summary.exists():
        sys.exit(f"error: 摘要頁 wiki/folds/{fid}.md 不存在 —— 先寫摘要、後封存，順序不可反")
    raw_dir = FOLDS / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / (fid + ".md")
    if raw_path.exists():
        sys.exit(f"error: wiki/folds/raw/{fid}.md 已存在，疑似重複封存")
    segs = sorted((e["start"], e["end"]) for e in batch)   # 批次在檔內不一定連續，逐段搬
    block = []
    for s, t in segs:
        block.extend(lines[s:t])
        if block and block[-1].strip():
            block.append("")
    header = [
        "---", "type: fold-raw", f"fold_id: \"{fid}\"", "source: wiki/log.md",
        f"archived: {date.today().isoformat()}", f"entries: {len(batch)}", "frozen: true", "---",
        f"# {fid} — 原文封存", "",
        f"> `wiki/log.md` 日期序號第 {batch[0]['idx']}–{batch[-1]['idx']} 條（1＝日期最早）的原文原封搬移，一字未改。",
        f"> 摘要在 [[folds/{fid}]]。刪快照前的 MUST-grep 要連本目錄一起：`grep -r <關鍵字> wiki/log.md wiki/folds/`。",
        "",
    ]
    raw_path.write_text("\n".join(header + block) + "\n", encoding="utf-8")
    new_lines = list(lines)
    for s, t in reversed(segs):
        del new_lines[s:t]
    LOG.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    moved = sum(t - s for s, t in segs)
    print(f"archived: {len(batch)} 條、{moved} 行（{len(segs)} 段）→ wiki/folds/raw/{fid}.md")
    print(f"log.md  : {len(lines)} → {len(new_lines)} 行")
    print("next    : 在 log.md 最上方 prepend 一條 fold 紀錄（格式見 skill）")


def main():
    global ROOT, LOG, FOLDS
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--tail", type=int, default=20, help="只列最舊的 N 條（0＝全部）")
    p = sub.add_parser("batch")
    p.add_argument("--k", type=int, default=3); p.add_argument("--offset", type=int, default=0)
    p.add_argument("--range", help="A-B（1＝最舊），覆蓋 --k/--offset"); p.add_argument("--no-body", action="store_true")
    p = sub.add_parser("archive")
    p.add_argument("--k", type=int, default=3); p.add_argument("--offset", type=int, default=0)
    p.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    ROOT = find_vault_root(Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
    if ROOT is None:
        sys.exit("error: 找不到 vault")
    LOG, FOLDS = log_path(ROOT), ROOT / "wiki" / "folds"
    if not LOG.is_file():
        sys.exit("error: 找不到 wiki/log.md")
    {"list": cmd_list, "batch": cmd_batch, "archive": cmd_archive}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
