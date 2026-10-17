#!/usr/bin/env python3
"""agenda —— 日程唯一真相來源 wiki/agenda.md 的讀寫、開場窗口、排程引擎與單向匯出。

為什麼：日期散在 log／hot／README 的散文裡，「哪天要做什麼」沒有地方能回答。
一行一事、靠腳本維護（驗格式／展開重複／順延／歸檔）；外部日曆與甘特圖都是由本檔產出的視圖。
設計與藍圖見 wiki/meta/agenda-system.md。

格式（一行一事；細節用 → 指回出處，不複寫）：
    2026-09-25 14:00-15:30  會議  X1 說明會 @會議室A   #專案A #QMS  → log 2026-09-18
    2026-09-23              交件  月報   每月23日  #行政
    ✅ 2026-09-20           待辦  已完成的事（前綴 ✅ ＝ 完成，--tidy 會歸檔）
    日期 [HH:MM[-HH:MM]] 類型 標題 [專案欄位] [重複規則] [#tag …] [→ 出處]
    重複規則：每月D日／每週一…日／每年MM-DD／每N天（只寫一行，腳本展開下一次，不手抄）
    專案欄位（選填、順序不拘）：工期N天（工作天，行首日期＝最後一天）、
        代號:x、接:a,b（a、b 完成後才開始；接:a+2＝a 完成後隔 2 工作天；接:a~SS+2＝類型 SS／FF／SF＋前置天數）、完成:MM-DD（實際完成日，done 自動寫）、
        原定:MM-DD（基準，move 與順延自動寫）、截止:MM-DD（過了只標紅不推）、進度:60%（✅＝100%）、
        屬:x（掛在代號 x 下；x 成母項，日期由子項推出）
    排程引擎（agenda_cpm.py）：工作天扣國定假日；每次寫入時前項延誤 → 後項自動順延並記變更紀錄；
        硬期限類型（預設 交件／稽核／會議）不推，只在 --check 報會晚幾天

用法（vault 由 CLAUDE_PROJECT_DIR 或目前目錄往上找；找不到時不帶參數＝安靜結束）：
    python agenda.py                       # 開場窗口：逾期／今天／7 天內／期限會延誤
    python agenda.py --days 14 --tag QMS   # 放寬窗口、按 tag 篩
    python agenda.py --check               # 格式、相依、待順延、硬期限延誤（exit 一律 0）
    python agenda.py add "2026-09-25 14:00-15:30 會議 …"   # 驗格式後寫入並排版（無檔則建最小骨架）
    python agenda.py done 關鍵字            # 把符合的未完成行加 ✅＋完成:今天
    python agenda.py undone 關鍵字          # 勾錯了：拿掉符合的已完成行的 ✅ 與 完成:
    python agenda.py move 關鍵字 2026-10-23 # 改期；沒有 原定 就把舊日期記進去；接它的後項一起平移同樣工作天
    python agenda.py dur 關鍵字 5            # 改工期：開始日不動、完成日跟著變；後項同 move 一起平移
    python agenda.py link 後項 前項 [--type SS] [--lag 2] [--id 代號]  # 畫接；前項沒代號用 --id 補
    python agenda.py unlink 後項 代號         # 拆接（日期不動）
    python agenda.py plan                  # 以接串起來的各組：開始／完成／寬裕／要徑★／硬期限延誤
    python agenda.py --fmt                 # 手改後補做順延＋分段排序
    python agenda.py --tidy                # 歸檔到 wiki/agenda-archive.md：專案 tag 整個結案才搬；
                                           # 非專案行照舊（✅ 或 30 天前的非重複事件）
    python agenda.py --ics [out]           # 全量重生 .ics（預設 <vault>/agenda.ics；重複事件展開 365 天）
    python agenda.py --notify              # 同窗口、Telegram 友善的精簡文字（只印，不發送）
    python agenda.py --json                # 全部事件 JSON（Obsidian 甘特圖外掛讀；寫回走上面的指令，關鍵字用 match）
    python agenda.py --json --file x.md    # 改用別的 agenda 檔（示範／測試用；tidy／fmt 不行）
    寫入指令加 --source 名稱 → 操作本身也記進變更紀錄（外掛帶「Obsidian 甘特圖」）

設定（全部選填，raw/.manifest.json 的 config.agenda）：
    changes        變更紀錄路徑（相對 vault；預設 wiki/agenda-changes.md）
    calendar_dir   辦公日曆 CSV 目錄（相對 vault；沒設＝只扣週末）
    hard_types     硬期限類型（預設 ["交件", "稽核", "會議"]）
    project_dirs   有 <tag>.md 就算專案 tag 的目錄（預設 ["wiki/products", "wiki/projects"]）
    first_order    檔案第一次分段時的段落順序（預設 []）
    due_cmd        開場窗口另外併入的到期清單指令（argv 陣列，於 vault 根執行；"python" 換成目前的直譯器；
                   只取 🔴／🟡／⏰ 開頭的行）
    due_label      上面那段的標題（預設＝指令裡 .py 的檔名）

--notify 不發送：由使用者接 OS 排程器＋Bot（例：Windows 工作排程器每天 08:30 跑本指令，stdout 餵 Bot API）。
原則：只用 stdlib、Python 3.9 相容；預設模式唯讀；不動 hot.md；寫 agenda.md 一律持鎖。
"""
import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import agenda_cpm as cpm  # noqa: E402
from _lib.vaultpaths import find_vault_root, load_manifest  # noqa: E402

try:
    import _guard_status  # noqa: E402
except ImportError:
    _guard_status = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ARCHIVE_AFTER_DAYS = 30
ICS_HORIZON_DAYS = 365
WEEKDAY = "一二三四五六日"

# 以下由 configure(vault 根) 設定；測試可直接改
ROOT = AGENDA = CHANGES = ARCHIVE = None
CAL = cpm.Calendar()  # 沒設日曆目錄＝只扣週末
HARD_TYPES = ("交件", "稽核", "會議")
PROJECT_DIRS = ()
FIRST_ORDER = ()
DUE_CMD = None
DUE_LABEL = "外部到期"


def configure(root):
    """依 vault 根與 manifest config.agenda 設定路徑與規則。"""
    global ROOT, AGENDA, CHANGES, ARCHIVE, CAL, HARD_TYPES, PROJECT_DIRS, FIRST_ORDER, DUE_CMD, DUE_LABEL
    ROOT = Path(root).resolve()
    cfg = (load_manifest(ROOT).get("config") or {}).get("agenda") or {}
    AGENDA, ARCHIVE = ROOT / "wiki" / "agenda.md", ROOT / "wiki" / "agenda-archive.md"
    CHANGES = ROOT / cfg.get("changes", "wiki/agenda-changes.md")
    CAL = cpm.Calendar(ROOT / cfg["calendar_dir"] if cfg.get("calendar_dir") else None)
    HARD_TYPES = tuple(cfg.get("hard_types", ("交件", "稽核", "會議")))
    PROJECT_DIRS = tuple(ROOT / d for d in cfg.get("project_dirs", ("wiki/products", "wiki/projects")))
    FIRST_ORDER = tuple(cfg.get("first_order", ()))
    DUE_CMD = cfg.get("due_cmd") or None
    DUE_LABEL = cfg.get("due_label") or next((Path(x).stem for x in DUE_CMD or () if x.endswith(".py")), "外部到期")

