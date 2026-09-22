# {{name}}

**系統：** `llm-wiki` plugin 提供 skills／commands／hooks／scripts。
本檔只放**這個 vault 專屬**的東西 —— 升級 plugin 不會覆蓋它。
⚠️ 本檔超過 ~150 行就把按需的規則拆到 `wiki/ops/`，在最下方「規則模組索引」留指標（`/wiki-doctor` 會提醒）。

---

## 這個 vault 是什麼

{{domain}}

---

## 專屬術語／縮寫

<!-- 讓 Claude 不必每次問「這是什麼意思」 -->

| 縮寫 | 全稱 | 說明 |
|------|------|------|
|      |      |      |

---

## 資料夾用途（raw/ 底下怎麼分）

<!-- 系統不預設分類，你自己定。定了 Claude 就會照做。 -->
<!-- /wiki-new 建夾後 MUST 在這裡加一列（腳本只提醒不代寫） -->

| 資料夾 | 放什麼 |
|--------|--------|
| `raw/` |        |

---

## 查詢路由（問題 → 去哪查）

<!-- 有結構化真相來源（xlsx／資料庫／資料夾）的問題，寫腳本現算，不讀 wiki 頁 —— wiki 頁一定過期 -->
<!-- 判準：答案會不會因為某個檔案被改而改變？會 → 腳本；不會 → wiki 頁 -->

<!-- 一種問題一條路。有腳本的寫腳本名；「查無的條件」寫死：一支腳本 0 筆不等於沒有 -->

| 問題類型 | 去哪（腳本／檔） | 什麼情況才能說「查無」 |
|---|---|---|
| 最近在做什麼 | `wiki/hot.md` | — |
| 某份文件講什麼 | `wiki/catalog/` 卡 → 數值回正本（卡上「正本各頁」表定位） | 卡沒有、`raw/` 也 find 不到 |
| XX 到哪了／卡在哪（進度） | 該夾 `_README.md`；沒有就**問我** | 不讀舊狀態頁、不推論 |
|  |  |  |

---

## 🔴 鐵律／裁示（最近 5 條；全文在 `wiki/ops/rulings.md`）

<!-- 格式：一句話規則（v日期，使用者裁示）。Why 與實例寫在 rulings.md，這裡只留一句 -->
<!-- 超過 5 條就把最舊的搬去 rulings.md —— 本區大小固定，才不會每 session 越載越多 -->

-

---

## ⚠️ 踩過的雷（最近 5 條；全文在 `wiki/ops/rulings.md`）

<!-- 格式：不要做 X → 改做 Y（日期）。代價與經過寫在 rulings.md -->

-

---

## 我的工作習慣

-

---

## Session 開始／結束

**開始**：讀 `wiki/hot.md` → 需要更多背景才讀 `wiki/index.md`。開場 hook 已印成熟度／快照整理／日程窗口，有 🔴 提一句。不知道下一步 → `/wiki-coach`。
**結束**：更新 `wiki/hot.md`「上次重大操作」（讓下次知道停在哪）；**待辦做完就刪，不留 ✅**；日程一律 `/wiki-agenda add`，不寫進 hot.md。
**每次動檔**：回覆末行列 `已寫入：` 路徑，`.md` 用 Obsidian `open … newtab` 開給我；引用一律指 `raw/` 正本或 alias 路徑，不指 wiki 卡（`wiki-core` R2／R4）。

---

## 參考文件索引

| 文件 | 用途 |
|---|---|
| `wiki/hot.md` | 最近上下文（每 session 先讀） |
| `wiki/index.md` | 全局目錄 |
| `wiki/log.md` | 操作日誌（只能 Grep；`log_index.py --query` 查） |
| `wiki/agenda.md` | 日程唯一真相來源（設計見 `wiki/meta/agenda-system.md`） |
| `wiki/meta/coordination.md` | 多 session 當前狀態（主管維護） |
| `Templates/_README模板.md` | 資料夾執行節點（進度儀表板）模板；新夾用 `/wiki-new` |

---

## 規則模組索引（按需讀，不在開場載入）

| 我要做… | 讀 |
|---|---|
| ingest 這個 vault 的例外（哪些不建卡、圖片、批次） | `wiki/ops/ingest.md` |
| 查東西：完整路由表、scope 規則、腳本清單 | `wiki/ops/query.md` |
| 命名／編號／版次／frontmatter 必填 | `wiki/ops/naming.md` |
| 多 session：共用檔、分工、主管制入口 | `wiki/ops/collab.md`（流程見 plugin `wiki-collab`，狀態見 `wiki/meta/coordination.md`） |
| 裁示與踩雷的全文（Why、實例、代價） | `wiki/ops/rulings.md` |
| 開新資料夾／`_README` 怎麼寫／取用副本夾 | plugin `wiki-new` skill |
| 日程怎麼記／匯出 | plugin `wiki-agenda` skill |

空的模組不佔 token（沒人會讀）；寫滿了本檔也不會變長。

> 系統原則（資料溯源、wiki 只存指標、成熟度分級、數字綁日期）在 plugin 的 `wiki-core` skill，
> 不必抄到這裡 —— 抄了就會跟 plugin 漂掉。
