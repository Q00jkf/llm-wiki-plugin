#!/usr/bin/env python3
"""rules_check —— 規則層漂移偵測（防「手寫清單與現實脫節」）。

為什麼要有這支：wiki-doctor 只守 wiki 層（孤兒卡、死連結、來源檔消失），
不守 CLAUDE.md／wiki/ops 這些「告訴 Claude 怎麼做」的檔。成熟 vault 實測（2026-09-20）：
產品清單漏 2 個近半年、停用裁示只傳播到 2 個檔、規則層 14 行逐字重複、腳本登記率 58% ——
全是「沒有東西驗證它還在對」。規則層不手寫任何機器能推導的清單；寫了就由機器對帳。

檢查（只讀、只列候選）：
  F1 資料夾用途表 vs raw/ 實際頂層夾   CLAUDE.md 表裡沒有的夾／表裡有但不存在的夾
  F2 停用頁反查                         frontmatter `deprecated: true` 的頁，規則層與 wiki 誰還指向它
  F3 引用腳本存在性                     規則層提到的 scripts/*.py 是否存在（vault 自己的或 plugin 的）
  F4 規則層逐字重複                     CLAUDE.md／hot／index／ops 之間相同的長行（未來矛盾的種子）
  F5 同檔重複標題                       同一頁兩個相同的 H1／H2
  F6 未登記腳本                         vault 自己的 scripts/*.py 沒有任何規則層檔提到它

抓不到的（要靠人）：清單內容對不對、規則本身該不該存在。

用法：
  python rules_check.py            # 全部
  python rules_check.py --only F1,F3
  python rules_check.py --quiet    # 只印 verdict（SessionStart 用）

exit 一律 0 —— 提醒不是閘門。只用 stdlib；語法相容 Python 3.9。
"""
import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _guard_status  # noqa: E402
from _lib.vaultpaths import find_vault_root  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_SCRIPTS = Path(__file__).resolve().parent
SKIP_PARTS = {".git", "node_modules", "__pycache__", ".obsidian", "scratchpad", "folds"}
NEGATED = re.compile(r"⛔|不讀|不要|不再|不得|停止維護|停用|deprecated|移除|不存在|未啟用|不適用|封存|已刪"
                     r"|not available|skipped|missing|removed|disabled")
SCRIPT_REF = re.compile(r"(?<![\w/])((?:\$\{CLAUDE_PLUGIN_ROOT\}/)?scripts/[\w\-./]+?\.py)\b")
_WS = re.compile(r"\s+")


def read(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def fm_value(text, key):
    m = re.search(rf"(?m)^{key}:[ \t]*(.+?)[ \t]*$", text[:2000])
    return m.group(1).strip().strip('"') if m else ""


def section(text, start_pat, stop_pat=r"^## "):
    out, on = [], False
    for l in text.splitlines():
        if not on and re.search(start_pat, l):
            on = True
            continue
        if on and re.match(stop_pat, l):
            break
        if on:
            out.append(l)
    return out


class Ctx:
    def __init__(self, root):
        self.root = root
        self.wiki = root / "wiki"
        self.rule_files = [p for p in [root / "CLAUDE.md", self.wiki / "hot.md", self.wiki / "index.md"]
                           if p.is_file()] + sorted((self.wiki / "ops").glob("*.md"))

    def rel(self, p):
        try:
            return Path(p).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return str(p)

    def wiki_md(self):
        for p in self.wiki.rglob("*.md"):
            if any(part in SKIP_PARTS for part in p.parts):
                continue
            yield p


# ---------------------------------------------------------------- F1
def check_f1(c):
    raw = c.root / "raw"
    if not raw.is_dir():
        return [], "無 raw/"
    actual = {p.name for p in raw.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))}
    table = section(read(c.root / "CLAUDE.md"), r"^## 資料夾用途")
    if not table:
        return [], "CLAUDE.md 無「資料夾用途」表，略過"
    listed = set()
    for l in table:
        for m in re.finditer(r"`raw/([^/`]+)/?`", l):
            listed.add(m.group(1))
    hits = []
    for miss in sorted(actual - listed):
        hits.append(f"raw/{miss}/ 存在，CLAUDE.md「資料夾用途」表沒有它（/wiki-new 建夾後要加一列）")
    for ghost in sorted(listed - actual):
        hits.append(f"CLAUDE.md 表列了 raw/{ghost}/，實際不存在")
    return hits, f"raw/ 頂層 {len(actual)} 夾 vs 表列 {len(listed)}"


# ---------------------------------------------------------------- F2
def check_f2(c):
    dead = [p for p in c.wiki_md() if fm_value(read(p), "deprecated").lower() == "true"]
    hits, info = [], []
    scan = [p for p in c.rule_files] + [p for p in c.wiki_md() if p.name != "log.md"]
    seen = set()
    for d in dead:
        key_a = c.rel(d)
        key_b = key_a[len("wiki/"):-3] if key_a.startswith("wiki/") else d.stem
        for f in scan:
            if f.resolve() == d.resolve() or fm_value(read(f), "maintenance") == "frozen":
                continue
            for n, l in enumerate(read(f).splitlines(), 1):
                if (key_a in l or f"[[{key_b}" in l) and (c.rel(f), n) not in seen:
                    seen.add((c.rel(f), n))
                    (info if NEGATED.search(l) else hits).append(
                        f"{c.rel(f)}:{n}  仍指向已停用的 {d.name} —— {_WS.sub(' ', l.strip())[:70]}")
    return hits, f"{len(dead)} 個 deprecated 頁；活引用 {len(hits)}／已標註停用 {len(info)}（不計）"


