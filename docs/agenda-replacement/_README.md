---
maintenance: transactional
updated: 2026-10-17
---

# agenda 替換包（給 llm-wiki plugin）

用這包整組換掉 llm-wiki plugin 的 agenda 部分：把日程、排程引擎、Obsidian 甘特圖外掛換成互宇 vault 現行版本，並改成任何 vault 都能用的通用版。
來源是互宇 vault（LLM-Wiki-AEGIVERSE，下文「本 vault」皆指它）的 `scripts/agenda.py`、`agenda_cpm.py` 與 `.obsidian/plugins/agenda-gantt/`（該 repo `3dec3436`，2026-10-17）。

> **給 plugin 維護者**：本包只放在 `docs/agenda-replacement/`，**plugin 現行檔案都沒動**（使用者 2026-10-17：plugin 正在更新，交由維護者整組套用）。套用＝把本資料夾內各檔照下表複製到 repo 根目錄對應路徑（下表「包內」路徑皆相對於本資料夾）；套完可刪掉本資料夾。

---

## ① 檔案對照（包內路徑＝plugin repo 路徑，直接蓋）

| 包內 | plugin repo | 動作 |
|---|---|---|
| `scripts/agenda.py` | `scripts/agenda.py` | 覆蓋（366 → 1087 行） |
| `scripts/agenda_cpm.py` | `scripts/agenda_cpm.py` | 新增（排程引擎） |
| `scripts/test_agenda.py` | `scripts/test_agenda.py` | 新增（95 案） |
| `skills/wiki-agenda/SKILL.md` | 同 | 覆蓋 |
| `commands/wiki-agenda.md` | 同 | 覆蓋（只改 description） |
| `templates/vault/wiki/agenda.md` | 同 | 覆蓋（表頭補新格式） |
| `templates/vault/.obsidian/plugins/agenda-gantt/` | 同 | 新增（Obsidian 外掛 0.4.0） |
| `templates/vault/.obsidian/community-plugins.json` | 同 | 新增（預設啟用 agenda-gantt） |

另外要手動加一行到 `templates/vault/.skeleton-policy`（每個 vault 的外掛清單各自不同，不比內容）：

```
.obsidian/community-plugins.json   # 每個 vault 自己的外掛清單
```

`hooks/hooks.json` 不用改：開場一樣是不帶參數跑 `agenda.py`。

---

## ② 相容性（與 plugin 現行 agenda.py 比）

| 項目 | 結果 |
|---|---|
| 開場 hook：`CLAUDE_PROJECT_DIR` 或目前目錄找 vault；非 vault、或沒有 agenda.md 時安靜結束 | 保留 |
| `add`／`done`／`--check`／`--tidy`／`--ics`／`--notify`／`--days`／`--tag` | 保留 |
| `_guard_status`：只有未過濾的開場窗口才留痕 | 保留 |
| 依賴 | `_lib.vaultpaths` 的 `find_vault_root`、`load_manifest`（plugin 現有） |
| 新指令 | `undone`、`move`、`dur`、`link`、`unlink`、`plan`、`--fmt`、`--json`、`--file`、`--source` |
| 行為改變 | `add` 改成整檔排版（依第一個 tag 分段），不再只 append；`done` 自動補 `完成:今天`；每次寫入跑排程引擎（前項延誤會順延後項）；開場窗口多一段「期限會延誤」 |
| 新的資料檔 | 變更紀錄 `wiki/agenda-changes.md`（有寫入才建；路徑可設定） |

本 vault 現行的 agenda 格式全部向下相容：舊格式的行照常解析，專案欄位都是選填。

設定鍵（`raw/.manifest.json` 的 `config.agenda`，都選填）：`changes`、`calendar_dir`、`hard_types`、`project_dirs`、`first_order`、`due_cmd`、`due_label`，意思見 `SKILL.md` §設定。

---

## ③ 驗證（2026-10-17，本機）

| 驗證 | 結果 |
|---|---|
| `python scripts/test_agenda.py`：腳本放進複製 plugin `_lib`、`_guard_status.py` 的暫存目錄跑 | 95/95 通過 |
| 本 vault 真日程（24 事件）：包內版本照本 vault 設定，和現行版本比 `--json`／`--check`／`plan` | 三者完全一致（只差提示文字 `python scripts/agenda.py` → `agenda.py`） |
| `due_cmd` 併入開場窗口、非 vault 安靜、沒有 agenda.md 安靜、`add` 自動建骨架、`--ics` 有工期畫成跨日、`--notify` | 測試案涵蓋，通過 |
| Obsidian 外掛找 agenda.py：設定值／vault 的 `scripts/agenda.py`／installed_plugins.json／錯路徑報錯 | node 模擬四種情況都照預期 |
| 外掛在真的 Obsidian 裡從 plugin 安裝目錄跑 | **未驗**（plugin 還沒換上新版） |
| 保密掃描（型號、客戶名、公司名、人名、本機路徑） | 包內 0 筆 |

---

## ④ 已知限制與注意

- **外掛找 agenda.py**：順序是設定值 → vault 的 `scripts/agenda.py` → `~/.claude/plugins/installed_plugins.json` 裡 llm-wiki 的 `installPath`。plugin 以 dev 模式載入時，`installPath` 可能還指著舊版 cache（2026-10-17 實測本機指向 1.7.1，實際載入的是 1.8.0 dev），這時要在外掛設定填「agenda.py 路徑」。
- **既有 vault 不會自動拿到外掛**：`init_vault` 只複製樣板給新 vault。舊 vault 要手動複製 `.obsidian/plugins/agenda-gantt/`，並把 `agenda-gantt` 加進 `community-plugins.json`；要不要讓 `adopt` 代做，由 plugin 維護者決定。
- 新 vault 第一次開 Obsidian，可能要先到「設定 → 第三方外掛」關掉受限模式，外掛才會載入（推測，未驗）。
- **國定假日**：包裡不附日曆 CSV。台灣可下載行政院人事行政總處「政府行政機關辦公日曆表」（data.gov.tw 資料集 14718），放到 `calendar_dir`；沒設就只扣週末。
- **沒有包進來**：ProjectLibre 雙向同步（`agenda-gantt.py`，只能在 Windows＋ProjectLibre 用），仍留在本 vault。
- `templates/vault/wiki/meta/agenda-system.md` 沒有更新，新格式的說明目前寫在 `SKILL.md` 和 agenda.md 表頭。

---

## ⑤ 本 vault 之後若改用 plugin 版

在本 vault 的 `raw/.manifest.json` 加這段，輸出就會和現行版本一致（③ 的對照用的就是這組設定，`due_cmd` 另外驗過）：

```json
"config": { "agenda": {
  "changes": "raw/manager/schedule/changes.md",
  "calendar_dir": "raw/manager/schedule/ref",
  "project_dirs": ["wiki/products"],
  "first_order": ["GS-1A-AP", "GS-1V-UE", "QMS"],
  "due_cmd": ["python", "scripts/company-docs.py", "--due"],
  "due_label": "company-docs"
} }
```

`scripts/agenda-gantt.py`（ProjectLibre）會 import 同目錄的 `agenda`，所以本 vault 的 `scripts/agenda.py` 要留著，或改成轉呼叫 plugin 版的空殼。
