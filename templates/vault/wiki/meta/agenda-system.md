---
title: 日程系統（agenda）— 設計與擴充藍圖
type: meta
status: active
updated: {{today}}
tags: [meta, agenda, 日程, 架構]
---

# 日程系統（agenda）

> **為什麼**：vault 裡沒有日程物件時，日期散在 log／hot／README 的散文裡，「哪天要做什麼」沒地方能回答；
> 外部工具（Notion 日曆等）讀一次要上萬 token 且完成狀態沒人維護。要的是：到分鐘、省 token、可接外部日曆、架構可複製。

## 架構

```
wiki/agenda.md（唯一真相來源，一行一事）
        │
        ├─ agenda.py            ① 開場窗口：逾期／今天／7 天內              ✅ 已做（SessionStart hook）
        ├─ agenda.py --notify   ② 精簡文字 → OS 排程器 → Telegram Bot      ✅ 文字已做；排程與 Bot 由使用者接
        ├─ agenda.py --ics      ③ 全量產 .ics → Google Calendar 匯入／訂閱  ✅ 已做
        └─ agenda.py --notion   ④ 寫 Notion 資料庫（同一 exporter 介面）    ⬜ 藍圖
```

## 原則

- **外部日曆全是視圖**：只從 `agenda.md` 單向產出、不回寫、每次全量重生（冪等，沒有增量同步狀態）。
- **exporter 同一介面多個實作**：ics／Telegram 文字／Notion，加一個＝複製一個模板。
- **維護靠腳本不靠紀律**：格式由 `add` 驗、壞行由 `--check` 抓、過期由 `--tidy` 歸檔、重複事項只寫一行規則由腳本展開。
- **省 token**：開場只印窗口（≈300 tok）、查詢走參數不走 grep、主檔常駐 ≤100 行、細節 `→` 指回出處。

## 格式

```
2026-09-25 14:00-15:30  會議  X1 稽核包說明會 @會議室A   #QMS  → log 2026-09-18
2026-09-23              交件  訂閱請購單   每月23日  #行政
```

`日期 [HH:MM[-HH:MM]] 類型 標題 [重複規則] [#tag …] [→ 出處]`。沒時間＝全天。類型自由（會議／交件／待辦／提醒／出差…）。完成＝行首 `✅`。

## 指令（`python "${CLAUDE_PLUGIN_ROOT}/scripts/agenda.py" …`）

| 指令 | 做什麼 |
|---|---|
| （無參數） | 開場窗口；`--days N`／`--tag X` 可調；非 vault 或無 agenda.md 時安靜 |
| `add "…"` | 驗格式後 append；無檔則建最小骨架 |
| `done 關鍵字` | 唯一命中的未完成行加 `✅` |
| `--check` | 壞行、可歸檔行數（exit 0） |
| `--tidy` | `✅` 與 30 天前的非重複事件搬到 `wiki/agenda-archive.md` |
| `--ics [out]` | 全量重生 `.ics`（預設 `<vault>/agenda.ics`）；UID＝md5(日期＋標題)，重匯覆蓋不重複；重複事件展開 365 天 |
| `--notify` | 同窗口、Telegram 友善的精簡文字；只印不發送 |

## 藍圖

- **② 每日推播**：OS 排程器（Windows 工作排程器／cron）每天 08:30 跑 `--notify`，stdout 餵 Bot API。**0 token、不需 Claude session**；弱點是電腦要開機。不用 `/schedule`／`/loop`：只在 session 活著時跑且每次花 token。
- **③ Google Calendar**：匯入 `agenda.ics` 即可；會前 N 分鐘提醒交給 Google。要自動同步需公開可達的 ics URL（私 repo 不行）。
- **④ Notion**：同 exporter 介面，`任務`＝標題自帶所有資訊、`工作排程`＝日期／時段。未實作。

## 相關

- [[../agenda]] — 資料本體
- `wiki/hot.md` — **不放日程**；有到期日的待辦寫一行進 agenda
