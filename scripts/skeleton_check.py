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
from _lib.filehash import md5_of  # noqa: E402
from _lib.vaultpaths import find_vault_root  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "vault"
PLUGIN_JSON = Path(__file__).resolve().parent.parent / ".claude-plugin" / "plugin.json"
SKELETON = ".skeleton.json"
NL = chr(10)
HISTORY = "wiki/meta/init-history.md"

# 這些檔的內容本來就該長成每個 vault 自己的樣子（樣板只是空殼），不列入骨架對帳 ——
# 列進去等於每次都報「已客製」，純噪音。骨架對帳只管「規則與模板」，不管「資料」。
DATA_FILES = {
    "wiki/log.md",            # 歷程，append-only
    "wiki/hot.md",            # 每日輪替
    "wiki/index.md",          # 導航，隨 vault 內容長
    "wiki/agenda.md",         # 日程
    "wiki/meta/coordination.md",  # 登記簿
    "raw/.manifest.json",     # ingest 來源紀錄
    ".claude/settings.json",  # 每台機器自己的設定
}


def template_files(tdir=None):
    """樣板裡該納入對帳的檔（相對路徑）。.gitkeep 是佔位，不是骨架。"""
    tdir = tdir or TEMPLATE_DIR
    out = []
    for p in sorted(tdir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(tdir).as_posix()
        if p.name == ".gitkeep" or rel in DATA_FILES:
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


def added_lines(tpl: Path, local: Path, limit=6):
    """樣板新增的行。只看「多了什麼」——使用者自己加的東西他自己知道，不用唸回去。

    含 `{{…}}` 的行一律不算：那是 init 當下會被填掉的佔位符（`updated: {{today}}`、`# {{name}}`），
    vault 裡早就是實際值，永遠比得出差異。2026-10-09 乾跑 wiki-test 時 9 個檔有 5 個
    的「差異」全是這個，純誤報。
    """
    import difflib
    rd = lambda p: p.read_text(encoding="utf-8", errors="replace").split(chr(10)) if p.is_file() else []
    out = []
    for d in difflib.unified_diff(rd(local), rd(tpl), lineterm="", n=0):
        if d.startswith("+") and not d.startswith("+++"):
            t = d[1:].strip()
            if t and "{{" not in t:
                out.append(t)
    return out[:limit], len(out)


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
    """回 (三組, 降級模式?)。每項 = {rel, tpl_hash, local_hash, sections, lines, n_added, why}"""
    tdir = template_dir or TEMPLATE_DIR
    sk = load_skeleton(root)
    degraded = sk is None
    recorded = (sk or {}).get("files", {})
    # 降版（樣板比 vault 記錄的舊）只往前不倒退：使用者裝回舊 plugin 時不該被要求「升級」回去
    now = ver_tuple(plugin_version if plugin_version is not None else current_plugin_version())
    was = ver_tuple((sk or {}).get("plugin_version"))
    if now and was and now < was:
        return ([], [], []), degraded
    missing, safe, custom = [], [], []
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
                lines, n = added_lines(tpl, local)
                secs = new_sections(tpl, local)
                if not secs and n == 0:
                    continue      # 差異只有佔位符／你自己加的東西，樣板沒帶來新內容 → 不用唸
                custom.append({"rel": rel, "tpl_hash": tpl_hash, "local_hash": local_hash,
                               "sections": secs, "lines": lines, "n_added": n,
                               "why": "降級模式：沒有 .skeleton.json，無法分辨是你改的還是樣板改的"})
            continue
        if tpl_hash == base_tpl:
            continue                                  # 樣板沒變，絕大多數落這裡
        lines, n = added_lines(tpl, local)
        if not new_sections(tpl, local) and n == 0:
            continue      # 樣板這次沒帶來新內容（差異只有佔位符／潤稿）→ 不用唸
        if local_hash == base_local:
            safe.append({"rel": rel, "tpl_hash": tpl_hash, "local_hash": local_hash,
                         "sections": new_sections(tpl, local), "lines": lines, "n_added": n,
                         "why": "樣板更新了，你沒動過這個檔"})
        else:
            custom.append({"rel": rel, "tpl_hash": tpl_hash, "local_hash": local_hash,
                           "sections": new_sections(tpl, local), "lines": lines, "n_added": n,
                           "why": "樣板更新了，你也改過這個檔"})
    return (missing, safe, custom), degraded


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
    (missing, safe, _), _ = classify(root, tdir, ver)
    for it in missing + safe:
        dst = root / it["rel"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(tdir / it["rel"]), str(dst))
    done = [m["rel"] for m in missing] + [s["rel"] for s in safe]
    if done:
        append_history(root, sk_before, ver,
                       [m["rel"] for m in missing], [s["rel"] for s in safe], [], [])
    write_skeleton(root, tdir, ver, only=done)
    return len(done)


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("vault", nargs="?", default=None)
    ap.add_argument("--json", action="store_true")
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

    (missing, safe, custom), degraded = classify(root)
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
            if it.get("n_added"):
                print(f"         ＋樣板多了 {it['n_added']} 行：")
                for ln in it["lines"]:
                    print(f"             {ln[:76]}")
                if it["n_added"] > len(it["lines"]):
                    print(f"             … 另 {it['n_added'] - len(it['lines'])} 行")
    print(f"\nverdict : 🟡 {total} 項（缺 {len(missing)}／可換 {len(safe)}／要融合 {len(custom)}）")
    print("          本腳本只比對，不寫任何檔。升級走 /wiki-init（它會逐組問你）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
