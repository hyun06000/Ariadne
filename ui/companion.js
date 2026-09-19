// GIL Companion — 공용 UI bundle.
//
// 계보: Codex Plugin UI 시제품(`widget.html`, 2026-09-08 §9.2 실측)의 색·타이포·detail
// panel·상태 바를 출발점으로 삼았다. Graph 표현은 2026-09-11 판독 검토로 확정된
// **Step 중심 DAG**(Host UI Model §6.1)로 갈아 끼웠다.
//
// # 이 파일이 아는 것과 모르는 것
//
//   안다   canonical MonitorViewV1 · NodeDetailV1 (§3 · §7)
//   안다   window.GIL_HOST 라는 작은 문 하나
//   모른다 Tauri · Codex · browser · 파일 경로 · port · 어떤 transport
//
// # 사실을 다시 계산하지 않는다
//
// 부모·형제·revisit·현재 위치·요약·순서는 전부 View 가 말한 그대로 쓴다. 좌표와 접힘은
// **여기서만** 계산하고 wire 로 돌려보내지 않는다(§6 · §12-8).

import {
  place, projectSelection, revisitRoute, radiusOf, ROW_H, NODE_R, BOX_W,
} from "./layout.js";

const SUPPORTED_SCHEMA = 1;

const root = document.getElementById("gil-companion");
const el = (name) => root.querySelector(name);
const scopeSelect = el(".scope select");
const notice = el(".notice");
const intro = el(".intro");
const map = el(".map");
const stale = el(".stale");
const emptyState = el(".empty");
const working = el(".working");
const introSection = el(".intro");
const mapSection = el(".map");
const openButton = el(".scope .open");
const refreshButton = el(".scope .refresh");
const forgetButton = el(".scope .forget");
const settingsSay = el(".settings-say");
const stage = el(".stage");
const wires = el(".stage .wires");
const layer = el(".stage .layer");
const cardLayer = el(".stage .cards");
const detail = el(".detail");
const status = el(".status span");

// ── presentation state ──────────────────────────────────────────────
//
// **scope 마다 따로 산다.** Project 를 바꾸면 이전 Project 의 선택·접힘·상세가 현재 화면에
// 섞일 길이 없다. `.gil` 에 쓰지 않고 이 창이 사는 동안만 산다(§6 · §6.1-10).
const seats = new Map();
const seatOf = (scopeId) => {
  if (!seats.has(scopeId)) {
    seats.set(scopeId, { selectedStep: null, collapsed: new Set(), detail: null });
  }
  return seats.get(scopeId);
};

let current = null; // { scopeId, view, seat, plan }

/** Host 가 준 거절의 **종류**를 사람의 말로.
 *
 * 글을 뜯어 뜻을 짐작하지 않는다 — `code` 가 갈래를 정하고, Host 가 함께 준 한 줄은
 * **글자 그대로** 덧붙일 뿐이다(§9.1.1-7 · §10). 모르는 code 는 지어내지 않고 그대로 보인다. */
const REFUSAL = {
  not_a_project: "이 자리에 GIL Project 가 없다",
  unsupported_format: "이 Companion 이 읽지 않는 저장 판이다",
  busy: "다른 GIL 명령이 이 Project 를 쥐고 있다 — 잠시 뒤 새로고침",
  needs_recovery: "끝나지 않은 복원이 남아 있다 — 창은 그것을 고치지 않는다. " +
                  "그 Project 에서 GIL 명령을 하나 실행하면 제자리로 돌아간다",
  damaged: "저장된 것을 읽었지만 말이 되지 않는다",
  observe_failed: "Project 의 세계를 들여다보지 못했다",
  unreadable: "그 자리를 읽지 못했다",
  unknown_scope: "이 창이 연 Project 가 아니다",
  scope_collision: "서로 다른 두 Project 가 같은 주소를 받았다 — 섞지 않고 멈춘다",
  project_missing: "등록해 둔 자리를 찾을 수 없다",
  project_moved: "그 자리에 다른 Project 가 있다",
  settings_unwritable: "이 창의 설정을 적지 못했다",
  unsupported_vocabulary: "이 Companion 이 모르는 Grammar 낱말이 있다",
};
const why = (error) => {
  const code = error && error.code;
  const known = code && REFUSAL[code];
  const said = error && error.said ? error.said : (error && error.message) || String(error);
  if (known) return `${known} — ${said}`;
  return code ? `${code} — ${said}` : said;
};

const say = (message) => {
  notice.textContent = message;
  notice.dataset.shown = "true";
};

