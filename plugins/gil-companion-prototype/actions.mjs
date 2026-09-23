// **Agent 가 부를 수 있는 GIL 명령표.**
//
// 한 tool 이 한 subcommand 에만 대응한다. 자유 형식 command 를 받는 tool 을 만들지 않는다 —
// 그런 문이 하나 있으면 나머지 규칙이 전부 무의미해진다.
//
// `monitor` 는 여기 없다. 사람이 보는 지속 표면은 Companion 이 소유하고, 그 문은
// `gil_companion_status` 와 `show_gil_companion` 둘이다. 역할을 겹치지 않는다.
// (Rust 의 `gil monitor` 는 그대로 있다. 이 Agent 표면에서 노출하지 않을 뿐이다.)

/** 위치 인자로 들어갈 수 있는 값의 모양.
 *
 *  사용자 입력이 **flag 이름이 되지 못하게** 막는다. 이것을 열어 두면 `--help` 는 애교이고
 *  언젠가 다른 것이 들어온다. 값은 값이고, 문법은 우리가 정한다. */
export function safePositional(value, what) {
  if (typeof value !== "string" || value.length === 0) return `${what} 가 비었다`;
  if (value.startsWith("-")) return `${what} 는 '-' 로 시작할 수 없다`;
  if (/[\n\r\0]/.test(value)) return `${what} 에 줄바꿈이나 NUL 이 있다`;
  if (value.length > 200) return `${what} 가 너무 길다`;
  return null;
}

/**
 * 각 항목:
 *   name          MCP tool 이름
 *   subcommand    대응하는 Rust 명령 **하나**
 *   project       true 면 Project 자리를 요구한다
 *   stdin         본문을 stdin 으로 넘기는 인자 이름 (없으면 null)
 *   positional    허용하는 위치 인자 정의 (없으면 [])
 *   title/summary Host 가 사람에게 보일 말
 */
export const ACTIONS = [
  {
    name: "gil_status",
    subcommand: "status",
    project: true,
    stdin: null,
    positional: [],
    title: "GIL status",
    summary: "Answer where the journey stands right now, in three lines.",
  },
  {
    name: "gil_context",
    subcommand: "context",
    project: true,
    stdin: null,
    positional: [],
    title: "GIL context",
    summary: "Restore the working context for a new session or handoff.",
  },
  {
    name: "gil_story",
    subcommand: "story",
    project: true,
    stdin: null,
    positional: [],
    title: "GIL story",
    summary: "Read the journey so far in human language.",
  },
  {
    name: "gil_help",
    subcommand: "help",
    project: false,          // 주제를 정확히 대면 Project 없이도 펴진다
    stdin: null,
    positional: [{ key: "topic", required: false, what: "주제" }],
    title: "GIL manual topic",
    summary: "Open one GIL manual topic, or the topic that fits the current place.",
  },
  {
    name: "gil_start",
    subcommand: "start",
    project: true,
    stdin: null,
    positional: [],
    title: "Start a GIL project",
    summary: "Create the project and open its first Interview.",
  },
  {
    name: "gil_open",
    subcommand: "open",
    project: true,
    // Step 은 행동 계약을 stdin 으로 받는다. 이것은 command 문자열이 아니라 **본문**이다.
    stdin: "contract",
    positional: [{ key: "kind", required: false, what: "Cycle 종류" }],
    title: "Open the next GIL step",
    summary:
      "Open the next step with its action contract on stdin, or open a Cycle of the given kind. GIL decides which applies.",
  },
  {
    name: "gil_close",
    subcommand: "close",
    project: true,
    stdin: "report",
    positional: [],
    title: "Close the current GIL step",
    summary: "Close the open step with the Report body that the current grammar requires.",
  },
  {
    name: "gil_restore",
    subcommand: "restore",
    project: true,
    stdin: null,
    positional: [],
    title: "Restore the GIL world",
    summary: "Return the working tree to the world this place was opened from.",
  },
  {
    name: "gil_revisit",
    subcommand: "revisit",
    project: true,
    stdin: null,
    positional: [],
    title: "Revisit after a failure",
    summary: "Go back to the Cycle the closing Report already settled on.",
  },
  {
    name: "gil_cycle",
    subcommand: "cycle",
    project: true,
    stdin: null,
    positional: [
      { key: "action", required: true, what: "cycle 동작", oneOf: ["open", "close"] },
      { key: "kind", required: false, what: "Cycle 종류" },
    ],
    title: "Open or close a GIL cycle",
    summary: "Open a cycle of the given kind, or close the current one.",
  },
];

/** typed 입력을 **argv 배열**로 바꾼다. 문자열을 이어 붙이지 않는다. */
export function argvFor(action, input) {
  const argv = [action.subcommand];
  for (const slot of action.positional) {
    const value = input?.[slot.key];
    if (value === undefined || value === null || value === "") {
      if (slot.required) return { error: `${slot.what} 가 필요하다` };
      continue;
    }
    const wrong = safePositional(value, slot.what);
    if (wrong) return { error: wrong };
    if (slot.oneOf && !slot.oneOf.includes(value)) {
      return { error: `${slot.what} 는 ${slot.oneOf.join(" 또는 ")} 중 하나다` };
    }
    argv.push(value);
  }
  return { argv };
}
