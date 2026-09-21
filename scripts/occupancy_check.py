#!/usr/bin/env python3
"""occupancy_check —— 檔案佔用違規偵測（防無聲覆蓋）

xlsx／docx 不會提示衝突，後存檔的無聲覆蓋先存檔的，雙方都不會發現。
`wiki/meta/coordination.md` 的「# 檔案佔用」表登記誰持有哪個檔，
本腳本把它跟 git author 機械比對，不做語意判斷、不改任何檔案。

  O1 佔用違規   起始日期後，有「非佔用者」的 author 動過該檔
  O2 解析失敗   檔案欄撈不出磁碟上的路徑，或起始欄沒有日期
  O3 佔用者不明 佔用者欄認不出持有者（session 名稱／🔒 凍結／使用者）

持有者三類：
  session 名稱   佔用者欄內的英數 token 都算合法持有者（author 含該 token 即合法）
  🔒 凍結        任何 author 出現即違規
  使用者          永遠合法，不比對 author；仍列出標「未檢查」

自動備份的 author（obsidian-git 之類）在 raw/.manifest.json 設定：
  "config": { "occupancy_ignore_authors": ["<帳號>"] }

用法：
  python occupancy_check.py            # 完整報告
  python occupancy_check.py --quiet    # 只印 verdict
  python occupancy_check.py <路徑>     # 指定替代的 coordination.md（測試用）

只在收尾跑。exit code 一律 0 —— 提醒不是閘門。
"""
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib.vaultpaths import find_vault_root, load_manifest  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

COORD_REL = "wiki/meta/coordination.md"
MAX_MATCHES = 8

SECTION = re.compile(r"^#{1,3}\s*檔案佔用\s*$")
NEXT_SECTION = re.compile(r"^#{1,3}\s+")
BACKTICK = re.compile(r"`([^`\n]+)`")
EXT = re.compile(r"\.[A-Za-z0-9]{1,6}$")
TOKEN = re.compile(r"[A-Za-z][\w.-]{1,}")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
FROZEN = re.compile(r"凍結|不得動|frozen", re.I)
USER_HELD = re.compile(r"使用者|👤")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".obsidian", ".trash"}


def read_rows(text):
    """「# 檔案佔用」表的資料列 → [(行號, 檔案, 佔用者, 起始)]。"""
    rows, inside = [], False
    for ln, line in enumerate(text.splitlines(), 1):
        if SECTION.match(line):
            inside = True
            continue
        if inside and NEXT_SECTION.match(line):
            break
        if not inside or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0] == "檔案" or set(cells[0]) <= set("-: "):
            continue
        rows.append((ln, cells[0], cells[1], cells[2]))
    return rows


def all_files(root):
    for p in root.rglob("*"):
        if p.is_file() and not any(part in SKIP_DIRS for part in p.parts):
            yield p.relative_to(root).as_posix()


def fragments(cell):
    """檔案欄 → 必須依序出現在路徑裡的片段。優先反引號，其次整欄。"""
    frags = [t.strip() for t in BACKTICK.findall(cell)]
    frags = [t for t in frags if "/" in t or EXT.search(t)]
    if not frags:
        bare = re.split(r"[（(]", cell, 1)[0].strip()
        if "/" in bare or EXT.search(bare):
            frags = [bare]
    out = []
    for f in frags:
        out += [p.strip("/ ") for p in f.split("…") if p.strip("/ ")]
    return out


def matches(path, frag):
    """人寫的路徑常是簡寫：各段依序出現即可，不要求逐字相連。"""
    pos = 0
    for seg in frag.split("/"):
        seg = seg.strip()
        if not seg:
            continue
        i = path.find(seg, pos)
        if i < 0:
            return False
        pos = i + len(seg)
    return True


def resolve(root, cell, files):
    frags = fragments(cell)
    if not frags:
        return [], frags
    direct = [f for f in frags if (root / f).is_file()]
    if direct:
        return direct, frags
    return [f for f in files() if all(matches(f, x) for x in frags)], frags


def holder_tokens(cell):
    toks = set(BACKTICK.findall(cell))
    toks |= set(TOKEN.findall(cell))
    return {t.strip().lower() for t in toks if len(t.strip()) >= 2}


def is_holder(author, holders):
    a = author.lower()
    return any(t == a or t in a or a in t for t in holders)