// ── 지금 무엇을 기다리는가 ──────────────────────────────────────────
//
// 기다리는 일은 **셋뿐**이고, 셋 다 창을 멈추지 않는다(Rust 쪽이 event loop 밖에서 한다).
// 그래도 사람은 무엇을 기다리는지 알아야 한다 — 아무 말 없이 멈춰 보이는 화면과 「읽는
// 중」이라고 적힌 화면은 다른 것이다.
//
// **Graph 를 지우지 않는다.** 진행 줄은 위에 한 줄로 서고, 아래는 마지막으로 검증된
// 화면 그대로다.
const WORKING = {
  picking: "폴더를 고르는 중",
  opening: "Project 를 읽는 중",
  refreshing: "다시 읽는 중",
};
/** 중복 눌림만 그 손잡이로 막는다. 창 전체를 잠그지 않는다. */
const busyOn = (what, button) => {
  working.textContent = WORKING[what];
  working.dataset.shown = "true";
  if (button) button.disabled = true;
};
/** **어떤 길로 끝나든 반드시 걷힌다** — 됐든, 취소됐든, 실패했든. */
const busyOff = (button) => {
  working.textContent = "";
  working.dataset.shown = "false";
  if (button) button.disabled = false;
};
const clearNotice = () => {
  notice.dataset.shown = "false";
};
const text = (value) => (value === null || value === undefined ? "" : String(value));

// ── 사람이 읽는 낱말 ────────────────────────────────────────────────
const CYCLE_KIND = { interview: "인터뷰", experiment: "실험" };
const STEP_KIND = {
  question: "질문", interpretation: "해석", synthesis: "제안", define: "문제",
  hypothesis: "가설", verify: "검증", analysis: "해석", outcome: "판정",
};
const RELATION = {
  active_path: "지금 길", revisit_source: "여기서 갈라짐",
  abandoned: "두고 온 갈래", other: "지난 갈래",
};
const WORLD = { clean: "clean — 기준 세계와 같다", dirty: "dirty — 파일이 바뀌었다",
                unknown: "unknown — 보지 못했다" };
const VERDICT = { success: "성공", failure: "실패" };
const word = (table, value) => table[value] || text(value);
const cycleName = (ref, kind) => `${word(CYCLE_KIND, kind)} ${text(ref).split(":").pop()}`;
const shortId = (ref) => text(ref).split(":").pop();

const cycleOf = (cycleRef) =>
  current.view.timeline.find((one) => one.cycle_ref === cycleRef) || null;
const cycleOfStep = (stepRef) =>
  (current.view.timeline.find((one) => one.steps.some((s) => s.step_ref === stepRef)) || {})
    .cycle_ref || null;

// ── 그린다 ──────────────────────────────────────────────────────────

function svg(name, attrs) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}

/** 생성 edge — 같은 열이면 곧은 수직선, 열이 다르면 출발점에서 **오른쪽으로** 짧게 갈라진다.
 *
 *  형제는 언제나 오른쪽의 새 열을 받으므로(`columns()`) `to.x > from.x` 가 늘 참이다.
 *  왼쪽의 빈 열을 되쓰지 않는다 — 그러면 갈라짐이 되돌아감처럼 읽힌다(§6.1-3 · §12-19). */
function growPath(from, to) {
  if (from.col === to.col) {
    return `M ${from.x} ${from.y + NODE_R} L ${to.x} ${to.y - NODE_R}`;
  }
  // 출발점 바로 아래에서 옆으로 갈라진 뒤, 새 열을 따라 내려간다. 크게 휘지 않는다.
  const turn = from.y + Math.min(14, ROW_H / 2);
  return (
    `M ${from.x} ${from.y + NODE_R} L ${from.x} ${turn} ` +
    `L ${to.x} ${turn} L ${to.x} ${to.y - NODE_R}`
  );
}

/** 화살촉의 길이 — 선은 여기까지만 오고 나머지를 삼각형이 채운다. */
const HEAD = 8;

/**
 * 되돌아감 — **왼쪽으로** 나가 전용 gutter 를 타고 목표의 왼쪽 가장자리에 닿는다.
 *
 * 길은 `revisitRoute()` 가 정한다. 여기서는 그 네 점을 선으로 잇기만 한다.
 */
function revisitPath(route, from, to) {
  const stop = route.land - route.approach * HEAD; // 화살촉이 설 자리를 비워 둔다
  return (
    `M ${route.exit} ${from.y} L ${route.corridor} ${from.y} ` +
    `L ${route.corridor} ${to.y} L ${stop} ${to.y}`
  );
}

/** 화살촉 — 꼭짓점이 목표에 닿고, 진입 방향을 그대로 가리킨다. */
function revisitHead(route, to) {
  const back = -route.approach * HEAD;
  return `M ${route.land} ${to.y} l ${back} -4.5 l 0 9 z`;
}

