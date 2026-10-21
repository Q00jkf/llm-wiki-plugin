---
name: wiki-agenda
description: "日程：wiki/agenda.md 是唯一真相來源，agenda.py 讀寫；排期、查逾期、匯 ics／推播。Triggers: 日程, 行程, 排程, 哪天有會, 要交件, 每月幾號, 這週要做什麼, 逾期, 提醒我, agenda, 日曆。"
---

# wiki-agenda：日程

**一句話：日程一律在 `wiki/agenda.md`，不另建提醒清單、不寫進 `hot.md`。**
設計與藍圖在 vault 的 `wiki/meta/agenda-system.md`。

---

## 何時用

| 使用者說 | 做 |
|---|---|
| 「X 日有會」「Y 要交件」「每月 D 日做 Z」 | `add` |
| 「這週／這幾天要做什麼」「有沒有逾期」 | 印窗口（`--days`／`--tag` 可調） |
| 「XX 做完了」／「勾錯了」 | `done 關鍵字`／`undone 關鍵字` |
| 「XX 改到某天」「延一週」 | `move 關鍵字 YYYY-MM-DD` |
| 「XX 要做 N 天」 | `dur 關鍵字 N` |
| 「B 要等 A 做完」 | `link B A`（A 沒代號加 `--id`） |
| 「專案排得過來嗎」「哪些是要徑」 | `plan` |
| 「匯到 Google Calendar」 | `--ics` |
| 「每天推播到 Telegram」 | `--notify` ＋ 說明接法（見下） |

---

## 指令

```bash
A="${CLAUDE_PLUGIN_ROOT}/scripts/agenda.py"
python "$A"                                  # 逾期／今天／7 天內
python "$A" --days 14 --tag 產品A
python "$A" add "2026-09-25 14:00-15:30 會議 設計審查 #產品A → log 2026-09-18"
python "$A" done 設計審查                     # 重複事件＝只完成這一次（日期跳到下一次）
python "$A" undone 設計審查
python "$A" move 設計審查 2026-09-30          # 自動記 原定:；接它的後項一起平移
python "$A" dur 打樣 5                        # 改工期：開始日不動
python "$A" link 打樣 設計審查 [--type SS] [--lag 2] [--id d1]
python "$A" unlink 打樣 d1
python "$A" plan                              # 各組開始／完成／寬裕／要徑★
python "$A" --check                           # 壞行、相依問題、硬期限會延誤
python "$A" --fmt                             # 依第一個 #tag 分段排序（寫入時也會自動做）
python "$A" --tidy
python "$A" --ics [out.ics]
python "$A" --notify
python "$A" --json                            # 甘特圖外掛讀
```

格式：`日期 [HH:MM[-HH:MM]] 類型 標題 [專案欄位] [每月D日|每週X|每年MM-DD|每N天] [#tag …] [→ 出處]`

專案欄位（選填，甘特圖與排程引擎用）：`工期N天`（行首日期＝最後一天）、`代號:x`、`接:a,b`（`接:a+2`＝隔 2 工作天；`接:a~SS`＝類型 SS／FF／SF）、
`完成:MM-DD`（done 自動寫）、`原定:MM-DD`（move 自動寫）、`截止:MM-DD`、`進度:60%`、`屬:x`（母項日期由子項推出）。

排程引擎：工作天扣國定假日（`raw/manager/schedule/ref/辦公日曆表_*.csv` 有才扣，沒有只扣週末）；
前項延誤 → 後項自動順延並記 `raw/manager/schedule/changes.md`；**交件／稽核／會議是硬期限，不推**，只在 `--check` 報會晚幾天。

---

## 規則

- **`add` 前先把使用者的話換成一行**：日期補全年份、時間 24 小時制、類型用一個詞（會議／交件／待辦／提醒／出差）、細節不塞標題，用 `→` 指回 log／catalog。
- **重複事項只寫一行規則**，不手抄多行；腳本展開下一次。
- **`done` 要唯一命中**：命中 0 或 >1 行會拒絕，換更精確的關鍵字。
- **改期用 `move`、改工期用 `dur`，不要 `done` 舊行再 `add` 新行**（會斷掉 `接:` 相依、丟掉 `原定:` 基準）。
  Claude 代改時加 `--source agenda`，變更記進 changes.md。
- 甘特圖外掛（模組 `agenda-gantt`）會把同一份 `agenda.py` 裝進 vault 的 `scripts/`；vault 裡那份是安裝出來的複本，不要直接改。
- 開場窗口出現 🔴 逾期 → 提一句，問使用者要 `done` 還是改期，不代為決定。
- `--check` 有壞行 → 報行號，請使用者修或由你修成合格格式（Obsidian 手打常漏空白）。

---

## 匯出（都是視圖，單向、冪等）

- **`--ics`**：全量重生，UID 固定，Google Calendar 重匯會覆蓋不重複。給使用者檔案路徑，不代為上傳。
- **`--notify`**：只印文字、不發送。使用者要推播時，告訴他接法：OS 排程器每天定時跑 `--notify`，stdout 交給自己的 Bot（telegram plugin 的 token 可共用）；不用 `/schedule`／`/loop`（要 session 活著、每次花 token）。
- **Notion**：未實作，同介面藍圖在 `agenda-system.md`。
