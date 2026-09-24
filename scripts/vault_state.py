#!/usr/bin/env python3
"""偵測 vault 成熟度，輸出對應深度的指導。

設計原則：等級掛在 vault 上，不掛在人身上。
人的等級是自陳的、不會主動升級；vault 的成熟度是可測的、會自己長大。

用法：
    python vault_state.py            # 人看的報告
    python vault_state.py --json     # 機器讀的完整訊號
    python vault_state.py --brief    # SessionStart hook 用（極簡）
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib.vaultpaths import (find_vault_root, load_manifest,  # noqa: E402
                             manifest_sources, resolve_repo_path, resolve_source)
try:
    import _guard_status  # noqa: E402
except ImportError:      # 守門留痕模組缺席不該讓開場量測掛掉
    _guard_status = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# --- 門檻（集中在此，方便調整） ---
SEED_MAX = 20            # 頁數 < 此值 = 新生 vault
GROWING_MAX = 100        # 頁數 < 此值 = 成長中
LOG_WARN_KB = 200        # log.md 超過此大小 = 讀不動了
PAGE_WARN_KB = 100       # 單頁超過此大小 = 該拆
HOT_WARN_LINES = 150     # hot.md 超過此行數 = 輪替沒執行
CLAUDE_WARN_LINES = 150  # CLAUDE.md 超過此行數 = 該把按需規則拆到 wiki/ops/
RULING_MAX = 5           # CLAUDE.md 🔴／⚠️ 區各最多幾條，多的搬 wiki/ops/rulings.md
LINT_STALE_DAYS = 60     # 距上次健檢超過此天數 = 該跑了
DAY = 86400
# 不算「知識頁」的東西：系統骨架與規則層。剛 init 的 vault 頁數應為 0，不是 8。
NON_PAGE_TYPES = {"meta", "ops-rule", "fold"}
NON_PAGE_FILES = {"log.md", "hot.md", "index.md"}
GUARD_ALWAYS = ("tidy-check", "stale-check")   # 這兩支任何 vault 都該跑；其餘只在留痕過才追蹤
_TYPE_RE = re.compile(r"^type:\s*([\w\-]+)", re.M)


def _fm_type(p: Path):
    """frontmatter 的 type:，沒有回 None。只讀檔頭。"""
    try:
        with p.open(encoding="utf-8", errors="replace") as f:
            head = f.read(600)
    except OSError:
        return None
    if not head.startswith("---"):
        return None
    m = _TYPE_RE.search(head.split("---", 2)[1] if head.count("---") >= 2 else head)
    return m.group(1) if m else None


def _count_pages(wiki: Path):
    """回傳 (頁數, 最大的幾頁)。頁數排除 meta／ops-rule／fold 與 log／hot／index。"""
    pages, sizes = 0, []
    for p in wiki.rglob("*.md"):
        # 只看 wiki/ 內的相對路徑——絕對路徑可能含 . 開頭的父目錄（會被誤判成隱藏檔）
        rel = p.relative_to(wiki)
        if any(part.startswith(".") for part in rel.parts):
            continue
        try:
            sizes.append((p.stat().st_size, p))
        except OSError:
            pass
        if str(rel).replace("\\", "/") in NON_PAGE_FILES or _fm_type(p) in NON_PAGE_TYPES:
            continue
        pages += 1
    sizes.sort(reverse=True)
    return pages, sizes[:5]


def _guard_stale(root: Path):
    """守門失聯清單。只列「留痕過」或 GUARD_ALWAYS 的腳本，免得沒 agenda 的 vault 被唸。"""
    if _guard_status is None:
        return []
    try:
        known = _guard_status.known_scripts()
    except OSError:
        known = set()
    track = known | set(GUARD_ALWAYS)
    return [h for h in _guard_status.stale_report() if h.split("：", 1)[0] in track]


def _git_last_commit_age(root: Path):
    """距最後一次 commit 幾天。非 git 或無 commit 回 None。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%ct"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return (time.time() - int(out.stdout.strip())) / DAY
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def _newest_mtime(paths):
    best = None
    for p in paths:
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if best is None or m > best:
            best = m
    return best


