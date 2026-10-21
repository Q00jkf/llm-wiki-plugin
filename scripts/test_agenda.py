#!/usr/bin/env python3
"""agenda.py 整合測試：從 plugin 位置對暫存 vault 跑（同 SessionStart），資料全虛構。

用法：python test_agenda.py（stdlib unittest，相容 3.9）
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AGENDA = Path(__file__).resolve().parent / "agenda.py"


def run(cwd, *args):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    env.pop("CLAUDE_PROJECT_DIR", None)
    p = subprocess.run([sys.executable, str(AGENDA), *args], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", env=env)
    return p.returncode, p.stdout + p.stderr


class Agenda(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.v = Path(self.tmp.name) / "vault"
        (self.v / "wiki").mkdir(parents=True)
        self.md = self.v / "wiki" / "agenda.md"

    def tearDown(self):
        self.tmp.cleanup()

    def body(self):
        return self.md.read_text(encoding="utf-8")

    def test_outside_vault_quiet_but_commands_fail(self):
        out = Path(self.tmp.name) / "plain"
        out.mkdir()
        self.assertEqual(run(out), (0, ""))
        self.assertEqual(run(out, "add", "2030-01-02 待辦 甲")[0], 1)

    def test_no_agenda_quiet_and_add_creates_skeleton(self):
        self.assertEqual(run(self.v), (0, ""))
        self.assertEqual(run(self.v, "done", "甲")[0], 1)
        self.assertEqual(run(self.v, "add", "2030-01-02 待辦 甲 #測試")[0], 0)
        self.assertIn("<!-- 事件從下一行開始 -->", self.body())
        self.assertIn("2030-01-02 待辦 甲 #測試", self.body())

    def test_move_shifts_successor_and_keeps_baseline(self):
        run(self.v, "add", "2030-01-07 待辦 草圖 工期2天 代號:a #專案甲")
        run(self.v, "add", "2030-01-09 待辦 打樣 代號:b 接:a #專案甲")
        code, out = run(self.v, "move", "草圖", "2030-01-08")
        self.assertEqual(code, 0, out)
        self.assertIn("2030-01-08 待辦 草圖 工期2天 代號:a 原定:01-07", self.body())
        self.assertIn("2030-01-10 待辦 打樣 代號:b 接:a 原定:01-09", self.body())
        self.assertTrue((self.v / "raw" / "manager" / "schedule" / "changes.md").is_file())

    def test_hard_deadline_not_pushed(self):
        run(self.v, "add", "2030-01-10 待辦 製作 工期3天 代號:a #專案甲")
        run(self.v, "add", "2030-01-11 交件 送審 接:a #專案甲")
        run(self.v, "move", "製作", "2030-01-15")
        self.assertIn("2030-01-11 交件 送審", self.body())
        self.assertIn("硬期限", run(self.v, "--check")[1])

    def test_recurring_done_advances(self):
        run(self.v, "add", "2030-01-03 會議 週會 每週四 #行政")
        run(self.v, "done", "週會")
        self.assertIn("\n2030-01-10 會議 週會 每週四", self.body())  # 跳到下一次，不打 ✅

    def test_exports(self):
        run(self.v, "add", "2030-01-02 09:00-10:00 會議 甲 #測試")
        self.assertEqual(run(self.v, "--ics")[0], 0)
        self.assertIn(b"SUMMARY:", (self.v / "agenda.ics").read_bytes())
        self.assertEqual(run(self.v, "--json")[0], 0)
        self.assertEqual(run(self.v, "--notify")[0], 0)


if __name__ == "__main__":
    unittest.main()
