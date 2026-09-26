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
LEDGER_REL = "wiki/meta/maintenance/ledger.tsv"
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


def _verdict_score(verdict):
    """把 verdict 轉成可比大小的數字。CLEAN＝0，其餘取第一個數字，抓不到數字＝1。

    只用來判斷「變好還是變差」，不是精確度量 —— 不同腳本的數字意義本來就不同，
    但**同一支腳本自己跟自己比**是有意義的，而趨勢判讀只做同支比較。
    """
    v = str(verdict)
    if "CLEAN" in v.upper():
        return 0
    m = re.search(r"\d+", v)
    return int(m.group()) if m else 1


def _ledger_path(root):
    return None if root is None else Path(root) / LEDGER_REL


def ledger_rows(root=None):
    """讀分類帳。回 [(date, script, host, verdict)]，讀不到回 []。"""
    fp = _ledger_path(root if root is not None else _vault_root())
    if fp is None or not fp.is_file():
        return []
    rows = []
    try:
        for line in fp.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 4:
                rows.append(tuple(parts[:4]))
    except OSError:
        return []
    return rows


def _append_ledger(root, script, verdict, host):
    """🔴 只在 verdict **變化**時 append 一行 —— 記的是轉折點不是流水帳。

    為什麼不每次都寫：一個連續 60 天 CLEAN 的系統會產生 60 行相同內容，
    看的人要自己找哪裡變過 —— 那就是雜訊，而雜訊久了沒人看（實測：某 vault 的
    lint-report 四個月沒人產、也沒人想念）。只記變化點的話，穩定的系統幾乎不長，
    而每一行都是「這天開始不一樣了」。
    「上次何時跑過」不在這裡 —— 那是 _guard-status/{host}.json 的職責，兩者不重疊。
    """
    fp = _ledger_path(root)
    if fp is None:
        return
    prev = None
    for d, s, h, v in ledger_rows(root):
        if s == script and h == host:
            prev = v
    if prev is not None and prev == str(verdict):
        return                                    # 沒變，不寫
    line = "\t".join([date.today().isoformat(), script, host, str(verdict)])
    try:
        fp.parent.mkdir(parents=True, exist_ok=True)
        new = not fp.exists()
        with fp.open("a", encoding="utf-8", newline="\n") as f:
            if new:
                f.write("# 守門分類帳：只記 verdict 的**變化點**，不是每次執行。\n")
                f.write("# 「上次何時跑過」看 _guard-status/{host}.json；本檔看「結果何時變過」。\n")
                f.write("# 欄位：日期\t腳本\t機器\tverdict\n")
            f.write(line + "\n")
    except OSError:
        pass


def trend_report(root=None, days=60):
    """比對每支腳本最近一次變化：變差回一句話，變好或沒變不回。

    只報惡化 —— 變好不需要打擾人（同 tidy_check「CLEAN 就安靜」的取捨）。
    """
    root = root if root is not None else _vault_root()
    rows = ledger_rows(root)
    if not rows:
        return []
    byscript = {}
    for d, s, h, v in rows:
        byscript.setdefault((s, h), []).append((d, v))
    out = []
    today = date.today()
    for (s, h), seq in sorted(byscript.items()):
        if len(seq) < 2:
            continue
        (pd_, pv), (cd, cv) = seq[-2], seq[-1]
        try:
            age = (today - datetime.strptime(cd, "%Y-%m-%d").date()).days
        except ValueError:
            continue
        if age > days:
            continue                              # 太久以前的變化不再提
        before, after = _verdict_score(pv), _verdict_score(cv)
        if after <= before:
            continue                              # 變好或持平 → 不吵
        sev = "🔴" if before == 0 else "🟡"
        out.append(f"{sev} {s}：{pd_} 還是「{pv}」，{cd} 變成「{cv}」"
                   f"（{age} 天前{'' if h == platform.node() else '，在 ' + h}）")
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
    _append_ledger(root, script, verdict, platform.node())
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
