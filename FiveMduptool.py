from __future__ import annotations

import re
import sys
import hashlib
from pathlib import Path
from difflib import SequenceMatcher


# ============================================================
# REYOF // FIVEM RESOURCE ANALYZER
# ============================================================

HEADER = r"""
██████╗ ███████╗██╗   ██╗ ██████╗ ███████╗
██╔══██╗██╔════╝╚██╗ ██╔╝██╔═══██╗██╔════╝
██████╔╝█████╗   ╚████╔╝ ██║   ██║█████╗
██╔══██╗██╔══╝    ╚██╔╝  ██║   ██║██╔══╝
██║  ██║███████╗   ██║   ╚██████╔╝███████╗
╚═╝  ╚═╝╚══════╝   ╚═╝    ╚═════╝ ╚══════╝

             FIVEM RESOURCE ANALYZER
"""

RESET = "\033[0m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
BLUE = "\033[94m"
GRAY = "\033[90m"
WHITE = "\033[97m"


IGNORE_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    "cache",
    "dist",
    "build",
}

SUPPORTED_EXTENSIONS = {
    ".lua",
}

SIMILARITY_THRESHOLD = 0.70


# ============================================================
# TERMINAL
# ============================================================

def color(text, code):
    return f"{code}{text}{RESET}"


def banner():
    print(color(HEADER, GREEN))


def separator():
    print(color("────────────────────────────────────────", GRAY))


# ============================================================
# FILE SCANNER
# ============================================================

def find_lua_files(root: Path):
    files = []

    for path in root.rglob("*"):

        if not path.is_file():
            continue

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        if any(part in IGNORE_DIRS for part in path.parts):
            continue

        files.append(path)

    return sorted(files)


# ============================================================
# LUA COMMENTS
# ============================================================

def strip_comments(text: str):

    text = re.sub(
        r"--\[\[.*?\]\]",
        lambda m: "\n" * m.group(0).count("\n"),
        text,
        flags=re.DOTALL,
    )

    result = []

    for line in text.splitlines():

        output = []
        string_char = None
        escaped = False
        i = 0

        while i < len(line):

            ch = line[i]

            if escaped:
                output.append(ch)
                escaped = False
                i += 1
                continue

            if ch == "\\" and string_char:
                output.append(ch)
                escaped = True
                i += 1
                continue

            if ch in ("'", '"'):

                if string_char == ch:
                    string_char = None

                elif string_char is None:
                    string_char = ch

                output.append(ch)
                i += 1
                continue

            if (
                ch == "-"
                and i + 1 < len(line)
                and line[i + 1] == "-"
                and string_char is None
            ):
                break

            output.append(ch)
            i += 1

        result.append("".join(output))

    return "\n".join(result)


# ============================================================
# NORMALIZATION
# ============================================================

def normalize(text):

    lines = []

    for line in text.splitlines():

        line = line.strip()

        if not line:
            continue

        line = re.sub(r"\s+", " ", line)

        lines.append(line)

    return "\n".join(lines)


def hash_body(text):

    normalized = normalize(text)

    return hashlib.sha256(
        normalized.encode("utf-8", errors="ignore")
    ).hexdigest()


# ============================================================
# FUNCTION PARSER
# ============================================================

FUNCTION_PATTERN = re.compile(
    r"^\s*(?:local\s+)?function\s+"
    r"([A-Za-z_][\w\.:]*)\s*\("
)


def extract_functions(text, file):

    lines = text.splitlines()

    functions = []

    i = 0

    while i < len(lines):

        match = FUNCTION_PATTERN.match(lines[i])

        if not match:
            i += 1
            continue

        name = match.group(1)

        start = i + 1

        depth = 1

        j = i + 1

        while j < len(lines):

            current = lines[j].strip()

            clean = re.sub(
                r'(["\'])(?:\\.|(?!\1).)*\1',
                "",
                current,
            )

            nested_function = re.match(
                r"^(?:local\s+)?function\s+",
                clean,
            )

            if nested_function:
                depth += 1

            if re.match(
                r"^(if|for|while)\b",
                clean,
            ):
                depth += 1

            if re.search(
                r"\bdo\s*$",
                clean,
            ):
                depth += 1

            if clean.startswith("repeat"):
                depth += 1

            if clean == "end" or clean.startswith("end "):

                depth -= 1

                if depth == 0:
                    break

            if clean.startswith("until "):

                depth -= 1

                if depth == 0:
                    break

            j += 1

        end = min(
            j + 1,
            len(lines)
        )

        body = "\n".join(
            lines[i:end]
        )

        functions.append(
            {
                "name": name,
                "file": file,
                "start": start,
                "end": end,
                "body": body,
                "normalized": normalize(body),
                "hash": hash_body(body),
            }
        )

        i = max(j + 1, i + 1)

    return functions


