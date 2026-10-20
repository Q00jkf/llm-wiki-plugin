"""toolbox（工具箱說明檔檢查）回歸測試 —— 跑法：python scripts/test_toolbox.py

假工具寫在暫存目錄，不碰 vault；最後再對 vault 實際的說明檔跑一次（要 🟢）。
外掛（.obsidian/plugins/toolbox/main.js）的 JS 檢查照 toolbox.check_one 寫，改規則兩邊一起改。
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import toolbox  # noqa: E402

fails, cases = [], 0


def eq(name, got, want):
    global cases
    cases += 1
    if got != want:
        fails.append(f"{name}: got {got} want {want}")


root = Path(tempfile.mkdtemp(prefix="toolbox_"))


def put(rel, obj=None, text=None):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text if text is not None else json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return p


OK = {"name": "工具A", "type": "html", "entry": "a.html", "desc": "說明", "category": "分類"}
put("t/a.html", text="<html></html>")
put("t/a.html.tool.json", OK)
put("t/b.py", text="")
put("t/b.py.tool.json", {**OK, "name": "工具B", "type": "python", "entry": "b.py", "run": "python b.py", "deps": ["numpy"], "author": "某人"})
put(".obsidian/x.html.tool.json", {**OK, "entry": "x.html"})  # SKIP 資料夾不掃

tools, problems = toolbox.scan(root)
eq("1 正常兩個", [t["name"] for t in tools], ["工具A", "工具B"])
eq("1 沒問題", problems, [])
eq("1 path＝vault 相對入口", tools[0]["path"], "t/a.html")
eq("1 spec＝說明檔", tools[0]["spec"], "t/a.html.tool.json")
eq("1 tags／deps 預設空陣列", (tools[0]["tags"], tools[0]["deps"]), ([], []))
eq("1 python 帶 run／deps", (tools[1]["run"], tools[1]["deps"]), ("python b.py", ["numpy"]))

for rel, obj, text, want in (
    ("e/bad.html.tool.json", None, "{不是 json", "不是 JSON"),
    ("e/arr.html.tool.json", None, "[]", "要是 JSON 物件"),
    ("e/c.html.tool.json", {k: v for k, v in OK.items() if k != "desc"} | {"entry": "c.html"}, None, "缺 desc"),
    ("e/d.html.tool.json", {**OK, "entry": "d.html", "type": "bat"}, None, "type 只能是"),
    ("e/wrong.tool.json", {**OK, "entry": "a.html"}, None, "檔名要是 a.html.tool.json"),
    ("e/f.html.tool.json", {**OK, "entry": "f.html"}, None, "入口檔 f.html 不存在"),
    ("e/g.py.tool.json", {**OK, "entry": "g.py"}, None, "type html 的入口檔要是 .html"),
    ("e/h.exe.tool.json", {**OK, "entry": "h.exe", "type": "exe"}, None, "要寫 run"),
    ("e/i.html.tool.json", {**OK, "entry": "i.html", "tags": "產品A"}, None, "tags 要是字串陣列"),
):
    for ent in ("a.html", "g.py", "h.exe", "i.html", "c.html", "d.html"):
        if not (root / "e" / ent).exists():
            put(f"e/{ent}", text="")
    p = put(rel, obj, text)
    t, bad = toolbox.check_one(p, root)
    eq(f"2 {rel} 擋下", t, None)
    eq(f"2 {rel} 訊息", any(want in s for s in bad), True)

tools, problems = toolbox.scan(root)
eq("3 壞的不列、好的照列", [t["name"] for t in tools], ["工具A", "工具B"])
eq("3 問題數", len(problems), 9)

# 5) 第二期：download（exe 不進 git）、deps「pip 名[:import 名]」、缺套件判斷
DL = {**OK, "type": "exe", "entry": "big.exe", "download": "https://drive.google.com/x"}
t, bad = toolbox.check_one(put("d/big.exe.tool.json", DL), root)
eq("5 download：入口檔不在 vault 也可、exe 不用 run", (bool(t), bad), (True, []))
t, bad = toolbox.check_one(put("d/h1.exe.tool.json", {**DL, "entry": "h1.exe", "download": "http://x"}), root)
eq("5 download 要 https", any("https://" in s for s in bad), True)
t, bad = toolbox.check_one(put("d/c.py.tool.json", {**OK, "type": "python", "entry": "c.py", "run": "python c.py", "optional": "folium"}), root)
eq("5 optional 要是陣列", any("optional 要是字串陣列" in s for s in bad), True)
eq("5 split_dep", [toolbox.split_dep(x) for x in ("numpy", "pyserial:serial")], [("numpy", "numpy"), ("pyserial", "serial")])
have = {"numpy", "serial"}
fake = lambda m: object() if m in have else None  # noqa: E731
eq("5 missing 回 pip 名、用 import 名找", toolbox.missing(["numpy", "pyserial:serial", "pywin32:win32gui", "PySide6"], fake), ["pywin32", "PySide6"])
eq("5 find_spec 丟例外＝缺", toolbox.missing(["a.b"], lambda m: (_ for _ in ()).throw(ImportError())), ["a.b"])
put("p/run.py", text="")
put("p/run.py.tool.json", {**OK, "type": "python", "entry": "run.py", "run": "python run.py", "deps": ["json"], "optional": ["沒有這個套件xyz"]})
rep = toolbox.deps_report("p/run.py.tool.json", root)
eq("5 deps_report", (rep["ok"], rep["missing"], rep["optional_missing"], rep["pip"]), (True, [], ["沒有這個套件xyz"], "python -m pip install 沒有這個套件xyz"))
eq("5 deps_report 壞說明檔", toolbox.deps_report("e/c.html.tool.json", root)["ok"], False)

# 6) external：工具在 vault 外（只在擁有者電腦上）
ext = Path(tempfile.mkdtemp(prefix="toolbox_ext_"))
(ext / "gui.py").write_text("", encoding="utf-8")
EX = {**OK, "type": "python", "entry": "gui.py", "run": "python gui.py", "external": str(ext), "owner": "某人 <a@b>", "remote": "無（僅本機）"}
t, bad = toolbox.check_one(put("x/gui.py.tool.json", EX), root)
eq("6 external 在這台：列出、here、path＝絕對", (bad, t["here"], t["path"]), ([], True, (ext / "gui.py").as_posix()))
t, bad = toolbox.check_one(put("x/gui.py.tool.json", {**EX, "external": str(ext / "沒有")}), root)
eq("6 external 這台沒有：檢查通過、不算問題", (bad, t["here"]), ([], False))
t, bad = toolbox.check_one(put("x/gui.py.tool.json", {**EX, "external": "相對/路徑"}), root)
eq("6 external 要絕對路徑", any("external 要是絕對路徑" in s for s in bad), True)
t, bad = toolbox.check_one(put("x/gui.py.tool.json", {k: v for k, v in EX.items() if k != "remote"}), root)
eq("6 external 缺 remote", any("要寫 remote" in s for s in bad), True)
put("y/gui.py.tool.json", {**EX, "external": str(ext / "沒有")})
put("z/gui.py.tool.json", {**EX, "external": str(ext / "沒有"), "download": "https://drive.google.com/y"})
names = [t["spec"] for t in toolbox.scan(root)[0]]
eq("6 scan：別台的個人工具不列、有 download 照列", ("y/gui.py.tool.json" in names, "z/gui.py.tool.json" in names), (False, True))
eq("6 一般工具 here", toolbox.check_one(root / "t/a.html.tool.json", root)[0]["here"], True)

# 7) obsidian：vault 裡的外掛（說明檔不放外掛旁，entry＝外掛 id）
put(".obsidian/plugins/fp/manifest.json", {"id": "fp"})
OB = {**OK, "type": "obsidian", "entry": "fp", "command": "fp:open"}
t, bad = toolbox.check_one(put("o/fp.tool.json", OB), root)
eq("7 外掛有裝：列出、path、不用 run", (bad, t["here"], t["path"]), ([], True, ".obsidian/plugins/fp"))
t, bad = toolbox.check_one(put("o/nope.tool.json", {**OB, "entry": "nope"}), root)
eq("7 外掛沒裝＝問題", any("外掛 nope 沒裝" in s for s in bad), True)

# 8) 未登記提醒（使用者 10-19）：unregistered（開場 R12）＋hook-toolbox-nudge（寫檔當下）
import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location("nudge", HERE / "hook-toolbox-nudge.py")
nudge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nudge)
put("raw/RD/tools/ok.html", text="")
put("raw/RD/tools/ok.html.tool.json", {**OK, "entry": "ok.html"})
put("raw/RD/tools/new.html", text="")
put("raw/RD/tools/gui.py", text="import json\nfrom PySide6 import QtWidgets\n")
put("raw/RD/tools/cli.py", text="import json\n")
put("raw/RD/tools/plan.md", text="")
put("raw/RD/GUI tools/A/main.py", text="import tkinter as tk\n")
put("raw/RD/GUI tools/B/sub/main.py.tool.json", {})  # 子資料夾任一層有說明檔＝已登記
put("raw/RD/GUI tools/Doc/x.html", text="")
put("raw/RD/GUI tools/.toolbox-ignore", text="# 註解\nDoc   # 只是文件\n")
put("raw/a/b/c/d/tools/deep.html", text="")  # 超過三層：原廠 SDK 自帶的 tools/ 不管
eq("8 unregistered", toolbox.unregistered(root),
   ["raw/RD/GUI tools/A", "raw/RD/tools/gui.py", "raw/RD/tools/new.html"])
eq("8 ignored 去註解", toolbox.ignored(root / "raw/RD/GUI tools"), {"Doc"})
put("raw/RD/tools/.toolbox-ignore", text="new.html\n")
eq("8 ignore 後不報", toolbox.unregistered(root), ["raw/RD/GUI tools/A", "raw/RD/tools/gui.py"])
put("raw/n/report.html", text="")
put("raw/n/done.html", text="")
put("raw/n/done.html.tool.json", {})
put("raw/n/T/main.py.tool.json", {})
put("raw/n/T/lib/w.py", text="from PyQt5 import QtCore\n")
put("raw/n/lib.py", text="import os\n")
put("wiki/x.html", text="")
hit = lambda rel: nudge.nudge(root / rel, root) is not None  # noqa: E731
eq("8 hook：新 html 提醒", hit("raw/n/report.html"), True)
eq("8 hook：已有說明檔不提醒", hit("raw/n/done.html"), False)
eq("8 hook：已登記工具的子模組不提醒", hit("raw/n/T/lib/w.py"), False)
eq("8 hook：非 GUI 的 py 不提醒", hit("raw/n/lib.py"), False)
eq("8 hook：raw 以外不提醒", hit("wiki/x.html"), False)
eq("8 hook：ignore 的資料夾不提醒", hit("raw/RD/GUI tools/Doc/x.html"), False)
eq("8 hook：GUI tools 新 GUI 提醒", hit("raw/RD/GUI tools/A/main.py"), True)
eq("8 hook：ignore 的檔不提醒", hit("raw/RD/tools/new.html"), False)
put("raw/RD/tools/proj/index.html", text="")
eq("8 hook：tools 區的新專案資料夾照樣提醒", hit("raw/RD/tools/proj/index.html"), True)
(root / "raw/RD/tools/.toolbox-ignore").write_bytes("\ufeffgui.py\n".encode("utf-8"))  # PowerShell 5.1 寫的 UTF-8 帶 BOM
eq("8 ignore 檔有 BOM 也認得第一行", "raw/RD/tools/gui.py" in toolbox.unregistered(root), False)
(root / "raw/RD/tools/.toolbox-ignore").write_bytes("gui.py # 測試\n".encode("cp950"))
eq("8 ignore 檔不是 UTF-8 不會掛", toolbox.ignored(root / "raw/RD/tools") >= {"gui.py"}, True)

tools, problems = toolbox.scan()
eq("4 vault 實際說明檔沒問題", problems, [])
rd = toolbox.ROOT / "raw" / "shared" / "RD" / "tools"  # 第一批：這夾每支 HTML 都要有說明檔（增刪工具不用改這裡）
eq("4 RD/tools 每支 html 都進工具箱", sorted(t["entry"] for t in tools if t["path"].startswith("raw/shared/RD/tools/")),
   sorted(p.name for p in rd.glob("*.html")))

print(f"=== {cases - len(fails)}/{cases} 通過 ===")
for f in fails:
    print("   *** FAIL ***", f)
print("PASS" if not fails else "FAIL")
raise SystemExit(0 if not fails else 1)
