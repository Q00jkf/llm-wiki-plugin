# CHANGELOG

> **「某一版出了什麼」的正本。** 在這之前這件事只存在 commit message 裡，
> 所以 vault 端自己抄的版本紀錄開張同一天就落後兩版（ISS-005）。
>
> 🔴 **bump `plugin.json` 的那個 commit 要同時寫這裡**，不要事後補 —— 事後補就會變成第二份會漂的清單。
> 一版一段、最新在上。每段四件事：**改了什麼／為什麼／commit／issue**。
> 「為什麼」只寫 commit 內文或使用者裁示裡有的；查不到寫「待補」，**不推測**。
>
> 這個 repo 裝兩個 plugin，版號各自獨立：`llm-wiki`（`.claude-plugin/plugin.json`）、
> `pixel-office`（`plugins/pixel-office/.claude-plugin/plugin.json`）。
> 1.3.1～1.7.3 與 0.10.0～0.10.5 是 2026-10-10 從 git log 補記的。

---

# llm-wiki

## 1.12.0 — 2026-10-21

- **改了什麼**：agenda 統一成一份（含排程引擎）
  - `scripts/agenda.py` 換成完整版：`undone`／`move`／`dur`／`link`／`unlink`／`plan`／`--fmt`／`--json`、專案欄位（工期／代號／接／完成／原定／截止／進度／屬）、寫入鎖、分段排序、changes.md 變更紀錄；保留原有 `--ics`／`--notify`、非 vault 安靜、只有未過濾的執行才寫 `_guard-status`
  - 新增 `scripts/agenda_cpm.py`（工作天曆、順延、要徑）；辦公日曆路徑改由 agenda.py 傳入，沒有日曆只扣週末
  - vault 根目錄：檔案在 vault 的 `scripts/` → 上一層；放在 plugin → 從 `CLAUDE_PROJECT_DIR`／cwd 往上找。排程資料夾 `raw/manager/schedule/` 只在 agenda.py 定義一次（`SCHEDULE`）
  - addon agenda-gantt 0.4.0：`scripts` 改列 `agenda.py`、`agenda_cpm.py`，由 plugin 的 `scripts/` 裝進 vault（`addons.py`：模組 scripts/ 沒有的檔取 plugin scripts/）；`requires` 拿掉 `scripts/agenda.py`；沒有 XSD 副本時 XML 照產、標「未驗」
  - `wiki-agenda` skill、vault 範本 `agenda-system.md` 改教新指令；改期用 `move`，不再「done 舊行再 add 新行」
- **為什麼**：甘特圖依賴的完整版 agenda.py 只存在於單一 vault，其他 vault 裝了甘特圖也跑不起來（2026-10-21 在兩個 vault 實測 `ModuleNotFoundError`／`AttributeError: ROOT`）；使用者 10-21 裁示「統一用我們的，之後好管理」
- **升級注意**：vault 已自備 `scripts/agenda.py`／`agenda_cpm.py` 的，裝 agenda-gantt 0.4.0 會停在「vault 有改動」—— 先確認那兩支沒有 vault 專屬改動，再 `install agenda-gantt --force`
- **commit**：待補
- **issue**：無

## 1.11.0 — 2026-10-20

- **改了什麼**：addon pdf-translate 0.3.0 —— 可改走轉發伺服器
  - vault 放 `local-config.json`：`{"endpoint": "<轉發伺服器>/v1/messages", "keyEnv": "<環境變數名>"}`；沒有此檔＝照舊直連、讀 `ANTHROPIC_API_KEY`
  - 檔裡只寫「去哪個環境變數拿」，通行碼放各人電腦，不進 git
  - 🔴 設定**全對才採用，否則整份不用、維持直連＋側欄警告**（主管審查）：`keyEnv` 必填且須以 `_PROXY_TOKEN` 結尾；http 只准私有位址（localhost／127／10／172.16–31／192.168／*.local），外網一律 https。理由：此檔跟著 git，有 push 權的人改一行 endpoint 就能把同事的 `ANTHROPIC_API_KEY`（或任一環境變數的密碼）送出去
  - 沒設通行碼時錯誤訊息改講「轉發伺服器的個人通行碼，請向管理者申請」
  - `local-config.json` 列入 addon.json 的 `local`（安裝不覆蓋）；新增 `addons/pdf-translate/test_conn.js`（14 項）
