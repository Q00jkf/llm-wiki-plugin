# LLM Wiki

**讓 Claude 幫你管專案文件，打造自己的 AI 第二大腦，當你和團隊的秘書。**

跑在 Obsidian 上，用 Claude Code 操作。檔案留在原地，不搬、不抄，要用時一句話就找到。

適合手上專案很多、文件散在各處、每天在不同專案間切換的人。

它幫你做到：

- 要什麼文件，講一句就找到，還告訴你在哪一頁
- 團隊資訊同步，交接不斷線
- 日程、進度、雜事交給它記，你只做判斷
- 說「開工」「收工」就幫你接上次進度、收尾落盤，明天不用從頭想
- 同時開好幾個 Claude 分工時，有主管派工、驗收、追誰卡住（選裝的像素辦公室讓你一眼看到大家在做什麼）
- 搭配 Claude Code 的連接器，同一個入口管 Google Drive、Email、日曆、Telegram —— 它是中控台，其他工具接進來
- 一天就能把 AI 導入現有的工作流程，不用改變你放檔案的習慣

---

## 像跟秘書講話一樣用它

| 你想… | 你說 |
|---|---|
| 找某份文件、問裡面寫什麼 | 「查一下 XX 的規格」 |
| 記一件某天要做的事 | 「9/25 下午有個會」 |
| 開一個新專案的資料夾 | 「開一個新專案夾」 |
| 把散在各處的專案收進來管 | 「把 XX 專案也掛進來」 |
| 交接給同事、同步團隊狀態 | 「XX 專案現在到哪了」 |
| 把日程送到你常用的工具 | 「把這週日程匯到 Google 日曆」「推到 Telegram」 |
| 知道系統現在健不健康 | 「健檢一下」 |
| 一天的開始／結束 | 「開始工作」「收工」 |
| 同時開好幾個 Claude，找人分工、看誰卡住 | 「你來當主管」「大家在做什麼」 |

不用背指令。用平常說話的方式講，它會自己接。

---

## 三步開始

```
/wiki-init          在你要放資料的資料夾跑，回答三個問題
/wiki-ingest raw/   丟一份文件進 raw/，看它變成什麼
/wiki-coach         卡住就問它，它只告訴你下一步做什麼
```

不必先讀完文件。剛開始它會多解釋，用熟了就安靜。

---

## 系統教練：不知道下一步就問它

```
/wiki-coach
```

它看你的 vault 現況，**只講一件現在該做的事**，附一句為什麼。做完再叫它，它講下一件。
也可以直接問：「為什麼不能把數字抄進 wiki」「我這張卡寫得對嗎」「這份要不要收進來」。
剛開始用的人靠它就夠，不用讀完這份文件。

要它每次開場都講一件事：`/wiki-coach on`；嫌吵：`/wiki-coach off`；預設 `auto`（新 vault 講、用熟了就安靜）。

這是存在該 vault 裡的設定，同事 clone 下來也一樣。想只改自己的，在 `~/.claude/settings.json` 加：

```json
{ "env": { "LLM_WIKI_COACH": "on" } }
```

個人設定會蓋過 vault 設定。

---

## 指令

| 指令 | 做什麼 |
|---|---|
| `/wiki-init` | 建立新 vault，問三題後產出骨架 |
| `/wiki` | 現況：規模、有沒有老化訊號、下一步 |
| `/wiki-new <名稱>` | 開一個新工作夾，附進度儀表板（`_README.md`） |
| `/wiki-agenda add "…"` | 記日程；不帶參數印逾期／今天／7 天內 |
| `/wiki-repo add <路徑>` | 把外部專案掛進來管，檔案留原地；`discover` 幫你找、`scan` 看變更 |
| `/wiki-ingest <檔>` | 把一份文件收進 wiki（建索引卡，不抄內容） |
| `/wiki-query <問題>` | 查詢，附來源；要數字時幫你開原檔 |
| `/wiki-coach` | 系統教練，只講下一步 |
| `/wiki-doctor` | 健檢：找過期、孤兒、死連結、規則漂移 |
| `/wiki-start` | 開始工作：接上次進度、做 vault 自訂開工項（`wiki/ops/start.md`）、向主管報到 |
| `/wiki-end` | 結束工作：寫 hot.md 今日結論、落盤、commit、交接；vault 自訂收尾項在 `wiki/ops/end.md` |
| `/wiki-collab` | 同時開多個 Claude session 時的協調（主管制） |
| `/wiki-meet` | 開會：主管出題、點名參與者，參與者依職責提案並互相討論，結果寫進指定資料夾、散會通知主管 |
| `/wiki-fold` | log 太長時摺疊成摘要 |
| `/wiki-adopt` | 本來就有 wiki 的人接上這套系統 |

---

## 腳本：不開 Claude 也能跑

系統的判斷都在 Python 腳本裡，可以單獨執行、可以排程。路徑前綴 `~/.claude/plugins/cache/llm-wiki/llm-wiki/<版本>/scripts/`。

