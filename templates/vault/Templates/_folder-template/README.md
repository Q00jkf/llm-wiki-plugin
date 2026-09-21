# _folder-template —— 新資料夾骨架

**用法二選一**

| 方式 | 做法 |
|---|---|
| 指令（建議） | `/wiki-new <名稱>` → 複製本夾到 `raw/<名稱>/`，並建 topic 頁、更新 index／log |
| 手動 | 複製本夾到 `raw/<名稱>/`，把 `_README.md` 裡的 `{{folder}}`／`{{date}}`／`{{count}}`／`{{tree}}` 換成實值 |

**內容**

```
_README.md   ← 執行節點（進度儀表板），佔位符由 new_folder.py 代換
sessions/    ← AI 對話紀錄（套 Templates/AI對話紀錄模板.md）
docs/        ← 文件正本
data/        ← 量測／匯出資料
```

- 本 `README.md` 只說明模板，**不會被複製**到新資料夾。
- 佔位符用 `{{folder}}`／`{{date}}`，不用 `{{name}}`／`{{today}}` —— 後者在 `/wiki-init` 時就被代換掉了。
- 想改新資料夾長什麼樣：改**這個夾**（vault 內的），`new_folder.py` 優先讀 vault 的版本。
