---
module: lib
prefix:                      # 非模組，沒有單前綴（lib 的改動走 GOV 單）
category: internal
version: 0.1.0
bundles: [隨附]
owner:                       # 2026-10-11 使用者：先全部留白
requires: {}
optional: {}
covers:
  - scripts/_lib/vaultpaths.py
  - scripts/_lib/derived.py
  - scripts/_lib/filehash.py
  - scripts/_lib/logparse.py
  - scripts/_guard_status.py
install:
  templates: []
  hooks: []
  manifest_keys: []
uninstall:
  keep_user_data: true
tests:                       # 階段 1 可空；C7 登記（U2 會擋它變「可用」）
check:                       # 階段 1 可空；guard 改彙整器後才有
claude_md: claude.md         # 檔可空：CLAUDE.md 的組裝是 GOV-001 §3 的範圍
---

# lib

共用程式庫（非模組，不單獨選配）。葉節點：requires 必須為空。

> 開發狀態與索引在 vault 的 `raw/modules/lib/README.md`，本檔只放技術規格（契約 §2）。