- **為什麼**：使用者 10-20 裁示 API 走自架轉發、金鑰只在伺服器，同事用個人通行碼；plugin 正本不放公司網址
- **commit**：待補
- **issue**：無

## 1.10.1 — 2026-10-20

- **改了什麼**：防降版同時比 plugin 版號 —— 安裝紀錄多記 `plugin`；內容不同時，addon 版號**或** plugin 版號比本機舊 → 「plugin 比較舊」。內容相同照樣算最新。測試 +2（共 13）
- **已知限制**：addon 與 plugin 版號都沒 bump 就改內容，仍分不出新舊 —— 發版一律 bump `plugin.json`（本 repo CLAUDE.md 既有規則）
- **為什麼**：主管審 1.10.0 指出只比 addon 版號時，改內容忘了 bump 那個 addon 就會被當成「需更新」而降版；三個 addon.json 自 64d96fb 起都沒改過版號
- **commit**：待補
- **issue**：無

## 1.10.0 — 2026-10-20

- **改了什麼**：addons 兩項
  - 防降版：安裝紀錄版本比本機正本新 → 狀態「plugin 比較舊」，`install`／`update` 停下（`--force` 才裝）；版本比數值（0.10 > 0.9）
  - 新模組通知：沒裝也沒 `dismiss` 的模組，`check` 與開場報「有新模組可裝」；新指令 `dismiss`，選擇記在 `.obsidian/llm-wiki-addons.json`（跟著 git）；`install` 自動取消 dismiss
  - `vault_state` 老化訊號帶版本對照與對應提示；測試 +4（共 11）
- **為什麼**：1.9.0 只比內容不比版本，多人共用時先升級的人裝了新版，沒升級的人會被提示「需更新」並蓋回舊版；且新模組沒有任何人會知道（使用者 10-20 問「怎麼知道是最新」）
- **commit**：待補
- **issue**：無

## 1.9.0 — 2026-10-20

- **改了什麼**：新增可選裝模組
  - `addons/`：agenda-gantt 0.3.0、pdf-translate 0.2.0、toolbox 0.1.0（Obsidian 外掛＋各自的腳本）
  - `scripts/addons.py`：list／install／update／check；安裝紀錄分辨「需更新」與「vault 複本被改過」，後者不覆蓋
  - `vault_state` 老化訊號加「模組需更新／vault 有改動」，只看已裝的
  - pdf-translate 新增 vault 自有的 `local-rules.json`（接在問 wiki／各動作的系統提示後），安裝不覆蓋
  - 新 skill `wiki-addons`；`wiki-doctor` 表加一列；測試 `test_addons.py`
- **已知限制**：新版刪掉或改名的檔，vault 裡的舊檔不會被收掉（例：`scripts/` 的舊腳本），要手動刪
- **為什麼**：使用者 10-20 要拆成多個 vault，自製外掛原本每個 vault 手動複製一份會對不上；要可選裝、doctor 提醒更新。外掛作者改為使用者本人、去除特定公司內容（使用者裁示）
- **commit**：待補
- **issue**：無

## 1.8.0 — 2026-10-10

- **改了什麼**：三個「假訊號」bug ＋ 本檔
  - `skeleton_check`：骨架紀錄比本機 plugin 新時不再印「🟢 骨架已是最新」，改印「本機 plugin 比骨架舊，先更新 plugin」並回 exit 1（`downgrade_note()`）
  - `rules_check` F1：`` `raw/members/<人>/` `` 這種帶佔位符的尾段不再讓整列對不上
  - `vault_state`：掛載路徑不在、但 `owner.machine` 標明是別人機器 → 不報「路徑失效」，在「外部 repo」那行標「（<機器> 上，本機沒有）」
  - 新增 `CHANGELOG.md`；`CLAUDE.md`「改完要做的」加一步
  - 新增測試 `test_rules_check.py`、`test_vault_state.py`，`test_skeleton_check.py` 加 2 支
