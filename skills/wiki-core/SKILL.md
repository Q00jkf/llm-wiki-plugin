---
name: wiki-core
description: "LLM Wiki 知識庫系統的架構與鐵律。任何涉及本 vault 的知識庫操作（ingest／查詢／建頁／整理／判斷該不該寫進 wiki）都先讀這份。也用於回答「這個系統怎麼運作」「我該把東西放哪」「為什麼不能直接抄進 wiki」。Triggers on: wiki 架構, 知識庫怎麼運作, 這要放哪, 系統原則, wiki-core, 這個 vault 怎麼用。"
---

# LLM Wiki — 系統核心

**一句話：raw/ 是真相，wiki/ 是索引。索引可以重建，真相不能。**

---

## 三條鐵律（違反就會產生「看起來有、其實錯」的垃圾）

### R1　wiki 不是第二個真相來源

會變動的內容**不抄進 wiki** —— 規格數值、pin 表、量測數據、單價、庫存、版本號。
wiki 只寫：**有什麼、在哪裡、哪一頁、怎麼找**。要數值就當場開正本。

抄一份 = 正本改了它不會跟著改 = 遲早變成錯的，而且沒有人會發現。

> 例外：已凍結不會再變的文件（結案報告、出版書籍），可做完整摘要。

### R2　所有資訊標來源

| 標記 | 用在 |
|------|------|
| `[📚 書名, Ch.X p.XX]` | 資料庫內的書 |
| `[📄 文件名, p.XX]` | 資料庫內的文件 |
| `[⚠️ 非資料庫：訓練資料]` | Claude 記憶 |
| `[⚠️ 非資料庫：網路，來源 URL]` | 查來的 |
| `[⚠️ 非資料庫：推導]` | 算出來的 |

查不到就說「資料庫中無足夠資料」。**不得用訓練資料假裝是書中內容。**

### R3　要跨 session 存活的東西必須落盤

寫在對話裡等於沒寫。落盤三處，依取用速度排序：
**① commit message → ② 該資料夾的 `_README.md` → ③ `wiki/log.md`**

---

## 三條寫檔規則（兩個成熟 vault 各踩過一次才定下來的）

### W1　寫進檔案的數字必須綁日期

「現價 83」到三個月後就是錯的，而且錯得像對的。寫 `2026-09-21 收 83`，不寫 `現價 83`；
frontmatter 不放 `current_*` 這種宣稱「現在」的欄位，改 `xxx_at_draw` ＋ `xxx_date`。
條件式規則用時間中性寫法（「當日收盤價落入…」）。

### W2　待辦做完就刪，不留 ✅

留著的已完成項會在下個 session 被當成未完成再報一次、再查一輪。
過程與結論寫進 `wiki/log.md`（那是歷史），待辦清單只留還沒做的。
狀態欄已表達的事不另寫紀錄（`status: watching` 就不必記「某日決定不買」）。

### W3　手寫清單必標權威來源

任何機器能推導的清單（產品清單、腳本清單、表單張數、模組數）寫在規則層都會漂。
寫了就在旁邊標「本清單會漂，以 `{真相來源}` 為準」，並讓腳本從真相來源推導對帳。
規則帶 `（v日期，使用者裁示）`＋Why＋實例 —— 沒有日期與原因的規則，三個月後沒人知道還算不算數。

---

## 目錄結構

```
raw/                  原始檔（人維護，Claude 原則上唯讀）
  .manifest.json      ← ingest 紀錄 + 外部 repo 註冊表 + config
wiki/                 Claude 維護的知識層
  index.md            全局目錄
  hot.md              最近上下文（每 session 先讀，輪替制 ≤150 行）
  log.md              操作日誌（只增不減 → 只能 Grep，不可整份讀）
  repos.md            外部 repo 總覽
  catalog/            文件目錄卡（書 / 文件 / spec / 報告）
  topics/ concepts/   主題索引（多產品時依產品分子資料夾）
  questions/          查詢結果
  projects/           開發專案（需求→設計→進度→測試→追溯）
  agenda.md           日程唯一真相來源（一行一事，agenda.py 讀寫）
  ops/                本 vault 的規則模組（ingest／query／naming／collab／rulings）
  meta/               coordination.md（多 session 狀態）、_guard-status.json（守門留痕）、folds/
Templates/            資料夾模板（_README模板、AI對話紀錄模板、_folder-template）
raw/{名稱}/_README.md 每個工作資料夾的執行節點（見下）
```

