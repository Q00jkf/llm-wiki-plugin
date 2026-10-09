# vault 骨架升級（skeleton upgrade）

> 狀態：待使用者審 ｜ 提出 2026-10-09 ｜ 使用者裁示的設計，IT（user-f4）撰寫

## 1. 問題

`wiki-init` 建骨架是**一次性快照**：照當時的 `templates/vault/` 複製 30 多個檔
（`CLAUDE.md`、`wiki/ops/` 7 支、`wiki/meta/`、`Templates/`、`.claude/settings.json`）。

之後 plugin 升級，`skills/` 會跟著更新（從 plugin 讀），但**已建好的 vault 那 30 個檔永遠停在建立那天**。

更根本的是：**沒有任何東西會發現它沒成長**。

- vault 裡沒有骨架版本戳記（`raw/.manifest.json` 記的是 ingest 來源，不是骨架）
- `rules_check.py` 只查規則層內部一致性（F1–F6），不比對 plugin 樣板
- `wiki-adopt` 是一次性「接上 plugin」，不是持續升級

**實例（2026-10-09）**：`06-coordination格式.md` 新增「狀態欄開頭寫登記日」，`tidy_check.py` 的 T9 靠它。
舊 vault 的 `coordination.md` 沒有這個欄位規則，使用者也不會知道要加 —— skill 更新了，資料結構沒有，T9 永遠只報個數。

## 2. 目標與非目標

**目標**

1. 知道某個 vault 的骨架停在哪一版，以及與現行樣板差在哪
2. 用人話說明「新版多了什麼功能」，不是只丟檔名或 diff
3. 對客製過的檔給出融合方式，**使用者同意後才寫檔**
4. 留下可追的升級史

**非目標**

- 不自動升級（不做無人值守的 migration）
- 不碰 vault 自己新增的檔（不在樣板裡的一律不管）
- 不處理 plugin 降版（只往前）

## 3. 資料結構

### 3.1 `.skeleton.json`（vault 根，隱藏檔）

與 `raw/.manifest.json` 同一慣例。每個樣板檔記**兩個** hash：

```json
{
  "plugin_version": "1.4.0",
  "created_with": "1.0.4",
  "updated_at": "2026-10-09",
  "files": {
    "wiki/ops/collab.md": {
      "template_hash": "<上次對帳時 plugin 樣板的 hash>",
      "local_hash": "<上次對帳時這個 vault 的 hash>"
    },
    "wiki/ops/query.md": { "opted_out": true }
  }
}
```

兩個 hash 才分得出「樣板變了」與「使用者改了」—— 這是 base／theirs／mine 的三方比較。
只記一個就只知道「有差異」，分不出是誰造成的，也就提不出融合建議。

`opted_out`：使用者明確說不要的檔，之後不再報缺檔。

### 3.2 `wiki/meta/init-history.md`（人讀，**腳本 append**）

🔴 **只由腳本寫，人不手改。** 手寫的升級史漏記一次就永遠對不上。
`wiki/meta/_guard-status/` 已是這個模式。

```markdown
## 2026-10-09　1.0.4 → 1.4.0

- 新增 3：`wiki/ops/naming.md`（文件命名規則）、`Templates/角色卡模板.md`（角色接手用）、…
- 更新 4（未客製）：`wiki/ops/end.md`、`wiki/ops/start.md`、…
- 融合 1：`wiki/ops/collab.md` —— 新版多了 T9 登記日規則，插在 §格式 之後；R-collab-1～10 保留
- 跳過 1：`wiki/ops/query.md`（使用者刪過，記為 opted_out）
```

寫的是**實際做了什麼**，不是計畫；使用者說 no 的不寫進來。

### 3.3 三者分工

| 檔 | 存什麼 | 誰寫 |
|---|---|---|
| `.skeleton.json` | 當前狀態 | 腳本 |
| `wiki/meta/init-history.md` | 升級史 | 腳本 append |
| `wiki/log.md` | **不重複寫**，當天條目放一行 `→ [[wiki/meta/init-history]]` 指過去 | 既有流程 |

最後一列是刻意的：升級史已經有家，再寫進 log 就是兩個家。

## 4. 分類邏輯（腳本，純機械）

對每個樣板檔 `f`：

