// **GIL Monitor launcher** — 사람이 여정을 볼 수 있게 하는 한 가지 일만 한다.
//
// 이 server 는 설치된 `GIL Companion.app` 을 열거나, 이미 떠 있으면 그 창을 앞으로 보낸다.
// 창 하나만 사는 것은 앱의 single-instance 가 지킨다.
//
// # 하지 않는 일
//
//   browser UI · loopback server · port · capability URL      만들지 않는다
//   fixture 사실을 live Project 처럼 보여 주기                  하지 않는다
//   Project 짐작 · `.gil` 읽기 · Graph·Artifact·Journey 쓰기    하지 않는다
//   사용자 승인 없이 내려받기 · 설치 · 업데이트                  하지 않는다
//
// 예전 판은 fixture 로 만든 Cycle 목록을 widget 으로 띄웠다. 그것은 UI 시제품이었고, 살아
// 있는 Project 의 사실이 아니었다 — 같은 도구 이름으로 가짜를 보여 주면 사람이 그 둘을
// 구별할 수 없다. 그래서 이 판은 **사실을 나르지 않는다.** 창을 여는 일만 한다.
//
// # 명령을 글자로 잇지 않는다
//
// 실행은 **고정된 bundle identifier** 하나로만 한다. 사용자의 입력도, 임의의 경로도
// 명령줄에 이어 붙이지 않는다. shell 을 거치지 않는 `execFile` 만 쓴다.
//
// # 판정은 한 자리에서
//
// 무엇을 열 수 있는지는 `capability.mjs` 가 정하고, 사람에게 할 말은 `say.mjs` 가 만든다.
// 여기 남는 것은 **바깥 세계에 닿는 부분**뿐이다 — 그것이 시험에서 갈아 끼우는 자리다.

import { execFile } from "node:child_process";
import { randomBytes } from "node:crypto";
import { promisify } from "node:util";
import { access } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import {
  COMPANION_STATE, DEFAULT_POLICY, HOST_SURFACE, OUTCOME,
  installationOf, openMonitor,
} from "./capability.mjs";
import { ACTIONS, argvFor } from "./actions.mjs";
import { callCore, probeCore } from "./core.mjs";
import { assertNoLeak, sayOutcome, sayState } from "./say.mjs";

const run = promisify(execFile);

/** 이 앱의 **유일한 이름**. 어디서도 조립하지 않는다. */
const BUNDLE_ID = "dev.ariadne.gil.companion";
const APP_NAME = "GIL Companion";
const HANDSHAKE_ARG = "--gil-companion-handshake";
const PROBE_ARG = "--gil-companion-probe";
const PROTOCOL_VERSION = 1;
const VIEW_SCHEMA_VERSION = 1;
/** 설치되어 있을 수 있는 자리. 사용자 영역이 먼저다. */
const PLACES = [
  join(homedir(), "Applications", `${APP_NAME}.app`),
  join("/Applications", `${APP_NAME}.app`),
];

async function installedAt() {
  for (const place of PLACES) {
    try {
      await access(place);
      return place;
    } catch {
      /* 다음 자리를 본다 */
    }
  }
  return null;
}

function binaryAt(place) {
  return join(place, "Contents", "MacOS", APP_NAME);
}

function covers(range, wanted) {
  return Number.isInteger(range?.min) && Number.isInteger(range?.max)
    && range.min <= wanted && wanted <= range.max;
}

function compatible(one) {
  return one?.schema_version === 1
    && one.product === "gil_companion"
    && one.bundle_id === BUNDLE_ID
    && typeof one.app_version === "string"
    && covers(one.protocol, PROTOCOL_VERSION)
    && covers(one.monitor_view_schema, VIEW_SCHEMA_VERSION)
    && covers(one.node_detail_schema, VIEW_SCHEMA_VERSION);
}

async function descriptorOf(executable) {
  try {
    const { stdout } = await run(executable, [HANDSHAKE_ARG], {
      timeout: DEFAULT_POLICY.probeTimeoutMs,
      maxBuffer: 16 * 1024,
    });
    const said = JSON.parse(stdout);
    return compatible(said) ? said : null;
  } catch {
    return null;
  }
}

/** 실행 중인 process 가 **새 challenge** 를 그대로 돌려주는가.
 *  PID·process 이름은 호환성의 증거가 아니다. */
async function answersFreshChallenge(executable, described) {
  const challenge = randomBytes(24).toString("base64url");
  try {
    const { stdout } = await run(executable, [PROBE_ARG, challenge], {
      timeout: DEFAULT_POLICY.probeTimeoutMs,
      maxBuffer: 32 * 1024,
    });
    const said = JSON.parse(stdout);
    return said?.schema_version === 1
      && said.challenge === challenge
      && JSON.stringify(said.companion) === JSON.stringify(described);
  } catch {
    return false;
  }
}

