# LLM Wiki 設計說明

> 這份是給想知道「為什麼這樣設計」的人。日常使用看 [README](../README.md) 就夠。

**給團隊與 PM 的專案管理系統。** 跑在 Obsidian 上，用 Claude Code 操作。

管**專案／產品線、日程、多 session 分工、散在各處的檔案資產（含多人權限）、公司制度**。
知識庫（`raw/` → `wiki/` 編譯）是其中一個能力，負責「資料要有出處、不抄會變動的東西」。

**一句話：raw/ 是真相，wiki/ 是索引。索引可以重建，真相不能。**

> 名字裡有 wiki，但它不是筆記工具。真實部署長這樣：`raw/` 底下按 11 條產品線
> 與 ISO 制度分，每條線再按 RD／PM／FAE／產線分職能；`wiki/` 的知識層 78 頁，
> 制度／管理／營運層 106 頁。**知識庫是最小的那一塊。**

---

## 給誰用

| 適合 | 不適合 |
|---|---|
| PM／團隊負責人：同時看多條產品線、多個交付 | 個人筆記、日記、讀書摘要 —— 用一般筆記工具就好 |
| 文件散在硬碟各處、各 git repo 裡，不想搬家 | 純程式碼專案 —— 程式有自己的工具鏈，這裡管的是文件 |
| 規格、量測數據、單價會改版，怕抄錯 | 只有一個人、一個資料夾、資料不會變 —— 不需要溯源 |
| 多人（或多個 Claude session）同時動同一批檔 | 想要「全文都在 wiki 裡」的人 —— 這裡刻意不抄 |

一句話判斷：**你的資料有正本、正本會改、而且不只你一個人在動** → 適合。

---

## 它管哪五件事

| # | 面向 | 靠哪些 skill |
|---|---|---|
| 1 | **專案／產品線** | `wiki-new`（開工作資料夾＋`_README` 執行節點＝進度儀表板）|
| 2 | **日程** | `wiki-agenda`（唯一真相來源、開場窗口、`--ics` 匯出、`--notify`）|
| 3 | **多 session 分工** | `wiki-collab`（主管制：登記／派工／回報節奏／撞檔仲裁／收尾）。多**人**不走這裡：同事各自 clone＋`add`，權限看 #4 |
| 4 | **檔案資產與權限** | `wiki-repo`（多來源掛載、可攜路徑、擁有者、寫入權限四級）|
| 5 | **知識庫** | `wiki-core`／`wiki-ingest`／`wiki-query`／`wiki-fold` |

外加維運：`wiki-doctor`（老化健檢）、`wiki-init`／`wiki-adopt`（建置與遷移）、`wiki-coach`（下一步該做什麼）。

### 兩層：內建即有 vs 你要填的

| 層 | 內容 | 怎麼來 |
|---|---|---|
| **內建即有** | 上表五件事的機制、健檢、教練、Read 守門 | plugin 給的，裝上就有；要用就啟用（如第二個 session 開起來就 `/wiki-collab takeover`） |
| **彈性修改** | 管什麼對象、`raw/` 怎麼分、術語、查詢路由、工作習慣、鐵律／踩雷 | `/wiki-init` 問出來，填進該 vault 的 `CLAUDE.md`；之後隨用隨改 |

內建層升級 plugin 就更新；彈性層在 vault 裡，升級不會覆蓋。

---

## 三個特點

### 1. wiki 只存指標，不抄會變動的內容；引用一律指回 `raw/` 正本

規格數值、pin 表、量測數據、單價 —— **不抄進 wiki**。wiki 只寫「有什麼、在哪裡、哪一頁」，要數值就當場開正本。

抄一份 = 正本改了它不會跟著改 = 遲早變成錯的，而且沒有人會發現。

回答時標的來源是 `raw/…` 或 `alias::…` 的路徑與頁碼，不是 wiki 卡。每次寫檔，回覆末行列「已寫入」路徑並用 Obsidian 開給你 —— 你不必記系統的資料夾結構，也能馬上核對它改了什麼。

### 2. 一個 wiki 管理散在各處的多個專案

檔案**留在原地**。適合「幾十個專案散在硬碟上，不想搬進 wiki」的情況。

```bash
/wiki-repo discover D:\            # 掃出候選專案 + 產生批次註冊指令
/wiki-repo add D:\硬體部門\專案A
/wiki-ingest 專案a::doc/spec.docx
```

