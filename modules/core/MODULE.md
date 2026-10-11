---
module: core
prefix: CORE
category: base
version: 0.1.0
bundles: [基本包]
owner:                       # 2026-10-11 使用者：先全部留白
requires: {}
optional: {}
covers:
  - skills/wiki-core/
install:
  templates: [CLAUDE.md, .gitignore, .gitattributes, .claude/settings.json, wiki/index.md, wiki/log.md, wiki/hot.md, wiki/projects/, wiki/ops/rulings.md]
  hooks: []
  manifest_keys: []
uninstall:
  keep_user_data: true
tests:                       # 階段 1 可空；C7 登記（U2 會擋它變「可用」）
check:                       # 階段 1 可空；guard 改彙整器後才有
claude_md: claude.md         # 檔可空：CLAUDE.md 的組裝是 GOV-001 §3 的範圍
---

# core

所有模組共同遵守的契約與 vault 骨架。腳本與 hook 都已移出。

> 開發狀態與索引在 vault 的 `raw/modules/core/README.md`，本檔只放技術規格（契約 §2）。