LINE = re.compile(
    r"^(?P<done>✅\s+)?"
    r"(?P<date>\d{4}-\d{2}-\d{2})"
    r"(?:\s+(?P<t1>\d{2}:\d{2})(?:-(?P<t2>\d{2}:\d{2}))?)?"
    r"\s+(?P<type>[^\s#→]+)"
    r"\s+(?P<title>.+?)"
    r"(?P<attrs>(?:\s+(?:工期\d+天|代號:[^\s#,]+|接:[^\s#]+|屬:[^\s#,]+|進度:\d{1,3}%"
    r"|(?:完成|原定|截止):(?:\d{4}-)?\d{2}-\d{2}))*)"
    r"(?:\s+(?P<rule>每(?:月\d{1,2}日|週[一二三四五六日]|年\d{2}-\d{2}|\d+天)))?"
    r"(?P<tags>(?:\s+#[^\s#]+)*)"
    r"(?:\s+→\s*(?P<ref>.+?))?\s*$"
)
HEADER_END = "<!-- 事件從下一行開始 -->"
FORMAT_HINT = ("日期 [HH:MM[-HH:MM]] 類型 標題 [工期N天] [代號:x] [接:a,b] [屬:x] [完成:MM-DD] [原定:MM-DD] [截止:MM-DD] "
               "[進度:N%] [每月D日|每週X|每年MM-DD|每N天] [#tag …] [→ 出處]")
MIN_HEADER = (
    "---\ntitle: 日程（agenda）\ntype: meta\nmaintenance: transactional\n---\n\n# 日程\n\n"
    f"> 一行一事，由 agenda.py 讀寫。格式：`{FORMAT_HINT}`；完成的行前綴 `✅`。\n\n{HEADER_END}\n"
)
LAG = re.compile(r"^(.+?)(?:~(FS|SS|FF|SF))?([+-]\d+)?$")  # 接:a~SS+2＝類型＋前置天數；類型省略＝FS


def load():
    if not AGENDA.is_file():
        return [], []
    return parse_text(AGENDA.read_text(encoding="utf-8"))


def parse_text(text):
    lines = text.splitlines()
    events, bad = [], []
    body = False
    for i, l in enumerate(lines, 1):
        if not body:
            body = l.strip() == HEADER_END
            continue
        s = l.strip()
        if not s or s.startswith("#") or s.startswith("<!--") or s.startswith(">"):
            continue
        if not valid(s):
            bad.append((i, s))
            continue
        d = LINE.match(s).groupdict()
        d["d"] = datetime.strptime(d["date"], "%Y-%m-%d").date()
        d["line"] = i
        d["raw"] = l
        d["tags"] = [t.lstrip("#") for t in d["tags"].split()] if d["tags"] else []
        d["done"] = bool(d["done"])
        a = d.pop("attrs").split()
        d["dur"] = next((int(x[2:-1]) for x in a if x.startswith("工期")), None)
        d["id"] = next((x[3:] for x in a if x.startswith("代號:")), None)
        d["links"] = [(m.group(1), m.group(2) or "FS", int(m.group(3) or 0)) for x in a if x.startswith("接:")
                      for y in x[2:].split(",") if y and (m := LAG.match(y))]  # 接:a+2＝a 完成後隔 2 工作天
        d["after"] = [c for c, _, _ in d["links"]]
        d["fin"] = next((near(x[3:], d["d"]) for x in a if x.startswith("完成:")), None)
        d["base"] = next((near(x[3:], d["d"]) for x in a if x.startswith("原定:")), None)
        d["deadline"] = next((near(x[3:], d["d"]) for x in a if x.startswith("截止:")), None)
        d["pct"] = 100 if d["done"] else next((int(x[3:-1]) for x in a if x.startswith("進度:")), 0)
        d["parent"] = next((x[2:] for x in a if x.startswith("屬:")), None)
        events.append(d)
    return events, bad


def near(s, ref):
    """完成／原定的日期：MM-DD 取最接近行首日期的那一年；YYYY-MM-DD 照寫。"""
    if len(s) == 10:
        return datetime.strptime(s, "%Y-%m-%d").date()
    m, d = map(int, s.split("-"))
    return min((date(y, m, d) for y in (ref.year - 1, ref.year, ref.year + 1)), key=lambda x: abs(x - ref))


def short(d, ref):
    return d.strftime("%m-%d") if d.year == ref.year else d.isoformat()


def set_attr(s, key, val):
    """行（已 strip）的 key:val 欄位：有就換、沒有就加在標題後。"""
    m = LINE.match(s)
    toks = [t for t in m.group("attrs").split() if not t.startswith(key + ":")] + [f"{key}:{val}"]
    return s[:m.start("attrs")] + "".join(" " + t for t in toks) + s[m.end("attrs"):]


def reschedule(s, new):
    """改期：沒有 原定 就把舊日期記成 原定（保留最早那次基準），再換行首日期；改回原定那天就拿掉 原定。"""
    m = LINE.match(s)
    old = datetime.strptime(m.group("date"), "%Y-%m-%d").date()
    toks = m.group("attrs").split()
    if f"原定:{short(new, new)}" in toks or f"原定:{new.isoformat()}" in toks:
        s = s[:m.start("attrs")] + "".join(" " + t for t in toks if not t.startswith("原定:")) + s[m.end("attrs"):]
        m = LINE.match(s)
    elif not any(t.startswith("原定:") for t in toks) and new != old:
        s = set_attr(s, "原定", short(old, new))
        m = LINE.match(s)
    return s[:m.start("date")] + new.isoformat() + s[m.end("date"):]


def mark_done(s, today):
    """打勾；沒寫 完成 就補今天（手填的不動）。"""
    m = LINE.match(s)
    if not any(t.startswith("完成:") for t in m.group("attrs").split()):
        s = set_attr(s, "完成", short(today, datetime.strptime(m.group("date"), "%Y-%m-%d").date()))
    return s if s.startswith("✅") else "✅ " + s


def workdays_back(d, n):
    """d 往前數 n 個工作天（一到五，扣國定假日）。"""
    return CAL.add(d, -n)


def start_of(e):
    """有工期的事件：行首日期＝最後一天，開始日往前推（工作天）。"""
    return workdays_back(e["d"], e["dur"] - 1) if e["dur"] else e["d"]


