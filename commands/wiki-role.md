---
description: 角色卡：接手專責角色（session 重開或 /clear 後）、列出角色與目前持有者、建卡、收工更新進行中事項。子指令 take｜list｜new｜save。
---

Read the `wiki-role` skill and follow it exactly.

$ARGUMENTS

- `take <角色>`（或使用者說「你是 <角色>，接手」）→ 讀卡、查前一位持有者、只讀必讀清單、登記、報到。
- `list`（預設）→ 角色清單＋在線核對。
- `new <角色>` → 從範本建卡（使用者明說要建才做）。
- `save` → 更新本 session 角色卡的進行中事項（wiki-end 會呼叫）。

🔴 卡上的持有者還在線就先問使用者，不搶角色；「定義」段只有使用者或主管能改。
