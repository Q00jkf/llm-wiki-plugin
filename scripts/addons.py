#!/usr/bin/env python3
"""可選裝模組（Obsidian 外掛＋它用的腳本）：列出、安裝、更新、檢查。

正本在 plugin 的 addons/<id>/；vault 裡的是安裝出來的複本。裝不裝由使用者選，
沒裝的模組不檢查、不提醒。

用法：
    python addons.py                    # 列出所有模組與本 vault 的狀態
    python addons.py install <id>...    # 安裝（已存在且被改過 → 停下，要 --force）
    python addons.py update [<id>...]   # 更新已裝的（不給 id＝全部已裝）
    python addons.py check [--quiet]    # 只報已裝且「需更新／vault 有改動」的（開場與 doctor 用）

模組結構：addons/<id>/addon.json、obsidian/（→ .obsidian/plugins/<id>/）、scripts/（→ scripts/）。
安裝紀錄：.obsidian/plugins/<id>/.llm-wiki-addon.json（版本＋每個檔安裝當下的 hash），
用來分辨「plugin 出新版」與「有人在 vault 裡改了複本」—— 後者不能直接覆蓋。
addon.json 的 local 列出 vault 自己的檔（設定、快取），安裝與更新永遠不碰。
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib.filehash import md5_of  # noqa: E402
from _lib.vaultpaths import find_vault_root  # noqa: E402

MODULES = Path(__file__).resolve().parent.parent / "addons"
RECORD = ".llm-wiki-addon.json"

UP_TO_DATE, OUTDATED, MODIFIED, ABSENT = "最新", "需更新", "vault 有改動", "未裝"


def available():
    out = {}
    if MODULES.is_dir():
        for d in sorted(MODULES.iterdir()):
            f = d / "addon.json"
            if f.is_file():
                out[d.name] = json.loads(f.read_text(encoding="utf-8"))
    return out


def targets(mid, meta):
    """[(plugin 內來源, vault 相對路徑)]"""
    src = MODULES / mid
    pairs = [(p, f".obsidian/plugins/{mid}/{p.name}") for p in sorted((src / "obsidian").iterdir()) if p.is_file()]
    pairs += [(src / "scripts" / s, f"scripts/{s}") for s in meta.get("scripts", [])]
    return pairs


def _record(root, mid):
    p = root / ".obsidian" / "plugins" / mid / RECORD
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def status(root, mid, meta):
    if not (root / ".obsidian" / "plugins" / mid / "manifest.json").is_file():
        return {"id": mid, "state": ABSENT, "files": [], "missing_requires": []}
    rec = _record(root, mid) or {}
    recorded = rec.get("files", {})
    changed, stale = [], []
    for src, rel in targets(mid, meta):
        dst = root / rel
        have = md5_of(dst) if dst.is_file() else None
        want = md5_of(src)
        if have == want:
            continue
        # 沒紀錄時無從判斷是誰改的 → 當作改動，寧可停下也不要蓋掉別人的修改
        if have is not None and have != recorded.get(rel):
            changed.append(rel)
        else:
            stale.append(rel)
    state = MODIFIED if changed else OUTDATED if stale else UP_TO_DATE
    req = [r for r in meta.get("requires", []) if not (root / r).exists()]
    return {"id": mid, "state": state, "files": changed or stale, "missing_requires": req,
            "installed": rec.get("version"), "latest": meta.get("version")}


def statuses(root):
    """已裝模組的狀態（vault_state 用）。沒裝的不列。"""
    return [s for mid, meta in available().items() if (s := status(root, mid, meta))["state"] != ABSENT]


def _enable(root, mid):
    p = root / ".obsidian" / "community-plugins.json"
    try:
        ids = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ids = []
    if mid not in ids:
        ids.append(mid)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(ids, indent=2) + "\n", encoding="utf-8")


def install(root, mid, meta, force=False):
    st = status(root, mid, meta)
    if st["state"] == MODIFIED and not force:
        print(f"⛔ {mid}：vault 裡這些檔跟安裝時不同，可能有人改過，沒有覆蓋：")
        for f in st["files"]:
            print(f"   - {f}")
        print("   先把改動搬回 plugin 的 addons/ 正本；確認可丟棄再加 --force")
        return False
    files = {}
    for src, rel in targets(mid, meta):
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        files[rel] = md5_of(src)
    rec = root / ".obsidian" / "plugins" / mid / RECORD
    rec.write_text(json.dumps({"version": meta["version"], "files": files}, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    _enable(root, mid)
    print(f"✅ {mid} {meta['version']}：{len(files)} 個檔")
    if st["missing_requires"]:
        print(f"   ⚠️ 缺少依賴：{'、'.join(st['missing_requires'])}（模組裝了但相關功能不會出現）")
    return True


def main():
    ap = argparse.ArgumentParser(description="可選裝模組")
    ap.add_argument("cmd", nargs="?", default="list", choices=["list", "install", "update", "check"])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--force", action="store_true", help="vault 複本被改過也覆蓋")
    ap.add_argument("--quiet", action="store_true", help="check：沒事不印")
    a = ap.parse_args()

    root = find_vault_root(Path.cwd())
    if not root:
        print("不在 vault 內（找不到 wiki/ 或 raw/.manifest.json）")
        return 2
    mods = available()
    unknown = [i for i in a.ids if i not in mods]
    if unknown:
        print(f"沒有這個模組：{'、'.join(unknown)}；可用：{'、'.join(mods)}")
        return 2

    if a.cmd == "list":
        for mid, meta in mods.items():
            s = status(root, mid, meta)
            ver = f"{s.get('installed') or '?'} → {meta['version']}" if s["state"] == OUTDATED else meta["version"]
            print(f"{s['state']:<10} {mid:<15} {ver:<12} {meta.get('name', '')}：{meta.get('description', '')}")
            for f in s["files"]:
                print(f"{'':<11}- {f}")
        print("\n安裝：python addons.py install <id>（Obsidian 需重新載入）")
        return 0

    if a.cmd == "check":
        bad = [s for s in statuses(root) if s["state"] != UP_TO_DATE]
        if not bad:
            if not a.quiet:
                print("🟢 已裝模組皆為最新")
            return 0
        print(f"🟡 模組 {len(bad)} 個要處理：")
        for s in bad:
            hint = "跑 addons.py update" if s["state"] == OUTDATED else "改動先搬回 plugin 正本"
            print(f"  - {s['id']}：{s['state']}（{len(s['files'])} 個檔）→ {hint}")
        return 0

    if a.cmd == "install":
        if not a.ids:
            print("要給模組 id；先跑 addons.py 看有哪些")
            return 2
        ids = a.ids
    else:  # update
        ids = a.ids or [s["id"] for s in statuses(root)]
        ids = [i for i in ids if status(root, i, mods[i])["state"] != UP_TO_DATE] or []
        if not ids:
            print("🟢 已裝模組皆為最新")
            return 0
    ok = all([install(root, i, mods[i], a.force) for i in ids])
    if ok:
        print("Obsidian：重新載入（Ctrl+R）或 設定 → 第三方外掛 確認已啟用")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