| 條件 | 歸類 |
|---|---|
| vault 沒有 `f` 且未 opted_out | **① 缺檔** |
| `hash(樣板) == template_hash` | 不報（絕大多數落這裡） |
| 樣板變了 ＋ `hash(vault 檔) == local_hash` | **② 未客製** → 可安全換 |
| 樣板變了 ＋ vault 檔也變了 | **③ 已客製** → 要融合 |

### 4.1 降級模式（沒有 `.skeleton.json`）

**現有 vault 全都沒有這個檔**，第一次跑時 base 未知：

- 缺檔判斷照常準確
- vault 有的檔只能比「vault 檔 vs 現行樣板」：相同 → 不報；不同 → **一律進組③**（保守，會多問幾次）

跑完寫出 `.skeleton.json`，第二次起②③才分得清。

## 5. 誰做什麼

| | 腳本 `scripts/skeleton_check.py` | `wiki-init` skill（Claude） |
|---|---|---|
| 比對、分類、產 diff | ✅ | |
| 用人話講「多了什麼功能」 | ❌ 只看得到行差異 | ✅ 讀 diff 總結 |
| 組①② 寫檔 | ✅ `--apply-safe`（純複製，無判斷） | |
| 組③ 融合 | ❌ | ✅ 提方案 → 等同意 → Edit 寫入 |
| 寫 `.skeleton.json`／`init-history.md` | ✅ | |

**升級一定要 Claude 在場**，不能純腳本跑完 —— 「多了什麼功能」與「怎麼融合」都是判斷。
這也沿用 plugin 既有慣例：腳本只列候選，判斷交給 Claude（見 `wiki-doctor`）。

### 5.1 腳本介面

```
python skeleton_check.py              # 人讀的三組分類報告
python skeleton_check.py --json       # 給 skill 吃的結構化輸出（含每檔 diff）
python skeleton_check.py --apply-safe # 只做組①②，寫檔並更新 .skeleton.json
python skeleton_check.py --record '<json>'  # 組③由 skill 寫完後，補記 hash 與 history
```

`--apply-safe` 不碰組③，即使誤用也不會毀客製內容。

## 6. 操作流程

`/wiki-init <路徑>`：目標已是 vault（有 `wiki/` 或 `raw/.manifest.json`）→ **自動進升級模式**，不另開指令。

```
Step 0  skeleton_check.py --json
Step 1  沒有差異 → 一句「骨架已是最新（1.4.0）」，結束
Step 2  組① 缺檔：列出檔名＋我讀樣板後寫的「這個檔是幹嘛的」，整批問一次 [y/n]
Step 3  組② 未客製：列出檔名＋「這版改了什麼」，整批問一次 [y/n]
Step 4  組③ 已客製：逐檔
          - 新版多了什麼（我讀 diff 講）
          - 你加了什麼（我讀你的檔講）
          - 建議的融合方式（插在哪、要不要插）
          - [y / n / 改]
Step 5  執行：①② 走 --apply-safe；③ 我用 Edit 寫
Step 6  skeleton_check.py --record → 更新 .skeleton.json、append init-history.md
Step 7  回報：做了什麼、跳過什麼、init-history 連結
```

## 7. 邊界情況

| 情況 | 處理 |
|---|---|
| 使用者故意刪掉某樣板檔 | 答 n 時記 `opted_out: true`，之後不再報 |
| plugin 降版（樣板比 vault 舊） | 不報。只往前 |
| vault 自己加的檔（不在樣板裡） | 完全不管 |
| 客製過、樣板也變了 | hash 是整檔的，所以**分類一定會進組③**；但報告只呈現樣板變動的那幾段，不把整檔 diff 丟出來。使用者改的部分與樣板改的部分不重疊時，我的融合建議就是「直接插入，不衝突」 |
| `.skeleton.json` 損毀／手動刪除 | 退回降級模式，不報錯 |
| 樣板檔被 plugin 刪掉 | 不動 vault 的檔，只在報告提一句 |

## 8. 測試策略

🔴 **plugin 現在沒有 Python 測試框架**（只有 `plugins/pixel-office/*.test.tsx`）。
這套東西會寫使用者的檔，不能只靠「跑一次看起來對」。

本案建立 repo 第一支 Python 測試 `scripts/test_skeleton_check.py`（stdlib `unittest`，與腳本同樣只用 stdlib）：

