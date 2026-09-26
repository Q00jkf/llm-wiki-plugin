---
name: wiki-ingest
description: "把原始檔編譯成 wiki 知識層：建 catalog 卡、更新主題索引、記錄 manifest。支援本地 raw/ 與外部 repo（alias::路徑），依文件是否會變動決定做指標卡或完整摘要。Triggers on: wiki-ingest, ingest, 建卡, 把這份加進 wiki, 編譯到 wiki, 讀這份文件, 批次匯入。"
---

# wiki-ingest：素材 → 知識層

先讀 `wiki-core` 的四條鐵律。**R1（wiki 不是第二個真相來源）決定這裡的每一個判斷。**

---

## Step 0　來源解析

| 輸入 | 解析 |
|------|------|
| `raw/BOOK/x.pdf` | 本 vault |
| `{alias}::docs/x.md` | 查 manifest `repos.{alias}.path`，實際路徑＝`{path}/docs/x.md` |
| `{alias}::` | 該 repo 全部，走批次 |

alias 查不到 → 停下來回報「repo `{alias}` 未註冊，先跑 `/wiki-repo add`」。**不要猜路徑。**

> 🔴 **ingest 對來源一律唯讀**：不在對方目錄建檔、不 commit、不 pull。產物只寫本 vault。
> （這條不受 `writable` 影響 —— 能不能改那個 repo 是另一回事，**ingest 本身永遠不該寫來源**。
> 要改對方的檔，走 `wiki-repo` skill 的「寫入權限三級」。）

---

## 🔴 Step 0.5　憑證檔一律不 ingest

**看起來像憑證的檔，不建卡、不摘要、不把內容寫進任何 wiki 頁。** 發現就停下來回報使用者。

判準（`repo.py` 的 `SECRET_PATTERNS` 是同一份清單）：檔名含 `secret`／`credential`／`password`／`密碼`／`帳密`／`金鑰`，
或是 `.env*`／`id_rsa*`／`*.pem`／`*.pfx`／`*.key`／`.npmrc`／`.netrc`／`*.kdbx`。

**為什麼這條必須在 ingest 這層再擋一次**：`repo.py` 已經在掛載時擋掉了，但那只涵蓋「掛進來的 repo」。
使用者直接 `/wiki-ingest raw/某某/密碼表.xlsx` 是繞過掛載層的 —— 判斷層要自己認得。

🔴 **洩漏鏈是這個系統特有的**：掛別人的目錄 → 讀檔 → 摘要寫進 `wiki/` → `git commit` → `push`。
一般專案沒有這條鏈，所以別處的直覺在這裡不適用。**憑證進了 wiki 頁就等於進了 git 歷史，刪不乾淨。**

## Step 1　Hash 檢查（先做，省最多 token）

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/stale_check.py" --hash "{實際路徑}"
```

🔴 **一律用這支算，不要自己寫 `hashlib.md5(open(...).read())`**（跨平台；也不要用 `certutil`——mac／Linux 沒有）。
文字檔必須先把 CRLF 正規化成 LF 再 hash：Windows + git `core.autocrlf` 下，任何 `checkout`／`clone`
都會改寫行尾，內容沒變但 md5 變了，整個 `raw/` 會被誤判成需要重編，而 `git status` 顯示乾淨、看不出來。
定義在 `scripts/_lib/filehash.py`（2026-09-21 驗收 #19）。

manifest 中 hash 存在 → **跳過，不讀檔**，回報「已 ingest（未變更）」。
hash 不同 → 是**更新**，走 supersession（見 Step 4），不是重新建卡。

---

## Step 2　決定做哪一層（最關鍵的判斷）

```
這份文件之後還會被改嗎？
├─ 會 → 先分它是哪一型（成熟 vault 實測的三型，處理法不同）
│   ├─ 版次型（規格、ICD、SOP：改了就出新版次）
│   │    → Tier 1 指標卡：身分／版本／TOC／正本各頁，🔴 不放數值
│   │      版本歷程＝資料夾裡的 dated 檔案集合（新版另存、舊版保留），manifest doc_index 接替
│   ├─ 登錄簿型（總覽表、名冊、料號主檔：一份持續更新，只有版次沒有「生效日」）
│   │    → 只建一張指標卡說「在哪、欄位是什麼」；🔴 內容一律腳本現查（xlsx 用腳本，Grep 撈不到）
│   │      檔名不帶日期（識別碼不含隨版次變的要素）
│   └─ 狀態／數量型（有幾份、簽了沒、誰借了、逾期哪張）
│        → 🔴 不建頁。腳本掃資料夾現算；規則頁只寫「怎麼填」，不寫使用紀錄
└─ 不會（出版書籍、結案報告、已凍結版本）
     → 完整摘要卡：章節結構、關鍵概念索引、頁碼

