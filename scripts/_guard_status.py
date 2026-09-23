"""守門腳本的「我跑過了」留痕。

問題：tidy_check／stale_check 跑完就消失在終端機，「沒跑」「跑掛了」「跑出 CLEAN」事後無法區分
（原 vault 的 tidy-check 在 Python 3.11 掛 10 天沒人發現）。
做法：每支守門結尾呼叫 record()，寫 wiki/meta/_guard-status/{host}.json；vault_state 開場讀 stale_report()，
某支超過上限天數沒成功執行就列「守門失聯」。

🔴 一台機器一個檔，不是一台機器取最新覆蓋全部：
同一個 vault 被兩台機器共用（多機協作本來就是本 plugin 的既有場景，見 wiki-repo 的 owner/machine 追蹤）時，
若所有機器共寫同一個 key，B 機今天跑過就會把 A 機「60 天沒跑」蓋成「今天跑過」——A 機的守門可能早就掛了，
沒人會發現。拆檔只解決「寫入互相覆蓋」，判讀邏輯不跟著拆一樣白做：判讀改成兩層——
「全體失聯」（所有機器都逾期，這是真的問題）與「單機停跑」（這台逾期、別台仍在期內，這台環境可能有問題，
但不算全滅）。「這台從未跑過某支」一律不算它逾期——不是每台都該跑每一支，把沒紀錄當逾期
會在第一次執行就對每台機器噴一排假陽性。

取捨：只記日期、內容沒變不寫檔（不製造 git 噪音）；crash 不會寫（日期停在上次成功，正是要抓的）；
部分執行（掃子路徑）由呼叫端決定不記。找不到 vault 時全部靜默 no-op。
"""
import json
import os
import platform
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib.vaultpaths import find_vault_root  # noqa: E402

STATUS_DIR_REL = "wiki/meta/_guard-status"
STATUS_REL = "wiki/meta/_guard-status.json"  # 舊格式（單檔），只用於一次性遷移

# 多少天沒成功執行就算失聯
EXPECTED_DAYS = {
    "tidy-check": 7,
    "stale-check": 30,
    "agenda": 7,
    "rules-check": 7,
}


def _safe_host(name):
    return re.sub(r"[^A-Za-z0-9._-]", "_", name or "") or "unknown"


def _vault_root():
    return find_vault_root(Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))


def _status_dir(root=None):
    root = root if root is not None else _vault_root()
    return (root / STATUS_DIR_REL) if root else None


def _load(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, AttributeError):
        return {}


def _migrate_legacy(root):
    """把舊的單檔 wiki/meta/_guard-status.json 依 entry 的 host 欄位拆進每機一檔（冪等）。"""
    if root is None:
        return
    legacy = root / STATUS_REL
    if not legacy.is_file():
        return
    d = root / STATUS_DIR_REL
    if d.is_dir() and any(d.glob("*.json")):
        try:
            legacy.unlink()
        except OSError:
            pass
        return
    data = _load(legacy)
    by_host = {}
    for script, entry in data.items():
        h = _safe_host(entry.get("host"))
        by_host.setdefault(h, {})[script] = entry
    try:
        d.mkdir(parents=True, exist_ok=True)
        for h, entries in by_host.items():
            (d / f"{h}.json").write_text(
                json.dumps(entries, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                encoding="utf-8")
        legacy.unlink()
    except OSError:
        pass


def known_scripts():
    """所有機器留痕過的腳本名稱聯集（給 vault_state 判斷「這個 vault 有沒有在追蹤這支」）。"""
    root = _vault_root()
    _migrate_legacy(root)
    d = _status_dir(root)
    if d is None or not d.is_dir():
        return set()
    out = set()
    for fp in d.glob("*.json"):
        out |= set(_load(fp))
    return out


def record(script, verdict, exit_code=0, scope=None):
    """寫一筆留痕到**這台機器自己的檔**。內容與現有相同就不動檔案；留痕失敗不能讓守門本身失敗。"""
    root = _vault_root()
    _migrate_legacy(root)
    d = _status_dir(root)
    if d is None:
        return
    host = _safe_host(platform.node())
    fp = d / f"{host}.json"
    data = _load(fp)
    entry = {
        "date": date.today().isoformat(),
        "python": platform.python_version(),
        "host": platform.node(),
        "verdict": verdict,
        "exit": exit_code,
    }
    if scope:
        entry["scope"] = scope
    if data.get(script) == entry:
        return
    data[script] = entry
    try:
        d.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                     encoding="utf-8")
    except OSError:
        pass


def stale_report(today=None):
    """回傳失聯清單（每項 '{script}：…'），空＝全部在期內。

    兩層判斷：
    - 全體失聯：所有機器最後一次成功執行都超過上限天數 → 真的沒人在顧
    - 單機停跑：這台超過上限天數，但別台在期內 → 不算全滅，但這台環境可能有問題
    這台從未跑過某支 → 不算它逾期（不是每台都該跑每一支）；
    全體都從未跑過某支 → 照舊回報「從未留痕」。
    """
    root = _vault_root()
    _migrate_legacy(root)
    d = _status_dir(root)
    if d is None:
        return []
    today = today or date.today()
    current_host = _safe_host(platform.node())

    per_script = {}  # script -> {host_key: entry}
    if d.is_dir():
        for fp in sorted(d.glob("*.json")):
            for script, entry in _load(fp).items():
                per_script.setdefault(script, {})[fp.stem] = entry

    hits = []
    for script, limit in EXPECTED_DAYS.items():
        by_host = per_script.get(script)
        if not by_host:
            hits.append(f"{script}：從未留痕（沒有任何機器記錄過）")
            continue

        parsed = []
        for h, e in by_host.items():
            try:
                last = datetime.strptime(e["date"], "%Y-%m-%d").date()
            except (KeyError, ValueError, TypeError):
                continue
            parsed.append((h, last, e))
        if not parsed:
            hits.append(f"{script}：留痕日期格式壞掉")
            continue
        parsed.sort(key=lambda x: x[1], reverse=True)
        newest_host, newest_date, newest_entry = parsed[0]
        global_age = (today - newest_date).days

        if global_age > limit:
            hits.append(f"{script}：全體失聯，{global_age} 天沒有任何機器成功執行"
                        f"（最後一次 {newest_date.isoformat()}，{newest_entry.get('host', newest_host)}；"
                        f"上限 {limit} 天）")
            continue

        mine = by_host.get(current_host)
        if mine is None:
            continue  # 這台從未跑過這支，不算它逾期
        try:
            mine_last = datetime.strptime(mine["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError, TypeError):
            hits.append(f"{script}：{current_host} 留痕日期格式壞掉（{mine!r}）")
            continue
        mine_age = (today - mine_last).days
        if mine_age > limit and newest_host != current_host:
            hits.append(f"{script}：這台（{current_host}）{mine_age} 天沒成功執行，"
                        f"其他機器（{newest_entry.get('host', newest_host)}）{global_age} 天前還在跑——"
                        f"這台環境可能有問題（上次 {mine['date']}，verdict {mine.get('verdict', '?')}；上限 {limit} 天）")
    return hits
