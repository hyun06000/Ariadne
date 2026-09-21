// **설치 capability의 판정과 조율** — 무엇이 실제로 가능한지 하나의 자리에서 정한다.
//
// 이 파일은 바깥 세계에 손대지 않는다. process를 띄우지도, 파일을 읽지도, 시계를 보지도
// 않는다. 그 셋은 전부 `ports`로 들어온다. 그래야 결정적인 시계와 가짜 launcher로 시험할 수
// 있고, 시험을 위해 production protocol을 약하게 만들 필요가 없다.
//
// # 왜 한 자리인가
//
// 같은 판정을 두 군데에 적으면 한쪽이 낡는다. Host surface의 유무와 Companion의 네 상태는
// 따로 물어볼 수 있지만 **"Monitor를 열 수 있는가"는 하나의 답**이어야 한다.

/** Agent가 GIL의 typed action을 쓸 수 있는가. */
export const AGENT_SURFACE = {
  ready: "ready",
  unavailable: "unavailable",
};

/** 사람이 지속형 Monitor를 열 수 있는 표면. 선택 순서가 그대로 이 순서다. */
export const MONITOR_SURFACE = {
  persistentHost: "persistent_host",
  nativeCompanion: "native_companion",
  unavailable: "unavailable",
};

/** Companion handshake가 가르는 네 값. 이 밖의 값을 만들지 않는다. */
export const COMPANION_STATE = {
  missing: "missing",
  stopped: "stopped",
  outdated: "outdated",
  ready: "ready",
};

/** Host의 지속형 surface를 **실제로 확인했는가**.
 *
 *  `unverified`는 "이 Host가 PiP를 지원하지 않는다"는 뜻이 **아니다**. 아직 정식 probe로
 *  확인하지 않았다는 뜻이다(Host UI Model §9.2). 기능 이름이나 요청 성공만으로 지원을
 *  추측하지 않는 것과 같은 이유로, 확인하지 못한 것을 미지원으로 단정하지도 않는다.
 *  판정 결과는 어느 쪽이든 같다 — 확인되지 않았으면 persistent_host로 세지 않는다. */
export const HOST_SURFACE = {
  verified: "verified",
  unverified: "unverified",
};

/** coordinator가 실제로 한 일. 문자열을 뜯어 뜻을 짐작하지 않도록 값으로 가른다. */
export const OUTCOME = {
  openedPersistentHost: "opened_persistent_host",
  focusedExistingCompanion: "focused_existing_companion",
  startedAndOpenedCompanion: "started_and_opened_companion",
  needsCompanionInstall: "needs_companion_install",
  needsCompanionUpdate: "needs_companion_update",
  monitorUnavailable: "monitor_unavailable",
};

/** 유한한 재시도. 무한 polling도 background busy loop도 만들지 않는다. */
export const DEFAULT_POLICY = Object.freeze({
  probeTimeoutMs: 2_000,
  readyAttempts: 30,
  readyGapMs: 100,
});

/** 설치 완료 조건의 read model (Distribution Model §2).
 *
 *  `monitor_surface`는 **지금 창이 떠 있는가**가 아니라 **사람이 지속형 Monitor를 열 수
 *  있는가**를 말한다. 그래서 호환판이 설치됐지만 꺼져 있는 `stopped`도 `native_companion`이다
 *  — 열면 되기 때문이다. 반대로 `outdated`는 설치는 됐어도 열어서는 안 되므로 표면이 없다. */
export function installationOf({ agentReady, hostSurface, companionState }) {
  return {
    agent_surface: agentReady ? AGENT_SURFACE.ready : AGENT_SURFACE.unavailable,
    monitor_surface: monitorSurfaceOf(hostSurface, companionState),
  };
}

function monitorSurfaceOf(hostSurface, companionState) {
  if (hostSurface === HOST_SURFACE.verified) return MONITOR_SURFACE.persistentHost;
  if (companionState === COMPANION_STATE.ready || companionState === COMPANION_STATE.stopped) {
    return MONITOR_SURFACE.nativeCompanion;
  }
  return MONITOR_SURFACE.unavailable;
}

/** 설치가 완료됐는가 — 둘 다 있어야 한다. inline과 text는 여기에 세지 않는다. */
export function isComplete(installation) {
  return installation.agent_surface === AGENT_SURFACE.ready
    && installation.monitor_surface !== MONITOR_SURFACE.unavailable;
}

