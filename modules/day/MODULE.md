---
module: day
prefix: DAY
category: base
version: 0.1.0
bundles: [基本包]
owner:                       # 2026-10-11 使用者：先全部留白
requires: {core: ">=0.1.0", lib: ">=0.1.0"}
optional: {collab: ">=0.1.0"}
covers:
  - skills/wiki-day/SKILL.md
  - skills/wiki-day/start.md
  - skills/wiki-day/end.md
install:
  templates: [wiki/ops/start.md, wiki/ops/end.md]
  hooks: []
  manifest_keys: []
uninstall:
  keep_user_data: true
tests:                       # 階段 1 可空；C7 登記（U2 會擋它變「可用」）
check:                       # 階段 1 可空；guard 改彙整器後才有
claude_md: claude.md         # 檔可空：CLAUDE.md 的組裝是 GOV-001 §3 的範圍
---

# day

一天的開工與收工（單人路線）。peer／主管兩路由 collab 擴充。

> 開發狀態與索引在 vault 的 `raw/modules/day/README.md`，本檔只放技術規格（契約 §2）。