| 案例 | 驗什麼 |
|---|---|
| 全新 vault，樣板無變更 | 零差異，不報 |
| 缺一個檔 | 進組① |
| 樣板變、local 未動 | 進組② |
| 樣板變、local 也變 | 進組③ |
| 無 `.skeleton.json`（降級） | 有差異的一律進組③ |
| `opted_out` 的檔 | 不報缺檔 |
| `--apply-safe` | 只動①②，組③檔案 byte 不變 |
| plugin 降版 | 不報 |

測試在 `tmp` 目錄建假 vault，不碰真實 vault。

## 9. 影響範圍

| 檔 | 動作 |
|---|---|
| `scripts/skeleton_check.py` | 新增 |
| `scripts/test_skeleton_check.py` | 新增 |
| `skills/wiki-init/SKILL.md` | 加「升級模式」分支（原 5 步是建新 vault 的路徑，不動） |
| `templates/vault/wiki/meta/init-history.md` | 新增（空殼＋檔頭說明「本檔由腳本寫，勿手改」） |
| `.claude-plugin/plugin.json` | bump minor |
| `README.md`／`docs/design.md` | 升級流程各補一行 |
| ~~`wiki/ops/tools.md`（各 vault）~~ | **不需要**。`rules_check.py` 的 F6 是 `sdir = c.root / "scripts"`，只掃 vault 自己的腳本；`skeleton_check.py` 住在 plugin，F6 看不到（llm-wiki-aegiverse-e4 2026-10-09 實跑 `[F6] 🟢 0 筆` 指正）。要不要為了好查而登記是規則層的另一個決定 |

## 10. 未決／待辦

- ~~死 glob 測試~~ **已補**（`test_18`，驗收後）：`.skeleton-policy` 的每個 glob 至少要命中
  一個樣板檔，否則樣板改名後死 glob 會無聲腐爛。
- 要不要為了好查而把 `skeleton_check.py` 登記進各 vault 的 `wiki/ops/tools.md`：
  規則層的決定，由主管與使用者定，F6 不逼（見 §9）。

設計已由使用者在 2026-10-09 對話中逐項裁示：
只報告→改為同意後才改（使用者修正）、三組批次同意、加 `init-history` 紀錄層。

---

## 11. 實作後補記（2026-10-09）

spec 是動手前的決定，以下是實作與實跑 `wiki-test` 時才發現的，**原 spec 沒寫**。
不回頭改上面的章節（那是當時的判斷），差異記在這裡。

### 11.1 四條降噪規則

原 spec 假設「樣板有差異＝要處理」。實跑發現 13 項裡有 4 項是雜訊：

| 規則 | 不做會怎樣 | 落在哪 |
|---|---|---|
| 資料檔不對帳 | 每次都報「已客製」 | `templates/vault/.skeleton-policy` |
| 標題後補註解算同一段 | `## 分工` vs `## 分工（註解）` 報成一加一減 | `same_heading()` |
| 含 `{{…}}` 的行不算新增 | 佔位符永遠比得出差異 | `PLACEHOLDER` |
| 扣掉上面之後沒新增就不報 | wiki-test 從 13 項降到 9 項 | `classify()` |

**不對帳清單放在 `.skeleton-policy` 而不是腳本裡**：加樣板檔的人跟改腳本的人不是同一次動作，
寫在程式裡會漏。先確認過現有 frontmatter 不夠用 —— `type: meta` 同時涵蓋資料檔（log/hot）
與規則檔（agenda-system），`maintenance:` 在模板裡是「給產物的宣告」不是模板自己的性質。

### 11.2 🔴 降噪必須可查

`--verbose` 列出「有差異但判斷不用報」的檔與原因。
判斷錯就等於把變更藏起來 —— 那正是這支腳本要解決的病，不能用它來製造同一種病。

### 11.3 🔴 write_skeleton 只能封存處理過的檔

原 spec 沒寫這條，第一次實跑就踩到：`--apply-safe` 後報告變 🟢，但 5 個待融合的檔
**根本沒融合** —— 它們被一併記成新基準，等於宣告「已對帳」，下次不會再報。

修法：`write_skeleton(only=[...])`，只封存實際處理過的 rel。測試補 `test_10` 的斷言
（原本只驗「缺檔補完了」，沒驗「沒處理的還在不在」）。

### 11.4 與 `init_vault.py --force` 的關係