function drawEdges() {
  wires.innerHTML = "";
  wires.setAttribute("viewBox", `0 0 ${current.plan.width} ${current.plan.height}`);
  wires.setAttribute("width", current.plan.width);
  wires.setAttribute("height", current.plan.height);
  for (const edge of current.plan.edges) {
    if (edge.kind === "grow") {
      wires.appendChild(svg("path", { class: "edge grow", d: growPath(edge.from, edge.to) }));
    } else {
      const route = revisitRoute(edge);
      wires.appendChild(
        svg("path", { class: "edge revisit", d: revisitPath(route, edge.from, edge.to) }),
      );
      wires.appendChild(
        svg("path", { class: "head revisit", d: revisitHead(route, edge.to) }),
      );
    }
  }
}

function drawCycles() {
  for (const cycle of current.plan.cycles) {
    if (cycle.collapsed) continue;
    const top = current.plan.nodes.find((n) => n.cycleRef === cycle.ref);
    const bottom = [...current.plan.nodes].reverse().find((n) => n.cycleRef === cycle.ref);
    if (!top || !bottom) continue;
    const box = document.createElement("div");
    // **경계는 클릭을 가로막지 않는다** — pointer event 를 통과시킨다(§6.1 · 규칙 4).
    box.className = "bound";
    box.dataset.cycle = cycle.ref;
    box.dataset.relation = cycle.relation;
    box.style.left = `${top.x - BOX_W / 2}px`;
    box.style.top = `${top.y - 17}px`;
    box.style.width = `${BOX_W}px`;
    box.style.height = `${bottom.y - top.y + 30}px`;
    const name = document.createElement("span");
    name.className = "bound-name";
    name.textContent = shortId(cycle.ref);
    name.title = cycleName(cycle.ref, cycle.kind);
    box.appendChild(name);

    // 접기 control — 누를 수 있는 자리만 pointer event 를 되살린다.
    const fold = document.createElement("button");
    fold.type = "button";
    fold.className = "fold";
    fold.textContent = "−";
    fold.setAttribute("aria-expanded", "true");
    fold.setAttribute(
      "aria-label",
      `${cycleName(cycle.ref, cycle.kind)} 접기 — Step ${cycle.toRow - cycle.fromRow + 1}개를 감춘다`,
    );
    fold.onclick = (event) => {
      event.stopPropagation();
      collapseCycle(cycle.ref);
    };
    box.appendChild(fold);
    layer.appendChild(box);
  }
}

function drawNodes() {
  const seat = current.seat;
  for (const node of current.plan.nodes) {
    const button = document.createElement("button");
    button.type = "button";
    button.style.left = `${node.x}px`;
    button.style.top = `${node.y}px`;
    if (node.kind === "cycle") {
      const one = cycleOf(node.ref);
      button.className = "node cycle";
      button.dataset.cycle = node.ref;
      button.textContent = shortId(node.ref);
      button.setAttribute("aria-expanded", "false");
      button.setAttribute(
        "aria-label",
        `${cycleName(node.ref, node.cycleKind)} — 접혀 있다. Step ${node.stepCount}개. 펼치려면 누른다`,
      );
      button.dataset.verdict = one && one.report ? one.report.verdict : "";
      button.onclick = () => expandCycle(node.ref);
    } else {
      button.className = "node step";
      button.dataset.step = node.ref;
      button.dataset.kind = node.stepKind;
      button.dataset.here = String(node.here);
      button.setAttribute(
        "aria-label",
        `${word(STEP_KIND, node.stepKind)} · ${node.ref}` +
          `${node.here ? " · 현재 자리" : ""}${node.summary ? ` · ${node.summary}` : ""}`,
      );
      button.onclick = () => selectStep(node.ref);
    }
    const chosen = seat.selectedStep &&
      (node.ref === seat.selectedStep ||
        (node.kind === "cycle" && node.ref === cycleOfStep(seat.selectedStep)));
    button.setAttribute("aria-selected", String(Boolean(chosen)));
    layer.appendChild(button);
  }
}

