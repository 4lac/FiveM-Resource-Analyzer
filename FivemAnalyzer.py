#!/usr/bin/env python3
"""REYOF // FIVEM RESOURCE ANALYZER"""
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

NET_REGISTER = {"RegisterNetEvent", "RegisterServerEvent"}
CALLBACK_REGISTER = {
    "lib.callback.register", "QBCore.Functions.CreateCallback", "ESX.RegisterServerCallback",
}
REGISTER_CALLS = NET_REGISTER | CALLBACK_REGISTER | {"AddEventHandler", "RegisterNUICallback"}
TRIGGER_CALLS = {
    "TriggerServerEvent", "TriggerLatentServerEvent", "TriggerClientEvent",
    "TriggerLatentClientEvent", "TriggerEvent", "lib.callback", "lib.callback.await",
    "QBCore.Functions.TriggerCallback", "ESX.TriggerServerCallback",
}
SENSITIVE_CALL = re.compile(
    r"AddItem|RemoveItem|AddMoney|RemoveMoney|SetMoney|AccountMoney|SetJob|"
    r"ExecuteCommand|DropPlayer|SetPlayerRoutingBucket|GiveWeapon|MySQL|oxmysql",
    re.I,
)


# ============================================================
# TERMINAL / OUTPUT
# ============================================================

class C:
    RESET, RED, GREEN, YELLOW = "\033[0m", "\033[91m", "\033[92m", "\033[93m"
    CYAN, MAGENTA, BLUE, GRAY, WHITE = "\033[96m", "\033[95m", "\033[94m", "\033[90m", "\033[97m"
    PINK = "\033[1;38;2;255;105;180m"  # hot pink


USE_COLOR = True


def paint(text: str, code: str | None) -> str:
    return f"{code}{text}{C.RESET}" if USE_COLOR and code else text


class Out:
    """Collects lines once, then prints them (colored) and writes them (plain)."""

    def __init__(self):
        self.lines: list[tuple[str, str | None]] = []

    def add(self, text: str = "", code: str | None = None):
        self.lines.append((text, code))

    def section(self, title: str, code: str):
        self.add("─" * 60, C.GRAY)
        self.add(title, code)
        self.add()

    def flush(self):
        for text, code in self.lines:
            print(paint(text, code))

    def write(self, path: Path):
        path.write_text("\n".join(t for t, _ in self.lines) + "\n", encoding="utf-8")


# ============================================================
# TOKENIZER  (handles strings, long strings, all comment forms)
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


def matching_close(toks, i) -> int:
    pairs = {"(": ")", "[": "]", "{": "}"}
    open_, close = toks[i].val, pairs[toks[i].val]
    depth = 0
    for j in range(i, len(toks)):
        if toks[j].kind == "op":
            if toks[j].val == open_:
                depth += 1
            elif toks[j].val == close:
                depth -= 1
                if depth == 0:
                    return j
    return len(toks) - 1


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
class Func:
    name: str
    file: Path
    side: str
    start: int
    end: int
    tokens: list[str]
    calls: list[str]
    span: tuple[int, int]
    is_local: bool = False
    is_named: bool = False
    handler_of: str | None = None
    handler_via: str | None = None
    hash: str = ""
    snippet: list[str] = field(default_factory=list)


@dataclass
class Event:
    call: str
    name: str
    file: Path
    line: int
    side: str

    @property
    def is_register(self) -> bool:
        return self.call in REGISTER_CALLS


@dataclass
class ExportRef:
    kind: str  # provides | uses
    resource: str
    method: str
    file: Path
    line: int


# ============================================================
# EXTRACTORS
# ============================================================

def detect_side(rel: Path) -> str:
    names = [p.lower() for p in rel.parts[:-1]] + [rel.stem.lower()]
    for nm in names:
        if nm in ("server", "sv") or nm.startswith(("server", "sv_")) or nm.endswith(("_sv", "_server")):
            return "server"
        if nm in ("client", "cl") or nm.startswith(("client", "cl_")) or nm.endswith(("_cl", "_client")):
            return "client"
        if nm.startswith("shared") or nm == "config":
            return "shared"
    return "?"


