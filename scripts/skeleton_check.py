#!/usr/bin/env python3
"""骨架對帳 —— vault 建好那天的樣板，跟現在 plugin 的樣板差在哪。

為什麼要有這支：`wiki-init` 建骨架是一次性快照。之後 plugin 升級，`skills/` 會跟著更新
（從 plugin 讀），但已建好的 vault 那 30 個檔永遠停在建立那天，而且**沒有任何東西會發現**。
實例（2026-10-09）：`06-coordination格式.md` 新增「狀態欄寫登記日」，tidy_check 的 T9 靠它；
舊 vault 沒有這條規則，使用者也不會知道要加。

分類（`.skeleton.json` 記兩個 hash 才分得出是誰改的 —— base／theirs／mine）：

  ① 缺檔      vault 沒有這個樣板檔（且未 opted_out）
  ② 未客製    樣板變了，你的檔還等於上次對帳時的樣子  → 可安全換
  ③ 已客製    樣板變了，你的檔也變了                  → 要融合，本腳本不碰

沒有 `.skeleton.json`（所有既有 vault 的第一次）→ 降級模式：base 未知，
只能比「你的 vs 現行樣板」，有差異一律進 ③，寧可多問。

🔴 本腳本只做機械比對。「這版多了什麼功能」「怎麼融合」是判斷，交給 wiki-init skill。

用法：
  skeleton_check.py [vault路徑]          人讀的三組報告
  skeleton_check.py --json               給 skill 吃的結構化輸出
exit 一律 0 —— 提醒不是閘門。只用 stdlib；語法相容 Python 3.9。
"""
import argparse
import datetime
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import init_vault  # noqa: E402  —— 共用 render()，佔位符語法只有一處定義
from _lib.filehash import md5_of  # noqa: E402
from _lib.vaultpaths import find_vault_root  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "vault"
PLUGIN_JSON = Path(__file__).resolve().parent.parent / ".claude-plugin" / "plugin.json"
SKELETON = ".skeleton.json"
NL = chr(10)
HISTORY = "wiki/meta/init-history.md"

POLICY = ".skeleton-policy"

# 佔位符：init_vault.render() 在建 vault 時把 `{{key}}` 換成實際值。
# 🔴 兩邊是同一套語法，改一邊要改另一邊（這裡只判斷存在，不做代換，所以沒有共用模組）。
PLACEHOLDER = "{{"


def skip_globs(tdir=None):
    """讀 `.skeleton-policy`：不比內容的樣板檔（glob，相對樣板根）。

    清單放在樣板旁邊而不是寫在這支腳本裡 —— 加樣板檔的人跟改腳本的人不是同一次動作，
    寫在程式裡就會漏。政策檔自己也不對帳、不複製進 vault。
    """
    tdir = tdir or TEMPLATE_DIR
    p = tdir / POLICY
    out = [POLICY]
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8", errors="replace").split(NL):
        pat = line.split("#")[0].strip()
        if pat:
            out.append(pat)
    return out


def template_files(tdir=None):
    """樣板裡該納入對帳的檔（相對路徑）。排除 `.skeleton-policy` 列的那些。"""
    import fnmatch
    tdir = tdir or TEMPLATE_DIR
    skips = skip_globs(tdir)
    out = []
    for p in sorted(tdir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(tdir).as_posix()
        if any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(rel, g.lstrip("*/")) for g in skips):
            continue
        out.append(rel)
    return out


def current_plugin_version():
    try:
        return json.loads(PLUGIN_JSON.read_text(encoding="utf-8")).get("version", "")
    except (ValueError, OSError):
        return ""


def ver_tuple(v: str):
    """`1.10.2` → (1, 10, 2)；比不出來就回 ()，呼叫端當作無法判斷。"""
    try:
        return tuple(int(x) for x in str(v).split("."))
    except (TypeError, ValueError):
        return ()