def dep_problems(events):
    """工期／相依的問題：代號重複、代號像前置天數、接到不存在的代號、循環、重複事件不支援相依。
    「前項還沒完成就開始」改由排程引擎自動順延（pending），不在這裡報。"""
    out, ids = [], {}
    for e in events:
        if e["id"]:
            if e["id"] in ids:
                out.append(f"代號重複 {e['id']}：L{ids[e['id']]['line']}、L{e['line']}")
            if re.search(r"[+-]\d+$|~", e["id"]):
                out.append(f"L{e['line']}: 代號:{e['id']} 不可含 ~ 或用 +數字／-數字 結尾（接: 會當成類型／前置天數）")
            ids.setdefault(e["id"], e)
        if e["rule"] and (e["after"] or e["dur"] or e["id"]):
            out.append(f"L{e['line']}: 重複事件不支援工期／代號／接")
    for e in events:
        for a in e["after"]:
            if a not in ids:
                out.append(f"L{e['line']}: 接:{a} 找不到這個代號")
    parents = {e["parent"] for e in events if e["parent"]}
    for e in events:
        if e["parent"] and e["parent"] not in ids:
            out.append(f"L{e['line']}: 屬:{e['parent']} 找不到這個代號")
        if e["rule"] and e["parent"]:
            out.append(f"L{e['line']}: 重複事件不支援 屬")
        if e["id"] in parents and (e["after"] or e["dur"]):  # 母項日期由子項推出；相依寫在子項
            out.append(f"L{e['line']}: 母項 {e['id']} 不寫 接／工期（日期由子項推出，相依請寫在子項）")
    for e in ids.values():  # 屬 循環
        seen, x = [], e
        while x and x["parent"]:
            if x["id"] in seen:
                out.append("屬 循環：" + " → ".join(seen + [x["id"]]))
                break
            seen.append(x["id"])
            x = ids.get(x["parent"])
    state = {}

    def visit(e, path):
        if state.get(e["id"]) == 1:
            out.append("循環：" + " → ".join(path + [e["id"]]))
            return
        if state.get(e["id"]) == 2:
            return
        state[e["id"]] = 1
        for a in e["after"]:
            if a in ids:
                visit(ids[a], path + [e["id"]])
        state[e["id"]] = 2

    for e in ids.values():
        visit(e, [])
    out += [f"L{e['line']}: 有 完成:{e['fin']} 但沒打 ✅" for e in events if e["fin"] and not e["done"]]
    return out


PAREN = re.compile(r"（[^）]*）|\([^)]*\)")


def multi_items(events):
    """一行綁多件（只提示不擋）：括號外的標題用「；」分成 ≥2 段、每段 ≥4 字。"""
    out = []
    for e in events:
        segs = [x.strip() for x in PAREN.sub("", e["title"]).split("；")]
        if not e["done"] and len(segs) >= 2 and all(len(x) >= 4 for x in segs):
            out.append(f"L{e['line']}: 可能一行綁 {len(segs)} 件（；分段）→ 考慮拆行、用 代號／接 串起來")
    return out


def next_occurrences(e, start, end):
    """重複事件在 [start, end] 內的日期；非重複回傳 [原日期]（若在範圍內）。"""
    rule = e["rule"]
    if not rule:
        return [e["d"]] if start <= e["d"] <= end else []
    out, d = [], max(e["d"], start)
    while d <= end:
        ok = False
        if rule.startswith("每月"):
            ok = d.day == int(rule[2:-1])
        elif rule.startswith("每週"):
            ok = WEEKDAY[d.weekday()] == rule[2]
        elif rule.startswith("每年"):
            ok = d.strftime("%m-%d") == rule[2:]
        else:  # 每N天
            ok = (d - e["d"]).days % int(rule[1:-1]) == 0
        if ok:
            out.append(d)
        d += timedelta(days=1)
    return out


def fmt(e, d):
    t = f"{e['t1']}" + (f"-{e['t2']}" if e["t2"] else "") if e["t1"] else ""
    tags = " ".join("#" + x for x in e["tags"])
    return f"{d.strftime('%m-%d')}（{WEEKDAY[d.weekday()]}）{t:<12} {e['type']:<4} {e['title']}  {tags}".rstrip()


def extra_due():
    """config.agenda.due_cmd 的逾期／到期行（原樣，不解析語意）。"""
    if not DUE_CMD:
        return []
    cmd = [sys.executable if x == "python" else x for x in DUE_CMD]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=30, cwd=str(ROOT)).stdout
    except (OSError, subprocess.SubprocessError):
        return [f"（{' '.join(DUE_CMD)} 執行失敗）"]
    return [l.strip() for l in out.splitlines() if l.strip()[:1] in ("🔴", "🟡", "⏰")]


def window(events, days, tag, today):
    end = today + timedelta(days=days)
    overdue, todays, soon = [], [], []
    for e in events:
        if e["done"] or (tag and tag not in e["tags"]):
            continue
        if not e["rule"] and e["d"] < today:
            overdue.append((e, e["d"]))
            continue
        for d in next_occurrences(e, today, end):
            (todays if d == today else soon).append((e, d))
    return (sorted(overdue, key=lambda x: x[1]), sorted(todays, key=lambda x: x[0]["t1"] or ""),
            sorted(soon, key=lambda x: (x[1], x[0]["t1"] or "")))


def report(events, bad, days, tag, today):
    overdue, todays, soon = window(events, days, tag, today)
    print(f"=== agenda {today}（{WEEKDAY[today.weekday()]}） 窗口 {days} 天" + (f" tag:{tag}" if tag else "") + " ===")
    for label, rows in (("🔴 逾期", overdue), ("⏰ 今天", todays), (f"🔵 {days} 天內", soon)):
        if rows:
            print(label)
            for e, d in rows:
                extra = f"（逾 {(today - d).days} 天）" if label.startswith("🔴") else ""
                print(f"   {fmt(e, d)}{extra}")
    rows = plan(events).values()
    late = sorted((r for r in rows if r["late"] and (not tag or tag in r["e"]["tags"])), key=lambda r: r["fin0"])
    dls = [x for x in overdue_deadlines(events, rows) if not tag or tag in x[0]["tags"]]
    if late or dls:
        print("🔴 期限會延誤（日期沒動）")
        for r in late:
            print(f"   {fmt(r['e'], r['fin0'])}（晚 {r['late']} 工作天，卡在 {r['drive']}）")
        for e, f, dl, n in dls:
            print(f"   {fmt(e, dl)}（截止日；預計 {f} 完成，晚 {n} 工作天）")
    ext = extra_due()
    if ext:
        print(f"📎 {DUE_LABEL}")
        for l in ext:
            print(f"   {l}")
    if bad:
        print(f"⚠️ 格式壞行 {len(bad)}（agenda.py --check）")
    n = len(overdue) + len(todays) + len(soon) + len(ext) + len(late) + len(dls)
    if n == 0 and not bad:
        print("（窗口內無事）")
    return n


