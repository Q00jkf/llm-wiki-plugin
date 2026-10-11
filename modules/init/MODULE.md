---
module: init
prefix: INIT
category: base
version: 0.1.0
bundles: [基本包]
owner:                       # 2026-10-11 使用者：先全部留白
requires: {core: ">=0.1.0", lib: ">=0.1.0"}
optional: {}
covers:
  - skills/wiki-init/
  - skills/wiki-adopt/
  - commands/wiki-init.md
  - commands/wiki-adopt.md
  - scripts/init_vault.py
  - scripts/skeleton_check.py
  - scripts/adopt.py
install:
  templates: [.skeleton-policy, wiki/meta/init-history.md]
  hooks: []
  manifest_keys: []
uninstall:
  keep_user_data: true
tests:                       # 階段 1 可空；C7 登記（U2 會擋它變「可用」）
check:                       # 階段 1 可空；guard 改彙整器後才有
claude_md: claude.md         # 檔可空：CLAUDE.md 的組裝是 GOV-001 §3 的範圍
---

# init

建 vault 骨架與骨架對帳。只擁有對帳機制，不擁有任何樣板檔的內容。

> 開發狀態與索引在 vault 的 `raw/modules/init/README.md`，本檔只放技術規格（契約 §2）。