# ============================================================
# FUNCTION CALL DETECTION
# ============================================================

def extract_function_calls(
    text,
    functions,
):

    calls = []

    known_names = {
        function["name"].split(":")[-1].split(".")[-1]
        for function in functions
    }

    lines = text.splitlines()

    for index, line in enumerate(lines):

        for name in known_names:

            pattern = rf"\b{re.escape(name)}\s*\("

            if re.search(pattern, line):

                calls.append(
                    {
                        "name": name,
                        "line": index + 1,
                    }
                )

    return calls


def build_function_relationships(
    text,
    functions,
):

    relationships = []

    lines = text.splitlines()

    for function in functions:

        body_lines = lines[
            function["start"] - 1:
            function["end"]
        ]

        body = "\n".join(body_lines)

        known_functions = {
            f["name"].split(":")[-1].split(".")[-1]
            for f in functions
        }

        for target in known_functions:

            if target == function["name"].split(":")[-1].split(".")[-1]:
                continue

            if re.search(
                rf"\b{re.escape(target)}\s*\(",
                body,
            ):

                relationships.append(
                    {
                        "source": function["name"],
                        "target": target,
                        "file": function["file"],
                    }
                )

    return relationships


# ============================================================
# FIVEM EVENTS
# ============================================================

def extract_events(text, file):

    events = []

    patterns = {

        "RegisterNetEvent": re.compile(
            r"RegisterNetEvent\s*\(\s*['\"]([^'\"]+)"
        ),

        "TriggerServerEvent": re.compile(
            r"TriggerServerEvent\s*\(\s*['\"]([^'\"]+)"
        ),

        "TriggerClientEvent": re.compile(
            r"TriggerClientEvent\s*\(\s*['\"]([^'\"]+)"
        ),

        "TriggerEvent": re.compile(
            r"TriggerEvent\s*\(\s*['\"]([^'\"]+)"
        ),

        "lib.callback.register": re.compile(
            r"lib\.callback\.register\s*\(\s*['\"]([^'\"]+)"
        ),

        "lib.callback.await": re.compile(
            r"lib\.callback\.await\s*\(\s*['\"]([^'\"]+)"
        ),

        "QBCore callback": re.compile(
            r"QBCore\.Functions\.CreateCallback\s*\(\s*['\"]([^'\"]+)"
        ),

    }

    for line_number, line in enumerate(
        text.splitlines(),
        start=1,
    ):

        for event_type, pattern in patterns.items():

            matches = pattern.findall(line)

            for name in matches:

                events.append(
                    {
                        "type": event_type,
                        "name": name,
                        "file": file,
                        "line": line_number,
                    }
                )

    return events


# ============================================================
# EXPORTS
# ============================================================

def extract_exports(text, file):

    exports = []

    patterns = [
        re.compile(
            r"exports\s*\.\s*([A-Za-z_][\w]*)"
        ),
        re.compile(
            r"exports\s*\[\s*['\"]([^'\"]+)"
        ),
    ]

    for line_number, line in enumerate(
        text.splitlines(),
        start=1,
    ):

        for pattern in patterns:

            for match in pattern.findall(line):

                exports.append(
                    {
                        "name": match,
                        "file": file,
                        "line": line_number,
                    }
                )

    return exports


# ============================================================
# DUPLICATE ANALYSIS
# ============================================================

def find_exact_duplicates(functions):

    groups = {}

    for function in functions:

        groups.setdefault(
            function["hash"],
            [],
        ).append(function)

    return [
        group
        for group in groups.values()
        if len(group) > 1
    ]


def find_same_names(functions):

    groups = {}

    for function in functions:

        key = function["name"].lower()

        groups.setdefault(
            key,
            [],
        ).append(function)

    return [
        group
        for group in groups.values()
        if len(group) > 1
    ]


def similarity(a, b):

    return SequenceMatcher(
        None,
        a,
        b,
    ).ratio()


def find_similar(functions):

    results = []

    for i in range(len(functions)):

        for j in range(i + 1, len(functions)):

            a = functions[i]
            b = functions[j]

            if a["hash"] == b["hash"]:
                continue

            score = similarity(
                a["normalized"],
                b["normalized"],
            )

            if score >= SIMILARITY_THRESHOLD:

                results.append(
                    {
                        "a": a,
                        "b": b,
                        "score": score,
                    }
                )

    return results


# ============================================================
# PRINT DUPLICATES
# ============================================================

