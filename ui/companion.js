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

const say = (message) => {
  notice.textContent = message;
  notice.dataset.shown = "true";
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
    say(`상세를 읽지 못했다: ${error && error.message ? error.message : error}`);
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

  let view;
  try {
    view = await window.GIL_HOST.loadView(scopeId);
  } catch (error) {
    say(`이 Project 를 읽지 못했다: ${error && error.message ? error.message : error}`);
    return;
  }
  if (view.schema_version !== SUPPORTED_SCHEMA) {
    say(`이 Companion 은 schema_version ${view.schema_version} 을 읽을 수 없다 ` +
        `(v${SUPPORTED_SCHEMA} 만 안다).`);
    return;
  }
  current = { scopeId, view, seat: seatOf(scopeId), plan: null };
  renderIntro();
  renderGraph();
  renderDetail(current.seat.detail);
}

async function start() {
  if (!window.GIL_HOST) {
    say("이 Host 가 GIL_HOST 를 제공하지 않는다.");
    return;
  }
  const scopes = await window.GIL_HOST.listProjects();
  scopeSelect.innerHTML = "";
  for (const one of scopes) {
    const option = document.createElement("option");
    option.value = one.scope_id;
    // 크기는 **등록부가 지닌 값**을 그대로 읽는다. 이름 안에 숫자를 적어 두면 Project 가
    // 자랄 때 이름만 낡는다.
    const size = Number.isInteger(one.cycles) && Number.isInteger(one.steps)
      ? ` · Cycle ${one.cycles} · Step ${one.steps}`
      : "";
    option.textContent = `${one.label}${size}`;
    scopeSelect.appendChild(option);
  }
  scopeSelect.onchange = () => showScope(scopeSelect.value);
  if (scopes.length) await showScope(scopes[0].scope_id);
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
  ready: start(),
};