/** 바깥 세계에 닿는 문들. 시험은 이 셋만 갈아 끼운다. */
export function realPorts() {
  let found = null;

  return {
    // 이 tool 이 답한다는 사실은 **Companion launcher 가 살아 있다**는 뜻일 뿐,
    // Agent 가 GIL 을 부를 수 있다는 뜻이 아니다. 실린 Core 에게 직접 묻는다.
    agent: { state: async () => (await probeCore()).state },
    clock: { sleep: (ms) => new Promise((go) => setTimeout(go, ms)) },
    host: {
      // 정식 `ui://` probe 가 앱 선언·Host 광고·요청 반환값·mode 변경 event 를 함께
      // 기록하기 전까지는 **확인되지 않음**이다. 미지원이라고 단정하지 않는다.
      // 미래 Host adapter 가 실제 판정을 넣을 자리가 여기다.
      surface: async () => HOST_SURFACE.unverified,
      open: async () => {
        throw new Error("확인된 지속형 Host surface 가 없다");
      },
    },
    companion: {
      async state() {
        const place = await installedAt();
        if (!place) {
          found = null;
          return { state: COMPANION_STATE.missing, descriptor: null };
        }
        const executable = binaryAt(place);
        const described = await descriptorOf(executable);
        found = { executable, descriptor: described };
        if (!described) return { state: COMPANION_STATE.outdated, descriptor: null };
        const ready = await answersFreshChallenge(executable, described);
        return {
          state: ready ? COMPANION_STATE.ready : COMPANION_STATE.stopped,
          descriptor: described,
        };
      },
      // 실행과 앞으로 가져오기는 macOS 에서 같은 동작이다 — 이미 떠 있으면 그 창이
      // 앞으로 오고, 아니면 뜬다. 둘을 따로 둔 것은 **뜻이 다르기 때문**이고,
      // coordinator 가 그 둘을 다른 결과로 보고하기 때문이다.
      launch: () => openByIdentity(),
      focus: () => openByIdentity(),
      probeReady: (descriptor) =>
        found?.executable
          ? answersFreshChallenge(found.executable, descriptor)
          : Promise.resolve(false),
    },
  };
}

async function openByIdentity() {
  try {
    await run("open", ["-b", BUNDLE_ID]);
    return true;
  } catch {
    // 실패 이유는 OS 문구이고 거기에는 경로가 들어 있다. 밖으로 내보내지 않는다.
    return false;
  }
}

const server = new McpServer(
  { name: "gil-companion", version: "0.3.0" },
  { capabilities: { tools: {} } },
);

server.registerTool(
  "gil_companion_status",
  {
    title: "Check GIL Monitor availability",
    description:
      "Report whether a persistent human Monitor surface is available: the agent surface, the monitor surface, and the native Companion handshake state (missing, stopped, outdated, ready). Does not read or write a project.",
    inputSchema: z.object({}),
    outputSchema: z.object({
      agent_surface: z.enum(["ready", "unavailable"]),
      monitor_surface: z.enum(["persistent_host", "native_companion", "unavailable"]),
      companion_state: z.enum(["missing", "stopped", "outdated", "ready"]),
      agent_state: z.enum(["ready", "outdated_agent", "unavailable"]),
      appVersion: z.string().nullable(),
      said: z.string(),
    }),
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  },
  async () => {
    const ports = realPorts();
    const hostSurface = await ports.host.surface();
    const seen = await ports.companion.state();
    const agentState = await ports.agent.state();
    const installation = installationOf({ agentState, hostSurface, companionState: seen.state });
    const appVersion = seen.descriptor?.app_version ?? null;
    const said = assertNoLeak(sayState(seen.state, appVersion));
    const structuredContent = {
      ...installation,
      companion_state: seen.state,
      agent_state: agentState,
      appVersion,
      said,
    };
    return { structuredContent, content: [{ type: "text", text: said }] };
  },
);

server.registerTool(
  "show_gil_companion",
  {
    title: "Show GIL Monitor",
    description:
      "Open the persistent GIL Monitor for the user. Use when the user asks to open, show, pin, or keep the GIL monitor visible. If the native Companion is installed but closed, it is started and the original request is resumed automatically once its handshake answers. Read-only: it never reads or writes the project, and never installs anything.",
    inputSchema: z.object({}),
    outputSchema: z.object({
      result: z.enum([
        "opened_persistent_host",
        "focused_existing_companion",
        "started_and_opened_companion",
        "needs_companion_install",
        "needs_companion_update",
        "monitor_unavailable",
      ]),
      agent_surface: z.enum(["ready", "unavailable"]),
      monitor_surface: z.enum(["persistent_host", "native_companion", "unavailable"]),
      said: z.string(),
    }),
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
    _meta: {
      "openai/toolInvocation/invoking": "GIL Monitor 를 여는 중…",
      "openai/toolInvocation/invoked": "GIL Monitor 를 앞으로 가져왔습니다.",
    },
  },
  async () => {
    const settled = await openMonitor(realPorts());
    const said = assertNoLeak(sayOutcome(settled.outcome));
    return {
      structuredContent: { result: settled.outcome, ...settled.installation, said },
      content: [{ type: "text", text: said }],
      // 열지 못한 것을 열었다고 말하지 않는다. 다만 GIL 자체는 계속 쓸 수 있다.
      isError: settled.outcome === OUTCOME.needsCompanionInstall
        || settled.outcome === OUTCOME.needsCompanionUpdate
        || settled.outcome === OUTCOME.monitorUnavailable,
    };
  },
);


