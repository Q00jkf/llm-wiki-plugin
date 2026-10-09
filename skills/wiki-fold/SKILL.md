---
name: wiki-fold
description: "把 wiki/log.md 最舊的 2^k 條摺成一頁 extractive 摘要（wiki/folds/），預設 dry-run 只印不寫。Triggers: wiki-fold, 摺疊 log, 壓縮 log, log 太長, log rollup。"
---

# wiki-fold：log.md 摺疊

**存在的理由**：log.md 只增不減，終究會長到被 `big_read_guard` 擋整份讀，且 `grep 關鍵字 wiki/log.md` 的回傳量與檔案同步成長。
摺疊＝把最舊的 2^k 條壓成一頁**可回溯**的摘要；原文不竄改。

> 前一版 skill 用 `grep "^## \["` 抓條目，與實際格式不合 → 命中 0 筆、4.5 個月從沒跑起來。
> 本版把解析與封存交給腳本（`_lib/logparse.py` 只定義一次 HEAD regex），skill 只負責寫摘要。

---

## 模式

| 模式 | 寫檔？ | 呼叫 |
|---|---|---|
| **dry-run（預設）** | 否。摘要用 Bash heredoc 印到 stdout | `fold the log, dry-run k=3` |
| **commit** | 寫 `wiki/folds/{fold-id}.md`、改 `wiki/index.md`、prepend `wiki/log.md`、commit | `fold the log, commit k=3`（dry-run 乾淨後才做） |
| **commit + archive** | 同上，再把原文原封搬到 `wiki/folds/raw/` 並從 log.md 移除 | `fold the log, commit k=3, archive` |

**archive 是政策不是技術**：不用 → log.md 不變短，摘要頁只是多一個入口；用 → log.md 真的變短，
但「刪快照前 MUST grep wiki/log.md」那條規則要改成 `grep -r … wiki/log.md wiki/folds/`。
建議第一次先不 archive，看摘要頁有沒有人用。

## 參數

- `k`（預設 3）：批次**目標** 2^k 條，實際會對齊日期邊界（見下），所以 n 可能少於或多於 2^k。
  k=3～4 是摘要品質與讀取成本的平衡點，**不要 k≥5**。
- `offset`（預設 0）：跳過最舊的 N 條（＝已摺過的）。**下一次的 offset 看上一批實際的 n，不是 2^k** —— 對齊日期後兩者常不相等。
- `range A-B`：明確指定序號（1＝最舊），覆蓋 k／offset。

---

## 程序

### 1. 取批次（腳本，不 Read）

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/wiki_fold_parse.py" list --tail 20
python "${CLAUDE_PLUGIN_ROOT}/scripts/wiki_fold_parse.py" batch --k 3 --offset 0
```

`batch` 的輸出是本次的**唯一輸入**。`exists : YES` → 同範圍已摺過，停，回報檔名。條目不足 → exit 1，**不摺部分批次**。
腳本按**日期**排序（log.md 常兩種順序並存，位置不代表先後），批次在檔內可能不連續。

🔴 **批次不切開同一天**：同日條目的先後在 log 裡無法判定（早期 append 行號小＝舊、近期 prepend 行號小＝新），切在一天中間會讓 fold_id 宣稱的日期範圍與 log 殘留條目重疊。
腳本因此把批次結尾退到前一天結尾；整批都在同一天時改為吃滿那一天。`--range` 若切開某一天會直接 exit 1 並給出對齊後的值。（2026-09-21 驗收 #17）

### 2. 讀 children JSON

每條已抽好 `date`／`title`／`wikilinks`／`paths`／`commits`／`bytes`／`lines`。一條一筆，不依頁面去重。

### 3. 讀被引用的頁（有界）

只讀 children 的 `wikilinks`／`paths` 指到、且原文沒講清楚的頁，預算 0–10 頁、上限 15。
頁不存在 → `page_missing: true` 照記。**`raw/` 內的檔不開**（wiki 只做索引）。

### 4. 寫摘要（照 `references/fold-template.md`）

- **每個 outcome／theme 標來源**：`（來自 2026-05-06 條）`或引一句原文。不引入原文沒有的事件、數字、解讀。
- **數字要對帳**：寫「3 頁」就 grep 原文確認是 3。對不上＝dry-run blocker。
- **原文優先於被引用的頁**：矛盾時寫「來源不一致：log 說 X、頁說 Y」，不擇一。
- 🔴 **裁示逐條保留**：log 常含「使用者裁示」「不得再提」「界定什麼不是我方範圍」這類**沒有別的家**的內容。
  摘要頁 MUST 有「裁示與界線」一節，一字不漏列出並標日期。

### 5. 自檢

`children:` 筆數 ＝ 腳本印的條數 ＝ Child Entries 表列數；fold_id 與腳本一致；每個數字可 grep 回原文；
「裁示與界線」每條能在原文找到原句。任一失敗 → 停，報出哪一項。

### 6. 輸出

**dry-run**：heredoc 印整頁；最後印「fold_id：…；commit 會寫 wiki/folds/{id}.md、改 index.md、prepend log.md」。**不呼叫 Write／Edit。**

**commit**（使用者明說後）：
1. `Write` → `wiki/folds/{fold-id}.md`
2. `Edit` `wiki/index.md`：`## Folds` 節（沒有就建）加一列 `| {from}→{to} | [[folds/{fold-id}]] | n{count} |`
3. **prepend** `wiki/log.md` 一條（Bash 純文字插入，不 Read）：
   ```
   ## YYYY-MM-DD fold — k{K} 摺疊 {count} 條（{from} → {to}）
   - 摘要：[[folds/{fold-id}]]
   - 範圍：log.md 序號 {a}–{b}（1＝最舊）；archive：{是/否}
   ```
4. （若 archive）`python "${CLAUDE_PLUGIN_ROOT}/scripts/wiki_fold_parse.py" archive --k {K} --offset {N} --yes`
   —— 腳本先檢查摘要頁存在、raw 檔不重複，再搬。
5. 順手 `python "${CLAUDE_PLUGIN_ROOT}/scripts/log_index.py" --apply` 給新條目補標記，再 commit（多 session 時用 session 名當 author）。

---

## 不變式

1. **結構冪等**：同範圍＋同 k → 同 fold_id → `exists: YES` 擋重寫。
2. **原文不竄改**：archive 只整段搬移、一字不改，且必須在摘要頁存在之後。
3. **有界讀取**：0–15 頁。
4. **extractive**：零捏造，數字對帳。
5. **不串接**：不呼叫 lint／ingest／save；不動 hot.md。

## 不要做

- 不要 `Read wiki/log.md`。
- 不要把「今天」放進檔名或標題。
- 不要為了湊 2^k 摺不足的批次；也不要因為 n≠2^k 就手動 `--range` 去湊 —— 日期邊界優先。
- 順序固定：摘要 → index → log 條目 → archive → commit，不可反。
- 不要把「裁示與界線」省略成「見原文」。

## 復原

一個 commit 就能 `git revert`；若有 archive，revert 會把原文放回 log.md、刪 raw 檔，摘要頁一併消失。