def check(events, bad):
    print("=== agenda --check ===")
    print(f"input   : {len(events)} 事件（{sum(e['done'] for e in events)} ✅，{sum(bool(e['rule']) for e in events)} 重複）")
    for i, s in bad:
        print(f"   L{i}: 格式不符 → {s[:80]}")
    stale = archivable(events, date.today())
    if stale:
        print(f"   {len(stale)} 行可歸檔（agenda.py --tidy）")
    deps = dep_problems(events)
    for s in deps:
        print(f"   {s}")
    for s in multi_items(events):
        print(f"   ℹ️ {s}")
    rows = plan(events).values()
    pend = [r for r in rows if r["push"]]
    late = [r for r in rows if r["late"]]
    dls = overdue_deadlines(events, rows)
    for r in pend:
        print(f"   L{r['e']['line']}: {r['e']['title'][:30]} 前項 {r['drive']} 延誤，應順延到 {r['push']}（手改未套用 → --fmt）")
    for r in late:
        print(f"   🔴 L{r['e']['line']}: 硬期限 {r['e']['type']} {r['e']['title'][:30]} {r['fin0']} 會晚 {r['late']} 工作天（前項 {r['drive']}）")
    for e, f, dl, n in dls:
        print(f"   🔴 L{e['line']}: {e['title'][:30]} 截止 {dl}，預計 {f} 完成，晚 {n} 工作天")
    for e in events:
        if not e["done"] and e["pct"] == 100:
            print(f"   ℹ️ L{e['line']}: 進度 100% 但沒打 ✅：{e['title'][:30]}（agenda.py done …）")
    for e in events:
        if not e["done"] and not e["rule"] and e["d"] >= date.today() and not CAL.is_work(e["d"]):
            why = CAL.names.get(e["d"]) or ("週末" if e["d"].year in CAL.years else "週末（該年無辦公日曆）")
            print(f"   ℹ️ L{e['line']}: {e['d']} 不是工作天（{why}）：{e['title'][:30]}")
    if AGENDA.is_file() and not bad and fmt_text(t := AGENDA.read_text(encoding="utf-8")) != t:
        print("   ℹ️ 尚未分段排序（有人直接 append 或手改）→ agenda.py --fmt")
    issues = ([f"{len(bad)} 壞行"] * bool(bad) + [f"{len(deps)} 工期／相依問題"] * bool(deps)
              + [f"{len(pend)} 項待順延"] * bool(pend) + [f"{len(late)} 項硬期限會延誤"] * bool(late)
              + [f"{len(dls)} 項會過截止日"] * bool(dls))
    print("verdict : " + ("🟡 " + "、".join(issues) if issues else "🟢 CLEAN"))


def valid(s):
    """格式＋日期／時間真的存在（regex 擋不住 2026-13-99、25:00）。"""
    m = LINE.match(s)
    if not m:
        return False
    try:
        datetime.strptime(m.group("date"), "%Y-%m-%d")
        for t in (m.group("t1"), m.group("t2")):
            if t:
                datetime.strptime(t, "%H:%M")
        for t in m.group("attrs").split():
            if t[:3] in ("完成:", "原定:", "截止:"):
                near(t[3:], date(2000, 1, 1))  # 只驗日期存在（02-30 會丟 ValueError）
            if t.startswith("進度:") and int(t[3:-1]) > 100:
                return False
    except ValueError:
        return False
    return True


def add(text):
    s = text.strip()
    if not valid(s):
        sys.exit(f"格式不符：{s}\n  {FORMAT_HINT}")
    if not AGENDA.is_file():
        AGENDA.parent.mkdir(parents=True, exist_ok=True)
        AGENDA.write_text(MIN_HEADER, encoding="utf-8")
    with agenda_lock(AGENDA):  # 加在檔尾再整檔排版歸位
        if SOURCE:
            e = parse_text(f"{HEADER_END}\n{s}")[0][0]
            log_changes(CHANGES, [(SOURCE, "新增", f"{e['type']}｜{e['title']}", "", str(e["d"]), "")])
        write_fmt(AGENDA.read_text(encoding="utf-8").splitlines() + [s])
    print(f"added   : {s}")


# agenda.md 寫入鎖。協定：O_CREAT|O_EXCL 建
# `agenda.md.lock`（內容 pid＋時間＋誰），寫完刪；鎖檔逾 LOCK_STALE 秒視為持有者已死、可搶；等不到 wait 秒
# 丟 RuntimeError、什麼都不寫。所有寫 agenda.md 的路徑（本檔各寫入指令、外部同步工具）MUST 取這把鎖：
# 併發測試證實沒鎖時「比對內容再 os.replace」仍會吃掉別人 append 的行，且 os.replace 進行中對方 open("a") 會 PermissionError。
LOCK_STALE = 30


@contextlib.contextmanager
def agenda_lock(p, wait=10.0):
    lock = p.with_name(p.name + ".lock")
    deadline = time.monotonic() + wait
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {datetime.now().isoformat(timespec='seconds')} {Path(sys.argv[0]).name}\n".encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > LOCK_STALE:
                    lock.unlink()
                    continue
            except OSError:
                continue
            if time.monotonic() > deadline:
                raise RuntimeError(f"agenda.md 被鎖住超過 {wait:.0f} 秒（{lock.name}），什麼都沒寫")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def edit_one(key, label, change, done=False, chain=None):
    """關鍵字剛好命中 1 個未打勾（done＝True 時：已打勾）的行 → change(行) 後寫回。讀→改→寫都在鎖內。
    chain(lines, i)：改完這行後連帶改別行（move 的後項平移），回傳 changes.md 列。"""
    with agenda_lock(AGENDA):
        lines = AGENDA.read_text(encoding="utf-8").splitlines()
        hit = [i for i, l in enumerate(lines) if key in l and LINE.match(l.strip()) and l.strip().startswith("✅") == done]
        if len(hit) != 1:
            sys.exit(f"命中 {len(hit)} 行（要剛好 1 行）：{[lines[i][:60] for i in hit]}")
        old = lines[hit[0]]
        lines[hit[0]] = change(old.strip())
        rows = source_rows(label, old, lines[hit[0]])
        rows += chain(lines, hit[0], old) if chain else []
        log_changes(CHANGES, rows)  # 操作本身→平移→順延（照發生順序）
        write_fmt(lines)
    print(f"{label:<8}: {lines[hit[0]]}")


SOURCE = None  # --source：操作本身也記進變更紀錄（Obsidian 外掛傳「Obsidian 甘特圖」）


def source_rows(label, old, new):
    act = {"move": "改期", "done": "完成", "undone": "取消完成", "dur": "改工期"}.get(label)
    a, b = (parse_text(f"{HEADER_END}\n{x.strip()}")[0] for x in (old, new))
    if not SOURCE or not act or not a or not b:
        return []
    a, b = a[0], b[0]
    if act == "改工期":
        return [(SOURCE, act, f"{b['type']}｜{b['title']}", f"{a['dur']}天" if a["dur"] else "里程碑", f"{b['dur']}天",
                 f"完成日 {a['d']} → {b['d']}")]
    was, now = {"改期": (a["d"], b["d"]), "完成": ("", b["fin"] or b["d"]), "取消完成": (a["fin"] or "", "")}[act]
    return [(SOURCE, act, f"{b['type']}｜{b['title']}", str(was), str(now), "")]


def done(key):
    edit_one(key, "done", lambda s: mark_done(s, date.today()))


