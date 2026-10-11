---
module: agenda
prefix: AGENDA
category: feature
version: 0.1.0
bundles: []
owner:                       # 2026-10-11 使用者：先全部留白
requires: {core: ">=0.1.0", lib: ">=0.1.0"}
optional: {}
covers:
  - skills/wiki-agenda/
  - commands/wiki-agenda.md
  - scripts/agenda.py
install:
  templates: [wiki/agenda.md, wiki/meta/agenda-system.md]
  hooks: [SessionStart:agenda.py]
  manifest_keys: []
uninstall:
  keep_user_data: true
tests:                       # 階段 1 可空；C7 登記（U2 會擋它變「可用」）
check:                       # 階段 1 可空；guard 改彙整器後才有
claude_md: claude.md         # 檔可空：CLAUDE.md 的組裝是 GOV-001 §3 的範圍
---

# agenda

日程：逾期／今天／窗口、匯出 ics 與通知。唯一真相來源 wiki/agenda.md。

> 開發狀態與索引在 vault 的 `raw/modules/agenda/README.md`，本檔只放技術規格（契約 §2）。
