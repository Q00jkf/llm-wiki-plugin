#!/usr/bin/env python3
"""腳本引用的 vault 路徑，樣板裡要「看得見」。

為什麼有這支（llm-wiki-aegiverse-e4 2026-10-09 排查後建議）：
`skeleton_check.py` 管的是「**樣板**變了，已建好的 vault 沒跟上」。
但還有一種漏法它管不到 —— 「**功能**變了，樣板沒跟上」：
加了新功能、腳本開始讀寫 vault 的某個路徑，卻忘了讓那個路徑出現在 `templates/vault/` 裡。
新 vault 的使用者於是不知道有這個機制。

實例（都是人工比對才發現的）：
- `wiki/meta/roles/`：1.3.0 加角色卡功能時只加了範本，沒讓資料夾進樣板
- `wiki/meta/init-history.md`：spec 的影響範圍表列了，實作時漏掉

判準是**使用者看不看得見這個機制**，不是樣板有沒有那個實體檔 —— 所以二選一就算過：
  (1) 樣板裡真的有那個檔／目錄，或
  (2) 樣板某個 .md 的內文提到這個路徑（文件寫到位就夠）
`wiki/meta/_guard-status/`、`maintenance/ledger.tsv` 走的是 (2)：
`maintenance/README.md` 已經把兩者的用途與寫入者寫成表了。

🔴 **(b) 類抓不到**：功能要求某個既有檔有特定「格式」（T9 的登記日、T7 的編號命名空間、
log 的 kind/scope 註解）——那些要求藏在腳本的 regex 裡，對不到文件。那部分只能靠
plugin repo `CLAUDE.md` 的「🔴 skill 要求 vault 做某件事時，要讓樣板看得見」那段紀律。

用法：python test_template_coverage.py
"""
import io
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "templates" / "vault"
SCRIPTS = ROOT / "scripts"

# 腳本裡出現、但不是「vault 裡該有的東西」的路徑
NOT_VAULT_CONTENT = {
    "wiki/",            # 存在性判斷用的裸目錄
    "wiki/ops/",
    # 舊格式單檔，只用於一次性遷移成每機一檔（_guard_status.py:32）。新 vault 不該有它
    "wiki/meta/_guard-status.json",
}


def referenced_paths():
    """腳本裡寫死的 vault 相對路徑：`"wiki/…"` 字面值與 *_REL 常數。"""
    out = {}
    for py in sorted(SCRIPTS.glob("*.py")):
        if py.name.startswith("test_"):
            continue
        text = io.open(py, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r'["\'](wiki/[A-Za-z0-9_./一-鿿-]+)["\']', text):
            p = m.group(1)
            if p not in NOT_VAULT_CONTENT:
                out.setdefault(p, set()).add(py.name)
        for m in re.finditer(r'Path\(["\'](wiki/[^"\']+)["\']\)', text):
            out.setdefault(m.group(1), set()).add(py.name)
    return out


class TestTemplateCoverage(unittest.TestCase):
    def test_every_referenced_path_is_visible_in_the_template(self):
        prose = ""
        for md in TPL.rglob("*"):
            if md.is_file() and md.suffix in (".md", ".json"):
                prose += io.open(md, encoding="utf-8", errors="replace").read()
        missing = []
        for rel, who in sorted(referenced_paths().items()):
            if (TPL / rel).exists():
                continue                      # (1) 樣板真的有
            # (2) 樣板某份文件提到它。比對最後一段而不是完整相對路徑 ——
            # 文件裡本來就會用相對寫法（`maintenance/README.md` 寫的是 `../_guard-status/{機器}.json`）
            if Path(rel.rstrip("/")).name in prose:
                continue
            missing.append(f"{rel}　← {'、'.join(sorted(who))}")
        self.assertEqual(
            missing, [],
            "這些路徑腳本會用、但樣板裡完全看不到（新 vault 的人不會知道有這個機制）："
            + chr(10) + chr(10).join("  " + m for m in missing)
            + chr(10) + "補法見 plugin repo CLAUDE.md「🔴 動 templates/vault/ 之前先看這段」",
        )

    def test_the_check_actually_sees_something(self):
        """防呆：正則若因改寫而失效，上面那條會變成永遠通過。"""
        self.assertGreater(len(referenced_paths()), 5, "一個 vault 路徑都沒掃到，正則壞了")


if __name__ == "__main__":
    unittest.main(verbosity=2)
