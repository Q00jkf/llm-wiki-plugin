---
description: 開新工作資料夾（複製 Templates/_folder-template/ 到 raw/<name>/）並在 wiki 登錄：_README 執行節點、topic stub、index、log。
argument-hint: "<name> [--under raw] [--sub a,b,c]"
---

Read the `wiki-new` skill and follow it exactly.

目標：`$ARGUMENTS`（未指定名稱時先問使用者，不要自行取名）

先 `--dry-run` 給使用者看，確認後才實際執行。🔴 完成後提醒使用者把新資料夾加進 `CLAUDE.md`「資料夾用途」表。
