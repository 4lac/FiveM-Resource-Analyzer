#!/usr/bin/env python3
"""
REYOF // FIVEM RESOURCE ANALYZER
Finds functions that are duplicated / similar across different files.
Requires Python 3.10+

------------------------------------------------------------
USAGE
------------------------------------------------------------

Linux / Linux Mint (bash):
    python3 fivem_analyzer.py "/path/to/resources"
    cd "/path/to/resources" && python3 /path/to/fivem_analyzer.py

WSL (Windows drives live under /mnt/c):
    python3 /mnt/c/Users/PC/Downloads/fivem_analyzer.py "/mnt/c/Users/PC/OneDrive/Desktop/New folder (3)/medical-dna"

    # optional: install as a global command
    mkdir -p ~/bin
    cp /mnt/c/Users/PC/Downloads/fivem_analyzer.py ~/bin/fivem-analyzer
    chmod +x ~/bin/fivem-analyzer
    echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
    fivem-analyzer .

Windows PowerShell:
    python .\\fivem_analyzer.py "C:\\Users\\PC\\OneDrive\\Desktop\\New folder (3)\\medical-dna"
    py .\\fivem_analyzer.py .          # if `python` isn't on PATH

Windows CMD:
    python fivem_analyzer.py "C:\\Users\\PC\\OneDrive\\Desktop\\New folder (3)\\medical-dna"
    py fivem_analyzer.py .

macOS (zsh):
    python3 fivem_analyzer.py "/path/to/resources"

------------------------------------------------------------
OPTIONS
------------------------------------------------------------
    path                 folder to scan, recursively (default: current folder)
    -o, --output FILE    report path (default: <folder>/similar_functions_report.txt)
    --threshold 0.70     similarity threshold (0-1)
    --min-tokens 20      ignore tiny functions (fewer tokens than this)
    --no-color           plain output (no ANSI colors)

Example:
    python3 fivem_analyzer.py . --threshold 0.8 -o report.txt
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

HEADER = r"""
██████╗ ███████╗██╗   ██╗ ██████╗ ███████╗
██╔══██╗██╔════╝╚██╗ ██╔╝██╔═══██╗██╔════╝
██████╔╝█████╗   ╚████╔╝ ██║   ██║█████╗
██╔══██╗██╔══╝    ╚██╔╝  ██║   ██║██╔══╝
██║  ██║███████╗   ██║   ╚██████╔╝███████╗
╚═╝  ╚═╝╚══════╝   ╚═╝    ╚═════╝ ╚══════╝

             FIVEM RESOURCE ANALYZER
