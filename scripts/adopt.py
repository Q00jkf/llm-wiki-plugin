#!/usr/bin/env python3
"""既有 vault 改用 plugin 版系統：找出撞名、算差異、撈出不能弄丟的紀錄。

情境：vault 本身有 skills/wiki-ingest/，plugin 也有 —— 兩份同名會讓 Claude 不確定用哪個。
正解是刪掉 vault 版、改用 plugin 版，但**客製化不能跟著陪葬**。

🔴 本腳本只做偵測與分析，不刪任何東西。刪不刪是判斷，由 wiki-adopt skill 帶著人走。

用法：
    python adopt.py                  # 撞名總覽
    python adopt.py --diff <名稱>     # 單項逐行差異
    python adopt.py --rescue         # 只列「刪掉就永遠消失」的內容
"""
import argparse
import difflib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import filehash as _filehash  # noqa: E402
from _lib.vaultpaths import find_vault_root  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 「刪掉就永遠消失」的內容特徵：裁示、踩雷、教訓。
# 這類句子通常只寫在那個人自己的 skill 裡，wiki 沒有、git message 沒有、沒有別的家。
# 🔴 中英文都要認：早期只列中文關鍵字，英文僅認 MUST，對英文寫的 skill 幾乎全漏。
#    實測 LLM-wiki-Template-share（英文 skill）：738 行 vault 獨有內容只撈到 5 行，
#    wiki-fold／wiki-query 更是回報「需搶救 0」—— 照那個數字刪，整個功能就沒了。
#    （2026-09-21 驗收 #21）
RESCUE_PAT = re.compile(
    r"(🔴|⚠️|🔑|⛔|🔒|不要|不得|不可|禁止|絕不|勿|務必|一律|鐵律|踩|教訓|裁示|裁定|實測|坑|代價|曾因|導致|錯誤示範|v20\d\d-"
    r"|\bMUST(?:\s+NOT)?\b|\bSHOULD\s+NOT\b|\bNEVER\b|\bALWAYS\b|\bREQUIRED\b|\bFORBIDDEN\b"
    r"|\bdo not\b|\bdon't\b|\bcannot\b|\bavoid\b|\bcaution\b|\bwarning\b|\bgotcha\b"
    r"|\bexception\b|\bonly if\b|\bpitfall\b|\bbreaks?\b)",
    re.IGNORECASE,
)
DATE_PAT = re.compile(r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}")


def _read(p: Path):
    try:
        return p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _md5(p: Path):
    try:
        return _filehash.md5_of(p)          # 只差行尾的 skill 應判「完全相同」（#19）
    except OSError:
        return None


def plugin_root():
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    return Path(__file__).resolve().parent.parent


def collect(base: Path):
    """回傳 {名稱: 路徑}，skills 與 commands 各一份。"""
    skills, commands = {}, {}
    sd = base / "skills"
    if sd.is_dir():
        for d in sd.iterdir():
            f = d / "SKILL.md"
            if f.is_file():
                skills[d.name] = f
    cd = base / "commands"
    if cd.is_dir():
        for f in cd.glob("*.md"):
            commands[f.stem] = f
    return skills, commands


def user_skills():
    """使用者層 skill（`~/.claude/skills/`）—— 每個專案都生效，且常是 symlink 指到別的 vault。

    🔴 這層最容易被忽略：實測發現 wiki-ingest／wiki-query 等在此處是 symlink，
    指向第三個 vault。人以為在用本地那份，其實跑的是別人的。
    """
    root = Path.home() / ".claude" / "skills"
    out = {}
    if not root.is_dir():
        return out
    for d in root.iterdir():
        f = d / "SKILL.md"
        if not f.is_file():
            continue
        try:
            real = d.resolve()
        except OSError:
            real = d
        out[d.name] = {
            "file": f,
            "symlink": d.is_symlink(),
            "target": real,
        }
    return out


def vault_only(vlines, plines):
    """vault 版有、plugin 版沒有的行號（1-based）。

    🔴 rescue 的定義是「刪掉就永遠消失」，所以只有這些行算數 —— plugin 版也有的句子，
    刪掉 vault 版之後 plugin 裡還有一份，不會消失。掃整份檔會把 plugin 原文一起列出來
    （實測一份客製 skill：11 行裡有 8 行是 plugin 原文），真正該搬的 3 行反而被埋掉。
    （2026-09-21 驗收 #16）
    """
    keep = set()
    for tag, _i1, _i2, j1, j2 in difflib.SequenceMatcher(None, plines, vlines,
                                                         autojunk=False).get_opcodes():
        if tag in ("insert", "replace"):
            keep.update(range(j1 + 1, j2 + 1))
    return keep


