---
description: 教練：看這個 vault 的狀態，只講下一步該做的一件事；也答「為什麼這樣設計」「我這樣寫對嗎」。
---

Read the `wiki-coach` skill and follow it exactly.

`$ARGUMENTS` 是 `on`／`off`／`auto` 之一時，不走教練流程，直接跑
`python "${CLAUDE_PLUGIN_ROOT}/scripts/coach.py" --set $ARGUMENTS` 並回報結果。

使用者的問題（可空）：$ARGUMENTS
