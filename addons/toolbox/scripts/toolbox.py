#!/usr/bin/env python3
"""toolbox —— Obsidian 工具箱的說明檔檢查與相依檢查（2026-10-17）

為什麼：工具清單不手寫（使用者 10-17）——每個工具旁放一份 `<入口檔>.tool.json`，工具箱外掛
（.obsidian/plugins/toolbox/）自己掃出來。外掛直接用 JS 讀說明檔，同事沒裝 Python 也能看清單；
本腳本負責檢查說明檔寫得對不對（--check），以及 python 工具執行前的套件檢查（--deps，外掛呼叫）。

說明檔（放在工具同層，檔名＝入口檔名＋.tool.json）：
    {"name": "MPLogScope",              必填：工具箱上顯示的名稱
     "type": "python",                  必填：html／python／exe／obsidian（obsidian＝vault 裡的外掛，entry 寫外掛 id）
     "entry": "mplogscope.py",          必填：入口檔，相對說明檔所在資料夾（有 download 時可不在 vault）
     "desc": "一句話說明",              必填
     "category": "飛行日誌",            必填：工具箱分組
     "tags": ["產品A"],                   選填：產品 tag
     "run": "python mplogscope.py",     python 必填、exe 在 vault 內時必填：執行指令，cwd＝工具所在資料夾
     "deps": ["PySide6", "pyserial:serial"],  選填：必要套件，「pip 名[:import 名]」（import 名不同時才寫）
     "optional": ["folium"],            選填：選配套件（缺了照樣能開，只提示）
     "download": "https://…",           選填：檔案太大不進 git（exe）時的下載連結；工具箱顯示「下載」
     "version": "…",                    選填：版本或打包來源（commit sha）
     "note": "…",                       選填：使用注意（例：限公司內部）
     "author": "姓名 <email>",          選填
     "external": "C:/…/SG-AHRS-GUI",  選填：工具在 vault 外（只在擁有者電腦上）的資料夾絕對路徑；entry／run 相對這裡
     "owner": "名字 <email>",           有 external 必填：擁有者（git user.name <user.email>）
     "remote": "無（僅本機）",           有 external 必填：remote URL，或「無（僅本機）」
     "command": "pdf-translate:open"}   obsidian 選填：按下去執行的 Obsidian 指令 id；不寫＝打開該外掛設定頁
    obsidian 的說明檔不放外掛旁（.obsidian 不掃），放 raw/shared/RD/tools/；外掛沒裝＝問題。
    external 的資料夾這台沒有 → 不列（個人工具，別人看不到；有 download 才列成下載），不算問題（使用者 10-18）。

用法（vault 根目錄執行）：
    python scripts/toolbox.py                 # 列出全部工具
    python scripts/toolbox.py --check         # 檢查說明檔（有問題 exit 1）
    python scripts/toolbox.py --json          # 全部工具＋問題 JSON
    python scripts/toolbox.py --deps <說明檔>  # 這台 Python 缺哪些套件（JSON；外掛執行前呼叫）
"""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUFFIX = ".tool.json"
TYPES = ("html", "python", "exe", "obsidian")
REQUIRED = ("name", "type", "entry", "desc", "category")
LISTS = ("tags", "deps", "optional")
STRS = ("run", "author", "download", "version", "note", "external", "owner", "remote", "command")
SKIP = {".git", ".obsidian", ".trash", "node_modules"}  # 不掃的資料夾（外掛走 Obsidian vault，本來就不含 .obsidian）

sys.stdout.reconfigure(encoding="utf-8")


def find(root):
    """root 底下全部 *.tool.json（跳過 SKIP）。"""
    return sorted(p for p in root.rglob("*" + SUFFIX) if not SKIP & set(p.relative_to(root).parts))


def check_one(p, root):
    """讀一份說明檔 → (工具 dict 或 None, 問題清單)。外掛的 JS 檢查照這份寫。"""
    rel = p.relative_to(root).as_posix()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return None, [f"{rel}: 讀不到或不是 JSON（{e}）"]
    if not isinstance(d, dict):
        return None, [f"{rel}: 要是 JSON 物件"]
    bad = [f"{rel}: 缺 {k}" for k in REQUIRED if not (isinstance(d.get(k), str) and d[k].strip())]
    for k in LISTS:
        if k in d and not (isinstance(d[k], list) and all(isinstance(x, str) for x in d[k])):
            bad.append(f"{rel}: {k} 要是字串陣列")
    for k in STRS:
        if k in d and not isinstance(d[k], str):
            bad.append(f"{rel}: {k} 要是字串")
    if bad:
        return None, bad
    dl, ext = d.get("download", "").strip(), d.get("external", "").strip()
    plug = d["type"] == "obsidian"
    base = Path(ext) if ext else root / ".obsidian" / "plugins" if plug else p.parent
    if d["type"] not in TYPES:
        bad.append(f"{rel}: type 只能是 {'／'.join(TYPES)}（寫了 {d['type']}）")
    if p.name != d["entry"] + SUFFIX:
        bad.append(f"{rel}: 檔名要是 {d['entry']}{SUFFIX}（說明檔放在工具旁邊）")
    if dl and not dl.startswith("https://"):
        bad.append(f"{rel}: download 要是 https:// 連結")
    if ext and not base.is_absolute():
        bad.append(f"{rel}: external 要是絕對路徑")
    if ext:
        bad += [f"{rel}: 有 external 要寫 {k}" for k in ("owner", "remote") if not d.get(k, "").strip()]
    here = (base / d["entry"] / "manifest.json" if plug else base / d["entry"]).is_file() if base.is_absolute() else False
    if plug and not here:
        bad.append(f"{rel}: 外掛 {d['entry']} 沒裝（.obsidian/plugins/{d['entry']}/manifest.json 不存在）")
    elif not dl and not ext and not here:
        bad.append(f"{rel}: 入口檔 {d['entry']} 不存在（不進 git 的檔案要寫 download）")
    if d["type"] == "html" and not d["entry"].lower().endswith((".html", ".htm")):
        bad.append(f"{rel}: type html 的入口檔要是 .html")
    if (d["type"] == "python" or (d["type"] == "exe" and not dl)) and not d.get("run", "").strip():
        bad.append(f"{rel}: type {d['type']} 要寫 run（執行指令）")
    if bad:
        return None, bad
    entry = (base / d["entry"]).as_posix() if ext else (base / d["entry"]).relative_to(root).as_posix()
    return {**d, **{k: d.get(k, []) for k in LISTS}, "spec": rel, "path": entry, "here": here}, []


