---
name: wiki-new
description: "開一個新的工作資料夾（專案／產品／客戶／交付夾）並在 wiki 登錄：複製 Templates/_folder-template/ 到 raw/<name>/、寫 _README.md 執行節點、建 topic stub、更新 index／log。也定義 _README.md 的維護規則與取用副本夾（_manifest.json）模式。Triggers on: wiki-new, 開新資料夾, 新專案, 新產品, 建資料夾, new folder, _README 怎麼寫, 執行節點, 取用副本夾, 稽核夾。"
---

# wiki-new：開新資料夾 ＋ 登錄

先讀 `wiki-core`。R3（要跨 session 存活的東西必須落盤）是本 skill 存在的理由：
**建夾不登錄 ＝ 三個月後沒人知道它為什麼在那裡。**

---

## 何時用

| 情況 | 用 |
|---|---|
| 新專案／產品／客戶／主題要開一個 `raw/` 子夾 | `/wiki-new <name>` |
| 為一次稽核／交付集中複製多份正本 | `/wiki-new <name> --under raw/<專案>/取用` ＋ 手寫 `_manifest.json`（見下） |
| 只是放幾個檔，沒人會查進度 | **不用**。直接放，不建夾不建頁 |

---

## 🔴 `_README.md` ＝ 該資料夾的執行節點

一件工作做完了沒、卡在哪、下一步是什麼 —— 全部匯集在該資料夾的 `_README.md`。
它不是文件之一，是**那個資料夾的儀表板**。使用者只看它確認進度。

| 規則 | 理由 |
|---|---|
| 只寫**當前狀態**（覆蓋式）；工作歷程寫 `wiki/log.md` | 歷史只增不減，混進儀表板會讓它每天長 |
| ③「現在卡在哪」**只列未解決的**；解決即整列刪，不留 ✅ | 已結案項會在下個 session 被當未完成再報一次 |
| 刪 ③ 的列之前 MUST `grep wiki/log.md`；查不到先補 log 再刪 | 刪了又沒 log ＝ 這件事從沒發生過 |
| 靜態段（①②⑤）寫完不再動；日常只碰 ③④ | 三種生命週期混在一起 → 每次都得重讀整份 |
| 表格不對齊、`\|` 之間不補空白 | 對齊空白佔單檔 50–60% 字元，渲染結果相同 |
| 有主管 session 時，`_README.md` 由主管維護；peer 回報**欄位級**變更（哪一列／哪一欄／改成什麼），不直接編輯 | 主管對使用者的報告負責，代寫＝把報告品質外包 |
| 純技術頁（topics／catalog）不算執行節點 | 判準：**使用者會不會自己打開它看進度** |

模板：`Templates/_README模板.md`（六段＋四條格式規則）。`/wiki-new` 產出的 `_README.md` 是它的空白實例。

---

## 取用副本夾（為一次稽核／交付集中複製正本時）

```
raw/<專案>/取用/<標的>_<YYYYMMDD>/
  _README.md        ← 當前狀態
  _manifest.json    ← 每份副本的正本路徑
  <副本們>
```

`_manifest.json` 兩種寫法擇一：

```json
[["群組", "副本檔名", "raw/.../正本路徑"], ...]
{"files": [{"copy": "副本檔名", "source": "raw/.../正本路徑", "group": "可選"}]}
```

| 規則 | 理由 |
|---|---|
| 🔴 **改正本 → 整批重新複製**，絕不單獨改副本 | 副本改了正本沒改 ＝ 兩個真相 |
| 每份副本 MUST 登記正本路徑 | 沒登記就查不出它過期了沒 |
| 交付前跑 `python "${CLAUDE_PLUGIN_ROOT}/scripts/audit_copy_check.py" <副本夾>` | md5 比對：過期／消失／未登記。消失 → exit 1 |
| `## 目錄內容（N 份）` 有 manifest 時比 manifest 條目數 | `tidy_check` T3 的規則 |

---

## 五步流程

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/new_folder.py" <name> [--under raw] [--sub a,b,c] --dry-run
python "${CLAUDE_PLUGIN_ROOT}/scripts/new_folder.py" <name> [--under raw] [--sub a,b,c]
```

| # | 做什麼 | 誰做 |
|---|---|---|
| 1 | 複製 `Templates/_folder-template/` → `<under>/<name>/`（vault 有自訂版就用 vault 的） | 腳本 |
| 2 | 寫 `_README.md`（代換名稱／日期／份數／目錄樹） | 腳本 |
| 3 | 建 `wiki/topics/<name>.md` stub（`status: initializing`） | 腳本 |
| 4 | `wiki/index.md` `## Topics` 加一列；`wiki/log.md` 最上方加 `## 日期 \| new \| <name>` | 腳本 |
| 5 | 🔴 **CLAUDE.md「資料夾用途」表加一列**（腳本只提醒，不動 CLAUDE.md）。`/wiki-new` 是使用者下的指令，加這一列＝執行該指令的一部分，**直接加、回報加了什麼**；不算「改規則層」（規則層＝鐵律／流程，見 `wiki-collab` 01） | 你 |

先 `--dry-run` 給使用者看，確認後才實際執行。目標已存在會拒絕，不覆寫。

> 為什麼第 5 步不能省：兩個成熟 vault 都因為建夾流程漏了這一步，「我們有哪些專案」這類盤點題長期少報 —— 根因是流程缺步驟，不是誰忘記。

完成後告知使用者：資料夾位置、下一步（素材放進去 → `/wiki-ingest <under>/<name>/` → 填 `_README.md` ④ 進度表）。
