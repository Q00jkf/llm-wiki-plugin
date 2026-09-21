---
description: 知識庫現況：成熟度、老化訊號、下一步建議。
---

1. 跑 `python "${CLAUDE_PLUGIN_ROOT}/scripts/vault_state.py"`
1b. 跑 `python "${CLAUDE_PLUGIN_ROOT}/scripts/coach.py"`，把它印的那一項當「下一步」回給使用者（只講這一件；與 `/wiki-coach` 同一份判斷，不兩套漂掉）
2. 讀 `wiki-core` skill，依成熟度決定回覆深度：
   - `absent` → 說明如何初始化，並問使用者要不要現在建骨架
   - `seed` → 講解架構與原則，推薦下一步做什麼
   - `growing` → 簡短現況 + 提醒建索引與 lint
   - `mature` → **只報老化訊號**，不解說架構
3. 有老化訊號 → 讀 `wiki-doctor` skill，說明每項該怎麼處理（不要直接動手刪）
