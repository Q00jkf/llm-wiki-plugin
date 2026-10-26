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

## 1.14.1 — 2026-10-26

- **改了什麼**：修 1.14.0 多主管的判錯人與文件矛盾（B 期驗收 B1～B6）
  - `role_cards.py`：主管欄取整格（去粗體、去 `[ref]`），不再套「至少一個連字號」的名稱正則 —— 中文名（`willy主管辦公室`）或沒連字號（`office`）的主管不再整列被丟、peer 被判給別人；任何一列讀不出名稱時不走「只有一位」「唯一範圍空白」退路
  - `role_cards.py`：舊「# 目前主管」只讀標題下第一個非空、非註解行的第一個 token，抓不到回 None —— 不再往下抓到說明裡的 `llm-wiki:wiki-collabteam`（AEGIVERSE 實例，現在解析成 `GUANGUAN`）
  - `06-coordination格式.md`：範圍空白定成「單主管＝全 vault、並存＝其餘」，上線時「範圍重疊」或「兩位都空白」要先問使用者；新增「誰是我的主管」（唯一一份判斷順序，同 `current_manager`）與「多主管分工」（各改自己那列、自己 peer 的列、自己範圍的佔用；hot.md 各寫一塊、標名稱）
  - `role.md` 第 7、8 步、`wiki-day` start／end 改指向「誰是我的主管」；`end.md` 加「所屬主管離線、另有主管在線 → 向在線那位報收工」；`end-manager.md` 清理與 hot.md 指向分工；`collab.md` 路徑 1 同步範圍規則
  - 表頭改「主管（ListAgents 名稱，沒有就寫 uds 位址）」（06 與樣板）
- **為什麼**：oftest B 期驗收報告 `.team/reports/B-test.md`；修法是主管 office 2026-10-26 裁示
- **commit**：e8c47be
- **issue**：無

## 1.14.0 — 2026-10-26

- **改了什麼**：多主管 —— coordination 的「目前主管」改成「主管名單」表格（主管、範圍、peer、上線）
  - `collab.md`：上線時範圍重疊的主管仍在線先問使用者，不重疊就新增一列；佔用申請與衝突先看「檔案在誰的範圍誰裁」，跨範圍交使用者
  - `02-派工.md`：只派自己範圍內的工作；`06-coordination格式.md`：範圍空白＝全 vault、跟任何人都算重疊（單主管舊用法不變）
  - `role.md`、`wiki-day` start／end：向所屬主管報到（peer 欄有你或範圍涵蓋你的那位）；判斷不出報第一列並寫「不確定歸屬，請轉」
  - `role_cards.py`：`current_manager` 讀新表（peer 欄 → 卡上 office_team → 只有一位 → 唯一範圍空白的），舊標題「# 目前主管」照讀；樣板 `coordination.md`、`角色卡模板.md` 同步
- **為什麼**：控制塔設計稿第 0 期（jacky 2026-10-26 加入多主管）；細節與第 2、7 點補充是主管 office 2026-10-26 裁示。`coordination.md` 在 `.skeleton-policy` 排除清單，樣板改了推不到舊 vault，所以舊標題要繼續相容
- **commit**：ef65bde
- **issue**：無

## 1.13.0 — 2026-10-21

- **改了什麼**：addon pdf-translate 0.4.0 —— 問 wiki 的出處改成正本優先
  - `search_wiki`／`read_page` 回傳加一行「正本：…」，取自命中頁 frontmatter `sources:` 中 vault 內找得到的檔（最多 6 筆，找不到的不列）
  - 系統提示：出處先寫 `[[正本路徑]]`（PDF 有頁碼加 `#page=N`），wiki 頁放後面當索引；沒列正本才只寫 wiki 頁。raw/ 仍不可讀，只引用路徑
- **為什麼**：使用者 10-21「我們比較常需要的是知道 raw 的 PDF 或是筆記放在哪，通常不會看 concept」
- **commit**：待補
- **issue**：無

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

## 0.16.1 — 2026-10-27

