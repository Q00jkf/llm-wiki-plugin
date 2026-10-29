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


class Managers(unittest.TestCase):
    """1.14.0：「目前主管」→「主管名單」（多主管）；舊標題照讀。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="managers-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def coord(self, section: str):
        write(self.tmp / rc.COORD_REL, "# 主管名單" + NL + "<!-- 一列一位主管 -->" + NL + "| 主管（ListAgents 名稱） | 範圍 | peer | 上線 |" + NL + "|---|---|---|---|" + NL + section + NL + "# Session 狀態" + NL + "| a-1 | x |" + NL)

    def test_old_heading_still_reads(self):
        write(self.tmp / rc.COORD_REL, "# 目前主管" + NL + "user-30（上線於 10-12；派工）" + NL + "# Session 狀態" + NL + "| a-1 | x |" + NL)
        self.assertEqual(rc.current_manager(self.tmp, "w-9"), "user-30", "舊 vault 的 coordination.md 推不到新樣板，舊標題要照讀")

    def test_peer_column_wins(self):
        self.coord("| boss-a | raw/QMS/ | w-1、w-2 | 10-26 |" + NL + "| boss-b | raw/3V/ | w-3 | 10-26 |")
        self.assertEqual(rc.current_manager(self.tmp, "w-3"), "boss-b")
        self.assertEqual(rc.current_manager(self.tmp, "w-1", "boss-b"), "boss-a", "peer 欄比卡上 office_team 新")

    def test_peer_match_is_whole_name(self):
        self.coord("| boss-a | raw/QMS/ | w-10 | 10-26 |" + NL + "| boss-b | raw/3V/ | w-1 | 10-26 |")
        self.assertEqual(rc.current_manager(self.tmp, "w-1"), "boss-b", "w-1 不可因為 w-10 含它就配到 boss-a")

    def test_card_team_then_single(self):
        self.coord("| boss-a | raw/QMS/ | | 10-26 |" + NL + "| boss-b | raw/3V/ | | 10-26 |")
        self.assertEqual(rc.current_manager(self.tmp, "w-9", "boss-b"), "boss-b")
        self.assertIsNone(rc.current_manager(self.tmp, "w-9"), "兩位都有範圍、peer 欄沒有你 → 判斷不出，不要猜")

    def test_empty_scope_means_whole_vault(self):
        self.coord("| boss-a |  | | 10-26 |")
        self.assertEqual(rc.current_manager(self.tmp, "w-9"), "boss-a", "單主管、範圍空白＝舊用法，行為不變")
        self.coord("| boss-a | raw/QMS/ | | 10-26 |" + NL + "| boss-b |  | | 10-26 |")
        self.assertEqual(rc.current_manager(self.tmp, "w-9"), "boss-b", "範圍空白的主管涵蓋全 vault，接得住沒歸屬的人")

    def test_template_header_is_not_a_manager(self):
        self.coord("")
        self.assertIsNone(rc.current_manager(self.tmp, "w-9"))
        self.assertEqual(rc.managers(self.tmp), [])

    def test_chinese_manager_name_is_kept(self):
        self.coord("| willy主管辦公室 |  | w-1 | 10-26 |" + NL + "| boss-b | raw/3V/ | w-3 | 10-26 |")
        self.assertEqual([m[0] for m in rc.managers(self.tmp)], ["willy主管辦公室", "boss-b"])
        self.assertEqual(rc.current_manager(self.tmp, "w-1"), "willy主管辦公室", "B1：中文名主管被丟掉時 w-1 會被判給 boss-b")
        self.coord("| **office [ab12cd]** | | | 10-26 |")
        self.assertEqual(rc.current_manager(self.tmp, "w-9"), "office", "沒有連字號也是名稱；去粗體、去 [ref]")

    def test_unreadable_row_disables_fallbacks(self):
        self.coord("| ** ** |  | | 10-26 |" + NL + "| boss-b |  | w-3 | 10-26 |")
        self.assertEqual(rc.current_manager(self.tmp, "w-3"), "boss-b", "peer 欄照樣認")
        self.assertIsNone(rc.current_manager(self.tmp, "w-9"), "有一列讀不出名稱：不走「只有一位」「唯一空白」退路")

    def test_old_heading_reads_first_line_only(self):
        write(self.tmp / rc.COORD_REL, "# 目前主管" + NL + "**GUANGUAN [a1fe38]**（名牌 GUANGUAN；2026-10-13 使用者當面指派）" + NL + "> 規則：plugin `llm-wiki:wiki-collabteam`" + NL + "# Session 狀態" + NL)
        self.assertEqual(rc.current_manager(self.tmp, "w-9"), "GUANGUAN", "B2：AEGIVERSE 那種寫法")
        write(self.tmp / rc.COORD_REL, "# 目前主管" + NL + "<!-- 上線時填 -->" + NL + NL + "（無）" + NL + "> 規則：plugin `llm-wiki:wiki-collabteam`" + NL + "# Session 狀態" + NL)
        self.assertIsNone(rc.current_manager(self.tmp, "w-9"), "第一行抓不到就回 None，不往下抓到 llm-wiki")

    def test_no_coordination_file(self):
        self.assertIsNone(rc.current_manager(self.tmp, "w-9"))

    def test_team_format_upper_column_is_not_peer(self):
        write(self.tmp / rc.COLLAB_REL, "# 主管" + NL + "| 主管 | 範圍 | 上層 | 上線 |" + NL + "|---|---|---|---|" + NL
              + "| lead-1 | 實作 | boss-1 | 10-29 |" + NL + "| boss-1 | 全專案 |  | 10-29 |" + NL)
        self.assertIsNone(rc.current_manager(self.tmp, "boss-1"), "上層欄不是 peer：boss-1 不屬於 lead-1")


OLD_CARD = NL.join([
    "---", "role: QA", "agent: s-1", "taken: 2026-10-01 09:00", "office_name: QA", "office_title: 品保", "office_team: 主管", "---",
    "<!-- 舊卡 -->", "", "## 定義", "",
    "- 職責範圍：品保文件。", "- 必讀（最多 5 份）：", "  - [[wiki/qa]] —— 規則", "- 接手時讀什麼：主管摘要（`collab.md` 接手那列）",
    "- 用到才查：", "  - `raw/QA/` —— 原始檔", "- 🔴 客戶資料唯讀", "- 守門腳本：無", "",
    "## 進行中事項", "", "- [[wiki/qa#待辦]]（A 件）：下一步送審", ""])


class Migrate(unittest.TestCase):
    """1.16.0：wiki/meta/roles/、coordination.md → .claude/office/（pixel-office skill team 的格式）。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="migrate-"))
        write(self.tmp / "wiki" / "qa.md", "# QA" + NL + "## 待辦" + NL)
        write(self.tmp / rc.OLD_ROLES_REL / "QA.md", OLD_CARD)
        write(self.tmp / rc.OLD_COORD_REL, "---" + NL + "maintenance: transactional" + NL + "---" + NL
              + "# 主管名單" + NL + "| 主管 | 範圍 | peer | 上線 |" + NL + "|---|---|---|---|" + NL + "| boss-1 |  | s-2 | 10-29 |" + NL
              + "# Session 狀態" + NL + "| session | 專長 | 任務 | 上次回報 | 狀態 |" + NL + "|---|---|---|---|---|" + NL + "| s-2 | QA | 送審 | 10-29 | 在線 |" + NL)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cmd(self, fn, *a):
        buf = io.StringIO()
        with redirect_stdout(buf):
            fn(self.tmp, *a)
        return buf.getvalue()

    def test_old_location_still_reads_before_migrate(self):
        self.assertEqual(rc.roles_dir(self.tmp), self.tmp / rc.OLD_ROLES_REL)
        self.assertEqual(rc.must_reads(rc.load(self.tmp / rc.OLD_ROLES_REL / "QA.md")[2]), ["wiki/qa"])
        self.assertIn("還在舊位置", self.run_cmd(rc.cmd_check, True))

    def test_dry_run_writes_nothing(self):
        self.run_cmd(rc.cmd_migrate, True)
        self.assertFalse((self.tmp / rc.OFFICE_REL).exists())
        self.assertTrue((self.tmp / rc.OLD_COORD_REL).is_file())

    def test_migrate_moves_and_regroups_verbatim(self):
        self.run_cmd(rc.cmd_migrate, False)
        card = (self.tmp / rc.ROLES_REL / "QA.md").read_text(encoding="utf-8")
        self.assertFalse((self.tmp / rc.OLD_ROLES_REL / "QA.md").exists())
        self.assertNotIn("agent:", card)
        self.assertIn("reports_to: 主管", card)
        self.assertIn("## 職責" + NL + "品保文件。", card)
        self.assertIn("## 邊界" + NL + "- 🔴 客戶資料唯讀", card, "沒對到的條目進邊界，原文不改")
        self.assertIn("## 用到才查" + NL + "- 用到才查：" + NL + "  - `raw/QA/` —— 原始檔", card)
        self.assertEqual(rc.must_reads(rc.load(self.tmp / rc.ROLES_REL / "QA.md")[2]), ["wiki/qa"], "用到才查、說明句裡的 `collab.md` 都不算必讀")
        cp = (self.tmp / rc.CHECKPOINTS_REL / "QA.md").read_text(encoding="utf-8")
        self.assertIn("  - [[wiki/qa#待辦]]（A 件）：下一步送審", cp)
        self.assertEqual((self.tmp / rc.OFFICE_REL / ".gitignore").read_text(encoding="utf-8"), "collab.md" + NL + "checkpoints/" + NL)

    def test_collab_headings_renamed_and_still_read(self):
        self.run_cmd(rc.cmd_migrate, False)
        self.assertFalse((self.tmp / rc.OLD_COORD_REL).exists())
        text = (self.tmp / rc.COLLAB_REL).read_text(encoding="utf-8")
        self.assertIn("# 主管" + NL, text)
        self.assertIn("# 在線" + NL, text)
        self.assertIn("maintenance: transactional", text, "tidy_check 靠 frontmatter")
        self.assertEqual(rc.current_manager(self.tmp, "s-2"), "boss-1")
        self.assertEqual(rc.holder_of(self.tmp, "QA"), "s-2")

    def test_after_migrate_list_check_claim(self):
        self.run_cmd(rc.cmd_migrate, False)
        self.assertIn("| QA | s-2 | 品保 | 1 | 2026-", self.run_cmd(rc.cmd_list))
        self.assertIn("角色卡沒有斷掉的指標", self.run_cmd(rc.cmd_check, False))
        out = self.run_cmd(rc.cmd_claim, "QA", "s-3")
        self.assertIn("由 s-2 持有", out)
        self.assertIn("team=boss-1", out)
        self.assertNotIn("s-3", (self.tmp / rc.ROLES_REL / "QA.md").read_text(encoding="utf-8"), "claim 不寫卡")

    def test_migrate_twice_does_not_clobber(self):
        self.run_cmd(rc.cmd_migrate, False)
        write(self.tmp / rc.OLD_ROLES_REL / "QA.md", OLD_CARD)
        self.assertIn("已存在", self.run_cmd(rc.cmd_migrate, False))
        self.assertTrue((self.tmp / rc.OLD_ROLES_REL / "QA.md").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