def extract_functions(toks, src_lines, file, side) -> list[Func]:
    funcs = []

    for k, t in enumerate(toks):
        if not (t.kind == "kw" and t.val == "function"):
            continue

        is_local = is_kw(toks, k - 1, "local")
        named, name, handler_of, via = False, None, None, None

        if k + 1 < len(toks) and toks[k + 1].kind == "name":
            # function a.b:c(...)
            parts, p = [toks[k + 1].val], k + 2
            while p + 1 < len(toks) and toks[p].kind == "op" and toks[p].val in (".", ":") \
                    and toks[p + 1].kind == "name":
                parts += [toks[p].val, toks[p + 1].val]
                p += 2
            name, named = "".join(parts), True
        else:
            # anonymous: name it from its context
            p = k + 1
            bracket, callee, arg = enclosing_bracket(toks, k)

            if is_op(toks, k - 1, "="):
                chain, cstart = chain_before(toks, k - 1)
                if chain and bracket == "{":
                    name = "{" + chain + "}"  # table field, e.g. onSelect
                elif chain:
                    name, named = chain, True
                    is_local = is_kw(toks, cstart - 1, "local")
            elif bracket == "(" and callee:
                name = f"{callee}('{arg}')" if arg else f"{callee}(…)"
                if arg and callee in REGISTER_CALLS:
                    handler_of, via = arg, callee

            name = name or f"<anonymous:{t.line}>"

        end = block_end(toks, k)
        body = toks[p:end + 1]
        tokens = [f'"{x.val}"' if x.kind == "str" else x.val for x in body]

        calls = []
        for idx in range(p + 1, end + 1):
            if is_op(toks, idx, "("):
                chain, cstart = chain_before(toks, idx)
                if chain and not is_kw(toks, cstart - 1, "function"):
                    calls.append(chain)

        start_line, end_line = t.line, toks[end].line
        funcs.append(Func(
            name=name, file=file, side=side, start=start_line, end=end_line,
            tokens=tokens, calls=calls, span=(k, end), is_local=is_local, is_named=named,
            handler_of=handler_of, handler_via=via,
            hash=hashlib.sha256(" ".join(tokens).encode()).hexdigest(),
            snippet=src_lines[start_line - 1:end_line],
        ))

    return funcs


def extract_events(toks, file, side) -> list[Event]:
    events = []
    for i, t in enumerate(toks):
        if not is_op(toks, i, "("):
            continue
        chain, _ = chain_before(toks, i)
        if chain not in REGISTER_CALLS and chain not in TRIGGER_CALLS:
            continue
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        name = nxt.val if nxt is not None and nxt.kind == "str" else "<dynamic>"
        events.append(Event(chain, name, file, t.line, side))
    return events


def extract_exports(toks, file) -> list[ExportRef]:
    refs = []
    for i, t in enumerate(toks):
        if t.kind != "name" or t.val != "exports" or is_op(toks, i - 1, ".") or is_op(toks, i - 1, ":"):
            continue

        if is_op(toks, i + 1, "(") and i + 2 < len(toks) and toks[i + 2].kind == "str":
            refs.append(ExportRef("provides", "", toks[i + 2].val, file, t.line))
            continue

        if is_op(toks, i + 1, ".") and i + 2 < len(toks) and toks[i + 2].kind == "name":
            res, j = toks[i + 2].val, i + 3
        elif is_op(toks, i + 1, "["):
            close = matching_close(toks, i + 1)
            static = close == i + 3 and toks[i + 2].kind == "str"
            res, j = (toks[i + 2].val if static else "<dynamic>"), close + 1
        else:
            continue

        method = toks[j + 1].val if is_op(toks, j, ":") and j + 1 < len(toks) \
            and toks[j + 1].kind == "name" else "?"
        refs.append(ExportRef("uses", res, method, file, t.line))
    return refs


# ============================================================
# ANALYSIS
# ============================================================

