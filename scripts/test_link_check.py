#!/usr/bin/env python3
"""link_check 的測試。每個案例在 tmp 自建假 vault，不碰任何真實 vault。

用法：python test_link_check.py（stdlib unittest，相容 3.9）
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import link_check as lc  # noqa: E402


def write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="")


class LinkCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="linkchk-"))
        self.wiki = self.tmp / "wiki"
        self.wiki.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def pairs(self):
        _, found, _ = lc.scan(self.wiki)
        return {(s, d) for s, d, _ in found}

    def test_identifier_mention_without_link_is_reported(self):
        write(self.wiki / "products/GS-3V-NM.md", "# GS-3V-NM\n")
        write(self.wiki / "notes/a.md", "測試用 GS-3V-NM 跑了一圈。\n")
        self.assertEqual(self.pairs(), {("notes/a.md", "products/GS-3V-NM.md")})

    def test_existing_link_in_either_direction_is_not_reported(self):
        write(self.wiki / "products/GS-3V-NM.md", "# GS-3V-NM\n見 [[a]]\n")
        write(self.wiki / "notes/a.md", "測試用 GS-3V-NM 跑了一圈。\n")
        self.assertEqual(self.pairs(), set())

    def test_generic_words_and_cjk_are_ignored(self):
        write(self.wiki / "ops/ingest.md", "# ingest\n")
        write(self.wiki / "meta/主管.md", "# 主管\n")
        write(self.wiki / "notes/a.md", "ingest 之後交給主管。\n")
        self.assertEqual(self.pairs(), set())

    def test_alias_is_matched_and_code_is_skipped(self):
        write(self.wiki / "products/core.md", "---\naliases: [AegiverseCore]\n---\n# core\n")
        write(self.wiki / "notes/a.md", "`AegiverseCore` 只是在程式碼裡。\n")
        write(self.wiki / "notes/b.md", "AegiverseCore 的設定。\n")
        self.assertEqual(self.pairs(), {("notes/b.md", "products/core.md")})

    def test_ambiguous_term_and_log_are_skipped(self):
        write(self.wiki / "a/HINS.md", "# HINS\n")
        write(self.wiki / "b/HINS.md", "# HINS\n")
        write(self.wiki / "notes/x.md", "HINS\n")
        write(self.wiki / "log.md", "GS-3V-NM\n")
        write(self.wiki / "products/GS-3V-NM.md", "# GS-3V-NM\n")
        self.assertEqual(self.pairs(), set())

    def test_longer_id_does_not_match_inside_hyphenated_id(self):
        write(self.wiki / "products/GS-3V.md", "# GS-3V\n")
        write(self.wiki / "notes/a.md", "只提到 GS-3V-NM。\n")
        self.assertEqual(self.pairs(), set())

    def test_typed_ratio_counts_only_frontmatter_links(self):
        write(self.wiki / "a.md", "---\nsupersedes: [[b]]\n---\n見 [[c]]\n")
        write(self.wiki / "b.md", "# b\n")
        write(self.wiki / "c.md", "# c\n")
        _, _, (typed, edges) = lc.scan(self.wiki)
        self.assertEqual((typed, edges), (1, 2))


if __name__ == "__main__":
    unittest.main()
