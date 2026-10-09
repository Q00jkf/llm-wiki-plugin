# wiki-role：角色卡與接手

為什麼：session 沒有跨視窗記憶，ListAgents 名稱在重開或 `/clear` 後也會變（只有使用者能 `/rename`，session 改不了自己的名字）。
角色卡把「這個角色是誰、要讀什麼、做到哪」固定在 vault 裡，新 session 照卡接手；主管從卡上的 `agent` 欄對到現在的 ListAgents 名稱。

腳本：`python "${CLAUDE_PLUGIN_ROOT}/scripts/role_cards.py" <子指令>`（以下簡稱 `role_cards.py`），在 vault 內執行。

## 角色卡

位置 `wiki/meta/roles/<角色>.md`，範本 `Templates/角色卡模板.md`。

| 段 | 誰維護 | 內容 |
|---|---|---|
| frontmatter `role`／`office_*` | 使用者或主管 | 角色名、辦公室名牌／職稱／team |
| frontmatter `agent`／`taken` | **只由 `role_cards.py claim` 寫** | 目前持有者的 ListAgents 名稱、接手時間 |
| `## 定義` | **使用者或主管**；持有者不改 | 職責範圍、必讀（最多 5 份）、守門腳本 |
| `## 進行中事項` | 持有者，收工時整段覆寫 | 最多 10 行，做完就刪、不留 ✅；細節寫「去哪看」 |

🔴 持有者發現「定義」不對（必讀過時、職責變了）→ 回報使用者或主管，不自己改。

## 🔑 一件事只有一個家（省 token、不老化）

| 資訊 | 唯一的家 | 角色卡怎麼寫 |
|---|---|---|
| 工作進度、卡點、逐份文件狀態 | 資料夾 `_README.md` ③④ | 不抄；「進行中事項」用 `[[raw/X/_README#③ 🔴 現在卡在哪]]（哪一件）：做到哪、下一步` 指過去 |
| 資料夾邊界（做什麼、不做什麼） | `_README.md` ② | 「負責資料夾：[[raw/X/_README]]」一句 |
| 現在誰在線、檔案佔用、待裁示 | `wiki/meta/coordination.md` | 不寫；接手報到時主管回覆跟你有關的 |
| 角色的職責、必讀、守門腳本、個人做到哪 | **角色卡** | 本卡 |

指標用 Obsidian 連結。Obsidian 只在**從 Obsidian 裡**搬檔／改名時自動改連結 —— Claude 用指令搬、或 git 拉下來的改動它不知道；
指到「第幾列」也會在前面的列刪掉後錯位。所以：連結指**檔案或固定的段落標題**，哪一件用文字寫；
`role_cards.py check` 檢查每個連結的檔案與 #標題還在不在（`/wiki-doctor`、收工都跑）。**斷了只回報，不自動猜新位置。**

---

## take：接手（「你是 <角色>，接手」）

1. **讀卡**：`wiki/meta/roles/<角色>.md`。沒有這張卡 → 告訴使用者，問要不要 `new`；不要自己猜職責。
2. **查前一位持有者**：`ListAgents`。
   - 卡上的 `agent` **還在名單上、而且不是你** → **停下來問使用者**：「<角色> 目前由 <agent> 持有且在線，要我接手嗎？」
     不能兩個 session 同時頂同一個角色（進行中事項會互相覆寫）。使用者說接手才往下。
   - 不在名單、或是空的 → 往下。
3. **估成本**：`role_cards.py cost <角色>`，記下合計 token。
4. **只讀必讀清單**：卡＋「必讀」列的檔；`_README.md` 只讀 ③④（邊界 ② 要動手時再看）。
   **不翻 `wiki/log.md`、不讀 `hot.md`、不讀 `coordination.md`** —— 跟這個角色有關的部分已經在 `_README` 或會由主管在報到時回給你。
   有找不到的檔、`role_cards.py check` 報斷掉的連結 → 照實回報使用者，不自己猜位置。
5. **跑守門腳本**（卡上有寫才跑），結果記下。
6. **登記持有者**：`role_cards.py claim <角色> <你的 ListAgents 名稱>`（名稱取自 `ListAgents` 的「This session is X」）。
7. **辦公室（選裝）**：有 `mcp__pixel-office__office_profile`（沒看到就 `ToolSearch("select:mcp__pixel-office__office_profile")` 確認一次；查無＝沒裝，跳過）→
   `office_profile(agent=<你的 ListAgents 名稱>, name=<office_name>, title=<office_title>, team=<office_team 或 off>)`。
8. **向主管報到**（協作模式且主管在線；主管是誰見 `wiki/meta/coordination.md`）：
   ```
   接手：<角色>（ListAgents=<你的名稱>，前一位 <舊 agent 或 無>）
   進行中：<進行中事項前 3 行>
   ```
   主管會回覆跟你有關的佔用與待裁示；照它做。**主管不在線** → 改讀 `wiki/hot.md` 最上面一塊今日結論（只讀一塊），再開始。
9. **回報使用者**（三行內）：接手了什麼角色、讀了哪些檔（約多少 token）、進行中事項第一件與守門腳本結果。

> 建議但非必要：使用者先在新視窗 `/rename <角色>`，ListAgents 名稱就跟角色名一致、好認。沒改名也能接手 —— 卡上記的是實際名稱。

## list：角色清單（主管派工、改名後對人）

`role_cards.py list` → 再 `ListAgents` 核對每個 `agent` 是否在線，輸出（「注意」欄有數字就跑 `role_cards.py check` 看細節）：

| 角色 | 持有者 | 在線 | 接手 | 進行中 |
|---|---|---|---|---|

持有者不在線＝角色空著，等使用者開新視窗接手。主管傳訊息給某角色時，用這張表的「持有者」當 `SendMessage` 的 `to`。

## new：建卡

`role_cards.py new <角色>` → 照使用者給的內容填「定義」段與 `office_*`。
🔴 建新文件只有使用者能核可：使用者明說要建這個角色才做。必讀超過 5 份就請使用者精簡。

## save：更新進行中事項（wiki-end 呼叫）

本 session 持有角色（卡上 `agent`＝你的 ListAgents 名稱）時：

1. **新的卡點先進 `_README`**：今天發現、屬於某資料夾的卡點 → 寫進該 `_README.md` ③（協作模式由主管寫：回報主管「哪一列改成什麼」）。
2. 重寫 `## 進行中事項` 整段：每行 `[[_README 連結#段落]]（哪一件）：做到哪、下一步`；不屬於任何資料夾的事才整句寫（40 字內）。做完的刪掉，**最多 10 行**。
3. 只改這一段，不動「定義」與 frontmatter。
4. `role_cards.py check --quiet`：有斷掉的連結或「疑似抄了 _README」就修正後再 commit。
5. commit 這張卡（和當天其他自己的檔一起）。

主管收工（`wiki-day` 的 `end-manager.md`）時讀各卡的進行中事項彙整，不改別人的卡。