def rescue_lines(lines, only=None):
    """撈出「刪掉就永遠消失」的句子。有日期的排前面 —— 那是真實事件的痕跡。

    only＝限定行號集合（vault_only 的結果）；None 代表整份檔都算（vault 獨有的 skill）。
    """
    hits = []
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if len(s) < 8 or s.startswith("|---"):
            continue
        if only is not None and i not in only:
            continue
        if RESCUE_PAT.search(s):
            hits.append((bool(DATE_PAT.search(s)), i, s))
    hits.sort(key=lambda x: (not x[0], x[1]))
    return hits


def pairs(vault: Path, plug: Path):
    vs, vc = collect(vault)
    ps, pc = collect(plug)
    out = []
    for kind, v, p in (("skill", vs, ps), ("command", vc, pc)):
        for name in sorted(set(v) & set(p)):
            out.append((kind, name, v[name], p[name]))
    return out


def cmd_sources(vault, plug, args):
    """列出每個 skill 名稱的所有來源：在哪、多大、symlink 指向誰。

    🔴 只陳述可驗證的事實，**不判定誰生效**。
    同名時哪一份勝出的規則，兩個 session 查過都只有推論、沒有實測，
    據此刪檔會刪錯。要知道答案得做對照實驗（兩份塞不同可辨識字串再觸發）。

    plugin 的 skill 帶命名空間（`llm-wiki:xxx`），這點是清單上看得到的事實 ——
    它不參與同名爭奪。
    """
    vs, vc = collect(vault)
    us = user_skills()
    ps, _ = collect(plug)

    names = sorted(set(vs) | set(us))
    rows = []
    for n in names:
        srcs = []
        if n in us:
            u = us[n]
            tag = "使用者層"
            if u["symlink"]:
                tgt = str(u["target"])
                inside = str(vault).lower() in tgt.lower()
                tag += f"→{'本 vault' if inside else '⚠️ ' + Path(tgt).parents[1].name}"
            srcs.append((tag, u["file"]))
        if n in vs:
            srcs.append(("專案層", vs[n]))
        if n in ps:
            srcs.append(("plugin(llm-wiki:)", ps[n]))
        if len(srcs) > 1:
            rows.append((n, srcs))

    if not rows:
        print("🟢 每個 skill 名稱都只有一個來源，沒有分岔。")
        return 0

    print(f"Vault：{vault}\n")
    print(f"{len(rows)} 個名稱存在於多個位置。以下只列**事實**（在哪、多大、symlink 指向誰）。\n")
    for n, srcs in rows:
        sizes = {s: (p.stat().st_size if p.exists() else 0) for s, p in srcs}
        spread = max(sizes.values()) - min(sizes.values())
        flag = "🔴" if spread > 2000 else "  "
        print(f"{flag} {n}")
        for s, p in srcs:
            print(f"     {s:<22} {sizes[s]:>7,} bytes   {p}")
        if spread > 2000:
            print(f"     ↳ 三份差 {spread:,} bytes，內容已經分岔")
    print("\n🔴 **同名時哪一份生效，尚未實測 —— 不要據此刪檔。**")
    print("   兩個 session 各自查過，都只有推論：cwd 在 vault 內／在 parent 時，清單內容不一致，")
    print("   且清單本身有篩選（有些確實存在的 skill 兩次都沒列出），不能當載入與否的證據。")
    print("   要知道答案得做對照實驗：兩份同名 skill 各塞不同的可辨識字串，再觸發看回哪一份。")
    print("\nℹ️ 可驗證的事實只有兩件：")
    print("   · plugin skill 帶命名空間（`llm-wiki:xxx`），清單上看得到 —— 它不參與同名爭奪")
    print("   · 上面標 ⚠️ 的 symlink 指向本 vault 以外的地方 —— 改那份會影響到別的 vault")
    return 0


