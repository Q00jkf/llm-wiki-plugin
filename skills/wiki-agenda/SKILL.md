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
| 「XX 做完了」 | `done 關鍵字` |
| 「匯到 Google Calendar」 | `--ics` |
| 「每天推播到 Telegram」 | `--notify` ＋ 說明接法（見下） |

---

## 指令

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/agenda.py"                       # 逾期／今天／7 天內
python "${CLAUDE_PLUGIN_ROOT}/scripts/agenda.py" --days 14 --tag QMS
python "${CLAUDE_PLUGIN_ROOT}/scripts/agenda.py" add "2026-09-25 14:00-15:30 會議 X1 說明會 #QMS → log 2026-09-18"
python "${CLAUDE_PLUGIN_ROOT}/scripts/agenda.py" done 說明會
python "${CLAUDE_PLUGIN_ROOT}/scripts/agenda.py" --check
python "${CLAUDE_PLUGIN_ROOT}/scripts/agenda.py" --tidy
python "${CLAUDE_PLUGIN_ROOT}/scripts/agenda.py" --ics [out.ics]
python "${CLAUDE_PLUGIN_ROOT}/scripts/agenda.py" --notify
```

格式：`日期 [HH:MM[-HH:MM]] 類型 標題 [每月D日|每週X|每年MM-DD|每N天] [#tag …] [→ 出處]`

---

## 規則

- **`add` 前先把使用者的話換成一行**：日期補全年份、時間 24 小時制、類型用一個詞（會議／交件／待辦／提醒／出差）、細節不塞標題，用 `→` 指回 log／catalog。
- **重複事項只寫一行規則**，不手抄多行；腳本展開下一次。
- **`done` 要唯一命中**：命中 0 或 >1 行會拒絕，換更精確的關鍵字。
- **不手改 `✅` 之外的既有行**；要改內容就 `done` 舊行再 `add` 新行（歸檔留痕）。
- 開場窗口出現 🔴 逾期 → 提一句，問使用者要 `done` 還是改期，不代為決定。
- `--check` 有壞行 → 報行號，請使用者修或由你修成合格格式（Obsidian 手打常漏空白）。

---

## 匯出（都是視圖，單向、冪等）

- **`--ics`**：全量重生，UID 固定，Google Calendar 重匯會覆蓋不重複。給使用者檔案路徑，不代為上傳。
- **`--notify`**：只印文字、不發送。使用者要推播時，告訴他接法：OS 排程器每天定時跑 `--notify`，stdout 交給自己的 Bot（telegram plugin 的 token 可共用）；不用 `/schedule`／`/loop`（要 session 活著、每次花 token）。
- **Notion**：未實作，同介面藍圖在 `agenda-system.md`。
