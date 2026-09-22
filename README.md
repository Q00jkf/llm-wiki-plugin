# LLM Wiki

以資料溯源為核心的 Obsidian 知識庫系統，打包成 Claude Code plugin。

**一句話：raw/ 是真相，wiki/ 是索引。索引可以重建，真相不能。**

---

## 三個特點

### 1. wiki 只存指標，不抄會變動的內容

規格數值、pin 表、量測數據、單價 —— **不抄進 wiki**。wiki 只寫「有什麼、在哪裡、哪一頁」，要數值就當場開正本。

抄一份 = 正本改了它不會跟著改 = 遲早變成錯的，而且沒有人會發現。

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

需要 Python 3（只用標準函式庫，無外部相依）。

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
| `SessionStart` | ① 量測 vault，注入對應深度的指導 ② 快照檔該整理了嗎（`tidy_check --quiet`）③ 日程窗口（逾期／今天／7 天內）。不是 vault 就完全安靜 |
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