def unmark_done(s):
    """取消打勾：拿掉 ✅ 與 完成:（勾錯時用）。"""
    s = s[1:].lstrip() if s.startswith("✅") else s
    m = LINE.match(s)
    toks = [t for t in m.group("attrs").split() if not t.startswith("完成:")]
    return s[:m.start("attrs")] + "".join(" " + t for t in toks) + s[m.end("attrs"):]


def undone(key):
    edit_one(key, "undone", unmark_done, done=True)


def move(key, new):
    try:
        d = datetime.strptime(new or "", "%Y-%m-%d").date()
    except ValueError:
        sys.exit("用法：agenda.py move 關鍵字 YYYY-MM-DD")
    edit_one(key, "move", lambda s: reschedule(s, d), chain=lambda lines, i, old: shift_after(lines, i, old, d))


def find_one(lines, key, done=None):
    """關鍵字剛好命中 1 行（done＝None 不分是否打勾）→ 行號（0 起）。"""
    hit = [i for i, l in enumerate(lines) if key in l and LINE.match(l.strip())
           and (done is None or l.strip().startswith("✅") == done)]
    if len(hit) != 1:
        sys.exit(f"命中 {len(hit)} 行（要剛好 1 行）：{[lines[i][:60] for i in hit]}")
    return hit[0]


def _one(line):
    return parse_text(f"{HEADER_END}\n{line.strip()}")[0][0]


def _guarded_write(orig, lines, rows):
    """相依改動的共同出口：改完有新的相依問題（循環、代號重複、母項接…）或壞行就不寫。"""
    (ev, bad), (ev0, bad0) = (parse_text("\n".join(x)) for x in (lines, orig))
    new = [x for x in dep_problems(ev) if x not in dep_problems(ev0)] + [s for _, s in bad if (_, s) not in bad0]
    if new:
        sys.exit("改了會出問題，沒寫：" + "；".join(new))
    log_changes(CHANGES, rows)
    write_fmt(lines)


def link(succ_key, pred_key, typ="FS", lag=0, code=None):
    """畫接（外掛連線模式）：後項加 接:前項代號[~類型][±天]；前項沒代號就用 code 補上。"""
    typ = (typ or "FS").upper()
    if typ not in ("FS", "SS", "FF", "SF"):
        sys.exit("--type 只能 FS／SS／FF／SF")
    with agenda_lock(AGENDA):
        lines = AGENDA.read_text(encoding="utf-8").splitlines()
        orig = list(lines)
        i, j = find_one(lines, succ_key, done=False), find_one(lines, pred_key)
        if i == j:
            sys.exit("前項和後項是同一行")
        p, q = _one(lines[j]), _one(lines[i])
        c = p["id"] or (code or "").strip()
        if not c:
            sys.exit("前項沒有代號：請用 --id 給一個")
        if not p["id"]:
            lines[j] = set_attr(lines[j].strip(), "代號", c)
        if c in q["after"]:
            sys.exit(f"已經接了 {c}")
        tok = c + (f"~{typ}" if typ != "FS" else "") + (f"{int(lag):+d}" if int(lag or 0) else "")
        have = [t[2:] for t in LINE.match(lines[i].strip()).group("attrs").split() if t.startswith("接:")]
        lines[i] = set_attr(lines[i].strip(), "接", ",".join(have + [tok]))
        rows = [(SOURCE, "接上", f"{q['type']}｜{q['title']}", "", f"接:{tok}", "")] if SOURCE else []
        _guarded_write(orig, lines, rows)
    print(f"link    : {lines[i].strip()}")


def unlink(succ_key, code):
    """拆接：後項的 接: 拿掉這個代號（其他保留；全拿掉就刪整個 接:）。日期不動。"""
    with agenda_lock(AGENDA):
        lines = AGENDA.read_text(encoding="utf-8").splitlines()
        orig = list(lines)
        i = find_one(lines, succ_key)
        q = _one(lines[i])
        if code not in q["after"]:
            sys.exit(f"這行沒有接 {code}")
        s = lines[i].strip()
        m = LINE.match(s)
        toks = []
        for t in m.group("attrs").split():
            if t.startswith("接:"):
                keep = [y for y in t[2:].split(",") if y and LAG.match(y).group(1) != code]
                if keep:
                    toks.append("接:" + ",".join(keep))
            else:
                toks.append(t)
        lines[i] = s[:m.start("attrs")] + "".join(" " + t for t in toks) + s[m.end("attrs"):]
        rows = [(SOURCE, "拆接", f"{q['type']}｜{q['title']}", f"接:{code}", "", "")] if SOURCE else []
        _guarded_write(orig, lines, rows)
    print(f"unlink  : {lines[i].strip()}")


def set_dur(s, n):
    m = LINE.match(s)
    toks = m.group("attrs").split()
    toks = [f"工期{n}天" if t.startswith("工期") else t for t in toks] if any(t.startswith("工期") for t in toks) \
        else [f"工期{n}天"] + toks
    return s[:m.start("attrs")] + "".join(" " + t for t in toks) + s[m.end("attrs"):]


def resize(key, n):
    """改工期（外掛拉條右端）：開始日不動，完成日（行首日期）跟著變；接的後項一起平移（同 move）。"""
    try:
        n = int(n or "")
    except ValueError:
        n = 0
    if n < 1:
        sys.exit("用法：agenda.py dur 關鍵字 N（工作天，≥1）")
    box = {}

    def change(s):
        e = parse_text(f"{HEADER_END}\n{s}")[0][0]
        if e["rule"]:
            sys.exit("重複事件不支援工期")
        box["d"] = CAL.add(start_of(e), n - 1)
        return reschedule(set_dur(s, n), box["d"])

    edit_one(key, "dur", change, chain=lambda lines, i, old: shift_after(lines, i, old, box["d"], start_moved=False))


def shift_after(lines, i, old, new, start_moved=True):
    """後項一起平移（A 提前／延後 N 天，接 A 的後項也 ±N 工作天，空檔不變）。
    順著接一路往下，每項只動一次；已完成、重複、硬期限（交件／稽核／會議）不動，也不從它往下傳。
    start_moved＝False（dur 改工期，開始日沒動）：只接在 A 開始日（~SS／~SF）的後項不動。
    平移完再由 settle 檢查：後項另有前項擋著時照常順延。"""
    events = {e["line"]: e for e in parse_text("\n".join(lines))[0]}
    me = parse_text(f"{HEADER_END}\n{old.strip()}")[0]
    me = me[0] if me else None
    if not me or not me["id"] or me["rule"] or not (n := CAL.diff(me["d"], new)):
        return []
    rows, seen, todo = [], {i + 1}, [me["id"]]
    while todo:
        code = todo.pop(0)
        for e in events.values():
            if e["rule"] or e["done"] or code not in e["after"] or e["line"] in seen or is_hard(e):
                continue
            if not start_moved and code == me["id"] and all(t in ("SS", "SF") for c, t, _ in e["links"] if c == code):
                continue
            seen.add(e["line"])
            nd = CAL.add(e["d"], n)
            lines[e["line"] - 1] = reschedule(lines[e["line"] - 1].strip(), nd)
            rows.append(("排程引擎", "改期", f"{e['type']}｜{e['title']}", str(e["d"]), str(nd), f"接 {code}，跟著平移"))
            print(f"平移    : {e['title'][:40]} {e['d']} → {nd}（接 {code}）")
            if e["id"]:
                todo.append(e["id"])
    return rows


