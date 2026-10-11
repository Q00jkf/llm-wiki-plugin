---
module: guard
prefix: GUARD
category: base
version: 0.1.0
bundles: [基本包]
owner:                       # 2026-10-11 使用者：先全部留白
requires: {core: ">=0.1.0", lib: ">=0.1.0"}
optional: {knowledge: ">=0.1.0", repo: ">=0.1.0", collab: ">=0.1.0", status: ">=0.1.0"}
covers:
  - skills/wiki-doctor/
  - commands/wiki-doctor.md
  - scripts/tidy_check.py
  - scripts/rules_check.py
  - scripts/big_read_guard.py
install:
  templates: [wiki/meta/maintenance/README.md]
  hooks: [SessionStart:tidy_check.py --quiet, SessionStart:rules_check.py --quiet, PreToolUse:big_read_guard.py]
  manifest_keys: []
uninstall:
  keep_user_data: true
tests:                       # 階段 1 可空；C7 登記（U2 會擋它變「可用」）
check:                       # 階段 1 可空；guard 改彙整器後才有
claude_md: claude.md         # 檔可空：CLAUDE.md 的組裝是 GOV-001 §3 的範圍
---

# guard

守門與健檢。改彙整器前 doctor 直接呼叫其他模組的腳本，故列為 optional。

> 開發狀態與索引在 vault 的 `raw/modules/guard/README.md`，本檔只放技術規格（契約 §2）。
