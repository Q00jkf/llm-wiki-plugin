---
name: wiki-agenda
description: "日程與排程：wiki/agenda.md 是唯一真相來源，agenda.py 讀寫；排期、工期與前後關係（接）、自動順延、查逾期、甘特圖、匯 ics／推播。Triggers: 日程, 行程, 排程, 哪天有會, 要交件, 每月幾號, 這週要做什麼, 逾期, 提醒我, 改期, 延後, 工期, 甘特圖, 要徑, agenda, 日曆。"
---

# wiki-agenda：日程與排程

**一句話：日程一律在 `wiki/agenda.md`，不另建提醒清單、不寫進 `hot.md`；寫入一律走 `agenda.py`，不手改日期。**
設計與藍圖在 vault 的 `wiki/meta/agenda-system.md`。

---

## 何時用

| 使用者說 | 做 |
|---|---|
| 「X 日有會」「Y 要交件」「每月 D 日做 Z」 | `add` |
| 「這週／這幾天要做什麼」「有沒有逾期」 | 印窗口（`--days`／`--tag` 可調） |
| 「XX 做完了」／「勾錯了」 | `done 關鍵字`／`undone 關鍵字` |
| 「XX 延到 10-23」 | `move 關鍵字 2026-10-23`（接它的後項一起平移） |
| 「XX 要做 3 天」 | `dur 關鍵字 3`（開始日不動、完成日跟著變） |
| 「B 要等 A 做完」 | `link B A`（A 沒代號加 `--id`） |
| 「進度排得完嗎」「哪些是要徑」 | `plan` |
| 「匯到 Google Calendar」 | `--ics` |
| 「每天推播到 Telegram」 | `--notify` ＋ 說明接法（見下） |
| 「看甘特圖」 | Obsidian 外掛「日程甘特圖」（見下） |

---

## 指令

```bash
A="${CLAUDE_PLUGIN_ROOT}/scripts/agenda.py"
python "$A"                                  # 逾期／今天／7 天內／期限會延誤
python "$A" --days 14 --tag QMS
python "$A" add "2026-09-25 14:00-15:30 會議 X1 說明會 #QMS → log 2026-09-18"
python "$A" add "2026-10-23 待辦 樣品測試 工期3天 代號:test 接:spec #專案A"
python "$A" done 說明會                      # 補 完成:今天
python "$A" undone 說明會
python "$A" move 樣品測試 2026-10-27         # 沒有 原定 就記舊日期；後項一起平移
python "$A" dur 樣品測試 5
python "$A" link 樣品測試 規格 --type SS --lag 1 --id spec
python "$A" unlink 樣品測試 spec
python "$A" plan
python "$A" --check                          # 壞行、相依問題、待順延、硬期限延誤
python "$A" --fmt                            # 手改後補做順延＋分段排序
python "$A" --tidy
python "$A" --ics [out.ics]
python "$A" --notify
```

格式：`日期 [HH:MM[-HH:MM]] 類型 標題 [專案欄位] [每月D日|每週X|每年MM-DD|每N天] [#tag …] [→ 出處]`

專案欄位（選填、順序不拘）：

| 欄位 | 意思 |
|---|---|
| `工期N天` | 工作天；行首日期＝**最後一天**，開始日往前推 |
| `代號:x` | 給別人接用；不可含 `~`、不可用 `+數字`／`-數字` 結尾 |
| `接:a,b` | a、b 完成後才開始；`接:a+2`＝隔 2 工作天；`接:a~SS-1`＝類型 SS／FF／SF＋前置天數 |
| `屬:x` | 掛在代號 x 下；x 成母項，日期由子項推出（母項不寫 接／工期） |
| `完成:MM-DD` | 實際完成日，`done` 自動寫 |
| `原定:MM-DD` | 基準，改期與順延自動寫（只記最早那次；改回原定那天就拿掉） |
| `截止:MM-DD` | 過了只標紅、不推 |
| `進度:60%` | ✅＝100% |

