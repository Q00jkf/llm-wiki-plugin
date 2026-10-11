#!/usr/bin/env python3
"""ISS-022 C2：plugin 的每個實體恰好屬於一個模組。

根因不是分類分錯，是**沒有任何東西在檢查分類**。2026-10-10 人工對帳的結果：
孤兒 16、多重歸屬 7、兩條循環依賴 —— 模組 README 的「涵蓋」是人手寫的，寫完沒對過程式碼。

**兩段各自對帳**（契約 §2 把兩件事分在兩個欄位）：
  covers            → plugin repo 的實體（skills／commands／scripts／治理檔／docs）
  install.templates → 要裝進 vault 的樣板檔（相對 templates/vault/）

判準：**一個路徑只能出現在一個模組。** 「誰能改這個檔」要有唯一答案 ——
樣板是熱點（改了所有已建 vault 都要融合），多主人＝沒主人。

🔴 **不用 pyyaml**：repo 現有測試都只靠 stdlib，測試帶外部依賴會在別人機器上掛掉。
MODULE.md 的 frontmatter 刻意寫得夠簡單，幾十行就能解 —— 格式可被簡單 parser 讀，本身就是設計目標。

用法：python test_module_coverage.py
"""
import io
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULES = ROOT / "modules"
TPL = ROOT / "templates" / "vault"
NL = chr(10)


def _scalar(v: str):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [x.strip().strip(chr(34)) for x in inner.split(",")] if inner else []
    if v.startswith("{") and v.endswith("}"):
        inner = v[1:-1].strip()
        if not inner:
            return {}
        d = {}
        for part in inner.split(","):
            k, _, vv = part.partition(":")
            d[k.strip()] = vv.strip().strip(chr(34))
        return d
    return v.strip(chr(34))


def parse_front(text: str) -> dict:
    """只解 MODULE.md 用到的四種形狀：純量、行內清單、行內 dict、以及

        key:
          - 區塊清單
        key:
          子鍵: 值

    一個 key 的子層由「下一行起縮排 > 0」界定，看第一個子行是不是 `- ` 決定 list／dict。
    （第一版用 stack 遞迴，把區塊清單塞進它自己的子 dict —— governance 宣告的檔
      因此被誤報成孤兒。反向驗證那幾支是綠的，所以錯在 parser 不在判準。）
    """
    if not text.startswith("---"):
        return {}
    body = text.split("---", 2)[1]
    lines = [l.rstrip() for l in body.split(NL)
             if l.strip() and not l.lstrip().startswith("#")]
    out = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if len(line) - len(line.lstrip()) > 0:        # 子層已由上一輪吃掉
            i += 1
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.split("#")[0].strip()
        if val:
            out[key] = _scalar(val)
            i += 1
            continue
        j, items, sub = i + 1, [], {}
        while j < len(lines) and len(lines[j]) - len(lines[j].lstrip()) > 0:
            s = lines[j].lstrip()
            if s.startswith("- "):
                items.append(_scalar(s[2:]))
            else:
                k2, _, v2 = s.partition(":")
                sub[k2.strip()] = _scalar(v2.split("#")[0].strip())
            j += 1
        out[key] = items if items else sub
        i = j
    return out


def modules() -> dict:
    out = {}
    for f in sorted(MODULES.glob("*/MODULE.md")):
        out[f.parent.name] = parse_front(io.open(f, encoding="utf-8").read())
    return out


def owner_map(mods: dict, key: str) -> dict:
    """{宣告的路徑: [模組…]}。key 是 covers 或 install.templates。"""
    out = {}
    for name, m in mods.items():
        if key == "covers":
            decl = m.get("covers") or []
        else:
            decl = ((m.get("install") or {}).get("templates")) or []
        if not isinstance(decl, list):
            decl = []
        for p in decl:
            out.setdefault(p, []).append(name)
    return out


def classify(entities, owners, exceptions=()):
    """回 (孤兒, 多重歸屬)。宣告以 / 結尾 ＝ 整個目錄（含底下的 .gitkeep）。"""
    dirs = {d: ms for d, ms in owners.items() if d.endswith("/")}
    orphan, multi = [], []
    for e in entities:
        if any(e == x or e.startswith(x) for x in exceptions):
            continue
        hit = list(owners.get(e, []))
        for d, ms in dirs.items():
            if e.startswith(d) and e != d:
                hit += ms
        hit = sorted(set(hit))
        if not hit:
            orphan.append(e)
        elif len(hit) > 1:
            multi.append((e, hit))
    for d, ms in sorted(dirs.items()):
        if len(set(ms)) > 1 and (d, sorted(set(ms))) not in multi:
            multi.append((d, sorted(set(ms))))
    return orphan, multi


SKIP_PARTS = {"node_modules", "__pycache__", ".git"}