def print_duplicates(
    functions,
    exact,
    same_names,
    similar,
):

    print(
        color(
            f"Functions found: {len(functions)}",
            WHITE,
        )
    )

    print()

    if exact:

        print(
            color(
                f"🔴 EXACT DUPLICATES: {len(exact)}",
                RED,
            )
        )

        print()

        for group in exact:

            print(
                color(
                    f"  {group[0]['name']}()",
                    RED,
                )
            )

            print(
                color(
                    "  Same body: 100%",
                    RED,
                )
            )

            for item in group:

                print(
                    f"  ├─ "
                    f"{item['file']}:"
                    f"{item['start']}-"
                    f"{item['end']}"
                )

            print(
                color(
                    "  └─ Code:",
                    GRAY,
                )
            )

            for line in group[0]["body"].splitlines()[:20]:

                print(
                    color(
                        f"       {line}",
                        GRAY,
                    )
                )

            print()

    different_names = []

    for group in same_names:

        hashes = {
            item["hash"]
            for item in group
        }

        if len(hashes) > 1:

            different_names.append(group)

    if different_names:

        print(
            color(
                f"🟠 SAME NAME / DIFFERENT CODE: "
                f"{len(different_names)}",
                YELLOW,
            )
        )

        print()

        for group in different_names:

            print(
                color(
                    f"  {group[0]['name']}()",
                    YELLOW,
                )
            )

            for item in group:

                print(
                    f"  ├─ "
                    f"{item['file']}:"
                    f"{item['start']}"
                )

            for i in range(len(group)):

                for j in range(i + 1, len(group)):

                    score = similarity(
                        group[i]["normalized"],
                        group[j]["normalized"],
                    )

                    print(
                        color(
                            f"  Similarity: "
                            f"{score * 100:.1f}%",
                            YELLOW,
                        )
                    )

            print()

    if similar:

        print(
            color(
                f"🟡 SIMILAR FUNCTIONS: {len(similar)}",
                MAGENTA,
            )
        )

        print()

        for item in similar:

            print(
                color(
                    f"  {item['a']['name']}() "
                    f"<-> "
                    f"{item['b']['name']}()",
                    MAGENTA,
                )
            )

            print(
                color(
                    f"  Similarity: "
                    f"{item['score'] * 100:.1f}%",
                    MAGENTA,
                )
            )

            print(
                f"  ├─ "
                f"{item['a']['file']}:"
                f"{item['a']['start']}"
            )

            print(
                f"  └─ "
                f"{item['b']['file']}:"
                f"{item['b']['start']}"
            )

            print()


# ============================================================
# PRINT RELATIONSHIPS
# ============================================================

def print_relationships(relationships):

    separator()

    print(
        color(
            "🔗 FUNCTION RELATIONSHIPS",
            BLUE,
        )
    )

    print()

    if not relationships:

        print(
            color(
                "No internal function relationships detected.",
                GRAY,
            )
        )

        return

    grouped = {}

    for relation in relationships:

        grouped.setdefault(
            relation["source"],
            set(),
        ).add(
            relation["target"]
        )

    for source, targets in sorted(
        grouped.items()
    ):

        print(
            color(
                f"  {source}()",
                BLUE,
            )
        )

        for target in sorted(targets):

            print(
                f"    └─ calls → "
                f"{color(target + '()', CYAN)}"
            )

        print()


# ============================================================
# PRINT EVENTS
# ============================================================

def print_events(events):

    separator()

    print(
        color(
            "⚡ FIVEM EVENTS / CALLBACKS",
            CYAN,
        )
    )

    print()

    if not events:

        print(
            color(
                "No FiveM events or callbacks detected.",
                GRAY,
            )
        )

        return

    for event in events:

        print(
            f"  {color(event['type'], YELLOW)}"
        )

        print(
            f"    └─ {event['name']}"
        )

        print(
            color(
                f"       {event['file']}:{event['line']}",
                GRAY,
            )
        )

        print()


# ============================================================
# PRINT EXPORTS
# ============================================================

def print_exports(exports):

    separator()

    print(
        color(
            "📦 EXPORTS",
            GREEN,
        )
    )

    print()

    if not exports:

        print(
            color(
                "No exports detected.",
                GRAY,
            )
        )

        return

    for item in exports:

        print(
            f"  {item['name']}"
        )

        print(
            color(
                f"    └─ {item['file']}:{item['line']}",
                GRAY,
            )
        )


# ============================================================
# REPORT
# ============================================================