def scan(root=ROOT):
    tools, problems = [], []
    for p in find(root):
        t, bad = check_one(p, root)
        problems += bad
        if t and (t["here"] or t.get("download")):  # 個人工具（external 不在這台、沒 download）不列
            tools.append(t)
    tools.sort(key=lambda t: (t["category"], t["name"]))
    return tools, problems


ZONES = ("tools", "gui tools")  # 放工具的區（資料夾名，不分大小寫）
IGNORE = ".toolbox-ignore"  # 同層「不是工具」清單：一行一個檔名或資料夾名，# 後為註解
GUI_RE = re.compile(r"^\s*(?:import|from)\s+(?:tkinter|PySide[26]|PyQt[56]|streamlit|gradio|dearpygui|wx)\b", re.M)


def ignored(d):
    """d/.toolbox-ignore 列的名字（集合）。"""
    p = d / IGNORE
    if not p.is_file():
        return set()
    return {s.split("#")[0].strip() for s in p.read_text(encoding="utf-8-sig", errors="replace").splitlines()} - {""}


def is_gui(p):
    try:
        return bool(GUI_RE.search(p.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return False


def unregistered(root=ROOT):
    """疑似工具卻沒說明檔（使用者 10-19「有人做了工具就提醒要不要進工具箱」）：
    raw/ 往下三層內的 tools/ 直接放的 html 與 GUI 程式；GUI tools/ 底下每個子資料夾（裡面有任一份說明檔就算登記）。
    只看三層：更深的是原廠 SDK／ArduPilot 自帶的 tools/，不是我們的；也讓開場守門不用掃整個 raw（全掃 10 秒）。
    不是工具的寫進同層 .toolbox-ignore。"""
    out = []
    zones = {p for pat in ("*", "*/*", "*/*/*") for p in (root / "raw").glob(pat)
             if p.is_dir() and p.name.lower() in ZONES}
    for d in sorted(zones):
        skip = ignored(d)
        if d.name.lower() == "tools":
            for f in sorted(d.iterdir()):
                if f.is_file() and f.name not in skip and not (d / (f.name + SUFFIX)).is_file() and (
                        f.suffix.lower() in (".html", ".htm") or (f.suffix == ".py" and is_gui(f))):
                    out.append(f)
        else:
            out += [s for s in sorted(d.iterdir()) if s.is_dir() and s.name not in skip and not find(s)]
    return [p.relative_to(root).as_posix() for p in out]


def split_dep(s):
    """「pip 名[:import 名]」→ (pip 名, import 名)。"""
    pip, _, mod = s.partition(":")
    return pip.strip(), (mod or pip).strip()


def missing(deps, find_spec=importlib.util.find_spec):
    """這台 Python 找不到的套件（回 pip 名）。只找不 import，不會跑套件的初始化。"""
    out = []
    for pip, mod in map(split_dep, deps):
        try:
            ok = find_spec(mod) is not None
        except (ImportError, ValueError):
            ok = False
        if not ok:
            out.append(pip)
    return out


def deps_report(spec, root=ROOT):
    t, bad = check_one((root / spec).resolve() if not Path(spec).is_absolute() else Path(spec), root)
    if not t:
        return {"ok": False, "problems": bad}
    req, opt = missing(t["deps"]), missing(t["optional"])
    return {"ok": not req, "python": sys.version.split()[0], "missing": req, "optional_missing": opt,
            "pip": f"python -m pip install {' '.join(req + opt)}" if req or opt else ""}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="檢查說明檔，有問題 exit 1")
    ap.add_argument("--json", action="store_true", help="全部工具＋問題輸出 JSON")
    ap.add_argument("--deps", metavar="說明檔", help="這台 Python 缺哪些套件（JSON）")
    a = ap.parse_args()
    if a.deps:
        print(json.dumps(deps_report(a.deps), ensure_ascii=False))
        return 0
    tools, problems = scan()
    if a.json:
        print(json.dumps({"tools": tools, "problems": problems}, ensure_ascii=False, indent=1))
        return 0
    if not a.check:
        cat = None
        for t in tools:
            if t["category"] != cat:
                cat = t["category"]
                print(f"## {cat}")
            print(f"   [{t['type']}] {t['name']}  {' '.join('#' + x for x in t['tags'])}  → {t['path']}".rstrip())
    print(f"=== toolbox：{len(tools)} 個工具，{len(problems)} 個問題 ===")
    for s in problems:
        print(f"   🟡 {s}")
    for s in unregistered():  # 只提醒、不算問題（開場由 rules-doctor R12 報）
        print(f"   💡 {s} 還沒進工具箱（要放就寫 <入口檔>{SUFFIX}；不是工具寫進同層 {IGNORE}）")
    if a.check:
        print("verdict : " + ("🟢 CLEAN" if not problems else f"🟡 {len(problems)} 項"))
    return 1 if a.check and problems else 0


if __name__ == "__main__":
    sys.exit(main())
