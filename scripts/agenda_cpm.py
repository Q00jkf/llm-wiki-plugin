#!/usr/bin/env python3
"""agenda_cpm —— 排程引擎：工作天曆、前推／後推、要徑。純函式，agenda.py 呼叫。

規則：
- 工作天＝週一～五，扣辦公日曆（<ref>/辦公日曆表_*.csv，台灣人事行政總處格式）的放假日，加補班日；
  沒有日曆的年份只扣週末。ref 由 agenda.py 傳入（vault 的 raw/manager/schedule/ref/）
- 行首日期＝最後一天；工期N天往前推工作天出開始日；被接的里程碑當 1 天（同 agenda-gantt 匯出）
- 沒有接 → 日期照寫（Must Start On）；有接 → 開始＝max(寫的開始日, 前項完成＋1 工作天＋前置天數)
  （Start No Earlier Than：前項提早完成不往前拉）；後項是里程碑 → 落在前項完成日＋前置天數
- 已打 ✅ → 用實際完成日（完成:），不再推
- 屬:x → x 為母項：開始＝子項最早、完成＝子項最晚，寫入時跟著改（已完成／硬期限不改）
- 截止:MM-DD → 不推日期，只壓寬裕；預計完成晚於截止日記 dl_late
- 要徑：以接／屬串起來的每組各自算（不同於 ProjectLibre 的全檔終點）；組內最晚完成日為終點往回推，總寬裕 ≤ 0 的未完成事項
"""
import csv
from datetime import date, timedelta
from pathlib import Path


