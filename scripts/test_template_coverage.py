#!/usr/bin/env python3
"""作者端改了一邊，另一邊沒跟上 —— 兩條 CI 級的防線。

`skeleton_check.py` 管的是「**樣板**變了，已建好的 vault 沒跟上」。
這支管另外兩種它看不到的漏法，兩者同形：**改動只落在一邊，沒有東西會發現。**

| 條 | 抓什麼 | 實例 |
|---|---|---|
| 1 | **功能變了，樣板沒跟上**：腳本開始讀寫某個 vault 路徑，卻沒讓它出現在 `templates/vault/` | `wiki/meta/roles/`（1.3.0 只加範本沒加資料夾）、`wiki/meta/init-history.md`（spec 列了、實作漏了）|
| 2 | **指令沒了，文件沒跟上**：合併或刪掉 command／skill，文件還在教使用者打那個名字 | 2026-10-09 併六個 skill 成兩個，留下 9 處 `/wiki-collab`｜`/wiki-meet`｜`/wiki-role`；其中一處在樣板裡，已經透過骨架升級散播出去一次 |

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

# ---------------------------------------------------------------- 第 1 條

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
    """第 1 條：判準是**使用者看不看得見這個機制**，不是樣板有沒有那個實體檔。

    所以二選一就算過：(1) 樣板裡真的有那個檔／目錄，或 (2) 樣板某個 .md 的內文提到這個路徑。
    `wiki/meta/_guard-status/`、`maintenance/ledger.tsv` 走的是 (2)。

    🔴 **(b) 類抓不到**：功能要求某個既有檔有特定「格式」（T9 的登記日、T7 的編號命名空間、
    log 的 kind/scope 註解）—— 那些要求藏在腳本的 regex 裡，對不到文件。那部分只能靠
    plugin repo `CLAUDE.md` 的「🔴 skill 要求 vault 做某件事時，要讓樣板看得見」那段紀律。
    """

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


# ---------------------------------------------------------------- 第 2 條

# 只查本專案的命名空間。`/plugin`、`/clear`、`/output-style`、`/obsidian-cli` 之類
# 是 Claude Code 內建或別人的 plugin，查了只會變成雜訊
OWN_NAMESPACE = re.compile(r"(?<![A-Za-z0-9_/.\-])/(?:llm-wiki:)?((?:wiki|office)[a-z0-9\-]*)")

# 掃 .md 時跳過的地方
SKIP_DIRS = {".git", "node_modules", "docs/specs"}


def _md_files():
    for md in sorted(ROOT.rglob("*.md")):
        rel = md.relative_to(ROOT).as_posix()
        if any(rel == d or rel.startswith(d + "/") for d in SKIP_DIRS):
            continue
        yield md, rel


def invocable_names():
    """使用者打 `/<名字>` 打得到的東西，三種來源。"""
    names = set()
    for plugin_root in [ROOT] + sorted((ROOT / "plugins").glob("*")):
        # ① commands/<名>.md
        names |= {p.stem for p in (plugin_root / "commands").glob("*.md")}
        # ② skills/<名>/SKILL.md —— skill 本身就能用 /<plugin>:<skill> 叫
        names |= {p.parent.name for p in (plugin_root / "skills").glob("*/SKILL.md")}
        # ③ hooks 裡程式註冊的（pixel-office 的 /office 走這條）
        for src in list((plugin_root / "hooks").glob("*.ts")) + list((plugin_root / "hooks").glob("*.tsx")):
            if ".test." in src.name:
                continue
            text = io.open(src, encoding="utf-8", errors="replace").read()
            names |= set(re.findall(r"command\.register\(\s*\{[^}]*?name:\s*['\"]([a-z0-9\-]+)['\"]", text, re.S))
    return names


def cited_names():
    """文件裡教使用者打的 `/<名字>` → {名字: ["路徑:行", …]}"""
    out = {}
    for md, rel in _md_files():
        for i, line in enumerate(io.open(md, encoding="utf-8", errors="replace"), 1):
            for name in OWN_NAMESPACE.findall(line):
                out.setdefault(name, []).append(f"{rel}:{i}")
    return out


class TestCitedCommandsExist(unittest.TestCase):
    """第 2 條：文件裡教的 `/wiki-*`／`/office*`，MUST 真的叫得到。

    > 為什麼是 CI 級而不是靠自己記得：2026-10-09 刪掉 `/wiki-collab`｜`/wiki-meet`｜`/wiki-role`
    > 的那一版，自己的文件有 9 處還在教那三個名字 —— 包括同一天**才剛修掉同一個病**的
    > `roles/README.md`。作者比使用者更容易漏，因為不會去讀自己剛寫的檔。

    🔴 `docs/specs/` 不掃：帶日期的規格書是歷史紀錄，寫當時存在的指令是對的。
    """

    def test_every_cited_command_resolves(self):
        known = invocable_names()
        dead = [f"/{n}　← {'、'.join(where)}" for n, where in sorted(cited_names().items())
                if n not in known]
        self.assertEqual(
            dead, [],
            "文件在教使用者打這些，但 command 與 skill 都沒有這個名字："
            + chr(10) + chr(10).join("  " + d for d in dead)
            + chr(10) + f"現在叫得到的：{'、'.join(sorted(known))}"
            + chr(10) + "合併或刪 skill／command 時，同一個 commit 要把文件裡的名字一起換掉",
        )

    def test_the_check_actually_sees_something(self):
        """防呆：兩邊都掃空時，上面那條會變成永遠通過。"""
        self.assertGreater(len(invocable_names()), 8, "一個可呼叫的名字都沒掃到（commands/skills 的 glob 壞了）")
        self.assertGreater(len(cited_names()), 8, "文件裡一個 /wiki-* 都沒掃到（正則壞了）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
