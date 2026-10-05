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

## Overview

**REYOF // FiveM Resource Analyzer** is a lightweight, dependency-free static analysis tool built for FiveM developers.

It recursively scans a FiveM resource and analyzes its Lua source code to identify:

- Duplicate functions
- Same-name functions with different implementations
- Similar function bodies
- Internal function relationships
- FiveM events
- Server/client event usage
- Callbacks
- Exports
- Resource-level code relationships

The goal is simple:

> **Understand what your FiveM resource contains, what is duplicated, and how its code is connected.**

---

## Features

### Duplicate Detection

Find functions that appear multiple times across your resource.

```text
🔴 EXACT DUPLICATES

toast()

├─ client/beds.lua:15-17
└─ client/main.lua:10-12

Same body: 100%
