---
name: wiki-adopt
description: "既有 vault 接上 plugin：找出 skill／command 撞名、客製搬到個人層、刪掉 vault 自帶的舊版。Triggers: wiki-adopt, 撞名, 我本來就有 wiki, 升級系統, 遷移到 plugin, 兩份同名。"
---

# wiki-adopt：既有 vault 接上 plugin

**原則：系統歸 plugin，客製歸 CLAUDE.md。分開了才能升級。**

vault 自帶的 skill 是凍結的；plugin 版才會拿到更新。所以目標是**刪掉 vault 版**——
但客製化不能跟著陪葬。

---

## Step 0　先看清楚有幾份

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/adopt.py" --sources
```

同一個名稱常同時存在於**使用者層**（`~/.claude/skills/`，常是 symlink 指向別的 vault）
與**專案層**。先知道有幾份、各自多大、symlink 指到哪。

> ✅ **實測（2026-09-21）：vault 根目錄 `skills/` 不會被載入。** 對照法：某 vault 的 `skills/` 有 9 個
> 只存在於該處、沒被 symlink 進 `~/.claude/skills/` 的 skill（pm-ingest、docx-to-md、manager-briefing…），
> cwd 在該 vault 時 session 的 skill 清單**一個都沒出現**；反之 `~/.claude/skills/` 底下每個有 `SKILL.md` 的都出現。
> → 實際載入來源只有三個：`~/.claude/skills/`（使用者層）、`{專案}/.claude/skills/`（專案層）、plugin。
> vault 根目錄的 `skills/` 只有**被 symlink 指到**時才活著。

> 🔴 **所以「刪 vault 版」有一個隱藏風險**：`~/.claude/skills/wiki-ingest` 可能是 symlink → 指向**別的 vault** 的
> `skills/wiki-ingest/`。`--sources` 會印出 symlink 指向誰 —— 刪之前先看，**刪掉被指向的那份＝弄斷使用者層的入口**。
> 正確順序：先 `rm` 使用者層的 symlink（或改指 plugin 不需要，plugin 自帶命名空間），再刪 vault 版。

> ℹ️ plugin 的 skill 帶命名空間（`llm-wiki:xxx`），**不參與同名爭奪** ——
> 裝 plugin 不會遮蔽既有的東西，也不會被遮蔽。

---

## Step 1　vault 版 vs plugin 版

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/adopt.py"
```

輸出每個同名項的差異行數與「需搶救」行數。

- **完全相同** → 刪 vault 版零風險
- **有差異** → 先做下面的重疊率檢查，再決定進 Step 2 還是停
- **無同名項** → 這個 vault 直接可用，不必遷移

> 這一步回答的是「**要不要改用 plugin 版**」，不是「壞掉了要修」。

### 🔴 先確認這是「舊版」還是「另一套實作」

本流程的前提是 vault 版與 plugin 版**同源**（vault 那份是凍結的舊版）。
同名但不同源時，「搬走客製再刪」會直接刪掉 plugin 根本沒有的功能。

比章節標題的重疊率：

```bash
diff <(grep -E "^#{1,3} " <plugin>/skills/<名稱>/SKILL.md) \
     <(grep -E "^#{1,3} " <vault>/skills/<名稱>/SKILL.md)
```

**重疊率低（多數章節只有一邊有）→ 停，不要進 Step 2。**
回報給使用者：這是兩套實作，遷移＝功能取捨，不是版本升級。讓他決定要遷移、要回饋、還是維持原狀。

> 實測 `LLM-wiki-Template-share`（2026-09-21 驗收 #22）：`wiki-ingest` 差 558 行、章節重疊 0，
> vault 版獨有 URL／Image ingestion、Git Sync 防護、Address Assignment，plugin 一項都沒有。
> 差異行數本身不足以判斷 —— 558 行可能是「加了註解」，也可能是「另一套系統」。

---

## Step 2　🔴 先搶救不能弄丟的東西

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/adopt.py" --rescue
```

撈出裁示／踩雷／教訓類句子（帶 📅 的是有日期的，優先處理）。

**這類句子通常只存在於那份 skill 裡** —— wiki 沒有、commit message 沒有、沒有別的家。
刪 skill 之前必須先決定去處：

| 判斷 | 去處 |
|------|------|
| 只對這個 vault 成立 | `wiki/ops/rulings.md`，Why／實例／代價寫全 |
| 大家都該知道 | 提議合併回 plugin 對應 skill（見 Step 4）|
| 已經過時 | 確認後才丟，並在 `wiki/log.md` 留一筆說明為什麼丟 |

> ⚠️ `--rescue` 是關鍵字比對，**會漏**。Step 3 的人眼 diff 不可跳過。

---

## Step 3　逐項看差異，分類

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/adopt.py" --diff wiki-ingest
```

每一處差異問一個問題：**這是「系統怎麼運作」還是「我怎麼工作」？**

```
系統怎麼運作（流程、格式、判斷樹）
├─ plugin 版比較好 → 直接採用 plugin 版，丟棄 vault 版
└─ vault 版比較好 → 🔵 這是通用改進，走 Step 4 回饋

我怎麼工作（術語、資料夾分類、查詢路由、本 vault 的例外）
└─ 搬到 vault 的 CLAUDE.md 或 wiki/ops/{ingest,query,naming,collab}.md
```

**判準：換一個人／換一個 vault 還成立嗎？** 成立＝系統層，不成立＝個人層。

---

## Step 4　通用改進回饋給 plugin

vault 版有而 plugin 沒有、且對所有人都成立的東西，**不要只搬到個人層** ——
那等於讓其他人繼續缺這個功能。

跟使用者確認後，直接改 plugin 的對應 skill，並在 commit message 寫明來源 vault。

---

## Step 5　刪除與驗證

確認 Step 2–4 都處理完，才刪：

```bash
rm -rf <vault>/skills/<撞名的>       # 逐個刪，不要一次全刪
rm <vault>/commands/<撞名的>.md
```

驗證：

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/adopt.py"      # 應回報「沒有撞名」
```

然後跑 `/wiki` 確認系統仍正常回應。

commit：

```bash
git -c user.name="{session 名}" commit -m "chore: 改用 plugin 版 {名稱}，客製移至 {去處}"
```

**commit message 要寫客製搬到哪裡** —— 三個月後有人問「這條規則哪去了」，這是最快的線索。

---

## 🔴 不要做的事

| 不要 | 為什麼 |
|------|--------|
| 一次刪光所有撞名項 | 出問題時不知道是哪一個造成的 |
| 靠 `--rescue` 的結果就刪 | 它是關鍵字比對，會漏 |
| 把客製化改成 fork 一份 plugin skill | 那就是漂移的起點，正是本流程要消滅的東西 |
| 為了避免撞名而改 plugin 的 skill 名 | 撞名是暫時的，改名會讓這個 vault 跟所有人不一樣 |

---

## 進度回報

撞名項多時（>3），每處理完一項回報一次：

```
已處理 2/3：wiki-ingest
  搶救 4 行 → wiki/ops/ingest.md
  回饋 1 項 → plugin 的 hash 批次腳本（vault 版較好）
  已刪 skills/wiki-ingest/
下一項：wiki-query（差 150 行，1 行待搶救）
```