- **改了什麼**：oftest F 期驗收（`.team/reports/F-test.md`）小修；終端機 Raster 不變
  - 選單位置（`vector.ts` `menuPlace`）：依序試家具的右、左、上、下，選單要整個留在家具所在的房間（`Hit.room`：會議室／主管室／員工區），先挑不蓋到其他可點的東西與走動、排隊的人（`VectorScene.avoid`）的那一側；選單寬照字寬算（全形 2 格＋4）。修 G1：48 欄影印機選單原本固定往左退 18 欄，蓋到排隊的人、黑貓、郵筒，現在改開在影印機上方；終端機會議選單不再壓主管室金框
  - 終端機點寵物：toast 照送，另在按鈕列右邊留一行結果約 5 秒（oftest 實機截圖看不到 toast）
  - `CELL_UNITS`、`cellAt`、`menuPlace` 搬到 `vector.ts`（純函式，預覽腳本也能用），`register.tsx` 轉出
  - 測試 144 → 148：40 個情境 × 兩種面板，每件家具的選單都在房間內；48 欄影印機選單不蓋東西；會議選單不跨進主管室；終端機點寵物留一行
- **為什麼**：主管 office 2026-10-27 信件 office-015055
- **commit**：待補
- **issue**：無

## 0.16.0 — 2026-10-27

- **改了什麼**：F 期 —— 點寵物、點家具開選單、寶寶與山雀換像素圖、走路格；終端機 Raster 像素不變（`vector.test.tsx` 40 個雜湊照過）
  - **點寵物**（`register.tsx` `overlay`／`pressPet`）：走動中點 → 貓餵飯、寶寶餵奶、山雀放飛；停著再點 → 換下一隻。底下的「餵／放／換寵物」按鈕（`c`／`b`／`p`）拿掉，`/office pet`、`/office bite` 照舊。點柯基冒愛心（只在 Desktop）
  - **家具選單**：影印機、檔案櫃、郵筒、月曆、販賣機、時鐘、會議桌 7 件，各有預設選單（`MENUS`），選一項走個人按鈕同一套 `runButton` 送 prompt；同時只開一個、有「取消」、沒有快捷鍵；畫面上沒畫的家具沒有選單
  - `buttons.json` 新格式 `{ "object": "printer", "label": "查信", "prompt": "…" }`：同 `object` 整份取代那件家具的預設選單；沒有 `object` 的舊格式照舊畫在底下那排（家具項目不佔那 6 顆名額）；`/office buttons` 分開列兩種；`buttons.example.json` 改示範新格式
  - 疊按鈕：absolute `Box`，場景單位 → 字元格 `CELL_UNITS`（終端機 1×2；Desktop 1×2.5，2026-10-27 Desktop 實測，`office-calib` 0.0.2）；Svg 被縮小時乘「面板欄數／場景寬」。Desktop 用空白 plain 按鈕鋪滿整塊；終端機中心一格 `▾`／`♥`（會蓋掉 Raster 那一格的顯示，Raster 本身的 cells 不變）；終端機寵物換格才重畫面板
  - `vector.ts`：`drawVector` 多回傳 `hits`（每件點得到的東西的框）；走廊多畫一個檔案櫃（素材沒有，照色盤畫），販賣機移到影印桌與櫃台之間、擠不下就不畫
  - 升為主管／設為員工按鈕拿掉（jacky：用不到），改角色用 `/office role`
  - **寶寶、山雀**：`build_sheet.py` 依 Sweetie 16 手繪像素圖（寶寶坐／爬、山雀停／飛）
  - **走路**：5 個人物 × 8 種上衣各多 4 格（正面左右腳、側面左右腳），抬起那隻腳短 1 像素＋1 像素起伏；往左走翻面、上下走維持正面。素材表 256×220 → 256×545，base64 約 3.1 萬字元；最大情境 SVG 65,971 字元（上限 131072）
  - 測試 136 → 144
- **為什麼**：主管 office 2026-10-27 轉 jacky 裁示（信件 office-010229、010741、010853、012052）；點擊位置先用獨立 mod `office-calib` 在 Desktop 實測定案
- **commit**：96612d9
- **issue**：無

