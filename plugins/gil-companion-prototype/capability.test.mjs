// **capability coordinator 의 시험** — `node --test`
//
// 바깥 효과는 전부 가짜로 끼운다: launcher, handshake probe, 시계. production protocol 을
// 약하게 만들지 않고, 고정된 fixture 결과를 제품 코드에 넣지도 않는다. 갈아 끼우는 것은
// **경계**뿐이다.

import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, writeFile, readdir, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  AGENT_SURFACE, COMPANION_STATE, HOST_SURFACE, MONITOR_SURFACE, OUTCOME,
  installationOf, isComplete, openMonitor,
} from "./capability.mjs";
import { assertNoLeak, sayOutcome, sayState } from "./say.mjs";

/** 무엇이 실제로 불렸는지 세는 가짜 문. 시계는 잠들지 않고 **센다**. */
function fakePorts({ host = HOST_SURFACE.unverified, state, readyAfter = 0, canLaunch = true } = {}) {
  const log = [];
  let probes = 0;
  return {
    log,
    slept: [],
    ports: {
      agentReady: true,
      clock: {
        sleep(ms) {
          this.owner.slept.push(ms);
          return Promise.resolve();
        },
      },
      host: {
        surface: async () => { log.push("host.surface"); return host; },
        open: async () => { log.push("host.open"); return true; },
      },
      companion: {
        state: async () => {
          log.push("companion.state");
          return { state, descriptor: state === COMPANION_STATE.missing ? null : { app_version: "0.1.0" } };
        },
        launch: async () => { log.push("companion.launch"); return canLaunch; },
        focus: async () => { log.push("companion.focus"); return true; },
        probeReady: async () => {
          log.push("companion.probeReady");
          probes += 1;
          return readyAfter > 0 && probes >= readyAfter;
        },
      },
    },
  };
}

/** 시계가 자기 장부에 적을 수 있도록 묶는다. */
function ready(setup) {
  const made = fakePorts(setup);
  made.ports.clock.owner = made;
  return made;
}

// ── ① 표면 선택 순서 ────────────────────────────────────────────────

test("1. 확인된 Host surface 가 있으면 Companion 을 조회하지도 실행하지도 않는다", async () => {
  const made = ready({ host: HOST_SURFACE.verified, state: COMPANION_STATE.ready });
  const settled = await openMonitor(made.ports);

  assert.equal(settled.outcome, OUTCOME.openedPersistentHost);
  assert.equal(settled.installation.monitor_surface, MONITOR_SURFACE.persistentHost);
  assert.deepEqual(made.log, ["host.surface", "host.open"]);
  assert.ok(!made.log.some((one) => one.startsWith("companion.")), "Companion 을 건드렸다");
});

test("2. Host surface 가 없고 Companion 이 ready 이면 기존 창을 focus 한다", async () => {
  const made = ready({ state: COMPANION_STATE.ready });
  const settled = await openMonitor(made.ports);

  assert.equal(settled.outcome, OUTCOME.focusedExistingCompanion);
  assert.equal(settled.installation.monitor_surface, MONITOR_SURFACE.nativeCompanion);
  assert.deepEqual(made.log, ["host.surface", "companion.state", "companion.focus"]);
  assert.equal(made.log.filter((one) => one === "companion.launch").length, 0, "이미 떠 있는데 또 띄웠다");
});

test("3. stopped 이면 실행하고 fresh handshake 를 다시 한 뒤 자동으로 focus 한다", async () => {
  const made = ready({ state: COMPANION_STATE.stopped, readyAfter: 3 });
  const settled = await openMonitor(made.ports);

  assert.equal(settled.outcome, OUTCOME.startedAndOpenedCompanion);
  assert.deepEqual(made.log, [
    "host.surface", "companion.state", "companion.launch",
    "companion.probeReady", "companion.probeReady", "companion.probeReady",
    "companion.focus",
  ]);
  // 실행 → 재감지 → 원래 요청 재개. 사람이 같은 말을 두 번 하지 않는다.
  assert.ok(made.log.indexOf("companion.launch") < made.log.indexOf("companion.probeReady"));
  assert.ok(made.log.lastIndexOf("companion.probeReady") < made.log.indexOf("companion.focus"));
});

