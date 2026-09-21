#!/usr/bin/env python3
"""開一個新工作資料夾：複製 Templates/_folder-template/ → raw/<name>/，並在 wiki 登錄。

做五件事（缺一就會出現「有夾沒頁」「有頁沒 log」的斷點）：
  1. raw/<name>/            ← 複製資料夾骨架（優先用 vault 自己的 Templates/，沒有才用 plugin 的）
  2. raw/<name>/_README.md  ← 執行節點，代換 {{folder}}/{{date}}/{{count}}/{{tree}}
  3. wiki/topics/<name>.md  ← topic stub（status: initializing）
  4. wiki/index.md          ← ## Topics 底下加一列
  5. wiki/log.md            ← 最上方加一則 `## YYYY-MM-DD | new | <name>`

🔴 不改 CLAUDE.md —— 「資料夾用途」表要人自己補（本腳本只提醒）。
   理由：兩個成熟 vault 都因為建夾流程漏了這一步，盤點題長期少報。

用法：
    python new_folder.py <name> [--under raw] [--sub a,b,c] [--dry-run]
"""
import argparse
import os
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib.vaultpaths import find_vault_root  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_TPL = Path(__file__).resolve().parent.parent / "templates" / "vault" / "Templates" / "_folder-template"
TPL_REL = Path("Templates") / "_folder-template"
TEXT_EXT = {".md", ".json", ".txt", ".yaml", ".yml", ""}
SKIP_TOP = {"README.md"}          # 模板夾自己的說明檔，不複製
NOT_COUNTED = {"_README.md", "_manifest.json", ".gitkeep"}


def find_template(root: Path):
    for cand in (root / TPL_REL, PLUGIN_TPL):
        if (cand / "_README.md").is_file():
            return cand
    return None


def render(p: Path, subs: dict) -> bytes:
    data = p.read_bytes()
    if p.suffix.lower() not in TEXT_EXT:
        return data
    s = data.decode("utf-8")
    for k, v in subs.items():
        s = s.replace("{{" + k + "}}", v)
    return s.encode("utf-8")


def tree_text(target: Path) -> str:
    lines = [target.name + "/"]
    for d in sorted(p for p in target.rglob("*") if p.is_dir()):
        depth = len(d.relative_to(target).parts) - 1
        lines.append("  " * depth + "  " + d.name + "/")
    return "\n".join(lines)


def count_files(target: Path) -> int:
    return sum(1 for p in target.rglob("*") if p.is_file() and p.name not in NOT_COUNTED and not p.name.startswith("."))


def topic_stub(name: str, under: str, today: str) -> str:
    return (
        "---\n"
        "type: topic\n"
        f'title: "{name}"\n'
        f"created: {today}\n"
        "status: initializing\n"
        "sources: []\n"
        "---\n\n"
        f"# {name}\n\n"
        f"> 尚未 ingest。素材放進 `{under}/{name}/` 後執行 `/wiki-ingest {under}/{name}/`。\n"
        f"> 進度看 `{under}/{name}/_README.md`（執行節點），不看本頁。\n\n"
        "## 概述\n\n"
        "## 相關文件\n\n"
        "## 相關主題\n"
    )


def add_index_row(index: Path, row: str, name: str, dry: bool) -> str:
    if not index.is_file():
        return "缺 wiki/index.md，略過"
    text = index.read_text(encoding="utf-8")
    if row in text:
        return "已有該列，略過"
    lines = text.split("\n")
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "## Topics")
    except StopIteration:
        lines += ["", "## Topics", "", row]
    else:
        end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        block = lines[start + 1:end]
        if any(l.lstrip().startswith("|") for l in block):      # 該區塊已是表格 → 插表格列
            header = next(l for l in block if l.lstrip().startswith("|"))
            ncol = max(2, header.strip().strip("|").count("|") + 1)   # 跟既有表格欄數對齊
            cells = [name, f"[[topics/{name}]]"] + [""] * (ncol - 2)
            row = "| " + " | ".join(cells) + " |"
            last_tbl = max(i for i in range(start + 1, end) if lines[i].lstrip().startswith("|"))
            end = last_tbl + 1
        lines.insert(end, row)
        if end == start + 1:
            lines.insert(end, "")
    if not dry:
        index.write_text("\n".join(lines), encoding="utf-8")
    return "已加一列到 ## Topics"