---

## 排程引擎（每次寫入自動跑）

- **前項延誤 → 後項自動順延**（只推不拉：前項提早完成，後項不往前）；每筆記進變更紀錄。
- **`move`／`dur` → 接它的後項一起平移同樣工作天**（往前也一起動）；已完成、重複、硬期限不動。
- **硬期限**（預設 交件／稽核／會議）：引擎從不替它改期，只在窗口與 `--check` 報「會晚 N 工作天」。
- 工作天扣國定假日：vault 設了辦公日曆目錄才扣，沒設只扣週末（見下「設定」）。
- `link` 會造成循環、代號重複、母項接 → 拒絕，什麼都不寫。

---

## 規則

- **`add` 前先把使用者的話換成一行**：日期補全年份、時間 24 小時制、類型用一個詞（會議／交件／待辦／提醒／出差）、細節不塞標題，用 `→` 指回 log／catalog。
- **重複事項只寫一行規則**，不手抄多行；腳本展開下一次。重複事件不支援工期／代號／接。
- **關鍵字要唯一命中**：`done`／`move`／`dur`／`link` 命中 0 或 >1 行會拒絕，換更精確的關鍵字。
- **日期一律用 `move`／`dur` 改**，不手改行首日期（手改不會平移後項、不會記原定）；手改了就跑 `--fmt` 補順延。
- **你（Claude）代改時加 `--source agenda`**，變更紀錄才看得出是誰動的。
- 開場窗口出現 🔴 逾期或「期限會延誤」→ 提一句，問使用者要 `done`、改期還是改工期，不代為決定。
- `--check` 有壞行或相依問題 → 報行號，請使用者修或由你修成合格格式（Obsidian 手打常漏空白）。

---

## 設定（`raw/.manifest.json` 的 `config.agenda`，全部選填）

| key | 預設 | 意思 |
|---|---|---|
| `changes` | `wiki/agenda-changes.md` | 變更紀錄（自動追加，不手改） |
| `calendar_dir` | 無（只扣週末） | 放 `辦公日曆表_*.csv`（行政院人事行政總處格式）的目錄 |
| `hard_types` | `["交件","稽核","會議"]` | 硬期限類型 |
| `project_dirs` | `["wiki/products","wiki/projects"]` | 有 `<tag>.md` 就算專案 tag（分段、結案才歸檔） |
| `first_order` | `[]` | 第一次分段時的段落順序 |
| `due_cmd`／`due_label` | 無 | 開場窗口另外併入的到期清單指令（argv 陣列）與標題 |

---

## 甘特圖（Obsidian 外掛「日程甘特圖」）

- 左側 ribbon 甘特圖示或命令「開啟日程甘特圖」。只畫畫面，資料讀 `agenda.py --json`，寫回走上面的指令並帶 `--source "Obsidian 甘特圖"`。
- 拖整條＝`move`；拉右端＝`dur`；打勾／取消＝`done`／`undone`；「＋ 新增」＝`add`；「畫接」模式點前項再點後項＝`link`，點連線＝`unlink`。
- 找不到 agenda.py → 外掛設定填「agenda.py 路徑」（plugin 以 dev 模式載入時一定要填：自動找讀的是 `installed_plugins.json`，可能指向舊版 cache）。
- 需要本機有 python；僅桌面版。

---

## 匯出（都是視圖，單向、冪等）

- **`--ics`**：全量重生，UID 固定，Google Calendar 重匯會覆蓋不重複；有工期的事件畫成開始日到完成日。給使用者檔案路徑，不代為上傳。
- **`--notify`**：只印文字、不發送。使用者要推播時，告訴他接法：OS 排程器每天定時跑 `--notify`，stdout 交給自己的 Bot（telegram plugin 的 token 可共用）；不用 `/schedule`／`/loop`（要 session 活著、每次花 token）。
- **Notion**：未實作，同介面藍圖在 `agenda-system.md`。