def _ruling_overflow(text):
    """CLAUDE.md 的 🔴／⚠️ 區各數條目（以 - 或 ### 開頭），超過 RULING_MAX 就回報。"""
    out, sec, n = [], None, 0
    for line in text.splitlines() + ["## END"]:
        if line.startswith("## "):
            if sec and n > RULING_MAX:
                out.append((sec, n))
            sec = "🔴 鐵律／裁示" if line.startswith("## 🔴") else "⚠️ 踩過的雷" if line.startswith("## ⚠️") else None
            n = 0
        elif sec and (line.startswith("- ") or line.startswith("### ")):
            n += 1
    return out


INGESTABLE = {".pdf", ".md", ".docx", ".doc", ".xlsx", ".pptx", ".txt"}


def _raw_pending(root: Path, manifest):
    """raw/ 底下還沒 ingest 的檔數。

    只為了回答「開場該不該推 /wiki-ingest」—— 素材都編完了還在推，
    等於每個 session 開頭都叫人做一件已經做完的事（2026-09-21 驗收發現）。
    `_README.md` 是資料夾儀表板、不是來源，不計。
    """
    raw = root / "raw"
    if not raw.is_dir():
        return 0
    done = set(manifest_sources(manifest))
    n = 0
    try:
        for p in raw.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in INGESTABLE:
                continue
            if p.name == "_README.md" or any(x.startswith(".") for x in p.parts):
                continue
            if str(p.relative_to(root)).replace("\\", "/") not in done:
                n += 1
    except OSError:
        return 0
    return n


def collect(root: Path):
    wiki = root / "wiki"
    manifest = load_manifest(root)

    s = {
        "root": str(root),
        "has_wiki": wiki.is_dir(),
        "pages": 0,
        "big_pages": [],
        "log_kb": 0,
        "hot_lines": None,
        "claude_lines": None,
        "ruling_overflow": [],
        "sources": len(manifest_sources(manifest)),
        "repos": [k for k in manifest.get("repos", {}) if not k.startswith("_")],
        "days_since_lint": None,
        "days_since_commit": _git_last_commit_age(root),
        "broken_sources": [],
        "broken_repos": [],
        "orphan_cards": [],
        "index_missing": [],
        "index_dead_refs": [],
        "guard_stale": [],
        "raw_pending": 0,
    }

    if not s["has_wiki"]:
        return s

    s["raw_pending"] = _raw_pending(root, manifest)

    s["pages"], big = _count_pages(wiki)
    s["guard_stale"] = _guard_stale(root)
    s["big_pages"] = [
        {"path": str(p.relative_to(root)).replace("\\", "/"), "kb": round(n / 1024)}
        for n, p in big if n > PAGE_WARN_KB * 1024
    ]

    log = wiki / "log.md"
    if log.is_file():
        s["log_kb"] = round(log.stat().st_size / 1024)

    hot = wiki / "hot.md"
    if hot.is_file():
        try:
            s["hot_lines"] = sum(1 for _ in hot.open(encoding="utf-8", errors="replace"))
        except OSError:
            pass

    cm = root / "CLAUDE.md"
    if cm.is_file():
        try:
            text = cm.read_text(encoding="utf-8", errors="replace")
            s["claude_lines"] = text.count("\n") + 1
            s["ruling_overflow"] = _ruling_overflow(text)
        except OSError:
            pass

    # 健檢時間：找任何叫 lint-report* 的檔，取最新
    reports = (list(wiki.rglob("doctor-report*")) + list(wiki.rglob("lint-report*"))
               + list(wiki.rglob("*lint*.md")))
    newest = _newest_mtime(reports)
    if newest:
        s["days_since_lint"] = (time.time() - newest) / DAY

    # 來源完整性：抽查 manifest 指向的檔還在不在
    repos_cfg = manifest.get("repos", {})
    srcs = manifest_sources(manifest)
    for key in list(srcs)[:400]:
        if "::" in key:
            alias, rel = key.split("::", 1)
            base = repos_cfg.get(alias, {}).get("path")
            if not base:
                s["broken_sources"].append(key)
                continue
            target = resolve_repo_path(root, base) / rel   # #27
        else:
            target = root / key
        if not target.exists():
            s["broken_sources"].append(key)

    for alias in s["repos"]:
        p = repos_cfg.get(alias, {}).get("path", "")
        if p and not resolve_repo_path(root, p).exists():  # #27
            s["broken_repos"].append(alias)

    # 🔴 #28 反向對帳：catalog 卡存在、manifest 卻沒有對應的 sources 條目。
    # broken_sources 抓的是 manifest → 檔案不見；這裡抓的是卡 → 沒有來源紀錄。
    # 後者更陰險：卡看起來在，但 scan 永遠不會說它過期 —— 死卡，會無聲腐爛。
    # （2026-09-21 踩到：AS9100 指標卡手寫進 catalog/ 卻漏了 ingest 的 Step 4。）
    cited = {v.get("catalog_page", "").replace("\\", "/") for v in srcs.values()}
    cat = root / "wiki" / "catalog"
    if cat.is_dir():
        for f in sorted(cat.glob("*.md")):
            rel = f.relative_to(root).as_posix()
            if rel not in cited:
                s["orphan_cards"].append(rel)

    # 🔴 #30 index.md 雙向對帳。`wiki/repos.md` 由 repo.py 自動重建，但 `wiki/index.md`
    # 只靠 ingest Step 5 手動加，也沒有 maintenance 宣告 → tidy_check 不看它。
    # 兩種腐爛都實際發生過（2026-09-21）：建了卡忘了進目錄；alias 重掛後目錄裡的
    # source key 變死連結。目錄是給人讀的入口，錯了比沒有更糟。
    idx = root / "wiki" / "index.md"
    if idx.is_file():
        try:
            itext = idx.read_text(encoding="utf-8", errors="replace")
        except OSError:
            itext = ""
        if itext:
            for f in sorted((root / "wiki" / "catalog").glob("*.md"))                     if (root / "wiki" / "catalog").is_dir() else []:
                if f.stem not in itext:
                    s["index_missing"].append(f.relative_to(root).as_posix())
            for key in set(re.findall(r"`([^`\s]+::[^`]+)`", itext)):
                tgt = resolve_source(root, key)
                if tgt is None or not tgt.exists():
                    s["index_dead_refs"].append(key)

    return s


