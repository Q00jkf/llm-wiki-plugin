#!/usr/bin/env python3
"""多 repo 來源管理：讓一個 wiki 管理散在各處的多個 git 專案。

核心原則：wiki 不搬檔案，只記路徑。外部 repo 的檔案永遠留在原地，一律唯讀。

🔴 為什麼每筆都要記擁有者：
   絕對路徑（C:\\Users\\...）只存在於記錄者那一台電腦。多人共編時，
   別台機器看到的是一條死路徑 —— 必須知道「這是誰的機器、有沒有 remote 可拿」。

用法：
    python repo.py add <路徑> [--alias 別名] [--desc 說明]
    python repo.py list
    python repo.py scan [alias]
    python repo.py remove <alias>
"""
import argparse
import os
import platform
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import filehash as _filehash  # noqa: E402
from _lib.vaultpaths import (find_vault_root, load_manifest, save_manifest,  # noqa: E402
                             resolve_repo_path, portable_path, is_hardcoded)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

INGESTABLE = {".md", ".txt", ".pdf", ".docx", ".doc", ".epub", ".xlsx", ".pptx"}

# 🔴 #25：超過這個數量就不建議批次 ingest。
# 原本寫死 200 —— 但公司級文件庫常見規模就落在 100～200（實例：某份二階程序書
# 共 139 份），正好在門檻下，`add` 於是建議「批次 ingest 整個 repo」= 一口氣編一兩百張卡。
# 批次的合理上限是「你願意一次看完的量」，不是「檔案系統撐得住的量」。
BATCH_SAFE_MAX = 30
DEFAULT_EXCLUDE = [".git", "node_modules", "__pycache__", "dist", "build",
                   ".venv", "venv", ".obsidian", "site-packages"]


