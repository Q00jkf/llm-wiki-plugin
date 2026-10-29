# wiki-role：vault 的角色卡

**卡的格式、接手、檢查點照 pixel-office skill `team` 的 `roles.md`**（卡只放定義、做到哪寫 `checkpoints/`、誰在線由主管記在 `collab.md`）。
這份只寫 vault 多的：腳本、`_README` 指標規則、守門腳本。

腳本：`python "${CLAUDE_PLUGIN_ROOT}/scripts/role_cards.py" <子指令>`（以下簡稱 `role_cards.py`），在 vault 內執行。

| 檔 | 位置 | 誰寫 |
|---|---|---|
| 角色卡 | `.claude/office/roles/<角色>.md`（進 git），範本 `Templates/角色卡模板.md` | 使用者或主管 |
| 檢查點 | `.claude/office/checkpoints/<角色>.md`（不進 git，只往後加） | 持有這個角色的 session |
| 誰在線 | `.claude/office/collab.md`「在線」 | 主管 |

vault 卡比 `team` 多兩段：**`## 用到才查`**（不算必讀，用 Grep 定位到節）、**`## 守門腳本`**（動手前要跑的；沒有寫「無」）。

> 1.16.0 前卡在 `wiki/meta/roles/`、進度寫在卡上「進行中事項」。腳本照讀舊位置；搬：`role_cards.py migrate --dry-run` 給使用者看 → 說好再不帶 `--dry-run` 跑。
> 搬的時候原文一字不改，只重新歸段（沒對到的條目進「邊界」）；「進行中事項」變成檢查點第一筆。搬完請使用者看「邊界」「交付」兩段要不要補。

## 🔑 一件事只有一個家（省 token、不老化）

| 資訊 | 唯一的家 | 卡／檢查點怎麼寫 |
|---|---|---|
| 工作進度、卡點、逐份文件狀態 | 資料夾 `_README.md` ③④ | 不抄；檢查點用 `[[raw/X/_README#③ 🔴 現在卡在哪]]（哪一件）：做到哪、下一步` 指過去 |
| 資料夾邊界（做什麼、不做什麼） | `_README.md` ② | 卡的職責寫「負責資料夾：[[raw/X/_README]]」一句 |
| 現在誰在線、檔案佔用、待裁示 | `.claude/office/collab.md` | 不寫；接手報到時主管回覆跟你有關的 |
| 角色的職責、邊界、必讀、守門腳本 | **角色卡** | 本卡 |

指標用 Obsidian 連結。Obsidian 不索引 `.claude/`，卡上的連結在 Obsidian 裡點不到，但 `role_cards.py check` 照樣檢查；
連結指**檔案或固定的段落標題**，哪一件用文字寫（指「第幾列」會在前面的列刪掉後錯位）。**斷了只回報，不自動猜新位置。**

## take：接手（「你是 <角色>，接手」）

照 `team` 的 `roles.md` §3，vault 多三步：

- 讀卡前：`role_cards.py cost <角色>`，記下合計 token。
- 讀完必讀與最後一筆檢查點：**跑守門腳本**（卡上有寫才跑）。不翻 `wiki/log.md`、不讀 `hot.md`、不讀 `collab.md`。
- 登記與報到：`role_cards.py claim <角色> <你的 ListAgents 名稱>` —— 不寫卡；它印出最後一筆檢查點、collab.md 記的前一位持有者、**已解析好主管的 `office_profile` 那行**與報到對象，照印的跑。
  主管不在線 → 改讀 `wiki/hot.md` 最上面一塊今日結論（只讀一塊），再開始。

回報使用者三行內：接手了什麼角色、讀了哪些檔（約多少 token）、檢查點的下一步與守門腳本結果。

## list：角色清單

`role_cards.py list` → 再 `ListAgents` 核對持有者在不在線（「注意」欄有數字就跑 `role_cards.py check`）。持有者欄來自 `collab.md`「在線」，沒有主管就是「（無人）」。

## new：建卡

`team` 的 `roles.md` §1（從規則產生）或使用者直接給內容 → `role_cards.py new <角色>` 照範本建、填各段。
🔴 建新文件只有使用者能核可。必讀超過 5 份就請使用者精簡。

## save：存檢查點（wiki-day 收工呼叫）

1. **新的卡點先進 `_README`**：今天發現、屬於某資料夾的卡點 → 寫進該 `_README.md` ③（協作模式由主管寫：回報主管「哪一列改成什麼」）。
2. 在 `checkpoints/<角色>.md` **加一筆**（格式見 `team` 的 `roles.md` §4）；「下一步」每行用 `[[_README 連結#段落]]（哪一件）：…` 指過去，不屬於任何資料夾的事才整句寫（40 字內）。
3. `role_cards.py check --quiet`：有斷掉的連結或「疑似抄了 _README」就改這一筆。
4. 不改卡；定義不對 → 回報使用者或主管。檢查點不進 git，不用 commit。

主管收工（`wiki-day` 的 `end-manager.md`）時讀各角色最後一筆彙整，不改別人的檢查點。
