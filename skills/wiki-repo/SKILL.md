---
name: wiki-repo
description: "把散在各處的 git 專案／資料夾掛進同一個 wiki 管理。註冊、列出、掃描變更、解除註冊。檔案留在原地不搬家，wiki 只存指標。Triggers on: wiki-repo, 註冊 repo, 加入外部專案, 管理多個 git, 掃描 repo, 這個 wiki 也要管 XXX, 我的專案散在好幾個資料夾。"
---

# wiki-repo：多 repo 來源管理

**一個 wiki 當中控台，管理散在各處的多個專案。檔案不搬家，wiki 只記路徑。**

---

## 指令（一律走腳本，不要手改 manifest）

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/repo.py" discover <上層路徑> [--depth N] [--min-files N] [--min-office N]
python "${CLAUDE_PLUGIN_ROOT}/scripts/repo.py" add <路徑> [--alias 別名] [--desc 說明]
python "${CLAUDE_PLUGIN_ROOT}/scripts/repo.py" list
python "${CLAUDE_PLUGIN_ROOT}/scripts/repo.py" scan [alias]
python "${CLAUDE_PLUGIN_ROOT}/scripts/repo.py" remove <alias> [--force]
python "${CLAUDE_PLUGIN_ROOT}/scripts/repo.py" rename <舊> <新> [--strip-prefix raw/] [--dry-run]
python "${CLAUDE_PLUGIN_ROOT}/scripts/repo.py" link <source key> <卡片路徑> [--tier 1|full] [--topics a,b]
```

`rename` 改 alias 並搬動所有 `sources` key 與 `doc_index` 的 `current_file`／`history[].file`。
拆 alias（整包掛的 vault 拆成 raw／wiki）時用 `--strip-prefix` 把多出來的那段去掉。
**有任何一筆搬不動就整批中止** —— 半套的 manifest 比沒搬更難修。卡片 frontmatter 只回報不自動改。
已被 `remove` 掉、只剩殘留紀錄的 alias 也能當 `<舊>`，那正是最該修的情況。

`link` 把 catalog 卡登記進 `sources`（＝ingest 的 Step 4），自動算 hash。
**建完卡就跑這支**，不要手寫 manifest —— 漏了就是孤兒卡（卡在、但 `scan` 永遠不報它過期）。

`add` 會自動抓 git remote 與擁有者，掃描可 ingest 的檔案數量，**但不 ingest**。
`add`／`remove`／`scan` 都會依 manifest 重建 `wiki/repos.md`（外部 repo 總覽）——
那頁是**衍生檔，不要手改**，真相來源永遠是 `raw/.manifest.json`。

---

## 情境：整顆硬碟上有幾十個專案

```
硬碟 ├ 硬體部門 ├ 專案A ├ doc/
     │          │       ├ sub1 ├ doc/  Design_v1/  Design_v2/
     │          └ 專案B
     ├ FPGA專案
     └ MCU專案