def _git(path, *args):
    try:
        r = subprocess.run(["git", "-C", str(path), *args],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _is_excluded(p: Path, base: Path, excludes):
    try:
        parts = p.relative_to(base).parts
    except ValueError:
        return True
    return any(part in excludes for part in parts)


def _walk(base: Path, excludes, max_depth=None):
    """深度受限、容錯的目錄走訪。

    不用 rglob：真實硬碟上有 WSL 符號連結、junction、權限不足的路徑，
    rglob 撞到就整個拋 OSError（實測 WinError 1920）。
    """
    stack = [(base, 0)]
    while stack:
        d, depth = stack.pop()
        # 🔴 這裡是 >= 不是 >：下面 yield 的是 depth+1。
        # 用 > 會讓 --depth 1 吐到第 2 層（2026-09-21 驗收實測）。
        if max_depth is not None and depth >= max_depth:
            continue
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue                      # 權限不足／斷掉的連結 → 跳過，不中斷
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    if e.name in excludes or e.name.startswith("."):
                        continue
                    stack.append((Path(e.path), depth + 1))
                    yield Path(e.path), True, depth + 1
                elif e.is_file(follow_symlinks=False):
                    yield Path(e.path), False, depth + 1
            except OSError:
                continue


def _candidates(base: Path, excludes, max_depth=None):
    return [p for p, is_dir, _ in _walk(base, excludes, max_depth)
            if not is_dir and p.suffix.lower() in INGESTABLE]


def _md5(p: Path):
    try:
        return _filehash.md5_of(p)          # 文字檔正規化行尾（#19）
    except OSError:
        return None


def _slug(name):
    s = re.sub(r"[^\w\-]+", "-", name.strip().lower())
    return re.sub(r"-{2,}", "-", s).strip("-") or "repo"


# 這些名字當 alias 毫無鑑別力（一顆硬碟上會有幾十個 doc/），改用「父層-自己」
GENERIC = {"doc", "docs", "raw", "wiki", "src", "app", "lib", "data", "files",
           "其他", "文件", "資料", "temp", "tmp", "new", "old", "bak"}

# 程式碼樹的特徵檔：出現就代表這是 source repo，不是文件資料夾
CODE_MARKERS = {"package.json", "cmakelists.txt", "makefile", "cargo.toml",
                "pyproject.toml", "setup.py", "go.mod", "pom.xml", "wscript"}


def _suggest_alias(d: Path, taken):
    """產生有鑑別力且不重複的 alias。"""
    base = _slug(d.name)
    if base in GENERIC or base in taken:
        parent = _slug(d.parent.name)
        if parent and parent not in GENERIC:
            base = f"{parent}-{base}"
    cand, i = base, 2
    while cand in taken:
        cand, i = f"{base}-{i}", i + 1
    taken.add(cand)
    return cand


# 🔴 掛進來的東西本身就是一個 llm-wiki vault（或它的知識層）時，行為必須不同：
# 對方的 `wiki/` 是「已經編譯過的知識」，再 ingest 一次＝同一份知識存兩份，
# 之後對方更新、我方不知道 → 兩邊無聲漂掉。這正是「wiki 只存指標」要防的事。
# （2026-09-21 踩到 #23：掛一個別人已編譯的 vault，add 照樣印「批次 ingest 整個 repo」。）
def _detect_wiki(d: Path):
    """判斷掛載目標是不是既有 wiki vault。回傳 kind 或 None。

    - "vault-root"    ：整個 vault（有 wiki/index.md，旁邊還有 raw/ 或 CLAUDE.md）
    - "compiled-wiki" ：vault 的知識層本身（index.md + log.md 並存）
    """
    try:
        if (d / "wiki" / "index.md").is_file() and (
                (d / "raw").is_dir() or (d / "CLAUDE.md").is_file()):
            return "vault-root"
        if (d / "index.md").is_file() and (d / "log.md").is_file():
            return "compiled-wiki"
    except OSError:
        pass
    return None


def _looks_like_code(d: Path):
    try:
        names = {e.name.lower() for e in os.scandir(d) if e.is_file()}
    except OSError:
        return False
    return bool(names & CODE_MARKERS)


# 🔴 #26：`kind` 只在 add 當下判定，0.4.12 之前掛的條目通通沒有這一欄，
# 於是 repos.md 把「整包掛進來的 wiki vault」標成「文件」—— 0.4.12 的防護對
# **已經掛錯的**完全無效，而已經掛錯的才是最需要提醒的。
# （2026-09-21 發現：某 alias 指向 vault 根，raw 1396＋wiki 65＋雜訊 79，卻標「文件」。）
# 每次重建 repos.md 前回填一次：缺 kind、或路徑內容變了（raw/wiki 被加進去）都重判。
# #27 遷移：0.4.14 以前註冊的條目存的是絕對路徑，一律壓成可攜 spec。
# 壓不掉的（跨磁碟機）保持絕對，由 list／repos.md 標出來讓使用者自己改成 ${VAR}。
def backfill_paths(root, m) -> bool:
    changed = False
    for alias, r in m.get("repos", {}).items():
        if alias.startswith("_"):
            continue
        spec = r.get("path", "")
        if not is_hardcoded(spec):
            continue                      # 已是 ~ / ${VAR} / 相對
        better = portable_path(root, spec)
        if better != spec:
            r["path"] = better
            changed = True
    return changed


def backfill_kinds(root, m) -> bool:
    """替 manifest 內的 repos 補上／更新 kind。回傳有沒有改動。"""
    changed = False
    for alias, r in m.get("repos", {}).items():
        if alias.startswith("_"):
            continue
        path = resolve_repo_path(root, r.get("path", ""))
        if not path.is_dir():
            continue                      # 路徑失效時不動它，維持原狀待擁有者處理
        now = _detect_wiki(path) or "docs"
        if r.get("kind") != now:
            r["kind"] = now
            changed = True
    return changed


def write_repos_page(root):
    """依 manifest 重建 `wiki/repos.md`（外部 repo 總覽）。

    為什麼要有這支：`wiki-ingest` skill 與 `wiki-core` 的目錄樹都寫「外部 repo 更新
    wiki/repos.md」，但在 0.4.2 以前沒有任何程式會建它 —— 那一頁永遠不存在
    （2026-09-21 驗收發現）。這裡由 manifest 全量重建，所以不會與 manifest 漂掉。

    整份重寫是刻意的：它是**衍生檔**，真相來源永遠是 raw/.manifest.json。
    """
    wiki = root / "wiki"
    if not wiki.is_dir():
        return None
    m = load_manifest(root)
    if backfill_paths(root, m) | backfill_kinds(root, m):
        save_manifest(root, m)            # #26 補 kind、#27 把絕對路徑壓成可攜
    repos = {k: v for k, v in m.get("repos", {}).items() if not k.startswith("_")}
    sources = m.get("sources", {})
    p = wiki / "repos.md"

    if not repos:
        if p.exists():
            p.unlink()                    # 最後一個 repo 被 remove → 不留空殼頁
        return None

    L = [
        "---", "type: meta", "title: 外部 repo 總覽",
        f"updated: {date.today().isoformat()}",
        "---", "",
        "# 外部 repo 總覽", "",
        "> 由 `repo.py` 依 `raw/.manifest.json` 自動重建 —— **不要手改**，改了下次 add／remove 會被蓋掉。",
        "> 🔴 外部 repo 一律唯讀：不建檔、不改檔、不 commit、不 pull。", "",
        "| alias | 種類 | 路徑 | 擁有者 | Remote | 卡片 | 狀態 |",
        "|---|---|---|---|---|---|---|",
    ]
    # 「種類」欄不是裝飾：知識層 alias 一律不可 ingest，下個 session 只看得到這一頁，
    # 沒標就會照一般 repo 處理，把別人的知識重編一份（#23）。
    KIND = {"compiled-wiki": "🔴 知識層", "vault-root": "⚠️ wiki 根", "docs": "文件"}
    for alias, r in sorted(repos.items()):
        n = sum(1 for k in sources if k.startswith(f"{alias}::"))
        o = r.get("owner") or {}
        alive = resolve_repo_path(root, r.get("path", "")).exists()
        L.append(
            f"| `{alias}` | {KIND.get(r.get('kind', 'docs'), '文件')} | `{r.get('path','')}` "
            f"| {o.get('name','?')} @ {o.get('machine','?')} "
            f"| {o.get('remote','?')} | {n} | {'✅ 在' if alive else '🔴 路徑失效'} |"
        )
    hard = [a for a, r in repos.items() if is_hardcoded(r.get("path", ""))]
    if hard:
        L += ["",
              f"> 🔴 {'、'.join(hard)} 的路徑是**絕對路徑**（壓不成相對／`~`，多半跨磁碟機）。",
              "> 換一台機器或改使用者名稱就會失效 —— 改成 `${你的變數}/子路徑`，兩台都設好那個環境變數。"]
    if any(r.get("kind") == "compiled-wiki" for r in repos.values()):
        L += ["",
              "> 🔴 標「知識層」的 alias 是**別人已編譯的 wiki**，"
              "一律不 ingest（重編＝同一份知識兩處，必漂）。",
              "> 查它就即時讀正本；要引用條文原文／數值，回對應的原始檔 alias。"]
    L.append("")
    for alias, r in sorted(repos.items()):
        cards = sorted(sources[k].get("catalog_page", "")
                       for k in sources if k.startswith(f"{alias}::"))
        L += [f"## {alias} — {r.get('desc') or '(無說明)'}", "",
              f"- 註冊：{r.get('registered_at','?')}　最後掃描：{r.get('last_scanned','?')}"]
        if cards:
            L.append("- 已建卡：" + "、".join(
                f"[[{c.removeprefix('wiki/').removesuffix('.md')}]]" for c in cards if c))
        else:
            L.append("- 已建卡：無")
        if not resolve_repo_path(root, r.get("path", "")).exists():
            L.append(f"- 🔴 路徑在本機失效 —— 去找 {(r.get('owner') or {}).get('name','?')}"
                     f"，remote：{(r.get('owner') or {}).get('remote','?')}")
        L += [f"- 查變更：`python \"${{CLAUDE_PLUGIN_ROOT}}/scripts/repo.py\" scan {alias}`", ""]

    p.write_text("\n".join(L), encoding="utf-8")
    return p


def cmd_add(root, args):
    src = Path(args.path).expanduser()
    if not src.is_dir():
        print(f"🔴 路徑不存在或不是資料夾：{src}")
        return 1
    src = src.resolve()

    kind = _detect_wiki(src)
    if kind == "vault-root" and not args.force:
        print(f"🔴  這是一個既有的 wiki vault（偵測到 {src.name}/wiki/index.md），不要整包掛。")
        print("   整包掛會把對方『已編譯的知識層』和『原始正本』混成同一個 alias，")
        print("   scan 分不出哪些該重 ingest、哪些根本不該碰。\n")
        print("   正確做法是分兩個 alias 掛，原始與編譯層各一：\n")
        base = _slug(src.name)
        if (src / "raw").is_dir():
            print(f'     python repo.py add "{src.as_posix()}/raw" --alias {base}-raw '
                  f'--desc "{src.name} 原始正本"')
        print(f'     python repo.py add "{src.as_posix()}/wiki" --alias {base}-wiki '
              f'--desc "{src.name} 已編譯知識層（唯讀，不重 ingest）"')
        print("\n   真的要整包掛：加 --force")
        return 1

    m = load_manifest(root)
    repos = m.setdefault("repos", {})
    alias = args.alias or _slug(src.name)
    if alias in repos:
        print(f"🔴 alias `{alias}` 已存在（指向 {repos[alias].get('path')}）")
        print("   換一個名字：--alias 其他名稱")
        return 1

    is_git = _git(src, "rev-parse", "--is-inside-work-tree") == "true"
    remote = _git(src, "remote", "get-url", "origin") if is_git else None

    entry = {
        # #27：存可攜 spec，不存絕對路徑（換機器／換使用者名稱就全部失效）
        "path": portable_path(root, src),
        "desc": args.desc or "",
        "git": is_git,
        "registered_at": date.today().isoformat(),
        "last_scanned": date.today().isoformat(),
        "exclude": DEFAULT_EXCLUDE,
        # 既有 wiki vault 的知識層 —— 不可 ingest，只能建指標卡路由（#23）
        "kind": kind or "docs",
        # 🔴 擁有者標記：絕對路徑只在這台機器有效，別台必須知道去找誰
        "owner": {
            "name": (_git(src, "config", "user.name") if is_git else None) or "unknown",
            "email": (_git(src, "config", "user.email") if is_git else None) or "",
            "machine": platform.node(),
            "remote": remote or ("僅本機，需向擁有者取得" if is_git else "非 git"),
        },
    }
    repos[alias] = entry
    save_manifest(root, m)
    page = write_repos_page(root)

    files = _candidates(src, set(DEFAULT_EXCLUDE))
    by_ext = {}
    for f in files:
        by_ext[f.suffix.lower()] = by_ext.get(f.suffix.lower(), 0) + 1
    breakdown = " / ".join(f"{k} {v}" for k, v in sorted(by_ext.items(), key=lambda x: -x[1]))

    print(f"✅ 已註冊：{alias}")
    print(f"   路徑：{entry['path']}   （本機：{src}）")
    if is_hardcoded(entry["path"]):
        print(f"   {R} 這條壓不成可攜路徑（多半是跨磁碟機）—— 換機器會失效。")
        print("      建議改用環境變數：手動把 path 改成 ${你的變數}/子路徑，並在兩台機器都設好。")
    print(f"   Git：{'是' if is_git else '否'}　擁有者：{entry['owner']['name']} @ {entry['owner']['machine']}")
    print(f"   Remote：{entry['owner']['remote']}")
    print(f"   可 ingest 候選：{len(files)} 個（{breakdown or '無'}）")
    if page:
        print(f"   總覽已更新：{page.relative_to(root).as_posix()}")
    if kind == "compiled-wiki":
        # 🔴 對方已經編譯過的知識層 —— ingest 它＝同一份知識存兩份，必漂。
        print(f"\n🔴 這是**別人已編譯的知識層**（{len(files)} 份 md），"
              f"**不要 ingest** —— 不論單份或批次。")
        print("   重編一份等於同一份知識存兩處，對方更新時我方不會知道，兩邊無聲漂掉。\n")
        print("   正確做法 —— 建一張 Tier 1 指標卡做路由，不抄內容：")
        print(f"     1. 讀 {alias}::index.md 取得對方的目錄結構")
        print(f"     2. 在 wiki/catalog/ 建卡：記身分／TOC／路徑，frontmatter 標 "
              f"repo: {alias}、tier: 1")
        print("     3. 在本 vault CLAUDE.md『查詢路由』表加一列，指向那張卡")
        print("     4. 查詢時回正本即時讀；要引用條文原文／數值則回原始檔那個 alias，"
              "不可引用編譯層（那是別人的摘要）")
        print(f"\n   看對方有什麼：python repo.py scan {alias}")
    elif len(files) > BATCH_SAFE_MAX:
        print(f"\n🔴 {len(files)} 份候選檔（批次上限 {BATCH_SAFE_MAX}）—— "
              f"**不要**批次 `/wiki-ingest {alias}::`。")
        print("   批次會一口氣建出幾十上百張卡，沒人會逐張檢查，錯的卡比沒有卡更糟。")
        print(f"   按需單份：/wiki-ingest {alias}::{{repo 內路徑}}")
        print(f"   先看有什麼：python repo.py scan {alias}")
    else:
        print(f"\n下一步：/wiki-ingest {alias}::           ← 批次 ingest 整個 repo")
    return 0


def cmd_discover(root, args):
    """掃描一個上層資料夾，列出候選專案供批次註冊。

    給「硬碟上有幾十個專案資料夾」的情境用 —— 一個個 add 太累，
    但整顆硬碟註冊成一個 alias 又會讓 source key 長到無法掃描。
    """
    base = Path(args.path).expanduser()
    if not base.is_dir():
        print(f"🔴 路徑不存在：{base}")
        return 1
    base = base.resolve()

    m = load_manifest(root)
    registered = {resolve_repo_path(root, v.get("path", "")).as_posix().rstrip("/").lower()
                  for k, v in m.get("repos", {}).items() if not k.startswith("_")}
    excludes = set(DEFAULT_EXCLUDE)

    # 本 vault 自己不是「外部 repo」—— manifest 已有 _self，列出來只會誤導
    self_root = str(root.resolve()).replace("\\", "/").lower()

    OFFICE = {".docx", ".doc", ".pdf", ".xlsx", ".pptx"}
    rows = []
    for d, is_dir, depth in _walk(base, excludes, max_depth=args.depth):
        if not is_dir:
            continue
        low = str(d.resolve()).replace("\\", "/").lower()
        if low == self_root or low.startswith(self_root + "/"):
            continue                      # 本 vault 與其子目錄
        files = _candidates(d, excludes)
        if len(files) < args.min_files:
            continue
        office = sum(1 for f in files if f.suffix.lower() in OFFICE)
        if office < args.min_office:
            continue                      # 沒有 Office 檔的資料夾進 wiki 沒有意義
        code = _looks_like_code(d)
        if code and not args.include_code:
            continue                      # source repo，不是文件資料夾
        rows.append((d, len(files), office, depth))

    # 🔴 只保留最淺的命中（父層優先），不是最深。
    # _candidates() 是遞迴計數，父層檔數恆 ≥ 子層 —— 取最深等於保證丟掉「一個專案一層」
    # 的那一列（2026-09-21 驗收：專案根 1040 office 消失、被切成 7 個子 alias）。
    # 顆粒度由 --depth 控制：--depth 1 = 專案層，--depth 2 = 子專案層。
    chosen = []
    paths = {str(d).lower() for d, _, _, _ in rows}
    for d, n, office, depth in rows:
        low = str(d).lower()
        if any(low.startswith(p + "\\") or low.startswith(p + "/")
               for p in paths if p != low):
            continue                      # 祖先已入選 → 不重複列子層
        chosen.append((d, n, office, depth))

    if not chosen:
        print(f"在 {base} 下（深度 ≤{args.depth}）找不到含 ≥{args.min_files} 份文件"
              f"（其中 ≥{args.min_office} 份 Office）的資料夾。")
        print("試試 --depth 3、--min-files 1、--min-office 0，或 --include-code（含程式碼專案）")
        return 0

    chosen.sort(key=lambda x: (-x[2], -x[1]))   # Office 文件多的排前面
    print(f"在 {base} 下找到 {len(chosen)} 個候選（深度 ≤{args.depth}，"
          f"≥{args.min_files} 份、其中 ≥{args.min_office} 份 Office）"
          f"{'' if args.include_code else '，已排除程式碼專案'}：\n")
    print(f"{'狀態':<6} {'種類':<6} {'Office':>6} {'總計':>6}  {'建議 alias':<24} 路徑")
    print("-" * 112)

    taken = set()
    cmds = []
    wikis = 0
    for d, n, office, _ in chosen:
        done = str(d).replace("\\", "/").lower() in registered
        alias = _suggest_alias(d, taken)
        # 既有 wiki vault 不能照一般專案的方式掛（#23）—— 在清單就標出來，
        # 不然使用者會直接複製下面的 add 指令，踩到整包掛。
        kind = _detect_wiki(d)
        mark = {"vault-root": "wiki根", "compiled-wiki": "知識層"}.get(kind, "文件")
        if kind:
            wikis += 1
        print(f"{'已註冊' if done else '  -   ':<6} {mark:<6} {office:>6} {n:>6}  {alias:<24} {d}")
        if not done and not kind:
            cmds.append(f'python repo.py add "{d}" --alias {alias} --desc "{d.name}"')

    if cmds:
        print(f"\n批次註冊指令（{len(cmds)} 條）：\n")
        for c in cmds:
            print(f"  {c}")
        print("\n🔴 不必全部註冊 —— 只註冊你真的會查的專案。Office 欄是 docx/pdf/xlsx/pptx 數量，"
              "通常那才是值得進 wiki 的東西。")
    if wikis:
        print(f"\n🔴 其中 {wikis} 個是既有 wiki vault（種類欄 wiki根／知識層），"
              "沒有產生 add 指令。")
        print("   那種要分兩個 alias 掛（raw 與 wiki 各一），知識層一律不 ingest、改建指標卡。")
        print("   直接對它跑 add 會擋下並印出正確指令。")
    return 0


def cmd_list(root, args):
    m = load_manifest(root)
    repos = {k: v for k, v in m.get("repos", {}).items() if not k.startswith("_")}
    sources = m.get("sources", {})
    if not repos:
        print("尚未註冊任何外部 repo。加入：python repo.py add <路徑>")
        return 0

    if backfill_paths(root, m) | backfill_kinds(root, m):
        save_manifest(root, m)            # #26 / #27
    KIND = {"compiled-wiki": "知識層", "vault-root": "wiki根", "docs": "文件"}
    print(f"{'alias':<16} {'種類':<6} {'卡':>4}  {'狀態':<6} {'擁有者':<12} 路徑")
    print("-" * 100)
    bad, hard = [], []
    for alias, r in sorted(repos.items()):
        n = sum(1 for k in sources if k.startswith(f"{alias}::"))
        alive = resolve_repo_path(root, r.get("path", "")).exists()
        owner = (r.get("owner") or {}).get("name", "?")
        k = r.get("kind", "docs")
        print(f"{alias:<16} {KIND.get(k, '文件'):<6} {n:>4}  {'✅ 在' if alive else '🔴 失效':<6} "
              f"{owner:<12} {r.get('path','')}")
        if r.get("desc"):
            print(f"{'':<16}              {r['desc']}")
        if not alive:
            print(f"{'':<16}              ↳ remote: {(r.get('owner') or {}).get('remote','?')}")
        if k == "vault-root":
            bad.append(alias)
        if is_hardcoded(r.get("path", "")):
            hard.append(alias)
    if bad:
        print(f"\n🔴 {'、'.join(bad)} 是整包掛進來的 wiki vault —— "
              "原始正本與對方已編譯的知識層混在同一個 alias。")
        print("   拆成兩個：remove 後分別 add <路徑>/raw 與 <路徑>/wiki（知識層只建指標卡，不 ingest）。")
    if hard:
        print(f"\n🔴 {'、'.join(hard)} 存的是絕對路徑，換機器會失效。"
              "改成 ${你的變數}/子路徑，兩台機器都設好那個環境變數。")
    return 0


def cmd_scan(root, args):
    m = load_manifest(root)
    repos = {k: v for k, v in m.get("repos", {}).items() if not k.startswith("_")}
    if args.alias:
        repos = {k: v for k, v in repos.items() if k == args.alias}
        if not repos:
            print(f"🔴 repo `{args.alias}` 未註冊")
            return 1
    sources = m.get("sources", {})
    rc = 0

    for alias, r in sorted(repos.items()):
        base = resolve_repo_path(root, r.get("path", ""))
        print(f"\n### {alias} — {r.get('desc') or '(無說明)'}")
        if not base.exists():
            owner = r.get("owner") or {}
            print(f"🔴 路徑失效：{base}")
            print(f"   這條路徑屬於 {owner.get('name','?')} @ {owner.get('machine','?')}")
            print(f"   remote：{owner.get('remote','?')}")
            print("   （不自動移除註冊 —— 可能只是換了機器）")
            rc = 1
            continue

        excludes = set(r.get("exclude") or DEFAULT_EXCLUDE)
        found = {str(p.relative_to(base)).replace("\\", "/") for p in _candidates(base, excludes)}
        known = {k.split("::", 1)[1]: v for k, v in sources.items() if k.startswith(f"{alias}::")}

        new = sorted(found - set(known))
        gone = sorted(set(known) - found)
        changed = []
        for rel, meta in known.items():
            if rel in found and meta.get("hash"):
                h = _md5(base / rel)
                if h and h != meta["hash"]:
                    changed.append(rel)

        if changed:
            print(f"🟡 變更 {len(changed)} 個（hash 不同，wiki 可能已過期）：")
            for x in changed[:10]:
                print(f"   ~ {x}")
        if new:
            print(f"🔵 新增 {len(new)} 個（未 ingest）：")
            for x in new[:10]:
                print(f"   + {x}")
            if len(new) > 10:
                print(f"   … 另有 {len(new)-10} 個")
        if gone:
            print(f"🔴 消失 {len(gone)} 個（manifest 有紀錄但檔案不在）：")
            for x in gone[:10]:
                print(f"   - {x}")
        if not (changed or new or gone):
            print("🟢 無變更")

        r["last_scanned"] = date.today().isoformat()

    save_manifest(root, m)
    write_repos_page(root)
    print("\n（只回報，不自動 ingest。要處理變更：/wiki-ingest {alias}::{路徑}）")
    return rc


def dangling_repos_refs(root):
    """`wiki/repos.md` 不在時，找出還連向它的 wiki 頁。

    刪衍生頁是刻意的（見 write_repos_page），但 hot.md／index.md 常留著 [[repos]]，
    刪完就變死連結，Obsidian 不會報錯、只會靜靜壞掉（2026-09-21 驗收 #14）。
    """
    wiki = root / "wiki"
    if not wiki.is_dir():
        return []
    pat = re.compile(r"\[\[repos(?=[|#\]])")
    out = []
    for f in sorted(wiki.rglob("*.md")):
        try:
            if pat.search(f.read_text(encoding="utf-8")):
                out.append(f.relative_to(root).as_posix())
        except OSError:
            pass
    return out


def cmd_remove(root, args):
    m = load_manifest(root)
    repos = m.get("repos", {})
    if args.alias not in repos:
        print(f"🔴 repo `{args.alias}` 未註冊")
        return 1
    n = sum(1 for k in m.get("sources", {}) if k.startswith(f"{args.alias}::"))
    if n and not args.force:
        print(f"⚠️ `{args.alias}` 有 {n} 筆 ingest 紀錄，移除後這些 catalog 卡會指向失效來源。")
        print("   確定要移除 → 加 --force（只移除 repos 條目，保留 sources 與 catalog 卡）")
        return 1
    repos.pop(args.alias)
    save_manifest(root, m)
    write_repos_page(root)
    print(f"✅ 已移除 repo `{args.alias}`（保留 {n} 筆 sources 紀錄與 catalog 卡）")
    if not (root / "wiki" / "repos.md").exists():
        refs = dangling_repos_refs(root)
        if refs:
            print("🟡 最後一個外部 repo 已移除 → `wiki/repos.md` 一併刪除，"
                  "下列頁面的 [[repos]] 變成死連結，請清掉：")
            for f in refs:
                print(f"   · {f}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="多 repo 來源管理")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add"); a.add_argument("path"); a.add_argument("--alias"); a.add_argument("--desc", default="")
    a.add_argument("--force", action="store_true",
                   help="目標是既有 wiki vault 時仍整包掛（預設擋下，改建議分兩個 alias）")
    sub.add_parser("list")
    s = sub.add_parser("scan"); s.add_argument("alias", nargs="?")
    r = sub.add_parser("remove"); r.add_argument("alias"); r.add_argument("--force", action="store_true")
    d = sub.add_parser("discover", help="掃描上層資料夾，列出候選專案供批次註冊")
    d.add_argument("path")
    d.add_argument("--depth", type=int, default=2, help="往下找幾層（預設 2）")
    d.add_argument("--min-files", type=int, default=3, dest="min_files",
                   help="至少幾份文件才算候選（預設 3）")
    d.add_argument("--min-office", type=int, default=1, dest="min_office",
                   help="至少幾份 Office 檔（docx/pdf/xlsx/pptx）才算候選（預設 1，設 0 不過濾）")
    d.add_argument("--include-code", action="store_true", dest="include_code",
                   help="連程式碼專案也列（預設排除 package.json/CMakeLists 那類）")

    args = ap.parse_args()
    root = find_vault_root(Path.cwd())
    if root is None:
        print("🔴 找不到 vault（往上找不到含 wiki/ 或 raw/.manifest.json 的目錄）")
        return 1
    return {"add": cmd_add, "list": cmd_list, "scan": cmd_scan,
            "remove": cmd_remove, "discover": cmd_discover}[args.cmd](root, args)


if __name__ == "__main__":
    sys.exit(main())