def headings(p: Path):
    """檔裡的 ## 段落標題。比對段落比比對行有用：行差異多半是潤稿，段落差異才是功能。"""
    if not p.is_file():
        return []
    try:
        txt = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [l.strip() for l in txt.split(chr(10)) if l.startswith("##")]


def same_heading(a: str, b: str) -> bool:
    """標題只在後面補了註解時算同一段 —— `## 分工` 與 `## 分工（名稱會變…）` 是同一段，
    精確比對會報成一加一減（2026-10-09 乾跑 wiki-test 實際踩到）。"""
    cut = lambda h: h.split("（")[0].split("(")[0].rstrip("# ").strip()
    return cut(a) == cut(b)


def new_sections(tpl: Path, local: Path):
    """樣板有、你沒有的段落（標題後補註解的不算新段）。"""
    mine = headings(local)
    return [h for h in headings(tpl) if not any(same_heading(h, m) for m in mine)]


def diff_lines(tpl: Path, local: Path, limit=6):
    """樣板相對於你的檔，多了哪幾行、少了幾行。回 (前 limit 行新增, 新增數, 刪除數)。

    **新增**：講「這版多了什麼功能」用的。你自己加的東西你知道，不唸回去。
    **刪除**：樣板廢掉一條規則也是升級，只看新增會整個漏掉
    （llm-wiki-aegiverse-e4 2026-10-09 review 指出；該 vault 前一天剛廢掉一條判準）。

    兩邊都先把「佔位符那一組行」拿掉再比：樣板的 `updated: {{today}}` 與 vault 的
    `updated: 2026-09-21` 是同一行的兩個樣子，不先配掉的話，前者算新增、後者算刪除，
    一行製造兩筆誤報。
    """
    import difflib
    import re
    rd = lambda p: p.read_text(encoding="utf-8", errors="replace").split(chr(10)) if p.is_file() else []
    tl, ll = rd(tpl), rd(local)
    # 樣板的佔位符行 → 比對式（`updated: {{today}}` → `^updated:\s*.*$`），用來認出 vault 裡被填過的那一行
    pats = []
    for line in tl:
        if PLACEHOLDER not in line:
            continue
        # 🔴 整行只有佔位符（`{{domain}}`）→ 比對式會變成 `^.*$`，把 local 每一行都當成它，
        # 整個檔的差異被抹平。那種行沒有可辨識的骨架，只能放棄配對（代價是多報一筆，不是漏報）。
        if not re.sub(r"\{\{\w+\}\}", "", line).strip():
            continue
        pats.append(re.compile("^" + re.sub(r"\\\{\\\{\w+\\\}\\\}", ".*", re.escape(line.strip())) + "$"))
    tl = [l for l in tl if PLACEHOLDER not in l]
    ll = [l for l in ll if not any(p.match(l.strip()) for p in pats)]
    out, removed = [], 0
    for d in difflib.unified_diff(ll, tl, lineterm="", n=0):
        t = d[1:].strip()
        if not t:
            continue
        if d.startswith("+") and not d.startswith("+++"):
            out.append(t)
        elif d.startswith("-") and not d.startswith("---"):
            removed += 1
    return out[:limit], len(out), removed


def first_line(p: Path):
    """檔案在講什麼：拿第一個 # 標題，沒有就第一行非空白。"""
    if not p.is_file():
        return ""
    for l in p.read_text(encoding="utf-8", errors="replace").split(chr(10))[:40]:
        if l.startswith("#"):
            return l.lstrip("# ").strip()
    return ""


def load_skeleton(root: Path):
    p = root / SKELETON
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None      # 損毀就當沒有，退回降級模式，不報錯