def find_lua_files(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*.lua")
        if p.is_file() and not any(part in IGNORE_DIRS for part in p.relative_to(root).parts)
    )


def nested(a: Func, b: Func) -> bool:
    if a.file != b.file:
        return False
    return (a.span[0] <= b.span[0] and b.span[1] <= a.span[1]) or \
           (b.span[0] <= a.span[0] and a.span[1] <= b.span[1])


def find_exact_duplicates(funcs, min_tokens):
    groups = defaultdict(list)
    for f in funcs:
        if len(f.tokens) >= min_tokens:
            groups[f.hash].append(f)
    return [g for g in groups.values() if len(g) > 1]


def find_same_names(funcs):
    groups = defaultdict(list)
    for f in funcs:
        if f.is_named and not f.is_local:  # Lua is case-sensitive; locals are file-scoped
            groups[f.name].append(f)
    return [g for g in groups.values() if len(g) > 1 and len({f.hash for f in g}) > 1]


def find_similar(funcs, threshold, min_tokens):
    pool = [f for f in funcs if len(f.tokens) >= min_tokens]
    results = []
    for i in range(len(pool)):
        for j in range(i + 1, len(pool)):
            a, b = pool[i], pool[j]
            if a.hash == b.hash or nested(a, b):
                continue
            la, lb = len(a.tokens), len(b.tokens)
            if 2 * min(la, lb) / (la + lb) < threshold:  # upper bound of ratio()
                continue
            sm = SequenceMatcher(None, a.tokens, b.tokens, autojunk=False)
            if sm.real_quick_ratio() < threshold or sm.quick_ratio() < threshold:
                continue
            score = sm.ratio()
            if score >= threshold:
                results.append((a, b, score))
    return sorted(results, key=lambda r: -r[2])


def build_resolver(funcs):
    by_name = defaultdict(list)
    by_method = defaultdict(list)
    for f in funcs:
        if f.is_named:
            by_name[f.name].append(f)
            if ":" in f.name:
                by_method[short(f.name)].append(f)

    def resolve(call: str, caller: Func) -> list[Func]:
        cands = by_name.get(call) or (by_method.get(short(call), []) if ":" in call else [])
        return [c for c in cands if c is not caller and (not c.is_local or c.file == caller.file)]

    return resolve


# ============================================================
# REPORT SECTIONS
# ============================================================

def loc(f) -> str:
    return f"{f.file}:{f.start}-{f.end}"


def report_duplicates(out, exact, same_names, similar):
    out.section("🧬 DUPLICATES", C.RED)

    if not (exact or same_names or similar):
        out.add("No duplicates detected.", C.GRAY)
        out.add()
        return

    if exact:
        out.add(f"🔴 EXACT DUPLICATES (same body, any name/formatting): {len(exact)}", C.RED)
        for group in exact:
            out.add(f"  {' / '.join(sorted({f.name for f in group}))}", C.RED)
            for f in group:
                out.add(f"  ├─ {loc(f)}")
            for line in group[0].snippet[:12]:
                out.add(f"  │    {line.rstrip()}", C.GRAY)
            out.add()

    if same_names:
        out.add(f"🟠 SAME GLOBAL NAME / DIFFERENT CODE (last one loaded wins): {len(same_names)}", C.YELLOW)
        for group in same_names:
            out.add(f"  {group[0].name}()", C.YELLOW)
            for f in group:
                out.add(f"  ├─ {loc(f)}")
        out.add()

    if similar:
        out.add(f"🟡 SIMILAR FUNCTIONS: {len(similar)}", C.MAGENTA)
        for a, b, score in similar:
            out.add(f"  {a.name}  <->  {b.name}   {score * 100:.1f}%", C.MAGENTA)
            out.add(f"  ├─ {loc(a)}")
            out.add(f"  └─ {loc(b)}")
        out.add()


def report_relationships(out, relationships):
    out.section("🔗 FUNCTION RELATIONSHIPS", C.BLUE)
    if not relationships:
        out.add("No internal function relationships detected.", C.GRAY)
        out.add()
        return
    for source in sorted(relationships):
        out.add(f"  {source}", C.BLUE)
        for target in sorted(relationships[source]):
            out.add(f"    └─ calls → {target}()", C.CYAN)
    out.add()


