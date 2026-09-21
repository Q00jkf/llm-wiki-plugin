#!/usr/bin/env python3
"""agenda —— 日程唯一真相來源 wiki/agenda.md 的讀寫、開場窗口與單向匯出。

為什麼：日期散在 log／hot／README 的散文裡，「哪天要做什麼」沒有地方能回答。
一行一事、靠腳本維護（驗格式／展開重複／歸檔）；外部日曆全是由本檔單向產出的視圖。
設計與藍圖見 wiki/meta/agenda-system.md。

格式：日期 [HH:MM[-HH:MM]] 類型 標題 [每月D日|每週X|每年MM-DD|每N天] [#tag …] [→ 出處]；行首 ✅＝完成。

用法：
    python agenda.py                    # 開場窗口：逾期／今天／7 天內（非 vault 或無 agenda.md 時安靜）
    python agenda.py --days 14 --tag X  # 放寬窗口、按 tag 篩
    python agenda.py add "…"            # 驗格式後 append（無檔則建最小骨架）
    python agenda.py done 關鍵字         # 唯一命中的未完成行加 ✅
    python agenda.py --check            # 壞行與可歸檔行數（exit 0）
    python agenda.py --tidy             # ✅ 與 30 天前的非重複事件搬到 wiki/agenda-archive.md
    python agenda.py --ics [out]        # 全量重生 .ics（預設 <vault>/agenda.ics；重複事件展開 365 天）
    python agenda.py --notify           # 同窗口、Telegram 友善的精簡文字（只印，不發送）

--notify 不發送：由使用者接 OS 排程器＋Bot（例：Windows 工作排程器每天 08:30 跑本指令，stdout 餵 Bot API）。
plugin 不持有 token、不打網路；0 token、不需要 Claude session。
"""
import argparse
import hashlib
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib.vaultpaths import find_vault_root  # noqa: E402

try:
    import _guard_status  # noqa: E402
except ImportError:
    _guard_status = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ARCHIVE_AFTER_DAYS = 30
ICS_HORIZON_DAYS = 365
WEEKDAY = "一二三四五六日"
HEADER_END = "<!-- 事件從下一行開始 -->"
FORMAT_HINT = "日期 [HH:MM[-HH:MM]] 類型 標題 [每月D日|每週X|每年MM-DD|每N天] [#tag …] [→ 出處]"
MIN_HEADER = (
    "---\ntitle: 日程（agenda）\ntype: meta\nmaintenance: transactional\n---\n\n# 日程\n\n"
    f"> 一行一事，由 agenda.py 讀寫。格式：`{FORMAT_HINT}`；完成的行前綴 `✅`。\n\n{HEADER_END}\n"
)

LINE = re.compile(
    r"^(?P<done>✅\s+)?"
    r"(?P<date>\d{4}-\d{2}-\d{2})"
    r"(?:\s+(?P<t1>\d{2}:\d{2})(?:-(?P<t2>\d{2}:\d{2}))?)?"
    r"\s+(?P<type>[^\s#→]+)"
    r"\s+(?P<title>.+?)"
    r"(?:\s+(?P<rule>每(?:月\d{1,2}日|週[一二三四五六日]|年\d{2}-\d{2}|\d+天)))?"
    r"(?P<tags>(?:\s+#[^\s#]+)*)"
    r"(?:\s+→\s*(?P<ref>.+?))?\s*$"
)


def parse(s):
    """格式＋日期／時間真的存在（regex 擋不住 2026-13-99、25:00）。不合回 None。"""
    m = LINE.match(s)
    if not m:
        return None
    d = m.groupdict()
    try:
        d["d"] = datetime.strptime(d["date"], "%Y-%m-%d").date()
        for t in (d["t1"], d["t2"]):
            if t:
                datetime.strptime(t, "%H:%M")
    except ValueError:
        return None
    d["tags"] = [t.lstrip("#") for t in d["tags"].split()] if d["tags"] else []
    d["done"] = bool(d["done"])
    return d


def load(agenda):
    events, bad = [], []
    if not agenda.is_file():
        return events, bad
    lines = agenda.read_text(encoding="utf-8").splitlines()
    if not any(l.strip() == HEADER_END for l in lines):
        return events, [(0, f"缺少哨兵行 {HEADER_END}，其後才算事件")]
    body = False
    for i, l in enumerate(lines, 1):
        if not body:
            body = l.strip() == HEADER_END
            continue
        s = l.strip()
        if not s or s[0] in "#<>":
            continue
        e = parse(s)
        if e is None:
            bad.append((i, s))
            continue
        e["line"], e["raw"] = i, l
        events.append(e)
    return events, bad