- **為什麼**：三者都是**多人共用同一個 vault 才會走到的路徑**，而且三者都讓守門說謊
  - `downgrade` 旗標在 `classify` 設了卻**沒有任何地方讀**。`.skeleton.json` 跟著 git 走，誰先升 plugin，所有沒升的人都被告知「已是最新」
  - 「按人分 `raw/`」是多人 vault 的標準做法，所以每個多人 vault 每場開場都會被誤報一次
  - `raw/.manifest.json` 是 tracked、掛載路徑是相對 vault 根的，所以除了註冊者以外每個人每場都看到「repo 路徑失效」
  - 🔑 後兩者的代價不是那兩行字，是**每天唸同一句會訓練所有人忽略整個老化訊號區**，連帶漏掉真的問題
- **commit**：`ee23d4a`（ISS-002）、`2090502`（ISS-003）、`809faa7`（ISS-004）、本段所屬 commit（ISS-005）
- **issue**：ISS-002、ISS-003、ISS-004、ISS-005

## 1.7.3 — 2026-10-10

- **改了什麼**：清掉 9 處 `/wiki-collab｜/wiki-meet｜/wiki-role` 死引用；`test_template_coverage.py` 加「文件教的指令必須叫得到」；落盤判準改寫
- **為什麼**：1.6.0 刪 command 後自己的文件還在教舊指令，其中 `templates/vault/wiki/ops/collab.md` 已透過骨架升級散播進 vault；第一版落盤判準被 vault 側以四支腳本實證駁回
- **commit**：`fa7287d`
- **issue**：無

## 1.7.2 — 2026-10-10

- **改了什麼**：「訊息只傳路徑與一句話」從 `meet.md` 的開會流程升為 `wiki-collabteam` 通則；`agenda.py` 過濾查詢不再落盤
- **為什麼**：主管回報 2026-10-09 當天 12 則跨 session 訊息、數則超過 1000 token；`--days`／`--tag` 是文件明文教的查詢，卻會蓋掉完整掃描結果，讓趨勢誤顯示「5 項降到 1 項」
- **commit**：`021a856`
- **issue**：無

## 1.7.1 — 2026-10-09

- **改了什麼**：`roles/README.md` 三行 `/wiki-role take｜list｜new` 改成觸發詞＋`role_cards.py list`；補 bump 版號
- **為什麼**：那三個 command 在 1.6.0 已刪，樣板還在教一個會失敗的用法
- **commit**：`2476846`、`b377b18`
- **issue**：無

## 1.7.0 — 2026-10-09

- **改了什麼**：樣板補 5 項（manifest `occupancy_ignore_authors`、coordination 裁定編號改 `裁定-N`、待辦表登記日說明、log init 標記、`wiki/meta/init-history.md`）；新增 `test_template_coverage.py`
- **為什麼**：「功能變了、樣板沒跟上」沒有東西在管。其中 `occupancy_ignore_authors` 不設的話，掛 obsidian-git 的 vault 佔用表當天就廢（實證：一個檔三天 76 筆全是備份帳號）
- **commit**：`f0ac208`、`530a348`、`354aa75`
- **issue**：無

## 1.6.0 — 2026-10-09

- **改了什麼**：`wiki-start`＋`wiki-end` 合併成 `wiki-day`；刪除 `/wiki-collab`、`/wiki-meet`、`/wiki-role` 三個 command
- **為什麼**：使用者裁示「合併後原本的指令需要刪除，不然我合併做什麼」。三個舊 command 的 description 仍吃 230 tok/session；always-on 2,557 → 2,289
- **commit**：`042434f`
- **issue**：無

## 1.5.2 — 2026-10-09

- **改了什麼**：樣板補 `wiki/meta/roles/README.md`
- **為什麼**：新 vault 看不到 `roles/`，使用者不會知道有角色卡機制（功能本身沒壞）
- **commit**：`2c24ef1`
- **issue**：無

## 1.5.1 — 2026-10-09

- **改了什麼**：骨架對帳加「樣板刪檔」偵測（retired 群組）、死 glob 測試、`--record` 封存組③與 opted_out
- **為什麼**：spec 說好沒做；skill 規則改了但樣板沒反映時對帳完全偵測不到（實例：T9 要求的登記日）
- **commit**：`da8046f`、`403d3b2`、`825b1f0`
- **issue**：無