"""

IGNORE_DIRS = {".git", ".idea", ".vscode", "node_modules", "cache", "dist", "build"}

LUA_KEYWORDS = {
    "and", "break", "do", "else", "elseif", "end", "false", "for", "function",
    "goto", "if", "in", "local", "nil", "not", "or", "repeat", "return", "then",
    "true", "until", "while",
}
# for/while are closed by the `do` they contain, so only `do` opens a block.
BLOCK_OPEN = {"function", "if", "do", "repeat"}
BLOCK_CLOSE = {"end", "until"}

REGISTER_CALLS = {
    "RegisterNetEvent", "RegisterServerEvent", "AddEventHandler", "RegisterNUICallback",
    "RegisterCommand", "lib.callback.register", "QBCore.Functions.CreateCallback",
    "ESX.RegisterServerCallback",
}
TRIGGER_CALLS = {
    "TriggerServerEvent", "TriggerLatentServerEvent", "TriggerClientEvent",
    "TriggerLatentClientEvent", "TriggerEvent", "lib.callback", "lib.callback.await",
    "QBCore.Functions.TriggerCallback", "ESX.TriggerServerCallback",
}


# ============================================================
# COLORS / OUTPUT
# ============================================================

class C:
    RESET = "\033[0m"
    PINK = "\033[1;38;2;255;105;180m"
    RED, GREEN, YELLOW = "\033[91m", "\033[92m", "\033[93m"
    CYAN, MAGENTA, BLUE = "\033[96m", "\033[95m", "\033[94m"
    GRAY, WHITE = "\033[90m", "\033[97m"


USE_COLOR = True


def paint(text: str, code: str | None) -> str:
    return f"{code}{text}{C.RESET}" if USE_COLOR and code else text


class Out:
    """Collects lines once: printed with colors, saved to the report without."""

    def __init__(self):
        self.lines: list[tuple[str, str | None]] = []

    def add(self, text: str = "", code: str | None = None):
        self.lines.append((text, code))

    def flush(self):
        for text, code in self.lines:
            print(paint(text, code))

    def write(self, path: Path):
        path.write_text("\n".join(t for t, _ in self.lines) + "\n", encoding="utf-8")


# ============================================================
# TOKENIZER  (strings, long strings and all comment forms)
# ============================================================

NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
NUM_RE = re.compile(
    r"0[xX][0-9a-fA-F]*(?:\.[0-9a-fA-F]*)?(?:[pP][+-]?\d+)?|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
)
LONG_OPEN = re.compile(r"\[(=*)\[")
TWO_CHAR_OPS = {"==", "~=", "<=", ">=", "..", "::", "//", "<<", ">>"}


@dataclass(slots=True)
class Tok:
    kind: str  # name | kw | str | num | op
    val: str
    line: int


def _long_close(src: str, start: int, eq: str) -> tuple[int, int]:
    close = "]" + eq + "]"
    j = src.find(close, start)
    return (len(src), len(src)) if j == -1 else (j, j + len(close))


def tokenize(src: str) -> list[Tok]:
    toks: list[Tok] = []
    i, n, line = 0, len(src), 1

    while i < n:
        c = src[i]

        if c == "\n":
            line += 1
            i += 1
            continue
        if c.isspace():
            i += 1
            continue

        if src.startswith("--", i):  # comment
            m = LONG_OPEN.match(src, i + 2)
            if m:
                _, j = _long_close(src, m.end(), m.group(1))
            else:
                j = src.find("\n", i)
                j = n if j == -1 else j
            line += src.count("\n", i, j)
            i = j
            continue

        m = LONG_OPEN.match(src, i)  # [[ long string ]]
        if m:
            content_end, j = _long_close(src, m.end(), m.group(1))
            toks.append(Tok("str", src[m.end():content_end], line))
            line += src.count("\n", i, j)
            i = j
            continue

        if c in "'\"":
            j = i + 1
            while j < n and src[j] != c and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            j = min(j, n)
            toks.append(Tok("str", src[i + 1:j], line))
            line += src.count("\n", i, j)
            i = j + 1 if j < n and src[j] == c else j
            continue

        m = NAME_RE.match(src, i)
        if m:
            word = m.group(0)
            toks.append(Tok("kw" if word in LUA_KEYWORDS else "name", word, line))
            i = m.end()
            continue

        if "0" <= c <= "9" or (c == "." and i + 1 < n and "0" <= src[i + 1] <= "9"):
            m = NUM_RE.match(src, i)
            toks.append(Tok("num", m.group(0), line))
            i = m.end()
            continue

        if src.startswith("...", i):
            op = "..."
        elif src[i:i + 2] in TWO_CHAR_OPS:
            op = src[i:i + 2]
        else:
            op = c
        toks.append(Tok("op", op, line))
        i += len(op)

    return toks


# ============================================================
# TOKEN HELPERS
# ============================================================

def is_op(toks, i, val) -> bool:
    return 0 <= i < len(toks) and toks[i].kind == "op" and toks[i].val == val


def is_kw(toks, i, val) -> bool:
    return 0 <= i < len(toks) and toks[i].kind == "kw" and toks[i].val == val


def chain_before(toks, k) -> tuple[str | None, int]:
    """Dotted/colon name ending right before index k, e.g. lib.callback.register."""
    j = k - 1
    if j < 0 or toks[j].kind != "name":
        return None, k
    parts = [toks[j].val]
    while j - 2 >= 0 and toks[j - 1].kind == "op" and toks[j - 1].val in (".", ":") \
            and toks[j - 2].kind == "name":
        parts += [toks[j - 1].val, toks[j - 2].val]
        j -= 2
    return "".join(reversed(parts)), j


def enclosing_bracket(toks, k, limit=600):
    """Innermost unclosed bracket before k -> (bracket, callee, first_string_arg)."""
    depth = 0
    for j in range(k - 1, max(-1, k - limit), -1):
        if toks[j].kind != "op":
            continue
        v = toks[j].val
        if v in (")", "]", "}"):
            depth += 1
        elif v in ("(", "[", "{"):
            if depth:
                depth -= 1
                continue
            if v != "(":
                return v, None, None
            callee, _ = chain_before(toks, j)
            arg = toks[j + 1].val if j + 1 < len(toks) and toks[j + 1].kind == "str" else None
            return v, callee, arg
    return None, None, None


def block_end(toks, k) -> int:
    depth = 0
    for idx in range(k, len(toks)):
        t = toks[idx]
        if t.kind == "kw":
            if t.val in BLOCK_OPEN:
                depth += 1
            elif t.val in BLOCK_CLOSE:
                depth -= 1
                if depth == 0:
                    return idx
    return len(toks) - 1


def short(name: str) -> str:
    return re.split(r"[.:]", name)[-1]


# ============================================================
# MODEL
# ============================================================

@dataclass
class Site:
    """A place where something is called or an event is fired."""
    what: str
    file: Path
    line: int
    call: str = ""


@dataclass
class Func:
    name: str
    file: Path
    start: int
    end: int
    tokens: list[str]
    hash: str
    is_local: bool = False
    is_named: bool = False
    handles: str | None = None        # e.g. "medical-dna:server:treat (RegisterNetEvent)"
    handles_event: str | None = None
    calls: list[str] = field(default_factory=list)
    fires: list[Site] = field(default_factory=list)


# ============================================================
# EXTRACTION
# ============================================================

def extract(toks, file) -> tuple[list[Func], list[Site], list[Site]]:
    """Returns (functions, call sites, event trigger sites) for one file."""
    funcs: list[Func] = []
    call_sites: list[Site] = []
    fire_sites: list[Site] = []

    for idx, t in enumerate(toks):
        if is_op(toks, idx, "("):
            chain, cstart = chain_before(toks, idx)
            if chain and not is_kw(toks, cstart - 1, "function"):
                call_sites.append(Site(chain, file, t.line))
                if chain in TRIGGER_CALLS and idx + 1 < len(toks) and toks[idx + 1].kind == "str":
                    fire_sites.append(Site(toks[idx + 1].val, file, t.line, chain))

    for k, t in enumerate(toks):
        if not (t.kind == "kw" and t.val == "function"):
            continue

        is_local = is_kw(toks, k - 1, "local")
        named, name, handles, handles_event = False, None, None, None

        if k + 1 < len(toks) and toks[k + 1].kind == "name":
            parts, p = [toks[k + 1].val], k + 2
            while p + 1 < len(toks) and toks[p].kind == "op" and toks[p].val in (".", ":") \
                    and toks[p + 1].kind == "name":
                parts += [toks[p].val, toks[p + 1].val]
                p += 2
            name, named = "".join(parts), True
        else:
            p = k + 1
            bracket, callee, arg = enclosing_bracket(toks, k)
            if is_op(toks, k - 1, "="):
                chain, cstart = chain_before(toks, k - 1)
                if chain and bracket == "{":
                    name = "{" + chain + "}"
                elif chain:
                    name, named = chain, True
                    is_local = is_kw(toks, cstart - 1, "local")
            elif bracket == "(" and callee:
                name = f"{callee}('{arg}')" if arg else f"{callee}(…)"
                if arg and callee in REGISTER_CALLS:
                    handles, handles_event = f"{arg}  ({callee})", arg
            name = name or "<anonymous>"

        end = block_end(toks, k)
        body = toks[p:end + 1]
        tokens = [f'"{x.val}"' if x.kind == "str" else x.val for x in body]
        start_line, end_line = t.line, toks[end].line

        func = Func(
            name=name, file=file, start=start_line, end=end_line, tokens=tokens,
            hash=hashlib.sha256(" ".join(tokens).encode()).hexdigest(),
            is_local=is_local, is_named=named, handles=handles, handles_event=handles_event,
        )
        func.calls = [s.what for s in call_sites
                      if start_line <= s.line <= end_line and s.what != name]
        func.fires = [s for s in fire_sites if start_line <= s.line <= end_line]
        funcs.append(func)

    return funcs, call_sites, fire_sites


def find_lua_files(root: Path) -> list[Path]:
    """Walks the folder and every sub-folder inside it."""
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() == ".lua"
        and not any(part in IGNORE_DIRS for part in p.relative_to(root).parts)
    )


# ============================================================
# SIMILARITY  (groups copies that live in different files)
# ============================================================

def ratio(a: Func, b: Func) -> float:
    if a.hash == b.hash:
        return 1.0
    return SequenceMatcher(None, a.tokens, b.tokens, autojunk=False).ratio()


def find_groups(funcs: list[Func], threshold: float, min_tokens: int) -> list[list[Func]]:
    pool = [f for f in funcs if len(f.tokens) >= min_tokens]
    parent = list(range(len(pool)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    # 1) identical bodies
    by_hash = defaultdict(list)
    for i, f in enumerate(pool):
        by_hash[f.hash].append(i)
    for idxs in by_hash.values():
        for i in idxs[1:]:
            union(idxs[0], i)

    # 2) similar bodies (sorted by size so we stop early when lengths drift too far)
    order = sorted(range(len(pool)), key=lambda i: len(pool[i].tokens))
    max_growth = (2 - threshold) / threshold
    for pos, i in enumerate(order):
        a = pool[i]
        for j in order[pos + 1:]:
            b = pool[j]
            if len(b.tokens) > len(a.tokens) * max_growth:
                break
            if a.file == b.file or find(i) == find(j):
                continue
            sm = SequenceMatcher(None, a.tokens, b.tokens, autojunk=False)
            if sm.real_quick_ratio() >= threshold and sm.quick_ratio() >= threshold \
                    and sm.ratio() >= threshold:
                union(i, j)

    clusters = defaultdict(list)
    for i, f in enumerate(pool):
        clusters[find(i)].append(f)

    def ordered(g):
        count = defaultdict(int)
        for f in g:
            count[f.hash] += 1
        return sorted(g, key=lambda f: (-count[f.hash], str(f.file), f.start))

    groups = [
        ordered(g)
        for g in clusters.values()
        if len({f.file for f in g}) > 1  # must appear in more than one file
    ]
    return sorted(groups, key=lambda g: (-len(g), str(g[0].file), g[0].start))


# ============================================================
# LINKS  (what each similar function is connected to)
# ============================================================

def callers_of(f: Func, call_sites: list[Site]) -> list[Site]:
    if not f.is_named:
        return []
    result = []
    for s in call_sites:
        if f.is_local and s.file != f.file:
            continue
        if s.file == f.file and f.start <= s.line <= f.end:
            continue  # inside itself
        if s.what == f.name or (":" in f.name and ":" in s.what and short(s.what) == short(f.name)):
            result.append(s)
    return result


def links_of(f: Func, known: set[str], call_sites: list[Site], fire_sites: list[Site]):
    called_by = callers_of(f, call_sites)
    triggered_from = [s for s in fire_sites if f.handles_event and s.what == f.handles_event]
    calls = sorted({c for c in f.calls if c in known or short(c) in known})
    uses = sorted({c.split(".", 1)[1] for c in f.calls if c.startswith("exports.")})
    fires = sorted({f"{s.call} → {s.what}" for s in f.fires})
    return called_by, triggered_from, calls, uses, fires


def fmt_sites(sites: list[Site], limit=6) -> str:
    text = ", ".join(f"{s.file}:{s.line}" for s in sites[:limit])
    return text + (f"  (+{len(sites) - limit} more)" if len(sites) > limit else "")


# ============================================================
# REPORT
# ============================================================

def report(out, root, groups, known, call_sites, fire_sites):
    for n, group in enumerate(groups, start=1):
        rep = group[0]
        files = len({f.file for f in group})
        identical = len({f.hash for f in group}) == 1
        label = "100% identical" if identical else "similar"

        out.add("═" * 64, C.MAGENTA)
        out.add(f"[{n}] {len(group)} copies in {files} files  ·  {label}", C.MAGENTA)
        out.add("═" * 64, C.MAGENTA)

        for i, f in enumerate(group, start=1):
            out.add(f"  ({i}) {f.name}", C.YELLOW)
            out.add(f"      📁 Folder : {f.file.parent}")
            out.add(f"      📄 File   : {f.file.name}   (lines {f.start} → {f.end})")
            out.add(f"      📍 Path   : {f.file}:{f.start}", C.CYAN)
            if i > 1:
                score = ratio(rep, f)
                text = "100% identical to (1)" if score == 1.0 else f"{score * 100:.1f}% similar to (1)"
                out.add(f"      🧬 {text}", C.MAGENTA)

            called_by, triggered_from, calls, uses, fires = links_of(f, known, call_sites, fire_sites)
            linked = False
            if f.handles:
                out.add(f"      🎯 Handles event : {f.handles}", C.GREEN)
                linked = True
            if triggered_from:
                out.add(f"      ⚡ Fired from    : {fmt_sites(triggered_from)}", C.GREEN)
                linked = True
            if called_by:
                out.add(f"      🔗 Called from   : {fmt_sites(called_by)}", C.GREEN)
                linked = True
            if calls:
                out.add(f"      ➡  Calls         : {', '.join(c + '()' for c in calls)}", C.BLUE)
                linked = True
            if fires:
                out.add(f"      ⚡ Fires events  : {', '.join(fires)}", C.BLUE)
                linked = True
            if uses:
                out.add(f"      📦 Uses exports  : {', '.join(uses)}", C.BLUE)
                linked = True
            if not linked:
                out.add("      ○ Not linked to anything (possibly unused)", C.GRAY)
            out.add()


# ============================================================
# MAIN
# ============================================================

def main():
    global USE_COLOR

    ap = argparse.ArgumentParser(description="Find similar functions across FiveM Lua files")
    ap.add_argument("path", nargs="?", default=".", help="folder to scan (default: current folder)")
    ap.add_argument("-o", "--output", help="report path")
    ap.add_argument("--threshold", type=float, default=0.70, help="similarity threshold (0-1)")
    ap.add_argument("--min-tokens", type=int, default=20, help="ignore tiny functions")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if os.name == "nt":
        os.system("")  # enables ANSI colors on Windows consoles
    USE_COLOR = not args.no_color and sys.stdout.isatty() and "NO_COLOR" not in os.environ

    print(paint(HEADER, C.PINK))

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(paint(f"[ERROR] Not a folder: {root}", C.RED))
        sys.exit(1)

    print(paint(f"[ SCANNING ] {root}", C.CYAN))
    files = find_lua_files(root)

    funcs: list[Func] = []
    call_sites: list[Site] = []
    fire_sites: list[Site] = []

    for file in files:
        try:
            src = file.read_text(encoding="utf-8", errors="ignore")
        except OSError as error:
            print(paint(f"[ERROR] {file}: {error}", C.RED))
            continue
        rel = Path(root.name) / file.relative_to(root)  # e.g. medical-dna/client/main.lua
        f, c, e = extract(tokenize(src), rel)
        funcs += f
        call_sites += c
        fire_sites += e

    known = {f.name for f in funcs if f.is_named} | {short(f.name) for f in funcs if f.is_named}
    groups = find_groups(funcs, args.threshold, args.min_tokens)

    out = Out()
    folders = len({f.parent for f in files})
    out.add(f"Folders scanned : {folders}", C.WHITE)
    out.add(f"Lua files       : {len(files)}", C.WHITE)
    out.add(f"Functions       : {len(funcs)}", C.WHITE)
    out.add()

    if groups:
        report(out, root, groups, known, call_sites, fire_sites)
        copies = sum(len(g) for g in groups)
        out.add(f"Similar groups: {len(groups)}  ({copies} functions involved)", C.YELLOW)
    else:
        out.add("✓ No similar functions across files.", C.GREEN)

    out.flush()

    report_path = Path(args.output).resolve() if args.output else root / "similar_functions_report.txt"
    out.write(report_path)
    print()
    print(paint(f"[ REPORT ] {report_path}", C.CYAN))


if __name__ == "__main__":
    main()
