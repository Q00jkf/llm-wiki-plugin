<%*
const role = await tp.system.prompt("角色／來源（例：RD、PM、客戶）", "", false);
-%>
---
type: session
tags: [<% role %>, sessions]
date: <% tp.file.creation_date("YYYY-MM-DD") %>
status: done
---

# <% tp.file.title %>

## 背景

## 結論

## 重要決策

## 待確認

<!-- 沒裝 Templater：把 <% %> 手動換成實值即可。存放位置：raw/<專案>/sessions/ -->