/** 고른 node 옆의 짧은 요약 카드와, 그 둘을 잇는 굵고 반투명한 화살표. */
function drawCard() {
  cardLayer.innerHTML = "";
  const seat = current.seat;
  if (!seat.selectedStep) return;
  const anchor = projectSelection(current.plan, seat.selectedStep, cycleOfStep(seat.selectedStep));
  if (!anchor) return;

  const card = document.createElement("div");
  card.className = "card"; // pointer-events 는 CSS 가 꺼 둔다(§6.1-6).
  const folded = anchor.kind === "cycle";
  const stepCycle = cycleOfStep(seat.selectedStep);
  const one = cycleOf(stepCycle);
  const step = one && one.steps.find((s) => s.step_ref === seat.selectedStep);
  const head = document.createElement("small");
  head.textContent = folded
    ? `${cycleName(stepCycle, one ? one.kind : "")} · 접힘`
    : `${cycleName(stepCycle, one ? one.kind : "")} · ${word(RELATION, one ? one.relation_to_current : "")}`;
  const name = document.createElement("b");
  name.textContent = step ? `${word(STEP_KIND, step.kind)} · ${seat.selectedStep}` : seat.selectedStep;
  const said = document.createElement("p");
  said.textContent = step && step.summary
    ? step.summary
    : folded
      ? "접힌 Cycle 안의 자리다. 펼치면 그 Step 으로 돌아간다."
      : "아직 닫히지 않아 요약이 없다.";
  card.append(head, name, said);
  cardLayer.appendChild(card);

  // **언제나 오른쪽이다.** 창이 좁다고 왼쪽으로 뒤집으면 카드가 Graph 를 덮는다. 방향을
  // 바꾸는 대신 무대를 넓히고, 화면 밖으로 나가면 `revealSelection()` 이 굴려서 보여 준다
  // — 생성 edge·되돌아감과 같은 원칙이다(§6.1-3 · §6.1-4).
  const cardW = card.offsetWidth || 190;
  // 경계 상자와 그 오른쪽 위의 접기 control 을 지나서 놓는다.
  const gap = BOX_W / 2 + 30;
  const x = anchor.x + gap;
  const y = Math.max(4, anchor.y - card.offsetHeight / 2);
  card.style.left = `${x}px`;
  card.style.top = `${y}px`;
  // 카드가 설 자리까지 무대가 지닌다 — 그래야 잘리지 않고 스크롤로 닿는다.
  stage.style.minWidth = `${Math.max(current.plan.width, x + cardW + 8)}px`;

  // 화살표는 node 중심에서 카드의 가까운 모서리로. **화살촉은 언제나 카드 쪽이다.**
  const arrow = svg("svg", { class: "arrow" });
  const reach = x + cardW + 8;
  arrow.setAttribute("viewBox", `0 0 ${reach} ${current.plan.height}`);
  arrow.setAttribute("width", reach);
  arrow.setAttribute("height", current.plan.height);
  const radius = radiusOf(anchor);
  const tipX = x - 5;
  const fromX = anchor.x + radius;
  const midY = y + card.offsetHeight / 2;
  arrow.appendChild(
    svg("path", {
      class: "lead",
      d: `M ${fromX} ${anchor.y} L ${tipX} ${midY}`,
    }),
  );
  const back = -9;
  arrow.appendChild(
    svg("path", {
      class: "lead-head",
      d: `M ${tipX} ${midY} l ${back} -5.5 l 0 11 z`,
    }),
  );
  cardLayer.appendChild(arrow);
}

/** 다시 그리기 직전, 사람이 서 있던 자리. DOM 이 통째로 바뀌어도 돌려주기 위해서다. */
function whereTheyStood() {
  const held = document.activeElement;
  if (!held || !layer.contains(held)) return null;
  const bound = held.closest(".bound");
  return {
    step: held.dataset.step || null,
    // 접기 control 에는 주소가 없다 — 그것을 담은 **상자**가 지니고 있다.
    cycle: held.dataset.cycle || (bound ? bound.dataset.cycle : null),
    fold: held.classList.contains("fold"),
  };
}

/**
 * 그 자리를 돌려준다.
 *
 * 키보드만 쓰는 사람에게 이것이 없으면, 누를 때마다 focus 가 `<body>` 로 떨어져 처음부터
 * 다시 tab 해야 한다. 고른 Step 이 접혀 사라졌으면 그 Cycle 의 원이, 접힌 원을 폈으면 그
 * Cycle 의 접기 control 이 같은 자리를 잇는다.
 *
 * 스크롤은 건드리지 않는다(`preventScroll`) — 최소 이동은 `revealSelection()` 의 몫이다.
 */
function giveBackTheirPlace(stood) {
  if (!stood) return;
  const pick = (selector) => layer.querySelector(selector);
  let seat = null;
  if (stood.fold && stood.cycle) {
    seat = pick(`.bound[data-cycle="${CSS.escape(stood.cycle)}"] .fold`) ||
      pick(`.node.cycle[data-cycle="${CSS.escape(stood.cycle)}"]`);
  } else if (stood.step) {
    seat = pick(`[data-step="${CSS.escape(stood.step)}"]`);
    if (!seat) {
      const home = cycleOfStep(stood.step);
      if (home) seat = pick(`.node.cycle[data-cycle="${CSS.escape(home)}"]`);
    }
  } else if (stood.cycle) {
    seat = pick(`.node.cycle[data-cycle="${CSS.escape(stood.cycle)}"]`) ||
      pick(`.bound[data-cycle="${CSS.escape(stood.cycle)}"] .fold`);
  }
  if (seat) seat.focus({ preventScroll: true });
}

