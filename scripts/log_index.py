#!/usr/bin/env python3
"""wiki/log.md 行內索引：每條 `## YYYY-MM-DD …` 標題下一行放機器推導的標記。

問題：log.md 只增不減，`grep 產品名 wiki/log.md` 回傳量與檔案同步成長，big_read_guard 管不到 Grep。
另抽一份 decisions.md 的路走過並失敗（靠人自覺判斷「這算不算裁示」的機制不會活）。
做法：標記全部由內容推導、可隨時重生（--apply 冪等）；grep 只撈標記行，一條一行，與條目長度脫鉤。

    <!-- log kind:ingest,裁示 scope:產品A,meta ref:SPEC-07 -->
  kind  ：標題 op 欄（`| save |`）、日期後綴詞（新建／補記／收尾）、內文含「使用者…裁示」加 `裁示`
  scope ：內文命中的產品／主題（清單從 wiki/products/*.md 推導，沒有就用 wiki/topics/*.md；
          支援頁面 frontmatter `aliases:`）、meta（scripts/ skills/ CLAUDE.md wiki/ops wiki/meta）、否則 general
  ref   ：內文的 ID 樣式 token（如 SPEC-07、PROC-14、WI-03-A），去重排序，最多 12 個

用法：--check（只報數，exit 0）／--apply（寫入）／--query scope:X kind:裁示（AND；值內逗號＝OR，直接從內容推導）
標記是 HTML 註解，Obsidian 閱讀模式不顯示。
"""
import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib.logparse import load_entries, log_path  # noqa: E402
from _lib.vaultpaths import find_vault_root  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

MARK = re.compile(r"^<!-- log (.*?) -->$")
OP = re.compile(r"^[|·\s]*([A-Za-z][A-Za-z\-]+)\b")
OPS = {"save", "ingest", "update", "restructure", "query", "lint", "doctor", "fold", "autoresearch",
       "new-product", "init", "setup", "session", "repo"}
SUFFIX = re.compile(r"^(新建|補記|收尾|上午|下午|續)\b")
RULING = re.compile(r"使用者[^\n]{0,12}?裁示")
REF = re.compile(r"\b[A-Z]{2,4}-\d{2}(?:-\d{2})?(?:-[A-Z])?\b")
META_HINT = re.compile(r"scripts/|skills/|CLAUDE\.md|coordination|wiki/ops/|wiki/meta/|tidy[-_]check|stale[-_]check|vault_state")
ALIASES_LINE = re.compile(r"^aliases:\s*\[?(.*?)\]?\s*$")
MAX_REF = 12


def scope_terms(root: Path):
    """{顯示名: [比對詞…]}，清單從資料夾檔名推導，零維護。"""
    for folder in ("products", "topics"):
        pages = sorted((root / "wiki" / folder).glob("*.md")) if (root / "wiki" / folder).is_dir() else []
        if pages:
            break
    out = {}
    for p in pages:
        terms = [p.stem]
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:1500].split("\n")
        except OSError:
            head = []
        for i, l in enumerate(head[:40]):
            m = ALIASES_LINE.match(l)
            if not m:
                continue
            inline = [x.strip(" \"'") for x in m.group(1).split(",") if x.strip(" \"'")]
            for l2 in head[i + 1:i + 20]:
                if l2.strip().startswith("- "):
                    inline.append(l2.strip()[2:].strip(" \"'"))
                elif l2.strip():
                    break
            terms += inline
            break
        out[p.stem] = [t for t in terms if t]
    return out, folder if pages else None


def derive(entry, lines, scopes):
    title = entry["title"]
    body = "\n".join(lines[entry["start"]:entry["end"]])
    kinds = []
    m = OP.match(title)
    if m and m.group(1).lower() in OPS:
        kinds.append(m.group(1).lower())
    m = SUFFIX.match(title)
    if m:
        kinds.append(m.group(1))
    if RULING.search(body):
        kinds.append("裁示")
    if not kinds:
        kinds.append("note")
    scope = {name for name, terms in scopes.items() if any(t in body for t in terms)}
    if META_HINT.search(body):
        scope.add("meta")
    if not scope:
        scope.add("general")
    return {"kind": sorted(set(kinds)), "scope": sorted(scope), "ref": sorted(set(REF.findall(body)))}


def marker(d):
    refs = d["ref"]
    ref_s = ",".join(refs[:MAX_REF]) + (f",+{len(refs) - MAX_REF}" if len(refs) > MAX_REF else "")
    return f"<!-- log kind:{','.join(d['kind'])} scope:{','.join(d['scope'])} ref:{ref_s or '-'} -->"


def existing_marker(entry, lines):
    for i in range(entry["start"] + 1, min(entry["end"], entry["start"] + 3)):
        if lines[i].strip() == "":
            continue
        return (i, lines[i]) if MARK.match(lines[i].strip()) else None
    return None


def plan(lines, entries, scopes):
    missing, stale, out = [], [], list(lines)
    for e in sorted(entries, key=lambda e: e["start"], reverse=True):   # 由後往前改，行號才不位移
        want = marker(derive(e, lines, scopes))
        have = existing_marker(e, lines)
        if have is None:
            missing.append(e)
            out.insert(e["start"] + 1, want)
        elif have[1].strip() != want:
            stale.append(e)
            out[have[0]] = want
    return missing, stale, out


def parse_query(tokens):
    q = {}
    for t in tokens:
        if ":" not in t:
            sys.exit(f"query 格式：kind:xxx scope:xxx ref:xxx（收到 {t!r}）")
        k, v = t.split(":", 1)
        q.setdefault(k, set()).update(x for x in v.split(",") if x)
    return q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只報缺／過期標記數")
    ap.add_argument("--apply", action="store_true", help="寫入標記（冪等）")
    ap.add_argument("--query", nargs="+", metavar="K:V", help="列符合的條目（AND；值內逗號＝OR）")
    a = ap.parse_args()

    root = find_vault_root(Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
    if root is None:
        print("error   : 找不到 vault")
        return 0
    log = log_path(root)
    if not log.is_file():
        print("error   : 找不到 wiki/log.md")
        return 0
    lines, entries = load_entries(log)
    scopes, src = scope_terms(root)

    if a.query:
        q = parse_query(a.query)
        hits = [(e, d) for e in entries for d in [derive(e, lines, scopes)]
                if all(set(d.get(k, [])) & vals for k, vals in q.items())]
        print(f"=== log-index query {' '.join(a.query)} === {len(hits)}／{len(entries)} 條")
        for e, d in sorted(hits, key=lambda x: x[0]["date"], reverse=True):
            print(f"L{e['start'] + 1}-{e['end']}  {e['date']}  {e['title'][:70]}")
        return 0

    missing, stale, out = plan(lines, entries, scopes)
    print("=== log-index ===")
    print(f"input   : {len(entries)} 條｜scope 清單 {len(scopes)}（wiki/{src}/）" if src
          else f"input   : {len(entries)} 條｜scope 清單 0（wiki/products/ 與 wiki/topics/ 皆無頁面；scope 只會標 meta／general）")
    print(f"missing : {len(missing)}　stale : {len(stale)}")
    if a.apply and (missing or stale):
        log.write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"written : 補 {len(missing)}、更新 {len(stale)}")
        missing, stale = [], []
    elif a.apply:
        print("written : 0（已是最新）")
    print("verdict : " + ("🟢 CLEAN — 每條都有現行標記" if not (missing or stale)
                         else f"🟡 {len(missing) + len(stale)} 條待補（log_index.py --apply）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
