#!/usr/bin/env python3
"""agenda-gantt —— wiki/agenda.md ↔ ProjectLibre（MS Project XML）雙向同步（2026-10-16）

為什麼：agenda.md 一行一事，AI 好讀，人看吃力。使用者用 ProjectLibre 看圖、拖曳調整；
真相來源仍是 agenda.md —— XML 是視圖，每次同步後重新產生。兩端的每筆變動都記進 changes.md。

用法（vault 根目錄執行；說明與資料在 raw/manager/schedule/_README.md）：
    python scripts/agenda-gantt.py check            # 兩端是否同步（🟢／🟡），只讀
    python scripts/agenda-gantt.py sync --dry-run   # 列出兩端變動，不寫
    python scripts/agenda-gantt.py sync [--open]    # ProjectLibre 改動寫回 agenda.md → 記 changes.md → 重新產生 XML
    python scripts/agenda-gantt.py open             # 桌面捷徑：sync＋以 UTC 時區開 ProjectLibre（已開著就不重開）
    python scripts/agenda-gantt.py export [--open]  # 只重新產生 XML（ProjectLibre 有未同步改動時拒絕，--force 才丟棄；視窗開著也拒絕）
    pythonw scripts/agenda-gantt.py watch           # 常駐自動感測（使用者 2026-10-16 要求）：
                                                    #   ProjectLibre 存檔 → 自動寫回；agenda.md 有新變動 → 視窗關著就重產、開著就通知

XML 格式：寫出照官方 MSPDI XSD 順序並自驗（agenda_xml.py），不合就不寫；讀 ProjectLibre 存檔則寬鬆。

對應規則：
- 每個事件＝里程碑，依第一個 #tag 分組；重複事件展開 今天-7～今天+--days 的各次（只顯示，不寫回）
- 備註＝全文＋`agenda:<代碼>`（代碼＝「類型｜標題」雜湊，改日期不變）；使用者在備註另加的文字＝改動原因
- export 時存快照（agenda-gantt.snapshot.json）：用來判斷「ProjectLibre 端改了什麼」與「agenda 端改了什麼」
- 寫回：Finish 日期 → 行首日期；完成度 100% → 加 ✅；新任務（名稱「類型｜標題」）→ 加一行
- 衝突（同一件事兩端都改了日期）→ 整次 sync 中止、不寫任何東西，交使用者決定
- 刪除不寫回（ProjectLibre 裡刪掉的任務只列出）
"""
import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path

if sys.stdout is None:  # pythonw（開機常駐）沒有 console；agenda.py 匯入時會 reconfigure stdout
    sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")
import agenda  # noqa: E402
import agenda_xml as X  # noqa: E402

WATCH_PORT = 47561  # watch 單一實例鎖

NS = X.NS
DATA = agenda.ROOT / "raw" / "manager" / "schedule"  # 資料層：XML／快照／changes.md
DEFAULT_XML = DATA / "agenda-gantt.xml"
PL_EXE = Path(r"C:\Program Files\ProjectLibre\ProjectLibre.exe")
# ProjectLibre 1.9.8 在 UTC+8 讀日曆例外（國定假日）全部早一天；JVM 改 UTC 就正確，XML 不用改
# （2026-10-16 對答案：本機時區 2 項不一致，UTC 9/9 一致）。只影響這個程序，不動安裝檔與系統設定。
PL_ENV = {**os.environ, "JAVA_TOOL_OPTIONS": "-Duser.timezone=UTC"}
SEP = "｜"
NOTE_KEY = re.compile(r"agenda:([0-9a-f]{10}(?:~\d+)?)(?:@(\S+))?")
log_changes = agenda.log_changes  # changes.md 只有一份寫法（排程引擎順延也寫），在 agenda.py


def assign_keys(events):
    """任務代碼＝「類型｜標題」雜湊：改日期、加 ✅ 都不變，ProjectLibre 同一個視窗連存多次也對得回。同名第 n 行加 ~n。"""
    seen, out = {}, {}
    for e in events:
        h = hashlib.sha1(full_name(e).encode("utf-8")).hexdigest()[:10]
        n = seen[h] = seen.get(h, 0) + 1
        out[id(e)] = h if n == 1 else f"{h}~{n}"
    return out


def group_of(e):
    return e["tags"][0] if e["tags"] else "其他"


def full_name(e):
    return f"{e['type']}{SEP}{e['title']}"


SHORT_MAX = 28
CUT = re.compile(r"[；：（(]")


def short_name(e):
    """甘特圖顯示用短名（使用者 2026-10-16：欄位太長要拉）：去掉與分組重複的產品名；仍超過 SHORT_MAX 才切在第一個；：（，再截斷。全文放備註。"""
    t = e["title"]
    g = group_of(e)
    if t.startswith(g + " "):
        t = t[len(g) + 1:]
    m = CUT.search(t, 4) if len(t) > SHORT_MAX else None
    if m:
        t = t[:m.start()]
    t = t.strip()
    if len(t) > SHORT_MAX:
        t = t[:SHORT_MAX] + "…"
    return f"{e['type']}{SEP}{t}"