## 0.15.1 — 2026-10-27

- **改了什麼**：oftest E 期驗收（`.team/reports/E-test.md`）B1～B4，只動 `vector.ts`，終端機不變
  - B1 會議室下排椅子底端收在房間下緣（原本伸出 1.4 單位：112 欄蓋住時鐘、48 欄伸進門洞）；時鐘改成建築最後畫
  - B2 桌上杯子的杯底移到名牌框上方，不再壓到名牌右端
  - B3 主管都穿西裝但造型不重複：依桌號從名字雜湊那個造型起找沒人用的（max 情境 cc 與主管乙原本撞同一個）
  - B4 寵物改在走動、排隊的人之前畫，窄面板排隊的人在貓前面；貓不改路線 —— 位置是跟 Raster 共用的計算，改了終端機畫面就會變
  - 測試 132 → 136
- **為什麼**：主管 office 轉 oftest 驗收報告，2026-10-27 裁示一起修
- **commit**：7ae7c8c
- **issue**：無

## 0.15.0 — 2026-10-27

- **改了什麼**：Desktop 畫面換成 2dPig「Pixel Office」素材（CC0）；終端機 Raster 一個像素都沒變（`vector.test.tsx` 40 個雜湊照過）
  - 新 `assets/build_sheet.py` → `assets/office-sheet.png`（256×220，原素材表去天空＋5 人物 × 8 種上衣色）與 `hooks/sheet.ts`（base64 約 1.4 萬字元＋裁切框）
  - `vector.ts`：新形狀 `sprite`；SVG 的 `<defs>` 只嵌一次素材表，每個圖素是巢狀 `<svg viewBox>`＋`<use href="#S">`（2026-10-27 用 Edge 以 `<img>` 開實測：`<use>` 引用 `<image>`、翻面、`image-rendering:pixelated` 都有效）
  - 長相：會議室與主管室白色後牆＋窗戶、月曆、國旗；藍磚地板；隔間＝素材灰隔板＋橘桌（人在桌後，桌子擋下半身）；會議長桌兩端照比例、中段拉長；走廊販賣機、影印桌、紅色垃圾桶當郵筒、櫃台橘桌
  - 人物：5 個造型依名字雜湊固定分配，再依名字換上衣顏色（不用橘、黃，會跟膚色糊在一起）；主管一律深藍西裝。素材沒有動畫格 → 走路、打字上下輕跳 1 個素材像素
  - 狀態泡泡、問號、紅牌、冷汗、閃光、名牌照舊向量畫；圓頭小人的眼睛表情（思考眼睛往上、眨眼）沒了，閒著改成頭旁打瞌睡的 z
  - 寵物：橘貓換素材黑貓（往右走翻面、走路輕跳）；主管室右下角趴一隻柯基（只在 Desktop，不是可切換的寵物）；寶寶、鳥照舊向量
  - 時鐘：員工區看得到的那面牆（會議室門與隔牆之間）掛數字鐘，`register.tsx` 傳現在時間（本機時區）；放不下（48 欄）就不掛
  - 團隊地毯、TEAM 牌、櫃台 YOU、核准按鈕不變
  - SVG 最大 48,278 字元（2026-10-27 實測 max-112-7，含素材表；上限 131072），測試加 < 80000 斷言
- **為什麼**：jacky 嫌 Desktop 向量畫面醜；主管 office 2026-10-27 指派 E 期換皮
- **commit**：ea50ee4
- **issue**：無

## 0.14.1 — 2026-10-26

