---
name: wiki-end
description: "結束工作：本 session 今天的收尾入口——寫 hot.md 今日結論、落盤、commit、交接。單一 session 與協作主管共用；有主管在線時一般 session 只回報主管。使用者明說「結束工作」「收工」「今天到這裡」「收尾」「今天的總結」，或 /wiki-end 時觸發。一般對話裡「總結一下這段」只是要對話內摘要，不觸發。"
---

# wiki-end：結束工作

vault 自訂的收尾項目在 **`wiki/ops/end.md`**（每個 vault 自己寫，本 skill 不管內容）；不存在就跳過並在回報裡說一句。

## 0. 先判斷走哪一段

讀 `wiki/meta/coordination.md` 的「目前主管」，再 `ListAgents` 看他在不在線。

| 情況 | 走 |
|---|---|
| 沒有主管，或主管不在線 | **A. 單一 session** |
| 主管在線，我不是主管 | **B. peer** |
| 我就是主管 | **C. 主管** → `manager.md` |

## A. 單一 session

1. 照 `wiki/ops/end.md` 做 vault 自訂項目。
2. `wiki/log.md` 最上方補今天的條目（已寫過就不重複），append 後跑 `python "${CLAUDE_PLUGIN_ROOT}/scripts/log_index.py" --apply`。
3. 寫 `wiki/hot.md` 今日結論一塊（格式見下），再依 hot.md 檔頭輪替規則修剪；刪舊塊前先 grep `wiki/log.md` 有記載。
4. 本 session 持有角色（`wiki/meta/roles/` 有卡的 `agent`＝你的 ListAgents 名稱）→ 走 `wiki-role` 的 save，更新該卡「進行中事項」。
5. commit 只 add 自己動過的檔；`git push`。
6. 回報使用者：做完什麼、卡在誰身上、明天第一件事。

## B. peer（協作模式，主管在線）

1. 照 `wiki/ops/end.md` 做 vault 自訂項目中屬於自己的部分。
2. 持有角色 → `wiki-role` save，更新該卡「進行中事項」。
3. commit 自己動過的檔（含角色卡）。
4. `SendMessage` 給主管：今天完成什麼（附 commit sha）、手上還有沒有佔用、遺留什麼。
5. **不寫 hot.md**（多個 session 同時寫會互相覆蓋，由主管統一寫）。

## C. 主管

走 `manager.md`（驗證 → 清理 → 落盤 → push → 交接）。落盤時由主管寫 hot.md 今日結論一塊，彙整所有 peer 的回報。

## hot.md 今日結論格式

```markdown
## YYYY-MM-DD 今日結論（session <名稱>）
- 做完：一句話，附關鍵 commit
- 卡誰：逐項寫對象
- 待使用者：明天第一件事
```

不超過 6 行。細節寫 log，hot.md 只放下一個 session 開場需要知道的事。
