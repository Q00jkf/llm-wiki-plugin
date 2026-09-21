"""wiki/log.md 條目解析。log_index 與 wiki_fold_parse 共用，HEAD regex 只定義在這一處。

為什麼獨立成模組：上游 fold skill 用另一套 regex 抓條目，命中 0 筆卻沒人發現、4.5 個月沒跑起來。
兩支腳本各寫一份解析器就會再漂一次。
"""
import re
from pathlib import Path

HEAD = re.compile(r"^## (\d{4}-\d{2}-\d{2})(.*)$")
TITLE_STRIP = " —-：:|"


def log_path(root: Path) -> Path:
    return Path(root) / "wiki" / "log.md"


def load_entries(log: Path):
    """回傳 (全部行, entries)。entries 依日期排序（同日依檔案位置），idx 1＝最早。

    每筆 {idx, start, end, date, title}；start/end 為 0-based 行區間 [start, end)。
    🔴 log.md 常兩種順序並存（早期 append 檔尾、近期 prepend 檔頭），位置不代表先後，所以按日期排。
    """
    lines = Path(log).read_text(encoding="utf-8").splitlines()
    heads = [(i, m.group(1), m.group(2).strip(TITLE_STRIP)) for i, l in enumerate(lines)
             for m in [HEAD.match(l)] if m]
    entries = []
    for n, (i, date, title) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        entries.append({"start": i, "end": end, "date": date, "title": title})
    entries.sort(key=lambda e: (e["date"], e["start"]))
    for n, e in enumerate(entries, 1):
        e["idx"] = n
    return lines, entries