def classify(root: Path, template_dir=None, plugin_version=None):
    """回 (三組, info)。

    info = {degraded, downgrade, trivial}。trivial 是「有差異但判斷不用報」的檔與原因 ——
    🔴 降噪一定要留得下紀錄，否則判斷錯就等於把變更藏起來，跟這支腳本要解決的病一樣。
    """
    tdir = template_dir or TEMPLATE_DIR
    sk = load_skeleton(root)
    degraded = sk is None
    recorded = (sk or {}).get("files", {})
    # 降版（樣板比 vault 記錄的舊）只往前不倒退：使用者裝回舊 plugin 時不該被要求「升級」回去
    now = ver_tuple(plugin_version if plugin_version is not None else current_plugin_version())
    was = ver_tuple((sk or {}).get("plugin_version"))
    if now and was and now < was:
        return ([], [], []), {"degraded": degraded, "downgrade": (was, now), "trivial": [], "retired": []}
    # plugin 這版不再提供的樣板檔：只說一聲，絕不碰 vault 裡那個檔。
    # 判斷依據是「上次對帳記錄裡有、現在的樣板沒有」，所以降級模式（沒有 .skeleton.json）看不出來。
    live = set(template_files(tdir))
    retired = sorted(r for r, n in recorded.items() if r not in live and not n.get("opted_out"))
    missing, safe, custom, trivial = [], [], [], []
    for rel in template_files(tdir):
        note = recorded.get(rel, {})
        if note.get("opted_out"):
            continue
        tpl = tdir / rel
        local = root / rel
        tpl_hash = md5_of(tpl)
        if not local.is_file():
            missing.append({"rel": rel, "tpl_hash": tpl_hash, "about": first_line(tpl)})
            continue
        local_hash = md5_of(local)
        base_tpl = note.get("template_hash")
        base_local = note.get("local_hash")
        if degraded or base_tpl is None:
            # base 未知：只能比「你的 vs 現行樣板」，不同就當客製過
            if local_hash != tpl_hash:
                lines, n, _gone = diff_lines(tpl, local)
                secs = new_sections(tpl, local)
                # 降級模式不看「你有、樣板沒有」的行數：沒有 base 就分不出那是你加的
                # 還是樣板廢掉的，而絕大多數是前者（wiki-test 的 rulings.md 有 80 行自己的裁示）。
                # 報出來只會變噪音，所以這裡只認「樣板帶來了新內容」。
                if not secs and n == 0:
                    trivial.append((rel, "有差異，但扣掉佔位符之後樣板沒帶來新內容（降級模式看不出刪除）"))
                    continue
                custom.append({"rel": rel, "tpl_hash": tpl_hash, "local_hash": local_hash,
                               "sections": secs, "lines": lines, "n_added": n,
                               "why": "降級模式：沒有 .skeleton.json，無法分辨是你改的還是樣板改的"})
            continue
        if tpl_hash == base_tpl:
            continue                                  # 樣板沒變，絕大多數落這裡
        lines, n, gone = diff_lines(tpl, local)
        if not new_sections(tpl, local) and n == 0 and gone == 0:
            trivial.append((rel, "樣板這次只動了佔位符或潤稿，沒有新增也沒有刪除"))
            continue
        # 🔴 `local_hash == base_local` 只代表「上次對帳後沒再動」，不代表它曾經等於樣板。
        # CLAUDE.md／wiki/ops/*.md 建 vault 當天就是真規則層、樣板是空殼，而且常常幾個月沒人動 ——
        # 少了 base_local == base_tpl 這個條件，樣板一改它就落進「可安全換」，整份被覆蓋。
        # （llm-wiki-aegiverse-e4 2026-10-09 review 實跑驗出；一開始就分岔的檔永遠只能進組③）
        if local_hash == base_local and base_local == base_tpl:
            safe.append({"rel": rel, "tpl_hash": tpl_hash, "local_hash": local_hash,
                         "sections": new_sections(tpl, local), "lines": lines, "n_added": n, "n_removed": gone,
                         "why": "樣板更新了，你沒動過這個檔"})
        else:
            custom.append({"rel": rel, "tpl_hash": tpl_hash, "local_hash": local_hash,
                           "sections": new_sections(tpl, local), "lines": lines, "n_added": n, "n_removed": gone,
                           "why": "樣板更新了，你也改過這個檔"})
    return (missing, safe, custom), {"degraded": degraded, "downgrade": None,
                                     "trivial": trivial, "retired": retired}


