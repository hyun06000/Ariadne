// **사람에게 보이는 문장** — 다음 행동을 말하고, 구현 세부를 말하지 않는다.
//
// Distribution Model §7은 port·localhost URL·binary path·package format·MCP transport를
// 사용자에게 보여 주지 않는다고 정한다. 예전 판은 설치 안내에 `~/Applications/...`와
// `./companion/make-app.sh`를 실어 그 계약을 어겼고, 실행 실패는 OS의 오류 문구를 그대로
// 흘렸다. 오류 문구에는 경로가 들어 있다.
//
// 그래서 문장은 **여기서만** 만든다. 바깥에서 받은 글을 그대로 잇지 않는다.

import { OUTCOME } from "./capability.mjs";

const APP_NAME = "GIL Monitor";

/** Monitor가 없어도 GIL은 계속 쓸 수 있다 — 매번 같은 말로 붙인다. */
const STILL_USABLE = "Monitor를 열 수 없지만 GIL 기록 작업은 계속할 수 있다.";

/** 실제로 밟을 수 있는 다음 행동만 적는다. 없는 길을 안내하지 않는다. */
const NEXT_IN_TEXT = "지금 상태는 `gil context`로 이어서 볼 수 있다.";

const WORDS = {
  [OUTCOME.openedPersistentHost]: () =>
    `${APP_NAME}를 이 Host의 지속형 화면에 열었다.`,
  [OUTCOME.focusedExistingCompanion]: () =>
    `이미 열려 있던 ${APP_NAME} 창을 앞으로 가져왔다.`,
  [OUTCOME.startedAndOpenedCompanion]: () =>
    `${APP_NAME}를 열고 응답을 확인했다.`,
  [OUTCOME.needsCompanionInstall]: () =>
    `${APP_NAME}가 아직 설치되어 있지 않다. 설치하면 이 여정을 창으로 계속 볼 수 있다. `
    + `설치는 승인을 받은 뒤에만 진행한다. ${STILL_USABLE}`,
  [OUTCOME.needsCompanionUpdate]: () =>
    `설치된 ${APP_NAME}가 지금 판과 호환되지 않는다. 호환판으로 업데이트해야 열 수 있다. `
    + `낡은 판을 대신 열지 않는다. ${STILL_USABLE}`,
  [OUTCOME.monitorUnavailable]: () => `${STILL_USABLE} ${NEXT_IN_TEXT}`,
};

/** 네 상태를 사람 말로. 판 번호는 사람이 업데이트를 판단할 근거라서 남긴다. */
const STATE_WORDS = {
  missing: () => `${APP_NAME}가 설치되어 있지 않다.`,
  stopped: (version) => `${APP_NAME} 호환판 ${version}이 설치되어 있고 지금은 닫혀 있다.`,
  outdated: () => `${APP_NAME}가 설치되어 있지만 지금 판과 호환되지 않는다.`,
  ready: (version) => `${APP_NAME} 호환판 ${version}이 열려 있고 응답한다.`,
};

export function sayOutcome(outcome) {
  const make = WORDS[outcome];
  if (!make) throw new Error(`말할 줄 모르는 결과다: ${outcome}`);
  return make();
}

export function sayState(state, appVersion) {
  const make = STATE_WORDS[state];
  if (!make) throw new Error(`말할 줄 모르는 상태다: ${state}`);
  return make(appVersion ?? "알 수 없음");
}

/** 응답에 경로·PID·socket·port가 섞이지 않았는지 문 앞에서 한 번 더 본다.
 *
 *  문장을 여기서만 만들어도, 누군가 나중에 바깥 글을 이어 붙일 수 있다. 그때 조용히
 *  새어 나가지 않도록 **내보내기 직전에** 막는다. */
const LEAKS = [
  [/(^|[\s"'`(])[~/][^\s"'`)]{2,}/, "경로"],
  [/\.(app|sock|sh|exe|dmg|pkg)\b/i, "파일 이름"],
  [/\b(?:localhost|127\.0\.0\.1|0\.0\.0\.0)\b/i, "loopback 주소"],
  [/\b(?:port|포트)\s*[:=]?\s*\d{2,5}\b/i, "port"],
  [/:\d{2,5}\b/, "port"],
  [/\bPID\b|\bpid\s*[:=]?\s*\d+/i, "PID"],
  [/\bsocket\b|\bsock\b/i, "socket"],
];

export function assertNoLeak(text) {
  for (const [pattern, what] of LEAKS) {
    if (pattern.test(text)) throw new Error(`사용자 응답에 ${what}가 섞였다: ${text}`);
  }
  return text;
}