def snapshot_path(xml):
    return xml.with_name(xml.stem + ".snapshot.json")


def load_snapshot(xml):
    p = snapshot_path(xml)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def save_snapshot(xml, rows):
    snapshot_path(xml).write_text(json.dumps({"exported": datetime.now().isoformat(timespec="seconds"), "rows": rows},
                                             ensure_ascii=False, indent=1), encoding="utf-8")


def shown(e):
    """甘特圖上的日期：已完成且有 完成: → 實際完成日；否則行首日期。快照與兩端比對都用它。"""
    return e["fin"] if e["done"] and e["fin"] else e["d"]


def snap_row(e, d=None):
    return {"k": full_name(e), "title": e["title"], "d": str(d or shown(e)), "done": e["done"], "rule": bool(e["rule"])}


BASE_NOTE = re.compile(r"^原定 \S+，(延|提前) \d+ 天$")


def base_note(e, d):
    n = (d - e["base"]).days
    return f"原定 {agenda.short(e['base'], d)}，{'延' if n >= 0 else '提前'} {abs(n)} 天"


def tmp_saves(path):
    return list(path.parent.glob(f"{path.stem}_tmp*{path.suffix}"))


def latest(path):
    """ProjectLibre 1.9.8 存 XML 會寫 <名>_tmp0.xml、刪原檔，卻不改回原名（2026-10-16 兩次實測）→ 取最新的。"""
    cands = [p for p in [path, *tmp_saves(path)] if p.is_file()]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


# ---------- export ----------

def sub(parent, tag, text=None):
    el = ET.SubElement(parent, f"{{{NS}}}{tag}")
    if text is not None:
        el.text = str(text)
    return el


def dt(d, hm="08:00:00"):
    return f"{d.isoformat()}T{hm}"


def work_hours(wd):
    wts = sub(wd, "WorkingTimes")
    for f, t in (("08:00:00", "12:00:00"), ("13:00:00", "17:00:00")):
        wt = sub(wts, "WorkingTime")
        sub(wt, "FromTime", f)
        sub(wt, "ToTime", t)


LINK_TYPE = {"FF": 0, "FS": 1, "SF": 2, "SS": 3}  # MSPDI PredecessorLink/Type


