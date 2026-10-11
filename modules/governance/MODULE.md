---
module: governance
prefix: GOV
category: internal
version: 0.1.0
bundles: []
owner:                       # 2026-10-11 使用者：先全部留白
requires: {}
optional: {}
covers:
  - CLAUDE.md
  - CHANGELOG.md
  - README.md
  - .claude-plugin/plugin.json
  - .claude-plugin/marketplace.json
  - hooks/hooks.json
  - docs/
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

# governance

研發流程與 plugin 端的治理檔。不出貨給客戶。

> 開發狀態與索引在 vault 的 `raw/modules/governance/README.md`，本檔只放技術規格（契約 §2）。
