---
title: 多 session 協作
type: ops-rule
updated: {{today}}
---

# 多 session 協作

> 這裡管的是**同一個使用者開多個 Claude session**。多**人**協作走 `wiki-repo`（各自 clone、各自 add、權限看擁有者），不在這份。

> **規則層**，個案不寫這裡。流程與權責見 plugin `wiki-collabteam` skill 的 `collab.md`；**當前狀態**（主管／佔用／待裁示）見 `wiki/meta/coordination.md`。
> 這裡只寫本 vault 的**共用檔清單**與**分工**。空著沒關係。

## 共用檔（動之前 `ListAgents` ＋ 登記佔用）

| 檔 | 誰維護 | 備註 |
|---|---|---|
| `wiki/log.md` | 所有人 append | 只增不減；刪任何快照內容前先 grep 這裡 |
| `wiki/hot.md` | 主管輪替 | ≤150 行 |
| `wiki/meta/coordination.md` | 主管 | 快照，只寫當前狀態 |
| 各資料夾 `_README.md` | 主管 | 執行節點；peer 只回報欄位級建議 |

## 分工

專責角色（職責、必讀、守門腳本、目前持有者）各一張卡在 `wiki/meta/roles/`，`/wiki-role list` 看全部；這裡不重寫。
現在哪個 session 在線、在做什麼 → `wiki/meta/coordination.md`。

## 收尾要跑的本 vault 自訂檢查

<!-- 例：python scripts/xxx.py —— plugin 的 occupancy_check 與 /wiki-doctor 不必列 -->
