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


if __name__ == "__main__":
    unittest.main(verbosity=2)
