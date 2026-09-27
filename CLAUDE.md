# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running

```bash
python pomodoro.py
```

There is no build step, no dependency install, and no test suite. The app uses only the
Python standard library (`tkinter`, `enum`) — there is no `requirements.txt`, and that is
deliberate. `python -m py_compile pomodoro.py` is the closest thing to an automated check
available here.

It is a Tkinter desktop window, so it needs a graphical display; it is not runnable
headless. UI strings, comments, and docstrings are Chinese.

## Architecture

Everything lives in `pomodoro.py` as a single `PomodoroApp` class driving one Tkinter window.

**State** — six attributes set in `__init__`: `phase` (a `Phase` enum member), `remaining`
and `total` (seconds in the current phase), `running`, `completed` (finished pomodoros),
and `_job` (the pending `after()` id).

**Timing is a self-rescheduling `after()` chain, not a wall-clock deadline.** `_start`
schedules `_tick` one second out; `_tick` decrements `remaining`, re-renders, and reschedules
itself. Two consequences:

- A blocked event loop makes the countdown drift slow, and pause/resume discards partial
  elapsed time. Nothing corrects against real time.
- `_pause` **must** cancel `_job` and set it to `None`. Any new code path that stops the
  timer without doing this leaves the old chain running alongside the new one, and the
  countdown advances at double speed. `reset` and `skip` both route through `_pause` for
  exactly this reason.

**Phase transitions happen only in `_advance`.** A finished WORK phase increments `completed`
and selects `LONG_BREAK` every `POMODOROS_BEFORE_LONG` pomodoros, otherwise `SHORT_BREAK`;
any break returns to `WORK`. `skip` calls `_advance` directly, so skipping a work phase still
counts it as completed.

**`_render` is the only function that writes to the UI**, and every state change ends by
calling it. It fully clears and redraws the canvas (`delete("all")`) rather than updating
widgets incrementally, so a full redraw on every tick is expected and there is no stale
widget state to sync by hand. Note `_set_phase` calls `_render` itself.

**`PHASE_STYLE` is the single source of truth for per-phase presentation**: it maps
`Phase → (theme color, Chinese label, duration in minutes)`. Durations come from the
`WORK_MIN` / `SHORT_BREAK_MIN` / `LONG_BREAK_MIN` constants at the top of the file. The
color constants above it are a light warm palette; `shade(color, factor)` derives the
darker button hover/active variants.

## Customizing

- **Durations and long-break cadence** — the `*_MIN` constants and `POMODOROS_BEFORE_LONG`
  at the top of the file.
- **Colors** — the palette block; `shade(color, factor)` produces the active-state variant.
- **Adding or reordering a phase** — this is *not* purely data-driven. Add the `Phase`
  member, add its `PHASE_STYLE` entry, and add the branch in `_advance` that decides what
  follows it. `_counter_text` groups its 🍅 marks by `POMODOROS_BEFORE_LONG`.

## Platform notes

The app targets Windows even though it is stdlib-only:

- `_notify` imports `winsound` inside a `try` and falls back to `root.bell()`, so it still
  runs elsewhere but loses the system alert sound.
- Fonts are hardcoded to Windows families (`Microsoft YaHei UI`, `Consolas`).