/** 한 축에서 **최소로** 움직일 거리. 이미 다 보이면 있던 자리를 그대로 돌려준다. */
function leastScroll(start, end, at, room) {
  if (end - start >= room) return start;   // 창보다 크면 앞쪽(=node 쪽)을 보인다
  if (start < at) return start;            // 위·왼쪽으로 벗어났다
  if (end > at + room) return end - room;  // 아래·오른쪽으로 벗어났다
  return at;                               // 이미 보인다 — **건드리지 않는다**
}

/**
 * 고른 자리와 그 요약 카드가 **함께** 보이게 최소 거리만 굴린다(§6.1-6).
 *
 * 이미 둘 다 보이면 scroll 을 바꾸지 않는다. 사람이 직접 누른 node 는 이미 보이는 자리라
 * 화면이 튀지 않는다. focus 도 건드리지 않는다 — `scrollLeft`·`scrollTop` 만 옮긴다.
 * 즉시 이동이라 `prefers-reduced-motion` 에서도 따로 할 일이 없다.
 *
 * 여기서 정한 viewport 는 이 창이 사는 동안의 화면 상태다. `.gil`·View·detail·Journey 로
 * 나가지 않는다.
 */
function revealSelection() {
  if (!current || !current.seat.selectedStep) return;
  const anchor = layer.querySelector('[aria-selected="true"]');
  if (!anchor) return;
  const card = cardLayer.querySelector(".card");
  const frame = stage.getBoundingClientRect();
  const rect = (node) => {
    const box = node.getBoundingClientRect();
    return { l: box.left - frame.left, r: box.right - frame.left,
             t: box.top - frame.top, b: box.bottom - frame.top };
  };
  const a = rect(anchor);
  const both = card
    ? (() => { const c = rect(card);
               return { l: Math.min(a.l, c.l), r: Math.max(a.r, c.r),
                        t: Math.min(a.t, c.t), b: Math.max(a.b, c.b) }; })()
    : a;
  // 가장자리에 딱 붙지 않게 조금 물린다.
  const edge = 8;
  const room = map;
  room.scrollLeft = leastScroll(both.l - edge, both.r + edge, room.scrollLeft, room.clientWidth);
  room.scrollTop = leastScroll(both.t - edge, both.b + edge, room.scrollTop, room.clientHeight);
}

function renderGraph() {
  const stood = whereTheyStood();
  current.plan = place(current.view, current.seat.collapsed);
  layer.innerHTML = "";
  stage.style.height = `${current.plan.height}px`;
  stage.style.minWidth = `${current.plan.width}px`;
  drawEdges();
  drawCycles();
  drawNodes();
  drawCard();
  giveBackTheirPlace(stood);
  revealSelection();
}

function renderIntro() {
  const view = current.view;
  const here = cycleOf(view.current.cycle_ref);
  const define = here && here.experiment_definition;
  intro.querySelector("h1").textContent = define
    ? define.problem
    : "아직 이 Cycle 의 질문이 정의되지 않았다";
  intro.querySelector("p").textContent = define
    ? `성공 기준 · ${define.success_condition}`
    : `${cycleName(view.current.cycle_ref, here ? here.kind : "")} 안에 서 있다`;
  intro.querySelector(".world").textContent = word(WORLD, view.world.state);
  status.textContent =
    `${view.current.cycle_ref} · ${view.current.step_ref || "Cycle 경계"} · 읽기 전용`;
}

function renderDetail(node) {
  detail.innerHTML = "";
  if (!node) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "Step 을 고르면 그 자리의 Report 를 보여 준다.";
    detail.appendChild(empty);
    return;
  }
  const head = document.createElement("small");
  head.textContent =
    `${node.cycle_ref} · ${word(STEP_KIND, node.kind)} · ${node.state === "open" ? "열림" : "닫힘"}`;
  const name = document.createElement("h2");
  name.textContent = node.step_ref;
  detail.append(head, name);
  if (!node.report) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "아직 닫히지 않아 Report 가 없다.";
    detail.appendChild(empty);
    return;
  }
  const list = document.createElement("dl");
  for (const field of node.report.fields) {
    const label = document.createElement("dt");
    label.textContent = field.name;
    const value = document.createElement("dd");
    value.textContent = field.value; // **글자다.** markup 으로 해석하지 않는다.
    list.append(label, value);
  }
  detail.appendChild(list);
}

// ── 사람이 누르는 것 ────────────────────────────────────────────────

async function selectStep(stepRef) {
  const seat = current.seat;
  const scopeId = current.scopeId;
  seat.selectedStep = stepRef;
  renderGraph();
  let node = null;
  try {
    node = await window.GIL_HOST.loadDetail(scopeId, stepRef);
  } catch (error) {
    say(`상세를 읽지 못했다 — ${why(error)}`);
  }
  // 기다리는 동안 Project 가 바뀌었으면 **버린다** — 남의 Project 에 섞지 않는다.
  if (!current || current.scopeId !== scopeId || seat.selectedStep !== stepRef) return;
  seat.detail = node;
  renderDetail(node);
}

