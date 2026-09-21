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
    agentReady: true,   // 이 tool 이 답하고 있다는 것 자체가 Agent 표면의 증거다
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
      appVersion: z.string().nullable(),
      said: z.string(),
    }),
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  },
  async () => {
    const ports = realPorts();
    const hostSurface = await ports.host.surface();
    const seen = await ports.companion.state();
    const installation = installationOf({
      agentReady: ports.agentReady,
      hostSurface,
      companionState: seen.state,
    });
    const appVersion = seen.descriptor?.app_version ?? null;
    const said = assertNoLeak(sayState(seen.state, appVersion));
    const structuredContent = {
      ...installation,
      companion_state: seen.state,
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

if (process.env.GIL_COMPANION_NO_SERVE !== "1") {
  await server.connect(new StdioServerTransport());
}