- **改了什麼**：Desktop 向量畫面的重疊瑕疵（oftest D 期驗收第 4 節，7 類）
  - 名牌、TEAM 牌、+N 改畫在最上層（夜間也在暗幕之上），字帶描邊（深字白邊、金字深棕邊）—— 修好文件圖示壓字尾、通知紅牌蓋 TEAM 牌、貓蓋排隊名牌、被咬的人蓋自己名牌
  - 主管思考泡泡、問號、紅牌改畫在頭的右側，不再蓋到主管名牌
  - 坐不下的主管 +N 從名牌拆出來，變成桌角一顆小徽章；名牌放不下先縮字（最小 1.5）再截字，窄面板「★主管乙」完整
  - 會議室上排名牌貼牆放不下就放到人下面
  - `scenarios.ts` 的 max 情境改帶開會座位（參加者改成閒著的人，會議室真的有人）；Raster 鎖的 8 個 max hash 用 0.13.2（9fe6804）的 scene.ts 重算，終端機畫法沒動
  - SVG 最大約 4.9 萬字元（2026-10-26 實測，上限 131072）
- **為什麼**：主管 office 轉 oftest 驗收報告
- **commit**：de022bd
- **issue**：無

## 0.14.0 — 2026-10-26

- **改了什麼**：Desktop 辦公室改畫向量（設計稿第 2 期）
  - 新 `hooks/vector.ts`：吃跟 `drawScene` 同一份 crew、座位、SceneOptions，輸出形狀清單（圓角矩形、圓、橢圓、路徑、文字），純資料不依賴 `$`；`vectorSvg` 轉成 SVG（磁磚用 `<pattern>`，夜間蓋暗幕、螢幕與問號畫在暗幕上）
  - 人物：圓頭＋兩眼，依 mode 換表情 —— thinking 眼睛往上＋泡泡、error 冒汗發抖、done 跳一下＋閃光、waiting 頭上問號、idle 8 格眨一次眼、typing 手動、reading 拿紙、blocked 紅牌
  - 名牌、門牌（會議室／主管室）、TEAM 牌可中文，依顯示寬度截字（全形算 2）
  - Desktop（Svg）改用向量；終端機（Raster）的 `drawScene`＋`encode` 不動，新測試用 40 個情境的 hash 鎖住跟 0.13.2 逐位元相同
  - SVG 大小（2026-10-26 實測）：最大情境 112×80、30 人＋貓＋紙飛機＋開會＋排隊約 4.6 萬字元（點陣版 8.0 萬），上限 131072
  - 新 `hooks/scenarios.ts`（測試與截圖共用的情境）；`scene.ts` 只多 export 常數與配色
  - 沒做：支援圖片的終端機（`Image` 元素）、眼睛看向游標 —— 設計稿列為之後
- **為什麼**：設計稿第 2 期；點陣在 Desktop 放大後糊、名牌不能寫中文
- **commit**：6ee166f
- **issue**：無

## 0.13.3 — 2026-10-26

- **改了什麼**：辦公室核准保留、預設關閉
  - 審核端開關 `/office approve on｜off`（存 `$.store`，重開記得；預設 off）；狀態檔多一欄 `approve`（開著面板且核准開啟才為 true）。請求端只在有人 `office && approve` 時送單，否則 PermissionRequest 直接 `next(e)`
  - 關著時面板不顯示「審」與 Allow／Deny；開著時面板頂端常駐「核准已開啟（/office approve off 關閉）」
  - 排隊走去櫃台改看 `mode === 'waiting'`（依 since 排序），不再靠核准單 —— 核准關著也照常排隊
  - Allow 按鈕冷卻中「Allow（等一秒）」、可按「Allow（可以按）」同寬，Deny 不再左移（oftest 回報）
  - README 指令表與「點人核准」節更新；`/office` 說明加 `approve on|off`
- **為什麼**：jacky 2026-10-26 最終裁示 B（保留辦公室核准、預設關閉），細節是主管 office 轉達
- **commit**：c1ec1ca
- **issue**：無

## 0.13.2 — 2026-10-26

