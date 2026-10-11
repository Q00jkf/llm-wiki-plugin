---
module: folder
prefix: FOLDER
category: feature
version: 0.1.0
bundles: []
owner:                       # 2026-10-11 使用者：先全部留白
requires: {core: ">=0.1.0", lib: ">=0.1.0"}
optional: {}
covers:
  - skills/wiki-new/
  - commands/wiki-new.md
  - scripts/new_folder.py
  - scripts/audit_copy_check.py
install:
  templates: [Templates/_folder-template/, Templates/_README模板.md]
  hooks: []
  manifest_keys: []
uninstall:
  keep_user_data: true
tests:                       # 階段 1 可空；C7 登記（U2 會擋它變「可用」）
check:                       # 階段 1 可空；guard 改彙整器後才有
claude_md: claude.md         # 檔可空：CLAUDE.md 的組裝是 GOV-001 §3 的範圍
---

# folder

開新資料夾與執行節點（_README 進度儀表板）。

> 開發狀態與索引在 vault 的 `raw/modules/folder/README.md`，本檔只放技術規格（契約 §2）。