function collapseCycle(cycleRef) {
  current.seat.collapsed.add(cycleRef);
  renderGraph();
}

function expandCycle(cycleRef) {
  current.seat.collapsed.delete(cycleRef);
  renderGraph();
  // 접혀 있는 동안 원으로 투영됐던 선택이 제 Step 으로 돌아온다.
  if (current.seat.selectedStep) renderDetail(current.seat.detail);
}

// ── Project scope 전환 ──────────────────────────────────────────────

/**
 * 마지막으로 검증된 View 가 **최신이 아닐 수 있다**는 사실을 따로 세운다(§9.1.1-6).
 *
 * 화면의 Graph 를 지우지 않는다. 실패를 `dirty` 나 빈 Graph 로 바꾸지도 않는다 — 그것은
 * 일어난 일이 아니다. 마지막으로 확인된 사실은 그대로 두고, **확인하지 못했다는 사실**만
 * 옆에 적는다.
 */
function markStale(error) {
  stale.textContent = `마지막으로 확인된 화면이다. 다시 읽지 못했다: ${why(error)}`;
  stale.dataset.shown = "true";
}
function markFresh() {
  stale.textContent = "";
  stale.dataset.shown = "false";
}

/**
 * 조회가 도는 중인가, 그리고 **끝나면 한 번 더 봐야 하는가.**
 *
 * 자동 갱신과 손으로 누른 새로고침이 같은 자리를 쓴다. 둘이 따로 놀면 백 개의 event 가
 * 백 개의 완전한 조회를 만든다.
 *
 * 도는 중에 온 것은 **한 비트**로만 남긴다 — 지금 조회를 취소하지도, 결과를 합치지도
 * 않는다. 끝난 뒤 딱 한 번 더 본다(§5).
 */
let reading = null;
let readAgain = false;

/** 사람이 누르는 새로고침 — **완전한 View** 를 다시 읽는다. 부분 갱신은 없다(§8). */
async function refresh() {
  if (!current) return;
  // 이미 돌고 있으면 그 한 비트만 남기고 그 조회에 얹힌다.
  if (reading) {
    readAgain = true;
    return reading;
  }
  reading = readOnce().finally(() => {
    reading = null;
  });
  const first = reading;
  await first;
  // 도는 동안 무언가 왔다면 **정확히 한 번** 더 본다.
  if (readAgain) {
    readAgain = false;
    await refresh();
  }
  return first;
}

/** 완전한 View 하나를 읽어 화면을 통째로 간다. */
async function readOnce() {
  if (!current) return;
  const scopeId = current.scopeId;
  busyOn("refreshing", refreshButton);
  try {
    const view = await window.GIL_HOST.loadView(scopeId);
    if (!current || current.scopeId !== scopeId) return; // 그새 Project 가 바뀌었다
    if (view.schema_version !== SUPPORTED_SCHEMA) {
      markStale({ code: "unsupported_vocabulary",
                  said: `schema_version ${view.schema_version} 을 읽을 수 없다` });
      return;
    }
    // **통째로 갈아 끼운다.** 옛 View 에 새 조각을 얹어 사실을 만들지 않는다.
    current.view = view;
    markFresh();
    renderIntro();
    renderGraph();

    // 고른 Step 이 새 View 에도 있으면 그 자리의 상세를 다시 읽는다. 없어졌으면 **다른
    // Step 을 추측하지 않고** 선택과 상세를 비운다(§7). 접힘은 그대로 둔다 — 그것은
    // 이 창의 표현 상태이지 Project 의 사실이 아니다.
    const chosen = current.seat.selectedStep;
    if (chosen) {
      const still = view.timeline.some((one) => one.steps.some((s) => s.step_ref === chosen));
      if (still) {
        await selectStep(chosen);
      } else {
        current.seat.selectedStep = null;
        current.seat.detail = null;
        renderGraph();
        renderDetail(null);
      }
    }
  } catch (error) {
    // 마지막으로 검증된 View 는 그대로 둔다.
    markStale(error);
  } finally {
    busyOff(refreshButton);
  }
}

/** 사람이 폴더를 고른다. **취소는 아무 일도 아니다**(§9.1.1-8). */
async function openProject() {
  busyOn("picking", openButton);
  try {
    // 사람이 고르개를 만지는 동안 — 창은 계속 움직인다.
    const picked = await window.GIL_HOST.addProject();
    // **취소는 아무 일도 아니다.** 진행 줄만 걷고 나간다(§9.1.1-8).
    if (!picked) return;
    clearNotice();
    busyOn("opening", openButton);
    await listScopes();
    scopeSelect.value = picked.scope_id;
    await showScope(picked.scope_id);
  } catch (error) {
    say(why(error));
  } finally {
    busyOff(openButton);
  }
}

