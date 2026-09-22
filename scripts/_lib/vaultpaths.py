"""Vault 路徑解析。所有腳本共用，避免各自寫一份會漂掉的路徑邏輯。"""
import json
from pathlib import Path

MANIFEST_REL = "raw/.manifest.json"
MARKERS = ("wiki", "raw/.manifest.json")


def find_vault_root(start: Path, limit: int = 6):
    """從 start 往上找 vault 根（含 wiki/ 目錄或 raw/.manifest.json）。找不到回 None。"""
    cur = Path(start).resolve()
    for _ in range(limit):
        if (cur / "wiki").is_dir() or (cur / MANIFEST_REL).is_file():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def manifest_path(root: Path) -> Path:
    return Path(root) / MANIFEST_REL


def load_manifest(root: Path) -> dict:
    p = manifest_path(root)
    if not p.is_file():
        return {}
    try:
        with p.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_manifest(root: Path, data: dict) -> None:
    p = manifest_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(p)


def manifest_sources(manifest: dict) -> dict:
    """manifest 裡**真正的來源紀錄**，過濾掉備註。

    🔴 兩種東西會混在 sources 裡，直接迭代會出事（2026-09-22 在成熟 vault 實測）：
      · `_` 開頭的 key ＝ 人寫的備註（`_note`／`_batch_note_2026-05-05`…）——
        本 plugin 自己的範本也用這個慣例（`_scope_note`／`_doc_index_note`）
      · 值不是 dict（就是一段說明文字）
    不過濾的後果：`v.get(...)` 直接 AttributeError（#30 對帳整支掛掉、hook 靜默無輸出）、
    來源數多算、備註 key 被當成「來源檔消失」。

    同時吸收舊式 manifest：來源直接放在頂層（`raw/…` 或 `alias::…`），不在 sources 底下。
    """
    out = {}
    for k, v in (manifest.get("sources") or {}).items():
        if not k.startswith("_") and isinstance(v, dict):
            out[k] = v
    for k, v in manifest.items():
        if k in ("config", "repos", "sources", "doc_index") or k.startswith("_"):
            continue
        if isinstance(v, dict) and (k.startswith("raw/") or "::" in k):
            out.setdefault(k, v)
    return out


def resolve_source(root: Path, key: str):
    """把 manifest 的 source key 解析成實際路徑。

    'raw/BOOK/x.pdf'      -> {root}/raw/BOOK/x.pdf
    'alias::docs/x.md'    -> {repos[alias].path}/docs/x.md
    找不到 alias 回 None。
    """
    if "::" not in key:
        return Path(root) / key
    alias, rel = key.split("::", 1)
    base = load_manifest(root).get("repos", {}).get(alias, {}).get("path")
    return resolve_repo_path(root, base) / rel if base else None

# ── 可攜路徑（#27）─────────────────────────────────────────────
# 🔴 manifest 不存絕對路徑。絕對路徑等於把 `C:/Users/<某人>` 硬編碼進資料，
#    換一台機器、換一個使用者名稱、hub 搬個位置，全部 alias 一起失效。
#    （初版 6d3db33 就是這樣寫的；2026-09-21 使用者裁示：不准硬編碼。）
#
# 存的是 spec，解析順序：
#    ${VAR}/x  → 環境變數（跨機器最穩，適合大家路徑不同的共用來源）
#    ~/x       → 使用者家目錄（適合同一人不同機器）
#    ../x      → 相對 vault 根（適合來源與 hub 放在同一個上層資料夾）
#    C:/x      → 絕對，最後手段（跨磁碟機時無可避免），會被標記
import os

_MAX_UP = 4          # 相對表示最多往上幾層；再多就不如用 ~ 或 ${VAR}


def resolve_repo_path(root: Path, spec: str) -> Path:
    """把 manifest 存的 path spec 解析成這台機器上的實際路徑。"""
    if not spec:
        return Path("")
    s = os.path.expandvars(str(spec))
    if s.startswith("~"):
        return Path(s).expanduser()
    p = Path(s)
    return p if p.is_absolute() else (Path(root) / p).resolve()


def portable_path(root: Path, target) -> str:
    """把絕對路徑壓成可攜 spec。壓不掉就原樣回傳（呼叫端負責示警）。"""
    t = Path(target).resolve()
    root = Path(root).resolve()
    try:                                  # 1. 相對 vault 根
        rel = os.path.relpath(t, root).replace("\\", "/")
        if rel.count("../") + rel.count("..\\") <= _MAX_UP and not rel.startswith("/"):
            return rel
    except ValueError:
        pass                              # 不同磁碟機 → relpath 會拋
    try:                                  # 2. 家目錄
        return "~/" + t.relative_to(Path.home()).as_posix()
    except ValueError:
        pass
    return t.as_posix()                   # 3. 絕對（最後手段）


def is_hardcoded(spec: str) -> bool:
    """spec 是不是沒壓掉的絕對路徑（換機器就會失效）。"""
    s = str(spec or "")
    return bool(s) and not s.startswith(("~", "${")) and Path(s).is_absolute()