這份值得建卡嗎？（/wiki-coach 會問你這兩題）
├─ 有人會查它嗎？不會（行程、訂餐、重複副本、衍生檔）→ 留在 raw/，不動 wiki
├─ 查它時需要的是「找得到」還是「讀得懂」？只要找得到 → 指標卡就夠，不要摘要
└─ 都是 → 建卡
```

**不確定就問使用者**，不要自行判斷後大量建頁。

---

## 🔴 PDF 怎麼讀（第一次用最常卡在這）

`Read` 對 PDF **不理會 `offset`／`limit`** —— 帶 `limit=50` 一樣會回整份文字＋每頁渲染圖。
PDF 的切片參數是 **`pages=`**，守門（`big_read_guard`）也只認它：沒帶 `pages` 的大 PDF 會被擋。

| 你要做什麼 | 怎麼讀 |
|---|---|
| 判斷 Tier、抓標題／版次／日期 | `Read pages="1-3"`（封面＋目錄通常就夠） |
| 建 Tier 1 卡的章節結構（TOC） | `Read` 目錄那幾頁；**不要為了列 TOC 讀完整份** |
| 要某一節的內容 | `Read pages="N-M"`，一次 ≤20 頁 |
| 要全文檢索關鍵字 | 先抽成文字檔再 Grep：<br>`python -c "import pypdf,sys;print(chr(10).join(p.extract_text() or '' for p in pypdf.PdfReader(sys.argv[1]).pages))" "<pdf>" > "<pdf>.txt"`<br>（沒有 pypdf 就用 `pdftotext`）|

🔴 **被擋時不要改用 `limit` 或 Bash `cat` 繞過** —— 對 PDF 那不是切片，是把整份灌進 context。
⚠️ 抽出來的 `.txt`／`.md` 是**產出物不是正本**：可以建、可以更新，但不可改原始 PDF。

---

## Step 3　建卡

🔴 **每張卡都要有 `scope:`**：值＝這份文件在 `raw/` 的第一層資料夾名（使用者在 CLAUDE.md 定的隔離軸），
外部檔就寫 alias。跨多個對象 `scope: [A, B]`，真正通用的 `scope: shared`。
查詢靠它判斷「這頁是不是當前對象的」；沒有 `scope` 的卡等於沒有邊界，會被撈進任何問題。

### Tier 1 指標卡（會變動的文件）

```markdown
---
type: doc-index
title: "{文件標題}"
doc_number: "{編號}"
revision: "{版本}"
doc_status: "{draft / review / approved}"
current_file: "{正本路徑：raw/… 或 alias::…，🔴 不准絕對路徑}"
current_hash: "{MD5}"
scope: "{raw/ 第一層名 或 alias；跨多個用 [A, B]；通用 shared}"   # 🔴 必填，查詢靠它隔離
repo: "{alias}"            # 外部 repo 才有
owner: "{擁有者} @ {機器}"  # 非本 vault 路徑必標
tier: 1
---

> [!info] 這是指標卡，不含數值。細節請即時讀 `current_file`。

## 文件身分
## 一句話用途
## 正本各頁（頁 → 內容；🔴 必填，查詢時靠它 `Read pages=`）
## 快速定位：哪個問題看哪一頁／哪個 Table
## 交叉引用
## 版本歷史
```

### 重要文件索引卡（委外報告、客戶合約、認證、datasheet、量測報告）

這類文件**很重要又不能抄**：正本是蓋章／出具方的，我方無法修改也無法保證同步。
卡的價值只有一個：**讓下次能精準開到正確的那一頁**。所以章節／頁碼清單要比一般指標卡更細。

```markdown
---
type: doc-index
subtype: report | contract | certificate | datasheet
title: "{文件標題}"
issuer: "{出具單位}"
report_date: YYYY-MM-DD
doc_version: "{版次}"
dut: "{待測物／標的／料號／序號}"
source_doc: "{檔名}"
source_path: "{正本路徑}"
sources: ["{正本路徑}"]
scope: "{raw/ 第一層名 或 alias}"   # 🔴 必填
tier: 1
---

> [!warning] 這是索引卡，不是文件本身
> 完整數值表、逐筆量測值、條款原文一律回正本。

## 有什麼（一張表：標的／日期／出具方／涵蓋範圍／性質＝實測 or 轉抄）

## 正本各頁（🔴 每一頁或每一節一列，不可省略；這是這張卡存在的理由）
| 頁 | 章節／測項 | 內容一句話 |
|---|---|---|

## 判斷（每項一句 verdict，可含概略範圍如「~2.4–3.2 s」，不放完整表）