## 1.5.0 — 2026-10-09

- **改了什麼**：`/wiki-init` 目標已是 vault 時進升級模式（對帳 → 三組分開問 → 同意才寫）；降噪規則移到 `.skeleton-policy`
- **為什麼**：建骨架是一次性快照，plugin 升級後舊 vault 的檔永遠停在建立那天，而且**沒有東西會發現**
- **commit**：`bd57188`、`c3bd9d1`、`6dcbaab`、`fe424d8`、`7381fc2`
- **issue**：無

## 1.4.0 — 2026-10-09

- **改了什麼**：skill 16 → 14（`wiki-collab`／`wiki-meet`／`wiki-role` 併成 `wiki-collabteam`）、13 個 description 瘦身、`tidy_check` 加 T9、新增 plugin repo 的 `CLAUDE.md`
- **為什麼**：always-on 成本 3,977 → 2,524 tok/session；不 bump 的話 cache 與 dev repo 同為 1.3.1 但內容不同、分不出是哪一份
- **commit**：`5c8a87e`、`0747f28`、`87efc85`、`8d39267`、`d81efdc`、`e2fd3df`、`c47537b`
- **issue**：無

## 1.3.1 — 2026-10-07

- **改了什麼**：每件事只留一個家（進度 → `_README`、職責 → 角色卡、在線狀態 → `coordination.md`）；角色卡改用 Obsidian 連結，`role_cards.py check` 檢查連結老化
- **為什麼**：使用者要求角色卡不要跟 `_README` 重疊、指標要確定不會老化
- **commit**：`5c4640a`
- **issue**：無

> 1.3.1 之前（1.0.x～1.3.0）尚未補記。要查就看 `git log -p -- .claude-plugin/plugin.json`。

---

# pixel-office

## 未發版（0.10.5 之後）

- **改了什麼**：山雀加一支渲染層測試（連續 8 格白色像素數必須相同）
- **為什麼**：使用者截圖回報跳起來頭還是被切掉。實測程式正確，使用者看到的是 1–2 天前開的 session 載入的舊版 —— plugin 在 session 啟動時載入記憶體，在跑的視窗不會重讀
- **commit**：`ae18a60`
- **issue**：無

## 0.10.5 — 2026-10-08

- **改了什麼**：開會點名改用 ref 比對；山雀跳躍改成整隻位移
- **為什麼**：agent 名稱與名牌都不唯一（實測兩個 session 同名、四個名牌同為 `user`），點名會抓錯人；跳躍原本是裁掉頂端列來假裝上移，切掉的正是頭
- **commit**：`722f986`
- **issue**：無

## 0.10.4 — 2026-10-08

- **改了什麼**：`office_roster` 加 ref 欄，撞名時直接給可貼的定址字串
- **為什麼**：同名 session 時 `SendMessage` 必須帶 `[ref]`，原本得再跑一次 `ListAgents`
- **commit**：`99fb0d0`
- **issue**：無

## 0.10.3 — 2026-10-07

- **改了什麼**：銀喉長尾山雀改回側面，羽色照圖鑑
- **為什麼**：使用者覺得斜前方看起來奇怪，要求先查北海道シマエナガ照片再上色
- **commit**：`cf8406d`
- **issue**：無

## 0.10.2 — 2026-10-07

- **改了什麼**：山雀照使用者給的照片重畫（斜前方視角）
- **為什麼**：使用者貼照片要求
- **commit**：`dc68a45`
- **issue**：無

## 0.10.1 — 2026-10-07

- **改了什麼**：山雀改成全白
- **為什麼**：使用者：「山雀是全白的」
- **commit**：`1baceaf`
- **issue**：無

## 0.10.0 — 2026-10-07

- **改了什麼**：新增可切換的寵物銀喉長尾山雀（貓 → 寶寶 → 山雀）
- **為什麼**：使用者要求「多加一個可以切換的寵物」
- **commit**：`714e53c`
- **issue**：無

> 0.10.0 之前尚未補記。要查就看 `git log -p -- plugins/pixel-office/.claude-plugin/plugin.json`。
