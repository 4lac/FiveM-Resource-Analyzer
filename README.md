<div align="center">

# REYOF : FiveM Resource Analyzer

### Static analysis tool for FiveM Lua resources

Detect duplicate functions, analyze function relationships, inspect FiveM events and callbacks, and map resource dependencies — directly from your terminal.

<br>

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FiveM](https://img.shields.io/badge/FiveM-Resource%20Analyzer-F40552?style=for-the-badge)
![Lua](https://img.shields.io/badge/Lua-Supported-000080?style=for-the-badge&logo=lua&logoColor=white)
![Dependencies](https://img.shields.io/badge/Dependencies-None-00FF88?style=for-the-badge)

</div>

---

## Features

### Duplicate Detection

Detects functions that contain identical code across different files.

* Exact duplicate functions
* Same function name with different implementations
* Similar function bodies
* Line numbers and source files
* Duplicate code preview

### Function Relationships

Analyzes relationships between functions and attempts to identify which functions call other functions.

Example:

```text
playerLoad()
    └── getPlayerData()
            └── getInventory()
```

This helps visualize how different parts of a resource are connected.

### FiveM Events & Callbacks

Detects common FiveM communication patterns including:

* `RegisterNetEvent`
* `TriggerEvent`
* `TriggerServerEvent`
* `TriggerClientEvent`
* `lib.callback.register`
* `lib.callback.await`
* `QBCore.Functions.CreateCallback`

### Export Detection

Finds exported functions such as:

```lua
exports('FunctionName', function()
    ...
end)
```

and:

```lua
exports.resource:FunctionName()
```

### Recursive Scanning

The analyzer scans Lua files inside the entire resource, including nested folders.

Example:

```text
resource/
├── client/
│   ├── main.lua
│   └── beds.lua
├── server/
│   └── main.lua
├── shared/
│   └── utils.lua
└── config/
    └── config.lua
```

Ignored directories include:

```text
.git
.idea
.vscode
node_modules
cache
dist
build
```

---

## Requirements

* Python 3.10+
* No external Python packages required

---

## Installation

Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/fivem-resource-analyzer.git
```

Enter the project:

```bash
cd fivem-resource-analyzer
```

---

## Usage

Run the analyzer and provide the path to your FiveM resource:

```bash
python FiveMduptool.py "C:\path\to\your\resource"
```

Example:

```bash
python FiveMduptool.py "C:\Users\PC\Desktop\medical-dna"
```

You can also run it against a parent directory containing multiple resources.

---

## Example Output

```text
██████╗ ███████╗██╗   ██╗ ██████╗ ███████╗
██╔══██╗██╔════╝╚██╗ ██╔╝██╔═══██╗██╔════╝
██████╔╝█████╗   ╚████╔╝ ██║   ██║█████╗
██╔══██╗██╔══╝    ╚██╔╝  ██║   ██║██╔══╝
██║  ██║███████╗   ██║   ╚██████╔╝███████╗
╚═╝  ╚═╝╚══════╝   ╚═╝    ╚═════╝ ╚══════╝

          FIVEM RESOURCE ANALYZER

[ SCANNING ] C:\Users\PC\Desktop\medical-dna

Lua files found: 6
Functions found: 6

🔴 EXACT DUPLICATES: 1

  toast()
  Same body: 100%

  ├─ client\beds.lua:15-17
  ├─ client\main.lua:10-12
```

---

## Analysis Sections

The analyzer currently provides several analysis sections.

### 🔴 Exact Duplicates

Finds functions with identical normalized function bodies.

### 🟠 Same Name / Different Code

Finds functions using the same name while having different implementations.

### 🟡 Similar Functions

Uses code similarity analysis to identify functions that may be doing similar work even when their code is not completely identical.

### 🔗 Function Relationships

Attempts to identify internal function calls and build relationships between functions.

### ⚡ FiveM Events / Callbacks

Detects FiveM networking events and callback registrations/usages.

### 📦 Exports

Detects exported functions and resource-to-resource interactions.

---

## Generated Reports

The analyzer can generate a report containing the detected relationships and potential issues.

Example:

```text
duplicate_report.txt
```

The report can be used for reviewing large resources without having to inspect every Lua file manually.

---

## Why?

FiveM resources can become difficult to maintain as they grow.

Large resources often contain:

* duplicated functions
* repeated utility code
* unused functions
* multiple implementations of the same logic
* complicated event chains
* unnecessary dependencies
* duplicated callbacks
* resource-to-resource dependencies

This project was created to make those problems easier to spot.

---

## Use Cases

This tool can be useful when:

* Cleaning up an old FiveM resource
* Refactoring a large resource
* Auditing a purchased resource
* Looking for duplicated code
* Understanding an unfamiliar resource
* Investigating how events are connected
* Finding potentially unnecessary functions
* Preparing a resource for optimization
* Reviewing code before publishing it

---

## Example

Given:

```lua
local function toast(msg)
    SendNUIMessage({
        action = 'toast',
        text = msg
    })
end
```

and another file containing:

```lua
local function toast(msg)
    SendNUIMessage({
        action = 'toast',
        text = msg
    })
end
```

The analyzer can identify that both functions contain the same implementation:

```text
🔴 EXACT DUPLICATES

toast()

├─ client\main.lua
└─ client\beds.lua
```

This can indicate an opportunity to move shared functionality into a common utility file.

---

## Limitations

This project performs **static analysis**.

It does not execute the FiveM resource.

Because Lua and FiveM resources can use dynamic behavior, the analyzer may produce false positives or miss relationships in some situations.

For example:

* dynamically generated function names
* dynamically generated events
* metatables
* complex Lua patterns
* functions created at runtime
* obfuscated code
* indirect function calls

The results should therefore be treated as analysis hints rather than absolute proof.

---

## Roadmap

Possible future improvements:

* [ ] Better Lua AST parsing
* [ ] Advanced call graph generation
* [ ] Interactive dependency graph
* [ ] HTML reports
* [ ] JSON export
* [ ] Resource dependency detection
* [ ] Unused function detection
* [ ] Unused event detection
* [ ] Event flow visualization
* [ ] Better QBCore analysis
* [ ] Better ox_lib analysis
* [ ] Config dependency analysis
* [ ] Cross-resource analysis
* [ ] Web-based interface

---

## Project Structure

```text
FiveM-Resource-Analyzer/
│
├── FiveMduptool.py
├── README.md
├── LICENSE
└── .gitignore
```

---

## Contributing

Contributions, improvements, and bug reports are welcome.

If you find an issue or have an idea for improving the analyzer, feel free to open an issue or submit a pull request.

---

## License

This project is licensed under the MIT License.

See `LICENSE` for more information.

---

## Author

**REYOF**

FiveM Developer • Cybersecurity • Offensive Security • Low-Level Systems

Built for analyzing, understanding, and improving FiveM resources.

---

## Disclaimer

This tool is intended for legitimate development, debugging, auditing, and code-maintenance purposes.

Only analyze resources and code that you have permission to inspect.

---

> **REYOF Analyze. Understand. Refactor.**