def to_json(events, bad, today):
    """給畫面程式（Obsidian 甘特圖外掛）讀：只讀不寫。
    寫回一律走 move／done，關鍵字傳 match（整行原文，必唯一命中），不自行解析 agenda.md。"""
    lines = AGENDA.read_text(encoding="utf-8").splitlines() if AGENDA.is_file() else []
    sec, sec_of, sections = None, {}, []
    for i, l in enumerate(lines, 1):
        if l.startswith("## "):
            sec = l[3:].strip()
            sections.append(sec)
        sec_of[i] = sec
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    rows = {r["e"]["line"]: r for r in plan(events).values()}
    out = []
    for e in events:
        nxt = next_occurrences(e, today, today + timedelta(days=400)) if e["rule"] else []
        r = rows.get(e["line"])
        out.append({"line": e["line"], "section": sec_of.get(e["line"]), "match": e["raw"].strip(),
                    "done": e["done"], "date": iso(e["d"]), "start": iso(start_of(e)), "t1": e["t1"], "t2": e["t2"],
                    "type": e["type"], "title": e["title"], "dur": e["dur"], "id": e["id"], "after": e["after"],
                    "fin": iso(e["fin"]), "base": iso(e["base"]), "rule": e["rule"], "next": iso(nxt[0]) if nxt else None,
                    "tags": e["tags"], "ref": e["ref"], "links": [list(x) for x in e["links"]], "hard": is_hard(e),
                    "deadline": iso(e["deadline"]), "pct": e["pct"], "parent": e["parent"],
                    "plan": r and {"es": iso(r["es"]), "ef": iso(r["ef"]), "slack": r["slack"], "critical": r["critical"],
                                   "late": r["late"], "dl_late": r["dl_late"], "summary": r["summary"],
                                   "group": r["group"]}})
    src = AGENDA.relative_to(ROOT).as_posix() if AGENDA.is_relative_to(ROOT) else str(AGENDA)
    cal = {"off": {iso(d): CAL.names[d] for d in sorted(CAL.off)}, "on": {iso(d): CAL.names[d] for d in sorted(CAL.on)},
           "years": sorted(CAL.years)}  # 畫面畫假日灰底用；沒有日曆的年份只扣週末
    print(json.dumps({"generated": datetime.now().isoformat(timespec="seconds"), "source": src, "calendar": cal,
                      "sections": sections, "events": out, "bad": [{"line": i, "text": s} for i, s in bad],
                      "problems": dep_problems(events)}, ensure_ascii=False, indent=1))
    return 0


def project_tags(events):
    """專案 tag：PROJECT_DIRS 有 <tag>.md（產品／專案註冊表），或該 tag 有行用了工期／代號／接。"""
    tags = {t for e in events for t in e["tags"]}
    return {t for t in tags if any((d / f"{t}.md").is_file() for d in PROJECT_DIRS)
            or any(t in e["tags"] and (e["dur"] or e["id"] or e["after"]) for e in events)}


def closed_tags(events, today):
    """結案：專案 tag 沒有未打勾的非重複行，且最後完成日（沒寫用行首日期）已超過 ARCHIVE_AFTER_DAYS。"""
    cut, out = today - timedelta(days=ARCHIVE_AFTER_DAYS), set()
    for t in project_tags(events):
        rows = [e for e in events if t in e["tags"] and not e["rule"]]
        if rows and all(e["done"] for e in rows) and max(e["fin"] or e["d"] for e in rows) < cut:
            out.add(t)
    return out


def archivable(events, today):
    """專案 tag 未結案前，✅ 與逾期行都留著（看得到計畫對實際）；
    整個 tag 結案才一起歸檔。非專案的行照舊：✅ 或超過 ARCHIVE_AFTER_DAYS 的非重複行。"""
    cut = today - timedelta(days=ARCHIVE_AFTER_DAYS)
    proj, closed = project_tags(events), closed_tags(events, today)
    out = []
    for e in events:
        mine = proj & set(e["tags"])
        if mine:
            if mine <= closed and (e["done"] or not e["rule"]):
                out.append(e)
        elif e["done"] or (not e["rule"] and e["d"] < cut):
            out.append(e)
    return out


ROUTINE = "例行與其他"
DONE_HEAD = "### ✅ 已完成"


def fmt_text(text):
    """本體依第一個 #tag 分段（`## 段名`），段內未完成依日期排、
    重複事件置頂；✅ 收進段尾 `### ✅ 已完成`。只搬行、不改字、冪等。
    段落順序沿用檔案現有 `## ` 順序（第一次用 config first_order）；新段插在「例行與其他」前（字母序）；空段刪掉。
    哪些 tag 自成一段：檔案已有該段、專案 tag（project_tags），第一次排版另加 FIRST_ORDER；其餘進「例行與其他」。
    本體有事件行與段標題以外的東西（壞行、註解、引用）→ 原樣不動，交給 --check／--fmt 報。"""
    lines = text.splitlines()
    try:
        cut = next(i for i, l in enumerate(lines) if l.strip() == HEADER_END) + 1
    except StopIteration:
        return text
    order, stray = [], False
    for l in lines[cut:]:
        s = l.strip()
        if s.startswith("## "):
            order.append(s[3:].strip())
        elif s and s != DONE_HEAD and not valid(s):
            stray = True
    if stray:
        return text
    events, _ = parse_text(text)
    named = set(order) | project_tags(events) | (set(FIRST_ORDER) if not order else set())
    if not order:
        order = list(FIRST_ORDER)
    order = [g for g in order if g != ROUTINE]
    secs = {}
    for e in events:
        g = e["tags"][0] if e["tags"] and e["tags"][0] in named else ROUTINE
        secs.setdefault(g, []).append(e)
    order += sorted(g for g in secs if g not in order and g != ROUTINE)
    out = lines[:cut]
    for g in order + [ROUTINE]:
        rows = secs.get(g)
        if not rows:
            continue
        todo = sorted((e for e in rows if not e["done"]), key=lambda e: (not e["rule"], e["d"], e["line"]))
        done = sorted((e for e in rows if e["done"]), key=lambda e: (e["fin"] or e["d"], e["line"]))
        out += ["", f"## {g}"] + [e["raw"] for e in todo]
        if done:
            out += ["", DONE_HEAD] + [e["raw"] for e in done]
    return "\n".join(out) + "\n"


def fmt_file():
    with agenda_lock(AGENDA):
        text = AGENDA.read_text(encoding="utf-8")
        new, pushes = settle(text)
        if new == text:
            bad = parse_text(text)[1]
            print("fmt     : 已排好" if not bad else f"fmt     : 有 {len(bad)} 行不是事件也不是段標題，沒排版 → --check 看是哪幾行")
            return 1 if bad else 0
        write_fmt(text.splitlines())
    print("fmt     : 已順延／分段排序" if pushes else "fmt     : 已分段排序（只搬行不改字）")
    return 0