def cmd_overview(vault, plug, args):
    hits = pairs(vault, plug)
    if not hits:
        print("🟢 vault 與 plugin 沒有同名項。")
        print("   （plugin skill 帶命名空間 llm-wiki:xxx，本來就不會被遮蔽）")
        print("   仍建議跑 python adopt.py --sources 檢查使用者層是否有分岔。")
        return 0

    print(f"Vault ：{vault}")
    print(f"Plugin：{plug}\n")
    print(f"找到 {len(hits)} 個同名項。\n")
    print("ℹ️ plugin skill 帶命名空間（`llm-wiki:xxx`），**不會被遮蔽也不會遮蔽別人**。")
    print("   所以這張表是「要不要改用 plugin 版」的決策依據，不是「壞掉了要修」。")
    print("   真正會互相遮蔽的是使用者層與專案層 —— 跑 --sources 看。\n")
    print(f"{'類型':<8} {'名稱':<16} {'狀態':<10} {'需搶救':>6}  說明")
    print("-" * 92)

    total_rescue = 0
    for kind, name, vp, pp in hits:
        vlines, plines = _read(vp), _read(pp)
        same = _md5(vp) == _md5(pp)
        r = [] if same else rescue_lines(vlines, vault_only(vlines, plines))
        total_rescue += len(r)
        if same:
            state, note = "完全相同", "直接刪 vault 版，零風險"
        else:
            d = sum(1 for x in difflib.ndiff(plines, vlines) if x[0] in "+-")
            state = f"差 {d} 行"
            note = "有客製，刪之前要先看" if not r else "🔴 含裁示／踩雷，刪前必須搬走"
        print(f"{kind:<8} {name:<16} {state:<10} {len(r):>6}  {note}")

    print(f"\n逐行差異：python adopt.py --diff <名稱>")
    if total_rescue:
        print(f"🔴 共 {total_rescue} 行疑似裁示／踩雷紀錄 —— 跑 python adopt.py --rescue 全部列出。")
        print("   這類句子通常只存在於那份 skill 裡，wiki 沒有、commit message 也沒有。")
        print("   搬到 vault 的 wiki/ops/rulings.md 之後才可以刪。")
    return 0


def cmd_diff(vault, plug, args):
    for kind, name, vp, pp in pairs(vault, plug):
        if name != args.diff:
            continue
        vlines, plines = _read(vp), _read(pp)
        print(f"--- plugin：{pp}")
        print(f"+++ vault ：{vp}")
        print(f"（+ 是 vault 才有的，- 是 plugin 才有的）\n")
        n = 0
        for ln in difflib.unified_diff(plines, vlines, lineterm="", n=2):
            if ln.startswith(("---", "+++")):
                continue
            print(ln)
            n += 1
        if not n:
            print("（兩份完全相同）")
        return 0
    print(f"🔴 找不到撞名項 `{args.diff}`。先跑 python adopt.py 看清單。")
    return 1


def cmd_rescue(vault, plug, args):
    hits = pairs(vault, plug)
    found = False
    for kind, name, vp, pp in hits:
        if _md5(vp) == _md5(pp):
            continue
        vlines, plines = _read(vp), _read(pp)
        r = rescue_lines(vlines, vault_only(vlines, plines))
        if not r:
            continue
        found = True
        print(f"\n### {kind} {name}　（{vp}）")
        for dated, i, s in r:
            print(f"  {'📅' if dated else '  '} L{i:<4} {s}")
    if not found:
        print("🟢 撞名項裡沒有偵測到裁示／踩雷紀錄。")
        print("   仍建議用 --diff 人眼看過再刪 —— 偵測是關鍵字比對，會漏。")
        return 0
    print("\n🔴 以上每一行在刪除 vault 版 skill 之前，都要先決定去處：")
    print("   · 只對這個 vault 成立 → 搬到 wiki/ops/rulings.md（Why／實例／代價寫全）")
    print("   · 大家都該知道      → 提議合併回 plugin 的對應 skill")
    print("   · 已經過時          → 確認後才丟棄，並在 wiki/log.md 留一筆說明為什麼丟")
    return 0


def main():
    ap = argparse.ArgumentParser(description="既有 vault 改用 plugin 版系統的遷移分析")
    ap.add_argument("--vault", help="vault 路徑（預設從當前目錄往上找）")
    ap.add_argument("--diff", help="顯示某個撞名項的逐行差異")
    ap.add_argument("--rescue", action="store_true", help="只列「刪掉就永遠消失」的內容")
    ap.add_argument("--sources", action="store_true",
                    help="列出每個 skill 名稱的所有來源（使用者層／專案層／plugin），找出分岔")
    args = ap.parse_args()

    vault = Path(args.vault).resolve() if args.vault else find_vault_root(Path.cwd())
    if vault is None:
        print("🔴 找不到 vault（往上找不到含 wiki/ 或 raw/.manifest.json 的目錄）")
        return 1
    plug = plugin_root()

    if args.diff:
        return cmd_diff(vault, plug, args)
    if args.rescue:
        return cmd_rescue(vault, plug, args)
    if args.sources:
        return cmd_sources(vault, plug, args)
    return cmd_overview(vault, plug, args)


if __name__ == "__main__":
    sys.exit(main())