def write_skeleton(root: Path, tdir: Path, version: str, only=None, opted_out=None):
    """把**處理過的檔**封存成新的對帳基準。

    🔴 `only` 一定要給（處理過的 rel 清單）。沒處理的檔若也一起封存，等於宣告「已對帳」，
    下次就不會再報 —— 待融合的檔會被默默吞掉（2026-10-09 對 wiki-test 複本實跑時踩到：
    5 個待融合的檔被記成已對帳，報告變 🟢）。
    """
    sk = load_skeleton(root) or {}
    files = sk.get("files", {})
    touched = set(only or []) | set(opted_out or [])
    for rel in template_files(tdir):
        if rel not in touched:
            continue
        local = root / rel
        if rel in (opted_out or []):
            files[rel] = {"opted_out": True}
        elif local.is_file():
            files[rel] = {"template_hash": md5_of(tdir / rel), "local_hash": md5_of(local)}
    sk.update({"plugin_version": version, "files": files,
               "updated_at": datetime.date.today().isoformat()})
    sk.setdefault("created_with", version)
    (root / SKELETON).write_text(json.dumps(sk, ensure_ascii=False, indent=1), encoding="utf-8", newline="")


def append_history(root: Path, from_ver: str, to_ver: str, added, updated, merged, skipped):
    """升級史：一次一塊，寫實際做了什麼。🔴 本檔由腳本寫，人不手改。"""
    p = root / HISTORY
    p.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    head = "" if p.is_file() else (
        "# init 升級史" + NL + NL
        + "> 🔴 本檔由 `skeleton_check.py` 寫，**人不手改**。一次升級一塊，記的是實際做了什麼。" + NL + NL)
    block = [f"## {today}　{from_ver or '（未知）'} → {to_ver}", ""]
    for label, items in (("新增", added), ("更新（未客製）", updated), ("融合", merged), ("跳過", skipped)):
        if items:
            block.append(f"- {label} {len(items)}：" + "、".join(f"`{i}`" for i in items))
    block.append("")
    with p.open("a", encoding="utf-8", newline="") as f:
        f.write(head + NL.join(block) + NL)


