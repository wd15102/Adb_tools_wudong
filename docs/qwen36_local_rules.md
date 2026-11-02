# Qwen3.6 Local Running Rules (DSH Harness)

> For qwen3.6-35b-1m running in DeepSeek Harness.

---

## 1. TypeScript Code Pitfalls in run_code

### 1.1 Variable declarations must be strict
- Every variable MUST use const/let/var. Never skip the keyword.

### 1.2 JS syntax errors are the main cause of interruptions
- Missing semicolons, unmatched brackets, ${} interpolation
- import/export cannot be used directly in async function body
- require() is NOT available (ESM environment)
- LESSON: Keep code minimal. Less nesting, less complexity.

### 1.3 String escaping
- JS template strings: ${...} triggers interpolation. Avoid in PS/Python code.
- Unicode in JS templates: works for file writing but NOT for console output.
- Python print with Chinese chars -> GBK console error.
- LESSON: Use pure ASCII for Python code. Build Chinese with chr().

### 1.4 spawnSync is more reliable than spawn+Promise
- spawnSync is synchronous, no Promise management needed.
- For simple cases, prefer spawnSync.

### 1.5 Timeout must be reasonable
- Never set 180000ms timeout. Worst case: wait 3 minutes for nothing.
- Reasonable: Python compile 10s, import 60s, PowerShell 30s.

---

## 2. Python File Operations

### 2.1 Do not write Chinese characters via JS templates
- Chinese chars may corrupt when written through JS.
- LESSON: Write Python files with ASCII, add Chinese content separately.

### 2.2 Always verify after writing
- Use py_compile immediately after writing Python files.
- Never assume the content is correct.

### 2.3 Clean up temp files
- Delete test scripts immediately after use.

---

## 3. Git Operations

### 3.1 safe.directory issue
- Windows git often reports "dubious ownership".
- Fix: set HOME env var + use --global config.
- Always keep git config in a persistent location.

### 3.2 Always check diff before commit
- Never blindly git add -A.
- Use git status --short first.

### 3.3 Update .gitignore BEFORE staging
- Order: add .gitignore -> add files -> commit.

### 3.4 Verify SSH key before push
- Check ~/.ssh/ for keys before pushing.

---

## 4. General Principles

### 4.1 One thing per run_code call
- Do NOT combine file writing, testing, and git in one call.
- Split into steps, verify each before continuing.

### 4.2 Do not over-verify
- One verification is enough. Do not repeatedly check the same thing.

### 4.3 Speed up when user is impatient
- Reduce intermediate reports.
- Confirm critical steps (git push) but move fast.

### 4.4 Error recovery strategy
- When run_code fails: STOP and analyze, do not keep retrying.
- JS syntax error: rewrite the whole block, do not patch.
- Python syntax error: check file content, not the code logic.

---

## 5. Lessons from This Task

| # | Problem | Lesson |
|---|---------|--------|
| 1 | run_code crashed repeatedly | Minimal code, declare all vars |
| 2 | PowerShell could not get IPv4 | Check PS commands char by char |
| 3 | Empty popup window | Check widget layout (pack/grid) |
| 4 | PowerShell command errors | Test empirically, dont guess |
| 5 | Temp files not cleaned | Clean after each step |
| 6 | Import test timed out | Set timeout to 60s max |
| 7 | safe.directory config lost | Put git config in persistent path |

---

## 6. Pre-commit Checklist

- [ ] All temp files deleted
- [ ] Python syntax verified
- [ ] Import test passed
- [ ] Functionality tested
- [ ] git status is clean
- [ ] git push succeeded
- [ ] Reported results to user

---
*Last updated: 2026-11-02*