`discover` 會自動排除程式碼樹、處理 alias 撞名、按 Office 文件數排序。
路徑存的是**可攜 spec**（`${VAR}/`、`~/`、`../`）不是絕對路徑，換機器不會整批失效；
壓不掉的會標紅，並記錄**擁有者與 remote 狀態** —— 別台機器掃到失效時知道去找誰。

**寫入權限依「誰的」分三級**（預設唯讀，`writable` 逐個 alias 開）：

| 級別 | 判準 | MUST |
|---|---|---|
| 🔴 別人的 | remote／owner 不是本人 | 對方同意＋動手前 `git pull`＋完成後 `commit`／`push` |
| 🟡 自己的 vault | 是本人的、有自己的 `CLAUDE.md` | 先讀它的 `CLAUDE.md`、寫它的 `wiki/log.md` |
| 🟢 自己的資料夾 | 是本人的、沒有自己的規則 | 照本 vault 規則 |

> 🔴 **既有的 llm-wiki vault 不能整包掛** —— `add` 偵測到會擋下，要求拆成
> `{名}-raw`＋`{名}-wiki` 雙掛。對方的 `wiki/` 是**已編譯的知識**，重 ingest 等於同一份知識存兩處。
> 只建一張 Tier 1 指標卡；要原文／數值一律回 `-raw`。

### 3. 系統依 vault 成熟度自動換檔，不需要選等級

| 成熟度 | 判準 | 行為 |
|--------|------|------|
| `seed` | < 20 頁 | 講解架構與原則、推薦下一步 |
| `growing` | 20–100 頁 | 少量提示 |
| `mature` | > 100 頁 | **不解說**，只在有老化訊號時出聲 |

老化訊號（log 過大、hot 沒輪替、健檢過期、來源檔消失…）獨立於成熟度，任何階段都會報。

> 為什麼不讓人自己選等級：等級是自陳的，選了「入門」的人三個月後還在入門。
> vault 的成熟度可測且會自己長大，人的等級不可測且會騙。

---

## 安裝

```bash
/plugin marketplace add <這個資料夾的路徑或 git URL>
/plugin install llm-wiki
```

### 前置條件

| 需要 | 版本／說明 |
|---|---|
| Claude Code | 支援 plugin 的版本（`/plugin` 指令存在即可） |
| Python | **3.9+**，只用標準函式庫，無外部相依 |
| git | 建議。vault 本身用 git 記錄；外部來源沒有 git 時仍可掛，但擁有者會記 `unknown` |
| Obsidian | 建議但非必要。所有檔案都是純 Markdown＋wikilink，Obsidian 只是閱讀介面 |
| 作業系統 | Windows／macOS／Linux 皆可；Windows 需注意 `raw/` 行尾（範本已附 `.gitattributes`） |

### 裝完之後，第一次用就這三步

```
/wiki-init                 # 在你要放知識庫的資料夾跑。會問三題，然後產出骨架
/wiki-ingest raw/          # 丟一份文件進 raw/，把它編成 wiki 的第一張卡
/wiki-coach                # 任何時候卡住 → 它看你的 vault 現況，只講一件該做的事
```

**不必先讀完這份 README。** 系統會依 vault 成熟度自動給對應深度的指導：
新 vault 開場會講解架構，長大後就閉嘴，只在有問題時出聲。

> 想知道「為什麼要這樣設計」→ 問 `/wiki-coach`，它只從 `wiki-core` 的規則回答，不會自己編。

---

## 指令

| 指令 | 做什麼 |
|------|--------|
| `/wiki-init [路徑]` | 建立新 vault，引導填出專屬 CLAUDE.md |
| `/wiki` | 現況：成熟度、老化訊號、下一步 |
| `/wiki-ingest [路徑]` | 建 catalog 卡。支援 `{alias}::{路徑}` |
| `/wiki-query [問題]` | 查詢並附來源引用 |
| `/wiki-repo` | 管理外部 repo（discover／add／list／scan／remove／rename／link）|
| `/wiki-doctor` | 老化健檢（含 tidy／stale／log-index／compileall） |
| `/wiki-coach [問題]` | 教練：看 vault 狀態只講下一步一件事；答「為什麼」「這樣對嗎」 |
| `/wiki-new <name>` | 開新資料夾：`Templates/_folder-template/` → `raw/<name>/`，建 `_README` 執行節點＋topic stub |
| `/wiki-agenda [add "…"｜done 關鍵字｜--ics｜--notify]` | 日程：逾期／今天／7 天內窗口；匯出 ics／Telegram 文字 |
| `/wiki-collab [status｜takeover｜wrapup]` | 多 session 主管：三層權責、派工、佔用登記、每日收尾 |
| `/wiki-fold [k]` | 把 log.md 最舊 2^k 條摺成一頁摘要 |
| `/wiki-adopt [vault]` | 既有 vault 接上 plugin：找撞名、搶救裁示／踩雷、刪 vault 自帶舊版 |