// ── Agent 가 부르는 GIL ──────────────────────────────────────────────
//
// 명령표는 `actions.mjs` 에 있고, 여기서는 그 표를 **그대로** MCP 로 편다. tool 하나가
// 허용된 subcommand 하나에만 대응하며, 자유 형식 command 를 받는 문은 만들지 않는다.

/** Project 자리는 **명시적으로** 받는다. cwd 나 최근 폴더를 짐작하지 않고,
 *  Companion 이 사람에게 보여 주는 선택을 몰래 빌리지도 않는다 — 사람이 보는 것과
 *  Agent 가 고치는 것이 달라도 되어야 한다. */
const PROJECT_ROOT_SAID =
  "Absolute path of the GIL project to act on. The host-verified workspace root, or a path the user named. It is never guessed.";

async function usableDirectory(root) {
  if (typeof root !== "string" || root.length === 0) return "Project 자리가 비었다";
  try {
    const { stat } = await import("node:fs/promises");
    const seen = await stat(root);
    if (!seen.isDirectory()) return "Project 자리가 폴더가 아니다";
  } catch {
    return "Project 자리를 열 수 없다";
  }
  return null;
}

function refusal(text) {
  // 우리가 만든 거절이다. Core 가 한 말과 섞이지 않게 `exit_code` 를 비워 둔다.
  return {
    structuredContent: { ok: false, exit_code: null, said: "", problem: text },
    content: [{ type: "text", text }],
    isError: true,
  };
}

for (const action of ACTIONS) {
  const shape = {};
  if (action.project) shape.project_root = z.string().describe(PROJECT_ROOT_SAID);
  else shape.project_root = z.string().optional().describe(PROJECT_ROOT_SAID);
  for (const slot of action.positional) {
    const one = z.string();
    shape[slot.key] = slot.required ? one : one.optional();
  }
  if (action.stdin) {
    // 본문은 사람이나 Agent 가 쓴 **글**이다. command 문자열이 아니다. 어떤 칸이
    // 필요한지는 Grammar 가 정하고 Core 가 판정한다 — 여기 베껴 적지 않는다.
    shape[action.stdin] = z.string().optional().describe(
      "Body text passed to GIL on stdin, exactly as written. GIL validates it.",
    );
  }

  server.registerTool(
    action.name,
    {
      title: action.title,
      description: `${action.summary} Runs the GIL core bundled with this plugin; never a global or repository build.`,
      inputSchema: z.object(shape),
      outputSchema: z.object({
        ok: z.boolean(),
        exit_code: z.number().int().nullable(),
        said: z.string(),
        problem: z.string(),
      }),
      annotations: {
        readOnlyHint: action.stdin === null && ["status", "context", "story", "help"].includes(action.subcommand),
        destructiveHint: false,
        openWorldHint: false,
      },
    },
    async (input) => {
      const seen = await probeCore();
      if (seen.state !== "ready") {
        // 부를 수 없으면 **부르지 않는다.** 성공을 가장하지 않고, 다른 gil 로 물러서지도 않는다.
        return refusal(
          `GIL core is not usable here (${seen.why}). GIL actions are unavailable until the plugin ships a core for this machine.`,
        );
      }
      const root = input?.project_root;
      if (action.project || root !== undefined) {
        const wrong = await usableDirectory(root);
        if (wrong) return refusal(wrong);
      }
      const built = argvFor(action, input);
      if (built.error) return refusal(built.error);

      const body = action.stdin ? input?.[action.stdin] : undefined;
      const got = await callCore(seen.exe, built.argv, {
        input: body === undefined ? null : String(body),
        cwd: root,
      });
      if (!got.ran) return refusal("GIL core did not run.");
      // Core 가 한 말을 **그대로** 나른다. 요약하지도 다시 쓰지도 않는다.
      // 성공은 종료 코드 하나로만 가른다 — 문장을 읽고 판단하지 않는다.
      return {
        structuredContent: { ok: got.ok, exit_code: got.exit_code, said: got.said, problem: got.problem },
        content: [{ type: "text", text: got.said + got.problem }],
        isError: !got.ok,
      };
    },
  );
}

if (process.env.GIL_COMPANION_NO_SERVE !== "1") {
  await server.connect(new StdioServerTransport());
}
