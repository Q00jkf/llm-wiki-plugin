#!/usr/bin/env python3
"""vault_state 的測試。每個案例在 tmp 自建假 vault，不碰任何真實 vault。

用法：python test_vault_state.py（stdlib unittest，相容 3.9）
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vault_state as vs  # noqa: E402

NL = chr(10)


class ForeignRepos(unittest.TestCase):
    """ISS-004：掛載路徑在別人機器上時，不該報「路徑失效」。

    > `raw/.manifest.json` 是 tracked 的，而掛載路徑是相對 vault 根的（`../plugin-llm-wiki`）。
    > 共用 vault 之後，**除了註冊者以外每個人每場開場都看到「repo 路徑失效」**。
    > 代價不是那一行字，是它會訓練所有人忽略整個老化訊號區。
    > 判法抄 `_guard_status.stale_report()`：分不清就照舊報，分得清就說清楚是誰的。
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vstate-"))
        (self.tmp / "wiki").mkdir()
        (self.tmp / "raw").mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def manifest(self, repos):
        (self.tmp / "raw" / ".manifest.json").write_text(
            json.dumps({"config": {}, "sources": {}, "repos": repos}, ensure_ascii=False),
            encoding="utf-8")

    def collect(self):
        return vs.collect(self.tmp)

    def test_01_someone_elses_machine_is_not_a_broken_path(self):
        self.manifest({"jacky-llm-wiki": {
            "path": "../nowhere-on-this-machine", "git": True,
            "owner": {"name": "Q00jkf", "machine": "SomeoneElsePC"}}})
        s = self.collect()
        self.assertEqual(s["broken_repos"], [],
                         "別人機器上的 repo 不是「壞了」，不該進老化訊號")
        self.assertEqual([a for a, _m in s["foreign_repos"]], ["jacky-llm-wiki"],
                         "要認得出來並標明是誰的")

    def test_02_my_own_missing_repo_is_still_broken(self):
        import platform
        here = vs._this_host() or platform.node()
        self.manifest({"mine": {
            "path": "../nowhere-on-this-machine", "git": True,
            "owner": {"name": "me", "machine": here}}})
        s = self.collect()
        self.assertEqual(s["broken_repos"], ["mine"],
                         "本機擁有的 repo 不見了，照舊要報")

    def test_03_unknown_owner_machine_is_still_broken(self):
        """分不出是誰的 → 照舊報。不確定時要吵，不要靜音。"""
        self.manifest({"legacy": {"path": "../nowhere-on-this-machine", "git": True}})
        s = self.collect()
        self.assertEqual(s["broken_repos"], ["legacy"])
        self.assertEqual(s["foreign_repos"], [])

    def test_04_an_existing_path_is_never_reported(self):
        (self.tmp / "sub").mkdir()
        self.manifest({"ok": {"path": "sub", "git": False,
                              "owner": {"machine": "SomeoneElsePC"}}})
        s = self.collect()
        self.assertEqual(s["broken_repos"], [])
        self.assertEqual(s["foreign_repos"], [], "路徑在就什麼都不用講")


class RawPendingHiddenDirs(unittest.TestCase):
    """ISS-015：`_raw_pending` 用絕對路徑判隱藏資料夾 → vault 在 `.` 開頭的目錄底下就假綠。

    > `vault_state.py:180` 用 `p.parts`（絕對），而**同一支檔的 :82-84 用 `rel.parts`**
    > 並且註解明文寫了這個坑。知識寫在同一個檔裡，不到 100 行後還是犯了 ——
    > 這不是沒想到，是沒有守門（同 ISS-002、ISS-004：守門自己說謊）。
    """

    def setUp(self):
        # 🔴 父目錄故意以 `.` 開頭 —— 這就是重現條件
        self.base = Path(tempfile.mkdtemp(prefix="vstate-"))
        self.hidden = self.base / ".aaproject"
        self.plain = self.base / "plain"
        self.vaults = {}
        for tag, parent in (("hidden", self.hidden), ("plain", self.plain)):
            v = parent / "v"
            (v / "wiki").mkdir(parents=True)
            (v / "raw").mkdir()
            (v / "raw" / "a.md").write_text("A", encoding="utf-8")
            (v / "raw" / "b.md").write_text("B", encoding="utf-8")
            (v / "raw" / "_README.md").write_text("dash", encoding="utf-8")
            (v / "raw" / ".hidden").mkdir()
            (v / "raw" / ".hidden" / "c.md").write_text("C", encoding="utf-8")
            (v / "raw" / ".manifest.json").write_text(
                json.dumps({"config": {}, "sources": {}, "repos": {}}, ensure_ascii=False),
                encoding="utf-8")
            self.vaults[tag] = v

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def pending(self, tag):
        return vs.collect(self.vaults[tag])["raw_pending"]

    def test_01_hidden_parent_does_not_hide_the_whole_raw(self):
        """A1 重現測試：修前這支會是 0。"""
        self.assertEqual(self.pending("hidden"), 2,
                         "vault 的父目錄以 . 開頭時，raw/ 底下的檔不該被當成隱藏檔")

    def test_02_both_paths_agree(self):
        """A2：同內容、不同路徑，數字必須一樣（修前不一樣）。"""
        self.assertEqual(self.pending("hidden"), self.pending("plain"))

    def test_03_真的隱藏資料夾仍然跳過(self):
        """A3：別把 raw/.hidden/c.md 算進來 —— 否則就修壞另一邊。"""
        self.assertEqual(self.pending("plain"), 2, "剛好 a.md 與 b.md，不含 .hidden/c.md")

    def test_04_dash_readme_still_excluded(self):
        """A4：`_README.md` 是資料夾儀表板，既有行為不變。"""
        v = self.vaults["plain"]
        (v / "raw" / "_README.md").write_text("still a dashboard", encoding="utf-8")
        self.assertEqual(self.pending("plain"), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