class Calendar:
    def __init__(self, ref=None):
        """ref：放 辦公日曆表_*.csv 的資料夾；None 或不存在＝只扣週末。"""
        self.off, self.on, self.names, self.years = set(), set(), {}, set()
        for p in (sorted(Path(ref).glob("辦公日曆表_*.csv")) if ref else []):
            with p.open(encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    s = r["西元日期"].strip()
                    d = date(int(s[:4]), int(s[4:6]), int(s[6:8]))
                    self.years.add(d.year)
                    holiday = r["是否放假"].strip() == "2"
                    if holiday and d.weekday() < 5:
                        self.off.add(d)
                        self.names[d] = r["備註"].strip() or "放假"
                    elif not holiday and d.weekday() >= 5:
                        self.on.add(d)
                        self.names[d] = r["備註"].strip() or "補班"

    def is_work(self, d):
        return d in self.on or (d.weekday() < 5 and d not in self.off)

    def add(self, d, n):
        """往後（n>0）或往前（n<0）數 n 個工作天；n＝0 原樣。"""
        step = 1 if n > 0 else -1
        while n:
            d += timedelta(days=step)
            if self.is_work(d):
                n -= step
        return d

    def diff(self, a, b):
        """a→b 相差幾個工作天（b 較晚為正）。"""
        if a == b:
            return 0
        lo, hi, sign = (a, b, 1) if a < b else (b, a, -1)
        n, d = 0, lo
        while d < hi:
            d += timedelta(days=1)
            n += self.is_work(d)
        return sign * n


def schedule(events, cal, hard=lambda e: False):
    """回傳 {id(e): row}，只含以 代號／接 連起來的非重複事件。e["links"]＝[(前項代號, 類型 FS|SS|FF|SF, 前置天數)]。
    hard(e) 為真＝硬期限（比照 MS Project「必須完成於」＋截止日）：日期不動、後項從它寫的日期排，
    前項延誤只記 late（晚幾個工作天），負浮時往前項傳。
    row：es／ef（引擎算的開始／完成）、ls／lf、slack（工作天）、critical、push（應順延到的新完成日或 None）、
    late、drive（決定開始日的前項代號；None＝照寫的日期）。循環的事件不算（--check 另報）。"""
    nodes = [e for e in events if not e["rule"]]
    ids = {}
    for e in nodes:
        if e["id"]:
            ids.setdefault(e["id"], e)
    preds = {id(e): [(ids[a], t, lag, a) for a, t, lag in e["links"] if a in ids] for e in nodes}
    succs = {id(e): [] for e in nodes}
    for e in nodes:
        for p, t, lag, _ in preds[id(e)]:
            succs[id(p)].append((e, t, lag))
    kids = {id(e): [] for e in nodes}  # 屬:x → x 是母項（摘要任務），日期由子項推出
    up = {}
    for e in nodes:
        if e["parent"] in ids and ids[e["parent"]] is not e:
            kids[id(ids[e["parent"]])].append(e)
            up[id(e)] = ids[e["parent"]]
    net = [e for e in nodes if preds[id(e)] or succs[id(e)] or kids[id(e)] or id(e) in up]
    is_pred = {id(e) for e in net if succs[id(e)]}

    def dur(e):
        if kids[id(e)] and id(e) in rows:  # 母項：子項跨距（工作天）
            return cal.diff(rows[id(e)]["es"], rows[id(e)]["ef"]) + 1
        return e["dur"] or (1 if id(e) in is_pred else 0)

    order, state = [], {}

    def visit(e):  # 前項先排；遇到循環就放棄這條
        st = state.get(id(e))
        if st == 2:
            return True
        if st == 1:
            return False
        state[id(e)] = 1
        ok = all(visit(p) for p, *_ in preds[id(e)]) and all(visit(k) for k in kids[id(e)])
        state[id(e)] = 2 if ok else 3
        if ok:
            order.append(e)
        return ok

    for e in net:
        visit(e)

    def start_from_finish(f, d):
        return cal.add(f, -(d - 1)) if d else f

    def finish_from_start(s, d):
        return cal.add(s, d - 1) if d else s

    def earliest_start(t, lag, p, d):
        """前項 p（row）→ 後項（工期 d）最早開始日。日為單位：開始＝08:00、完成＝17:00；里程碑沒有長度。"""
        if t == "SS":
            return cal.add(p["es"], lag)
        if t == "FF":
            return start_from_finish(cal.add(p["ef"], lag), d)
        if t == "SF":  # 後項完成 ≥ 前項開始（前項開始日 08:00＝前一工作天下班）
            return start_from_finish(cal.add(p["es"], lag - 1) if d else cal.add(p["es"], lag), d)
        return cal.add(p["ef"], (1 + lag) if d else lag)  # FS

    def latest_finish(t, lag, s, sd, d):
        """後項 s（row，工期 sd）→ 前項（工期 d）最晚完成日；earliest_start 的反運算。"""
        if t == "SS":
            return finish_from_start(cal.add(s["ls"], -lag), d)
        if t == "FF":
            return cal.add(s["lf"], -lag)
        if t == "SF":
            return finish_from_start(cal.add(s["lf"], 1 - lag) if sd else cal.add(s["ls"], -lag), d)
        return cal.add(s["ls"], -((1 + lag) if sd else lag))  # FS

    rows = {}
    for e in order:
        fin = e["fin"] if e["done"] and e["fin"] else e["d"]
        ks = [rows[id(k)] for k in kids[id(e)] if id(k) in rows]
        if ks:  # 母項：開始＝子項最早、完成＝子項最晚（兩個方向都跟著改）；已完成或硬期限不改
            es, ef = min(k["es"] for k in ks), max(k["ef"] for k in ks)
            late = cal.diff(fin, ef) if hard(e) and not e["done"] and ef > fin else 0
            keep = e["done"] or hard(e)
            rows[id(e)] = {"e": e, "es": es, "ef": fin if late else ef, "drive": "子項" if ef != fin else None,
                           "late": late, "fin0": fin, "summary": True,
                           "push": None if keep or ef == e["d"] else ef}
            continue
        s0 = start_from_finish(fin, dur(e))
        es, drive = s0, None
        if not e["done"]:
            for p, t, lag, code in preds[id(e)]:
                st = earliest_start(t, lag, rows[id(p)], dur(e))
                if st > es:
                    es, drive = st, code
        ef = finish_from_start(es, dur(e))
        late = 0
        if hard(e) and not e["done"] and ef > fin:  # 硬期限：留在寫的日期，只記晚多少
            late, es, ef = cal.diff(fin, ef), s0, fin
        rows[id(e)] = {"e": e, "es": es, "ef": ef, "drive": drive, "late": late, "fin0": fin, "summary": False,
                       "push": ef if not e["done"] and ef > e["d"] else None}

    # 後推：每組（以接連通）以組內最晚完成日為終點
    comp, cid = {}, 0
    for e in order:
        if id(e) in comp:
            continue
        cid += 1
        stack = [e]
        while stack:
            x = stack.pop()
            if id(x) in comp or id(x) not in rows:
                continue
            comp[id(x)] = cid
            stack += [p for p, *_ in preds[id(x)]] + [s for s, *_ in succs[id(x)]] + kids[id(x)] + ([up[id(x)]] if id(x) in up else [])
    end = {}
    for k, c in comp.items():
        end[c] = max(end.get(c, rows[k]["ef"]), rows[k]["ef"])
    for e in reversed(order):
        r = rows[id(e)]
        lf = end[comp[id(e)]]
        for s, t, lag in succs[id(e)]:
            if id(s) in rows:
                lf = min(lf, latest_finish(t, lag, rows[id(s)], dur(s), dur(e)))
        if id(e) in up and id(up[id(e)]) in rows:  # 子項不能晚於母項的最晚完成
            lf = min(lf, rows[id(up[id(e)])]["lf"])
        if e["deadline"] and not e["done"]:  # 截止日：只壓寬裕、不推日期（MS Project Deadline）
            lf = min(lf, e["deadline"])
        if hard(e) and not e["done"]:
            lf = min(lf, r["fin0"])
            r["ef"] = cal.add(r["ef"], r["late"])  # 寬裕用預計會完成的日子算 → 延誤時為負
        r["dl_late"] = cal.diff(e["deadline"], r["ef"]) if e["deadline"] and not e["done"] and r["ef"] > e["deadline"] else 0
        r["lf"] = lf
        r["ls"] = start_from_finish(lf, dur(e))
        r["slack"] = cal.diff(r["ef"], lf)
        r["critical"] = not e["done"] and r["slack"] <= 0
        r["group"] = comp[id(e)]
    return rows
