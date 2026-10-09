---
name: wiki-day
description: "一天的兩端：開工（接上次進度、vault 自訂開工項、向主管報到）與收工（寫 hot.md 今日結論、落盤、commit、交接）。Triggers: 開始工作, 開工, 結束工作, 收工, 今天到這裡, 收尾, wiki-start, wiki-end。（對話裡「總結一下這段」不觸發）"
---

# wiki-day：開工與收工

| 使用者說 | 讀 |
|---|---|
| 「開始工作」「開工」 | `start.md` |
| 「結束工作」「收工」「今天到這裡」「收尾」 | `end.md`（本 session 是主管 → 它會再帶你進 `end-manager.md`） |

**按需讀一份**，不要兩份一起讀 —— 合在同一個 skill 是為了省開場成本，不是要你全部載入。

> 2026-10-09 由 `wiki-start`＋`wiki-end` 合併（使用者裁示）。兩份內容一字未改，只是入口合一。
> 系統層的開場檢查（vault 狀態、日程、tidy、規則對帳）由 SessionStart hook 自動跑，這裡不重複。
