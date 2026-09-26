#!/usr/bin/env python3
"""看這個 vault 的實際狀態，只講「下一步做哪一件事」。

設計原則（承自 wiki-init）：新人需要的是一個能馬上做的動作，不是指令清單。
判斷全在 Python（可重跑、可對帳）；LLM 只負責措辭與回答「為什麼」（走 wiki-core）。

用法：
    python coach.py            # 只印優先度最高的一項
    python coach.py --all      # 印全部
    python coach.py --json     # 機器讀
    python coach.py --mode     # 目前教練模式（auto／on／off）
    python coach.py --set on   # 長開：每次開場都講下一步；off 長關：開場不講；auto 依成熟度
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib.vaultpaths import find_vault_root, load_manifest, manifest_sources, save_manifest  # noqa: E402
from _lib.logparse import load_entries, log_path  # noqa: E402
import vault_state as vs  # noqa: E402  複用頁數／成熟度／健檢時間，不另寫一份

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# --- 門檻 ---
INGESTABLE = {".md", ".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".epub", ".txt"}
RAW_SKIP_NAMES = {".manifest.json", "_README.md"}
RAW_SKIP_DIRS = {"templates"}          # 比對時轉小寫
BACKLOG_MIN = 10                       # 未 ingest 檔數超過此值 = 積壓
HOT_STALE_DAYS = 7
RULINGS_MIN_LOG = 10                   # log 條目 ≥ 此值仍無裁示 = 沒落盤
INGEST_UNQUERIED_MIN = 5               # ingest ≥ 此值且 query 0 次 = 該問「值不值得建卡」
DAY = 86400

# CLAUDE.md 必填區（依重要度排序；key 是標題子字串）
CLAUDE_SECTIONS = ["資料夾用途", "專屬術語", "我的工作習慣", "查詢路由"]
TEMPLATE_CLAUDE = Path(__file__).resolve().parent.parent / "templates" / "vault" / "CLAUDE.md"

SEV_RANK = {"🔴": 0, "🟡": 1, "🔵": 2}
DATE_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")


# ---------- 工具 ----------
def _strip_comments(text):
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def _sections(text):
    """{標題: [行]}，只切 `## ` 層級。"""
    out, cur = {}, None
    for line in _strip_comments(text).splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
    return out


def _content_lines(lines):
    """去掉空行、bare `-`、空表格列、分隔列後剩下的內容。"""
    keep = []
    for raw in lines:
        s = raw.strip()
        if not s or s in ("-", "*", "---"):
            continue
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(not c or set(c) <= set("-: ") for c in cells):
                continue
        keep.append(s)
    return keep


def _find_section(secs, key):
    for title, lines in secs.items():
        if key in title:
            return title, lines
    return None, None


def _empty_claude_sections(root):
    cm = root / "CLAUDE.md"
    if not cm.is_file():
        return []
    try:
        secs = _sections(cm.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return []
    tpl = {}
    if TEMPLATE_CLAUDE.is_file():
        try:
            tpl = _sections(TEMPLATE_CLAUDE.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    empty = []
    for key in CLAUDE_SECTIONS:
        title, lines = _find_section(secs, key)
        if title is None:
            continue                      # 舊 vault 沒這區 → 不算空
        _, tlines = _find_section(tpl, key)
        tpl_set = set(_content_lines(tlines or []))
        # 表頭列（例：| 縮寫 | 全稱 | 說明 |）也算範本自帶
        if not [l for l in _content_lines(lines) if l not in tpl_set]:
            empty.append(key)
    return empty


def _all_sources(manifest):
    """新式 sources ＋ 舊式頂層 raw/… 或 alias::… key，一律當來源。"""
    return manifest_sources(manifest)


def _raw_files(root):
    raw = root / "raw"
    if not raw.is_dir():
        return []
    out = []
    for p in raw.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in INGESTABLE or p.name in RAW_SKIP_NAMES:
            continue
        parts = p.relative_to(root).parts
        if any(x.startswith(".") or x.lower() in RAW_SKIP_DIRS for x in parts[:-1]):
            continue
        out.append("/".join(parts))
    return out


def _git(root, *args):
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=5)
        return r.returncode == 0 and r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _log_entries(root):
    lp = log_path(root)
    if not lp.is_file():
        return []
    try:
        return load_entries(lp)[1]
    except (OSError, UnicodeDecodeError):
        return []


def _mtime(p):
    try:
        return p.stat().st_mtime
    except OSError:
        return None


def _count_events(agenda):
    try:
        text = agenda.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    body = re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.S)
    return sum(1 for l in _strip_comments(body).splitlines()
               if DATE_RE.search(l) and not l.startswith(("#", ">", "✅")))


def _f(fid, sev, finding, why, action):
    return {"id": fid, "severity": sev, "finding": finding, "why": why, "action": action}


# 老化訊號 → 行動。key 是 vault_state.aging_flags() 的第一個元素（訊號名）。
# 沒列在這裡的訊號一律用 DEFAULT_AGING —— 新增訊號時忘了補這張表，
# 也不會從 coach 消失（只是話講得比較general）。
AGING_ACTION = {
    "守門結果變差": ("🔴", "守門的數字在惡化，代表某件事從某天起開始累積 —— 趁還記得那天做過什麼時處理最便宜",
                 "讀 wiki/meta/maintenance/ledger.tsv 找變化那天，對照 wiki/log.md 看當天做了什麼"),
    "守門失聯": ("🔴", "守門太久沒成功執行 —— 它可能早就掛了，而輸出看起來跟「沒問題」一樣",
               "先 python -m compileall 再手動跑那支；不要只把日期改新"),
    "收尾沒跑": ("🟡", "hot.md 是每 session 第一份讀的檔，落後 log 就會接錯地方",
               "把最近操作與待確認寫進 wiki/hot.md「目前狀態」，舊的移進 log"),
    "來源檔消失": ("🔴", "卡片指向不存在的檔＝假知識，查詢時會回一個開不了的路徑",
                "/wiki-repo scan 確認，然後修卡或標失效"),
    "repo 路徑失效": ("🔴", "換機器就開不到正本",
                   "看 owner 欄找擁有者要 remote；不要直接刪註冊"),
    "卡有絕對路徑": ("🟡", "current_file 寫死 C:/Users/… 換機器就失效",
                  'python "${CLAUDE_PLUGIN_ROOT}/scripts/repo.py" fixpaths --dry-run 看結果，再去掉 --dry-run'),
    "卡無 scope": ("🟡", "沒有 scope 的卡不知道屬於誰，會被撈進任何問題 —— 討論 A 撈到 B",
                 'python "${CLAUDE_PLUGIN_ROOT}/scripts/repo.py" scope --dry-run'),
    "孤兒卡": ("🟡", "卡在、manifest 沒紀錄 → scan 永遠不會報它過期",
             'python "${CLAUDE_PLUGIN_ROOT}/scripts/repo.py" link "{source key}" "{卡片}"'),
    "目錄死連結": ("🟡", "index.md 的 source key 解析不開，多半是 alias 被改名或 remove 過",
                'python "${CLAUDE_PLUGIN_ROOT}/scripts/repo.py" rename <舊> <新>'),
    "目錄漏卡": ("🔵", "卡建了但 index 沒登記，之後沒人找得到它", "把缺的卡補進 wiki/index.md 的 Catalog 表"),
    "從未健檢": ("🔵", "孤立頁與死連結會無聲累積，沒人驗證規則還在跑就會靜靜死掉",
               "/wiki-doctor（結果存 wiki/meta/doctor-report-{日期}.md）"),
    "健檢過期": ("🔵", "健檢是唯一會抓孤立頁／死連結／來源檔消失的機制", "/wiki-doctor"),
    "log 過大": ("🔵", "整份讀就是數十 k tokens，而它設計上只增不減", "/wiki-fold 把最舊的摺成摘要"),
    "hot 沒輪替": ("🔵", "hot.md 每 session 必讀，長了就每次多花 token",
                 "修剪成：常駐規則＋最近 3 次操作＋待確認，其餘移進 log"),
    "CLAUDE.md 過大": ("🔵", "每 session 都載入，規則越多越貴，且會出現互相矛盾的舊規則",
                     "把按需規則拆到 wiki/ops/，CLAUDE.md 只留「我要做…→讀哪份」索引表"),
    "單頁過大": ("🔵", "代表該頁混了太多主題", "依主題或產品拆成子頁"),
}
DEFAULT_AGING = ("🔵", "這是老化訊號，放著會累積", "/wiki-doctor 看這一項該怎麼處理")


def _aging_findings(s):
    """把 vault_state 偵測到的老化訊號轉成行動項。偵測不在這裡。"""
    out = []
    for kind, detail in vs.aging_flags(s):
        sev, why, action = AGING_ACTION.get(kind, DEFAULT_AGING)
        # detail 可能自帶嚴重度 emoji（trend_report 會加，給 vault_state 的表列用）；
        # coach 自己就印 severity，留著會變成「🔴 …：🔴 …」
        detail = re.sub(r"^\s*[🔴🟡🔵🟢]\s*", "", detail)
        out.append(_f(f"aging:{kind}", sev, f"{kind}：{detail}", why, action))
    return out


# ---------- 檢查 ----------
def findings(root):
    """依優先序回傳所有命中的建議。root 為 None 表示不是 vault。"""
    if root is None:
        return None, [_f("vault_absent", "🔴",
                         "這個資料夾還不是 wiki vault（沒有 wiki/ 也沒有 raw/.manifest.json）",
                         "系統的所有指令都靠 wiki/ 與 manifest 定位，沒有骨架什麼都跑不起來",
                         "/wiki-init")]

    s = vs.collect(root)
    tier = vs.tier_of(s)
    manifest = load_manifest(root)
    sources = _all_sources(manifest)
    self_sources = {k for k in sources if "::" not in k}
    raw_files = _raw_files(root)
    uningested = [f for f in raw_files if f not in self_sources]
    entries = _log_entries(root)
    out = []

    # 1 有素材但一筆都沒 ingest
    if raw_files and not self_sources:
        out.append(_f("ingest_zero", "🔴",
                      f"raw/ 有 {len(raw_files)} 份可 ingest 的檔，manifest 卻 0 筆紀錄",
                      "wiki 現在一張指標卡都沒有，/wiki-query 查不到任何東西 —— 系統等於還沒開始",
                      "/wiki-ingest raw/"))

    # 2 CLAUDE.md 還是範本空殼
    empty = _empty_claude_sections(root)
    if empty:
        first = empty[0]
        more = f"（另 {len(empty) - 1} 區也空）" if len(empty) > 1 else ""
        out.append(_f("claude_empty", "🟡",
                      f"CLAUDE.md「{first}」區還是空的{more}",
                      "這是個人化的唯一載體：沒填，Claude 每次都要重問「這縮寫是什麼」「raw/ 怎麼分」",
                      f"打開 CLAUDE.md 填「{first}」區（一兩列就好），或跑 /wiki-init 走引導"))

    # 3 掛了 repo 但沒 ingest 過
    for alias in s["repos"]:
        if not any(k.startswith(alias + "::") for k in sources):
            out.append(_f("repo_zero", "🟡",
                          f"外部 repo「{alias}」已註冊，但 0 筆 ingest 紀錄",
                          "註冊只是掛名，沒建卡 wiki 還是不知道裡面有什麼",
                          f"/wiki-ingest {alias}::"))
            break

    # 4 git
    if not _git(root, "rev-parse", "--is-inside-work-tree"):
        out.append(_f("no_git", "🟡",
                      "vault 不是 git repo",
                      "wiki/ 是 Claude 寫的，沒有版本紀錄就沒有回退點，也沒有 R3 的第一落盤處（commit message）",
                      'git init && git add -A && git commit -m "init: vault 骨架"'))
    elif not _git(root, "rev-parse", "--verify", "HEAD"):
        out.append(_f("no_commit", "🟡",
                      "git repo 還沒有任何 commit",
                      "沒有第一個 commit 就沒有回退點；R3 的第一落盤處是 commit message",
                      'git add -A && git commit -m "init: vault 骨架"'))

    # 5 積壓
    if self_sources and len(uningested) > BACKLOG_MIN:
        out.append(_f("ingest_backlog", "🟡",
                      f"raw/ 約有 {len(uningested)} 份檔沒有 ingest 紀錄（已 ingest {len(self_sources)} 筆；路徑比對，含刻意不建卡的）",
                      "沒建卡的檔對 wiki 是隱形的；積壓越久越分不清哪些是刻意不建卡、哪些是漏掉",
                      "先跑 scripts/stale_check.py 拿精確清單（hash 比對），對照 wiki/ops/ingest.md 的不建卡規則，剩下的 /wiki-ingest raw/ 批次"))

    # 6 hot 落後 log（判斷在 vault_state，這裡只轉成行動項 —— 同一件事不算兩次）
    if s.get("hot_behind_log"):
        hot_day, log_day = s["hot_behind_log"]
        out.append(_f("hot_stale", "🟡",
                      f"wiki/hot.md 停在 {hot_day}，log 已有 {log_day} 的條目",
                      "hot.md 是每 session 第一份讀的檔；它落後 log 表示收尾協議沒跑，下次開場會接錯地方",
                      "把最近 3 次操作與待確認寫進 wiki/hot.md「目前狀態」，舊的移進 log"))

    # 7 裁示沒落盤
    rul = root / "wiki" / "ops" / "rulings.md"
    if rul.is_file() and len(entries) >= RULINGS_MIN_LOG:
        try:
            body = _strip_comments(rul.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            body = ""
        if not re.search(r"^### ", body, flags=re.M):
            out.append(_f("rulings_empty", "🟡",
                          f"log 已有 {len(entries)} 條，wiki/ops/rulings.md 仍無任何裁示",
                          "跑了這麼多輪一定有「以後都這樣做」的決定；只留在對話或 log 裡等於沒定（R3）",
                          "回想最近一次「以後都這樣」的決定，寫成 `### 一句話（v日期，使用者裁示）` 進 rulings.md，CLAUDE.md 🔴 區留一句"))

    # 7b ingest 很多、從沒查過 → 問「值不值得建卡」
    n_ing = sum(1 for e in entries if e.get("kind") == "ingest")
    n_q = sum(1 for e in entries if e.get("kind") == "query")
    if n_ing >= INGEST_UNQUERIED_MIN and n_q == 0:
        out.append(_f("ingest_unqueried", "🔵",
                      f"log 有 {n_ing} 次 ingest、0 次 query",
                      "建了沒人查的卡不是知識，是維護負擔；下一份 ingest 前先問「有人會查它嗎」「要找得到還是讀得懂」",
                      "拿一個真問題跑 /wiki-query；之後每份 ingest 前先過 wiki-coach 的兩題"))

    # 8 老化訊號 —— 🔴 判斷不在這裡，在 vault_state.aging_flags()
    #    原本這裡自己重算「從未健檢／健檢過期」，與 aging 部分重疊 ——
    #    同一件事兩處實作遲早會漂（2026-09-26 收掉，同 hot_behind_log 的處理）。
    #    分工：vault_state 偵測「有什麼不對」，coach 只說「那該做什麼」。
    out.extend(_aging_findings(s))

    # 9 agenda
    agenda = root / "wiki" / "agenda.md"
    if agenda.is_file():
        if _count_events(agenda) == 0:
            out.append(_f("agenda_empty", "🔵",
                          "wiki/agenda.md 存在但沒有任何未完成的事件",
                          "空的 agenda 會被當成「沒事」，該追的期限就不會被提醒",
                          '/wiki-agenda，或 python scripts/agenda.py add "YYYY-MM-DD 提醒 標題"'))
    elif tier == "mature":
        out.append(_f("agenda_missing", "🔵",
                      "成熟 vault 但沒有 wiki/agenda.md",
                      "超過 100 頁的 vault 一定有期限與待追事項，散在 log 裡沒人會看到",
                      '/wiki-agenda，或 python scripts/agenda.py add "YYYY-MM-DD 提醒 標題"（無檔會自動建）'))

    out.sort(key=lambda f: SEV_RANK.get(f["severity"], 9))
    return tier, out


GREEN = {
    # 🔴 seed 分兩段：還沒 ingest → 教 ingest；已經有卡 → **教查詢**。
    # 只教到 ingest 等於教人蓋了索引卻從不查 —— 查詢才是這套系統的回報點，
    # 而且第一次查會親眼看到「指標卡不含數值、要回正本讀」是什麼意思（2026-09-22 驗收補）。
    "seed": "🟢 沒有卡點。新生 vault → 再丟一份文件進 raw/ 然後 /wiki-ingest raw/，看卡長什麼樣",
    "seed_has_cards": "🟢 沒有卡點。**下一步是實際用它**：`/wiki-query <你剛放進去那份文件裡的某個東西>`\n"
                      "   第一次查會看到系統怎麼從 hot → 卡 → 回正本，也會看到指標卡為什麼不放數值。",
    "growing": "🟢 沒有卡點。成長中 vault → 跑 /wiki-doctor，這階段最容易長出重複與孤島",
    "mature": "🟢 沒有卡點。成熟 vault → 拿一個真問題跑 /wiki-query，實際用它才知道哪裡缺",
}


def green_for(tier, root):
    """seed 階段依「有沒有卡」分流 —— 有卡了就該教查詢，不是再叫他 ingest 一份。"""
    if tier == "seed" and root is not None:
        cards = list((Path(root) / "wiki" / "catalog").glob("*.md")) if (Path(root) / "wiki" / "catalog").is_dir() else []
        if cards:
            return GREEN["seed_has_cards"]
    return GREEN.get(tier, "🟢 沒有卡點")


def render_one(f):
    return f"{f['severity']} {f['finding']}\n   為什麼：{f['why']}\n   做這個：{f['action']}"


def _set_mode(root, mode):
    if root is None:
        print("🔴 這裡不是 vault，沒有 manifest 可寫")
        return 1
    if mode not in vs.COACH_MODES:
        print(f"🔴 模式只能是 {'／'.join(vs.COACH_MODES)}")
        return 1
    m = load_manifest(root)
    m.setdefault("config", {})["coach"] = mode
    save_manifest(root, m)
    desc = {"auto": "依成熟度：新 vault 開場講解，成熟後閉嘴",
            "on": "長開：每次開場都講一件該做的事",
            "off": "長關：開場不講指導，只報老化訊號；/wiki-coach 仍可手動叫"}[mode]
    print(f"✅ 教練模式 → {mode}（{desc}）")
    print("已寫入：raw/.manifest.json（config.coach）；下次開場生效")
    return 0


def main():
    args = sys.argv[1:]
    start = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    root = find_vault_root(Path(start))

    if "--set" in args:
        i = args.index("--set")
        return _set_mode(root, args[i + 1] if i + 1 < len(args) else "")
    if "--mode" in args:
        print(f"教練模式：{vs.coach_mode(root)}")
        return 0

    tier, fs = findings(root)

    if "--json" in args:
        print(json.dumps({"root": str(root) if root else None, "tier": tier,
                          "top": fs[0] if fs else None, "findings": fs,
                          "green": None if fs else green_for(tier, root)}, ensure_ascii=False, indent=2))
        return 0

    head = f"Vault：{root}　成熟度：{tier}" if root else "Vault：（無）"
    print(head)
    if not fs:
        print(green_for(tier, root))
        return 0
    if "--all" in args:
        for i, f in enumerate(fs, 1):
            print(f"\n{i}. {render_one(f)}")
    else:
        print(render_one(fs[0]))
        if len(fs) > 1:
            print(f"（其餘 {len(fs) - 1} 項先不管；想看全部：--all）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
