---
module: office
prefix: OFFICE
category: feature
version: 0.1.0
bundles: []
owner:                       # 2026-10-11 使用者：先全部留白
requires: {}
optional: {}
covers:
  - plugins/pixel-office/
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

# office

像素辦公室（獨立 plugin，與 llm-wiki 零共用程式碼）。

> 開發狀態與索引在 vault 的 `raw/modules/office/README.md`，本檔只放技術規格（契約 §2）。