/**
 * 아무 Project 도 고르지 않은 상태로 화면을 비운다.
 *
 * 「고르지 않는다」는 **화면에도 아무것도 없다**는 뜻이어야 한다. 앞서 보던 Graph 가 남아
 * 있으면 사람은 그것이 지금 고른 것이라고 읽는다.
 */
function chooseNothing() {
  current = null;
  layer.innerHTML = "";
  wires.innerHTML = "";
  cardLayer.innerHTML = "";
  renderDetail(null);
  markFresh();
}

/**
 * 지금 Project 를 목록에서 뺀다 — **이 창의 설정에서만.**
 *
 * Project 폴더 · `.gil` · Artifact · Snapshot · Report 는 하나도 건드리지 않는다. 그래서
 * 「지운다」가 아니라 「뺀다」라고 적는다 — 사람이 파일이 사라진다고 오해하면 안 된다.
 *
 * 뺀 것이 보고 있던 것이면 **빈 선택**으로 간다. 다른 Project 를 추측해 열지 않는다(§9.1.2).
 */
async function forgetProject() {
  if (!current) return;
  const scopeId = current.scopeId;
  forgetButton.disabled = true;
  try {
    await window.GIL_HOST.forgetProject(scopeId);
    chooseNothing();
    seats.delete(scopeId);
    await listScopes();
  } catch (error) {
    say(why(error));
  } finally {
    forgetButton.disabled = false;
  }
}

async function showScope(scopeId) {
  clearNotice();
  // **이전 Project 의 화면을 먼저 비운다.** 새 사실이 오기 전에 옛 사실이 남아 있으면
  // 그 짧은 순간에 두 Project 가 한 화면에 섞인다.
  current = null;
  layer.innerHTML = "";
  wires.innerHTML = "";
  cardLayer.innerHTML = "";
  map.scrollLeft = 0;
  map.scrollTop = 0;
  renderDetail(null);

  markFresh();
  busyOn("opening", null);
  let view;
  try {
    view = await window.GIL_HOST.loadView(scopeId);
  } catch (error) {
    say(`이 Project 를 읽지 못했다 — ${why(error)}`);
    return;
  } finally {
    busyOff(null);
  }
  if (view.schema_version !== SUPPORTED_SCHEMA) {
    say(`이 Companion 은 schema_version ${view.schema_version} 을 읽을 수 없다 ` +
        `(v${SUPPORTED_SCHEMA} 만 안다).`);
    return;
  }
  current = { scopeId, view, seat: seatOf(scopeId), plan: null };
  introSection.hidden = false;
  mapSection.hidden = false;
  detail.hidden = false;
  emptyState.hidden = true;
  renderIntro();
  renderGraph();
  renderDetail(current.seat.detail);
}

/**
 * 이름이 같은 것이 둘 이상이면 **보이기 위해서만** 짧은 꼬리를 붙인다(§9.1.2).
 *
 * 꼬리는 주소가 아니다. Host 로 가는 요청은 언제나 **전체 scope** 를 쓴다 — 고르개의
 * `value` 가 그것이고, 이 함수는 `textContent` 에만 손댄다.
 */
function tellApart(scopes) {
  const seen = new Map();
  for (const one of scopes) seen.set(one.label, (seen.get(one.label) || 0) + 1);
  return (one) => {
    if ((seen.get(one.label) || 0) < 2) return one.label;
    const tail = String(one.scope_id).split(":").pop().slice(0, 6);
    return `${one.label} (${tail})`;
  };
}

/** 고르개를 Host 가 말한 목록으로 다시 세운다. 개수를 세지도 이름을 짓지도 않는다. */
async function listScopes() {
  const scopes = await window.GIL_HOST.listProjects();
  const naming = tellApart(scopes);
  scopeSelect.innerHTML = "";
  for (const one of scopes) {
    const option = document.createElement("option");
    option.value = one.scope_id;   // **언제나 전체 scope.**
    // 크기는 **등록부가 지닌 값**을 그대로 읽는다. 이름 안에 숫자를 적어 두면 Project 가
    // 자랄 때 이름만 낡는다. 없는 Host 도 있다 — 그러면 이름만 적는다.
    const size = Number.isInteger(one.cycles) && Number.isInteger(one.steps)
      ? ` · Cycle ${one.cycles} · Step ${one.steps}`
      : "";
    // 못 여는 것도 목록에 남는다 — 사람이 등록해 둔 사실은 사라지지 않는다(§9.1.2).
    const gone = one.unavailable ? ` — ${word(REFUSAL, one.unavailable) || one.unavailable}` : "";
    if (one.unavailable) option.dataset.unavailable = one.unavailable;
    option.textContent = `${naming(one)}${size}${gone}`;
    scopeSelect.appendChild(option);
  }
  // **연 Project 가 없으면 그 사실을 곧바로 보인다.** 「불러오는 중…」이 남아 있으면
  // 사람은 무언가 오고 있다고 믿고 기다린다 — 오지 않는데.
  const none = scopes.length === 0;
  emptyState.hidden = !none;
  scopeSelect.hidden = none;
  refreshButton.disabled = none;
  introSection.hidden = none;
  mapSection.hidden = none;
  detail.hidden = none;
  forgetButton.hidden = none || typeof window.GIL_HOST.forgetProject !== "function";
  return scopes;
}