def next_occurrences(e, start, end):
    """重複事件在 [start, end] 內的日期；非重複回 [原日期]（若在範圍內）。"""
    rule = e["rule"]
    if not rule:
        return [e["d"]] if start <= e["d"] <= end else []
    out, d = [], max(e["d"], start)
    while d <= end:
        if rule.startswith("每月"):
            ok = d.day == int(rule[2:-1])
        elif rule.startswith("每週"):
            ok = WEEKDAY[d.weekday()] == rule[2]
        elif rule.startswith("每年"):
            ok = d.strftime("%m-%d") == rule[2:]
        else:
            ok = (d - e["d"]).days % int(rule[1:-1]) == 0
        if ok:
            out.append(d)
        d += timedelta(days=1)
    return out


def timestr(e):
    return (e["t1"] + (f"-{e['t2']}" if e["t2"] else "")) if e["t1"] else ""


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
    overdue.sort(key=lambda x: x[1])
    todays.sort(key=lambda x: x[0]["t1"] or "")
    soon.sort(key=lambda x: (x[1], x[0]["t1"] or ""))
    return overdue, todays, soon


def fmt(e, d):
    tags = " ".join("#" + x for x in e["tags"])
    return f"{d.strftime('%m-%d')}（{WEEKDAY[d.weekday()]}）{timestr(e):<12} {e['type']:<4} {e['title']}  {tags}".rstrip()


def report(events, bad, days, tag, today):
    overdue, todays, soon = window(events, days, tag, today)
    print(f"=== agenda {today}（{WEEKDAY[today.weekday()]}） 窗口 {days} 天" + (f" tag:{tag}" if tag else "") + " ===")
    for label, rows in (("🔴 逾期", overdue), ("⏰ 今天", todays), (f"🔵 {days} 天內", soon)):
        if rows:
            print(label)
            for e, d in rows:
                extra = f"（逾 {(today - d).days} 天）" if label.startswith("🔴") else ""
                print(f"   {fmt(e, d)}{extra}")
    if bad:
        print(f"⚠️ 格式壞行 {len(bad)}（agenda.py --check）")
    n = len(overdue) + len(todays) + len(soon)
    if n == 0 and not bad:
        print("（窗口內無事）")
    return n


def notify(events, bad, days, tag, today):
    """Telegram 友善：無對齊、無表頭、每行一事。"""
    overdue, todays, soon = window(events, days, tag, today)

    def row(e, d, with_date):
        head = (f"{d.strftime('%m-%d')} " if with_date else "") + (timestr(e) + " " if e["t1"] else "")
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


def check(events, bad, agenda, today):
    print("=== agenda --check ===")
    if not agenda.is_file():
        print(f"   無 {agenda.name}（agenda.py add 會自動建立）")
    print(f"input   : {len(events)} 事件（{sum(e['done'] for e in events)} ✅，{sum(bool(e['rule']) for e in events)} 重複）")
    for i, s in bad:
        print(f"   L{i}: 格式不符 → {s[:80]}")
    stale = [e for e in events if e["done"] or (not e["rule"] and e["d"] < today - timedelta(days=ARCHIVE_AFTER_DAYS))]
    if stale:
        print(f"   {len(stale)} 行可歸檔（agenda.py --tidy）")
    print("verdict : " + ("🟢 CLEAN" if not bad else f"🟡 {len(bad)} 壞行"))
    return 0


