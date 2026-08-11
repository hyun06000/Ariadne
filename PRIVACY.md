# Privacy Policy — gil

_Last updated: 2026-08-11_

gil is a local command-line tool and MCP server. It records an agent's reasoning history
(hypotheses, verifications, verdicts) as commits in a git repository on your own machine.

**The short version: gil runs entirely on your computer. There is no gil server, no account,
and no telemetry. Nothing you write is sent anywhere.**

## What gil collects

**Nothing is collected by us.** gil has no backend and we operate no service that receives
your data. gil reads and writes only:

- **The git repository you point it at** — chain, cycle, and step commits; the interview
  answers you type; the reference criteria you write. These are ordinary git objects in
  your repository's `.git` directory.
- **The existence records** (`refs/gil/global`) — the agent identity, will, relations, and
  memory documents, stored as a git ref in that same repository. If you have configured a
  git remote and push, they go wherever your remote is — that destination is yours, not ours.
- **Local diagnostic files, only when you turn them on** — `GIL_MCP_LOG=<path>` writes the
  raw MCP protocol frames to a file you name; `GIL_UI_PROBE=1` makes the on-screen card
  report its own state back to the local server process. Both are off by default. The frame
  log contains repository paths and tool arguments, so treat it as you would any debug log.

gil does **not** read your chat history, conversation summaries, memory, or unrelated files
on your machine. It does not collect conversation data beyond the arguments a tool is called
with, and those are used only to run that command.

## Network access

gil makes exactly one kind of outbound request, and only to check whether a newer release
exists:

- `GET https://api.github.com/repos/hyun06000/Ariadne/releases/latest`, falling back to the
  public `https://github.com/hyun06000/Ariadne/releases/latest` redirect.

These requests are unauthenticated and send no information about you, your repository, or
your usage — only the standard HTTP request a browser would make. They are rate-limited to
roughly one lookup per repository per hour. Builds from source skip the check entirely.

Any other network traffic is your own: if you push a git repository to a remote, that is
your git client talking to your remote.

## Storage and retention

All data stays in your repository and on your disk. gil does not upload, back up, or expire
anything. You control retention entirely — deleting the repository deletes everything gil
wrote. Temporary files gil creates to pass document bodies between processes are removed at
the end of the call that created them.

## Third-party sharing

**None.** We do not share, sell, or transfer your data, because we never receive it. gil has
no analytics, no crash reporting, and no third-party SDKs.

When gil runs as an MCP server, the MCP host application (for example Claude Desktop) sends
tool arguments to gil and displays gil's responses. That exchange is governed by your host
application's own privacy policy, not this one.

## Children

gil is a developer tool and is not directed at children under 13.

## Changes

Material changes to this policy will be published in this file, and the "Last updated" date
above will change. The file's full history is public in this repository.

## Contact

Questions or reports: <https://github.com/hyun06000/Ariadne/issues>

Source code: <https://github.com/hyun06000/Ariadne> (MIT licensed)