def export(out, days, open_it):
    events, bad = agenda.load()
    today = date.today()
    rows, snap = [], {}  # rows: (group, start, finish, name, done, note, 工期, event)
    kmap = assign_keys(events)
    preds = {a for e in events if not e["rule"] for a in e["after"]}
    plan = {r["e"]["line"]: r for r in agenda.plan(events).values()}
    ids = {e["id"]: e for e in reversed(events) if e["id"] and not e["rule"]}
    parents = {e["parent"] for e in events if e["parent"] in ids and not e["rule"]}

    def top(e):  # 屬 的最上層母項（分組依它的 #tag）；循環由 agenda.py --check 報
        seen = set()
        while e["parent"] in ids and e["id"] not in seen:
            seen.add(e["id"])
            e = ids[e["parent"]]
        return e
    for e in events:
        occ = (agenda.next_occurrences(e, today - timedelta(days=7), today + timedelta(days=days))
               if e["rule"] else [shown(e)])
        # 被接的里程碑當 1 天：完成＝當天下班，後項才會從下一個工作天開始
        dur = 0 if e["rule"] else e["dur"] or (1 if e["id"] in preds else 0)
        summ = e["id"] in parents and e["line"] in plan
        if summ:  # 母項＝摘要任務：跨距由子項推出（ProjectLibre 也會自己重算）
            r = plan[e["line"]]
            occ, dur = [r["ef"]], agenda.CAL.diff(r["es"], r["ef"]) + 1
        for d in occ:
            nk = f"{kmap[id(e)]}@{d}" if e["rule"] else kmap[id(e)]
            start = agenda.workdays_back(d, dur - 1) if dur else d
            note = "\n".join([e["title"]] + ([base_note(e, d)] if e["base"] and not e["rule"] else []) + [f"agenda:{nk}"])
            rows.append((group_of(top(e)), start, d, short_name(e), e["done"], note, dur, e))
            snap[nk] = snap_row(e, d)
    groups = {}
    for r in sorted(rows, key=lambda r: (r[1], r[2], r[3])):
        groups.setdefault(r[0], []).append(r)

    ET.register_namespace("", NS)
    p = ET.Element(f"{{{NS}}}Project")
    sub(p, "SaveVersion", 12)
    sub(p, "Name", out.name)
    sub(p, "Title", "日程（agenda.md 視圖）")
    sub(p, "LastSaved", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    sub(p, "ScheduleFromStart", 1)
    sub(p, "StartDate", dt(min(r[1] for r in rows)))
    sub(p, "CurrencyCode", "TWD")  # XSD 必填
    sub(p, "CalendarUID", 1)
    sub(p, "DefaultStartTime", "08:00:00")
    sub(p, "DefaultFinishTime", "17:00:00")
    sub(p, "MinutesPerDay", 480)
    sub(p, "MinutesPerWeek", 2400)
    sub(p, "DaysPerMonth", 20)
    eas = sub(p, "ExtendedAttributes")  # 自訂欄位定義（類型／標籤／出處／重複規則／代號），別的程式靠別名認
    for fid, fname, alias in X.FIELDS.values():
        ea = sub(eas, "ExtendedAttribute")
        sub(ea, "FieldID", fid)
        sub(ea, "FieldName", fname)
        sub(ea, "Alias", alias)
    cal = sub(sub(p, "Calendars"), "Calendar")
    sub(cal, "UID", 1)
    sub(cal, "Name", "Standard")
    sub(cal, "IsBaseCalendar", 1)
    wds = sub(cal, "WeekDays")
    for dtype in range(1, 8):  # 1＝週日
        wd = sub(wds, "WeekDay")
        sub(wd, "DayType", dtype)
        working = dtype not in (1, 7)
        sub(wd, "DayWorking", int(working))
        if working:
            work_hours(wd)
    # 國定假日／補班＝例外日（MSPDI 舊式 DayType 0，各版讀取端都認）；與 agenda.py 排程引擎同一份辦公日曆
    for d in sorted(agenda.CAL.off | agenda.CAL.on):
        wd = sub(wds, "WeekDay")
        sub(wd, "DayType", 0)
        sub(wd, "DayWorking", int(d in agenda.CAL.on))
        tp = sub(wd, "TimePeriod")
        sub(tp, "FromDate", dt(d, "00:00:00"))
        sub(tp, "ToDate", dt(d, "23:59:00"))
        if d in agenda.CAL.on:
            work_hours(wd)

    tasks = sub(p, "Tasks")
    uid, uid_of, linked = 0, {}, []
    for gi, (g, rs) in enumerate(sorted(groups.items(), key=lambda kv: kv[1][0][1]), 1):
        uid += 1
        t = sub(tasks, "Task")
        for k, v in (("UID", uid), ("ID", uid), ("Name", f"#{g}"), ("OutlineNumber", gi), ("OutlineLevel", 1),
                     ("Start", dt(min(r[1] for r in rs))), ("Finish", dt(max(r[2] for r in rs), "17:00:00")),
                     ("Summary", 1)):
            sub(t, k, v)
        kids_of, roots = {}, []  # 屬：子項排在母項正下方，大綱層級往下一層
        for r in rs:
            par = r[7]["parent"]
            (kids_of.setdefault(par, []) if par in parents and not r[7]["rule"] else roots).append(r)
        tree, stack = [], [(r, f"{gi}.{i}", 2) for i, r in reversed(list(enumerate(roots, 1)))]
        while stack:
            r, num, lvl = stack.pop()
            tree.append((r, num, lvl))
            stack += [(k, f"{num}.{i}", lvl + 1) for i, k in reversed(list(enumerate(kids_of.get(r[7]["id"], []), 1)))
                      if r[7]["id"] in parents and not r[7]["rule"]]
        for (_, s, d, name, done, note, dur, e), num, lvl in tree:
            uid += 1
            t = sub(tasks, "Task")
            if e["id"] and not e["rule"]:
                uid_of[e["id"]] = uid
            summ = e["id"] in parents and not e["rule"]
            span = ((dt(s), dt(d, "17:00:00"), f"PT{8 * dur}H0M0S", 0) if dur else (dt(d), dt(d), "PT0H0M0S", 1))
            # 有接前項 → Start No Earlier Than：前項延期時排程引擎會把它往後推；其餘 Must Start On，不讓引擎挪日期
            ctype = 4 if e["after"] and not e["rule"] else 2
            if agenda.is_hard(e) and not e["rule"]:  # 硬期限＝Must Finish On：前項延誤也不推，甘特圖顯示負寬裕
                ctype = 3
            if summ:  # 摘要任務不設約束（ASAP），日期由子項決定
                ctype = 0
            for k, v in (("UID", uid), ("ID", uid), ("Name", name), ("OutlineNumber", num),
                         ("OutlineLevel", lvl), ("Start", span[0]), ("Finish", span[1]), ("Summary", int(summ)),
                         ("Duration", span[2]), ("DurationFormat", 7), ("Milestone", 0 if summ else span[3]),  # 7＝天
                         ("ConstraintType", ctype), ("PercentComplete", e["pct"]), ("Notes", note)):
                sub(t, k, v)
            if ctype:
                sub(t, "ConstraintDate", span[1] if ctype == 3 else span[0])
            if e["deadline"] and not e["rule"]:  # 截止日（MS Project Deadline）：只標記不推
                sub(t, "Deadline", dt(e["deadline"], "17:00:00"))
            vals = {"type": e["type"], "tags": " ".join(e["tags"]), "ref": e["ref"], "rule": e["rule"],
                    "id": None if e["rule"] else e["id"]}
            for key, (fid, _, _) in X.FIELDS.items():
                if vals[key]:
                    ea = sub(t, "ExtendedAttribute")
                    sub(ea, "FieldID", fid)
                    sub(ea, "Value", vals[key])
            if e["base"] and not e["rule"]:  # 原定＝基準線（ProjectLibre 追蹤甘特圖顯示）
                bs = agenda.workdays_back(e["base"], dur - 1) if dur else e["base"]
                bl = sub(t, "Baseline")
                for k, v in (("Number", 0), ("Start", dt(bs)), ("Finish", dt(e["base"], "17:00:00" if dur else "08:00:00")),
                             ("Duration", span[2])):
                    sub(bl, k, v)
            if e["after"] and not e["rule"]:
                linked.append((t, e))
    for t, e in linked:
        for a, typ, lag in e["links"]:
            if a in uid_of:  # 接錯的代號由 agenda.py --check 報，這裡略過
                lk = sub(t, "PredecessorLink")
                # LinkLag 單位＝0.1 分鐘：1 工作天＝480 分＝4800；LagFormat 7＝天
                for k, v in (("PredecessorUID", uid_of[a]), ("Type", LINK_TYPE[typ]), ("CrossProject", 0),
                             ("LinkLag", lag * 4800), ("LagFormat", 7)):
                    sub(lk, k, v)
    for t in tasks:  # 照 XSD sequence 排（MS Project 等嚴格讀取端會擋順序錯的檔）
        X.sort_children(t, X.TASK_ORDER)
    X.sort_children(p, X.PROJECT_ORDER)
    data = ET.tostring(p, encoding="utf-8", xml_declaration=True)
    errs = X.validate(data)
    if errs:
        raise RuntimeError("匯出的 XML 不合 MSPDI XSD，未寫入：" + "；".join(errs[:3]))

    out.parent.mkdir(parents=True, exist_ok=True)
    for stale in tmp_saves(out):  # 上一輪 ProjectLibre 存檔殘留；新視圖已取代它
        try:
            stale.unlink()
        except PermissionError:  # 舊 ProjectLibre 視窗還鎖著它（也是它改不回原名的原因）；比新 XML 舊，不會被讀
            print(f"note    : {stale.name} 被開著的 ProjectLibre 鎖住，關掉舊視窗後下次 sync 會清")
    out.write_bytes(data)
    save_snapshot(out, snap)
    print(f"export  : {len(events)} 事件 → {len(rows)} 項，{len(groups)} 組（{'、'.join(groups)}）；"
          + ("XSD ✅" if errs == [] else "XSD 未驗（沒裝 lxml）"))
    if bad:
        print(f"⚠️ agenda 壞行 {len(bad)} 未匯出（python scripts/agenda.py --check）")
    print(f"out     : {out}")
    if open_it:
        subprocess.Popen([str(PL_EXE), str(out)], env=PL_ENV)
        print("open    : ProjectLibre 已開新視窗 —— 舊的日程視窗請關掉不存（內容已過期）")


# ---------- 讀 ProjectLibre 存檔 ----------

def read_xml(path):
    root = ET.parse(path).getroot()
    ns = root.tag[1:].split("}")[0] if root.tag.startswith("{") else ""
    q = (lambda t: f"{{{ns}}}{t}") if ns else (lambda t: t)
    out, group = [], None
    for t in root.iter(q("Task")):
        get = lambda k: (t.findtext(q(k)) or "").strip()  # noqa: E731
        name = get("Name")
        if not name or get("UID") == "0":
            continue
        if get("Summary").lower() in ("1", "true"):  # 讀入寬鬆：布林 1／true、百分比 100／100.0 都認
            if get("OutlineLevel") in ("", "1"):  # 第一層摘要＝#tag 分組
                group = name.lstrip("#")
            continue  # 更深的摘要＝屬 的母項：日期由子項推出，不寫回（子項寫回後 agenda.py 會重算）
        fin = get("Finish") or get("Start")
        nested = get("OutlineLevel") not in ("", "1")  # 第一層的任務不屬於任何 #tag 組
        try:
            pct = float(get("PercentComplete") or 0)
        except ValueError:
            pct = 0
        out.append({"name": name, "note": get("Notes"), "group": group if nested else None,
                    "d": date.fromisoformat(fin[:10]) if fin else None,
                    "done": pct >= 100})
    return out


def reason_of(note, title):
    """備註裡全文、原定行與 agenda: 代碼以外的文字＝使用者寫的原因。"""
    extra = [l.strip() for l in note.splitlines()
             if l.strip() and l.strip() != title and not NOTE_KEY.match(l.strip()) and not BASE_NOTE.match(l.strip())]
    return re.sub(r"^原因[:：]\s*", "", "；".join(extra))


# ---------- 比對 ----------

def pl_changes(tasks, snap, events):
    """ProjectLibre 端的改動：任務與 export 當時（快照）不同的才算；沒快照就跟現在的 agenda 比。"""
    kmap = assign_keys(events)
    by_key = {kmap[id(e)]: e for e in events}
    by_k, by_name = {}, {}
    for e in events:
        by_k.setdefault(full_name(e), []).append(e)
        for n in {full_name(e), short_name(e)}:
            by_name.setdefault(n, []).append(e)
    rows = (snap or {}).get("rows", {})
    out = {"move": [], "done": [], "add": [], "skip": [], "conflict": []}

    for t in tasks:
        m = NOTE_KEY.search(t["note"])
        if m:
            base, occ = m.group(1), m.group(2)
            exp = rows.get(f"{base}@{occ}" if occ else base)
            cur = by_key.get(base)
            if cur is None and exp:  # 舊版代碼（行雜湊）→ 用「類型｜標題」找
                cands = by_k.get(exp["k"], [])
                cur = cands[0] if len(cands) == 1 else None
            ref = exp or (cur and {"d": occ or str(shown(cur)), "done": cur["done"], "k": full_name(cur), "title": cur["title"]})
            if ref is None:
                out["conflict"].append(f"無快照且對不到 agenda 的行，無法判斷：{t['name']}")
                continue
            moved = t["d"] is not None and str(t["d"]) != ref["d"]
            done = t["done"] and not ref["done"]
            if not (moved or done):
                continue  # 使用者沒動這筆；agenda 端若有改，以 agenda 為準
            if occ:
                out["skip"].append(f"重複事件不寫回單次改期（要改規則請直接改 agenda.md）：{t['name']} {occ}→{t['d']}")
                continue
            e = cur
            if e is None:
                out["conflict"].append(f"agenda 該行在 export 後被刪除或改了標題：{ref['k']}（ProjectLibre 改成 {t['d']}）")
                continue
            if moved and e["done"]:
                out["skip"].append(f"已完成的事不寫回改期（實際完成日請改 agenda 的 完成:）：{t['name']} →{t['d']}")
                moved = False
                if not done:
                    continue
            if moved and shown(e) != t["d"] and str(shown(e)) != ref["d"]:
                out["conflict"].append(f"兩端都改了日期：{ref['k']}（export 時 {ref['d']}，ProjectLibre 改成 {t['d']}，agenda 現在 {shown(e)}）")
                continue
            why = reason_of(t["note"], ref["title"])
        else:
            cands = by_name.get(t["name"], [])
            if len(cands) > 1:
                out["skip"].append(f"備註遺失且同名 {len(cands)} 行，無法對回：{t['name']}")
                continue
            if not cands:
                if SEP in t["name"] and t["d"]:
                    typ, title = (s.strip() for s in t["name"].split(SEP, 1))
                    tag = f" #{t['group']}" if t["group"] and t["group"] != "其他" else ""
                    out["add"].append((f"{t['d']} {typ} {title}{tag} → ProjectLibre {date.today()}", t["note"].strip()))
                else:
                    out["skip"].append(f"新任務名稱不是「類型{SEP}標題」，不知道怎麼寫回：{t['name']}")
                continue
            e, why = cands[0], t["note"].strip()
            moved = t["d"] is not None and t["d"] != shown(e) and not e["done"]
            done = t["done"] and not e["done"]
        if moved and t["d"] != shown(e):
            out["move"].append((e, t["d"], why))
        if done and not e["done"]:
            out["done"].append((e, why))
    return out


def agenda_changes(snap, events):
    """agenda 端在 export 後的改動（Claude／其他 session 直接改 agenda.md）。依「類型｜標題」對；重複事件不比。"""
    if not snap:
        return None
    old, new = {}, {}
    for r in snap["rows"].values():
        if not r["rule"]:
            old.setdefault(r["k"], []).append(r)
    for e in events:
        if not e["rule"]:
            new.setdefault(full_name(e), []).append(e)
    out = []
    for k in sorted(set(old) | set(new)):
        o, n = old.get(k, []), new.get(k, [])
        if len(o) == 1 and len(n) == 1:
            o, n = o[0], n[0]
            if n["done"] and not o["done"]:  # 打勾時畫的位置會換成 完成: 日，不另算改期
                out.append(("完成", k, "", str(shown(n))))
            elif o["d"] != str(shown(n)):
                out.append(("改期", k, o["d"], str(shown(n))))
        elif o and not n:
            out.append(("移除", k, o[0]["d"], ""))
        elif n and not o:
            out.append(("新增", k, "", str(n[0]["d"])))
    return out


# ---------- 寫回與紀錄 ----------

agenda_lock = agenda.agenda_lock  # 寫入鎖只有一份實作，協定見 agenda.py（76 2026-10-16）


def apply(ch):
    """寫回 agenda.md。共用檔（多 session 用 agenda.py add／done 同時改，76 2026-10-16 提醒）→
    取 agenda.md.lock 後：重讀、按行內容找目標行（不靠行號）、寫暫存檔再 os.replace；
    替換前檔案若又被改（對方沒取鎖時的保險）就重來。找不到的目標行從 ch 移除、不寫，回傳其清單。"""
    p = agenda.AGENDA
    with agenda_lock(p):
        return _apply_locked(ch, p)


def _apply_locked(ch, p):
    for _ in range(5):
        # 比對用「內容」不用 stat：Windows 對正被 append 的檔，目錄項 mtime／size 會延遲更新，
        # stat 比對看不到別人剛加的行 → 整檔覆寫把它蓋掉（76 2026-10-16 併發測試：0.05s 間隔掉 5/592 行）。
        before = p.read_bytes()
        lines = before.decode("utf-8").splitlines()
        new, missed = list(lines), []

        def find(e):
            i = e["line"] - 1
            if 0 <= i < len(lines) and lines[i].strip() == e["raw"].strip():
                return i
            hits = [j for j, l in enumerate(lines) if l.strip() == e["raw"].strip()]
            return hits[0] if len(hits) == 1 else None

        moves, dones, adds = [], [], []
        for e, d, why in ch["move"]:
            i = find(e)
            if i is None:
                missed.append(e["title"])
                continue
            new[i] = agenda.reschedule(new[i].strip(), d)  # 沒有 原定 就記舊日期
            moves.append((e, d, why))
        for e, why in ch["done"]:
            i = find(e)
            if i is None:
                missed.append(e["title"])
                continue
            new[i] = agenda.mark_done(new[i].strip(), date.today())  # 打勾＋完成:今天
            dones.append((e, why))
        for s, why in ch["add"]:
            if agenda.valid(s):
                new.append(s)
                adds.append((s, why))
            else:
                missed.append(s)
        tmp = p.with_name(p.name + ".agenda-gantt.tmp")
        try:
            text, pushes = agenda.settle("\n".join(new) + "\n")  # 排程引擎順延後項；新增行歸段、打勾行進已完成
            tmp.write_text(text, encoding="utf-8")
            if p.read_bytes() != before:  # 讀完到現在之間有人寫 → 重算
                time.sleep(0.2)
                continue
            # Windows：別的 process 正開著 agenda.md（例如 agenda.py add 在 append）時不能替換 → WinError 5。
            # 76 2026-10-16：當成「檔案正被改」，算進 5 次重試；不讓它冒出去留下 tmp。
            os.replace(tmp, p)
        except PermissionError:
            time.sleep(0.2)
            continue
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
        ch["move"], ch["done"], ch["add"] = moves, dones, adds
        log_changes(agenda.CHANGES, agenda.push_rows(pushes))
        return missed
    raise RuntimeError("agenda.md 一直在被改或被鎖住，5 次都沒寫成，什麼都沒寫")


def report(ch, ag, src):
    print(f"=== ProjectLibre 端（{src.name if src else '無存檔'}）===")
    for e, d, why in ch["move"]:
        print(f"📅 改期 L{e['line']}: {e['d']} → {d}  {e['title']}" + (f"（原因：{why}）" if why else ""))
    for e, why in ch["done"]:
        print(f"✅ 完成 L{e['line']}: {e['title']}")
    for s, _ in ch["add"]:
        print(f"➕ 新增: {s}")
    for s in ch["skip"]:
        print(f"⏭️  {s}")
    for s in ch["conflict"]:
        print(f"⚠️ 衝突: {s}")
    if not any(ch.values()):
        print("（無改動）")
    print("=== agenda 端（export 之後）===")
    if ag is None:
        print("（無快照，無法比對；同步一次後開始追蹤）")
    else:
        for act, k, old, new in ag:
            print(f"{'📅' if act == '改期' else '•'} {act}: {k}  {old or '—'} → {new or '—'}")
        if not ag:
            print("（無改動）")


def state(xml):
    snap = load_snapshot(xml)
    src = latest(xml)
    events, _ = agenda.load()
    ch = pl_changes(read_xml(src), snap, events) if src else {k: [] for k in ("move", "done", "add", "skip", "conflict")}
    if snap is None:
        # XML 進 git（9ec5424d）後，別台電腦 pull 到 XML 卻沒有快照：XML 與 agenda 的差異分不出是誰改的，
        # 照寫會把舊日期倒寫回 agenda（76 2026-10-16）→ 一律不寫回，以 agenda 為準；sync 會重產 XML 並建快照
        n = sum(len(ch[k]) for k in ("move", "done", "add", "conflict"))
        if n:
            ch["skip"].append(f"本機沒有快照，{n} 項差異分不出誰改的 → 不寫回，以 agenda 為準（sync 會重產 XML 並建快照，之後再調整）")
        ch.update(move=[], done=[], add=[], conflict=[])
    return snap, src, events, ch, agenda_changes(snap, events)


def check(xml):
    """分級同 rules-doctor R11（76 92ab32aa）：只有 ProjectLibre 端未同步算 🟡；
    agenda 端改動（任何 session 加一條就成立）與本機沒快照（其他電腦）只給 ℹ️，否則變永久黃燈。"""
    snap, src, _, ch, ag = state(xml)
    if snap is None and src is None:
        print("🟢 本機沒有甘特圖快照／XML（不適用）")
        return
    n_pl = len(ch["move"]) + len(ch["done"]) + len(ch["add"]) + len(ch["conflict"])
    if n_pl:
        print(f"🟡 ProjectLibre 有 {n_pl} 項改動未同步回 agenda.md（{len(ch['conflict'])} 衝突）→ agenda-gantt.py sync")
    else:
        print("🟢 ProjectLibre 沒有未同步的改動")
    if ag is None:
        print("ℹ️ 沒有快照，sync 一次後開始追蹤 agenda 端改動")
    elif ag:
        print(f"ℹ️ agenda.md 在 export 後改了 {len(ag)} 項，ProjectLibre 視圖過期（下次 sync 帶入）")


def sync(xml, days_, open_it, dry_run, force):
    snap, src, events, ch, ag = state(xml)
    report(ch, ag, src)
    if ch["conflict"] and not force:
        sys.exit("中止：有衝突，什麼都沒寫。先決定以哪端為準（改 agenda.md 或 ProjectLibre），或 --force 丟棄 ProjectLibre 端的衝突項")
    if dry_run:
        print("dry-run : 未寫入")
        return
    rows = ag_rows(ag, snap)
    if ch["move"] or ch["done"] or ch["add"]:
        for m in apply(ch):
            print(f"⚠️ agenda 該行剛被別人改掉，沒寫回：{m}")
        rows += pl_rows(ch)
        print(f"applied : 寫回 {agenda.AGENDA}")
    log_changes(xml.parent / "changes.md", rows)
    export(xml, days_, open_it)


def engine_logged(snap):
    """export 之後排程引擎已記過的順延 {(事項, 新日期)}：agenda 端比對會再看到同一筆，不重複記。"""
    if not snap or not agenda.CHANGES.is_file():
        return set()
    since = snap["exported"][:16].replace("T", " ")
    out = set()
    for l in agenda.CHANGES.read_text(encoding="utf-8").splitlines():
        c = l.split("|")
        if len(c) > 7 and c[2] == "排程引擎" and c[1] >= since:
            out.add((c[4], c[6]))
    return out


def ag_rows(ag, snap=None):
    skip = engine_logged(snap)
    return [("agenda", act, k, old, new, "") for act, k, old, new in (ag or []) if (k, new) not in skip]


def pl_rows(ch):
    return ([("ProjectLibre", "改期", full_name(e), str(e["d"]), str(d), why) for e, d, why in ch["move"]]
            + [("ProjectLibre", "完成", full_name(e), "", str(e["d"]), why) for e, why in ch["done"]]
            + [("ProjectLibre", "新增", s.split(" → ")[0], "", s[:10], why) for s, why in ch["add"]])


# ---------- 自動感測（watch）----------

def absorb(xml):
    """ProjectLibre 存檔 → 寫回 agenda.md、記 changes.md、快照跟上使用者視窗；**不重產 XML**（使用者的視窗繼續用）。
    回傳 (寫回筆數, 衝突清單)。沒快照就不自動做（要先手動 sync 一次建立基準）。"""
    snap, _, _, ch, _ = state(xml)
    if ch["conflict"]:
        return 0, ch["conflict"]
    n = len(ch["move"]) + len(ch["done"]) + len(ch["add"])
    if not n or snap is None:
        return 0, []
    missed = [f"agenda 該行剛被別人改掉，沒寫回：{m}" for m in apply(ch)]
    n = len(ch["move"]) + len(ch["done"]) + len(ch["add"])
    log_changes(xml.parent / "changes.md", pl_rows(ch))
    touched = {full_name(e) for e, _, _ in ch["move"]} | {full_name(e) for e, _ in ch["done"]}
    for s, _ in ch["add"]:
        m = agenda.LINE.match(s)
        if m:
            touched.add(f"{m.group('type')}{SEP}{m.group('title')}")
    events, _ = agenda.load()
    kmap = assign_keys(events)
    for e in events:
        if not e["rule"] and full_name(e) in touched:
            snap["rows"][kmap[id(e)]] = snap_row(e)
    snapshot_path(xml).write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    return n, missed


def refresh(xml, days_):
    """agenda 端有改動 → ProjectLibre 視窗沒開才重產 XML。
    開著時重產會出事：舊視窗裡的舊日期在下次存檔時，會被當成使用者把它改回去。"""
    snap, _, _, ch, ag = state(xml)
    if not ag:
        return None, 0
    if ch["move"] or ch["done"] or ch["add"] or ch["conflict"]:
        return "pending", len(ag)  # 先等 ProjectLibre 端寫回
    if gantt_window_open():
        return "window", len(ag)
    log_changes(xml.parent / "changes.md", ag_rows(ag, snap))
    export(xml, days_, False)
    return "refreshed", len(ag)


def gantt_window_open():
    """有沒有標題含 agenda-gantt 的視窗（ProjectLibre 開著甘特圖）。判斷失敗當作開著（保守，不重產）。"""
    try:
        import ctypes
        from ctypes import wintypes
        user32, found = ctypes.windll.user32, []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, _):
            n = user32.GetWindowTextLengthW(hwnd)
            if n and user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if DEFAULT_XML.stem in buf.value:
                    found.append(buf.value)
            return True

        user32.EnumWindows(cb, 0)
        return bool(found)
    except Exception:
        return True