- **改了什麼**：點人核准的等待放進 hook 的 10 秒預算內
  - 等待上限改成 `next.budget.remainingMs − 1500 ms`（`approvalWindow`；剩不到 2 秒就不送單，沒有計時時上限 120 秒），單與狀態檔都帶 `deadline`（絕對時間），到期自己清成墓碑、回 `next(e)`
  - 聽 `next.signal`：中止時睡眠立刻醒、清單、結束迴圈
  - 面板：核准區移到最上方，展開時顯示「剩 N 秒」、每秒重畫；過了 deadline 就收起、不給按（到點自動重畫，不等下一輪 refresh）；`decide()` 寫決定前再檢查 deadline；`parseApproval` 以 deadline 判斷過期（沒有 deadline 的舊單當不存在）
  - `/office who` 第一行：「🟡🟡 等你核准…：<名牌>（工具，剩 N 秒）」
- **為什麼**：oftest 2026-10-26 實測 `classic.PermissionRequest` 的 hook 預算固定 10 秒（`HookBudget.ms`），超過就改由終端機問但 hook 還在背景跑 → 單一直顯示 waiting，使用者按 Allow 寫得出決定卻不會被採用（以為放行了其實沒有）。修法是主管 office 裁示
- **commit**：9fe6804
- **issue**：無

## 0.13.1 — 2026-10-26

- **改了什麼**：核准決定綁指令內容
  - 決定檔多帶 `textHash`（面板展開時看到的全文的 SHA-256）；等的那方用自己手上的指令算 hash，四項（session、toolUseId、nonce、textHash）全對才採用，不符丟棄＋log
  - 面板按下時重讀單，全文跟展開時不同就不送；單上的 text 變了也重新展開
  - README 新增「點人核准」節，寫明限制：決定檔是本機共用檔，防誤按與配錯，不防本機惡意程式；同時更新桌數門檻與分區規則的舊說明
- **為什麼**：主管 office 2026-10-26 審 dbc5c81：approvals 檔任何本機程式都能改，同一張單（toolUseId＋nonce 不變）的 text 被換成無害字樣時，使用者看到的跟實際放行的會不同
- **commit**：77933aa
- **issue**：無

## 0.13.0 — 2026-10-26

- **改了什麼**：控制塔第 1 期「點人核准」—— 開著辦公室面板的視窗可以替別的 session 按 Allow／Deny
  - 請求端：`tool.check` 判 ask 時記下 toolUseId；`classic.PermissionRequest`（沒有 tool_use_id）用 2 秒內 tool＋input 完全相同、剛好一筆的 ask 配對，配不上就不接手。auto、bypass 類模式、subagent、host 代答、沒有人開辦公室 → 直接交回終端機
  - 送單 `~/.claude/pixel-office/approvals/<session>.json`（含隨機 nonce），每 300 ms 讀 `decisions/<session>.json`；session＋toolUseId＋nonce 全對才採用，不符丟棄並記一行 log；壞檔、逾時 120 秒、終端機先按（PostToolUse／PostToolUseFailure／PermissionDenied／tool.call 結束）→ 不回答。只回 allow／deny，從不送 updatedPermissions
  - 處理完兩個檔都覆寫成墓碑 `{"state":"done"}`（`$.fs` 不能刪檔）；開機先清自己的殘檔；逾時的一律當不存在
  - 面板：「🟡 等你核准：審 <名牌>」按鈕 → 展開全文＋Allow／Deny／收起。Allow 展開後 1 秒才按得下去，單被換成新的一筆就重新展開、冷卻重算；全文超過 1500 字或 20 行只給 Deny 與「回終端機按」；Allow／Deny 不給 hotkey。決定檔只有面板按鈕會寫，沒有任何模型工具能寫
  - 畫面：等核准的人拿著紙走到櫃台排隊（窄面板排大門口），結案後走回座位；名單標「辦公室面板可審」
  - 分區：最左一欄只在有人分不到區時才保留（主管 office 裁示），60～80 欄兩位主管各帶 peer 時有兩區
- **為什麼**：控制塔設計稿第 1 期；安全底線 8 條與冷卻、2 秒、不給 hotkey 是主管 office 2026-10-26 裁示
- **commit**：dbc5c81
- **issue**：無

## 0.12.1 — 2026-10-26