def is_hard(e):  # 硬期限：引擎不推，只報延誤
    return e["type"] in HARD_TYPES


def plan(events):
    return cpm.schedule(events, CAL, is_hard)


def overdue_deadlines(events, rows=None):
    """截止日會過：[(事件, 預計完成, 截止日, 晚幾工作天)]。預計完成＝引擎算的（有接／屬）或行首日期。"""
    rows = {r["e"]["line"]: r for r in (rows if rows is not None else plan(events).values())}
    out = []
    for e in events:
        if e["deadline"] and not e["done"] and not e["rule"]:
            r = rows.get(e["line"])
            f = r["ef"] if r else e["d"]
            if f > e["deadline"]:
                out.append((e, f, e["deadline"], CAL.diff(e["deadline"], f)))
    return out


def settle(text):
    """寫入前整理（呼叫端已持鎖）：排程引擎順延（前項延誤 → 後項往後推，記原定；硬期限不推）→ 分段排序。
    回傳 (新全文, 順延清單[(事件, 新完成日, 驅動前項)])。"""
    events, _ = parse_text(text)
    lines, pushes = text.splitlines(), []
    for r in plan(events).values():
        if r["push"]:
            i = r["e"]["line"] - 1
            lines[i] = reschedule(lines[i].strip(), r["push"])
            pushes.append((r["e"], r["push"], r["drive"]))
    if pushes:
        text = "\n".join(lines) + "\n"
    return fmt_text(text), pushes


def push_rows(pushes):
    return [("排程引擎", "改期", f"{e['type']}｜{e['title']}", str(e["d"]), str(d),
             "子項日期變動，母項跟著改" if drive == "子項" else f"接 {drive} 延誤，自動順延") for e, d, drive in pushes]


def write_fmt(lines):
    """整檔寫回 agenda.md 前順延＋排版（呼叫端已持鎖），順延記進 changes.md。"""
    text, pushes = settle("\n".join(lines) + "\n")
    AGENDA.write_text(text, encoding="utf-8")
    for e, d, drive in pushes:
        print(f"順延    : {e['title'][:40]} {e['d']} → {d}（{'子項' if drive == '子項' else '接 ' + drive}）")
    log_changes(CHANGES, push_rows(pushes))


CHANGES_HEAD = """# 排程變更紀錄

> 由 `agenda.py` 自動追加，一列一筆，不手改。來源：Obsidian 甘特圖＝使用者在外掛拖拉／打勾／新增／畫接；agenda＝Claude 或指令列帶 --source agenda；排程引擎＝前項延誤自動順延、接的後項跟著平移。
> 原因：看該行 `→` 出處。

| 記錄時間 | 來源 | 動作 | 事項 | 原 | 新 | 差(天) | 原因 |
|---|---|---|---|---|---|---|---|
"""


def _days(a, b):
    try:
        return f"{(date.fromisoformat(b) - date.fromisoformat(a)).days:+d}"
    except ValueError:
        return ""


def log_changes(path, rows):
    if not rows:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    clean = lambda s: str(s).replace("|", "／").replace("\n", " ")  # noqa: E731
    body = "".join(f"|{now}|{src}|{act}|{clean(what)}|{old}|{new}|{_days(old, new) if act == '改期' else ''}|{clean(why)}|\n"
                   for src, act, what, old, new, why in rows)
    if not path.is_file():
        path.write_text(CHANGES_HEAD, encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write(body)
    print(f"logged  : {len(rows)} 筆 → {path.name}")


def notify(events, bad, days, tag, today):
    """Telegram 友善：無對齊、無表頭、每行一事。"""
    overdue, todays, soon = window(events, days, tag, today)

    def row(e, d, with_date):
        head = (f"{d.strftime('%m-%d')} " if with_date else "") + (fmt_time(e) + " " if e["t1"] else "")
        return f"・{head}{e['type']} {e['title']}"

    out = [f"📅 {today.strftime('%m-%d')}（{WEEKDAY[today.weekday()]}）"]
    if overdue:
        out += ["🔴 逾期"] + [row(e, d, True) + f"（逾 {(today - d).days} 天）" for e, d in overdue]
    if todays:
        out += ["⏰ 今天"] + [row(e, d, False) for e, d in todays]
    if soon:
        out += [f"🔵 {days} 天內"] + [row(e, d, True) for e, d in soon]
    if len(out) == 1:
        out.append("（窗口內無事）")
    if bad:
        out.append(f"⚠️ 壞行 {len(bad)}")
    print("\n".join(out))
    return 0


def fmt_time(e):
    return (e["t1"] + (f"-{e['t2']}" if e["t2"] else "")) if e["t1"] else ""


def ics_escape(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_fold(line):
    """RFC 5545 §3.1：每行 ≤75 octets，續行前置一空白；不切斷 UTF-8 多位元組。"""
    out, cur = [], b""
    for ch in line:
        cb = ch.encode("utf-8")
        if len(cur) + len(cb) > (75 if not out else 74):
            out.append(cur)
            cur = b""
        cur += cb
    out.append(cur)
    return b"\r\n ".join(out)


ICS_STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # RFC 5545：DTSTAMP＝產生時間


def vevent(e, d):
    """固定 UID＝md5(日期＋標題)，重匯覆蓋不重複；無時間＝全天（有工期＝開始日到完成日）；無結束＝1 小時。"""
    uid = hashlib.md5(f"{d.isoformat()}{e['title']}".encode("utf-8")).hexdigest() + "@llm-wiki"
    if e["t1"]:
        start = datetime.combine(d, datetime.strptime(e["t1"], "%H:%M").time())
        end = datetime.combine(d, datetime.strptime(e["t2"], "%H:%M").time()) if e["t2"] else start + timedelta(hours=1)
        if end <= start:
            end += timedelta(days=1)
        when = [f"DTSTART:{start:%Y%m%dT%H%M%S}", f"DTEND:{end:%Y%m%dT%H%M%S}"]
    else:
        s0 = start_of(e) if e["dur"] and not e["rule"] else d
        when = [f"DTSTART;VALUE=DATE:{s0:%Y%m%d}", f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}"]
    lines = ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{ICS_STAMP}", *when,
             f"SUMMARY:{ics_escape(e['type'] + ' ' + e['title'])}"]
    if e["tags"]:
        lines.append("CATEGORIES:" + ",".join(ics_escape(t) for t in e["tags"]))
    if e["ref"]:
        lines.append(f"DESCRIPTION:{ics_escape('→ ' + e['ref'])}")
    return lines + ["END:VEVENT"]


def export_ics(events, out, today):
    """全量重生：非重複事件各一筆，重複事件展開至 365 天內每一次；✅ 不輸出。浮動本地時間（無 TZID）。
    DTSTAMP 為產生時間，故重跑不 byte-identical，UID 才是去重鍵。"""
    end = today + timedelta(days=ICS_HORIZON_DAYS)
    body, n = [], 0
    for e in events:
        if e["done"]:
            continue
        for d in (next_occurrences(e, today, end) if e["rule"] else [e["d"]]):
            body += vevent(e, d)
            n += 1
    cal = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//llm-wiki//agenda//ZH", "CALSCALE:GREGORIAN",
           "X-WR-CALNAME:agenda", *body, "END:VCALENDAR"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"\r\n".join(ics_fold(l) for l in cal) + b"\r\n")
    print(f"ics     : {n} VEVENT → {out}")
    return 0