`--force` 本來就能補缺檔，功能與組①重疊。保持分離：`--force` 不知道哪些檔「沒客製所以能安全換」，
也不留對帳基準。升級一律走 `skeleton_check`，`--force` 只在建新 vault 中斷後補檔時用。
`.skeleton-policy` 不複製進新 vault（`init_vault` 已排除）。

### 11.5 測試

12 支，`scripts/test_skeleton_check.py`。比 spec §8 多的：`test_12` 驗 policy 的 glob
與政策檔自身不對帳；`test_10` 多驗待融合的檔不被吞掉。

### 11.6 review 抓到的三條（2026-10-09，llm-wiki-aegiverse-e4）

都是實跑驗出來的，不是讀程式碼的推測。三條都已修、各補一支測試。

**🔴 組②會毀掉「本來就該跟樣板分岔」的檔**（`test_13`）
`local_hash == base_local` 只代表「上次對帳後沒再動」，**不代表它曾經等於樣板**。
`CLAUDE.md`／`wiki/ops/*.md` 建 vault 當天就是真規則層、樣板是空殼，而且常常幾個月沒人動 →
樣板一改就落進「未客製，可安全換」→ 整份被 `copyfile` 蓋掉，連 `{{name}}` 都沒代換。
修法：組② 多一個條件 `base_local == base_tpl`。一開始就分岔的檔**永遠**只能進組③。

**🔴 樣板「刪掉」內容時不會被報**（`test_14`）
原本只收 unified_diff 的 `+`。樣板廢掉一條過時規則 → 判成 trivial → 只有 `--verbose` 看得到，
而且理由字串寫「只動了佔位符或潤稿」是**錯的**。降噪可查的前提是理由要真。
修法：trivial 判準加入刪除行數。**但只在正常模式** —— 降級模式沒有 base，
分不出「你有、樣板沒有」是你加的還是樣板廢的，而絕大多數是前者
（wiki-test 的 `rulings.md` 有 80 行自己的裁示），算進去只會變噪音。報告端的標籤也照實寫成
「你有、樣板沒有：N 行（樣板這版廢掉的，或你自己加的）」，不假裝分得出來。

**🟡 補缺檔不經 `render()`**（`test_15`）
`shutil.copyfile` 讓 `updated: {{today}}` 原樣落地（wiki-test 實跑 2 個檔中招）。
修法：共用 `init_vault.render()`，`name` 取 vault 目錄名、`today` 取當天。

連帶修掉一個自己引入的誤報：兩邊比對前要先把「佔位符那一組行」配掉
（樣板 `updated: {{today}}` ↔ vault `updated: 2026-09-21` 是同一行的兩個樣子），
否則一行製造兩筆。整行只有佔位符的（`{{domain}}`）無法定位，放棄配對 —— 代價是多報一筆，不是漏報。

### 11.7 驗收與收尾（2026-10-09）

對 `wiki-test` 複本（骨架停在 0.4.5x）走完三組流程：補 4 檔、融合 4 檔、跳過 1 檔（記 opted_out），
最終 🟢。使用者客製的東西全數存活（`CLAUDE.md` 的 alias 路由 5 處、`rulings.md` 的 9 條裁示），
CRLF 行尾保留，補進去的檔經過 `render()`（`updated: 2026-10-09` 而非 `{{today}}`）。

驗收走到第 6 步才發現 `--record`（封存組③、記 opted_out）**設計了但沒實作** —— 補上，`test_16`。

收尾三項：
- **樣板刪檔要有反應**（原 §7 說好沒做）→ `retired` 群組，報「plugin 不再提供」，**絕不碰 vault 的檔**（`test_17`）。
  判斷依據是「上次對帳記錄裡有、現在樣板沒有」，所以降級模式看不出來，已在 skill 寫明。
- **死 glob 測試** → `test_18`。
- **對帳機制的破口寫進開發者守則**（plugin repo `CLAUDE.md`）：skill 的行為一旦依賴 vault 的
  某個檔或某種格式，那個格式要同時寫進樣板的對應檔，否則 `skeleton_check` 看不到，舊 vault 永遠不會被提醒。
  被 `.skeleton-policy` 排除的檔連格式變更也偵測不到 —— 那是這套機制的邊界，`wiki-init` 也照實寫了。

18 支測試。