/** 사용자가 처음 말한 것. **메모리 안에서만** 산다.
 *
 *  Graph·Journey·Memory·Will·Project 어디에도 적지 않는다. 이 요청 하나가 끝나면 함께
 *  사라진다. 적어 두면 다음 실행이 사람이 지금 원하지 않는 창을 열 수 있고, 그것은 사람의
 *  의사 없이 움직이는 것이다. */
export function monitorIntent() {
  return { kind: "open_monitor" };
}

/**
 * "GIL Monitor 열기" 하나를 끝까지 조율한다.
 *
 * `persistent_host → native_companion → unavailable` 순서를 그대로 밟는다. Companion이
 * 꺼져 있으면 실행하고, **fresh challenge로 다시 확인한 뒤**, 그제서야 원래 요청을 이어서
 * 수행한다. 실행 명령이 성공했다는 사실만으로 완료라고 답하지 않는다.
 *
 * @param ports.host        `.surface()` → HOST_SURFACE, `.open()` → 지속형 Host surface를 연다
 * @param ports.companion   `.state()` → { state, descriptor }, `.launch()`, `.focus()`,
 *                          `.probeReady(descriptor)` → boolean
 * @param ports.clock       `.sleep(ms)` — 결정적 시계를 끼울 자리
 * @param ports.policy      유한한 timeout·재시도
 */
export async function openMonitor(ports) {
  const policy = { ...DEFAULT_POLICY, ...(ports.policy || {}) };
  const intent = monitorIntent();
  const agentReady = ports.agentReady !== false;

  // ① 지속형 Host surface를 **확인된 경우에만** 쓴다. 확인되지 않았으면 Companion으로 간다.
  //    여기서 PiP를 새로 요청하거나 지원 여부를 짐작하지 않는다.
  const hostSurface = await ports.host.surface();
  if (hostSurface === HOST_SURFACE.verified) {
    await ports.host.open(intent);
    return settled(OUTCOME.openedPersistentHost, {
      agentReady,
      hostSurface,
      companionState: null,
    });
  }

  // ② Companion의 네 상태. 경로가 있다는 사실만으로 열지 않는다.
  const seen = await ports.companion.state();

  if (seen.state === COMPANION_STATE.missing) {
    return settled(OUTCOME.needsCompanionInstall, { agentReady, hostSurface, companionState: seen.state });
  }
  // `outdated`를 `missing`이나 `stopped`로 뭉개지 않는다. 지금 판을 ready처럼 열지도 않는다.
  if (seen.state === COMPANION_STATE.outdated) {
    return settled(OUTCOME.needsCompanionUpdate, { agentReady, hostSurface, companionState: seen.state });
  }

  if (seen.state === COMPANION_STATE.ready) {
    await ports.companion.focus(intent);
    return settled(OUTCOME.focusedExistingCompanion, { agentReady, hostSurface, companionState: seen.state });
  }

  // ③ `stopped` — 실행하고, 다시 확인하고, 원래 요청을 이어서 수행한다.
  const launched = await ports.companion.launch(intent);
  if (launched === false) {
    return settled(OUTCOME.monitorUnavailable, {
      agentReady,
      hostSurface,
      companionState: seen.state,
      why: "launch_failed",
    });
  }

  const became = await untilReady(ports, seen.descriptor, policy);
  if (!became) {
    // 실행 명령은 성공했지만 handshake가 오지 않았다. 원래 요청을 성공으로 표시하지 않는다.
    return settled(OUTCOME.monitorUnavailable, {
      agentReady,
      hostSurface,
      companionState: COMPANION_STATE.stopped,
      why: "not_ready_after_launch",
    });
  }

  // 여기서 **원래 요청이 재개된다.** 사람이 같은 말을 두 번 하지 않는다.
  await ports.companion.focus(intent);
  return settled(OUTCOME.startedAndOpenedCompanion, {
    agentReady,
    hostSurface,
    companionState: COMPANION_STATE.ready,
  });
}

/** 유한하게 기다린다. 매번 **새 challenge**로 묻는다 — 한 번의 성공을 계속 재사용하지 않는다. */
async function untilReady(ports, descriptor, policy) {
  for (let attempt = 0; attempt < policy.readyAttempts; attempt += 1) {
    if (await ports.companion.probeReady(descriptor)) return true;
    await ports.clock.sleep(policy.readyGapMs);
  }
  return false;
}

function settled(outcome, facts) {
  return {
    outcome,
    installation: installationOf(facts),
    why: facts.why || null,
  };
}
