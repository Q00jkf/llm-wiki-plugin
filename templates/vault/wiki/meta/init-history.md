---
title: init 升級史
type: meta
updated: {{today}}
---

# init 升級史

> 🔴 本檔由 `skeleton_check.py` 寫，**人不手改**。

每次跑 `/wiki-init <本 vault>`（目標已經是 vault → 升級模式）就 append 一塊，
記的是**實際做了什麼**：補了哪些檔、換了哪些、融合了哪些、跳過哪些。使用者說不要的不寫進來。

**為什麼需要這份**：建骨架是一次性快照，plugin 之後升級，skills 會跟著更新，
但已建好的 vault 那些檔不會 —— 而且沒有東西會發現。這份是那件事的紀錄層：
下次又出什麼怪事，可以直接查「上次融合某個檔的時候動了哪一段」。

當前狀態（骨架停在哪一版、每個檔的 hash）在 vault 根的 `.skeleton.json`，同樣由腳本維護。