- **改了什麼**：多主管畫面在實機寬度（50～80 欄）看得到
  - 小主管桌 10→8 寬、間距 12→9，往左排到主管室牆邊（盆栽在最後一張桌壓到時讓位）：≥60 欄就有 2 張、≥80 欄 3 張（原本 84／112）
  - peer 分區不再依賴有沒有桌子：坐不下的主管排在有桌的後面，他的 peer 照樣有一區與 TEAM 牌（分區數仍受欄數限制：最左一欄留給沒有 team 的人）
  - 櫃台貼下牆、矮一格（4 列）：走底部走廊去影印機／檔案櫃／郵筒的人不再壓到櫃台
- **為什麼**：oftest B 期驗收（實機面板 50～80 欄看不到第 2 張桌；跑腿的人壓到櫃台上緣），修法是主管 office 2026-10-26 裁示
- **commit**：e8c47be
- **issue**：無

## 0.12.0 — 2026-10-26

- **改了什麼**：控制塔第 0 期畫面 —— 多主管、各主管 peer 區、櫃台
  - 主管室：一位主管照舊坐 L 型大桌；兩位以上換 10 寬小桌，依寬度最多 3 張（第 0 張站位與大桌相同，人數變了不起身）；坐不下的不畫，最後一張桌名牌加 `+N`（不再被排去員工座位）
  - peer 區：`teamZones` 每位有 peer 在線的主管一欄（最右起），地毯金／藍／綠、各掛「TEAM <名牌>」，最左一欄留給沒有 team 的人；一位主管時行為不變
  - 櫃台：大門右邊、下方外牆標 `YOU`，`counterSpot()` 給第 1 期排隊用；窄面板放不下不畫
  - 設計稿 `docs/designs/control-tower.md` 進 repo，第 0 期標已實作
- **為什麼**：控制塔設計稿第 0 期（jacky 2026-10-26 加入多主管；核准一律走到使用者的櫃台）
- **commit**：d1f4ce3
- **issue**：無

## 0.11.1 — 2026-10-26

- **改了什麼**：名單「等輸入／剛完成」也附「上次出錯 N 分前」；沒名稱者的位址改用 code 格式 `to=uds:…`，系統提示 (3) 提醒照抄（兩個反斜線）；`plugins/*/tsconfig.json`（引擎載入 inline mod 時產生）加進 .gitignore
- **為什麼**：oftest A 期驗收（`.team/reports/A-test.md`）：idle／done 提早 return，出錯後停下來等人時看不到錯誤；模型抄位址掉一個反斜線 → ENOINBOX no-key
- **commit**：待補
- **issue**：無

## 0.11.0 — 2026-10-26

- **改了什麼**：控制塔 A 期 —— 名單（`office_roster`、`/office who`）資訊細分
  - 「目前」欄：「🟡 等核准 N 秒」與「等輸入（N 分）」分開（狀態檔新增 `since`）；出錯時存錯誤第一行（最多 80 字，`lastError`），名單顯示，之後 10 分鐘內標「上次出錯 N 分前」
  - 職稱自動帶：沒職稱時，使用者自己打的指令（composer／bridge，不含 slash 指令與 peer 訊息）以 classic hook 的 `session_title`（有的話）或指令前 16 字帶入，名單標「(自動)」；自動帶的放超過 30 分鐘再來新指令才換。手動設的永遠不蓋，但超過 30 分鐘沒更新又來新指令時標「（N 分前設）」並在「目前」欄附最新指令
  - 回信位址：每個 session 發布自己的 `uds:<CLAUDE_CODE_MESSAGING_SOCKET>`（`addr`）；沒有 ListAgents 名稱時名單顯示「SendMessage 用 to=uds:…」；寄到位址也畫得出紙飛機
  - 系統提示 (2) 加一句「名單顯示你的職稱過期時，請更新 title」
- **為什麼**：控制塔設計稿（`plugins/pixel-office/docs/designs/control-tower.md`）A 期；手動 title 不蓋、改為過期標示是主管 office 2026-10-26 裁示
- **commit**：待補
- **issue**：無

## 未發版（0.10.5 之後，併入 0.11.0）

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