# ---------------------------------------------------------------- F3
def check_f3(c):
    hits, seen = [], set()
    for f in c.rule_files:
        for n, l in enumerate(read(f).splitlines(), 1):
            if NEGATED.search(l):
                continue
            for m in SCRIPT_REF.finditer(l):
                ref = m.group(1)
                if "xxx" in ref or "<" in ref or (c.rel(f), ref) in seen:
                    continue
                seen.add((c.rel(f), ref))
                if ref.startswith("${CLAUDE_PLUGIN_ROOT}/"):
                    ok = (PLUGIN_SCRIPTS.parent / ref[len("${CLAUDE_PLUGIN_ROOT}/"):]).exists()
                else:
                    ok = (c.root / ref).exists() or (PLUGIN_SCRIPTS / Path(ref).name).exists()
                if not ok:
                    hits.append(f"{c.rel(f)}:{n}  引用不存在的 {ref}")
    return hits, f"掃 {len(c.rule_files)} 個規則層檔的腳本引用"


# ---------------------------------------------------------------- F4
def check_f4(c, min_len=40, min_shared=3):
    owner = defaultdict(set)
    for f in c.rule_files:
        for l in read(f).splitlines():
            s = _WS.sub(" ", l.strip())
            if len(s) < min_len or s.startswith(("|--", "```", "---", "<!--")):
                continue
            owner[s].add(c.rel(f))
    pairs = defaultdict(list)
    for s, fs in owner.items():
        if len(fs) > 1:
            fl = sorted(fs)
            for i in range(len(fl)):
                for j in range(i + 1, len(fl)):
                    pairs[(fl[i], fl[j])].append(s)
    hits = []
    for (a, b), ls in sorted(pairs.items(), key=lambda kv: -len(kv[1])):
        if len(ls) >= min_shared:
            hits.append(f"{a} ↔ {b}  共 {len(ls)} 行逐字相同，例：「{ls[0][:50]}…」")
    return hits, f"規則層 {len(c.rule_files)} 檔，≥{min_len} 字元的行跨檔比對（≥{min_shared} 行才報）"


# ---------------------------------------------------------------- F5
def check_f5(c):
    hits, done = [], set()
    for f in [c.root / "CLAUDE.md"] + list(c.wiki_md()):
        if not f.is_file() or f.resolve() in done or f.name == "log.md":
            continue
        done.add(f.resolve())
        seen, in_fence = {}, False
        for n, l in enumerate(read(f).splitlines(), 1):
            if l.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            m = re.match(r"^(#{1,2})\s+(.+?)\s*$", l)
            if not m:
                continue
            text = re.sub(r"（.*?）|\(.*?\)", "", _WS.sub(" ", m.group(2))).strip()
            key = (m.group(1), text)
            if key in seen:
                hits.append(f"{c.rel(f)}:{seen[key]} 與 :{n}  重複的 {m.group(1)} 標題「{text}」")
            else:
                seen[key] = n
    return hits, f"{len(done)} 頁的 H1／H2 同檔重複"


# ---------------------------------------------------------------- F6
def check_f6(c):
    sdir = c.root / "scripts"
    if not sdir.is_dir():
        return [], "vault 無 scripts/"
    corpus = "\n".join(read(f) for f in c.rule_files)
    hits = []
    for p in sorted(sdir.glob("*.py")):
        if p.name.startswith("_"):
            continue
        if p.name not in corpus:
            hits.append(f"scripts/{p.name} 沒有任何規則層檔提到它（沒人知道它存在＝不會有人跑）")
    return hits, "vault scripts/*.py 反查 CLAUDE.md／wiki/ops"


CHECKS = {
    "F1": ("資料夾用途表對帳", check_f1),
    "F2": ("停用頁反查", check_f2),
    "F3": ("引用腳本存在性", check_f3),
    "F4": ("規則層逐字重複", check_f4),
    "F5": ("同檔重複標題", check_f5),
    "F6": ("未登記腳本", check_f6),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    import os
    root = find_vault_root(Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
    if root is None:
        return 0
    c = Ctx(root)
    want = [x.strip().upper() for x in a.only.split(",")] if a.only else list(CHECKS)
    total, out = 0, ["=== rules-check ===", f"input   : 規則層 {len(c.rule_files)} 檔"]
    for cid in want:
        if cid not in CHECKS:
            out.append(f"  未知檢查 {cid}（可用：{', '.join(CHECKS)}）")
            continue
        title, fn = CHECKS[cid]
        hits, note = fn(c)
        total += len(hits)
        out.append(f"[{cid}] {'🟡' if hits else '🟢'} {title} — {len(hits)} 筆｜{note}")
        if not a.quiet:
            out.extend(f"     {h}" for h in hits)
    out.append("-" * 60)
    out.append("verdict : 🟢 CLEAN — 規則層與現實一致" if total == 0
               else f"verdict : 🟡 {total} 筆漂移（僅為候選；改清單前先確認哪邊才是真相）")
    print(out[-1] if a.quiet else "\n".join(out))
    if not a.only:
        _guard_status.record("rules-check", "CLEAN" if total == 0 else f"{total} 筆", 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
