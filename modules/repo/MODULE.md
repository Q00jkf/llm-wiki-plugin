---
module: repo
prefix: REPO
category: feature
version: 0.1.0
bundles: [基本包]
owner:                       # 2026-10-11 使用者：先全部留白
requires: {core: ">=0.1.0", lib: ">=0.1.0"}
optional: {}
covers:
  - skills/wiki-repo/
  - commands/wiki-repo.md
  - scripts/repo.py
install:
  templates: []
  hooks: []
  manifest_keys: [repos]
uninstall:
  keep_user_data: true
tests:                       # 階段 1 可空；C7 登記（U2 會擋它變「可用」）
check:                       # 階段 1 可空；guard 改彙整器後才有
claude_md: claude.md         # 檔可空：CLAUDE.md 的組裝是 GOV-001 §3 的範圍
---

# repo

外部 repo 掛載：檔案留原地，vault 只存指標。

> 開發狀態與索引在 vault 的 `raw/modules/repo/README.md`，本檔只放技術規格（契約 §2）。