def prepend_log(log: Path, entry: str, dry: bool) -> str:
    if not log.is_file():
        return "缺 wiki/log.md，略過"
    lines = log.read_text(encoding="utf-8").split("\n")
    pos = 0
    if lines and lines[0].strip() == "---":
        pos = next((i + 1 for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
    pos = next((i for i in range(pos, len(lines)) if lines[i].startswith("## ")), len(lines))
    lines[pos:pos] = entry.split("\n") + [""]
    if not dry:
        log.write_text("\n".join(lines), encoding="utf-8")
    return "已加到最上方"


def main():
    ap = argparse.ArgumentParser(description="開新工作資料夾並在 wiki 登錄")
    ap.add_argument("name", help="資料夾名稱（也是 topic 名）")
    ap.add_argument("--under", default="raw", help="放在哪個上層目錄（預設 raw）")
    ap.add_argument("--sub", default="", help="額外子資料夾，逗號分隔")
    ap.add_argument("--dry-run", action="store_true", help="只列出會做什麼，不寫檔")
    args = ap.parse_args()

    root = find_vault_root(Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
    if not root:
        print("🔴 找不到 vault 根（需有 wiki/ 或 raw/.manifest.json）")
        return 1
    name = args.name.strip().strip("/\\")
    if not name or any(c in name for c in '/\\:*?"<>|'):
        print(f"🔴 名稱不合法：{args.name!r}")
        return 1

    tpl = find_template(root)
    if not tpl:
        print(f"🔴 找不到資料夾模板：{root / TPL_REL} 或 {PLUGIN_TPL}")
        return 1
    target = root / args.under / name
    if target.exists():
        print(f"🔴 {target} 已存在，不覆寫。要重建請先手動移走。")
        return 1

    today = date.today().isoformat()
    subs_extra = [s.strip().strip("/\\") for s in args.sub.split(",") if s.strip()]
    topic = root / "wiki" / "topics" / f"{name}.md"
    row = f"- [[topics/{name}]] — `{args.under}/{name}/` 建立 {today}，尚未 ingest"
    entry = (
        f"## {today} | new | {name}\n"
        f"- 資料夾：`{args.under}/{name}/`（模板：`{tpl.relative_to(root).as_posix() if tpl.is_relative_to(root) else 'plugin'}`）\n"
        f"- 主題頁：[[topics/{name}]]（status: initializing）\n"
        f"- 執行節點：`{args.under}/{name}/_README.md`"
    )
    dry = args.dry_run
    tag = "[dry-run] " if dry else ""

    print(f"{tag}vault：{root}")
    print(f"{tag}模板：{tpl}")
    print(f"{tag}目標：{target}")

    files = [p for p in tpl.rglob("*") if p.is_file() and not (p.parent == tpl and p.name in SKIP_TOP)]
    if not dry:
        target.mkdir(parents=True)
        for p in files:
            dst = target / p.relative_to(tpl)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if p.name == "_README.md":
                continue
            shutil.copyfile(p, dst)
        for s in subs_extra:
            d = target / s
            d.mkdir(parents=True, exist_ok=True)
            (d / ".gitkeep").touch()
        subs = {"folder": name, "date": today, "name": name, "today": today,
                "count": str(count_files(target)), "tree": tree_text(target)}
        (target / "_README.md").write_bytes(render(tpl / "_README.md", subs))
    for p in files:
        print(f"{tag}  file  {p.relative_to(tpl).as_posix()}")
    for s in subs_extra:
        print(f"{tag}  dir   {s}/ (.gitkeep)")

    if topic.exists():
        print(f"{tag}⚠️ {topic.relative_to(root).as_posix()} 已存在，不覆寫")
    else:
        if not dry:
            topic.parent.mkdir(parents=True, exist_ok=True)
            topic.write_text(topic_stub(name, args.under, today), encoding="utf-8")
        print(f"{tag}  topic wiki/topics/{name}.md")
    print(f"{tag}  index.md：{add_index_row(root / 'wiki' / 'index.md', row, name, dry)}")
    print(f"{tag}  log.md：{prepend_log(root / 'wiki' / 'log.md', entry, dry)}")

    print(f"\n{'會' if dry else '已'}建立 {args.under}/{name}/。")
    print(f"🔴 請手動把 `{args.under}/{name}/` 加進 CLAUDE.md「資料夾用途」表（本腳本不動 CLAUDE.md）。")
    print(f"   下一步：素材放進去 → /wiki-ingest {args.under}/{name}/ → 更新 _README.md ④ 進度表")
    return 0


if __name__ == "__main__":
    sys.exit(main())
