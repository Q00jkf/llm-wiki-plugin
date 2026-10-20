#!/usr/bin/env python3
"""可選裝模組（Obsidian 外掛＋它用的腳本）：列出、安裝、更新、檢查。

正本在 plugin 的 addons/<id>/；vault 裡的是安裝出來的複本。裝不裝由使用者選。

用法：
    python addons.py                    # 列出所有模組與本 vault 的狀態
    python addons.py install <id>...    # 安裝（被改過或會降版 → 停下，要 --force）
    python addons.py update [<id>...]   # 更新已裝的（不給 id＝全部已裝）
    python addons.py dismiss <id>...    # 這個 vault 不裝，之後不再提醒（要裝時直接 install）
    python addons.py check [--quiet]    # 開場與 doctor 用：已裝要處理的＋還沒決定的新模組

模組結構：addons/<id>/addon.json、obsidian/（→ .obsidian/plugins/<id>/）、scripts/（→ scripts/）。
安裝紀錄：.obsidian/plugins/<id>/.llm-wiki-addon.json（版本＋每個檔安裝當下的 hash），
用來分辨三件事：plugin 出新版、有人在 vault 裡改了複本、**本機 plugin 比裝進 vault 的那版舊**。
vault 跟著 git 給所有人，所以只要一個人先升級，其他人開場就會看到「plugin 比較舊」—— 不用連網。
不裝的決定記在 .obsidian/llm-wiki-addons.json（{"dismissed": [...]}），一樣跟著 git。
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

ADDONS = Path(__file__).resolve().parent.parent / "addons"
RECORD = ".llm-wiki-addon.json"
CHOICES = ".obsidian/llm-wiki-addons.json"

UP_TO_DATE, OUTDATED, MODIFIED, PLUGIN_OLD, ABSENT = "最新", "需更新", "vault 有改動", "plugin 比較舊", "未裝"


def vtuple(v):
    """'0.10.2' → (0, 10, 2)；讀不懂的段當 0，不讓壞版號讓開場掛掉。"""
    out = []
    for part in str(v or "").split("."):
        digits = "".join(c for c in part if c.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def available():
    out = {}
    if ADDONS.is_dir():
        for d in sorted(ADDONS.iterdir()):
            f = d / "addon.json"
            if f.is_file():
                out[d.name] = json.loads(f.read_text(encoding="utf-8"))
    return out


def targets(mid, meta):
    """[(plugin 內來源, vault 相對路徑)]"""
    src = ADDONS / mid
    local = {x.rstrip("/") for x in meta.get("local", [])}  # vault 自己的檔：就算正本誤放了同名檔也不裝
    pairs = [(p, f".obsidian/plugins/{mid}/{p.name}") for p in sorted((src / "obsidian").iterdir())
             if p.is_file() and p.name not in local]
    pairs += [(src / "scripts" / s, f"scripts/{s}") for s in meta.get("scripts", [])]
    return pairs


def _record(root, mid):
    p = root / ".obsidian" / "plugins" / mid / RECORD
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _choices(root):
    try:
        return json.loads((root / CHOICES).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_choices(root, data):
    p = root / CHOICES
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def status(root, mid, meta):
    if not (root / ".obsidian" / "plugins" / mid / "manifest.json").is_file():
        return {"id": mid, "state": ABSENT, "files": [], "missing_requires": []}
    rec = _record(root, mid) or {}
    base = {"id": mid, "installed": rec.get("version"), "latest": meta.get("version"),
            "missing_requires": [r for r in meta.get("requires", []) if not (root / r).exists()]}
    # vault 裡的版本比本機正本新＝別人用較新的 plugin 裝過；這時「不一致」不代表該更新，更新就是降版
    if rec.get("version") and vtuple(rec["version"]) > vtuple(meta.get("version")):
        return {**base, "state": PLUGIN_OLD, "files": []}
    recorded = rec.get("files", {})
    changed, stale = [], []
    for src, rel in targets(mid, meta):
        dst = root / rel
        have = md5_of(dst) if dst.is_file() else None
        if have == md5_of(src):
            continue
        # 沒紀錄時無從判斷是誰改的 → 當作改動，寧可停下也不要蓋掉別人的修改
        if have is not None and have != recorded.get(rel):
            changed.append(rel)
        else:
            stale.append(rel)
    state = MODIFIED if changed else OUTDATED if stale else UP_TO_DATE
    return {**base, "state": state, "files": changed or stale}


def statuses(root):
    """已裝模組的狀態（vault_state 用）。沒裝的不列。"""
    return [s for mid, meta in available().items() if (s := status(root, mid, meta))["state"] != ABSENT]


def undecided(root):
    """沒裝、也沒說不裝的模組 —— 新模組出來時靠這個讓人知道。"""
    dismissed = set(_choices(root).get("dismissed", []))
    return [(mid, meta) for mid, meta in available().items()
            if mid not in dismissed and status(root, mid, meta)["state"] == ABSENT]


def dismiss(root, ids):
    data = _choices(root)
    data["dismissed"] = sorted(set(data.get("dismissed", [])) | set(ids))
    _save_choices(root, data)


def _undismiss(root, mid):
    data = _choices(root)
    if mid in data.get("dismissed", []):
        data["dismissed"] = [x for x in data["dismissed"] if x != mid]
        _save_choices(root, data)


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
    if st["state"] == PLUGIN_OLD and not force:
        print(f"⛔ {mid}：vault 裡是 {st['installed']}，本機 plugin 只有 {meta['version']}，安裝會降版。")
        print("   先更新 plugin（/plugin update；開發機在 plugin repo 跑 git pull），再跑一次")
        return False
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
    _undismiss(root, mid)
    print(f"✅ {mid} {meta['version']}：{len(files)} 個檔")
    if st["missing_requires"]:
        print(f"   ⚠️ 缺少依賴：{'、'.join(st['missing_requires'])}（模組裝了但相關功能不會出現）")
    return True


HINT = {OUTDATED: "跑 addons.py update",
        MODIFIED: "改動先搬回 plugin 正本",
        PLUGIN_OLD: "先更新 plugin（/plugin update 或 plugin repo git pull）"}


def main():
    ap = argparse.ArgumentParser(description="可選裝模組")
    ap.add_argument("cmd", nargs="?", default="list", choices=["list", "install", "update", "dismiss", "check"])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--force", action="store_true", help="vault 複本被改過或會降版也照裝")
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
        dismissed = set(_choices(root).get("dismissed", []))
        for mid, meta in mods.items():
            s = status(root, mid, meta)
            state = "不裝" if s["state"] == ABSENT and mid in dismissed else s["state"]
            ver = (f"{s.get('installed') or '?'} → {meta['version']}" if s["state"] in (OUTDATED, PLUGIN_OLD)
                   else meta["version"])
            print(f"{state:<10} {mid:<15} {ver:<12} {meta.get('name', '')}：{meta.get('description', '')}")
            for f in s["files"]:
                print(f"{'':<11}- {f}")
        print("\n安裝：python addons.py install <id>（Obsidian 需重新載入）；不裝：python addons.py dismiss <id>")
        return 0

    if a.cmd == "check":
        bad = [s for s in statuses(root) if s["state"] != UP_TO_DATE]
        new = undecided(root)
        if not bad and not new:
            if not a.quiet:
                print("🟢 已裝模組皆為最新，沒有新模組")
            return 0
        if bad:
            print(f"🟡 模組 {len(bad)} 個要處理：")
            for s in bad:
                print(f"  - {s['id']}：{s['state']}（{s.get('installed') or '?'} vs plugin {s['latest']}）→ {HINT[s['state']]}")
        if new:
            print(f"🔵 有 {len(new)} 個模組還沒決定要不要裝：")
            for mid, meta in new:
                print(f"  - {mid}（{meta.get('name', '')}）：{meta.get('description', '')}")
            print("    要裝：addons.py install <id>；不要：addons.py dismiss <id>（之後不再提醒）")
        return 0

    if a.cmd == "dismiss":
        if not a.ids:
            print("要給模組 id")
            return 2
        dismiss(root, a.ids)
        print(f"已記下不裝：{'、'.join(a.ids)}（{CHOICES}）")
        return 0

    if a.cmd == "install":
        if not a.ids:
            print("要給模組 id；先跑 addons.py 看有哪些")
            return 2
        ids = a.ids
    else:  # update
        ids = a.ids or [s["id"] for s in statuses(root)]
        ids = [i for i in ids if status(root, i, mods[i])["state"] != UP_TO_DATE]
        if not ids:
            print("🟢 已裝模組皆為最新")
            return 0
    ok = all([install(root, i, mods[i], a.force) for i in ids])
    if ok:
        print("Obsidian：重新載入（Ctrl+R）或 設定 → 第三方外掛 確認已啟用")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