test("4. 실행 명령의 성공만으로 완료라고 답하지 않는다 — handshake 까지 확인한다", async () => {
  const made = ready({ state: COMPANION_STATE.stopped, readyAfter: 0, canLaunch: true });
  const settled = await openMonitor(made.ports);

  assert.notEqual(settled.outcome, OUTCOME.startedAndOpenedCompanion);
  assert.equal(settled.outcome, OUTCOME.monitorUnavailable);
  assert.equal(settled.why, "not_ready_after_launch");
  assert.ok(made.log.includes("companion.launch"), "실행은 했다");
  assert.ok(!made.log.includes("companion.focus"), "ready 가 아닌데 창을 앞으로 가져왔다");
});

test("5. 실행 뒤에도 ready 가 아니면 원래 요청을 성공으로 표시하지 않는다", async () => {
  const made = ready({ state: COMPANION_STATE.stopped, readyAfter: 0 });
  const settled = await openMonitor(made.ports);

  assert.equal(settled.outcome, OUTCOME.monitorUnavailable);
  assert.equal(settled.installation.monitor_surface, MONITOR_SURFACE.nativeCompanion);
  // 실행 자체가 실패한 경우도 성공이 아니다.
  const failed = ready({ state: COMPANION_STATE.stopped, canLaunch: false });
  const second = await openMonitor(failed.ports);
  assert.equal(second.outcome, OUTCOME.monitorUnavailable);
  assert.equal(second.why, "launch_failed");
  assert.ok(!failed.log.includes("companion.probeReady"), "실행도 못 했는데 handshake 를 물었다");
});

test("6. outdated 를 missing 이나 stopped 로 뭉개지 않는다", async () => {
  const seen = [];
  for (const state of [COMPANION_STATE.missing, COMPANION_STATE.outdated, COMPANION_STATE.stopped]) {
    const made = ready({ state, readyAfter: 1 });
    seen.push((await openMonitor(made.ports)).outcome);
  }
  assert.deepEqual(seen, [
    OUTCOME.needsCompanionInstall,
    OUTCOME.needsCompanionUpdate,
    OUTCOME.startedAndOpenedCompanion,
  ]);

  // outdated 는 지금 판을 ready 처럼 열지 않는다.
  const made = ready({ state: COMPANION_STATE.outdated });
  await openMonitor(made.ports);
  assert.ok(!made.log.includes("companion.launch"));
  assert.ok(!made.log.includes("companion.focus"));
  assert.equal(
    installationOf({ agentReady: true, hostSurface: HOST_SURFACE.unverified, companionState: COMPANION_STATE.outdated })
      .monitor_surface,
    MONITOR_SURFACE.unavailable,
  );
});

test("7. missing 에서는 사용자 승인 없는 설치를 시작하지 않는다", async () => {
  const made = ready({ state: COMPANION_STATE.missing });
  const settled = await openMonitor(made.ports);

  assert.equal(settled.outcome, OUTCOME.needsCompanionInstall);
  assert.deepEqual(made.log, ["host.surface", "companion.state"]);
  // 설치·내려받기·실행 어느 것도 하지 않는다. 다음 행동만 제안한다.
  assert.ok(!made.log.includes("companion.launch"));
  assert.match(sayOutcome(settled.outcome), /승인/);
});

// ── ② degraded mode ─────────────────────────────────────────────────

test("8. Host 와 Companion 이 모두 없어도 Agent 표면은 살아 있다", async () => {
  const made = ready({ state: COMPANION_STATE.missing });
  const settled = await openMonitor(made.ports);

  assert.equal(settled.installation.agent_surface, AGENT_SURFACE.ready);
  assert.equal(settled.installation.monitor_surface, MONITOR_SURFACE.unavailable);
  assert.equal(isComplete(settled.installation), false, "Monitor 없이 설치 완료라고 했다");
  // 사람에게는 "계속 쓸 수 있다"가 반드시 간다.
  for (const outcome of [OUTCOME.needsCompanionInstall, OUTCOME.needsCompanionUpdate, OUTCOME.monitorUnavailable]) {
    assert.match(sayOutcome(outcome), /계속할 수 있다/);
  }
});