def tier_of(s):
    if not s["has_wiki"]:
        return "absent"
    if s["pages"] < SEED_MAX:
        return "seed"
    if s["pages"] < GROWING_MAX:
        return "growing"
    return "mature"


def aging_flags(s):
    """老化訊號。與 tier 無關，任何成熟度都可能出現。"""
    f = []
    if s["log_kb"] > LOG_WARN_KB:
        f.append(("log 過大", f"wiki/log.md {s['log_kb']}KB — 已無法整份讀，查詢改用 Grep 帶關鍵字"))
    for bp in s["big_pages"]:
        if bp["path"].endswith("wiki/log.md") and s["log_kb"] > LOG_WARN_KB:
            continue  # 已由上一條報過
        f.append(("單頁過大", f"{bp['path']} {bp['kb']}KB — 考慮拆頁"))
    if s["hot_lines"] and s["hot_lines"] > HOT_WARN_LINES:
        f.append(("hot 沒輪替", f"wiki/hot.md {s['hot_lines']} 行（上限 {HOT_WARN_LINES}）— 該修剪"))
    if s["claude_lines"] and s["claude_lines"] > CLAUDE_WARN_LINES:
        f.append(("CLAUDE.md 過大", f"{s['claude_lines']} 行（上限 {CLAUDE_WARN_LINES}）— 每 session 都載入；把按需規則拆到 wiki/ops/，本檔留指標"))
    for sec, n in s["ruling_overflow"]:
        f.append((f"{sec} 區溢出", f"CLAUDE.md 該區 {n} 條（上限 {RULING_MAX}）— 最舊的搬到 wiki/ops/rulings.md，本區只留一句話"))
    if s["days_since_lint"] is None and s["pages"] >= SEED_MAX:
        f.append(("從未健檢", f"{s['pages']} 頁但找不到健檢紀錄 — 跑 /wiki-doctor 並存 doctor-report"))
    elif s["days_since_lint"] and s["days_since_lint"] > LINT_STALE_DAYS:
        f.append(("健檢過期", f"上次健檢在 {int(s['days_since_lint'])} 天前 — 跑 /wiki-doctor"))
    if s["index_missing"]:
        n = len(s["index_missing"])
        head = "、".join(Path(c).stem for c in s["index_missing"][:3])
        f.append(("目錄漏卡",
                  f"{n} 張 catalog 卡沒出現在 wiki/index.md（{head}{'…' if n > 3 else ''}）"
                  f" — 目錄是入口，漏了等於查不到"))
    if s["index_dead_refs"]:
        n = len(s["index_dead_refs"])
        f.append(("目錄死連結",
                  f"wiki/index.md 有 {n} 個 source key 解析不開"
                  f"（{s['index_dead_refs'][0]}{'…' if n > 1 else ''}）"
                  f" — alias 多半被 remove 或改名過，跑 /wiki-repo rename"))
    if s["orphan_cards"]:
        n = len(s["orphan_cards"])
        head = "、".join(Path(c).stem for c in s["orphan_cards"][:3])
        f.append(("孤兒卡",
                  f"{n} 張 catalog 卡沒有 manifest 紀錄（{head}{'…' if n > 3 else ''}）"
                  f" — scan 追不到它們過期，補 sources 條目或刪卡"))
    if s["broken_repos"]:
        f.append(("repo 路徑失效", f"{', '.join(s['broken_repos'])} — 跑 /wiki-repo scan"))
    n = len(s["broken_sources"])
    if n:
        f.append(("來源檔消失", f"{n} 筆 manifest 紀錄指向不存在的檔 — 跑 /wiki-repo scan"))
    for h in s["guard_stale"]:
        if "從未留痕" in h and s["pages"] < SEED_MAX:
            continue  # 新生 vault 還沒東西可守，與「從未健檢」同一門檻
        f.append(("守門失聯", f"{h} — 沒有東西驗證守門還在跑，它就會靜靜死掉"))
    return f


