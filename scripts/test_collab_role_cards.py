#!/usr/bin/env python3
"""role_cards 的測試（collab 模組）。每個案例在 tmp 自建假 vault，不碰真實 vault。

ISS-007：`all_cards()` 用「檔名不以 `_` 開頭」當角色卡判準 —— 那是排除法。
1.5.2 起樣板在 `wiki/meta/roles/` 放 `README.md`，於是它被當成一個叫「README」的角色。

③ 設計選了**正面判準**（frontmatter 有 `role:`）而不是再加一條排除 README：
排除法會在下一個放進 roles/ 的非卡文件再中一次。
🔴 但正面判準有另一種假綠 —— 既有卡漏寫 `role:` 會靜默消失，而
「角色卡不見了」比「多一列 README」危險。所以被排除的檔要**明確回報**，
唯一的例外是 `README.md`（樣板本來就有它，每個 vault 都報一次等於訓練大家忽略）。

用法：python test_collab_role_cards.py
"""
import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import role_cards as rc  # noqa: E402

NL = chr(10)


def write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="")


class RoleCards(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rolecards-"))
        (self.tmp / "wiki").mkdir()
        self.roles = self.tmp / rc.ROLES_REL
        self.roles.mkdir(parents=True)
        # 樣板本來就有的 README（沒有 role:）
        write(self.roles / "README.md",
              "---" + NL + "title: 角色卡" + NL + "type: meta" + NL + "---" + NL + "# 角色卡" + NL)
        # 一張真卡
        write(self.roles / "IT.md",
              "---" + NL + "role: IT" + NL + "agent: user-a1" + NL + "---" + NL
              + "## 定義" + NL + "- 職責範圍：plugin" + NL + "## 進行中事項" + NL)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def out(self, fn, *a):
        buf = io.StringIO()
        with redirect_stdout(buf):
            fn(self.tmp, *a)
        return buf.getvalue()

    # ── A3：重現測試（修前必須紅）
    def test_01_readme_is_not_a_role(self):
        names = [p.name for p in rc.all_cards(self.tmp)]
        self.assertNotIn("README.md", names, "roles/README.md 不是角色卡")
        self.assertIn("IT.md", names, "真卡還是要列出來")

    def test_02_list_has_no_readme_row(self):
        o = self.out(rc.cmd_list)
        self.assertNotIn("| README |", o, "list 不該有 README 這一列" + NL + o)
        self.assertIn("| IT |", o, "真卡要在" + NL + o)

    def test_03_check_does_not_check_readme(self):
        o = self.out(rc.cmd_check, False)
        self.assertNotIn("README.md", o, "check 不該把 README 當卡檢查" + NL + o)

    # ── A4：少列也要看得見
    def test_04_a_non_card_other_than_readme_is_reported(self):
        write(self.roles / "foo.md", "---" + NL + "title: 隨手筆記" + NL + "---" + NL + "內容" + NL)
        o = self.out(rc.cmd_list)
        self.assertNotIn("| foo |", o, "沒有 role: 就不是卡")
        self.assertIn("foo.md", o, "但要講出它被排除了，否則漏列看不見" + NL + o)
        self.assertIn("role:", o, "提示要說清楚缺什麼" + NL + o)

    # ── A5：反向驗證 —— 真卡漏寫 role: 不可靜默消失
    def test_05_a_real_card_missing_role_is_reported(self):
        write(self.roles / "QA.md", "---" + NL + "agent: x" + NL + "---" + NL + "## 定義" + NL)
        o = self.out(rc.cmd_list)
        self.assertNotIn("| QA |", o)
        self.assertIn("QA.md", o, "卡漏寫 role: 而靜默消失，比多一列 README 危險" + NL + o)

    # ── A8（G2 附條件）：只有樣板 README 時不可印 ⚠️
    def test_06_template_only_readme_prints_no_warning(self):
        o = self.out(rc.cmd_list)
        self.assertNotIn("⚠️", o, "每個 vault 都有 README，報它等於訓練大家忽略守門" + NL + o)

    def test_07_check_quiet_prints_no_warning_for_readme_only(self):
        o = self.out(rc.cmd_check, True)
        self.assertEqual(o.strip(), "", "--quiet 給 hook 用，只有樣板 README 時要完全安靜" + NL + repr(o))


if __name__ == "__main__":
    unittest.main(verbosity=2)