def report_events(out, events):
    out.section("⚡ FIVEM EVENTS / CALLBACKS", C.CYAN)
    if not events:
        out.add("No FiveM events or callbacks detected.", C.GRAY)
        out.add()
        return

    by_name = defaultdict(list)
    for e in events:
        by_name[e.name].append(e)

    for name in sorted(by_name):
        out.add(f"  {name}", C.YELLOW)
        items = sorted(by_name[name], key=lambda e: (not e.is_register, str(e.file), e.line))
        for idx, e in enumerate(items):
            branch = "└─" if idx == len(items) - 1 else "├─"
            role = "handler" if e.is_register else "trigger"
            out.add(f"    {branch} {role:<7} {e.call:<26} {e.file}:{e.line}")
    out.add()


def event_problems(events, handlers):
    by_name = defaultdict(list)
    for e in events:
        by_name[e.name].append(e)

    problems = []
    for name, items in sorted(by_name.items()):
        if name == "<dynamic>":
            for e in items:
                problems.append(("Dynamic event name (can't be resolved statically)", f"{e.call} @ {e.file}:{e.line}"))
            continue
        regs = [e for e in items if e.is_register]
        trigs = [e for e in items if not e.is_register]
        if trigs and not regs:
            problems.append(("Triggered but no handler in this resource", name))
        if regs and not trigs and ":" in name:
            problems.append(("Handler never triggered from Lua (NUI / other resource / dead?)", name))

    per_side = defaultdict(list)
    for f in handlers:
        per_side[(f.handler_of, f.side)].append(f)
    for (name, side), fs in sorted(per_side.items()):
        if len(fs) > 1:
            where = ", ".join(f"{f.file}:{f.start}" for f in fs)
            problems.append((f"Event has {len(fs)} handlers on {side} side (runs more than once)", f"{name} → {where}"))
    return problems


def report_problems(out, problems):
    out.section("⚠ EVENT ISSUES", C.YELLOW)
    if not problems:
        out.add("No event issues detected.", C.GRAY)
        out.add()
        return
    grouped = defaultdict(list)
    for kind, detail in problems:
        grouped[kind].append(detail)
    for kind, details in grouped.items():
        out.add(f"  {kind}", C.YELLOW)
        for d in details:
            out.add(f"    └─ {d}")
    out.add()


def report_attack_surface(out, surface):
    out.section("🎯 CLIENT-REACHABLE SERVER HANDLERS (attack surface)", C.RED)
    if not surface:
        out.add("No server-side net events or callbacks detected.", C.GRAY)
        out.add()
        return
    for f, sensitive in surface:
        flag = "  ⚠ sensitive" if sensitive else ""
        out.add(f"  {f.handler_of}  [{f.handler_via}]{flag}", C.RED if sensitive else C.WHITE)
        out.add(f"    └─ {loc(f)}", C.GRAY)
        for s in sensitive:
            out.add(f"       • {s}", C.YELLOW)
    out.add()


def report_exports(out, exports):
    out.section("📦 EXPORTS", C.GREEN)
    provided = [x for x in exports if x.kind == "provides"]
    used = defaultdict(lambda: defaultdict(list))
    for x in exports:
        if x.kind == "uses":
            used[x.resource][x.method].append(x)

    if not exports:
        out.add("No exports detected.", C.GRAY)
        out.add()
        return

    if provided:
        out.add("  Provides:", C.GREEN)
        for x in provided:
            out.add(f"    └─ {x.method}   {x.file}:{x.line}")
    if used:
        out.add("  Uses (dependencies):", C.GREEN)
        for res in sorted(used):
            out.add(f"    {res}", C.CYAN)
            for method, refs in sorted(used[res].items()):
                locs = ", ".join(f"{r.file}:{r.line}" for r in refs[:4])
                more = f" (+{len(refs) - 4})" if len(refs) > 4 else ""
                out.add(f"      └─ {method} ×{len(refs)}   {locs}{more}", C.GRAY)
    out.add()