GUIDANCE = {
    "absent": [
        "**這個資料夾還不是 wiki vault。** 第一次用的話照這三步：",
        "",
        "1. `/wiki-init` —— 會問你三題（管什麼對象／`raw/` 怎麼分／有沒有制度或散在別處的專案），然後產出骨架",
        "2. 把第一份文件丟進 `raw/`，跑 `/wiki-ingest raw/`",
        "3. 之後任何時候不知道下一步 → `/wiki-coach`（它看你的 vault 現況，只講一件該做的事）",
        "",
        "檔案在別的資料夾、不想搬 → `/wiki-repo add <路徑>`，檔案留原地只記指標。",
    ],
    "seed": [
        "**新生 vault** — 以下是這套系統的運作方式（vault 長大後這段會自動消失）：",
        "",
        "- `raw/` 放原始檔（你維護），`wiki/` 放 Claude 編譯出的知識（Claude 維護）",
        "- 鐵律：**wiki 只存指標，不抄會變動的內容** — 抄了就會過期，變成「看起來有、其實錯」的垃圾",
        "- 每個 wiki 頁必須標來源，非資料庫的資訊必須標 `[⚠️ 非資料庫：...]`",
        "- 檔案不必搬進來：`/wiki-repo add <路徑>` 可以把散在各處的專案掛進同一個 wiki",
    ],
    "growing": [
        "**成長中 vault** — 這個階段最容易累積的問題是「重複與孤島」。",
        "建議：`/wiki-doctor` 找出老化訊號與孤立頁；用 `/wiki-query` 查詢而不是自己翻檔案。",
    ],
    "mature": [],  # 成熟 vault 不解說，只在有老化訊號時出聲
}


def next_action(s, tier):
    """開場那句「現在最值得做的」。看實際狀態，不是固定字串。"""
    if tier not in ("seed", "growing"):
        return None
    n = s["raw_pending"]
    if n:
        return f"現在最值得做的：`/wiki-ingest raw/` 把 {n} 份還沒編的素材編一次，看它長什麼樣。"
    if not s["sources"]:
        return ("現在最值得做的：把第一份文件丟進 `raw/`，再 `/wiki-ingest raw/`；"
                "檔案在別的資料夾就用 `/wiki-repo add <路徑>`。")
    if not s["repos"]:
        return ("`raw/` 都編完了。下一步：`/wiki-query <問題>` 試查一次，"
                "或 `/wiki-repo discover <上層資料夾>` 把別處的專案掛進來。")
    return "`raw/` 都編完了。下一步：`/wiki-query <問題>` 試查，或 `/wiki-repo scan` 看外部 repo 有無變更。"


