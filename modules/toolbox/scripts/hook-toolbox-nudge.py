#!/usr/bin/env python3
"""hook-toolbox-nudge —— 在 raw/ 新建疑似工具時提醒「要不要放進工具箱」（PostToolUse Write，2026-10-19）

為什麼：使用者 10-19「有人創建了類似的工具，就提醒他是否要綁到工具箱」。IMU_規格比對 做完沒寫說明檔，
工具箱就看不到；規則寫在 CLAUDE.md，這支讓寫檔當下就看得到，tools／GUI tools 裡漏網的由 rules-doctor R12（toolbox.unregistered）開場補抓。
🔴 覆寫不提醒靠 tool_response.type == "update"；欄位不存在就照樣提醒（寧可多提醒）。

觸發：Write 新建（不是覆寫）raw/ 底下的 .html／.htm，或 import 了 GUI 套件的 .py；
略過：旁邊已有 <檔名>.tool.json、上層資料夾已有說明檔（屬於已登記工具的一部分；tools／GUI tools 區本身不算）、被 .toolbox-ignore 列掉。
只提醒不擋：輸出 additionalContext 給 Claude，exit 一律 0。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import toolbox  # noqa: E402


def nudge(path, root=toolbox.ROOT):
    """要提醒就回提醒文字，否則 None。"""
    p = Path(path).resolve()
    try:
        rel = p.relative_to(root)
    except ValueError:
        return None
    if rel.parts[:1] != ("raw",) or toolbox.SKIP & set(rel.parts) or not p.is_file():
        return None
    if not (p.suffix.lower() in (".html", ".htm") or (p.suffix == ".py" and toolbox.is_gui(p))):
        return None
    if (p.parent / (p.name + toolbox.SUFFIX)).is_file():
        return None
    for a in p.parents:
        if a == root:
            break
        if a != p.parent and a.name.lower() not in toolbox.ZONES and any(a.glob("*" + toolbox.SUFFIX)):
            return None  # 已登記工具的子模組
        if p.relative_to(a).parts[0] in toolbox.ignored(a):
            return None
    return (f"🧰 剛建立的 {rel.as_posix()} 看起來像給人用的工具（GUI／單檔 HTML）。"
            "做完後問使用者要不要放進 Obsidian 工具箱：要就在入口檔旁寫 "
            f"{p.name}{toolbox.SUFFIX}（格式見 scripts/toolbox.py 開頭，寫完跑 python scripts/toolbox.py --check）；"
            f"不是工具（報告、筆記、子模組）就在同層 {toolbox.IGNORE} 加一行檔名，之後不再提醒。（CLAUDE.md 工具箱規則，使用者 2026-10-19）")


def main():
    try:
        d = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    resp = d.get("tool_response")
    if isinstance(resp, dict) and resp.get("type") == "update":
        return 0  # 覆寫既有檔不重複提醒
    msg = nudge((d.get("tool_input") or {}).get("file_path", ""))
    if msg:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}},
                         ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # 提醒用的 hook 不可讓寫檔流程出錯
        sys.exit(0)
