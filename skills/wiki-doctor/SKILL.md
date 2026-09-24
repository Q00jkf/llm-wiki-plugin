---
name: wiki-doctor
description: "知識庫老化健檢。量測 vault 成熟度、抓出 log 過大／單頁過大／hot 沒輪替／健檢過期／來源檔消失／repo 路徑失效／守門失聯，並說明每一項該怎麼處理；也涵蓋 tidy_check／stale_check／log_index 三支守門腳本的用法。Triggers on: wiki-doctor, 健檢, 知識庫體檢, 系統老化, vault 狀態, 這個 wiki 還健康嗎, 該整理了嗎。"
---

# wiki-doctor：老化健檢

**這個 skill 存在的理由：沒有東西驗證規則還在跑，規則就會靜靜死掉而沒有人發現。**

---

## 跑健檢

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/vault_state.py"          # 人看的報告
python "${CLAUDE_PLUGIN_ROOT}/scripts/vault_state.py" --json    # 完整訊號
```

---

## 老化訊號與處理方式

| 訊號 | 為什麼危險 | 怎麼處理 |
|------|-----------|---------|
| **log 過大**（>200KB） | 整份讀就是數十 k tokens；設計上只增不減 | 改用 `Grep` 帶關鍵字；在 vault 內建摺疊／歸檔機制（plugin 不內建） |
| **單頁過大**（>100KB） | 同上，且代表該頁混了太多主題 | 拆頁，依主題或產品分子資料夾 |
| **CLAUDE.md 過大**（>150 行） | 每 session 都載入，規則越多越貴，且會出現互相矛盾的舊規則 | 按需規則拆到 `wiki/ops/{{主題}}.md`，CLAUDE.md 只留「我要做…→讀哪份」索引表 |
| **hot 沒輪替**（>150 行） | hot.md 是每 session 必讀，長了就每次多花 token | 修剪：常駐規則 + 最近 3 次操作 + 待確認，其餘移進 log |
| **健檢過期 / 從未健檢** | 孤立頁與死連結會無聲累積 | 跑本 skill 的完整報告並存檔（見「何時跑」收尾列）|
| **卡有絕對路徑** | `current_file` 寫 `C:/Users/…` 換機器就開不到正本（0.4.15 只修了 manifest，卡沒修） | `repo.py fixpaths --dry-run` → 去掉 `--dry-run`；不在已註冊 repo 底下的先 `add` |
| **卡無 scope** | 沒有 `scope:` 的卡不知道屬於誰，會被撈進任何問題 → 討論 A 撈到 B | `python "${CLAUDE_PLUGIN_ROOT}/scripts/repo.py" scope --dry-run` 看推導結果，再去掉 `--dry-run`；推不出的手填 |
| **來源檔消失** | catalog 卡指向不存在的檔＝假知識 | `/wiki-repo scan` 確認，修卡或標失效 |
| **repo 路徑失效** | 絕對路徑換機器就死 | 看 owner 欄找擁有者要 remote；不要直接刪註冊 |
| **守門失聯** | 某支守門腳本太久沒成功執行＝它可能早就掛了 | 見下節；先 `compileall` 再手動跑那支 |

---

## 三支守門腳本（老化訊號之外的日常對帳）

| 腳本 | 抓什麼 | 何時跑 |
|------|--------|--------|
| `tidy_check.py [--quiet] [path]` | frontmatter 有 `maintenance:` 宣告的檔（hot.md、`_README.md`、coordination）：已結案未刪列、斷掉的編號、數量與檔案／`_manifest.json` 不符、引用的檔名不存在、超出 token 上限 | session 開場 `--quiet`；收尾看完整輸出 |
| `stale_check.py [raw/子路徑] [--ext .txt]` | raw/ 哪些檔的 md5 不在 manifest（新檔或改過＝wiki 可能過期）。只比 hash 不比路徑；預設只掃 .md/.pdf | 使用者問某產品／資料現況前；ingest 前 |
| `rules_check.py [--quiet] [--only F1,F3]` | **規則層**漂移：CLAUDE.md 資料夾用途表 vs `raw/` 實際夾、停用頁還被誰引用、引用的腳本不存在（規則層＋vault 自己的 `skills/*.md`，抓「撞名遷移進來的 skill 沒把腳本一起搬」）、規則層逐字重複、同檔重複標題、vault 腳本沒登記。wiki 層的 doctor 不守這些 | session 開場 `--quiet`；改完 CLAUDE.md／ops 後跑一次 |
| `log_index.py --check` / `--apply` | log.md 每條標題下的 `<!-- log kind:… scope:… ref:… -->` 標記缺／過期。標記由內容推導、`--apply` 冪等 | append 條目後順手 `--apply`；健檢時 `--check` |

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/tidy_check.py" --quiet
python "${CLAUDE_PLUGIN_ROOT}/scripts/stale_check.py" raw/{子路徑}
python "${CLAUDE_PLUGIN_ROOT}/scripts/log_index.py" --check
python "${CLAUDE_PLUGIN_ROOT}/scripts/rules_check.py"
python -m compileall -q "${CLAUDE_PLUGIN_ROOT}/scripts"      # 升級 plugin 或換 Python 後跑一次
```

三支 exit 一律 0（`stale_check` 路徑不存在才 2），**只列候選、不擋 git**。
`stale_check` 回 PENDING → 提示使用者「raw/… 在上次 ingest 後已改，wiki 可能不是最新，要先 `/wiki-ingest` 嗎？」。
grep log.md 時只撈標記行：`grep -n "<!-- log .*scope:[^ ]*{產品}" wiki/log.md`，回傳量與條目長度脫鉤。

### `wiki/meta/_guard-status/{host}.json` 與「守門失聯」

`tidy_check`／`stale_check` 完整跑過一次就把 `{date, python, host, verdict}` 寫進**這台機器自己的**
`wiki/meta/_guard-status/{host}.json`（只記日期、內容沒變不寫檔；掃子路徑的 tidy_check 不記）。
`vault_state.py` 開場彙整所有機器的檔案，某支超過上限天數沒成功執行就報 **守門失聯**
（tidy-check 7 天、stale-check 30 天、agenda 7 天、rules-check 7 天，見 `_guard_status.EXPECTED_DAYS`）。
**沒跑、跑掛、跑出 CLEAN 三者事後要能分辨** —— 原 vault 曾有守門在 Python 3.11 靜默掛 10 天沒人發現。
看到守門失聯 → 先 `python -m compileall`，再手動跑那支看它還活著沒；不要只把日期改新。

🔴 **一台機器一個檔，判讀分兩層**：多機共用同一個 vault 時，若所有機器共寫同一筆紀錄，
B 機今天跑過就會把「A 機 60 天沒跑」蓋成「今天跑過」——A 機的守門可能早就掛了，沒人發現。
判讀分「全體失聯」（所有機器都逾期，真的沒人在顧）與「單機停跑」（這台逾期、別台在期內，
這台環境可能有問題但不算全滅）。**這台從未跑過某支不算它逾期**——不是每台都該跑每一支。

---

## 🔴 腳本只列候選，刪不刪是判斷

刪任何東西前 **MUST** 先 `Grep wiki/log.md` 確認這條裁示有沒有被記錄過。
**查不到就先補寫進 log.md 再刪。**

最不能丟的是「界定什麼**不是**我方範圍」那類結論 —— 它沒有別的家，刪掉就永遠消失。

---

## 何時跑

| 時機 | 動作 |
|------|------|
| SessionStart | hook 自動跑 `--brief`，有訊號才出聲 |
| 開場看到 🟡 | **提一句讓使用者知道**，收尾時處理，不必當場改 |
| 收尾 | 跑完整報告，處理掉當天新增的訊號；**把報告存成 `wiki/meta/doctor-report-YYYY-MM-DD.md`**（`vault_state.py` 以此檔的日期判斷「上次健檢」，不存就永遠報從未健檢）。frontmatter MUST 標 `maintenance: frozen` —— 報告是凍結紀錄，標 `transactional` 會讓 `tidy_check` 把驗收結果的 ✅ 當成「做完的待辦」要你刪|

---

## 門檻調整

寫在 vault 的 `raw/.manifest.json`：

```json
"config": {
  "big_read_limit_bytes": 100000,
  "max_slice_lines": 2000
}
```

其餘門檻（頁數分級、log 大小、hot 行數、健檢天數）集中在 `vault_state.py` 檔頭常數區。
