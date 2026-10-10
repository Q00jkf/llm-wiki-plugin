#!/usr/bin/env python3
"""rules_check 的測試。每個案例在 tmp 自建假 vault，不碰任何真實 vault。

用法：python test_rules_check.py（stdlib unittest，相容 3.9）
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import rules_check as rc  # noqa: E402

NL = chr(10)


def write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="")


class F1(unittest.TestCase):
    """ISS-003：資料夾用途表裡的佔位符不該被當成真路徑。

    > 原本的正則 `` `raw/([^/`]+)/?` `` 要求 `/` 後面緊接反引號，
    > 所以 `` `raw/members/<人>/` `` **整列對不上** → `members` 從沒被登記 → 每場誤報。
    > 按人分 `raw/` 正是多人 vault 的標準做法，所以每個多人 vault 都會踩。
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rules-"))
        (self.tmp / "wiki").mkdir()              # 讓 find_vault_root 認得

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def listed(self, table_rows, folders):
        for d in folders:
            (self.tmp / "raw" / d).mkdir(parents=True, exist_ok=True)
        write(self.tmp / "CLAUDE.md",
              "# v" + NL + NL + "## 資料夾用途" + NL + NL
              + "| 資料夾 | 放什麼 |" + NL + "|---|---|" + NL
              + NL.join(table_rows) + NL + NL + "## 下一節" + NL)
        return rc.check_f1(rc.Ctx(self.tmp))

    def test_01_placeholder_tail_still_registers_the_real_folder(self):
        """`raw/members/<人>/` 要算成「members 已登記」。"""
        hits, info = self.listed(["| `raw/members/<人>/` | 個人草稿 |"], ["members"])
        self.assertEqual(hits, [], "表裡明明有 members，不該報它沒登記｜" + info)

    def test_02_naming_rule_in_the_first_segment_is_still_skipped(self):
        """`raw/{專案代號}/` 是命名規則，不是某一夾 —— 舊行為要保住。"""
        hits, _ = self.listed(["| `raw/{專案代號}/` | 一個專案一夾 |"], [])
        self.assertEqual(hits, [], "命名規則不該被當成「表列了某夾」")

    def test_03_a_real_missing_folder_is_still_reported(self):
        """防呆：放寬比對後，真的沒登記的夾還要報得出來。"""
        hits, _ = self.listed(["| `raw/members/<人>/` | 個人草稿 |"], ["members", "issues"])
        self.assertEqual(len(hits), 1, "issues 沒登記，要報")
        self.assertIn("raw/issues/", hits[0])

    def test_04_a_file_path_is_not_a_folder_listing(self):
        """`raw/x/y.md` 是檔案路徑，不是在列資料夾 —— 不可因此認為 x 已登記。"""
        hits, _ = self.listed(["| 範例 `raw/issues/ISS-001.md` | 一單一檔 |"], ["issues"])
        self.assertEqual(len(hits), 1, "提到某夾裡的檔 ≠ 在用途表登記那個夾")


if __name__ == "__main__":
    unittest.main(verbosity=2)