def authors_since(root, path, since, ignored):
    try:
        out = subprocess.run(
            ["git", "log", f"--since={since}", "--format=%an%x1f%h%x1f%s", "--", path],
            cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    hits = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3 and parts[0] not in ignored:
            hits.append(tuple(parts))
    return hits


def main():
    quiet = "--quiet" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    start = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    root = find_vault_root(Path(start))
    if root is None:
        print("找不到 vault（往上找不到含 wiki/ 或 raw/.manifest.json 的目錄）")
        return 0
    coord = Path(args[0]).resolve() if args else root / COORD_REL
    if not coord.is_file():
        print(f"沒有 {COORD_REL} —— 本 vault 尚未啟用主管制，略過佔用檢查")
        return 0

    ignored = set(load_manifest(root).get("config", {}).get("occupancy_ignore_authors", []))
    rows = read_rows(coord.read_text(encoding="utf-8"))
    if not rows:
        print(f"{COORD_REL} 存在但「檔案佔用」表 0 列 —— 主管制已建骨架、目前無人登記佔用，略過")
        return 0
    cache = []

    def files():
        if not cache:
            cache.extend(all_files(root))
        return cache

    violations, unresolved, unknown, user_held, checked = [], [], [], [], 0

    for ln, fcell, hcell, scell in rows:
        paths, frags = resolve(root, fcell, files)
        if not paths:
            unresolved.append((ln, fcell, frags, "撈不到符合的檔案"))
            continue
        if len(paths) > MAX_MATCHES:
            unresolved.append((ln, fcell, frags, f"過於模糊（命中 {len(paths)} 個檔）"))
            continue
        frozen = bool(FROZEN.search(hcell))
        holders = set() if frozen else holder_tokens(hcell)
        if not frozen and USER_HELD.search(hcell):
            user_held.append((ln, fcell, hcell[:40]))
            continue
        if not frozen and not holders:
            unknown.append((ln, fcell, hcell[:40]))
            continue
        m = DATE.search(scell)
        if not m:
            unresolved.append((ln, fcell, frags, "起始欄無 YYYY-MM-DD"))
            continue
        since = m.group(0)
        for path in paths:
            hits = authors_since(root, path, since, ignored)
            if hits is None:
                print("git 不可用，無法比對 author")
                return 0
            checked += 1
            for an, sha, subj in hits:
                if not frozen and is_holder(an, holders):
                    continue
                violations.append((path, hcell, frozen, an, sha, subj, since))

    total = len(violations) + len(unresolved) + len(unknown)

    if not quiet:
        print(f"=== occupancy_check: {coord.name}（{len(rows)} 列登記、{checked} 個檔實查）===\n")
        for path, hcell, frozen, an, sha, subj, since in violations:
            tag = "🔒 凍結中仍被修改" if frozen else "佔用違規"
            print(f"🟡 WARN  [O1] {tag}：{path}")
            print(f"        佔用者：{hcell[:60]}")
            print(f"        實際動的人：{an}　{sha}  {subj[:60]}（起算 {since}）")
        for ln, fcell, frags, why in unresolved:
            print(f"🟡 WARN  [O2] 佔用表 L{ln} 無法解析：{why}")
            print(f"        檔案欄：{fcell[:70]}　片段：{frags}")
        for ln, fcell, hcell in user_held:
            print(f"👤 使用者持有（未檢查）：{fcell[:60]}")
        for ln, fcell, hcell in unknown:
            print(f"🟡 WARN  [O3] 佔用表 L{ln} 佔用者不明（無名稱、未標凍結）：{fcell[:50]}　佔用者欄：{hcell}")
        print("\n" + "-" * 60)

    ign = f"（已排除 {'／'.join(sorted(ignored))}）" if ignored else ""
    if total == 0:
        note = f"，另 {len(user_held)} 列使用者持有未檢查" if user_held else ""
        print(f"verdict : 🟢 CLEAN —— {checked} 個檔無佔用違規{note}{ign}")
    else:
        print(f"verdict : 🟡 {total} 項（違規 {len(violations)}／無法解析 {len(unresolved)}／"
              f"佔用者不明 {len(unknown)}）{ign} —— 提醒不是閘門；違規請回報主管，不要自行改 coordination.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
