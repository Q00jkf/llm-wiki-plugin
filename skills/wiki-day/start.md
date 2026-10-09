# wiki-start：開始工作

vault 自訂的開工項目在 **`wiki/ops/start.md`**（每個 vault 自己寫，本 skill 不管內容）；不存在就跳過並在回報裡說一句。

🔑 **分工**：SessionStart hook 管系統層（每個 session 自動跑）；本 skill 管這個 vault 的開工習慣（使用者開口才跑）。hook 已經印出的東西不要重跑。

## 步驟

1. 讀 `wiki/hot.md` 最上面一塊今日結論 —— 上次停在哪、卡誰、待使用者。
2. 照 `wiki/ops/start.md` 做 vault 自訂項目。
3. 協作模式：讀 `wiki/meta/coordination.md` 的「目前主管」，`ListAgents` 確認在線 → 在線就 `SendMessage` 報到（我是誰、今天打算做什麼）；不在線就照常工作。
4. 回報使用者，三行以內：上次停在哪、今天日程（取 hook 已印的窗口）、vault 開工項目的結果。
