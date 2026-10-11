---
module: collab
prefix: COLLAB
category: feature
version: 0.1.0
bundles: []
owner:                       # 2026-10-11 使用者：先全部留白
requires: {core: ">=0.1.0", lib: ">=0.1.0", agenda: ">=0.1.0"}
optional: {office: ">=0.1.0"}
covers:
  - skills/wiki-collabteam/
  - skills/wiki-day/end-manager.md
  - scripts/role_cards.py
  - scripts/occupancy_check.py
install:
  templates: [wiki/ops/collab.md, wiki/meta/coordination.md, wiki/meta/roles/, Templates/角色卡模板.md]
  hooks: []
  manifest_keys: []
uninstall:
  keep_user_data: true
tests:                       # 階段 1 可空；C7 登記（U2 會擋它變「可用」）
check:                       # 階段 1 可空；guard 改彙整器後才有
claude_md: claude.md         # 檔可空：CLAUDE.md 的組裝是 GOV-001 §3 的範圍
---

# collab

多 session 協作：主管派工、角色卡、開會、佔用登記。只管同一台機器的 session。

> 開發狀態與索引在 vault 的 `raw/modules/collab/README.md`，本檔只放技術規格（契約 §2）。
