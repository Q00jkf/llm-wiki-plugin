---
module: status
prefix: STATUS
category: base
version: 0.1.0
bundles: [基本包]
owner:                       # 2026-10-11 使用者：先全部留白
requires: {core: ">=0.1.0", lib: ">=0.1.0"}
optional: {}
covers:
  - scripts/vault_state.py
  - scripts/coach.py
  - skills/wiki-coach/
  - commands/wiki.md
  - commands/wiki-coach.md
install:
  templates: []
  hooks: [SessionStart:vault_state.py --brief]
  manifest_keys: []
uninstall:
  keep_user_data: true
tests:                       # 階段 1 可空；C7 登記（U2 會擋它變「可用」）
check:                       # 階段 1 可空；guard 改彙整器後才有
claude_md: claude.md         # 檔可空：CLAUDE.md 的組裝是 GOV-001 §3 的範圍
---

# status

看狀態給建議：成熟度、老化訊號（讀落盤歷史）、下一步。

> 開發狀態與索引在 vault 的 `raw/modules/status/README.md`，本檔只放技術規格（契約 §2）。
