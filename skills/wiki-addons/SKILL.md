---
name: wiki-addons
description: "可選裝模組（Obsidian 外掛＋它用的腳本）：列出、安裝、更新。裝不裝由使用者選；開場與 doctor 只檢查已裝的。Triggers: 模組, 裝外掛, 加裝 Obsidian 功能, 甘特圖, AI 助手, 工具箱, 外掛要更新, modules。"
---

# wiki-addons：可選裝模組

**為什麼有這個：** 自製 Obsidian 外掛原本是一個 vault 複製一份，改一處就要手動同步其他 vault，最後一定對不上。
現在正本只有一份（plugin 的 `addons/`），vault 裡的是「安裝」出來的複本。

## 指令

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/addons.py"                  # 列出模組與本 vault 狀態
python "${CLAUDE_PLUGIN_ROOT}/scripts/addons.py" install <id>...   # 安裝
python "${CLAUDE_PLUGIN_ROOT}/scripts/addons.py" update [<id>...]  # 更新已裝的（不給 id＝全部）
python "${CLAUDE_PLUGIN_ROOT}/scripts/addons.py" dismiss <id>...   # 這個 vault 不裝，不再提醒
python "${CLAUDE_PLUGIN_ROOT}/scripts/addons.py" check             # 已裝要處理的＋還沒決定的新模組
```

裝完請使用者在 Obsidian 按 Ctrl+R 重新載入。

## 狀態

| 狀態 | 意思 | 怎麼處理 |
|---|---|---|
| 未裝（還沒決定） | 新模組，或這個 vault 從沒選過 | 開場報「有新模組可裝」；問使用者，要就 `install`，不要就 `dismiss` |
| 不裝 | 使用者 `dismiss` 過（記在 `.obsidian/llm-wiki-addons.json`，跟著 git） | 不提醒；改變心意直接 `install` |
| plugin 比較舊 | vault 裡的版本是別人用較新 plugin 裝的 | 🔴 不要 `update`／`--force`（會降版）：先更新本機 plugin |
| 最新 | 複本＝正本 | — |
| 需更新 | plugin 出了新版，vault 複本沒人動過 | `update` |
| vault 有改動 | 有人直接改了 vault 裡的複本 | 🔴 **不要直接 `--force`**：先把改動搬回 `addons/<id>/` 正本（所有 vault 都成立的才搬；只屬於這個 vault 的寫進該模組的 local 檔），再 `update --force` |

## 怎麼知道 plugin 是不是最新

不連網。vault 跟著 git 給所有人，安裝紀錄記著版本：只要有一個人用新版 plugin 裝過，
其他人的 plugin 比較舊時，開場就會報「plugin 比較舊」。沒有人先升級的話不會知道 GitHub 有新版。

## 規則

- 模組正本**不放任何特定 vault／公司的內容**（產品名、人名、公司規定）。vault 專屬的行為放 `addon.json` 的 `local` 檔（例：AI 助手的 `local-rules.json`），安裝與更新永遠不碰。
- 改模組 → bump `addons/<id>/addon.json` 與 `obsidian/manifest.json` 的 `version`，CHANGELOG 記一筆。
- `requires` 缺檔只警告不擋：模組照裝，相關功能在 vault 補齊前不出現。