### 新 vault 只有薄骨架

`/wiki-init` 把 plugin 的 `templates/vault/` 整棵複製過去（CLAUDE.md、manifest、index／hot／log／agenda、`wiki/ops/` 五個空規則模組、`wiki/meta/coordination.md`、`Templates/`），不複製 skills／commands —— 系統由 plugin 提供，`git pull` 就升級。要改新 vault 長什麼樣，改 `templates/vault/`，不改腳本。

> `wiki/ops/{ingest,query,naming,collab,rulings}.md` 是兩個成熟 vault 各自長出來、高度重複的模組，init 時先把格子建好；CLAUDE.md 的 🔴 裁示／⚠️ 踩雷各只留最近 5 條一句話，全文進 `rulings.md` —— 開場載入量固定。

> 舊做法（每個範本夾帶一整套 skills 拷貝）已實測失敗：同一批範本的 skill 數量
> 分岔成 **18 / 18 / 30 / 31**，而且沒有人發現。拷貝一定會漂。

---

## 自動生效的 hook

| Hook | 做什麼 |
|------|--------|
| `SessionStart` | ① 量測 vault，注入對應深度的指導 ② 快照檔該整理了嗎（`tidy_check --quiet`）③ 日程窗口（逾期／今天／7 天內）④ 規則層對帳（`rules_check --quiet`）。不是 vault 就完全安靜 |
| `PreToolUse(Read)` | 擋掉整份讀 >100KB 的檔，強制切片或 Grep |

> ⚠️ Read 守門是**減速丘不是保證** —— 擋不住 Bash `cat`，也不管 Grep 的回傳量。
> 把它當保證比沒有它更危險。

---

## 腳本（可獨立執行，不經 Claude）

```bash
python scripts/vault_state.py            # 成熟度 + 老化訊號
python scripts/vault_state.py --json     # 機器讀的完整訊號
python scripts/repo.py list              # 外部 repo 一覽
python scripts/repo.py scan              # 掃描變更
python scripts/repo.py rename <舊> <新> --dry-run   # 改 alias，連 sources／doc_index 一起搬
python scripts/repo.py link <source key> <卡片>     # 建完卡登記進 manifest（漏了就是孤兒卡）
python scripts/coach.py                  # 下一步該做的一件事（--all 全列）
python scripts/agenda.py                 # 日程窗口；add／done／--check／--tidy／--ics／--notify
python scripts/tidy_check.py --quiet     # 快照檔該整理了嗎（T0–T8）
python scripts/rules_check.py --quiet    # 規則層漂移：手寫清單 vs 現實、停用頁引用、腳本存在性、逐字重複
python scripts/stale_check.py raw/子路徑 # raw/ 哪些檔 hash 不在 manifest
python scripts/log_index.py --check      # log.md 行內索引（--apply 補齊、--query 查）
python scripts/wiki_fold_parse.py list   # /wiki-fold 後端：列條目／取批次／封存
python scripts/new_folder.py <name> --dry-run   # 開新資料夾（_README 執行節點）
python scripts/audit_copy_check.py <副本夾>     # 取用副本 vs 正本 md5 一致性
python scripts/adopt.py [--sources|--rescue|--diff 名稱]   # 既有 vault 接 plugin 的遷移分析（只偵測不刪）
python scripts/occupancy_check.py --quiet   # 佔用表 vs git author（收尾跑；忽略帳號設 manifest config.occupancy_ignore_authors）
```

---

## 設定

vault 的 `raw/.manifest.json`：

```json
{
  "config": { "big_read_limit_bytes": 100000, "max_slice_lines": 2000 },
  "repos":  { "_self": { "path": ".", "desc": "本 vault" } },
  "sources": {}
}
```

其餘門檻（頁數分級、log 大小、hot 行數、健檢天數）在 `scripts/vault_state.py` 檔頭常數區。

---

## 授權

[MIT](LICENSE) © 2026 呂冠佑、呂筱婕

可自由使用、修改、散布與商用，保留著作權聲明即可。本軟體不附任何擔保。
