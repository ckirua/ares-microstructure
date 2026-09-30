# Auto-advance chapter research loop

## Pipeline status: **COMPLETE**

Ch.1 · Ch.2 · Ch.3 · App.A are all shipped under the MM quality bar (NOTES + CANDIDATES + EXP_REPORT + notebook + `out/`).  
**Do not invent new chapters.** Further `/loop` ticks should **no-op** or only fix clear index/doc gaps — do **not** reopen finished chapter packages without cause.

| Package | Status |
|---------|--------|
| Ch.1 fragmentation | **COMPLETE** |
| Ch.2 stakes | **COMPLETE** |
| Ch.3 optimal trading | **COMPLETE** |
| App.A quantitative appendix | **COMPLETE** |

Optional light polish only: Hold-list iterates listed in `CHAPTER_INDEX.md` (spatial trade FEI, mean–var λ, Harris MLE, finer Epps).

---

## Tick policy (armed loop)

If `AGENT_LOOP_TICK_microstructure` still fires:

1. Read this file + `CHAPTER_INDEX.md`.
2. If all four packages remain `exp_run` complete → **no-op** (confirm pipeline complete; do not re-run experiments).
3. Only act if something is **clearly missing** from the index (broken path, missing Promote rollup entry, sibling artifact not indexed).
4. Never reopen Ch.1–3 / App.A research without an explicit user request or a documented gap.

### Prompt (idle ticks)

```text
ares-microstructure pipeline COMPLETE (Ch.1–3 + App.A).
No-op unless CHAPTER_INDEX/LOOP show a clear gap. Do not reopen finished chapters
or invent new ones. ClickHouse MCP banned. No commits unless asked.
```

---

## Parallel ownership (historical)

| Role | Scope | Outcome |
|------|--------|---------|
| Coordinator + Ch.2 | Ch.2 + index/LOOP | Done |
| Sibling | Ch.3 | Done |
| Sibling | App.A | Done |

## Quality bar — MM / quant desk grade (archived requirement)

Still the bar for any future iterate: precise defs, formulas, D/T/E labels, hygiene, MM relevance, notebook structure, Promote/Hold/Kill.

## Mechanism (local IDE)

- **Interval:** 20m (`sleep 1200`) if still armed
- **Sentinel:** `AGENT_LOOP_TICK_microstructure`
- **PID file:** `research/.loop_microstructure.pid`
- **Stop:** `kill "$(cat research/.loop_microstructure.pid)"` when idle ticks are no longer wanted

## Current pointer

| Field | Value |
|-------|-------|
| **Pipeline** | **COMPLETE** |
| **Ch.1–3 + App.A** | all `exp_run` |
| **Next action** | no-op / optional Hold iterates only |
| **Promote rollup** | top of `CHAPTER_INDEX.md` |
| **Loop behavior** | idle no-op (do not reopen chapters) |
| **Quality bar** | MM-desk grade |
| **Loop armed** | yes (may leave running; ticks should no-op) |

Update this table only if status changes.
