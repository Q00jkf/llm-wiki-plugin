"""守門腳本的「我跑過了」留痕。

問題：tidy_check／stale_check 跑完就消失在終端機，「沒跑」「跑掛了」「跑出 CLEAN」事後無法區分
（原 vault 的 tidy-check 在 Python 3.11 掛 10 天沒人發現）。
做法：每支守門結尾呼叫 record()，寫 wiki/meta/_guard-status.json；vault_state 開場讀 stale_report()，
某支超過上限天數沒成功執行就列「守門失聯」。

取捨：只記日期、內容沒變不寫檔（不製造 git 噪音）；crash 不會寫（日期停在上次成功，正是要抓的）；
部分執行（掃子路徑）由呼叫端決定不記。找不到 vault 時全部靜默 no-op。
"""
import json
import os
import platform
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib.vaultpaths import find_vault_root  # noqa: E402

STATUS_REL = "wiki/meta/_guard-status.json"

# 多少天沒成功執行就算失聯
EXPECTED_DAYS = {
    "tidy-check": 7,
    "stale-check": 30,
    "agenda": 7,
    "rules-check": 7,
}


def _status_path():
    root = find_vault_root(Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
    return (root / STATUS_REL) if root else None


def _load(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, AttributeError):
        return {}


def record(script, verdict, exit_code=0, scope=None):
    """寫一筆留痕。內容與現有相同就不動檔案；留痕失敗不能讓守門本身失敗。"""
    p = _status_path()
    if p is None:
        return
    data = _load(p)
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
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                     encoding="utf-8")
    except OSError:
        pass


def stale_report(today=None):
    """回傳失聯清單（每項 '{script}：…'），空＝全部在期內。"""
    p = _status_path()
    if p is None:
        return []
    today = today or date.today()
    data = _load(p)
    hits = []
    for script, limit in EXPECTED_DAYS.items():
        e = data.get(script)
        if not e:
            hits.append(f"{script}：從未留痕（{STATUS_REL} 無此鍵）")
            continue
        try:
            last = datetime.strptime(e["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError, TypeError):
            hits.append(f"{script}：留痕日期格式壞掉（{e!r}）")
            continue
        age = (today - last).days
        if age > limit:
            hits.append(f"{script}：{age} 天沒成功執行（上次 {e['date']}，{e.get('host', '?')}，"
                        f"Python {e.get('python', '?')}，verdict {e.get('verdict', '?')}；上限 {limit} 天）")
    return hits