def apply_safe(root: Path, template_dir=None, version=None):
    """只做組①②：缺的補進來、未客製的換成新版。組③一個 byte 都不碰。回動了幾個。"""
    tdir = template_dir or TEMPLATE_DIR
    ver = version or current_plugin_version()
    sk_before = (load_skeleton(root) or {}).get("plugin_version")
    (missing, safe, _), _info = classify(root, tdir, ver)
    subs = {"name": root.name, "domain": "", "today": datetime.date.today().isoformat()}
    for it in missing + safe:
        dst = root / it["rel"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        # 🔴 要走 render，否則 `updated: {{today}}` 原樣落地（2026-10-09 review 實跑驗出 3 個檔中招）
        dst.write_bytes(init_vault.render(tdir / it["rel"], subs))
    done = [m["rel"] for m in missing] + [s["rel"] for s in safe]
    if done:
        append_history(root, sk_before, ver,
                       [m["rel"] for m in missing], [s["rel"] for s in safe], [], [])
    write_skeleton(root, tdir, ver, only=done)
    return len(done)


def record(root: Path, template_dir=None, merged=None, skipped=None, version=None):
    """組③由 skill 融合完之後呼叫：封存這些檔的新 hash、把使用者說不要的記 opted_out。

    🔴 只封存指定的 rel（同 write_skeleton 的理由）—— 沒處理的檔不能被宣告「已對帳」。
    """
    tdir = template_dir or TEMPLATE_DIR
    ver = version or current_plugin_version()
    was = (load_skeleton(root) or {}).get("plugin_version")
    merged, skipped = list(merged or []), list(skipped or [])
    if merged or skipped:
        append_history(root, was, ver, [], [], merged, skipped)
    write_skeleton(root, tdir, ver, only=merged, opted_out=skipped)
    return len(merged) + len(skipped)


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("vault", nargs="?", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="連「有差異但判斷不用報」的也列出來")
    ap.add_argument("--apply-safe", action="store_true",
                    help="只做①②（補缺檔、換未客製的），不碰已客製的檔")
    a = ap.parse_args()

    start = Path(a.vault).resolve() if a.vault else Path.cwd()
    root = find_vault_root(start)
    if root is None:
        print(f"不是 vault（往上找不到 wiki/ 或 raw/.manifest.json）：{start}")
        return 0

    if a.apply_safe:
        n = apply_safe(root)
        print(f"已補／更新 {n} 個檔（只動①②，已客製的一個 byte 都沒碰）")
        print(f"對帳基準已更新：{root / SKELETON}")
        if n:
            print(f"升級史：{root / HISTORY}")
        return 0

    (missing, safe, custom), info = classify(root)
    degraded = info["degraded"]
    sk = load_skeleton(root) or {}
    if a.json:
        print(json.dumps({"vault": str(root), "degraded": degraded,
                          "recorded_version": sk.get("plugin_version"),
                          "missing": missing, "safe": safe, "custom": custom},
                         ensure_ascii=False, indent=1))
        return 0

    total = len(missing) + len(safe) + len(custom)
    print("=== skeleton-check ===")
    print(f"vault   : {root}")
    print(f"對帳檔數: {len(template_files())}（樣板裡的規則與模板；log/hot/index/agenda 等資料檔不對帳）")
    print(f"骨架版本: {sk.get('plugin_version') or '（沒有 .skeleton.json）'}")
    if degraded:
        print("模式    : 🟡 降級 —— 無法分辨「你改的」與「樣板改的」，有差異一律歸到③；跑過一次升級後就準")
    if total == 0:
        print("\nverdict : 🟢 骨架已是最新")
        return 0
    for label, group in (("① 缺檔", missing), ("② 未客製，樣板有更新", safe), ("③ 已客製，要融合", custom)):
        if not group:
            continue
        print(f"\n[{label}] {len(group)}")
        for it in group:
            print(f"      {it['rel']}" + (f"  —— {it['about']}" if it.get("about") else ""))
            for h in it.get("sections", [])[:3]:
                print(f"         ＋新段落：{h}")
            if it.get("n_removed"):
                print(f"         －你有、樣板沒有：{it['n_removed']} 行（樣板這版廢掉的，或你自己加的）")
            if it.get("n_added"):
                print(f"         ＋樣板多了 {it['n_added']} 行：")
                for ln in it["lines"]:
                    print(f"             {ln[:76]}")
                if it["n_added"] > len(it["lines"]):
                    print(f"             … 另 {it['n_added'] - len(it['lines'])} 行")
    if info.get("retired"):
        print(f"\n[⚪ plugin 不再提供] {len(info['retired'])}　—— 你的檔不會被動，只是 plugin 這版起不再維護它")
        for rel in info["retired"]:
            print(f"      {rel}")
    if info["trivial"]:
        if a.verbose:
            print(f"\n[略過 —— 有差異但判斷不用報] {len(info['trivial'])}")
            for rel, why in info["trivial"]:
                print(f"      {rel}  —— {why}")
        else:
            print(f"\n（另有 {len(info['trivial'])} 個檔有差異但判斷不用報，--verbose 看是哪些）")
    print(f"\nverdict : 🟡 {total} 項（缺 {len(missing)}／可換 {len(safe)}／要融合 {len(custom)}）")
    print("          本腳本只比對，不寫任何檔。升級走 /wiki-init（它會逐組問你）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
