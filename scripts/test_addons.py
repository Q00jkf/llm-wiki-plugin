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
        self._orig = M.ADDONS
        M.ADDONS = self.mods

    def tearDown(self):
        M.ADDONS = self._orig
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


if __name__ == "__main__":
    unittest.main()