| 腳本 | 做什麼 |
|---|---|
| `vault_state.py` | vault 規模與老化訊號（`--json` 給程式讀） |
| `coach.py` | 下一步該做的一件事（`--all` 全列） |
| `agenda.py` | 日程：`add`／`done`／`--ics` 匯 Google 日曆／`--notify` 產推播文字 |
| `repo.py` | 外部專案：`discover`／`add`／`list`／`scan`／`remove` |
| `new_folder.py <名稱>` | 開工作夾（`--dry-run` 先看） |
| `stale_check.py raw/…` | 哪些原始檔改過、wiki 可能過期 |
| `tidy_check.py --quiet` | 快照檔有沒有該清的待辦 |
| `rules_check.py --quiet` | 規則檔跟實際狀況對不對得上 |
| `log_index.py --query <詞>` | 查操作日誌 |
| `adopt.py` | 既有 vault 要改用本系統：算差異、找撞名（`/wiki-adopt` 的後端） |
| `occupancy_check.py` | 多人同時改同一個檔的違規偵測（`/wiki-collab` 的後端） |
| `audit_copy_check.py` | 取用副本夾與正本的一致性 |

其餘 4 支是內部件，由指令或 hook 驅動，不必手動跑：
`init_vault.py`（`/wiki-init`）、`wiki_fold_parse.py`（`/wiki-fold`）、
`big_read_guard.py`（PreToolUse：擋整份讀大檔）、`_guard_status.py`（守門分類帳）。
另有 `_lib/` 放共用函式。

開 Claude Code 時 `vault_state`／`tidy_check`／`agenda`／`rules_check` 會自動跑一次，有事才出聲。

---

## 四個原則，知道就好

**1. 資料留在原地。** 系統不搬你的檔案，只記「有什麼、在哪裡、哪一頁」。你放檔案的習慣不用改。

**2. 憑證檔一律不收。** 掛進來的專案裡如果有 `.env`、`secrets.txt`、`密碼.xlsx` 這類檔，系統**不收進候選、不 ingest、不寫進 wiki**，並在畫面上列出擋掉了哪幾個。
三道防線：掛載時排除、編譯時再擋一次、`.claude/settings.json` 的 deny。
（擋不住你自己用 `cat` 去讀 —— 是減速丘不是保證。）

**3. 不抄會變的東西。** 規格數值、價格、量測數據不會被複製進 wiki。要看數字，它幫你開原本那份檔。
抄一份，原檔改了它不會跟著改，遲早變成錯的。

**4. 它是中控台，不是另一個資料庫。** Google Drive、Email、日曆、Telegram 這些工具照舊用，
透過 Claude Code 的連接器接進來；wiki 只記「東西在哪、誰負責、什麼時候」，讓你從一個入口指揮全部。

---

## 四個問題

**可以接 Google Drive、Email 嗎？**
可以，靠 Claude Code 的連接器（MCP）。裝好連接器後，在同一個對話裡叫它查信、開 Drive 的檔、寫日曆，wiki 負責記住結果放在哪。
日程匯出（`.ics`）和 Telegram 推播文字是內建的，不用另裝。

**它會改我的檔案嗎？**
不會。你的原始檔它只讀。它自己寫的東西都在 `wiki/` 資料夾，每次改完會告訴你改了哪個檔。

**init 之後它會動我的設定嗎？**
不會。`CLAUDE.md` 是你的，init 幫你填一次，之後只有你能改。

**可以多人一起用嗎？**
同事自己裝、自己掛同一個 GitHub repo 就好。誰能改哪個 repo 看擁有者，預設都是唯讀。

---

## 需要什麼

| | |
|---|---|
| Claude Code | 有 `/plugin` 指令的版本 |
| Python | 3.9 以上，不用裝套件 |
| Obsidian | 建議，不裝也能用 |
| git | 建議 |

---

## 安裝

```
/plugin marketplace add Q00jkf/llm-wiki-plugin
/plugin install llm-wiki
```

### 選裝：pixel-office 像素辦公室

同一個 marketplace 還有一個**選裝**的 plugin。它是一個 **Claude Code MOD**（用 function hooks 寫的即時面板），
把同時開著的每個 Claude Code session **視覺化**成一間像素辦公室：每個 session 是一位同事，坐在自己的桌子前工作。

<img src="plugins/pixel-office/docs/office.png" alt="像素辦公室：主管室、TEAM 區、等待核准的問號、被擋下的紅牌、紙飛機與橘貓" width="420">

- **一眼看出大家在做什麼**：打字、讀檔、思考、出錯、完成，小人的動作和螢幕顏色即時反映
- **誰卡住了**：等你核准的人頭上冒黃色問號；被權限擋下、要你在它的視窗說「放行」的人舉紅牌，其他視窗會跳提醒
- **有組織**：主管坐主管室，主管的 peer 坐 TEAM 區，傳訊息時有紙飛機飛過去
- **對外動作看得到**：寄信走去影印機、上傳文件走去檔案櫃、`git push` 走去郵筒
- **模型也看得到**：用 `office_roster` 查「誰是誰、該傳訊息給誰、誰在等放行」

畫面全由程式即時畫出，不花 token。不裝不影響 llm-wiki。

```
/plugin install pixel-office@llm-wiki
```

重開 Claude Code 後輸入 `/office`。用法與個人按鈕設定：[plugins/pixel-office/README.md](plugins/pixel-office/README.md)

---

## 想知道更多

為什麼這樣設計、規則的來由、完整腳本參數：[docs/design.md](docs/design.md)

## 授權

MIT © 2026 呂冠佑、呂筱婕