# ============================================================
# MAIN
# ============================================================

def main():
    global USE_COLOR

    ap = argparse.ArgumentParser(description="Static analyzer for FiveM Lua resources")
    ap.add_argument("path", nargs="?", default=".", help="resource folder (default: cwd)")
    ap.add_argument("-o", "--output", help="report path (default: <resource>/dependency_report.txt)")
    ap.add_argument("--threshold", type=float, default=0.70, help="similarity threshold (0-1)")
    ap.add_argument("--min-tokens", type=int, default=25, help="ignore tiny functions in duplicate checks")
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
        print(paint(f"[ERROR] Not a directory: {root}", C.RED))
        sys.exit(1)

    print(paint(f"[ SCANNING ] {root}", C.CYAN))
    files = find_lua_files(root)

    funcs: list[Func] = []
    events: list[Event] = []
    exports: list[ExportRef] = []

    for file in files:
        try:
            src = file.read_text(encoding="utf-8", errors="ignore")
        except OSError as error:
            print(paint(f"[ERROR] {file}: {error}", C.RED))
            continue
        rel = file.relative_to(root)
        side = detect_side(rel)
        toks = tokenize(src)
        funcs += extract_functions(toks, src.splitlines(), rel, side)
        events += extract_events(toks, rel, side)
        exports += extract_exports(toks, rel)

    exact = find_exact_duplicates(funcs, args.min_tokens)
    same_names = find_same_names(funcs)
    similar = find_similar(funcs, args.threshold, args.min_tokens)

    resolve = build_resolver(funcs)
    relationships = defaultdict(set)
    for f in funcs:
        for call in f.calls:
            for target in resolve(call, f):
                relationships[f.name].add(target.name)

    handlers = [f for f in funcs if f.handler_of]
    net_names = {e.name for e in events if e.call in NET_REGISTER and e.side in ("server", "?")}
    surface = []
    for f in handlers:
        if f.side not in ("server", "?"):
            continue
        if f.handler_of not in net_names and f.handler_via not in CALLBACK_REGISTER:
            continue
        calls = list(f.calls)
        for call in f.calls:  # follow one level into helper functions
            for target in resolve(call, f):
                calls += [f"{c}  (via {target.name})" for c in target.calls]
        sensitive = sorted({c for c in calls if SENSITIVE_CALL.search(c)})
        surface.append((f, sensitive))
    surface.sort(key=lambda s: (not s[1], s[0].handler_of))

    problems = event_problems(events, handlers)

    out = Out()
    out.add(f"Resource:  {root}", C.WHITE)
    out.add(f"Lua files: {len(files)}", C.WHITE)
    out.add(f"Functions: {len(funcs)}  (named: {sum(f.is_named for f in funcs)}, "
            f"handlers: {len(handlers)})", C.WHITE)
    out.add()

    report_duplicates(out, exact, same_names, similar)
    report_relationships(out, relationships)
    report_events(out, events)
    report_problems(out, problems)
    report_attack_surface(out, surface)
    report_exports(out, exports)

    issues = len(exact) + len(same_names) + len(similar)
    out.add("─" * 60, C.GRAY)
    out.add(f"Duplicate issues:        {issues}", C.YELLOW if issues else C.GREEN)
    out.add(f"Event issues:            {len(problems)}", C.YELLOW if problems else C.GREEN)
    out.add(f"Attack-surface handlers: {len(surface)} "
            f"({sum(bool(s) for _, s in surface)} sensitive)", C.RED)
    out.add(f"Function relationships:  {sum(len(v) for v in relationships.values())}", C.BLUE)
    out.add(f"Events/callbacks:        {len(events)}", C.CYAN)
    out.add(f"Export references:       {len(exports)}", C.GREEN)

    out.flush()

    report_path = Path(args.output).resolve() if args.output else root / "dependency_report.txt"
    out.write(report_path)
    print()
    print(paint(f"[ REPORT ] {report_path}", C.CYAN))


if __name__ == "__main__":
    main()
