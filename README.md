<div align="center">

# REYOF : FiveM Resource Analyzer

### A static analysis tool that scans FiveM Lua resources and finds **functions that are duplicated or similar across different files**, showing exactly where each copy lives and what it is connected to.

Point it at a single resource or your whole `resources` folder: it walks every sub-folder, compares every function, and groups the copies together.

<br>

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FiveM](https://img.shields.io/badge/FiveM-Resource%20Analyzer-F40552?style=for-the-badge)
![Lua](https://img.shields.io/badge/Lua-Supported-000080?style=for-the-badge&logo=lua&logoColor=white)
![Dependencies](https://img.shields.io/badge/Dependencies-None-00FF88?style=for-the-badge)

</div>

---

## Features

- **Recursive scan**: goes through the target folder and every folder inside it.
- **Cross-file detection**: reports only functions repeated in more than one file.
- **Exact and similar matches**: catches 100% identical copies as well as near-copies with renamed variables or small edits.
- **Grouped results**: a function copied into 4 files shows up once, with all 4 locations listed.
- **Precise locations**: folder, file, line range and a `path:line` you can click in VS Code.
- **Connection map** for every similar function:
  - 🎯 the event it handles (`RegisterNetEvent`, `lib.callback.register`, `RegisterCommand`...)
  - ⚡ where that event is fired from
  - 🔗 where the function is called from
  - ➡ project functions it calls
  - ⚡ events it fires (`TriggerServerEvent`, `TriggerClientEvent`...)
  - 📦 exports it uses (`ox_lib:notify`, `ox_inventory:AddItem`...)
  - ○ flags functions that aren't linked to anything (possibly dead code)
- **Real Lua tokenizer**: correctly handles strings, `[[long strings]]`, and every comment form (`--`, `--[[ ]]`, `--[==[ ]==]`), so commented-out code is never counted.
- **Plain-text report** saved after every run.

---

## Requirements

- Python **3.10+**
- No external packages (standard library only)

---

## Installation

```bash
git clone https://github.com/4lac/fivem-resource-analyzer.git
cd fivem-resource-analyzer
```

---

## Usage

### Linux / macOS

```bash
python3 fivem_analyzer.py "/path/to/resources"
```

### WSL

Windows drives are mounted under `/mnt/c`:

```bash
python3 fivem_analyzer.py "/mnt/c/Users/PC/Desktop/server/resources"
```

### Windows (PowerShell / CMD)

```powershell
python fivem_analyzer.py "C:\Users\PC\Desktop\server\resources"
```

Use `py` instead of `python` if Python isn't on your PATH.

### Scan the current folder

```bash
cd path/to/resource
python3 /path/to/fivem_analyzer.py
```

### Optional: install as a global command (Linux / WSL)

```bash
mkdir -p ~/bin
cp fivem_analyzer.py ~/bin/fivem-analyzer
chmod +x ~/bin/fivem-analyzer
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc

fivem-analyzer .
```

---

## Options

| Option | Default | Description |
|---|---|---|
| `path` | current folder | Folder to scan (recursively) |
| `-o`, `--output` | `<folder>/similar_functions_report.txt` | Where to save the report |
| `--threshold` | `0.70` | Minimum similarity (0–1) to count as similar |
| `--min-tokens` | `20` | Ignore tiny functions to reduce noise |
| `--no-color` | off | Disable colored output |

Example:

```bash
python3 fivem_analyzer.py . --threshold 0.8 -o report.txt
```

---

## Example Output

```text
════════════════════════════════════════════════════════════════
[1] 3 copies in 3 files  ·  similar
════════════════════════════════════════════════════════════════
  (1) getInventory
      📁 Folder : medical-dna/client
      📄 File   : main.lua   (lines 1 → 8)
      📍 Path   : medical-dna/client/main.lua:1
      🔗 Called from   : medical-dna/client/main.lua:11
      ⚡ Fires events  : TriggerServerEvent → medical-dna:server:sync

  (2) getInventory
      📁 Folder : other-res/client/utils
      📄 File   : helpers.lua   (lines 1 → 8)
      📍 Path   : other-res/client/utils/helpers.lua:1
      🧬 100% identical to (1)
      ⚡ Fires events  : TriggerServerEvent → medical-dna:server:sync

  (3) getInv
      📁 Folder : medical-dna/client
      📄 File   : beds.lua   (lines 1 → 8)
      📍 Path   : medical-dna/client/beds.lua:1
      🧬 90.4% similar to (1)
      ⚡ Fires events  : TriggerServerEvent → medical-dna:server:sync

Similar groups: 1  (3 functions involved)
```

---

## How It Works

1. **Scan**: collects every `.lua` file under the target folder. It skips `.git`, `node_modules`, `cache`, `dist`, `build`, `.idea` and `.vscode`.
2. **Tokenize**: each file is split into Lua tokens, so comments and whitespace don't affect comparisons.
3. **Extract functions**: picks up named functions (`function a.b:c()`, `local function x()`, `x = function()`) and anonymous handlers. Handlers are named after their context, for example `RegisterNetEvent('medical-dna:server:treat')`.
4. **Compare**: function bodies are compared token by token. A function's name is ignored, so the same body under a different name is still caught.
5. **Group**: matching functions from different files are merged into one group.
6. **Link**: each function in a group is mapped to its events, callers, calls and exports.

---

## Limitations

- Static analysis only: calls built dynamically at runtime (e.g. `_G[name]()`) can't be resolved.
- Only `.lua` files are scanned (NUI JavaScript is not).
- Similarity is structural, so two functions that do the same thing written in completely different ways won't match.

---

## Author

**Reyof** · [github.com/4lac](https://github.com/4lac)

---

> **REYOF Analyze. Understand. Refactor.**