> 檔案**不必搬進 raw/**。散在各處的專案用 `/wiki-repo add` 掛進來，檔案留原地。

---

## 系統會自己換檔（不需要選等級）

SessionStart 時 `vault_state.py` 量測 vault，依成熟度給不同深度的指導：

| 成熟度 | 判準 | 系統行為 |
|--------|------|---------|
| `seed` | < 20 頁 | 講解架構與原則、推薦下一步 |
| `growing` | 20–100 頁 | 少量提示，提醒建索引與 lint |
| `mature` | > 100 頁 | **不解說**，只在有老化訊號時出聲 |

**老化訊號獨立於成熟度**，任何階段都可能出現：log 過大、單頁過大、hot 沒輪替、健檢過期、來源檔消失、repo 路徑失效。

> 🔑 為什麼不讓人自己選等級：等級是自陳的，選了「入門」的人三個月後還在入門。
> vault 的成熟度可測且會自己長大，人的等級不可測且會騙。

---

## 指令

| 指令 | 做什麼 |
|------|--------|
| `/wiki` | 現況：成熟度、老化訊號、下一步建議 |
| `/wiki-ingest [路徑]` | 建 catalog 卡。路徑可為 `raw/...` 或 `{alias}::{repo內路徑}` |
| `/wiki-query [問題]` | 查詢並附來源引用 |
| `/wiki-repo` | 管理外部 repo（add／list／scan／remove） |
| `/wiki-doctor` | 老化健檢：老化訊號＋孤立頁／死連結，列出該處理的項目 |
| `/wiki-coach [問題]` | 不知道下一步／卡住／這樣對嗎 → 看 vault 現況，只講一件該做的事 |
| `/wiki-new <名稱>` | 開新資料夾：`_README` 執行節點＋topic stub，更新 index／log |
| `/wiki-agenda [add…\|done…\|--ics\|--notify]` | 日程：逾期／今天／7 天內；匯出 ics／Telegram 文字 |
| `/wiki-collab [status\|takeover\|wrapup]` | 多 session 主管：登記、派工、佔用、收尾 |
| `/wiki-fold [k]` | 把 log.md 最舊 2^k 條摺成一頁摘要 |
| `/wiki-adopt` | 本來就有 wiki、想接上 plugin：撞名分析＋搶救裁示後才刪 vault 版 |

---

## 效率規則（照做能省一個數量級的 token）

1. **Hash 優先**：ingest 前先算 hash 比對 manifest，存在就跳過，不要讀檔
2. **Grep 定位再切片讀**：改現有頁先 Grep 取行號，再 `Read` 帶 `offset`/`limit`，不整頁讀
3. **hot.md 夠用就不讀概念頁**
4. **不是每份素材都要建卡**：物流／行程／通用外部標準／重複副本 → 留在 raw/ 就好
5. **大檔一律 Grep 或 tail**，不整份讀（有 PreToolUse 守門，但它是減速丘不是保證）

---

## 多人／多 session

- 開工前 `ListAgents` 看有沒有 peer 在同一 vault
- 動共用檔（`wiki/log.md`、多人共寫的表）前先講一聲 —— **檔案系統沒有鎖，後存檔的會無聲覆蓋**
- commit 用自己的 session 名當 author：`git -c user.name="<session名>" commit ...`
- 🔴 **非 `raw/` 的路徑必標擁有者**：絕對路徑只在記錄者那台機器有效。`/wiki-repo add` 會自動記錄擁有者與 remote 狀態
- 有主管 session 時先跟主管登記；主管的權責、派工單、收尾流程、`coordination.md` 格式 → `wiki-collab` skill
- **`_README.md` ＝ 該資料夾的執行節點**：使用者只看它確認進度。只寫當前狀態（歷程進 `wiki/log.md`），③「卡在哪」只列未解決、解決即刪（刪前 grep log.md）。有主管時由主管維護，peer 回報欄位級變更。模板 `Templates/_README模板.md`，新夾用 `/wiki-new`

---

## 日程

日程一律在 `wiki/agenda.md`，不另建提醒清單、不寫進 hot.md。使用者說「X 日有會／要交件／每月 D 日做 Y」→ `wiki-agenda` skill 的 `add`；做完 `done`。
外部日曆（ics／Telegram／Notion）是視圖，只從 agenda.md 單向產出。

---

## 守門腳本（exit 一律 0，只列候選不擋 git）

- 開場 `tidy_check.py --quiet`：快照檔（`maintenance: rolling|transactional|append-only`）該整理了嗎（`frozen` ＝凍結紀錄，只驗宣告不掃）
- 問資料現況前 `stale_check.py raw/…`：hash 不在 manifest ＝ wiki 可能過期
- append log 後 `log_index.py --apply`：標記由內容推導，grep 只撈 `<!-- log … -->` 行
- log 太長 `/wiki-fold`：最舊 2^k 條摺成 `wiki/folds/`，原文不竄改
- 完整跑過會留痕 `wiki/meta/_guard-status.json`；太久沒跑 → `vault_state` 報「守門失聯」
- 不知道下一步做什麼 → `/wiki-coach`

---

## 查證與防錯原則

| 原則 | 說明 |
|------|------|
| **兩個訊號互相驗證** | 單一來源說「沒有」不算數。換另一支腳本／另一個位置再查過才能說查無 |
| **回答時講出查了哪幾處** | 範圍講明了，被指出遺漏時只要限縮範圍，不必推翻整個結論 |
| **內容自證有否決權** | 文件內文引用了某份資料，它必然**晚於**那份資料 —— 這條可以推翻任何日程表 |
| **狀態一律現算，不手維護** | 文件只寫「怎麼做」；狀態靠掃資料夾／算 hash 得到。手維護的狀態表，下次沒更新就是**假訊號** |
| **`--check` 模式當守門** | 任何規約都配一支「掃一遍、印出不合規、給 exit code」的腳本 |
| **防呆放在人正在決定的位置** | `--check` 是**事後**攔。每個資料夾放三行 `_README.md`：放什麼／檔名長怎樣（附一個真實範例）／狀態怎麼變 |

---

## 工具怎麼選：skill 還是腳本

| 形式 | 判準 |
|------|------|
| **腳本** | 輸入輸出固定、**能為它寫 `--check`／assert**；錯了會**靜默產生錯資料** → 必須是腳本 |
| **skill** | 需要判斷順序與「為什麼」；規則會隨經驗演化，且下一個人需要知道它**為何存在** |
| ⛔ **不可寫在 skill** | **任何帶頻率的規則**（「每週查一次」）MUST 有實際欄位記錄上次執行時間，否則每次都判定「剛做過」而**永不執行**（本 plugin 的 `_guard-status.json` 就是為這條存在） |

- 一句話：**腳本封裝「動作」，skill 封裝「判斷依據」。**
- 最好的形態是**混合**：skill 負責判斷與對話，確定性部分丟腳本 —— skill 短、腳本可單獨測。
- **skill 裡要寫「事故記錄」** —— 規則告訴人做什麼，**故事告訴人邊界在哪**。

---

## 判斷：這東西該不該進 wiki？

```
會再變動嗎？
├─ 會 → 只建指標卡（身分／版本／TOC／怎麼找），數值留正本
└─ 不會 → 可做完整摘要

有人會查它嗎？
├─ 不會（行程、訂餐、重複副本）→ 留在 raw/，不建卡
└─ 會 → 建卡

它已經有別的真相來源嗎？（xlsx 主檔、資料庫、外部系統）
└─ 有 → 寫腳本查，不要抄進 wiki
```
