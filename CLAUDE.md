# llm-wiki plugin — 原始碼地圖

這個 repo 是 `llm-wiki` plugin 的**唯一真相來源**。使用說明在 `README.md`，設計理念在 `docs/design.md`；
這份只回答一件事：**要改的東西在哪個檔**。（2026-10-08 建，因為找一個型別定義繞了 5 次 grep。）

🔴 **不要改 cache**：`~/.claude/plugins/cache/llm-wiki/llm-wiki/<版本>/` 是安裝後的產物，改了會被下次 `/plugin update` 蓋掉。一律改這個 repo。

🔴 **vault 專屬的差異不准改 plugin**（使用者 2026-10-02 裁示）：某個 vault 想要不一樣的行為 → 寫進該 vault 的 `wiki/ops/*`。
只有「所有 vault 都成立」的行為才動這裡。

---

## 要改什麼 → 開哪個檔

| 我要改… | 檔 |
|---|---|
| 某個 skill 的行為（ingest 怎麼跑、角色卡怎麼接手…） | `skills/<名>/SKILL.md` —— 一個 skill 一個資料夾，裡面就只有 SKILL.md |
| slash command 的觸發與參數 | `commands/<名>.md`（同名 skill 存在時，command 只負責轉進 skill） |
| 開場自動跑什麼 | `hooks/hooks.json` —— SessionStart 依序呼叫 `scripts/vault_state.py`→`tidy_check.py`→`agenda.py`→`rules_check.py` |
| 腳本邏輯（角色卡、日程、對帳…） | `scripts/<名>.py`，共用函式在 `scripts/_lib/`：`vaultpaths`（路徑）、`filehash`（雜湊）、`logparse`（log 解析）、`derived`（推導值） |
| 新 vault 建出來長什麼樣 | `templates/vault/`（`CLAUDE.md`、`wiki/`、`raw/`、`Templates/`） |
| 版本號、marketplace 條目 | `.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json` |
| **像素辦公室** | `plugins/pixel-office/` —— 獨立 plugin、獨立版本號，見下 |

### plugins/pixel-office/ 內部

| 我要改… | 檔 |
|---|---|
| hook、MCP 工具（`office_profile`／`office_roster`／`office_meeting`）、`/office` 指令、名單輸出 | `hooks/register.tsx` —— **全部邏輯都在這一支**（約 900 行） |
| 像素畫、座位配置、走路路徑、貓 | `hooks/scene.ts` |
| `Coworker` 等型別 | `types/index.d.ts` ← **不在 `hooks/` 裡**；2026-10-08 在這裡繞了 5 次 grep |
| 測試 | `hooks/office.test.tsx` |

---

## 🔴 動 `templates/vault/` 之前先看這段

已建好的 vault 不會自己跟上樣板。`skeleton_check.py` 負責對帳，但它**只看得到樣板檔本身的變化**。

| 你做的事 | 要不要額外處理 |
|---|---|
| 改樣板檔內容 | 不用。hash 變了就偵測得到 |
| 新增樣板檔 | 不用。自動進「缺檔」 |
| 新增的檔**內容本來就該每個 vault 不同**（登記簿、日誌、狀態檔） | 🔴 **要加進 `templates/vault/.skeleton-policy`**，否則每次都報「已客製」變噪音 |
| 刪掉樣板檔 | 不用。會報「plugin 不再提供」，vault 的檔不動 |

### 🔴 skill 要求 vault 做某件事時，要讓樣板看得見

**這是對帳機制唯一的破口。** skill 的規則改了（例如「coordination 狀態欄開頭寫登記日」，
`tidy_check` 的 T9 靠它），但如果那個要求沒有反映在 `templates/vault/` 的對應檔上，
`skeleton_check` 完全偵測不到 —— 舊 vault 永遠不會被提醒，skill 的新行為就默默失效。

所以：**skill 的行為一旦依賴 vault 的某個檔或某種格式，那個格式要同時寫進樣板的對應檔**
（上例：樣板的 `coordination.md` 表頭要帶出登記日欄位）。樣板一改，所有 vault 下次對帳就看得到。

被 `.skeleton-policy` 排除的檔（coordination、log、hot…）連格式變更也偵測不到 ——
那些檔只能靠 skill 在使用當下帶新格式，不能靠升級推送。寫規則時要知道這個邊界。

---

## 清單怎麼查（不寫死，寫死就會過期）

| 想知道 | 指令 |
|---|---|
| 有哪些 skill／command | `ls skills/ commands/` |
| 某支腳本吃什麼參數 | `python scripts/<名>.py --help` |
| 現在裝的是哪一版 | `grep -A5 '"llm-wiki@llm-wiki"' ~/.claude/plugins/installed_plugins.json` |
| 哪個 component 吃多少 token | `claude plugin details llm-wiki`（always-on 進每個 session，on-invoke 觸發才付） |

---

## 改完要做的

1. **跑測試**：`claude plugin test plugins/pixel-office` —— 目前**只有 pixel-office 有測試**，plugin 本體沒有，行為改動要實跑驗證，不要宣告「應該可以」
2. 改了行為就 bump 對應的 `.claude-plugin/plugin.json` 版本號
3. commit 用自己的 session 名當 author：`git -c user.name="<短代號>" commit ...`（只改 `user.name`，不動 email、不 `--global`）
4. 本機生效：`/plugin update`

---

## 踩坑

- **2026-10-08 Python 印中文炸掉**：這個環境 stdout 預設 cp950，腳本印中文會 `UnicodeEncodeError`。
  腳本開頭加 `sys.stdout.reconfigure(encoding='utf-8')`；**`python -I` 會忽略 `PYTHONIOENCODING`**，設環境變數救不了。
- **2026-10-08 掃 cache 會掃到垃圾**：`~/.claude/plugins/cache/` 下有 `temp_git_*` 殘留的暫存 clone，
  用 glob 當成「marketplace/plugin/版本」三層掃時，它的 `.git/logs` 之類會被誤認成版本目錄。掃 cache 一律排除 `temp_git_*`。
- **2026-10-08 cache 舊版本不會自動清**：`claude plugin prune` 只清「不再需要的自動安裝相依」，不清舊版本目錄。
  舊版堆積會讓 `find`／`grep` 的輸出被舊版路徑塞滿而截斷，進而誤讀舊版規則。清理要手動刪目錄。