test("8b. 네 가지 degraded 경로 전부에서 coordinator 가 답을 낸다", async () => {
  const paths = [
    ["missing", ready({ state: COMPANION_STATE.missing }), OUTCOME.needsCompanionInstall],
    ["stopped·실행 실패", ready({ state: COMPANION_STATE.stopped, canLaunch: false }), OUTCOME.monitorUnavailable],
    ["outdated", ready({ state: COMPANION_STATE.outdated }), OUTCOME.needsCompanionUpdate],
    ["handshake timeout", ready({ state: COMPANION_STATE.stopped, readyAfter: 0 }), OUTCOME.monitorUnavailable],
  ];
  for (const [name, made, expected] of paths) {
    const settled = await openMonitor(made.ports);
    assert.equal(settled.outcome, expected, name);
    assert.equal(settled.installation.agent_surface, AGENT_SURFACE.ready, `${name}: text loop 가 죽었다`);
  }
});

// ── ③ 유한함과 중복 없음 ────────────────────────────────────────────

test("10. 같은 요청 하나가 중복 창이나 중복 실행을 만들지 않는다", async () => {
  for (const setup of [
    { state: COMPANION_STATE.ready },
    { state: COMPANION_STATE.stopped, readyAfter: 2 },
  ]) {
    const made = ready(setup);
    await openMonitor(made.ports);
    assert.ok(made.log.filter((one) => one === "companion.launch").length <= 1, "실행이 두 번이다");
    assert.equal(made.log.filter((one) => one === "companion.focus").length, 1, "창을 두 번 앞으로 가져왔다");
  }
});

test("11. 재시도는 유한하고 결정적 시계로 잰다", async () => {
  const made = ready({ state: COMPANION_STATE.stopped, readyAfter: 0 });
  const settled = await openMonitor({ ...made.ports, policy: { readyAttempts: 5, readyGapMs: 40 } });

  assert.equal(settled.outcome, OUTCOME.monitorUnavailable);
  assert.equal(made.log.filter((one) => one === "companion.probeReady").length, 5, "시도 횟수가 정책과 다르다");
  assert.deepEqual(made.slept, [40, 40, 40, 40, 40], "기다린 시간이 정책과 다르다");
});

test("11b. 기본 정책도 유한하다", async () => {
  const made = ready({ state: COMPANION_STATE.stopped, readyAfter: 0 });
  await openMonitor(made.ports);
  const tries = made.log.filter((one) => one === "companion.probeReady").length;
  assert.ok(tries > 0 && tries <= 60, `시도가 ${tries}회다`);
  assert.ok(made.slept.reduce((a, b) => a + b, 0) <= 10_000, "총 대기가 너무 길다");
});

// ── ④ 새지 않는 응답 ────────────────────────────────────────────────

test("12. 응답 어디에도 절대경로·PID·socket·port 가 없다", () => {
  for (const outcome of Object.values(OUTCOME)) {
    assert.doesNotThrow(() => assertNoLeak(sayOutcome(outcome)), `${outcome} 가 샌다`);
  }
  for (const state of Object.values(COMPANION_STATE)) {
    assert.doesNotThrow(() => assertNoLeak(sayState(state, "0.1.0")), `${state} 가 샌다`);
  }
  // 문지기가 실제로 잡는지 — 잡지 못하면 위의 통과는 의미가 없다.
  for (const leak of [
    // 실제 사람의 계정 이름을 시험 자료에도 적지 않는다 — 이 파일도 설치물에 실려 간다.
    "/Applications/GIL Companion.app 에 있다",
    "~/Applications 에서 찾는다",
    "./companion/make-app.sh 를 돌려라",
    "127.0.0.1:8788 로 열었다",
    "PID 1653 이 답한다",
    "socket 이 없다",
  ]) {
    assert.throws(() => assertNoLeak(leak), `문지기가 놓쳤다: ${leak}`);
  }
});

