---
type: meta
title: 操作日誌
---

# 操作日誌

> 🔴 **只增不減，一律用 append。** 檔案會長到無法整份讀 —— 查詢用 `Grep`，不要 `Read`。

## {{today}} | init | vault 建立

- 由 `llm-wiki` plugin 的 `/wiki-init` 產生
- 骨架：raw/ + wiki/{catalog,topics,questions,projects}
- 系統由 plugin 提供，本 vault 不自帶 skills／commands
