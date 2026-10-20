#!/usr/bin/env python3
"""addons.py 的測試。每個案例在 tmp 自建假 vault 與假模組，不碰真實 vault 與 addons/。

用法：python test_addons.py（stdlib unittest，相容 3.9）
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import addons as M  # noqa: E402

META = {"id": "demo", "version": "1.0.0", "scripts": ["demo.py"], "requires": ["wiki/agenda.md"]}


class Modules(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mods = self.tmp / "addons"
        src = self.mods / "demo"
        (src / "obsidian").mkdir(parents=True)
        (src / "scripts").mkdir()
        (src / "obsidian" / "main.js").write_text("v1", encoding="utf-8")
        (src / "obsidian" / "manifest.json").write_text("{}", encoding="utf-8")
        (src / "scripts" / "demo.py").write_text("print(1)", encoding="utf-8")
        (src / "addon.json").write_text(json.dumps(META), encoding="utf-8")
        self.vault = self.tmp / "vault"
        (self.vault / "wiki").mkdir(parents=True)
        self._orig = M.ADDONS, M.PLUGIN_JSON
        M.ADDONS = self.mods
        M.PLUGIN_JSON = self.tmp / "plugin.json"
        M.PLUGIN_JSON.write_text('{"version": "1.0.0"}', encoding="utf-8")

    def tearDown(self):
        M.ADDONS, M.PLUGIN_JSON = self._orig
        shutil.rmtree(self.tmp)

    def st(self):
        return M.status(self.vault, "demo", META)

    def test_absent_not_reported(self):
        self.assertEqual(self.st()["state"], M.ABSENT)
        self.assertEqual(M.statuses(self.vault), [])

    def test_install_then_up_to_date_and_enabled(self):
        self.assertTrue(M.install(self.vault, "demo", META))
        self.assertEqual(self.st()["state"], M.UP_TO_DATE)
        self.assertTrue((self.vault / "scripts" / "demo.py").is_file())
        ids = json.loads((self.vault / ".obsidian" / "community-plugins.json").read_text(encoding="utf-8"))
        self.assertIn("demo", ids)
        self.assertEqual(self.st()["missing_requires"], ["wiki/agenda.md"])

    def test_new_plugin_version_is_outdated(self):
        M.install(self.vault, "demo", META)
        (self.mods / "demo" / "obsidian" / "main.js").write_text("v2", encoding="utf-8")
        s = self.st()
        self.assertEqual(s["state"], M.OUTDATED)
        self.assertEqual(s["files"], [".obsidian/plugins/demo/main.js"])

    def test_vault_edit_blocks_install_without_force(self):
        M.install(self.vault, "demo", META)
        (self.vault / "scripts" / "demo.py").write_text("print(2)", encoding="utf-8")
        self.assertEqual(self.st()["state"], M.MODIFIED)
        self.assertFalse(M.install(self.vault, "demo", META))
        self.assertEqual((self.vault / "scripts" / "demo.py").read_text(encoding="utf-8"), "print(2)")
        self.assertTrue(M.install(self.vault, "demo", META, force=True))
        self.assertEqual(self.st()["state"], M.UP_TO_DATE)

    def test_crlf_is_not_a_change(self):
        (self.mods / "demo" / "scripts" / "demo.py").write_bytes(b"a\nb\n")
        M.install(self.vault, "demo", META)
        p = self.vault / "scripts" / "demo.py"
        p.write_bytes(b"a\r\nb\r\n")  # 來源是 a\nb\n：git autocrlf checkout 後的樣子
        self.assertEqual(self.st()["state"], M.UP_TO_DATE)

    def test_local_files_untouched(self):
        M.install(self.vault, "demo", META)
        local = self.vault / ".obsidian" / "plugins" / "demo" / "local-rules.json"
        local.write_text('{"ask": "x"}', encoding="utf-8")
        (self.mods / "demo" / "obsidian" / "main.js").write_text("v2", encoding="utf-8")
        M.install(self.vault, "demo", META)
        self.assertEqual(local.read_text(encoding="utf-8"), '{"ask": "x"}')


    def test_local_declared_file_in_source_is_never_installed(self):
        """正本 obsidian/ 誤放了 local 宣告的檔，也不能蓋掉 vault 的設定。"""
        meta = {**META, "local": ["local-rules.json", "cache/"]}
        (self.mods / "demo" / "obsidian" / "local-rules.json").write_text('{"ask": "plugin"}', encoding="utf-8")
        local = self.vault / ".obsidian" / "plugins" / "demo" / "local-rules.json"
        local.parent.mkdir(parents=True)
        local.write_text('{"ask": "vault"}', encoding="utf-8")
        self.assertTrue(M.install(self.vault, "demo", meta))
        self.assertEqual(local.read_text(encoding="utf-8"), '{"ask": "vault"}')
        self.assertNotIn(".obsidian/plugins/demo/local-rules.json", [r for _, r in M.targets("demo", meta)])


    def _bump_vault_record(self, version):
        """模擬別人用較新的 plugin 裝過：vault 紀錄版本較新、檔案內容也不同。"""
        M.install(self.vault, "demo", META)
        rec = self.vault / ".obsidian" / "plugins" / "demo" / M.RECORD
        (self.vault / ".obsidian" / "plugins" / "demo" / "main.js").write_text("v9", encoding="utf-8")
        d = json.loads(rec.read_text(encoding="utf-8"))
        d["version"] = version
        d["files"][".obsidian/plugins/demo/main.js"] = M.md5_of(self.vault / ".obsidian" / "plugins" / "demo" / "main.js")
        rec.write_text(json.dumps(d), encoding="utf-8")

    def test_older_plugin_is_not_told_to_update(self):
        """防降版：vault 是 1.2.0、本機 plugin 是 1.0.0 → 報 plugin 比較舊，不是需更新。"""
        self._bump_vault_record("1.2.0")
        self.assertEqual(self.st()["state"], M.PLUGIN_OLD)

    def test_downgrade_install_refused_without_force(self):
        self._bump_vault_record("1.2.0")
        self.assertFalse(M.install(self.vault, "demo", META))
        self.assertEqual((self.vault / ".obsidian" / "plugins" / "demo" / "main.js").read_text(encoding="utf-8"), "v9")

    def _vault_installed_by_newer_plugin(self, plugin_ver):
        """別人用較新的 plugin 裝過，但 addon 版號沒 bump（只改內容）。"""
        M.install(self.vault, "demo", META)
        rec = self.vault / ".obsidian" / "plugins" / "demo" / M.RECORD
        d = json.loads(rec.read_text(encoding="utf-8"))
        d["plugin"] = plugin_ver
        rec.write_text(json.dumps(d), encoding="utf-8")

    def test_forgot_addon_bump_still_blocked_by_plugin_version(self):
        self._vault_installed_by_newer_plugin("2.0.0")
        main = self.vault / ".obsidian" / "plugins" / "demo" / "main.js"
        main.write_text("v9", encoding="utf-8")
        rec = self.vault / ".obsidian" / "plugins" / "demo" / M.RECORD
        d = json.loads(rec.read_text(encoding="utf-8"))
        d["files"][".obsidian/plugins/demo/main.js"] = M.md5_of(main)
        rec.write_text(json.dumps(d), encoding="utf-8")
        self.assertEqual(self.st()["state"], M.PLUGIN_OLD)
        self.assertFalse(M.install(self.vault, "demo", META))

    def test_newer_plugin_record_with_same_content_is_up_to_date(self):
        """plugin 升版但這個 addon 沒變：內容一樣就是最新，不該叫人更新 plugin。"""
        self._vault_installed_by_newer_plugin("2.0.0")
        self.assertEqual(self.st()["state"], M.UP_TO_DATE)

    def test_version_compare_is_numeric(self):
        self.assertGreater(M.vtuple("0.10.0"), M.vtuple("0.9.9"))
        self.assertEqual(M.vtuple(None), (0,))

    def test_undecided_lists_new_until_dismissed_or_installed(self):
        self.assertEqual([m for m, _ in M.undecided(self.vault)], ["demo"])
        M.dismiss(self.vault, ["demo"])
        self.assertEqual(M.undecided(self.vault), [])
        M.install(self.vault, "demo", META)  # 改變心意直接裝 → 自動從 dismissed 移除
        self.assertNotIn("demo", M._choices(self.vault).get("dismissed", []))
        self.assertEqual(M.undecided(self.vault), [])


if __name__ == "__main__":
    unittest.main()
