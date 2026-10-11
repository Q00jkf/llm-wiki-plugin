---
module: knowledge
prefix: KNOW
category: base
version: 0.1.0
bundles: [基本包]
owner:                       # 2026-10-11 使用者：先全部留白
requires: {core: ">=0.1.0", lib: ">=0.1.0", repo: ">=0.1.0"}
optional: {}
covers:
  - skills/wiki-ingest/
  - skills/wiki-query/
  - skills/wiki-fold/
  - commands/wiki-ingest.md
  - commands/wiki-query.md
  - commands/wiki-fold.md
  - scripts/stale_check.py
  - scripts/log_index.py
  - scripts/wiki_fold_parse.py
install:
  templates: [wiki/catalog/, wiki/topics/, wiki/questions/, wiki/ops/ingest.md, wiki/ops/query.md, wiki/ops/naming.md, Templates/AI對話紀錄模板.md]
  hooks: []
  manifest_keys: [sources]
uninstall:
  keep_user_data: true
tests:                       # 階段 1 可空；C7 登記（U2 會擋它變「可用」）
check:                       # 階段 1 可空；guard 改彙整器後才有
claude_md: claude.md         # 檔可空：CLAUDE.md 的組裝是 GOV-001 §3 的範圍
---

# knowledge

raw → wiki 的編譯與查詢。卡由 ingest 建、query 讀，不可分裝。

> 開發狀態與索引在 vault 的 `raw/modules/knowledge/README.md`，本檔只放技術規格（契約 §2）。
