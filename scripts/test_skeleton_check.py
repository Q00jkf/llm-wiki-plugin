#!/usr/bin/env python3
"""skeleton_check 的測試 —— 這支會寫使用者的檔，不能只靠「跑一次看起來對」。

每個案例在 tmp 自建樣板與假 vault，不碰任何真實 vault。
用法：python test_skeleton_check.py（stdlib unittest，相容 3.9）
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import skeleton_check as sc  # noqa: E402

NL = chr(10)


def write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="skel-"))
        self.tpl = self.tmp / "tpl"
        self.vault = self.tmp / "vault"
        # 最小樣板：一個規則檔、一個模板檔
        write(self.tpl / "CLAUDE.md", "# {{name}}" + NL + "規則一" + NL)
        write(self.tpl / "wiki" / "ops" / "start.md", "## 開工" + NL + "項目 A" + NL)
        write(self.tpl / "Templates" / "t.md", "模板" + NL)
        # vault 照抄一份，並有 wiki/ 讓 find_vault_root 認得
        for rel in ("CLAUDE.md", "wiki/ops/start.md", "Templates/t.md"):
            write(self.vault / rel, (self.tpl / rel).read_text(encoding="utf-8"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_classify(self):
        return sc.classify(self.vault, self.tpl)

    def seal(self):
        """寫一份與現況相符的 .skeleton.json（模擬剛升級完的狀態）"""
        files = {}
        for rel in sc.template_files(self.tpl):
            files[rel] = {"template_hash": sc.md5_of(self.tpl / rel),
                          "local_hash": sc.md5_of(self.vault / rel)}
        write(self.vault / sc.SKELETON,
              json.dumps({"plugin_version": "1.0.0", "files": files}, ensure_ascii=False))


class TestClassify(Base):
    def test_1_no_diff(self):
        self.seal()
        (missing, safe, custom), info = self.run_classify()
        degraded = info["degraded"]
        self.assertFalse(degraded)
        self.assertEqual((missing, safe, custom), ([], [], []))

    def test_2_missing_file(self):
        self.seal()
        (self.vault / "wiki" / "ops" / "start.md").unlink()
        (missing, safe, custom), _i = self.run_classify()
        self.assertEqual([m["rel"] for m in missing], ["wiki/ops/start.md"])
        self.assertEqual((safe, custom), ([], []))

    def test_3_template_changed_local_untouched(self):
        self.seal()
        write(self.tpl / "wiki" / "ops" / "start.md", "## 開工" + NL + "項目 A" + NL + "項目 B（新）" + NL)
        (missing, safe, custom), _i = self.run_classify()
        self.assertEqual([s["rel"] for s in safe], ["wiki/ops/start.md"])
        self.assertIn("項目 B（新）", safe[0]["lines"])
        self.assertEqual(custom, [])

    def test_4_both_changed(self):
        self.seal()
        write(self.tpl / "wiki" / "ops" / "start.md", "## 開工" + NL + "項目 A" + NL + "項目 B（新）" + NL)
        write(self.vault / "wiki" / "ops" / "start.md", "## 開工" + NL + "項目 A" + NL + "我自己加的" + NL)
        (missing, safe, custom), _i = self.run_classify()
        self.assertEqual([c["rel"] for c in custom], ["wiki/ops/start.md"])
        self.assertIn("項目 B（新）", custom[0]["lines"])
        self.assertEqual(safe, [])

    def test_5_degraded_without_skeleton(self):
        write(self.vault / "wiki" / "ops" / "start.md", "## 開工" + NL + "我改過" + NL + "項目 A" + NL)
        write(self.tpl / "wiki" / "ops" / "start.md", "## 開工" + NL + "項目 A" + NL + "樣板新規則" + NL)
        (missing, safe, custom), info = self.run_classify()
        degraded = info["degraded"]
        self.assertTrue(degraded)
        self.assertEqual([c["rel"] for c in custom], ["wiki/ops/start.md"])
        self.assertEqual(safe, [], "降級模式分不出未客製，不該有②")

    def test_6_opted_out_not_reported(self):
        self.seal()
        (self.vault / "Templates" / "t.md").unlink()
        sk = json.loads((self.vault / sc.SKELETON).read_text(encoding="utf-8"))
        sk["files"]["Templates/t.md"] = {"opted_out": True}
        write(self.vault / sc.SKELETON, json.dumps(sk, ensure_ascii=False))
        (missing, _, _), _i = self.run_classify()
        self.assertEqual(missing, [])

    def test_7_placeholder_lines_are_not_news(self):
        """`# {{name}}` 這種佔位符 init 時就被填掉，永遠比得出差異，不該報。"""
        self.seal()
        write(self.tpl / "CLAUDE.md", "# {{name}}" + NL + "規則一" + NL + "{{domain}}" + NL)
        write(self.vault / "CLAUDE.md", "# 我的 vault" + NL + "規則一" + NL)
        (_, _, custom), _i = self.run_classify()
        self.assertEqual(custom, [], "差異只有佔位符時不該列出來")

    def test_8_heading_with_note_is_same_section(self):
        """`## 分工` 與 `## 分工（註解）` 是同一段，不該報成新段落。"""
        self.assertTrue(sc.same_heading("## 分工", "## 分工（名稱會變，以專長欄為準）"))
        self.assertFalse(sc.same_heading("## 分工", "## 派工"))


    def test_12_policy_file_controls_what_is_compared(self):
        """不對帳的清單在 .skeleton-policy（樣板旁邊），不是寫在腳本裡。"""
        write(self.tpl / sc.POLICY, "wiki/ops/*.md   # 測試：ops 不對帳" + NL + "# 整行註解" + NL)
        rels = sc.template_files(self.tpl)
        self.assertNotIn("wiki/ops/start.md", rels, "policy 列的 glob 應該被排除")
        self.assertNotIn(sc.POLICY, rels, "政策檔自己不該被對帳")
        self.assertIn("CLAUDE.md", rels, "沒列到的照常對帳")


class TestApply(Base):
    def test_9_apply_safe_touches_only_groups_1_and_2(self):
        self.seal()
        (self.vault / "wiki" / "ops" / "start.md").unlink()              # ① 缺檔
        write(self.tpl / "Templates" / "t.md", "模板" + NL + "樣板新增" + NL)   # ② 未客製
        write(self.tpl / "CLAUDE.md", "# {{name}}" + NL + "規則一" + NL + "樣板新規則" + NL)
        write(self.vault / "CLAUDE.md", "# 我的" + NL + "規則一" + NL + "我的客製" + NL)  # ③ 已客製
        before = (self.vault / "CLAUDE.md").read_bytes()

        n = sc.apply_safe(self.vault, self.tpl)

        self.assertEqual(n, 2, "應該只動①②各一個")
        self.assertTrue((self.vault / "wiki" / "ops" / "start.md").is_file(), "缺的檔要補進來")
        self.assertIn("樣板新增", (self.vault / "Templates" / "t.md").read_text(encoding="utf-8"))
        self.assertEqual((self.vault / "CLAUDE.md").read_bytes(), before, "③ 一個 byte 都不能動")

    def test_10_apply_safe_updates_skeleton_and_history(self):
        self.seal()
        (self.vault / "wiki" / "ops" / "start.md").unlink()
        sc.apply_safe(self.vault, self.tpl)
        # 🔴 未處理的③不可以被封存掉：apply_safe 不碰它，下次就該繼續報
        # （2026-10-09 對 wiki-test 複本實跑時踩到：5 個待融合的檔被記成已對帳，報告變 🟢）
        write(self.tpl / "CLAUDE.md", "# {{name}}" + NL + "規則一" + NL + "樣板新規則" + NL)
        write(self.vault / "CLAUDE.md", "# 我的" + NL + "規則一" + NL + "我的客製" + NL)
        sc.apply_safe(self.vault, self.tpl)
        (_, _, custom), _i = self.run_classify()
        self.assertEqual([c["rel"] for c in custom], ["CLAUDE.md"], "待融合的檔被 apply_safe 吞掉了")
        sk = json.loads((self.vault / sc.SKELETON).read_text(encoding="utf-8"))
        self.assertEqual(sk["files"]["wiki/ops/start.md"]["local_hash"],
                         sc.md5_of(self.tpl / "wiki/ops/start.md"), "補完的檔要記新 hash")
        hist = (self.vault / sc.HISTORY).read_text(encoding="utf-8")
        self.assertIn("wiki/ops/start.md", hist, "升級史要記這次做了什麼")
        # 再跑一次 classify 應該乾淨了
        (missing, safe, custom), _i = self.run_classify()
        self.assertEqual((missing, safe), ([], []))

    def test_13_never_overwrite_a_file_that_never_matched_the_template(self):
        """🔴 從第一天就跟樣板不一樣的檔，永遠不可以進組②（會被整檔覆蓋）。

        `local_hash == base_local` 只代表「上次對帳後你沒再動它」，不代表它曾經等於樣板。
        CLAUDE.md／wiki/ops/*.md 這種檔建 vault 當天就是真規則層、樣板是空殼，
        而且常常好幾個月沒人動 → 樣板一改就落進「未客製，可安全換」→ 整份被蓋掉。
        （llm-wiki-aegiverse-e4 2026-10-09 review 實跑驗出）
        """
        write(self.vault / "CLAUDE.md", "# 我的 vault" + NL + "我累積的規則層" + NL)  # 一開始就 ≠ 樣板
        self.seal()
        write(self.tpl / "CLAUDE.md", "# {{name}}" + NL + "規則一" + NL + "樣板改了一行" + NL)
        (_, safe, custom), _i = self.run_classify()
        self.assertEqual(safe, [], "從來不等於樣板的檔不可以被歸成『可安全換』")
        self.assertEqual([c["rel"] for c in custom], ["CLAUDE.md"])
        sc.apply_safe(self.vault, self.tpl)
        self.assertIn("我累積的規則層", (self.vault / "CLAUDE.md").read_text(encoding="utf-8"),
                      "apply_safe 把使用者的規則層蓋掉了")

    def test_14_template_removals_are_reported(self):
        """樣板「刪掉」一條規則也是升級。只看新增行會整個漏掉，而且理由字串會說謊。"""
        self.seal()
        write(self.tpl / "wiki" / "ops" / "start.md", "## 開工" + NL)   # 刪掉「項目 A」
        (_, safe, custom), info = self.run_classify()
        self.assertEqual(info["trivial"], [], "刪除不是潤稿，不可以被判成 trivial")
        self.assertEqual(len(safe) + len(custom), 1, "樣板移除內容要報出來")
        hit = (safe + custom)[0]
        self.assertEqual(hit["n_removed"], 1)

    def test_15_placeholders_are_rendered_when_copying(self):
        """補缺檔時要經過 init_vault.render()，否則 `{{today}}` 原樣落地。"""
        self.seal()
        write(self.tpl / "wiki" / "ops" / "new.md", "updated: {{today}}" + NL + "# {{name}}" + NL)
        sc.apply_safe(self.vault, self.tpl)
        got = (self.vault / "wiki" / "ops" / "new.md").read_text(encoding="utf-8")
        self.assertNotIn("{{", got, "佔位符沒有被代換就落地了")
        self.assertIn(self.vault.name, got, "{{name}} 應該換成 vault 目錄名")

    def test_11_downgrade_is_not_reported(self):
        """plugin 降版（樣板比 vault 舊）只往前，不倒退。"""
        self.seal()
        sk = json.loads((self.vault / sc.SKELETON).read_text(encoding="utf-8"))
        sk["plugin_version"] = "9.9.9"
        write(self.vault / sc.SKELETON, json.dumps(sk, ensure_ascii=False))
        write(self.tpl / "wiki" / "ops" / "start.md", "## 開工" + NL + "舊版內容" + NL)
        (missing, safe, custom), _i = sc.classify(self.vault, self.tpl, plugin_version="1.0.0")
        self.assertEqual((missing, safe, custom), ([], [], []), "降版不該報任何東西")


if __name__ == "__main__":
    unittest.main(verbosity=2)