def generate_report(
    root,
    files,
    functions,
    exact,
    same_names,
    similar,
    relationships,
    events,
    exports,
):

    report_path = root / "dependency_report.txt"

    with report_path.open(
        "w",
        encoding="utf-8",
    ) as report:

        report.write(
            "REYOF // FIVEM RESOURCE ANALYZER\n"
        )

        report.write(
            "=" * 65 + "\n\n"
        )

        report.write(
            f"Resource: {root}\n"
        )

        report.write(
            f"Lua files: {len(files)}\n"
        )

        report.write(
            f"Functions: {len(functions)}\n\n"
        )

        # ----------------------------------------------------
        # DUPLICATES
        # ----------------------------------------------------

        report.write(
            "EXACT DUPLICATES\n"
        )

        report.write(
            "-" * 65 + "\n"
        )

        for group in exact:

            report.write(
                f"\n{group[0]['name']}()\n"
            )

            for item in group:

                report.write(
                    f"  {item['file']}:"
                    f"{item['start']}-"
                    f"{item['end']}\n"
                )

        # ----------------------------------------------------
        # SIMILAR
        # ----------------------------------------------------

        report.write(
            "\n\nSIMILAR FUNCTIONS\n"
        )

        report.write(
            "-" * 65 + "\n"
        )

        for item in similar:

            report.write(
                f"\n"
                f"{item['a']['name']}() "
                f"<-> "
                f"{item['b']['name']}()\n"
            )

            report.write(
                f"Similarity: "
                f"{item['score'] * 100:.1f}%\n"
            )

            report.write(
                f"  {item['a']['file']}:"
                f"{item['a']['start']}\n"
            )

            report.write(
                f"  {item['b']['file']}:"
                f"{item['b']['start']}\n"
            )

        # ----------------------------------------------------
        # RELATIONSHIPS
        # ----------------------------------------------------

        report.write(
            "\n\nFUNCTION RELATIONSHIPS\n"
        )

        report.write(
            "-" * 65 + "\n"
        )

        for relation in relationships:

            report.write(
                f"{relation['source']}() "
                f"-> "
                f"{relation['target']}()\n"
            )

        # ----------------------------------------------------
        # EVENTS
        # ----------------------------------------------------

        report.write(
            "\n\nFIVEM EVENTS / CALLBACKS\n"
        )

        report.write(
            "-" * 65 + "\n"
        )

        for event in events:

            report.write(
                f"{event['type']} "
                f"-> "
                f"{event['name']} "
                f"({event['file']}:{event['line']})\n"
            )

        # ----------------------------------------------------
        # EXPORTS
        # ----------------------------------------------------

        report.write(
            "\n\nEXPORTS\n"
        )

        report.write(
            "-" * 65 + "\n"
        )

        for item in exports:

            report.write(
                f"{item['name']} "
                f"({item['file']}:{item['line']})\n"
            )

    return report_path


# ============================================================
# MAIN
# ============================================================

def main():

    banner()

    if len(sys.argv) >= 2:

        root = Path(
            sys.argv[1]
        ).resolve()

    else:

        root = Path.cwd()

    if not root.exists():

        print(
            color(
                f"[ERROR] Path does not exist: {root}",
                RED,
            )
        )

        return

    print(
        color(
            f"[ SCANNING ] {root}",
            CYAN,
        )
    )

    files = find_lua_files(root)

    print(
        color(
            f"Lua files found: {len(files)}",
            WHITE,
        )
    )

    print()

    all_functions = []
    all_relationships = []
    all_events = []
    all_exports = []

    for file in files:

        try:

            raw = file.read_text(
                encoding="utf-8",
                errors="ignore",
            )

        except Exception as error:

            print(
                color(
                    f"[ERROR] {file}: {error}",
                    RED,
                )
            )

            continue

        cleaned = strip_comments(raw)

        relative = file.relative_to(root)

        functions = extract_functions(
            cleaned,
            relative,
        )

        relationships = build_function_relationships(
            cleaned,
            functions,
        )

        events = extract_events(
            cleaned,
            relative,
        )

        exports = extract_exports(
            cleaned,
            relative,
        )

        all_functions.extend(functions)
        all_relationships.extend(relationships)
        all_events.extend(events)
        all_exports.extend(exports)

    exact = find_exact_duplicates(
        all_functions
    )

    same_names = find_same_names(
        all_functions
    )

    similar = find_similar(
        all_functions
    )

    print_duplicates(
        all_functions,
        exact,
        same_names,
        similar,
    )

    print_relationships(
        all_relationships
    )

    print_events(
        all_events
    )

    print_exports(
        all_exports
    )

    separator()

    issues = (
        len(exact)
        + len(similar)
    )

    print(
        color(
            f"Potential duplicate issues: {issues}",
            YELLOW if issues else GREEN,
        )
    )

    print(
        color(
            f"Function relationships: "
            f"{len(all_relationships)}",
            BLUE,
        )
    )

    print(
        color(
            f"FiveM events/callbacks: "
            f"{len(all_events)}",
            CYAN,
        )
    )

    print(
        color(
            f"Exports: "
            f"{len(all_exports)}",
            GREEN,
        )
    )

    report = generate_report(
        root,
        files,
        all_functions,
        exact,
        same_names,
        similar,
        all_relationships,
        all_events,
        all_exports,
    )

    print()

    print(
        color(
            f"[ REPORT ] {report}",
            CYAN,
        )
    )


if __name__ == "__main__":
    main()
