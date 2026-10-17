"""agenda／agenda_cpm 回歸測試 —— 跑法：python scripts/test_agenda.py（exit 0＝全過）

排程（接／工期／硬期限／屬／截止／進度）的期望值都先拿 ProjectLibre 1.9.8 對過答案（日期與要徑一致；
要徑旗標差異是定義不同——本系統每組各算），再凍結成這裡的斷言。

每個案子建一個暫存 vault（wiki/agenda.md＋raw/.manifest.json），不碰真的 vault。
工作天曆用下面 HOLIDAYS_2026 寫成的辦公日曆 CSV（10-26 補假，多個案子靠它）。
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import agenda  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
D = date.fromisoformat
fails, cases = [], 0
# 2026 年平日放假（人事行政總處辦公日曆表 115 年）；本測試只靠 10-09、10-26
HOLIDAYS_2026 = ["20260101", "20260216", "20260217", "20260218", "20260219", "20260220", "20260227", "20260403",
                 "20260406", "20260501", "20260619", "20260925", "20260928", "20261009", "20261026", "20261225"]


def eq(name, got, want):
    global cases
    cases += 1
    if got != want:
        fails.append(f"{name}: got {got} want {want}")


def vault(body=None):
    """暫存 vault：日曆目錄 cal/、manifest 指過去；body 不是 None 就寫 wiki/agenda.md。"""
    work = Path(tempfile.mkdtemp(prefix="agenda_test_"))
    (work / "cal").mkdir()
    (work / "cal" / "辦公日曆表_115.csv").write_text(
        "西元日期,星期,是否放假,備註\n" + "".join(f"{d},,2,假日\n" for d in HOLIDAYS_2026), encoding="utf-8")
    (work / "raw").mkdir()
    (work / "raw" / ".manifest.json").write_text(json.dumps({"config": {"agenda": {"calendar_dir": "cal"}}}), encoding="utf-8")
    (work / "wiki").mkdir()
    if body is not None:
        (work / "wiki" / "agenda.md").write_text("---\n---\n" + agenda.HEADER_END + "\n" + body, encoding="utf-8")
    return work


def fresh(body):
    work = vault(body)
    agenda.configure(work)
    return work


key = lambda e: e["title"].split()[0]  # noqa: E731
by_key = lambda evs: {key(e): e for e in evs}  # noqa: E731

# 1) 接／工期／FS＋N／SS／FF／−N、已完成前項、里程碑後項、硬期限（交件）
fresh("""2026-10-20 待辦 A 規格 工期3天 代號:a #T
2026-10-21 待辦 B 實作 工期5天 代號:b 接:a #T
2026-10-23 待辦 C 測試 工期2天 代號:c 接:b+2 #T
2026-10-30 交件 D 樣品交付 接:c #T
2026-10-22 待辦 E 文件 工期2天 代號:e 接:a~SS+1 #T
2026-10-29 待辦 F 報告 工期1天 代號:f 接:e~FF+3,b-1 #T
✅ 2026-10-15 待辦 G 採購 完成:10-19 代號:g #U
2026-10-19 待辦 H 組裝 工期2天 代號:h 接:g #U
2026-10-20 提醒 I 通知 接:h #U
""")
ev, bad = agenda.load()
eq("1 解析", bad, [])
rows = {key(r["e"]): r for r in agenda.plan(ev).values()}
eq("1 A es", rows["A"]["es"], D("2026-10-16"))
eq("1 B ef（跳 10-26 補假）", rows["B"]["ef"], D("2026-10-28"))
eq("1 C es（10-28 完成＋1＋2）", rows["C"]["es"], D("2026-11-02"))
eq("1 C ef", rows["C"]["ef"], D("2026-11-03"))
eq("1 D 交件不推", rows["D"]["push"], None)
eq("1 D late", rows["D"]["late"], 2)
eq("1 D slack", rows["D"]["slack"], -2)
eq("1 C slack（負浮往前傳）", rows["C"]["slack"], -2)
eq("1 E es（SS 不早於寫的日期）", rows["E"]["es"], D("2026-10-21"))
eq("1 F es", rows["F"]["es"], D("2026-10-29"))
eq("1 H ef（接已完成 G 的實際完成日）", rows["H"]["ef"], D("2026-10-21"))
eq("1 I push（里程碑後項）", rows["I"]["push"], D("2026-10-21"))
eq("1 要徑", sorted(k for k, r in rows.items() if r["critical"]), ["A", "B", "C", "D", "H", "I"])

eq("1 fmt", agenda.fmt_file(), 0)
txt = agenda.AGENDA.read_text(encoding="utf-8")
ev2, _ = agenda.load()
got = by_key(ev2)
eq("1 B 行首順延", got["B"]["d"], D("2026-10-28"))
eq("1 B 原定", got["B"]["base"], D("2026-10-21"))
eq("1 D 行首不動", got["D"]["d"], D("2026-10-30"))
eq("1 順延後無待推", [r["e"]["title"] for r in agenda.plan(ev2).values() if r["push"]], [])
eq("1 冪等", agenda.settle(txt)[0], txt)
eq("1 changes 列數（B C H I）", agenda.CHANGES.read_text(encoding="utf-8").count("|排程引擎|改期|"), 4)

agenda.move("A 規格", "2026-10-22")  # 前項延後 2 工作天 → 接的後項一起平移（使用者 10-16「永遠一起動」）
got = by_key(agenda.load()[0])
eq("1 move 後 B（10-28＋2 工作天，跳補假）", got["B"]["d"], D("2026-10-30"))
eq("1 move 後 B 原定保留最早", got["B"]["base"], D("2026-10-21"))
eq("1 move 後 C", got["C"]["d"], D("2026-11-05"))
eq("1 move 後 D 硬期限不動", got["D"]["d"], D("2026-10-30"))
eq("1 move 後 H 不同組不動", got["H"]["d"], D("2026-10-21"))
eq("1 平移紀錄", agenda.CHANGES.read_text(encoding="utf-8").count("，跟著平移|"), 4)  # B E C F（F 接 e,b 只動一次）

eq("1 沒給 --source 不記操作本身", "|Obsidian 甘特圖|" in agenda.CHANGES.read_text(encoding="utf-8"), False)
agenda.SOURCE = "Obsidian 甘特圖"  # 外掛呼叫時帶 --source：操作本身也記
agenda.move("A 規格", "2026-10-20")  # 拖回去 → 後項一起往前，A 的原定自動拿掉
got = by_key(agenda.load()[0])
eq("1 拖回 A 原定拿掉", got["A"]["base"], None)
eq("1 拖回 B", got["B"]["d"], D("2026-10-28"))
eq("1 拖回 C", got["C"]["d"], D("2026-11-03"))
eq("1 拖回 E", got["E"]["d"], D("2026-10-22"))
eq("1 外掛改期有記", "|Obsidian 甘特圖|改期|待辦｜A 規格|2026-10-22|2026-10-20|" in agenda.CHANGES.read_text(encoding="utf-8"), True)

agenda.resize("A 規格", "5")  # 拉條右端：工期 3→5，開始日 10-16 不動
got = by_key(agenda.load()[0])
eq("1 改工期 A 工期", got["A"]["dur"], 5)
eq("1 改工期 A 完成日", got["A"]["d"], D("2026-10-22"))
eq("1 改工期 B 跟著平移（接完成日）", got["B"]["d"], D("2026-10-30"))
eq("1 改工期 E 不動（接開始日 ~SS）", got["E"]["d"], D("2026-10-22"))
eq("1 改工期有記", "|Obsidian 甘特圖|改工期|待辦｜A 規格|3天|5天|" in agenda.CHANGES.read_text(encoding="utf-8"), True)
agenda.SOURCE = None


def refused(f, *a, **k):
    """sys.exit 擋下＝True；檔案必須沒變。"""
    before = agenda.AGENDA.read_text(encoding="utf-8")
    try:
        f(*a, **k)
    except SystemExit:
        return agenda.AGENDA.read_text(encoding="utf-8") == before
    return False


# 1b) 外掛新增事項、畫接、拆接（使用者 10-16 待加功能 #4）
fresh("""2026-10-20 待辦 P 設計 工期2天 #T
2026-10-21 待辦 Q 打樣 工期1天 代號:q #T
✅ 2026-10-14 待辦 R 備料 完成:10-14 #T
""")
agenda.SOURCE = "Obsidian 甘特圖"
agenda.add("2026-10-23 待辦 S 驗收 #T")
log = lambda: agenda.CHANGES.read_text(encoding="utf-8")  # noqa: E731
eq("1b 新增有記", "|Obsidian 甘特圖|新增|待辦｜S 驗收||2026-10-23|" in log(), True)
agenda.link("Q 打樣", "P 設計", code="p")  # P 沒代號 → 補 代號:p
got = by_key(agenda.load()[0])
eq("1b 前項補代號", got["P"]["id"], "p")
eq("1b 後項接", got["Q"]["links"], [("p", "FS", 0)])
eq("1b 接上後引擎順延 Q", got["Q"]["d"], D("2026-10-21"))
agenda.link("S 驗收", "Q 打樣", typ="ss", lag=-1)
eq("1b 類型＋負前置", by_key(agenda.load()[0])["S"]["links"], [("q", "SS", -1)])
agenda.link("S 驗收", "R 備料", code="r")  # 已完成的前項也可以接；接在既有 接: 後面
eq("1b 第二個前項", by_key(agenda.load()[0])["S"]["after"], ["q", "r"])
eq("1b 接上有記", "|Obsidian 甘特圖|接上|待辦｜S 驗收||接:q~SS-1|" in log(), True)
eq("1b 循環不寫", refused(agenda.link, "P 設計", "S 驗收"), True)
eq("1b 重複接不寫", refused(agenda.link, "Q 打樣", "P 設計"), True)
eq("1b 前項沒代號又沒給不寫", refused(agenda.link, "S 驗收", "驗收"), True)  # 同一行
eq("1b 代號重複不寫", refused(agenda.link, "P 設計", "S 驗收", code="q"), True)
eq("1b 已完成的後項不接", refused(agenda.link, "R 備料", "P 設計"), True)
agenda.unlink("S 驗收", "q")
got = by_key(agenda.load()[0])
eq("1b 拆接留其他", got["S"]["after"], ["r"])
agenda.unlink("S 驗收", "r")
got = by_key(agenda.load()[0])
eq("1b 全拆掉 接: 消失", ("接:" in got["S"]["raw"], got["S"]["d"]), (False, D("2026-10-23")))
eq("1b 拆接有記", "|Obsidian 甘特圖|拆接|待辦｜S 驗收|接:r||" in log(), True)
eq("1b 沒接的拆不寫", refused(agenda.unlink, "S 驗收", "q"), True)
agenda.SOURCE = None

# 2) 屬（母項＝摘要）、截止、進度；母項當前項、硬期限母項
BODY2 = """2026-10-20 待辦 M 模組 代號:m #T
2026-10-16 待辦 M1 焊接 工期3天 代號:m1 屬:m 進度:60% #T
2026-10-22 待辦 M2 測試 工期2天 代號:m2 屬:m 接:m1 截止:10-21 #T
2026-10-23 待辦 N 整合 工期2天 代號:n 接:m #T
2026-10-30 交件 Q 交付 代號:q #T
2026-10-28 待辦 Q1 報告 工期5天 代號:q1 屬:q 接:n #T
2026-10-29 待辦 S 單獨 截止:10-27 #U
"""
fresh(BODY2)
ev, bad = agenda.load()
eq("2 解析", bad, [])
rows = {key(r["e"]): r for r in agenda.plan(ev).values()}
eq("2 dep_problems", agenda.dep_problems(ev), [])
eq("2 M1 進度", rows["M1"]["e"]["pct"], 60)
eq("2 M 是摘要", rows["M"]["summary"], True)
eq("2 M es", rows["M"]["es"], D("2026-10-14"))
eq("2 M ef", rows["M"]["ef"], D("2026-10-22"))
eq("2 M push", rows["M"]["push"], D("2026-10-22"))
eq("2 M2 超過截止", rows["M2"]["dl_late"], 1)
eq("2 N es", rows["N"]["es"], D("2026-10-23"))
eq("2 N ef（跳補假）", rows["N"]["ef"], D("2026-10-27"))
eq("2 Q1 ef", rows["Q1"]["ef"], D("2026-11-03"))
eq("2 Q 硬期限母項不推", rows["Q"]["push"], None)
eq("2 Q late", rows["Q"]["late"], 2)
eq("2 Q slack", rows["Q"]["slack"], -2)
eq("2 Q1 slack", rows["Q1"]["slack"], -2)
eq("2 M slack", rows["M"]["slack"], -2)
eq("2 S 不在網路", "S" in rows, False)
eq("2 截止逾期清單", [(key(x[0]), x[3]) for x in agenda.overdue_deadlines(ev)], [("M2", 1), ("S", 2)])

eq("2 fmt", agenda.fmt_file(), 0)
txt = agenda.AGENDA.read_text(encoding="utf-8")
got = by_key(agenda.load()[0])
eq("2 M 行首跟子項", got["M"]["d"], D("2026-10-22"))
eq("2 Q 行首不動", got["Q"]["d"], D("2026-10-30"))
eq("2 冪等", agenda.settle(txt)[0], txt)
eq("2 母項紀錄", agenda.CHANGES.read_text(encoding="utf-8").count("子項日期變動，母項跟著改"), 1)

agenda.move("M1 焊接", "2026-10-21")  # 子項延誤 → 兄弟、母項、母項後項連鎖
got = by_key(agenda.load()[0])
eq("2 move 後 M2（平移 3 工作天，跳補假）", got["M2"]["d"], D("2026-10-28"))
eq("2 move 後 M 跟子項", got["M"]["d"], D("2026-10-28"))
eq("2 move 後 N（引擎順延）", got["N"]["d"], D("2026-10-30"))

# 3) 指令列：plugin 開場 hook 的呼叫方式（CLAUDE_PROJECT_DIR）、無檔建骨架、--json／--ics／--notify、預設紀錄位置
def cli(*args, cwd=None, proj=None):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("CLAUDE_PROJECT_DIR", None)
    if proj:
        env["CLAUDE_PROJECT_DIR"] = str(proj)
    r = subprocess.run([sys.executable, str(HERE / "agenda.py"), *args], cwd=str(cwd or proj), env=env,
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (r.stdout + r.stderr).strip()


outside = Path(tempfile.mkdtemp(prefix="agenda_out_"))
eq("3 非 vault 開場安靜", cli(cwd=outside), (0, ""))
eq("3 非 vault 明確指令報錯", cli("--check", cwd=outside)[0], 1)
v = vault()
eq("3 沒 agenda.md 開場安靜", cli(proj=v), (0, ""))
eq("3 沒 agenda.md 的 done 報錯", cli("done", "甲", proj=v)[0], 1)
rc, _ = cli("add", "2026-10-21 待辦 甲 工期2天 代號:a #P", proj=v)
eq("3 add 建骨架", (rc, (v / "wiki" / "agenda.md").is_file()), (0, True))
cli("add", "2026-10-23 交件 乙 接:a #P", proj=v)
cli("add", "2026-10-20 10:00 會議 週會 每週二 #P", proj=v)
eq("3 add 擋壞格式", cli("add", "2026-13-01 待辦 壞", proj=v)[0], 1)
eq("3 check 乾淨", "🟢 CLEAN" in cli("--check", proj=v)[1], True)
j = json.loads(cli("--json", proj=v)[1])
eq("3 json 事件數", len(j["events"]), 3)
eq("3 json 日曆", j["calendar"]["off"].get("2026-10-26"), "假日")
eq("3 json 來源", j["source"], "wiki/agenda.md")
cli("--ics", proj=v)
ics = (v / "agenda.ics").read_text(encoding="utf-8")
eq("3 ics 工期跨日", "DTSTART;VALUE=DATE:20261020" in ics and "DTEND;VALUE=DATE:20261022" in ics, True)
eq("3 ics 重複展開", ics.count("SUMMARY:會議 週會") >= 50, True)
rc, out = cli("--notify", "--days", "400", proj=v)
eq("3 notify", out.startswith("📅") and "交件 乙" in out, True)
cli("dur", "甲", "3", "--source", "agenda", proj=v)
eq("3 預設紀錄 wiki/agenda-changes.md", "|agenda|改工期|待辦｜甲|2天|3天|" in (v / "wiki" / "agenda-changes.md").read_text(encoding="utf-8"), True)
eq("3 交件不推", "2026-10-23 交件 乙" in (v / "wiki" / "agenda.md").read_text(encoding="utf-8"), True)

print(f"=== {cases - len(fails)}/{cases} 通過 ===")
for f in fails:
    print("   *** FAIL ***", f)
print("PASS" if not fails else "FAIL")
raise SystemExit(0 if not fails else 1)
