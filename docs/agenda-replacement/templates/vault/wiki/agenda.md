---
title: 日程（agenda）
type: meta
maintenance: transactional
updated: {{today}}
---

# 日程 — 唯一真相來源

> 一行一事，由 plugin 的 `agenda.py` 讀寫（開場窗口／`add`／`done`／`move`／`dur`／`link`／`--tidy` 歸檔／`--ics`／`--notify`）。設計 → [[meta/agenda-system]]。
> 格式：`日期 [HH:MM[-HH:MM]] 類型 標題 [工期N天] [代號:x] [接:a,b] [屬:x] [完成:MM-DD] [原定:MM-DD] [截止:MM-DD] [進度:N%] [每月D日|每週X|每年MM-DD|每N天] [#tag …] [→ 出處]`；完成的行前綴 `✅`。
> 有工期的行，行首日期是最後一天。前項延誤時，排程引擎自動順延後項，並記進變更紀錄；改期請用 `move`，別手改日期。
> 細節不寫這裡，用 `→` 指回 log／catalog。外部日曆（ics／Telegram／Notion）只從本檔單向產出；甘特圖用 Obsidian 外掛「日程甘特圖」。

<!-- 事件從下一行開始 -->
{{today}}  提醒  熟悉 agenda：python agenda.py --help，然後 done 熟悉  #系統