```

**別把整顆硬碟註冊成一個 alias** —— source key 會變成
`hdd::硬體部門/專案A/sub1/doc/x.docx`，長到無法掃描與辨識。

**一個「專案」一個 alias**（上圖中＝`專案A`、`專案B` 那層）。先跑 `discover` 找出正確的那一層：

```bash
python repo.py discover "D:/" --depth 2
```

輸出每個候選的 **Office 檔數（docx/pdf/xlsx/pptx）**與總檔數，並產生可直接貼的批次 `add` 指令。

| 行為 | 說明 |
|------|------|
| 自動排除程式碼專案 | 有 `package.json`／`CMakeLists.txt` 等特徵檔者不列（要列加 `--include-code`）|
| alias 自動去重 | `doc`／`raw`／`src` 這類無鑑別力的名字改用「父層-自己」；撞名自動加序號 |
| 顆粒度由 `--depth` 決定 | **保留最淺命中**：祖先入選就不列子層。`--depth 1` ＝專案層、`--depth 2` ＝子專案層。<br>（0.4.3 前是反過來的「只保留最深」，因為計數是遞迴的，等於保證丟掉正確那層）|
| 過濾沒有文件的資料夾 | `--min-office`（預設 1）。`src`／`bin`／`vendor` 這種 0 份 Office 檔的不列，要列設 `--min-office 0` |
| 不列本 vault 自己 | manifest 已有 `_self` |
| 容錯走訪 | 遇到權限不足、斷掉的符號連結會跳過而不中斷 |

🔴 **不要全部註冊。** `discover` 只是列清單，只註冊真的會查的專案。

### `Design_v1` / `Design_v2` 這種版本並存

版本判斷屬於 ingest 層，不是 repo 層。做 Tier 1 指標卡，用 frontmatter 的
`current_file` 指向當前版本，舊版推進 `history[]`。詳見 `wiki-ingest` skill。

---

## 🔴 掛進來的是「既有的 wiki vault」

別人（或你自己）已經用 llm-wiki 編過的 vault，**不能當成一般文件專案掛**。
`add` 會自動偵測並擋下／改變建議，manifest 記 `kind`，`wiki/repos.md` 多一欄「種類」。

| 偵測到 | 判斷依據 | `add` 的行為 |
|---|---|---|
| `vault-root` | `<目標>/wiki/index.md` ＋ 旁邊有 `raw/` 或 `CLAUDE.md` | **擋下**，印出分兩個 alias 的正確指令（`--force` 可強掛） |
| `compiled-wiki` | `<目標>/index.md` ＋ `log.md` 並存 | 註冊，但印「🔴 不要 ingest，改建指標卡」 |
| `docs` | 以上皆非 | 照舊 |

### 為什麼不能整包掛

一個 vault 裡有**兩層不同性質**的東西，混成一個 alias 之後 `scan` 分不出來：

| 層 | 是什麼 | 該怎麼對待 |
|---|---|---|
| `raw/` | 原始正本（PDF／docx…） | 可 ingest，可建卡 |
| `wiki/` | 對方**已經編譯過的知識** | 🔴 一律不 ingest |

### 為什麼知識層不能 ingest

重編一份＝**同一份知識存在兩處**。對方更新時我方不會知道，兩邊無聲漂掉 ——
這正是「wiki 只存指標」要防的事。ingest 的輸入應該永遠是原始正本，不是別人的摘要。

### 正確做法：雙掛 ＋ 一張指標卡

```bash
python repo.py add "<vault>/raw"  --alias {名}-raw  --desc "原始正本"
python repo.py add "<vault>/wiki" --alias {名}-wiki --desc "已編譯知識層（不重 ingest）"
```

然後**只建一張 Tier 1 指標卡**（不 ingest 任何一份）：

1. 讀 `{名}-wiki::index.md` 取得對方的目錄結構
2. `wiki/catalog/` 建卡：記身分／TOC／兩個 alias 的路徑；frontmatter 標 `tier: 1`、`repo:`
3. 本 vault `CLAUDE.md`「查詢路由」表加一列，指向那張卡
4. 查詢時回正本即時讀

### 🔴 引用時的分界

| 要什麼 | 讀哪個 alias |
|---|---|
| 這份在講什麼、有哪些章節、去哪找 | `{名}-wiki::`（編譯層，快） |
| **條文原文／數值／版次／簽核** | `{名}-raw::`（原始檔）—— 編譯層是**別人的摘要**，不可當原文引用 |

> ⚠️ 編譯層有自己的時間戳。原始檔若之後改版，編譯層可能已過期 → 先 `scan {名}-raw`。

---

## Source key 格式

| 格式 | 意義 |
|------|------|
| `raw/BOOK/x.pdf` | 本 vault，舊紀錄不需改寫 |
| `{alias}::{repo 內相對路徑}` | 外部 repo |

分隔符是 `::`（雙冒號）—— Windows 絕對路徑含 `C:`，單冒號會撞到。

---

## 🔴 路徑不存絕對路徑（可攜 spec）

`manifest` 的 `repos[].path` 存的是 **spec，不是絕對路徑**。
絕對路徑等於把 `C:/Users/<某人>` 硬編碼進資料 —— 換機器、換使用者名稱、hub 搬位置，
所有 alias 一起失效。（初版就是這樣寫的；2026-09-21 使用者裁示：不准硬編碼。）

| spec | 解析成 | 什麼時候用 |
|---|---|---|
| `${VAR}/x` | 環境變數展開 | 跨機器、各人路徑不同（最穩） |
| `~/x` | 使用者家目錄 | 同一人不同機器 |
| `../x` | 相對 vault 根 | 來源與 hub 在同一個上層資料夾（**預設**） |
| `C:/x` | 原樣 | 跨磁碟機，最後手段 —— **會被標記示警** |

`add` 自動壓縮：相對 vault 根（最多往上 4 層）→ `~/` → 絕對。
0.4.14 以前註冊的絕對路徑，在 `list`／`add`／`remove`／`scan` 任一次執行時自動遷移。

壓不掉的（例如 hub 在 `C:`、來源在 `D:`）會在 `list` 與 `repos.md` 標紅，
請自己改成 `${你的變數}/子路徑`，並在每台機器設好那個環境變數。

---

## 🔴 擁有者標記（多人協作鐵律）

`repos` 的路徑 spec 有時只在註冊者那台機器解析得開（例如壓不掉的絕對路徑）。每筆自動記：

```json
"owner": {
  "name": "<git user.name>", "email": "<git user.email>", "machine": "<主機名>",
  "remote": "https://... 或「僅本機，需向擁有者取得」"
}
```

別台機器 `scan` 到路徑失效時，會直接告訴你**去找誰、有沒有 remote 可拿**，而不是只報一個死路徑。

---

## 🔴 寫入權限：依「誰的」分三級

外部 repo **預設唯讀**，但唯讀的理由是「動到別人的東西」，不是「它在 hub 外面」。
使用者自己的專案掛進來就是為了統一管理，一刀禁止等於廢掉這個用途。
（2026-09-21 使用者裁示，取代原本的「外部 repo 一律唯讀」。）

判準看 manifest 的 `owner` 與 `writable`，**`writable` 由使用者逐個 alias 明確開啟**，
沒有這個旗標一律當唯讀。

| 級別 | 判準 | 可寫 | MUST |
|---|---|---|---|
| 🔴 別人的 | remote／`owner` 不是本人 | 需**對方同意**＋`writable: true` | ① 對方同意　② 動手前 `git pull`　③ 完成後 `commit` + `push` |
| 🟡 自己的 vault | 是本人的，且有自己的 `CLAUDE.md` | `writable: true` | ① **先讀它的 `CLAUDE.md`**　② 寫它的 `wiki/log.md` |
| 🟢 自己的資料夾 | 是本人的，沒有自己的規則 | `writable: true` | 照本 vault 規則 |

### 🔴 別人的 repo：三個 MUST

1. **對方同意** —— 使用者說「某某同意了」才算。**不得從「使用者叫我改」推導出對方同意。**
2. **動手前 `git pull`** —— 不 pull 就改，等於基於舊版寫，push 時撞 conflict。
   （舊規則寫「不 pull」是錯的：那是為唯讀情境設計的，一旦要寫就必須先同步。）
3. **完成後 `commit` + `push`** —— 不要把改動留在本機。
   commit message **MUST 標明是從哪個 vault 遠端改的 ＋ session 名**
   （全 vault 同一個 git author，commit message 是唯一可靠的歸屬證據）。

**建議（非強制）**：工程量大就去那個資料夾開 session —— 它的 `CLAUDE.md` 與 skills 才會進 context。
小改動直接在 hub 做即可。

### ⚠️ 有自動同步的 vault 要先講

對方若裝了 Obsidian Git 這類自動 commit／push（看 `.obsidian/plugins/obsidian-git/data.json`
的 `autoSaveInterval`／`autoPushInterval`／`disablePush`），**改動會在幾分鐘內自動推出去，
沒有反悔空檔，半成品也會被推**。動手前 MUST 告知使用者「這會在 N 分鐘內推到 {remote}」。

### 仍然不變

- hub 自己的產物只寫 hub 的 `wiki/`。
- 唯讀 alias（沒開 `writable`）維持：不建檔、不改檔、不 commit、不 pull。

---

## Ingest 外部檔案

```
/wiki-ingest {alias}::{repo 內路徑}     單份
/wiki-ingest {alias}::                  整個 repo（批次）
```

catalog 卡 frontmatter 需加：

```yaml
repo: "{alias}"
source_file: "{repo 內相對路徑}"   # 相對該 repo 根
source_abs: "{完整路徑}"           # 方便直接開檔
owner: "{擁有者} @ {機器}"         # 非本 vault 路徑必標
```

---

## scan 的三類輸出

| 類別 | 意義 | 該做什麼 |
|------|------|---------|
| 🟡 變更 | hash 與 manifest 不同 | **最重要** —— wiki 已過期，重新 ingest |
| 🔵 新增 | 未 ingest | 判斷值不值得建卡（不是每份都要） |
| 🔴 消失 | manifest 有紀錄但檔案不在 | 檔案被移走或改名，卡要修或標失效 |

**只回報，不自動 ingest。** 掃出來的東西該不該處理是判斷，不是規則。

---

## remove 的預設行為

只移除 `repos` 條目，**保留 sources 紀錄與 catalog 卡**（加 `⚠️ 來源已解除註冊` 標記）。
有 ingest 紀錄時需 `--force` 才會執行 —— 避免手滑讓一批卡變孤兒。