def write_lines(p, lines):
    with p.open("w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def add(agenda, text):
    s = text.strip()
    if parse(s) is None:
        print(f"🔴 格式不符：{s}\n   {FORMAT_HINT}")
        return 1
    if not agenda.is_file():
        agenda.parent.mkdir(parents=True, exist_ok=True)
        write_lines(agenda, MIN_HEADER.splitlines())
    prefix = "" if agenda.read_text(encoding="utf-8").endswith("\n") else "\n"
    with agenda.open("a", encoding="utf-8", newline="\n") as f:
        f.write(prefix + s + "\n")
    print(f"added   : {s}")
    return 0


def done(agenda, key):
    if not key or not agenda.is_file():
        print("🔴 done 需要關鍵字，且 wiki/agenda.md 要存在")
        return 1
    lines = agenda.read_text(encoding="utf-8").splitlines()
    hit = [i for i, l in enumerate(lines) if key in l and LINE.match(l.strip()) and not l.strip().startswith("✅")]
    if len(hit) != 1:
        print(f"🔴 命中 {len(hit)} 行（要剛好 1 行）：{[lines[i][:60] for i in hit]}")
        return 1
    lines[hit[0]] = "✅ " + lines[hit[0]].strip()
    write_lines(agenda, lines)
    print(f"done    : {lines[hit[0]]}")
    return 0


def tidy(agenda, archive, events, today):
    cut = today - timedelta(days=ARCHIVE_AFTER_DAYS)
    move = [e for e in events if e["done"] or (not e["rule"] and e["d"] < cut)]
    if not move:
        print("tidy    : 無可歸檔行")
        return 0
    idx = {e["line"] - 1 for e in move}
    keep = [l for i, l in enumerate(agenda.read_text(encoding="utf-8").splitlines()) if i not in idx]
    write_lines(agenda, keep)
    head = "" if archive.is_file() else "# agenda 歸檔（由 agenda.py --tidy 搬入，原行不改）\n\n"
    with archive.open("a", encoding="utf-8", newline="\n") as f:
        f.write(head + "\n".join(e["raw"].strip() for e in sorted(move, key=lambda e: e["d"])) + "\n")
    print(f"tidy    : 歸檔 {len(move)} 行 → {archive.name}")
    return 0


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


ICS_STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")   # RFC 5545：DTSTAMP＝產生時間


def vevent(e, d):
    """固定 UID＝md5(日期＋標題)，重匯覆蓋不重複；無時間＝全天；無結束＝1 小時。"""
    uid = hashlib.md5(f"{d.isoformat()}{e['title']}".encode("utf-8")).hexdigest() + "@llm-wiki"
    ds = d.strftime("%Y%m%d")
    if e["t1"]:
        start = datetime.combine(d, datetime.strptime(e["t1"], "%H:%M").time())
        end = datetime.combine(d, datetime.strptime(e["t2"], "%H:%M").time()) if e["t2"] else start + timedelta(hours=1)
        if end <= start:
            end += timedelta(days=1)
        when = [f"DTSTART:{start:%Y%m%dT%H%M%S}", f"DTEND:{end:%Y%m%dT%H%M%S}"]
    else:
        when = [f"DTSTART;VALUE=DATE:{ds}", f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}"]
    lines = ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{ICS_STAMP}", *when,
             f"SUMMARY:{ics_escape(e['type'] + ' ' + e['title'])}"]
    if e["tags"]:
        lines.append("CATEGORIES:" + ",".join(ics_escape(t) for t in e["tags"]))
    if e["ref"]:
        lines.append(f"DESCRIPTION:{ics_escape('→ ' + e['ref'])}")
    return lines + ["END:VEVENT"]


def export_ics(events, out, today):
    """全量重生：非重複事件各一筆，重複事件展開至 365 天內每一次；✅ 不輸出。浮動本地時間（無 TZID，匯入端以自己的時區解讀；跨時區共用再加 TZID）。DTSTAMP 為產生時間，故重跑不 byte-identical，UID 才是去重鍵。"""
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


def main():
    ap = argparse.ArgumentParser(description=FORMAT_HINT)
    ap.add_argument("cmd", nargs="?", choices=["add", "done"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--tag")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--tidy", action="store_true")
    ap.add_argument("--ics", nargs="?", const="", metavar="OUT")
    ap.add_argument("--notify", action="store_true")
    a = ap.parse_args()

    root = find_vault_root(Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
    explicit = a.cmd or a.check or a.tidy or a.notify or a.ics is not None
    if root is None:
        if explicit:
            print("🔴 找不到 vault（往上找不到含 wiki/ 的目錄）")
            return 1
        return 0  # SessionStart：非 vault 目錄保持安靜
    agenda, archive = root / "wiki" / "agenda.md", root / "wiki" / "agenda-archive.md"
    today = date.today()

    if a.cmd == "add":
        return add(agenda, a.arg or "")
    if a.cmd == "done":
        return done(agenda, a.arg or "")
    events, bad = load(agenda)
    if a.check:
        return check(events, bad, agenda, today)
    if a.tidy:
        return tidy(agenda, archive, events, today)
    if a.ics is not None:
        return export_ics(events, Path(a.ics) if a.ics else root / "agenda.ics", today)
    if a.notify:
        return notify(events, bad, a.days, a.tag, today)
    if not agenda.is_file():
        return 0  # vault 尚未啟用日程：開場安靜
    n = report(events, bad, a.days, a.tag, today)
    if _guard_status is not None:
        try:
            _guard_status.record("agenda", f"{n} 項" if n else "CLEAN", 0)
        except Exception:  # 守門留痕失敗不影響窗口
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
