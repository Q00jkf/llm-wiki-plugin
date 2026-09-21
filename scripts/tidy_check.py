#!/usr/bin/env python3
"""快照檔「該整理了」偵測器（防 hot.md／登記簿無聲膨脹）。

掃 frontmatter 有 `maintenance:` 宣告的檔，列出客觀的不一致訊號，不改任何檔。
`frozen` 是凍結紀錄（健檢報告、結案報告）：只驗宣告合法，不列任何整理候選 —— 報告裡的 ✅
是「量測結果」不是「做完的待辦」，照 T1 清掉等於毀掉紀錄（2026-09-21 驗收 #15）。
為什麼量 token 不量行數：行數與重量不成比例（56 行可以 4,500 tok），成本是 context 不是行。
🔴 踩線時的正確動作是清理，不是把 POLICY 數字調大 —— 調大只是把過期往後推。

  T0 快照區未宣告  hot.md／coordination.md 存在卻沒寫 maintenance
  T1 已結案列      表格列含 ✅／⚪／🟢／已裁示／已解／已完成／不做，且無未結案標記
  T2 斷掉的引用    內文寫「缺口 №N」但本檔表上已無此列
  T3 數量不符      「目錄內容（N 份…）」vs 同夾 `_manifest.json` 條目數（無 manifest 則數檔案）
  T4 檔名過期      反引號內的檔名在磁碟上不存在
  T5 列內殘留      整列未結案，但列內 ①②③ 子項已標 ✅
  T6 超出型別上限  依 maintenance 型別查 token／項數上限（POLICY），外加檔頭自訂「≤N 行」
  T7 跨檔編號斷鏈  引用 coordination 的 `#N` 已不存在（僅 wiki/meta/coordination.md 存在時）
  T8 裁示未清登記  log.md 說「不得再提」的 `#N` 在 coordination 仍未結案（同上）

用法：tidy_check.py [path] [--quiet]。exit 一律 0，只列候選不擋 git。
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _guard_status  # noqa: E402
from _lib.vaultpaths import find_vault_root, resolve_source  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Python 3.9 相容：f-string 內不得放反斜線，壓空白一律用這個物件
_WS = re.compile(r"\s+")

MARKER = re.compile(r"^maintenance:\s*([a-z\-]+)\s*$", re.M)
KINDS = ("rolling", "transactional", "append-only", "frozen")

POLICY = {
    "rolling":       {"tokens": 6000, "items": None},            # ≈150 行 × 40 tok
    "transactional": {"tokens": 9000, "items": 45},
    "append-only":   {"tokens": None, "items": None, "guard_bytes": 100_000},
    "frozen":        {"tokens": None, "items": None},            # 凍結：不受上限約束，也不掃
}

SNAPSHOT_FILES = ("wiki/hot.md", "wiki/meta/coordination.md")
COORD = "wiki/meta/coordination.md"
XREF_HASH = re.compile(r"#(\d{1,3})\b")
XREF_CLAIM = re.compile(r"待辦\s*(\d+)\s*項")
QUOTED = re.compile(r"「[^」]*」")
ARCHIVED = re.compile(r"不得再|不再評估")
CLOSED_MARK = re.compile(r"✅|⚪|🟢")
CLOSED_WORD = re.compile(r"已裁示|已解(?![釋析])|已完成|已結案|結案|不做|已消解|已釐清")
OPEN_MARK = re.compile(r"🔴|🟡|⏸|📌|❌|待")
ROW_ID = re.compile(r"^\|\s*(?:№)?(\d+)\s*\|")
HEADING = re.compile(r"^#{1,6}\s+(.*)$")
SUBITEM = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]\s*(?:✅|已解|已釐清|已裁示)")
REF = re.compile(r"缺口\s*№\s*(\d+)")
CNT_DIR = re.compile(r"目錄內容（(\d+)\s*份[^）]*）")
CNT_SUB = re.compile(r"[`「]([^`」/]+)/[`」]\s*內容（(\d+)\s*份）")
CNT_TREE = re.compile(r"[├└]\s*([^\s/（(]+)/\((\d+)\)")
FNAME = re.compile(r"`([^`\n]+\.(?:xlsx?|docx?|pptx?|pdf|md))`")
FNAME_SKIP = re.compile(r"[*{}<>…]|\.\.\.|^\.|xx|XX|/-|//")   # 省略／佔位／樣板寫法，不是完整檔名
CAP = re.compile(r"[≤<]=?\s*(\d{2,4})\s*行")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".obsidian", "Templates", "templates"}  # 模板不是活快照

ROOT = None
_VAULT_NAMES = None


def iter_md(target: Path):
    if target.is_file():
        yield target
        return
    for p in target.rglob("*.md"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        yield p


def sections(lines):
    marks = [(i, m.group(1).strip()) for i, l in enumerate(lines)
             for m in [HEADING.match(l)] if m]
    if not marks:
        return [("(全檔)", 0, len(lines))]
    out = [("(檔頭)", 0, marks[0][0])] if marks[0][0] > 0 else []
    for k, (i, title) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else len(lines)
        out.append((title, i, end))
    return out


def check_closed(lines):
    """T1。排除進度勾選表（欄數 ≥5）與同列仍有未結案標記者。"""
    hits = []
    for i, l in enumerate(lines, 1):
        if not l.startswith("|") or not ROW_ID.match(l):
            continue
        if len(l.split("|")) - 2 >= 5 or OPEN_MARK.search(l):
            continue
        if CLOSED_MARK.search(l) or CLOSED_WORD.search(l):
            hits.append((i, _WS.sub(" ", l)[:70]))
    return hits


def check_subitems(lines):
    hits = []
    for i, l in enumerate(lines, 1):
        if not l.startswith("|") or not ROW_ID.match(l):
            continue
        n = len(SUBITEM.findall(l))
        if n:
            hits.append((i, f"列內 {n} 個子項已標結案未清 —— {_WS.sub(' ', l)[:45]}"))
    return hits


def check_refs(lines):
    gap_ids, all_ids = set(), set()
    for title, s, e in sections(lines):
        ids = {m.group(1) for l in lines[s:e] for m in [ROW_ID.match(l)] if m}
        all_ids |= ids
        if "缺口" in title:
            gap_ids |= ids
    pool = gap_ids or all_ids
    if not pool:
        return []
    hits = []
    for i, l in enumerate(lines, 1):
        if "_README" in l or ".md`" in l:
            continue
        for m in REF.finditer(l):
            if m.group(1) not in pool:
                hits.append((i, f"№{m.group(1)} 於缺口表查無此列 —— {_WS.sub(' ', l).strip()[:50]}"))
    return hits


def count_files(d: Path, recursive: bool):
    if not d.is_dir():
        return None
    it = d.rglob("*") if recursive else d.iterdir()
    return sum(1 for p in it if p.is_file() and not p.name.startswith(("_", "~$", ".")))


def manifest_count(base: Path):
    """「份」＝受控文件＝ `_manifest.json` 條目數；沒有 manifest 回 None。"""
    mf = base / "_manifest.json"
    if not mf.is_file():
        return None
    try:
        data = json.loads(mf.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict):
        data = data.get("files") or data.get("entries") or []
    return len(data) if isinstance(data, list) else None


def check_counts(lines, md: Path):
    base, hits = md.parent, []
    for i, l in enumerate(lines, 1):
        for m in CNT_DIR.finditer(l):
            actual, src = manifest_count(base), "manifest 受控"
            if actual is None:
                actual, src = count_files(base, True), "實際"
            if actual is not None and actual != int(m.group(1)):
                hits.append((i, f"目錄內容宣稱 {m.group(1)} 份，{src} {actual} 份"))
        for pat in (CNT_SUB, CNT_TREE):
            for m in pat.finditer(l):
                name, claimed = m.group(1), int(m.group(2))
                actual = count_files(base / name, False)
                if actual is not None and actual != claimed:
                    hits.append((i, f"`{name}/` 宣稱 {claimed} 份，實際 {actual} 份"))
    return hits


def vault_basenames():
    global _VAULT_NAMES
    if _VAULT_NAMES is None:
        _VAULT_NAMES = {p.name for p in ROOT.rglob("*")
                        if p.is_file() and not any(d in p.parts for d in SKIP_DIRS)}
    return _VAULT_NAMES


def check_filenames(lines, md: Path):
    base = md.parent
    known = {p.name for p in base.rglob("*") if p.is_file()} if base.is_dir() else set()
    stems = {n.rsplit(".", 1)[0] for n in known}
    hits = []
    for i, l in enumerate(lines, 1):
        for m in FNAME.finditer(l):
            name = m.group(1).strip()
            if FNAME_SKIP.search(name):
                continue
            # 🔴 #29：`{alias}::{路徑}` 是 source key（見 wiki-repo skill「Source key 格式」），
            # 不是 vault 相對路徑。不解析就會把「檔案明明在外部 repo 裡」誤報成不存在
            # —— 而且愈照慣例寫愈會被罵，等於在懲罰正確用法。
            if "::" in name:
                try:
                    tgt = resolve_source(ROOT, name)
                except Exception:
                    tgt = None
                if tgt is None:
                    hits.append((i, f"source key 的 alias 未註冊：{name}"))
                elif not tgt.exists():
                    hits.append((i, f"source key 指向的檔案不存在：{name}"))
                continue
            if "/" in name or "\\" in name:
                name = name.replace("\\", "/")
                tail = name.rsplit("/", 1)[-1]
                if (ROOT / name).exists() or tail in known or tail in vault_basenames():
                    continue
                hits.append((i, f"引用的路徑不存在：{name}"))
                continue
            if name in known or name.rsplit(".", 1)[0] in stems or name in vault_basenames():
                continue
            head = name.split("｜")[0]
            near = sorted(n for n in known if n.startswith(head))
            tip = f"；同名前綴現有：{near[0]}" if near else ""
            hits.append((i, f"引用的檔案不存在：{name}{tip}"))
    return hits


def est_tokens(text: str) -> int:
    """粗估：中文字 ×1 ＋ 其餘字元 ×0.3。只用於相對比較。"""
    cjk = len(re.findall(r"[一-鿿]", text))
    return int(cjk + (len(text) - cjk) * 0.3)


def check_cap(text, lines, kind):
    hits, pol = [], POLICY.get(kind, {})
    tok, cap_t = est_tokens(text), pol.get("tokens")
    if cap_t and tok > cap_t:
        hits.append((1, f"{kind} 上限 {cap_t} tok，實際 {tok} tok（{len(lines)} 行；行數不代表重量）"))
    cap_i = pol.get("items")
    if cap_i:
        n = sum(1 for l in lines if ROW_ID.match(l))
        if n > cap_i:
            hits.append((1, f"{kind} 項數上限 {cap_i} 條，實際 {n} 條編號列"))
    guard = pol.get("guard_bytes")
    if guard and len(text.encode("utf-8")) > guard:
        hits.append((1, f"{len(text.encode('utf-8')):,} bytes 超過 big_read_guard 門檻 {guard:,}"))
    for l in lines[:25]:
        m = CAP.search(l)
        if m and len(lines) > int(m.group(1)):
            hits.append((1, f"檔頭自訂上限 {m.group(1)} 行，實際 {len(lines)} 行 —— 輪替沒執行"))
            break
    return hits


def coord_rows():
    p = ROOT / COORD
    if not p.is_file():
        return {}
    out = {}
    for l in p.read_text(encoding="utf-8", errors="replace").split("\n"):
        m = ROW_ID.match(l)
        if m:
            out.setdefault(m.group(1), l)
    return out


def _rel(md: Path):
    return md.relative_to(ROOT).as_posix()


def check_xref(lines, md: Path, rows):
    """T7：只查點名 coordination 的活指標；引號內的 #N 是引述舊文不算。"""
    if not rows or _rel(md) == COORD:
        return []
    hits = []
    for i, l in enumerate(lines, 1):
        if "coordination" not in l:
            continue
        bare = QUOTED.sub("", l)
        for m in XREF_HASH.finditer(bare):
            if m.group(1) not in rows:
                hits.append((i, f"#{m.group(1)} 在 coordination 已無此列 —— {_WS.sub(' ', bare).strip()[:48]}"))
        for m in XREF_CLAIM.finditer(bare):
            if int(m.group(1)) != len(rows):
                hits.append((i, f"宣稱待辦 {m.group(1)} 項，coordination 實際 {len(rows)} 條 —— 指標不該複寫內容"))
    return hits