## 怎麼回溯（開哪個檔、看哪頁、注意什麼）
```

🔴 **頁碼表的精度＝查詢的精度**：PDF 用 `Read pages="1-3"` 讀封面與目錄列出來，超過 20 頁的報告至少到「節」；
每節一列。建卡時多讀幾頁目錄，比之後每次查都翻整份便宜。

### 完整摘要卡（已凍結的文件）

```markdown
---
type: book-catalog | doc-catalog
title: "{完整標題}"
source_file: "{路徑}"
source_hash: "{MD5}"      # 選填；要能偵測正本被換掉就寫
revision: "{版本}"         # 選填；文件本身有版次才寫
ingested_at: YYYY-MM-DD
scope: "{raw/ 第一層名 或 alias}"   # 🔴 必填
topics: ["{主題}"]
---

## 摘要（2–4 句）
## 章節結構（表格：章節 / 標題 / 頁碼 / 一句話）
## 關鍵概念索引（表格：概念 / 章節 / 頁碼 / 說明）
## 適合查詢的問題類型
```

---

## Step 4　更新 manifest

🔴 **走腳本，不要手寫**（手寫漏了就是孤兒卡，#28／#32）：

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/repo.py" link "{source key}" "{卡片路徑}" --tier 1 --topics "a,b"
```

它會自己算 hash、填 `repo`／`ingested_at`／`catalog_page`、把 `scope:` 補進卡的 frontmatter（alias 或 `raw/` 第一層；不對就 `--scope` 指定），並重建 `wiki/repos.md`。
寫出來長這樣：

```json
"{source key}": {
  "hash": "{MD5}",
  "repo": "{alias}",             // 外部 repo 才有
  "ingested_at": "YYYY-MM-DD",
  "catalog_page": "wiki/catalog/...",
  "topics_updated": ["{主題}"],
  "tier": 1
}
```

**更新（hash 變了）走 supersession**，動的是 manifest 的 `doc_index`（key＝`name:{slug}`，slug＝檔名去掉版次與日期，跨版次不變；
value＝`{current_file, current_summary, wiki_pages[], revision, history[]}`，說明見 manifest `_doc_index_note`）：

1. 舊 current（file／summary／revision）＋今天日期 → push 進 `history[]`（稽核用，不刪）
2. `current_file`／`revision` 指新檔；`sources` 新增新檔的 hash 紀錄
3. 卡片只改 frontmatter，加 `> [!note] 版本更新 vN→vM（日期）`。**改哪些欄位看卡的型別**：
   - Tier 1 指標卡 → `revision`／`current_file`／`current_hash`／`doc_status`
   - 完整摘要卡 → `revision`／`source_file`／`source_hash`（該模板沒有 `doc_status`）

   🔴 完整摘要卡的前提是「已凍結的文件」。**它如果在改版，就代表當初卡型選錯了** ——
   先問使用者要不要改建 Tier 1 指標卡，不要默默沿用（2026-09-21 驗收 #20）。
4. **不重抽內容** —— 章節結構沒變就不重寫；`wiki_pages` 列的頁面各加一行版本 note

查不到同 slug 的 entry 才視為新文件、走 Step 3 建卡。

---

## Step 5　更新索引與日誌

| 檔 | 動作 |
|----|------|
| `wiki/index.md` | 對應區塊新增條目 |
| `wiki/hot.md` | 更新計數與「最近 ingest」（注意 ≤150 行輪替） |
| `wiki/repos.md` | **不用手動改** —— `repo.py` 在 add／remove／scan 時依 manifest 自動重建 |
| `wiki/log.md` | 最上方新增一則（**用 append，不要整份讀**） |

log 格式：

```markdown
## YYYY-MM-DD | ingest | {文件名}
- 來源：`{source key}`
- 卡：[[catalog/...]]
- Tier：1 / 完整
- 一句話：{這份講什麼}
```

---

## Step 6　Commit

```bash
git -c user.name="{自己的 session 名}" add wiki/ raw/.manifest.json
git -c user.name="{自己的 session 名}" commit -m "ingest: {文件名}"
```

session 名當 author 才分得出誰做的。**不要 `git config --global`**。

---

## 批次

1. 掃描 → 對每個檔 hash check
2. 列出「新增／已 ingest／建議跳過」三類。**使用者已明確下 `/wiki-ingest <路徑>` 時，「新增」類直接開始，不再問一次**；只有 ①新增 >10 份 ②Tier 判斷有疑義 ③「建議跳過」裡有你不確定的，才停下來問
3. 每 5 份 check in 一次回報進度
4. 全部完成後做一次跨文件主題交叉引用
5. 統一更新 index / hot / log，最後 commit