COACH_MODES = ("auto", "on", "off")


def coach_mode(root):
    """manifest config.coach：auto（預設，依成熟度）／on（每次開場都講）／off（開場不講，只報老化訊號）。"""
    if not root:
        return "auto"
    m = load_manifest(Path(root)).get("config", {}).get("coach", "auto")
    return m if m in COACH_MODES else "auto"


def _coach_top(root):
    """on 模式：開場附上 coach 最優先的一項。延遲 import，coach 反向依賴本模組。"""
    try:
        import coach
        _, fs = coach.findings(Path(root))
        return coach.render_one(fs[0]) if fs else coach.green_for(tier_of(collect(Path(root))), Path(root))
    except Exception:  # noqa: BLE001 — 開場 hook 不能因 coach 壞掉而掛
        return None


def render(s, brief=False):
    tier = tier_of(s)
    flags = aging_flags(s)
    out = []

    if brief:
        # SessionStart 注入：沒事就安靜，有事才講
        if tier == "absent":
            return ""  # 不是 vault，完全不打擾
        head = f"[llm-wiki] {tier} · {s['pages']} 頁 · {s['sources']} 筆來源"
        if s["repos"]:
            head += f" · {len(s['repos'])} 個外部 repo"
        mode = coach_mode(s["root"])
        if mode != "auto":
            head += f" · coach {mode}"
        out.append(head)
        if mode == "on":
            top = _coach_top(s["root"])
            if top:
                out += ["", "🧭 教練：", top]
        elif mode == "auto" and tier in ("seed", "growing"):
            out += ["", *GUIDANCE[tier]]
            act = next_action(s, tier)
            if act:
                out += ["", act]
        if flags:
            out.append("")
            out.append(f"⚠️ 老化訊號 {len(flags)} 項（開場提一句，不必當場處理）：")
            out += [f"  - {k}：{v}" for k, v in flags[:5]]
        return "\n".join(out)

    out.append(f"Vault：{s['root']}")
    out.append(f"成熟度：{tier}　頁數：{s['pages']}　來源：{s['sources']}"
               f"　raw/ 待編：{s['raw_pending']}")
    if s["repos"]:
        out.append(f"外部 repo：{', '.join(s['repos'])}")
    if s["days_since_commit"] is not None:
        out.append(f"最後 commit：{int(s['days_since_commit'])} 天前")
    mode = coach_mode(s["root"])
    if mode != "auto":
        out.append(f"教練模式：{mode}（改：/wiki-coach auto|on|off）")
    elif tier in ("seed", "growing"):
        out.append(f"（{tier} 階段的操作指導只在 session 開場印；要看：/wiki-coach。長開／長關：/wiki-coach on|off）")
    out.append("")
    if flags:
        out.append(f"🟡 老化訊號 {len(flags)} 項：")
        out += [f"  - {k}：{v}" for k, v in flags]
    else:
        out.append("🟢 無老化訊號")
    return "\n".join(out)


def main():
    args = sys.argv[1:]
    start = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    root = find_vault_root(Path(start))
    if root is None:
        # --brief 是 SessionStart hook 在跑：非 vault 目錄一律靜默，不吵人。
        # 其他情況（使用者自己跑 /wiki）要給指導 —— 只印「找不到」等於把新手丟在原地。
        if "--json" in args:
            print(json.dumps({"has_wiki": False, "root": None, "tier": "absent"}, ensure_ascii=False))
        elif "--brief" not in args:
            print("找不到 vault（往上找不到含 wiki/ 或 raw/.manifest.json 的目錄）")
            print()
            print("\n".join(GUIDANCE["absent"]))
        return 0

    s = collect(root)
    if "--json" in args:
        s["tier"] = tier_of(s)
        s["aging"] = [{"kind": k, "detail": v} for k, v in aging_flags(s)]
        print(json.dumps(s, ensure_ascii=False, indent=2))
    else:
        text = render(s, brief="--brief" in args)
        if text:
            print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