def show_plan(events):
    """各組（以接連起來）的排程：開始／完成／寬裕／要徑★／待順延／硬期限延誤。只讀。"""
    rows = plan(events)
    if not rows:
        print("plan    : 沒有用 代號／接 連起來的事項")
        return 0
    groups = {}
    for r in rows.values():
        groups.setdefault(r["group"], []).append(r)
    for g, rs in sorted(groups.items(), key=lambda kv: min(r["es"] for r in kv[1])):
        print(f"=== 第 {g} 組（{min(r['es'] for r in rs)} ～ {max(r['ef'] for r in rs)}）===")
        for r in sorted(rs, key=lambda r: (r["es"], r["ef"])):
            e = r["e"]
            flag = "✅" if e["done"] else ("★" if r["critical"] else " ")
            note = ((f"  → 應改到 {r['push']}" if r["push"] else "") + (f"  🔴 硬期限會晚 {r['late']} 工作天" if r["late"] else "")
                    + (f"  🔴 過截止 {e['deadline']} {r['dl_late']} 工作天" if r["dl_late"] else ""))
            box = "▣ " if r["summary"] else ("  " if e["parent"] else "")
            print(f" {flag} {r['es']}～{r['ef']}  寬裕 {r['slack']:>3}  {e['id'] or '':<8} {box}{e['type']} {e['title'][:36]}{note}")
    print("★＝要徑（寬裕 ≤ 0）；▣＝母項（日期由子項推出）；寬裕單位＝工作天（扣國定假日）")
    return 0


def tidy():
    with agenda_lock(AGENDA):  # 讀（load）→ 整檔寫都在鎖內
        move = archivable(load()[0], date.today())
        if not move:
            print("tidy    : 無可歸檔行")
            return
        lines = AGENDA.read_text(encoding="utf-8").splitlines()
        idx = {e["line"] - 1 for e in move}
        write_fmt([l for i, l in enumerate(lines) if i not in idx])
        head = "" if ARCHIVE.is_file() else "# agenda 歸檔（由 agenda.py --tidy 搬入，原行不改）\n\n"
        with ARCHIVE.open("a", encoding="utf-8") as f:
            f.write(head + "\n".join(e["raw"].strip() for e in sorted(move, key=lambda e: e["d"])) + "\n")
    print(f"tidy    : 歸檔 {len(move)} 行 → {ARCHIVE.name}")


def main():
    ap = argparse.ArgumentParser(description=FORMAT_HINT)
    ap.add_argument("cmd", nargs="?", choices=["add", "done", "undone", "move", "dur", "link", "unlink", "plan"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("new", nargs="?", help="move 的新日期 YYYY-MM-DD")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--tag")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--tidy", action="store_true")
    ap.add_argument("--fmt", action="store_true", help="分段排序（方案 A）；add／done／move／tidy 寫入時也會自動做")
    ap.add_argument("--json", action="store_true", help="全部事件輸出 JSON（畫面程式用，只讀）")
    ap.add_argument("--ics", nargs="?", const="", metavar="OUT", help="全量重生 .ics（預設 <vault>/agenda.ics）")
    ap.add_argument("--notify", action="store_true", help="Telegram 友善的精簡窗口（只印）")
    ap.add_argument("--file", help="改用別的 agenda 檔（示範／測試用；--json／--check 與各寫入指令（tidy／fmt 除外）；變更紀錄寫它旁邊的 changes.md）")
    ap.add_argument("--type", default="FS", help="link 的連結類型 FS／SS／FF／SF")
    ap.add_argument("--lag", type=int, default=0, help="link 的前置天數（工作天，負＝重疊）")
    ap.add_argument("--id", help="link：前項沒代號時補上這個")
    ap.add_argument("--source", help="add／done／undone／move／dur／link／unlink 的操作本身也記進 changes.md，來源欄填這個（例：Obsidian 甘特圖）")
    a = ap.parse_args()
    global SOURCE
    SOURCE = a.source
    root = find_vault_root(Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
    explicit = (a.cmd or a.check or a.tidy or a.fmt or a.json or a.notify or a.ics is not None
                or a.days != ap.get_default("days") or a.tag)
    if root is None and not a.file:
        if explicit:
            print("🔴 找不到 vault（往上找不到含 wiki/ 或 raw/.manifest.json 的目錄）")
            return 1
        return 0  # SessionStart：非 vault 目錄保持安靜
    configure(root or Path(a.file).resolve().parent)
    if a.file:
        global AGENDA, CHANGES
        if a.tidy or a.fmt or not (a.json or a.check or a.cmd):
            ap.error("--file 只限 --json／--check 與 add／done／undone／move／dur／link／unlink／plan")
        AGENDA = Path(a.file).resolve()
        CHANGES = AGENDA.parent / "changes.md"
    if not AGENDA.is_file() and a.cmd not in ("add", None):
        print(f"🔴 沒有 {AGENDA}（先 agenda.py add 一行會自動建立）")
        return 1

    if a.cmd == "add":
        return add(a.arg or "")
    if a.cmd == "link":
        return link(a.arg or "", a.new or "", a.type, a.lag, a.id)
    if a.cmd == "unlink":
        return unlink(a.arg or "", a.new or "")
    if a.cmd == "done":
        return done(a.arg or "")
    if a.cmd == "undone":
        return undone(a.arg or "")
    if a.cmd == "move":
        return move(a.arg or "", a.new)
    if a.cmd == "dur":
        return resize(a.arg or "", a.new)
    events, bad = load()
    if a.cmd == "plan":
        return show_plan(events)
    if a.json:
        return to_json(events, bad, date.today())
    if a.check:
        if not AGENDA.is_file():
            print(f"=== agenda --check ===\n   無 {AGENDA.name}（agenda.py add 會自動建立）\nverdict : 🟢 CLEAN")
            return 0
        return check(events, bad)
    if a.ics is not None:
        return export_ics(events, Path(a.ics) if a.ics else ROOT / "agenda.ics", date.today())
    if a.notify:
        return notify(events, bad, a.days, a.tag, date.today())
    if not AGENDA.is_file():
        return 0  # vault 尚未啟用日程：開場安靜
    if a.tidy:
        return tidy()
    if a.fmt:
        return fmt_file()
    n = report(events, bad, a.days, a.tag, date.today())
    # 只有未過濾的執行才落盤：`--days 14 --tag QMS` 是人工查詢，寫進 _guard-status 會污染 trend
    if _guard_status is not None and not a.tag and a.days == ap.get_default("days"):
        try:
            _guard_status.record("agenda", f"{n} 項" if n else "CLEAN", 0)
        except Exception:  # 守門留痕失敗不影響窗口
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
