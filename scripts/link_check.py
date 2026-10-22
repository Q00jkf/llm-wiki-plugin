#!/usr/bin/env python3
"""「提到了但沒連」偵測器：wiki 頁內文出現別頁的識別碼（型號、產品名），兩頁之間卻沒有 [[wikilink]]。

只比對**識別碼型**的頁名／aliases（含數字，或有 2 個以上大寫字母，例如 GS-3V-NM、HINS、AegiverseCore）。
一般詞（ingest、status、agenda…）與中文詞（主管）不比：它們是頁名卻也是日常用字，2026-10-22 在
AEGIVERSE vault 實測，不濾的話 315 筆候選裡大半是這類誤判。
不呼叫 LLM、不改任何檔；exit 一律 0，只列候選不擋 git。

用法：link_check.py [path] [--quiet] [--all] [--scope wiki]
  --quiet  只印一行摘要（給開場 hook 用）
  --all    列出每一組（來源頁 → 該連的頁），預設只列被漏連最多的前 15 頁
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib.vaultpaths import find_vault_root  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WIKILINK = re.compile(r"!?\[\[([^\]\|#\^]+)(?:[#\^][^\]\|]*)?(?:\|[^\]]*)?\]\]")
MDLINK = re.compile(r"\]\(([^)\s]+?\.md)(?:#[^)]*)?\)")
FRONTMATTER = re.compile(r"\A---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|\Z)", re.S)
CODEBLOCK = re.compile(r"```.*?```", re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")
ALIAS_LINE = re.compile(r"^aliases?:\s*(.*)$", re.M)
ALIAS_ITEM = re.compile(r"^\s+-\s+(.+)$", re.M)

SKIP_DIRS = {".obsidian", ".trash", "folds", "_guard-status"}
SKIP_FILES = {"log.md", "index.md", "hot.md"}   # 流水帳與目錄：本來就提到一切，不算漏連
TOP = 15


def identifier_like(term):
    t = term.strip()
    if len(t) < 3 or not t.isascii():
        return False
    return bool(re.search(r"\d", t)) or len(re.findall(r"[A-Z]", t)) >= 2


def read_note(p):
    text = p.read_text(encoding="utf-8", errors="replace")
    m = FRONTMATTER.match(text)
    fm, body = (m.group(1), text[m.end():]) if m else ("", text)
    aliases = []
    am = ALIAS_LINE.search(fm)
    if am:
        inline = am.group(1).strip()
        if inline.startswith("["):
            aliases = [a.strip().strip("\"'") for a in inline.strip("[]").split(",") if a.strip()]
        elif inline:
            aliases = [inline.strip("\"'")]
        else:
            tail = fm[am.end():]
            aliases = [a.strip().strip("\"'") for a in ALIAS_ITEM.findall(tail.split("\n\n")[0])]
    return fm, body, aliases


def scan(root):
    notes = {}
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]) or p.name in SKIP_FILES:
            continue
        fm, body, aliases = read_note(p)
        notes[rel.as_posix()] = {"stem": p.stem, "fm": fm, "body": body, "aliases": aliases}

    by_stem = defaultdict(list)
    for path, n in notes.items():
        by_stem[n["stem"].lower()].append(path)

    linked = defaultdict(set)   # 無向：任一方向有連就算連
    for src, n in notes.items():
        text = CODEBLOCK.sub(" ", n["fm"] + "\n" + n["body"])
        targets = WIKILINK.findall(text) + MDLINK.findall(text)
        for t in targets:
            t = t.strip().replace("\\", "/")
            stem = t[:-3] if t.lower().endswith(".md") else t
            for dst in by_stem.get(stem.rsplit("/", 1)[-1].lower(), []):
                if dst != src:
                    linked[src].add(dst)
                    linked[dst].add(src)

    owners = defaultdict(set)
    for path, n in notes.items():
        for term in [n["stem"]] + n["aliases"]:
            if identifier_like(term):
                owners[term.lower()].add(path)
    terms = sorted(((t, next(iter(o))) for t, o in owners.items() if len(o) == 1),
                   key=lambda x: -len(x[0]))

    found = []   # (src, dst, term)
    for src, n in notes.items():
        plain = INLINE_CODE.sub(" ", CODEBLOCK.sub(" ", n["body"]))
        plain = WIKILINK.sub(" ", plain)
        low = plain.lower()
        seen = set()
        for term, dst in terms:
            if dst == src or dst in linked[src] or dst in seen or term not in low:
                continue
            if re.search(r"(?<![\w-])" + re.escape(term) + r"(?![\w-])", low):
                seen.add(dst)
                found.append((src, dst, term))
    return notes, found


def main(argv):
    quiet = "--quiet" in argv
    show_all = "--all" in argv
    scope = "wiki"
    if "--scope" in argv:
        scope = argv[argv.index("--scope") + 1]
    args = [a for i, a in enumerate(argv)
            if not a.startswith("--") and (i == 0 or argv[i - 1] != "--scope")]
    start = Path(args[0]) if args else Path.cwd()
    root = find_vault_root(start)
    if root is None or not (root / scope).is_dir():
        print("link_check: 找不到 vault 或 %s/ 目錄" % scope)
        return 0

    notes, found = scan(root / scope)
    by_dst = Counter(d for _, d, _ in found)
    if quiet:
        print("link_check: %d 組「提到了沒連」（%d 篇來源，%d 頁被漏連）" %
              (len(found), len({s for s, _, _ in found}), len(by_dst)))
        return 0

    print("掃 %s/（%d 篇）：識別碼被提到但兩頁間沒有連結 = %d 組，來源 %d 篇" %
          (scope, len(notes), len(found), len({s for s, _, _ in found})))
    print("\n被漏連最多的頁面：\n| 頁面 | 漏連篇數 |\n|---|---|")
    for dst, c in by_dst.most_common(None if show_all else TOP):
        print("| %s | %d |" % (dst, c))
    if show_all:
        print("\n來源頁 → 該連的頁（比對到的詞）：")
        for s, d, t in sorted(found):
            print("- %s → %s（%s）" % (s, d, t))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
