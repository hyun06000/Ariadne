// **Agent 가 부를 GIL Core** — Plugin 안에 실린 binary 하나를 연다.
//
// 여기서 하지 않는 일이 이 파일의 뜻이다:
//
//   shell · `sh -c` · command 문자열 조립        쓰지 않는다 — argv 로만 부른다
//   domain 규칙 복제 · Report 필드 하드코딩      하지 않는다 — Core 가 최종 판정한다
//   Core 의 산문을 해석·요약·재작성              하지 않는다 — 원문 그대로 나른다
//   `.gil` 직접 읽기·쓰기                        하지 않는다
//   전역 `gil`·Cargo·저장소·Go 유물로 물러서기   하지 않는다
//
// 성패는 **종료 코드**로만 가른다. 산문 안의 문장을 substring 으로 검사하면, Core 가 말을
// 다듬는 순간 Plugin 이 조용히 틀린 판정을 하게 된다.

import { spawn } from "node:child_process";
import { access, constants } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { AGENT_CORE_STATE } from "./capability.mjs";

/** 이 파일이 사는 자리. Plugin root 기준 상대경로만 쓴다 — 설치본은 어디로든 옮겨진다. */
const ROOT = dirname(fileURLToPath(import.meta.url));

// 상태의 어휘는 판정의 자리인 `capability.mjs` 가 소유한다. 여기서 다시 적으면 두 곳이 된다.
export { AGENT_CORE_STATE as AGENT_STATE };

/** node 가 말하는 기계 ↔ 실린 binary 의 자리. 없는 자리는 **실행하지 않는다.** */
const SLOTS = {
  "darwin/arm64": { slot: "darwin-arm64", os: "macos", arch: "aarch64" },
};

/** Plugin 과 Core **사이**의 계약. 이 둘이 어긋나면 부를 수 없다. */
export const EXPECTED = {
  product: "gil_core",
  schemaVersion: 1,
  protocol: 1,
  actionSurface: 1,
};

/** 한 번 부르는 데 주는 시간. 무한히 매달리지 않는다. */
export const CALL_TIMEOUT_MS = 30_000;
const HANDSHAKE_TIMEOUT_MS = 5_000;

function slotForThisMachine() {
  return SLOTS[`${process.platform}/${process.arch}`] || null;
}

function covers(range, wanted) {
  return Number.isInteger(range?.min) && Number.isInteger(range?.max)
    && range.min <= wanted && wanted <= range.max;
}

/** identity 와 **Plugin 이 거는 두 범위**만 본다.
 *
 *  저장 format 은 일부러 판정하지 않는다 — 그것은 Core 가 Project 를 열 때 스스로 거절하는
 *  일이고, Plugin 이 따라 적으면 판정이 두 자리에 살게 된다. descriptor 에 실어 나르되
 *  문지기로 쓰지는 않는다. */
export function compatible(said, machine) {
  return said?.schema_version === EXPECTED.schemaVersion
    && said.product === EXPECTED.product
    && typeof said.core_version === "string" && said.core_version.length > 0
    && covers(said.protocol, EXPECTED.protocol)
    && covers(said.action_surface, EXPECTED.actionSurface)
    && said.os === machine.os
    && said.arch === machine.arch;
}

/** argv 로만 부른다. 사용자 입력은 **인자 값**이 되지, 실행 파일도 flag 이름도 되지 않는다. */
function runFile(exe, argv, { input = null, timeoutMs = CALL_TIMEOUT_MS, cwd } = {}) {
  return new Promise((done) => {
    let kid;
    try {
      kid = spawn(exe, argv, { cwd, stdio: ["pipe", "pipe", "pipe"] });
    } catch {
      done({ ok: false, exit_code: null, said: "", problem: "", spawned: false });
      return;
    }
    let out = "", err = "", settled = false;
    const finish = (exit_code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      done({ ok: exit_code === 0, exit_code, said: out, problem: err, spawned: true });
    };
    const timer = setTimeout(() => { kid.kill("SIGKILL"); finish(null); }, timeoutMs);
    kid.stdout.on("data", (d) => { out += d; });
    kid.stderr.on("data", (d) => { err += d; });
    kid.on("error", () => { if (!settled) { settled = true; clearTimeout(timer);
      done({ ok: false, exit_code: null, said: "", problem: "", spawned: false }); } });
    kid.on("close", (code) => finish(code));
    if (input !== null) { kid.stdin.end(input); } else { kid.stdin.end(); }
  });
}

/** 실린 Core 가 지금 이 기계에서 **실제로 답하는가.** 파일의 존재는 증거가 아니다. */
export async function probeCore({ root = ROOT, challenge = null } = {}) {
  const machine = slotForThisMachine();
  if (!machine) {
    return { state: AGENT_CORE_STATE.unavailable, why: "unsupported_platform", descriptor: null, exe: null };
  }
  const exe = join(root, "core", machine.slot, "gil");
  try {
    await access(exe, constants.X_OK);
  } catch {
    // 없거나, 있어도 실행할 수 없다. 둘 다 부를 수 없는 것은 같다.
    return { state: AGENT_CORE_STATE.unavailable, why: "core_not_executable", descriptor: null, exe: null };
  }

  const asked = challenge || `plugin_probe_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
  const got = await runFile(exe, ["--gil-agent-probe", asked], { timeoutMs: HANDSHAKE_TIMEOUT_MS });
  if (!got.ok) {
    return { state: AGENT_CORE_STATE.unavailable, why: "core_did_not_answer", descriptor: null, exe: null };
  }

  let replied;
  try { replied = JSON.parse(got.said); } catch {
    return { state: AGENT_CORE_STATE.unavailable, why: "core_answer_unreadable", descriptor: null, exe: null };
  }
  // **이번에 준 challenge** 가 돌아와야 한다. 예전 답을 다시 보여 주는 것을 막는다.
  if (replied?.challenge !== asked) {
    return { state: AGENT_CORE_STATE.unavailable, why: "challenge_not_returned", descriptor: null, exe: null };
  }
  const said = replied.core;
  if (said?.product !== EXPECTED.product) {
    // 이름부터 다른 것은 낡은 판이 아니라 **다른 물건**이다.
    return { state: AGENT_CORE_STATE.unavailable, why: "identity_mismatch", descriptor: said ?? null, exe: null };
  }
  if (!compatible(said, machine)) {
    return { state: AGENT_CORE_STATE.outdatedAgent, why: "range_mismatch", descriptor: said, exe: null };
  }
  return { state: AGENT_CORE_STATE.ready, why: null, descriptor: said, exe };
}

/** Agent 의 한 동작. 허용된 subcommand 하나에만 대응하는 자리에서만 불린다. */
export async function callCore(exe, argv, { input = null, cwd } = {}) {
  const got = await runFile(exe, argv, { input, cwd });
  if (!got.spawned) {
    return { ok: false, exit_code: null, said: "", problem: "", ran: false };
  }
  // stdout 과 stderr 를 **합치지 않는다.** Core 는 성공을 stdout 에, 거절을 stderr 에 쓰고
  // 둘을 함께 쓰지 않으므로, 따로 두면 순서도 출처도 잃지 않는다. 합치면 어느 쪽이 한 말인지
  // 사라지고, 우리가 문장을 지어내야 하는 자리가 생긴다.
  return { ok: got.ok, exit_code: got.exit_code, said: got.said, problem: got.problem, ran: true };
}