// ── ⑤ Project 와 `.gil` 은 그대로 ───────────────────────────────────

async function fingerprint(root) {
  const seen = [];
  async function walk(dir, shown) {
    for (const entry of (await readdir(dir, { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name))) {
      const here = join(dir, entry.name);
      const name = `${shown}/${entry.name}`;
      if (entry.isDirectory()) await walk(here, name);
      else seen.push(`${name}:${createHash("sha256").update(await readFile(here)).digest("hex")}`);
    }
  }
  await walk(root, "");
  return seen.join("\n");
}

test("9·13. 모든 실패 경로 전후로 Project 와 .gil 의 바이트가 같고, 잠그지도 다시 관측하지도 않는다", async () => {
  const root = await mkdtemp(join(tmpdir(), "gil-capability-"));
  await mkdir(join(root, ".gil", "objects"), { recursive: true });
  await writeFile(join(root, ".gil", "state.yaml"), "format: 4\nproject: sample\n");
  await writeFile(join(root, ".gil", "objects", "one"), "bytes");
  await writeFile(join(root, "note.md"), "사람이 쓴 글");
  const before = await fingerprint(root);

  const was = process.cwd();
  try {
    process.chdir(root);
    for (const setup of [
      { state: COMPANION_STATE.missing },
      { state: COMPANION_STATE.outdated },
      { state: COMPANION_STATE.stopped, canLaunch: false },
      { state: COMPANION_STATE.stopped, readyAfter: 0 },
      { state: COMPANION_STATE.ready },
    ]) {
      await openMonitor(ready(setup).ports);
    }
  } finally {
    process.chdir(was);
  }

  assert.equal(await fingerprint(root), before, "Project 나 .gil 이 바뀌었다");
  // 잠금 파일을 만들지 않는다 — 상태를 보려고 Project 를 잠그지 않는다.
  assert.ok(!(await readdir(join(root, ".gil"))).includes("project.lock"));
  await rm(root, { recursive: true, force: true });
});

// ── ⑥ 읽기 모델 ────────────────────────────────────────────────────

test("설치 완료는 Agent 표면과 지속형 Monitor 둘 다 있어야 한다", () => {
  const table = [
    [HOST_SURFACE.verified, COMPANION_STATE.missing, MONITOR_SURFACE.persistentHost, true],
    [HOST_SURFACE.unverified, COMPANION_STATE.ready, MONITOR_SURFACE.nativeCompanion, true],
    [HOST_SURFACE.unverified, COMPANION_STATE.stopped, MONITOR_SURFACE.nativeCompanion, true],
    [HOST_SURFACE.unverified, COMPANION_STATE.outdated, MONITOR_SURFACE.unavailable, false],
    [HOST_SURFACE.unverified, COMPANION_STATE.missing, MONITOR_SURFACE.unavailable, false],
  ];
  for (const [hostSurface, companionState, surface, complete] of table) {
    const installation = installationOf({ agentReady: true, hostSurface, companionState });
    assert.equal(installation.monitor_surface, surface, `${hostSurface}+${companionState}`);
    assert.equal(isComplete(installation), complete, `${hostSurface}+${companionState}`);
  }
  // Agent 표면이 없으면 Monitor 가 있어도 완료가 아니다.
  assert.equal(
    isComplete(installationOf({
      agentReady: false, hostSurface: HOST_SURFACE.verified, companionState: COMPANION_STATE.ready,
    })),
    false,
  );
});

test("확인되지 않은 Host surface 를 미지원으로 단정하지 않는다", () => {
  // 값의 이름이 곧 뜻이다. `unsupported` 라는 값을 만들지 않는다 — 그렇게 적으면
  // 아직 하지 않은 probe 의 결과를 문서가 아니라 코드가 먼저 단정하게 된다.
  assert.deepEqual(Object.keys(HOST_SURFACE).sort(), ["unverified", "verified"]);
});