TOAST = ("[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]|Out-Null;"
         "$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
         "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
         "$t=$x.GetElementsByTagName('text');$t.Item(0).InnerText='甘特圖同步';$t.Item(1).InnerText=$env:AG_MSG;"
         "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
         "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe')"
         ".Show([Windows.UI.Notifications.ToastNotification]::new($x))")


def notify(msg, log):
    log(f"notify  : {msg}")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", TOAST], env={**os.environ, "AG_MSG": msg},
                       timeout=20, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        pass


def watch(xml, days_, interval):
    """常駐：① ProjectLibre 存檔 → 自動寫回 agenda.md；② agenda.md 有新變動 → 視窗關著就重產 XML，開著就通知。"""
    try:
        lock = socket.socket()
        lock.bind(("127.0.0.1", WATCH_PORT))  # 單一實例
    except OSError:
        sys.exit("已有一個 agenda-gantt watch 在跑")
    logf = xml.parent / "watch.log"

    def log(msg):
        line = f"{datetime.now():%m-%d %H:%M:%S} {msg}"
        print(line, flush=True)
        with logf.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    mtime = lambda p: p.stat().st_mtime if p and p.is_file() else 0  # noqa: E731
    last_save, last_ag, last_win, told = mtime(latest(xml)), 0, gantt_window_open(), False
    log(f"watch   : 開始（每 {interval}s；資料 {xml.parent}）")
    while True:
        time.sleep(interval)
        try:
            if mtime(latest(xml)) != last_save:
                time.sleep(2)  # 等 ProjectLibre 寫完
                n, conflicts = absorb(xml)
                last_save = mtime(latest(xml))
                if n:
                    notify(f"已把 {n} 項改動寫回 agenda.md（記在 changes.md）", log)
                if conflicts:
                    notify(f"有 {len(conflicts)} 項沒有寫回：{conflicts[0][:60]}", log)
            win = gantt_window_open()
            ag_m = mtime(agenda.AGENDA)
            if ag_m != last_ag or (last_win and not win):
                last_ag = ag_m
                status, n = refresh(xml, days_)
                last_save = mtime(latest(xml))
                if status == "refreshed":
                    notify(f"agenda.md 有 {n} 項新變動，甘特圖已更新；下次開啟就是最新", log)
                    told = False
                elif status == "window" and not told:
                    notify(f"agenda.md 有 {n} 項新變動；關掉甘特圖視窗後會自動更新", log)
                    told = True
            last_win = win
        except Exception as exc:  # 常駐程式不能因單次錯誤掛掉
            log(f"error   : {type(exc).__name__}: {exc}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check", "sync", "export", "watch", "open"])
    ap.add_argument("--interval", type=float, default=3, help="watch 輪詢秒數")
    ap.add_argument("--xml", type=Path, default=DEFAULT_XML)
    ap.add_argument("--days", type=int, default=90, help="重複事件展開天數")
    ap.add_argument("--open", action="store_true", help="完成後用 ProjectLibre 開")
    ap.add_argument("--dry-run", action="store_true", help="sync 只列不寫")
    ap.add_argument("--force", action="store_true", help="sync：略過衝突項；export：丟棄 ProjectLibre 未同步改動")
    a = ap.parse_args()
    if a.cmd == "check":
        return check(a.xml)
    if a.cmd == "sync":
        return sync(a.xml, a.days, a.open, a.dry_run, a.force)
    if a.cmd == "watch":
        return watch(a.xml, a.days, a.interval)
    # 拒絕時 exit code 分開（Obsidian 甘特圖外掛靠它決定跳哪種提示）：4＝視窗開著、3＝ProjectLibre 有未同步改動
    if gantt_window_open():  # open 與 export 都擋：開著重產，舊視窗存檔會把舊日期蓋回去（使用者 10-17 export 也擋）
        print("甘特圖已經開著：直接用那個視窗；要重產先關掉它（舊視窗存檔會把舊日期蓋回去）", file=sys.stderr)
        return 4
    if a.cmd == "open":  # 桌面捷徑用（使用者 2026-10-16）：同步 → 重產 → UTC 時區開
        return sync(a.xml, a.days, True, False, False)
    _, _, _, ch, _ = state(a.xml)
    pending = ch["move"] or ch["done"] or ch["add"] or ch["conflict"]
    if pending and not a.force:
        print("ProjectLibre 有未同步改動，export 會蓋掉它 → 改用 sync；確定要丟棄才加 --force", file=sys.stderr)
        return 3
    export(a.xml, a.days, a.open)


if __name__ == "__main__":
    sys.exit(main())