def plugin_entities():
    """🔴 實體一律是**檔**，不是目錄。

    第一版把 `skills/<名>/` 當成一個實體，於是 `day` 逐檔宣告 SKILL.md／start.md／end.md
    （因為 `end-manager.md` 歸 collab）之後，**目錄本身變成孤兒** —— 那是模型的瑕疵不是真漏。
    改成列檔、再讓「以 / 結尾的宣告」用前綴涵蓋，兩種宣告法就都成立。
    """
    out = []
    for base in ("skills", "plugins"):
        for p in sorted((ROOT / base).rglob("*")):
            if p.is_file() and not SKIP_PARTS & set(p.relative_to(ROOT).parts):
                out.append(p.relative_to(ROOT).as_posix())
    out += ["commands/" + f.name for f in sorted((ROOT / "commands").glob("*.md"))]
    out += ["scripts/" + f.name for f in sorted((ROOT / "scripts").glob("*.py"))]
    out += ["scripts/_lib/" + f.name for f in sorted((ROOT / "scripts" / "_lib").glob("*.py"))]
    out += [f.name for f in sorted(ROOT.glob("*.md"))]
    out += [".claude-plugin/" + f.name for f in sorted((ROOT / ".claude-plugin").glob("*.json"))]
    out += ["hooks/hooks.json"]
    out += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "docs").rglob("*")) if p.is_file()]
    return out


def template_entities():
    return [p.relative_to(TPL).as_posix() for p in sorted(TPL.rglob("*")) if p.is_file()]


def exceptions():
    """_unowned.yml：每筆要有 why；非建置產物要有 iss；筆數不得超過檔頭 baseline。"""
    text = io.open(MODULES / "_unowned.yml", encoding="utf-8").read()
    m = re.search(r"baseline:\s*(\d+)", text)
    baseline = int(m.group(1)) if m else 0
    rows, cur = [], None
    for line in text.split(NL):
        s = line.strip()
        if s.startswith("- path:"):
            cur = {"path": s.split(":", 1)[1].strip()}
            rows.append(cur)
        elif cur is not None and s and not s.startswith("#") and ":" in s:
            k, _, v = s.partition(":")
            cur[k.strip()] = v.strip()
    return rows, baseline


class Coverage(unittest.TestCase):
    def test_01_plugin_entities_have_exactly_one_owner(self):
        rows, _ = exceptions()
        orphan, multi = classify(plugin_entities(), owner_map(modules(), "covers"),
                                 [r["path"] for r in rows])
        self.assertEqual(multi, [], "一個路徑只能一個主人（誰能改這個檔要有唯一答案）：" + NL
                         + NL.join("  " + p + " ← " + "、".join(ms) for p, ms in multi))
        self.assertEqual(orphan, [], str(len(orphan)) + " 個 plugin 實體沒有任何模組認領：" + NL
                         + NL.join("  " + o for o in orphan))

    def test_02_template_files_have_exactly_one_owner(self):
        orphan, multi = classify(template_entities(), owner_map(modules(), "install.templates"))
        self.assertEqual(multi, [], "樣板是熱點，多主人＝沒主人：" + NL
                         + NL.join("  " + p + " ← " + "、".join(ms) for p, ms in multi))
        self.assertEqual(orphan, [], str(len(orphan)) + " 個樣板檔沒有任何模組認領：" + NL
                         + NL.join("  " + o for o in orphan))

    def test_03_exception_list_only_shrinks(self):
        rows, baseline = exceptions()
        self.assertLessEqual(
            len(rows), baseline,
            "例外清單 " + str(len(rows)) + " 筆 > baseline " + str(baseline)
            + "。要新增必須同一個 commit 調降 baseline 並說明理由 —— 否則它會變成繞過守門的後門")
        for r in rows:
            self.assertTrue(r.get("why"), r["path"] + " 沒有 why")
            if "建置產物" not in r.get("why", ""):
                self.assertNotIn(r.get("iss", "null"), ("", "null"),
                                 r["path"] + " 不是建置產物，必須有 iss（＝有單在追）")

    # ── 反向驗證：抓不到東西的守門等於沒有（ISS-002 的教訓）
    def test_04_catches_an_orphan(self):
        orphan, _ = classify(["scripts/new_thing.py"], {"scripts/old.py": ["core"]})
        self.assertEqual(orphan, ["scripts/new_thing.py"])

    def test_05_catches_multi_ownership(self):
        _, multi = classify(["scripts/x.py"], {"scripts/x.py": ["core", "status"]})
        self.assertEqual(multi, [("scripts/x.py", ["core", "status"])])

    def test_06_catches_multi_ownership_via_directory_claim(self):
        """一邊宣告整個目錄、另一邊宣告裡面的檔 —— 這是 end.md 那類衝突的形狀。"""
        _, multi = classify(["skills/wiki-day/end.md"],
                            {"skills/wiki-day/": ["day"], "skills/wiki-day/end.md": ["collab"]})
        self.assertEqual(len(multi), 1)
        self.assertEqual(sorted(multi[0][1]), ["collab", "day"])

    def test_07_directory_claim_covers_gitkeep(self):
        orphan, multi = classify(["wiki/catalog/.gitkeep"], {"wiki/catalog/": ["knowledge"]})
        self.assertEqual((orphan, multi), ([], []),
                         "/ 結尾＝整個目錄，不該把 .gitkeep 報成孤兒")

    def test_08_the_scan_actually_sees_something(self):
        mods = modules()
        self.assertGreater(len(mods), 10, "讀不到 MODULE.md，parser 或路徑壞了")
        self.assertGreater(len(plugin_entities()), 40, "plugin 實體掃不到，glob 壞了")
        self.assertGreater(len(template_entities()), 20, "樣板掃不到")
        self.assertEqual(mods["lib"].get("requires"), {}, "lib 的 requires 必須為空（D5 的前提）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
