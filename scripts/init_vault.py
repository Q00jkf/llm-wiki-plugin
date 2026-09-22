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
    ap.add_argument("--domain", default="<一兩句話說明這個 vault 管什麼對象（產品線／專案／客戶）、給誰用>", help="一句話說明用途")
    ap.add_argument("--force", action="store_true", help="目標已有 wiki/ 時仍繼續：只補缺少的範本檔，既有檔一律跳過")
    ap.add_argument("--dry-run", action="store_true", help="只列出會建立什麼，不寫檔")
    args = ap.parse_args()

    root = Path(args.path).expanduser().resolve()
    subs = {"name": args.name or root.name, "domain": args.domain, "today": date.today().isoformat()}

    if not TEMPLATES.is_dir():
        print(f"🔴 找不到範本目錄：{TEMPLATES}")
        return 1
    existing_vault = (root / "wiki").is_dir()
    if existing_vault and not args.force and not args.dry_run:
        print(f"🔴 {root} 已經有 wiki/ 了。要補齊缺少的範本檔請加 --force（既有檔一律跳過，不覆寫）")
        return 1

    files = sorted(p for p in TEMPLATES.rglob("*") if p.is_file())
    dirs = sorted({p.parent.relative_to(TEMPLATES) for p in files} - {Path(".")})
    real = [p for p in files if p.name != ".gitkeep"]
    # 🔴 既有檔永遠不碰：CLAUDE.md／log.md／rulings.md 是使用者累積的裁示與日誌，覆寫＝無聲清空。
    # （#33：dry-run 曾把 19 個既有檔全標「會建立」，--force 真的會蓋掉 log.md）
    exists = {p for p in real if (root / p.relative_to(TEMPLATES)).exists()}
    missing = [p for p in real if p not in exists]

    if args.dry_run:
        print(f"{'會補齊' if existing_vault else '會建立'}於 {root}：")
        for d in dirs:
            print(f"  dir   {d.as_posix()}/")
        for p in real:
            rel = p.relative_to(TEMPLATES).as_posix()
            print(f"  skip  {rel}   ⚠️ 已存在，跳過" if p in exists else f"  file  {rel}")
        tail = f"；{len(exists)} 個既有檔不動。" if exists else "。"
        print(f"\n共 {len(dirs)} 個資料夾 + {len(missing)} 個新檔{tail}")
        if existing_vault and not args.force:
            print("🔴 目標已有 wiki/，實際執行需加 --force（只補缺的，不覆寫）。")
        print("🔑 不複製 skills／commands —— 系統由 llm-wiki plugin 提供。")
        return 0

    for p in files:
        dst = root / p.relative_to(TEMPLATES)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            continue
        if p.name == ".gitkeep" and any(x.name != ".gitkeep" for x in dst.parent.iterdir() if x.is_file()):
            continue
        dst.write_bytes(render(p, subs))

    print(f"✅ vault 骨架已{'補齊' if existing_vault else '建立'}：{root}")
    print(f"   {len(dirs)} 個資料夾 + {len(missing)} 個新檔（不含 skills／commands 拷貝）")
    if exists:
        names = "、".join(p.relative_to(TEMPLATES).as_posix() for p in sorted(exists)[:6])
        print(f"   既有檔 {len(exists)} 個未動：{names}{'…' if len(exists) > 6 else ''}")
    print("\n下一步：")
    print(f"  1. 編輯 {root / 'CLAUDE.md'} —— 填術語、工作習慣、資料夾用途（wiki/ops/ 模組空著沒關係）")
    print("  2. 素材放進 raw/，或 /wiki-repo add <外部專案路徑>")
    print("  3. /wiki-ingest raw/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
