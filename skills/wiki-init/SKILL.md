---
name: wiki-init
description: "建立新 vault（團隊／PM 的專案管理系統），引導填出專屬的 CLAUDE.md（管理對象、術語、工作習慣、資料夾用途）。產出薄骨架，不複製 skills／commands。團隊導入請走 references/setup-interview.md。Triggers on: wiki-init, 建立 wiki, 導入這套系統, 我要用這套系統, 初始化 vault, 團隊導入, 新人第一次用。"
---

# wiki-init：建立新 vault

**產出薄骨架（`templates/vault/` 整棵複製），系統由 plugin 提供。**

---

## 🔴 為什麼不複製 skills／commands

舊做法是每個新 vault 夾帶一整套 skills 拷貝。實測結果：同一批範本的 skill 數量分岔成
**18 / 18 / 30 / 31** —— 拷貝一定會漂，而且沒有人會發現。

plugin 提供系統、vault 只放內容與個人設定，升級 plugin 時所有人一起更新。

---

## 流程

> 🔵 **團隊導入、或使用者答不出下面三題時**，改帶他跑 `references/setup-interview.md`
> —— 訪談式設計精靈（管理對象 → 團隊與角色 → 制度 → 既有資產 → 第一批）。
> 個人用、範圍清楚的情況，下面三題就夠，不要一開始就丟長問卷。

### Step 1　問清楚（一次問完，不要一題一題來）

🔴 **先問「管什麼」，不要先問「收什麼知識」。** 這是專案管理系統，知識庫是其中一個能力；
從知識庫問起會把使用者導向錯的結構（真實部署的知識層只佔四成）。

用 `AskUserQuestion` 一次問：

1. **要管什麼對象？**（產品線／專案／客戶／部門，大概幾個）
   → 決定 `raw/` 的第一層與 `wiki/products/`
2. **幾個人用？誰維護什麼？**（一個人／小組／跨部門）
   → 一人以上就要交代 `wiki/meta/coordination.md` 與 `wiki-collab`
3. **有沒有制度或既有資產要進來？**（ISO／SOP／表單；散在別處的專案）
   → 制度進 `raw/<制度名>/`；散在別處的之後跑 `/wiki-repo add`

新人不知道怎麼答時，給範例，不要讓他卡住。

### Step 2　建骨架

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/init_vault.py" <目標路徑> --name "名稱" --domain "用途"
```

先跑 `--dry-run` 讓使用者看會建立什麼，確認後才實際執行。

產出：

```
CLAUDE.md              ← 個人層（術語／習慣／資料夾用途）
raw/.manifest.json     ← config + repos 註冊表 + sources
wiki/index.md          ← 全局目錄
wiki/hot.md            ← 最近上下文（輪替制 ≤150 行）
wiki/log.md            ← 操作日誌（只增不減，只能 Grep）
wiki/{catalog,topics,questions,projects}/   ← projects/ 是專案頁，不是知識頁
wiki/ops/{ingest,query,naming,collab,rulings}.md  ← 規則模組（空殼，有東西才寫）
wiki/agenda.md         ← 日程唯一真相來源
wiki/meta/{coordination,agenda-system}.md
Templates/             ← _README模板、AI對話紀錄模板、_folder-template（/wiki-new 用）
.gitignore
```

**跟使用者介紹骨架時，五件事都要講到** —— 不要只講 catalog／topics 那一塊：

| 建出來的東西 | 管什麼 |
|---|---|
| `raw/<對象>/` ＋ `Templates/_folder-template/` | **專案／產品線**。用 `/wiki-new` 開夾，`_README.md` 是該夾的執行節點（進度儀表板）|
| `wiki/agenda.md` ＋ `wiki/meta/agenda-system.md` | **日程**。唯一真相來源，開場自動印窗口 |
| `wiki/meta/coordination.md` | **多人／多 session 分工**。一個人用先空著，第二個人進來就要維護 |
| `raw/.manifest.json` 的 `repos` | **檔案資產**。散在各處的專案掛進來，檔案留原地 |
| `wiki/{catalog,topics}/` ＋ `hot/index/log` | **知識庫**。raw → wiki 的編譯產物 |
| `wiki/ops/*.md` | 按需規則模組（空殼，有東西才寫）|

### Step 3　把 Step 1 的答案填進 CLAUDE.md

**這是最關鍵的一步，不要跳過。** 骨架產出的 CLAUDE.md 有這些區塊（鐵律／踩雷兩區刻意留空）：

| 區塊 | 填什麼 | 為什麼重要 |
|------|--------|-----------|
| 專屬術語／縮寫 | 領域黑話 | 否則 Claude 每次都要問「這是什麼意思」 |
| 資料夾用途 | `raw/` 怎麼分 | 系統不預設分類，講了才會照做 |
| 查詢路由 | 問題類型 → 腳本／檔案 | 有結構化真相的問題不讀 wiki 頁 |
| 🔴 鐵律／裁示 | **先留空**；裁示時 CLAUDE.md 留一句（最多 5 條），Why／實例寫 `wiki/ops/rulings.md` | 開場載入量固定，不會越滾越大 |
| ⚠️ 踩過的雷 | **先留空**，踩到才寫；含代價 | 同一個坑第二次踩最貴 |
| 我的工作習慣 | 希望每次都遵守的事 | 這是「個人化」的實際載體 |

用 Step 1 的回答直接填，**不要留空給使用者自己想** —— 新人面對空表格會放棄。

### Step 4　git init 與第一次 commit

```bash
git -C <目標路徑> init
git -C <目標路徑> add -A
git -C <目標路徑> commit -m "init: vault 骨架（llm-wiki plugin）"
```

### Step 5　告訴他下一步做什麼（只講一件）

> 「把一份你手上的文件丟進 `raw/`，然後跑 `/wiki-ingest raw/`，看它長什麼樣。」

**不要一次列出所有指令。** 新人需要的是一個能馬上做的動作。

---

## Obsidian

建好後提醒使用者在 Obsidian 用「Open folder as vault」加入該資料夾。
plugin 不自動改 `obsidian.json`（Obsidian 執行中改它會被覆蓋，且有弄壞其他 vault 註冊的風險）。
