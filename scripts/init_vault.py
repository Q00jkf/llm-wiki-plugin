#!/usr/bin/env python3
"""建立 vault 薄骨架 —— 把 plugin 的 templates/vault/ 整棵複製到目標，代換 {{name}}／{{domain}}／{{today}}。

🔴 薄：不複製 skills/commands。系統由 llm-wiki plugin 提供，可 git pull 升級。
   （舊做法每個範本夾帶一整套 skills 拷貝，實測分岔成 18/18/30/31 —— 拷貝一定會漂。）

範本就是檔案：要改新 vault 長什麼樣，改 templates/vault/ 底下的檔，不改本腳本。
`.gitkeep` 只用來保住空資料夾。

用法：
    python init_vault.py <目標路徑> --name "名稱" --domain "領域" [--force]
    python init_vault.py <目標路徑> --dry-run
"""
import argparse
import sys
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "vault"
TEXT_EXT = {".md", ".json", ".txt", ".yaml", ".yml", ""}   # 只在這些檔做代換


def render(p: Path, subs: dict) -> bytes:
    data = p.read_bytes()
    if p.suffix.lower() in TEXT_EXT:
        s = data.decode("utf-8")
        for k, v in subs.items():
            s = s.replace("{{" + k + "}}", v)
        return s.encode("utf-8")
    return data


def main():
    ap = argparse.ArgumentParser(description="建立 vault 薄骨架")
    ap.add_argument("path", help="目標資料夾（不存在會建立）")
    ap.add_argument("--name", default="", help="vault 名稱")
    ap.add_argument("--domain", default="<一兩句話說明這個 vault 收什麼知識、給誰用>", help="一句話說明用途")
    ap.add_argument("--force", action="store_true", help="目標已有 wiki/ 時仍繼續（只覆寫範本檔，不刪既有頁）")
    ap.add_argument("--dry-run", action="store_true", help="只列出會建立什麼，不寫檔")
    args = ap.parse_args()

    root = Path(args.path).expanduser().resolve()
    subs = {"name": args.name or root.name, "domain": args.domain, "today": date.today().isoformat()}

    if not TEMPLATES.is_dir():
        print(f"🔴 找不到範本目錄：{TEMPLATES}")
        return 1
    if (root / "wiki").is_dir() and not args.force and not args.dry_run:
        print(f"🔴 {root} 已經有 wiki/ 了。要覆寫範本檔請加 --force（不會刪除既有的 wiki 頁）")
        return 1

    files = sorted(p for p in TEMPLATES.rglob("*") if p.is_file())
    dirs = sorted({p.parent.relative_to(TEMPLATES) for p in files} - {Path(".")})
    real = [p for p in files if p.name != ".gitkeep"]

    if args.dry_run:
        print(f"會建立於 {root}：")
        for d in dirs:
            print(f"  dir   {d.as_posix()}/")
        for p in real:
            print(f"  file  {p.relative_to(TEMPLATES).as_posix()}")
        print(f"\n共 {len(dirs)} 個資料夾 + {len(real)} 個檔案。")
        print("🔑 不複製 skills／commands —— 系統由 llm-wiki plugin 提供。")
        return 0

    for p in files:
        dst = root / p.relative_to(TEMPLATES)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if p.name == ".gitkeep" and any(x.name != ".gitkeep" for x in dst.parent.iterdir() if x.is_file()):
            continue
        dst.write_bytes(render(p, subs))

    print(f"✅ vault 骨架已建立：{root}")
    print(f"   {len(dirs)} 個資料夾 + {len(real)} 個檔案（不含 skills／commands 拷貝）")
    print("\n下一步：")
    print(f"  1. 編輯 {root / 'CLAUDE.md'} —— 填術語、工作習慣、資料夾用途（wiki/ops/ 模組空著沒關係）")
    print("  2. 素材放進 raw/，或 /wiki-repo add <外部專案路徑>")
    print("  3. /wiki-ingest raw/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
