---
name: gil-companion
description: Open or focus the persistent GIL Monitor when the user asks to show, open, pin, keep visible, or monitor GIL, its journey, Step DAG, or current Cycle.
---

# GIL Monitor

The GIL Monitor is the **persistent human surface** on the user's journey. It is not an optional
extra: an installation is complete only when the agent can call GIL *and* a human can open a
persistent Monitor.

Two surfaces can carry it, in this order:

1. **persistent host** — the host itself shows the shared Monitor UI in a lasting panel or PiP
2. **native companion** — the installed desktop app shows the same UI in its own window

Use `gil_companion_status` to read what is actually available. Use `show_gil_companion` to open
the Monitor. The second one handles the whole sequence itself, including starting a closed
Companion and resuming the original request once it answers.

## What the tools report

`gil_companion_status` returns the availability read model:

- `agent_surface` — `ready` or `unavailable`
- `monitor_surface` — `persistent_host`, `native_companion`, or `unavailable`
- `companion_state` — `missing`, `stopped`, `outdated`, or `ready`

`show_gil_companion` reports what actually happened:

- `opened_persistent_host` — the host's own persistent surface was used
- `focused_existing_companion` — the window was already open and is now in front
- `started_and_opened_companion` — the app was closed; it was started, its handshake was
  confirmed, and then the window was brought forward
- `needs_companion_install` — nothing is installed; ask before installing anything
- `needs_companion_update` — an incompatible version is installed; it is not opened
- `monitor_unavailable` — no persistent surface could be opened right now

Never restate `needs_companion_install`, `needs_companion_update`, or `monitor_unavailable` as
success. `ready` requires a fresh runtime challenge; process names and paths are not evidence
of compatibility.

## When the Monitor cannot open

Say so plainly and keep working. GIL's text loop and its record of the journey do not depend on
the Monitor:

> Monitor를 열 수 없지만 GIL 기록 작업은 계속할 수 있다.

`gil context` still shows where the journey stands.

## Rules

- Do not substitute `gil monitor`, a browser page, a local server, or filesystem inspection.
- Do not search for or run an executable path yourself; the tools use a fixed bundle identity.
- Do not install, download, or update anything without the user's explicit approval.
- Do not choose or guess a GIL Project. The user picks projects inside the window.
- The window shows whichever project the user last selected. If they want a different one,
  tell them to use **폴더 열기** in the window — not a shell command.
- Do not show the user a path, port, PID, or socket. They are not part of the Monitor's
  vocabulary.
- If the tools are unavailable, say the plugin MCP server is not connected. Do not reinterpret
  the GIL Monitor as something you can open another way.

## A note on persistent host surfaces

`monitor_surface` is `persistent_host` only when a real probe has confirmed it — the app's
declared display modes, the host's advertised capability, the raw return of a user-initiated
mode request, and the observed mode and surface lifetime. Until that probe exists, the host
surface is *unverified*, which is **not** the same as unsupported. The Companion is used in the
meantime.