async function start() {
  if (!window.GIL_HOST) {
    say("이 Host 가 GIL_HOST 를 제공하지 않는다.");
    return;
  }
  // **문이 할 수 있는 것만 켠다.** bundle 은 어느 Host 인지 모르지만, 그 문에 폴더를 고르는
  // 손잡이가 달려 있는지는 볼 수 있다. fixture Host 에는 없다.
  const canPick = typeof window.GIL_HOST.addProject === "function";
  openButton.hidden = !canPick;
  openButton.onclick = openProject;
  refreshButton.onclick = refresh;
  scopeSelect.onchange = () => showScope(scopeSelect.value);

  forgetButton.onclick = forgetProject;

  // 창 밖에서 오는 말 — 있는 Host 에서만. **사실은 이 길로 오지 않는다.**
  if (typeof window.GIL_HOST.listen === "function") {
    // menu bar 의 새로고침은 **hint 한 줄**이다. 받는 쪽이 제 경계로 완전한 View 를
    // 다시 조회한다 — 부분 갱신을 합쳐 사실을 만들지 않는다(§8).
    window.GIL_HOST.listen("gil://refresh", () => {
      refresh();
    });
    // 이 창의 사정. Graph 를 건드리지 않고 한 줄로 알린다.
    window.GIL_HOST.listen("gil://say", (said) => {
      if (!said) return;
      // 자동 갱신이 (다시) 섰다 — 앞서 적어 둔 그 말만 걷는다. 남의 알림은 건드리지
      // 않는다. 성공했다고 따로 알리지도 않는다(토스트를 쌓지 않는다).
      if (said.code === "watch_live") {
        if (notice.textContent.includes("자동 갱신을 시작하지 못했다")) clearNotice();
        return;
      }
      if (said.said) say(said.said);
    });
  }

  const scopes = await listScopes();
  if (!scopes.length) {
    chooseNothing();
    return;
  }

  // **마지막으로 보던 것 하나만 연다**(§9.1.2). 등록됐다는 이유로 나머지를 읽지 않는다.
  //
  // 그 Host 가 무엇을 마지막으로 보았는지 모르면(fixture Host 가 그렇다) 목록의 첫 칸을
  // 연다 — 그 Host 에는 「마지막」이라는 것이 없기 때문이다.
  let start = scopes[0];
  if (typeof window.GIL_HOST.opening === "function") {
    let opened = null;
    try {
      opened = await window.GIL_HOST.opening();
    } catch (error) {
      say(why(error));
    }
    if (opened && opened.settings_refusal) {
      // 설정을 읽지 못했다. **원본은 그대로**이고 이번 실행만 임시로 돈다.
      settingsSay.textContent = opened.settings_refusal.said;
      settingsSay.dataset.shown = "true";
    }
    const last = opened && opened.last_selected;
    // 마지막 선택이 없거나 목록에 없으면 **아무것도 고르지 않는다.**
    start = last ? scopes.find((one) => one.scope_id === last) : null;
  }
  if (!start) {
    chooseNothing();
    return;
  }
  if (start.unavailable) {
    chooseNothing();
    // 열 수 없다는 사실만 말하고 **다른 Project 로 물러서지 않는다.**
    scopeSelect.value = start.scope_id;
    say(`마지막으로 보던 Project 를 열 수 없다 — ${word(REFUSAL, start.unavailable) || start.unavailable}`);
    return;
  }
  scopeSelect.value = start.scope_id;
  await showScope(start.scope_id);
}

window.addEventListener("resize", () => {
  if (!current) return;
  drawCard();
  revealSelection();
});

// 시험이 들여다보는 자리 — 화면이 말하는 것을 프로그램으로도 물을 수 있게.
window.GIL_COMPANION = {
  scopeId: () => current && current.scopeId,
  plan: () => current && current.plan,
  seats,
  showScope,
  selectStep,
  collapseCycle,
  expandCycle,
  revealSelection,
  refresh,
  openProject,
  working: () => working.textContent,
  listScopes,
  forgetProject,
  start,
  ready: start(),
};
