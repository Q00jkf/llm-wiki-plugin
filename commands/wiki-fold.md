---
description: 把 wiki/log.md 最舊的 2^k 條摺疊成一頁 extractive 摘要（wiki/folds/）。預設 dry-run 只印不寫。
---

Read the `wiki-fold` skill and follow it exactly.

參數：`$ARGUMENTS`（例：`dry-run k=3`／`commit k=3 offset=8`／`commit k=3 archive`；未指定＝dry-run k=3 offset=0）

🔴 不要 `Read wiki/log.md` —— 切片全部走 `wiki_fold_parse.py`。條目不足 2^k 就停，不摺部分批次。