def check_archived(md: Path, rows):
    """T8：語義規則的機械代理，輸出一律標「疑似」。"""
    p = ROOT / "wiki" / "log.md"
    if not rows or not p.is_file() or _rel(md) != COORD:
        return []
    hits = []
    for i, l in enumerate(p.read_text(encoding="utf-8", errors="replace").split("\n"), 1):
        if not ARCHIVED.search(l):
            continue
        for m in XREF_HASH.finditer(QUOTED.sub("", l)):
            row = rows.get(m.group(1))
            if row and not CLOSED_MARK.search(row):
                hits.append((1, f"疑似：log.md:{i} 稱 #{m.group(1)} 不得再提，但本頁該列仍未結案 —— {_WS.sub(' ', row)[:44]}"))
    return hits


def check_undeclared():
    hits = []
    for rel in SNAPSHOT_FILES:
        p = ROOT / rel
        if not p.is_file():
            continue
        m = MARKER.search(p.read_text(encoding="utf-8", errors="replace")[:600])
        if not m:
            hits.append(f"{rel} —— 位於快照區但未宣告 maintenance")
        elif m.group(1) not in KINDS:
            hits.append(f"{rel} —— maintenance: {m.group(1)} 不是已知型別 {KINDS}")
    return hits


def main():
    global ROOT
    ROOT = find_vault_root(Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
    quiet = "--quiet" in sys.argv
    if ROOT is None:
        if not quiet:                       # hook 用 --quiet：非 vault 目錄完全安靜
            print("找不到 vault（往上找不到含 wiki/ 或 raw/.manifest.json 的目錄）")
        return 0
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    target = Path(args[0]) if args else ROOT
    if not target.is_absolute():
        target = ROOT / target
    if not target.exists():
        print(f"找不到路徑：{target}")
        return 0
    whole = target.resolve() == ROOT.resolve()

    rows = coord_rows()
    files, total = [], 0
    for md in iter_md(target):
        try:
            text = md.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        fm = text.split("---")[1] if text.startswith("---") and "---" in text[3:] else ""
        m = MARKER.search(fm)
        if not m:
            continue
        kind, lines = m.group(1), text.split("\n")
        if kind == "frozen":                 # 凍結紀錄：寫完就不該再動，沒有「待整理」可言
            files.append((md, 0, kind, []))
            continue
        found = [("T1 已結案列", check_closed(lines)),
                 ("T2 斷掉的引用", check_refs(lines)),
                 ("T3 數量不符", check_counts(lines, md)),
                 ("T4 檔名過期", check_filenames(lines, md)),
                 ("T5 列內殘留", check_subitems(lines)),
                 ("T6 超出型別上限", check_cap(text, lines, kind)),
                 ("T7 跨檔編號斷鏈", check_xref(lines, md, rows)),
                 ("T8 裁示未清登記", check_archived(md, rows))]
        n = sum(len(h) for _, h in found)
        total += n
        files.append((md, n, kind, found))

    undeclared = check_undeclared() if whole else []
    total += len(undeclared)

    kinds = ", ".join(sorted({k for _, _, k, _ in files})) or "—"
    if not quiet:
        print("=== tidy-check ===")
        print(f"input   : {len(files)} 檔有 maintenance 宣告（{kinds}）｜coordination {len(rows)} 條編號列")
        if undeclared:
            print(f"\n🟡 [T0 快照區未宣告] {len(undeclared)}")
            for u in undeclared:
                print(f"      {u}")
        for md, n, kind, found in files:
            if n == 0:
                mark, note = ("🧊", "凍結紀錄，不列整理候選") if kind == "frozen" else ("🟢", "乾淨")
                print(f"\n{mark} {_rel(md)}（{kind}）—— {note}")
                continue
            print(f"\n🟡 {_rel(md)}（{kind}）—— {n} 項待整理")
            for label, hits in found:
                if not hits:
                    continue
                print(f"   [{label}] {len(hits)}")
                for ln, body in hits[:8]:
                    print(f"      L{ln}: {body}")
                if len(hits) > 8:
                    print(f"      … 另 {len(hits) - 8} 項")
    if not quiet:
        print()
        print("-" * 60)
    if total == 0:
        print("verdict : 🟢 CLEAN —— 無待整理項目")
    else:
        print(f"verdict : 🟡 {total} 項待整理（僅為候選；刪除前 MUST grep wiki/log.md，查不到就先補寫再刪）")
    if whole:
        _guard_status.record("tidy-check", "CLEAN" if total == 0 else f"{total} 項", 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
