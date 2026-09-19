// **공용 bundle 의 자동 시험** — Host UI Model §6.1 이 요구한 표현을 화면에서 잰다.
//
//   browser   ui/selftest.html 을 연다
//   Tauri     같은 창에서 selftest.html 로 옮기면 그대로 돈다
//   프로그램   await window.GIL_SELFTEST.run() → [{ name, ok, note }]
//
// 여기서 재는 것은 **표현**뿐이다. 부모·형제·revisit·순서 같은 사실은 Rust 쪽 시험이
// 이미 잡았다(`tests/companion.rs`). 같은 것을 두 자리에 적으면 한쪽이 낡는다.

import {
  place, revisitRoute, radiusOf, BOX_W, GUTTER_GAP, GUTTER_STEP, CANVAS_EDGE,
} from "./layout.js";

const checks = [];
const check = (name, body) => checks.push({ name, body });
const C = () => window.GIL_COMPANION;

// ── 장치의 기준점 ───────────────────────────────────────────────────
//
// 시험 장치가 스스로를 오염시키면 그 뒤의 판정은 **제품이 아니라 장치를 잰 것**이
// 된다. 실제로 그랬다: 검사마다 `REAL_HOST = window.GIL_HOST` 로 "진짜
// 문"을 **다시** 잡았기 때문에, 앞선 검사가 스텁을 꽂아 둔 채 끝나면 그 스텁이
// 기준점이 되고 스텁이 스스로에게 위임했다(`Maximum call stack size exceeded`).
// 기준점은 **한 번만** 잡는다. 다시 대입할 수 있는 전역을 정본으로 쓰지 않는다.

/** 제품이 아니라 장치가 깨졌다는 뜻 — 이것이 나오면 suite 를 멈춘다. */
class HarnessError extends Error {}
/** 시간 초과로 끊긴 기다림. */
class Aborted extends Error {}

const ORIGIN = window.GIL_HOST;
if (!ORIGIN) throw new HarnessError("host.js 가 먼저 서지 않았다");

let loads = 0;   // `loadView` 가 몇 번 불렸나 — 폭주인지 아닌지를 계수로 가른다
/** 원본 문을 그대로 두고 **세기만** 한다. `Object.keys` 도 원본과 같은 것을 준다. */
const REAL_HOST = new Proxy(ORIGIN, {
  get(door, key, self) {
    const got = Reflect.get(door, key, self);
    if (key !== "loadView" || typeof got !== "function") return got;
    return (...said) => { loads += 1; return got.apply(door, said); };
  },
});
window.GIL_HOST = REAL_HOST;   // bundle 도 같은 문을 쓴다 — 세는 자리가 하나다

// ── 검사 하나가 만든 자원의 장부 ────────────────────────────────────
//
// 끊어야 할 때 끊으려면 무엇을 만들었는지 알아야 한다. 검사 본문은 그대로 두고
// `wait`·`frame` 같은 공용 도구가 **지금 도는 검사**의 장부에 적는다.
let ledger = null;
const newLedger = () => ({ timers: new Set(), frames: new Set(), cut: [], done: false });
const cutLedger = (one, why) => {
  one.done = true;
  for (const id of one.timers) clearTimeout(id);
  for (const id of one.frames) cancelAnimationFrame(id);
  one.timers.clear();
  one.frames.clear();
  for (const stop of one.cut.splice(0)) { try { stop(why); } catch { /* 이미 끝났다 */ } }
};

/** 장부에 적히는 기다림 — 검사가 끊기면 **깨어나서 되던진다**. */
const wait = (ms = 260) => new Promise((done, fail) => {
  const mine = ledger;
  if (mine && mine.done) { fail(new Aborted("이미 끊긴 검사다")); return; }
  const id = setTimeout(() => { if (mine) mine.timers.delete(id); done(); }, ms);
  if (!mine) return;
  mine.timers.add(id);
  mine.cut.push((why) => { clearTimeout(id); fail(new Aborted(why)); });
});
/** 한 번 그려지기를 기다린다 — 그리지 않는 창에서 영원히 매달리지 않는다. */
const frame = () => new Promise((done, fail) => {
  const mine = ledger;
  if (mine && mine.done) { fail(new Aborted("이미 끊긴 검사다")); return; }
  const id = requestAnimationFrame(() => { if (mine) mine.frames.delete(id); done(); });
  if (!mine) return;
  mine.frames.add(id);
  mine.cut.push((why) => { cancelAnimationFrame(id); fail(new Aborted(why)); });
});
/** 장부 **밖**의 기다림 — 장치 자신이 쓴다. 검사를 끊어도 같이 끊기면 안 된다. */
const tick = (ms) => new Promise((done) => setTimeout(done, ms));
const at = (selector) => document.querySelector(selector);
const all = (selector) => [...document.querySelectorAll(selector)];

/** 깨끗한 자리에서 시작한다 — 접힘·선택은 scope 마다 **살아남게** 만들어 두었으므로,
 *  앞선 시험이 남긴 것을 지우지 않으면 다음 시험이 그것을 다시 잰다. */
const show = async (scope) => {
  C().seats.clear();
  await C().showScope(scope);
  await wait(80);
};
/** 남아 있는 것을 그대로 두고 되돌아간다 — 격리 시험이 쓰는 문(§6.1-10). */
const resume = async (scope) => {
  await C().showScope(scope);
  await wait(80);
};
const steps = (plan) => plan.nodes.filter((n) => n.kind === "step");
const columnOf = (plan, cycleRef) =>
  (plan.nodes.find((n) => n.cycleRef === cycleRef) || {}).col;
const boxOf = (node) => node.getBoundingClientRect();
const overlaps = (a, b) =>
  a.left < b.right - 0.5 && b.left < a.right - 0.5 &&
  a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5;

// ── ① 열과 행 ───────────────────────────────────────────────────────

check("1. 같은 Cycle 의 모든 Step 이 같은 열에 있다", async () => {
  await show("fixture:dense");
  const byCycle = new Map();
  for (const node of steps(C().plan())) {
    if (!byCycle.has(node.cycleRef)) byCycle.set(node.cycleRef, new Set());
    byCycle.get(node.cycleRef).add(node.col);
  }
  for (const [cycle, cols] of byCycle) {
    if (cols.size !== 1) throw new Error(`${cycle} 이 ${[...cols]} 열에 흩어졌다`);
  }
  return `Cycle ${byCycle.size}개 전부 한 열`;
});

check("2. 순차 자식은 부모의 열을 잇고 진짜 형제만 새 열을 쓴다", async () => {
  await show("fixture:dense");
  const plan = C().plan();
  const view = await window.GIL_HOST.loadView("fixture:dense");
  const eldest = new Map();
  let sequential = 0;
  let siblings = 0;
  for (const cycle of view.timeline) {
    const parent = cycle.parent_cycle_ref;
    if (!parent) continue;
    const mine = columnOf(plan, cycle.cycle_ref);
    const theirs = columnOf(plan, parent);
    if (!eldest.has(parent)) {
      eldest.set(parent, cycle.cycle_ref);
      if (mine !== theirs) throw new Error(`${cycle.cycle_ref} 은 맏이인데 열이 갈렸다`);
      sequential += 1;
    } else {
      if (mine === theirs) throw new Error(`${cycle.cycle_ref} 은 형제인데 같은 열을 썼다`);
      if (mine <= theirs) throw new Error(`${cycle.cycle_ref} 이 오른쪽으로 가지 않았다`);
      siblings += 1;
    }
  }
  if (!siblings) throw new Error("이 fixture 에 진짜 형제가 없어 규칙을 재지 못했다");
  return `순차 ${sequential}개는 같은 열 · 형제 ${siblings}개는 새 열`;
});

check("3. Step 하나가 시간 행 하나를 배타적으로 쓴다", async () => {
  await show("fixture:dense");
  const rows = C().plan().nodes.map((n) => n.row);
  if (new Set(rows).size !== rows.length) throw new Error("같은 행을 둘이 썼다");
  for (let i = 1; i < rows.length; i += 1) {
    if (rows[i] <= rows[i - 1]) throw new Error("행이 시간 순서를 거슬렀다");
  }
  return `${rows.length}행이 모두 다르고 아래로만 간다`;
});

/** 지금 화면의 되돌아감 edge 와 그 길, 그리고 화면에 그려진 경로의 점들. */
const revisits = () => {
  const drawn = all(".edge.revisit").map((p) =>
    [...p.getAttribute("d").matchAll(/([-\d.]+) ([-\d.]+)/g)]
      .map((m) => [Number(m[1]), Number(m[2])]));
  const heads = all(".head.revisit").map((p) => {
    const [, x, y] = p.getAttribute("d").match(/M ([-\d.]+) ([-\d.]+)/).map(Number);
    const back = Number(p.getAttribute("d").match(/l ([-\d.]+) /)[1]);
    return { x, y, pointing: -Math.sign(back) };
  });
  return C().plan().edges
    .filter((e) => e.kind === "revisit")
    .map((edge, at) => ({ edge, route: revisitRoute(edge),
                          path: drawn[at], head: heads[at] }));
};

// ── ② 줄 ────────────────────────────────────────────────────────────

check("4. 형제 분기 edge 가 짧게 오른쪽으로 갈라진다", async () => {
  await show("fixture:dense");
  const turning = C().plan().edges
    .filter((e) => e.kind === "grow" && e.from.col !== e.to.col);
  if (!turning.length) throw new Error("열을 옮기는 생성 edge 가 없다");
  const corners = all(".edge.grow")
    .map((p) => p.getAttribute("d"))
    .filter((d) => d.split(" L ").length === 4);
  if (corners.length !== turning.length)
    throw new Error(`갈라지는 경로가 ${corners.length}개뿐이다`);
  let worst = 0;
  for (const d of corners) {
    const ys = [...d.matchAll(/(-?[\d.]+) (-?[\d.]+)/g)].map((m) => Number(m[2]));
    for (let i = 1; i < ys.length; i += 1) {
      if (ys[i] < ys[i - 1] - 0.01) throw new Error("생성 edge 가 위로 되돌아갔다");
    }
    worst = Math.max(worst, ys[1] - ys[0]);
    if (ys[1] !== ys[2]) throw new Error("옆으로 가는 구간이 수평이 아니다");
  }
  // 닫힌 사각형으로 읽히지 않으려면 갈라지는 구간이 한 행보다 짧아야 한다.
  if (worst >= 32) throw new Error(`갈라지기 전에 ${worst}px 내려갔다 — 한 행만큼이다`);
  return `${corners.length}갈래 · 최대 ${worst}px 만에 갈라진다`;
});

check("5. revisit 은 생성 edge 와 구분되는 점선이고 화살촉이 목표에 닿는다", async () => {
  await show("fixture:dense");
  const back = C().plan().edges.filter((e) => e.kind === "revisit");
  if (!back.length) throw new Error("되돌아감 edge 가 없다");
  const dashed = at(".edge.revisit");
  const dash = getComputedStyle(dashed).strokeDasharray;
  if (!dash || dash === "none") throw new Error("생성 edge 와 같은 실선이다");
  if (dash === getComputedStyle(at(".edge.grow")).strokeDasharray)
    throw new Error("생성 edge 와 구별되지 않는다");
  for (const { edge, route, head } of revisits()) {
    if (Math.abs(head.y - edge.to.y) > 0.01) throw new Error("화살촉이 도착점의 행에 없다");
    if (Math.abs(head.x - route.land) > 0.01) throw new Error("화살촉이 계산된 착지점에 없다");
    if (Math.abs(head.x - edge.to.x) > radiusOf(edge.to) + 0.01)
      throw new Error("화살촉이 목표 가장자리 밖에 있다");
  }
  return `${back.length}줄 · dash ${dash} · ` +
    back.map((e) => `${e.from.ref}→${e.to.ref}`).join(" · ");
});

// ── ③ 선택 · 카드 · inspector ───────────────────────────────────────

check("6. 선택한 node 와 요약 카드 사이에 직접 연결선이 있다", async () => {
  await show("fixture:reading-one");
  await C().selectStep("step:C2/S1");
  await wait(320);
  const lead = at(".lead");
  if (!lead) throw new Error("연결선이 없다");
  if (!at(".lead-head")) throw new Error("화살촉이 없다");
  const stage = boxOf(at(".stage"));
  const node = boxOf(at('[data-step="step:C2/S1"]'));
  const card = boxOf(at(".card"));
  const [, sx, sy] = lead.getAttribute("d").match(/M ([\d.]+) ([\d.]+)/).map(Number);
  const [, ex] = lead.getAttribute("d").match(/L ([\d.]+) ([\d.]+)/).map(Number);
  const cx = node.left + node.width / 2 - stage.left;
  const cy = node.top + node.height / 2 - stage.top;
  if (Math.hypot(sx - cx, sy - cy) > 14) throw new Error("연결선이 node 에서 시작하지 않는다");
  const head = at(".lead-head").getAttribute("d");
  const [, hx] = head.match(/M ([\d.]+) ([\d.]+)/).map(Number);
  if (Math.abs(hx - ex) > 0.01) throw new Error("화살촉이 선의 끝에 없다");
  const nearCard = Math.min(
    Math.abs(hx - (card.left - stage.left)),
    Math.abs(hx - (card.right - stage.left)),
  );
  if (nearCard > 10) throw new Error("화살촉이 카드 쪽을 향하지 않는다");
  return "node 중심 → 카드 모서리, 화살촉은 카드 쪽";
});

check("7. 요약 카드가 node 의 pointer target 을 덮지 않는다", async () => {
  await show("fixture:reading-one");
  await C().selectStep("step:C2/S1");
  await wait(320);
  const node = boxOf(at('[data-step="step:C2/S1"]'));
  const hit = document.elementFromPoint(
    node.left + node.width / 2, node.top + node.height / 2);
  if (!hit || hit.dataset.step !== "step:C2/S1")
    throw new Error(`node 자리를 ${hit && hit.className} 가 가로챈다`);
  for (const layer of [".card", ".cards", ".arrow"]) {
    const found = at(layer);
    if (found && getComputedStyle(found).pointerEvents !== "none")
      throw new Error(`${layer} 가 pointer event 를 받는다`);
  }
  if (overlaps(boxOf(at(".card")), node)) throw new Error("카드가 node 위에 겹쳐 있다");
  return "node 가 여전히 눌리고 카드는 비켜 있다";
});

check("8. 카드와 detail inspector 가 같은 StepRef 를 말한다", async () => {
  await show("fixture:reading-one");
  await C().selectStep("step:C2/S3");
  await wait(340);
  const card = at(".card b").textContent;
  const inspector = at(".detail h2").textContent;
  if (!card.includes("step:C2/S3")) throw new Error(`카드가 "${card}" 라고 말한다`);
  if (inspector !== "step:C2/S3") throw new Error(`inspector 가 "${inspector}" 라고 말한다`);
  const fields = all(".detail dt").length;
  if (!fields) throw new Error("inspector 가 전체 Report 를 펴지 않았다");
  if (all(".card dt").length) throw new Error("카드가 짧은 요약이 아니라 전체 Report 다");
  return `둘 다 step:C2/S3 · inspector 칸 ${fields}개`;
});

// ── ④ 접기와 되접기 ─────────────────────────────────────────────────

check("9. 접으면 Step 이 숨고 Cycle 원 하나만 남는다", async () => {
  await show("fixture:dense");
  C().collapseCycle("cycle:C2");
  await wait(60);
  if (all('[data-step^="step:C2/"]').length) throw new Error("Step 이 남아 있다");
  const circles = all('[data-cycle="cycle:C2"].node.cycle');
  if (circles.length !== 1) throw new Error(`Cycle node 가 ${circles.length}개다`);
  const circle = circles[0];
  if (circle.getAttribute("aria-expanded") !== "false")
    throw new Error("aria-expanded 가 false 가 아니다");
  if (!circle.textContent.includes("C2")) throw new Error("식별자가 보이지 않는다");
  if (!circle.getAttribute("aria-label")) throw new Error("label 이 없다");
  const step = boxOf(all(".node.step")[0]);
  const box = boxOf(circle);
  if (box.width <= step.width) throw new Error("Cycle 원이 Step 보다 크지 않다");
  if (getComputedStyle(circle).borderRadius !== "50%") throw new Error("원이 아니다");
  return `Step 0개 · 원 하나(${box.width}px) · aria-expanded=false`;
});

check("10. 접으면 뒤의 것이 위로 당겨지고 전체 높이가 준다", async () => {
  await show("fixture:dense");
  const before = C().plan();
  C().collapseCycle("cycle:C2");
  await wait(60);
  const after = C().plan();
  if (after.height >= before.height)
    throw new Error(`높이가 ${before.height}→${after.height} 로 줄지 않았다`);
  if (after.nodes.at(-1).y >= before.nodes.at(-1).y)
    throw new Error("마지막 node 가 올라오지 않았다");
  if (at(".stage").style.height !== `${after.height}px`)
    throw new Error("화면의 높이가 계산과 다르다");
  return `${before.height}→${after.height}px · 꼬리 ${before.nodes.at(-1).y}→${after.nodes.at(-1).y}`;
});

check("11. 여러 Cycle 을 접으면 아낀 높이가 쌓인다", async () => {
  await show("fixture:dense");
  const marks = [C().plan().height];
  for (const cycle of ["cycle:C2", "cycle:C3", "cycle:C4"]) {
    C().collapseCycle(cycle);
    await wait(50);
    marks.push(C().plan().height);
  }
  for (let i = 1; i < marks.length; i += 1) {
    if (marks[i] >= marks[i - 1]) throw new Error(`${i}번째 접기가 아무것도 줄이지 못했다`);
  }
  const saved = marks[0] - marks.at(-1);
  if (saved < marks[0] * 0.3)
    throw new Error(`셋을 접고도 ${saved}px 밖에 못 줄였다 — 조밀해지지 않는다`);
  return `${marks.join("→")}px · 모두 ${saved}px 아꼈다`;
});

check("12. 펼치면 node·edge·선택·detail 이 원래대로 돌아온다", async () => {
  await show("fixture:dense");
  await C().selectStep("step:C2/S3");
  await wait(340);
  const was = {
    detail: at(".detail h2").textContent,
    fields: all(".detail dt").length,
    height: C().plan().height,
    nodes: C().plan().nodes.length,
    edges: C().plan().edges.length,
  };
  C().collapseCycle("cycle:C2");
  await wait(60);
  // 접힌 동안 선택은 그 Cycle 의 원으로 투영되고, detail 은 그대로다(§6.1-10).
  const circle = at('[data-cycle="cycle:C2"].node.cycle');
  if (circle.getAttribute("aria-selected") !== "true")
    throw new Error("접힌 원이 선택을 이어받지 않았다");
  if (!at(".card")) throw new Error("카드가 원에 따라붙지 않았다");
  if (at(".detail h2").textContent !== was.detail) throw new Error("접는 동안 detail 이 바뀌었다");

  C().expandCycle("cycle:C2");
  await wait(120);
  const now = C().plan();
  if (now.nodes.length !== was.nodes) throw new Error("node 수가 다르다");
  if (now.edges.length !== was.edges) throw new Error("edge 수가 다르다");
  if (now.height !== was.height) throw new Error("높이가 돌아오지 않았다");
  const back = at('[data-step="step:C2/S3"]');
  if (!back) throw new Error("Step 이 돌아오지 않았다");
  if (back.getAttribute("aria-selected") !== "true") throw new Error("선택이 돌아오지 않았다");
  if (at(".detail h2").textContent !== was.detail || all(".detail dt").length !== was.fields)
    throw new Error("detail 이 돌아오지 않았다");
  return `node ${was.nodes} · edge ${was.edges} · ${was.detail} 그대로`;
});

// ── ⑤ Project 격리 ──────────────────────────────────────────────────

check("13. Project 를 바꾸면 접힘·선택·detail 이 scope 별로 갈린다", async () => {
  await show("fixture:dense");
  await C().selectStep("step:C3/S2");
  await wait(340);
  C().collapseCycle("cycle:C2");
  await wait(60);
  const denseHeight = C().plan().height;

  // **처음 보는 Project 는 아무것도 물려받지 않는다.**
  await resume("fixture:reading-one");
  if (at(".card")) throw new Error("남의 Project 의 카드가 넘어왔다");
  if (all(".node.cycle").length) throw new Error("남의 Project 의 접힘이 넘어왔다");
  if (at(".detail h2")) throw new Error("남의 Project 의 detail 이 넘어왔다");
  await C().selectStep("step:C1/S1");
  await wait(340);
  const mine = at(".detail h2").textContent;

  // **제 것으로 돌아오면 제가 두고 간 그대로다.**
  await resume("fixture:dense");
  if (C().plan().height !== denseHeight) throw new Error("접힘이 복원되지 않았다");
  if (!at('[data-cycle="cycle:C2"].node.cycle')) throw new Error("접힌 Cycle 이 펴져 있다");
  if (at(".detail h2").textContent !== "step:C3/S2") throw new Error("선택이 복원되지 않았다");

  await resume("fixture:reading-one");
  if (all(".node.cycle").length) throw new Error("이쪽에 남의 접힘이 생겼다");
  if (at(".detail h2").textContent !== mine) throw new Error("이쪽 선택이 뒤바뀌었다");
  return `dense=cycle:C2 접힘·step:C3/S2 · reading-one=펼침·${mine}`;
});

// ── ⑥ 쓰지 않는다 ───────────────────────────────────────────────────

check("14. UI 에 쓰기 길이 없다 — .gil·Artifact·Journey·Will 을 건드릴 수단이 없다", async () => {
  await show("fixture:dense");
  await C().selectStep("step:C2/S1");
  await wait(340);
  C().collapseCycle("cycle:C3");
  await wait(60);

  // ① Host 로 가는 문에 **읽는 동사만** 있다. 이름이 쓰기를 뜻하는 것이 하나도 없다.
  //
  //    `addProject` 는 이 창이 **어느 Project 를 볼지**를 정할 뿐 Project 를 만들지도
  //    바꾸지도 않는다. fixture Host 에는 아예 없다.
  const readOnly = [
    "addProject", "forgetProject", "listProjects", "loadDetail", "loadView", "opening",
  ];
  const door = Object.keys(window.GIL_HOST).sort();
  for (const verb of door) {
    if (!readOnly.includes(verb)) throw new Error(`Host 문에 모르는 동사 ${verb} 가 있다`);
  }
  for (const verb of door) {
    // `forgetProject` 는 **이 창의 목록**에서 빼는 일이라 지우는 낱말이 아니다.
    if (/save|write|delete|remove|close|approve|reject|revisit|restore|commit|open_/i.test(verb))
      throw new Error(`Host 문의 ${verb} 가 쓰기를 뜻한다`);
  }

  // ② 사람이 누를 수 있는 것은 **읽는 손잡이**뿐이다.
  // `목록에서 빼기` 도 읽는 손잡이다 — 이 창의 설정에서 한 칸을 지울 뿐, Project 의
  // 파일은 하나도 건드리지 않는다(§9.1.2). Rust 시험이 그 바이트를 지킨다.
  const allowed = [".node", ".fold", ".scope .open", ".scope .refresh", ".scope .forget"];
  for (const button of all("button")) {
    if (!allowed.some((one) => button.matches(one)))
      throw new Error(`쓰기로 보이는 button 이 있다: .${button.className}`);
  }
  if (all("form, input, textarea").length) throw new Error("입력 요소가 있다");
  const selects = all("select");
  if (selects.length !== 1 || selects[0].id !== "scope")
    throw new Error("Project 고르개 말고 다른 입력이 있다");

  // ③ 데이터를 얻으러 간 곳은 fixture 뿐이다. bundle 이 제 파일을 들이는 것은 요청이 아니다.
  const fixture = /\/fixtures\/(projects\.json|[\w-]+\/(view|details)\.json)$/;
  const own = /\/(index|selftest)\.html$|\/(companion|host|layout|selftest)\.js$/;
  const sent = performance.getEntriesByType("resource")
    .filter((r) => r.initiatorType === "fetch" || r.initiatorType === "xmlhttprequest");
  const data = sent.filter((one) => !own.test(new URL(one.name).pathname));
  for (const one of data) {
    if (!fixture.test(new URL(one.name).pathname))
      throw new Error(`fixture 가 아닌 곳에 다녀왔다: ${one.name}`);
  }
  if (!data.length) throw new Error("아무것도 읽지 않았다 — 잴 것이 없다");
  return `읽는 동사 ${door.length} · 읽는 손잡이만 · 데이터 요청 ${data.length}건 모두 fixture`;
});

check("15. Project 마다 server·port·capability URL 이 없다", async () => {
  await show("fixture:dense");
  const base = new URL(".", document.baseURI);
  const loaded = performance.getEntriesByType("resource").map((r) => new URL(r.name));
  for (const one of loaded) {
    if (one.origin !== location.origin)
      throw new Error(`다른 origin 을 읽었다: ${one.origin}`);
    if (one.search) throw new Error(`capability 처럼 보이는 query 가 붙었다: ${one.search}`);
    if (!one.pathname.startsWith(base.pathname))
      throw new Error(`bundle 바깥을 읽었다: ${one.pathname}`);
  }
  if (typeof WebSocket !== "undefined" && window.__gilSockets)
    throw new Error("WebSocket 을 열었다");
  const ports = new Set(loaded.map((one) => one.port));
  if (ports.size > 1) throw new Error(`Project 마다 다른 port 를 썼다: ${[...ports]}`);
  return `origin 하나 · query 없음 · 자원 ${loaded.length}건이 전부 bundle 안`;
});

// ── ⑦ 좁은 창 · 넓은 창 · 키보드 ────────────────────────────────────

check("16. 좁은 창과 넓은 창 모두 control·node·카드가 겹치거나 잘리지 않는다", async () => {
  const map = at(".map");
  const told = [];
  try {
    for (const width of [360, 520, 900]) {
      map.style.width = `${width}px`;
      await show("fixture:dense");
      await C().selectStep("step:C5/S1");
      await wait(320);
      const boxes = [
        ...all(".node").map((n) => [n.dataset.step || n.dataset.cycle, boxOf(n)]),
        ...all(".fold").map((n) => [`${n.closest(".bound").dataset.cycle} 접기`, boxOf(n)]),
      ];
      for (let i = 0; i < boxes.length; i += 1) {
        for (let j = i + 1; j < boxes.length; j += 1) {
          if (overlaps(boxes[i][1], boxes[j][1]))
            throw new Error(`${width}px: ${boxes[i][0]} 와 ${boxes[j][0]} 가 겹친다`);
        }
      }
      const card = boxOf(at(".card"));
      for (const [name, box] of boxes) {
        if (overlaps(card, box)) throw new Error(`${width}px: 카드가 ${name} 를 덮는다`);
      }
      // 잘림은 **닿을 수 없는 것**을 말한다 — map 은 스크롤되므로, 안쪽 좌표가
      // 음수가 아니고 스크롤 범위 안에 있으면 사람이 끝까지 볼 수 있다.
      const stage = boxOf(at(".stage"));
      const left = card.left - stage.left;
      const right = card.right - stage.left;
      if (left < -0.5) throw new Error(`${width}px: 카드가 왼쪽으로 잘렸다 (${left}px)`);
      if (right > map.scrollWidth + 0.5)
        throw new Error(`${width}px: 카드가 스크롤로도 닿지 않는다`);
      if (card.bottom - stage.top > map.scrollHeight + 0.5)
        throw new Error(`${width}px: 카드가 아래로 잘렸다`);
      told.push(`${width}✓`);
    }
  } finally {
    map.style.width = "";
  }
  return told.join(" ");
});

check("17. 키보드만으로 Step 을 고르고 Cycle 을 접고 편다", async () => {
  await show("fixture:reading-one");
  const node = at('[data-step="step:C1/S2"]');
  // `<button>` 이라 tab 순서에 서고 Enter·Space 를 브라우저가 click 으로 옮긴다.
  if (node.tagName !== "BUTTON") throw new Error("Step 이 button 이 아니다");
  if (node.tabIndex < 0) throw new Error("Step 이 tab 순서에서 빠졌다");
  node.focus();
  if (document.activeElement !== node) throw new Error("Step 에 focus 가 가지 않는다");
  node.click();
  await wait(340);
  if (at(".detail h2").textContent !== "step:C1/S2") throw new Error("고르지 못했다");

  const fold = at('.bound[data-cycle="cycle:C1"] .fold');
  if (fold.tagName !== "BUTTON" || fold.tabIndex < 0)
    throw new Error("접기 control 이 tab 순서에 없다");
  if (fold.getAttribute("aria-expanded") !== "true") throw new Error("aria-expanded 가 없다");
  if (!fold.getAttribute("aria-label")) throw new Error("접기 control 에 label 이 없다");
  fold.focus();
  if (document.activeElement !== fold) throw new Error("접기 control 에 focus 가 가지 않는다");
  fold.click();
  await wait(80);

  const circle = at('[data-cycle="cycle:C1"].node.cycle');
  if (!circle) throw new Error("접히지 않았다");
  if (circle.tagName !== "BUTTON" || circle.tabIndex < 0)
    throw new Error("접힌 원이 tab 순서에 없다");
  circle.focus();
  if (document.activeElement !== circle) throw new Error("접힌 원에 focus 가 가지 않는다");
  circle.click();
  await wait(80);
  if (!at('[data-step="step:C1/S2"]')) throw new Error("펼쳐지지 않았다");
  return "button·tab·focus·Enter·aria-expanded·label";
});

// ── ⑧ 되돌아감의 길 ─────────────────────────────────────────────────
//
// 2026-09-11 실제 Tauri 창 판독에서 드러난 것: 목표가 **왼쪽**인데 고정된 오른쪽 통로로
// 크게 우회했다. 방향은 두 자리의 열 번호에서만 나와야 한다.

check("18. 모든 형제 생성 edge 의 첫 비수직 이동이 오른쪽이다", async () => {
  const told = [];
  for (const scope of ["fixture:reading-one", "fixture:dense"]) {
    await show(scope);
    const turning = C().plan().edges
      .filter((e) => e.kind === "grow" && e.from.col !== e.to.col);
    if (!turning.length) throw new Error(`${scope}: 열을 옮기는 생성 edge 가 없다`);
    for (const edge of turning) {
      if (edge.to.col <= edge.from.col)
        throw new Error(`${scope}: ${edge.to.ref} 가 왼쪽 열로 갈라졌다`);
      if (edge.to.x <= edge.from.x)
        throw new Error(`${scope}: ${edge.to.ref} 의 dx 가 ${edge.to.x - edge.from.x} 다`);
    }
    for (const d of all(".edge.grow").map((p) => p.getAttribute("d"))) {
      const pts = [...d.matchAll(/([-\d.]+) ([-\d.]+)/g)].map((m) => [Number(m[1]), Number(m[2])]);
      const moved = pts.slice(1).find((one, i) => Math.abs(one[0] - pts[i][0]) > 0.01);
      if (!moved) continue; // 곧은 수직선
      const at = pts.indexOf(moved);
      if (moved[0] - pts[at - 1][0] <= 0)
        throw new Error(`${scope}: 생성 edge 의 첫 가로 이동이 왼쪽이다`);
    }
    told.push(`${scope.split(":").pop()} ${turning.length}갈래 dx>0`);
  }
  return told.join(" · ");
});

check("19. 모든 revisit edge 의 첫 이동이 왼쪽이다 — 같은 열도 열을 가로질러도", async () => {
  const told = [];
  for (const scope of ["fixture:reading-one", "fixture:dense"]) {
    await show(scope);
    const found = revisits();
    if (!found.length) throw new Error(`${scope}: 되돌아감이 없다`);
    let same = 0;
    let across = 0;
    for (const { edge, path } of found) {
      const dx = path[1][0] - path[0][0];
      if (dx >= 0) throw new Error(`${scope}: ${edge.from.ref} 의 첫 이동 dx 가 ${dx} 다`);
      if (path[0][0] > edge.from.x)
        throw new Error(`${scope}: ${edge.from.ref} 의 오른쪽에서 출발했다`);
      if (edge.from.col === edge.to.col) same += 1; else across += 1;
    }
    told.push(`${scope.split(":").pop()} 같은열 ${same} · 가로지름 ${across} 모두 dx<0`);
  }
  return told.join(" · ");
});

check("20. 되돌아감이 쓰는 통로는 전부 왼쪽 gutter 이고 canvas 안에 온전히 있다", async () => {
  const told = [];
  for (const scope of ["fixture:reading-one", "fixture:dense"]) {
    await show(scope);
    const plan = C().plan();
    const leftmostBox = plan.padLeft - BOX_W / 2;
    for (const { edge, route, path } of revisits()) {
      // ① 상자보다 왼쪽이다 — 같은 열이든 아니든.
      if (route.corridor > leftmostBox - GUTTER_GAP + 0.01)
        throw new Error(`${scope}: 통로 ${route.corridor} 가 가장 왼쪽 상자(${leftmostBox})에 너무 가깝다`);
      // ② canvas 안이다. 음수 좌표로 잘려 숨지 않는다.
      const far = Math.min(...path.map((one) => one[0]));
      if (far < CANVAS_EDGE - 0.01)
        throw new Error(`${scope}: 경로가 x=${far} 로 canvas 왼쪽(${CANVAS_EDGE}) 밖으로 나갔다`);
      // ③ layout 이 잡아 둔 lane 자리에 정확히 선다.
      const want = plan.padLeft - BOX_W / 2 - GUTTER_GAP - edge.lane * GUTTER_STEP;
      if (Math.abs(route.corridor - want) > 0.01)
        throw new Error(`${scope}: 통로가 lane ${edge.lane} 의 자리에 없다`);
    }
    // ④ 그리고 SVG 가 그 폭을 실제로 지닌다.
    const wires = at(".wires");
    if (Number(wires.getAttribute("width")) < plan.width - 0.01)
      throw new Error(`${scope}: canvas 가 계산 폭보다 좁다`);
    const lanes = new Set(revisits().map((one) => one.edge.lane));
    told.push(`${scope.split(":").pop()} padLeft ${plan.padLeft} · lane ${[...lanes].join(",")}`);
  }
  return told.join(" · ");
});

check("21. 화살촉이 목표의 통로 쪽 가장자리에 닿고 진입 방향을 가리킨다", async () => {
  await show("fixture:dense");
  const told = [];
  for (const { edge, route, head } of revisits()) {
    if (Math.abs(head.y - edge.to.y) > 0.01) throw new Error("화살촉이 목표의 행에 없다");
    const want = edge.to.x - radiusOf(edge.to);
    if (Math.abs(head.x - want) > 0.01)
      throw new Error(`화살촉이 ${head.x} 인데 목표의 왼쪽 가장자리는 ${want} 다`);
    if (head.pointing !== 1)
      throw new Error("화살촉이 오른쪽(출발→목표의 진행 방향)을 보지 않는다");
    told.push(`${edge.to.ref} 의 왼쪽 가장자리 ▶`);
  }
  return told.join(" · ");
});

/** 지금 화면의 되돌아감 경로 중 **세로 구간**만. 통로가 지나는 자리다. */
const corridorsNow = () => {
  const out = [];
  for (const drawn of all(".edge.revisit")) {
    const pts = [...drawn.getAttribute("d").matchAll(/([-\d.]+) ([-\d.]+)/g)]
      .map((m) => [Number(m[1]), Number(m[2])]);
    for (let i = 1; i < pts.length; i += 1) {
      if (Math.abs(pts[i][0] - pts[i - 1][0]) > 0.01) continue;
      out.push({ x: pts[i][0],
                 top: Math.min(pts[i][1], pts[i - 1][1]),
                 bottom: Math.max(pts[i][1], pts[i - 1][1]) });
    }
  }
  return out;
};

/** stage 안쪽 좌표로 잰 사각형 — SVG 경로와 같은 자리에서 비교하려면 이 기준이어야 한다. */
const inStage = (node) => {
  const stage = boxOf(at(".stage"));
  const b = boxOf(node);
  return { l: b.left - stage.left, r: b.right - stage.left,
           t: b.top - stage.top, b: b.bottom - stage.top };
};
const crosses = (corridor, box) =>
  corridor.x > box.l + 0.01 && corridor.x < box.r - 0.01 &&
  corridor.top < box.b && corridor.bottom > box.t;

/** 통로가 Cycle 경계와 접기 control 어느 것도 지나지 않는가. 어기면 던진다. */
const corridorsAreClear = (where) => {
  const lanes = corridorsNow();
  if (!lanes.length) throw new Error(`${where}: 세로 구간이 없다`);
  for (const lane of lanes) {
    for (const bound of all(".bound")) {
      if (crosses(lane, inStage(bound)))
        throw new Error(`${where}: 통로 x=${lane.x} 가 ${bound.dataset.cycle} 상자를 관통한다`);
      const fold = bound.querySelector(".fold");
      if (fold && crosses(lane, inStage(fold)))
        throw new Error(`${where}: 통로 x=${lane.x} 가 ${bound.dataset.cycle} 접기 control 아래로 숨는다`);
    }
    // Step 의 누를 수 있는 자리도 지나지 않는다 — 선이 클릭 판정 위를 덮으면 안 된다.
    for (const node of all(".node")) {
      if (crosses(lane, inStage(node)))
        throw new Error(`${where}: 통로 x=${lane.x} 가 ${node.dataset.step || node.dataset.cycle} 를 지난다`);
    }
  }
  return lanes.map((one) => `x=${one.x}(${one.top}→${one.bottom})`).join(" · ");
};

check("22. 세로 통로가 Cycle 경계·접기 control·Step hit target 어느 것도 지나지 않는다", async () => {
  await show("fixture:dense");
  const open = corridorsAreClear("펼친 채");
  // 접고 펴서 재배치한 뒤에도 같은 조건이 선다.
  C().collapseCycle("cycle:C3");
  await wait(60);
  corridorsAreClear("cycle:C3 접은 뒤");
  C().collapseCycle("cycle:C1");
  await wait(60);
  corridorsAreClear("둘 접은 뒤");
  C().expandCycle("cycle:C3");
  await wait(60);
  C().expandCycle("cycle:C1");
  await wait(60);
  const back = corridorsAreClear("다시 편 뒤");
  if (back !== open) throw new Error("펼친 뒤 통로가 달라졌다");
  return `${open} — 접기 2회·펴기 2회 동안 유지`;
});

check("23. 접었다 펴도 같은 방향 규칙을 지킨다", async () => {
  await show("fixture:dense");
  const rule = () => revisits().map(({ edge, path, route, head }) => {
    if (path[1][0] - path[0][0] >= 0) throw new Error(`${edge.from.ref}: 첫 이동이 왼쪽이 아니다`);
    if (head.pointing !== 1) throw new Error("화살촉이 오른쪽을 보지 않는다");
    if (Math.abs(head.x - route.land) > 0.01) throw new Error("착지점이 어긋났다");
    return `${edge.from.cycleRef}→${edge.to.cycleRef} ◀gutter▶`;
  });
  const before = rule();
  for (const cycle of ["cycle:C1", "cycle:C3"]) {
    C().collapseCycle(cycle);
    await wait(60);
    rule(); // 접힌 상태에서도 규칙이 선다 — 어긋나면 여기서 던진다
  }
  for (const cycle of ["cycle:C1", "cycle:C3"]) {
    C().expandCycle(cycle);
    await wait(60);
  }
  const after = rule();
  if (after.join("|") !== before.join("|")) throw new Error("펼친 뒤 방향이 달라졌다");
  return `접기 2회·펴기 2회 뒤에도 ${after.join(" · ")}`;
});

check("24. 좁은 창과 넓은 창에서 같은 방향 규칙을 지킨다", async () => {
  const map = at(".map");
  const told = [];
  try {
    for (const width of [360, 900]) {
      map.style.width = `${width}px`;
      await show("fixture:dense");
      const plan = C().plan();
      for (const { edge, path, route, head } of revisits()) {
        if (path[1][0] - path[0][0] >= 0)
          throw new Error(`${width}px: 되돌아감이 오른쪽으로 출발했다`);
        if (head.pointing !== 1) throw new Error(`${width}px: 화살촉이 뒤집혔다`);
        const want = plan.padLeft - BOX_W / 2 - GUTTER_GAP - edge.lane * GUTTER_STEP;
        if (Math.abs(route.corridor - want) > 0.01)
          throw new Error(`${width}px: 통로가 창 너비에 흔들렸다`);
      }
      for (const edge of plan.edges.filter((e) => e.kind === "grow" && e.from.col !== e.to.col)) {
        if (edge.to.x <= edge.from.x)
          throw new Error(`${width}px: 형제 분기가 왼쪽으로 갈라졌다`);
      }
      told.push(`${width}✓`);
    }
  } finally {
    map.style.width = "";
  }
  return `${told.join(" ")} — 창 너비는 길에 관여하지 않는다`;
});

// ── ⑨ 되돌아감의 출처와 목표 ────────────────────────────────────────
//
// 2026-09-11 실제 Tauri 창 판독에서 드러난 것: 점선을 **새 Cycle 에서** 실패 Cycle 로
// 그렸다. 관계가 반대다. 명세가 정한 것은 이렇다(§6.1-4 · §12-18).
//
//   revisit_from  이 갈래를 낳은 **실패 Cycle**
//   parent        **실제로 되돌아간 목표 Cycle**
//   점선          실패 Cycle 의 Exit → 목표 Cycle 의 Exit
//   생성 실선      목표(=parent) Cycle 의 Exit → 새 Cycle 의 첫 Step

/** 이 View 가 말하는 되돌아감의 의미 — 화면이 아니라 **사실**에서 읽는다. */
const meant = (view) =>
  view.timeline
    .filter((one) => one.revisit_from_cycle_ref && one.parent_cycle_ref)
    .map((one) => ({
      opened: one.cycle_ref,
      failed: one.revisit_from_cycle_ref,
      target: one.parent_cycle_ref,
      firstStep: one.steps.length ? one.steps[0].step_ref : null,
    }));
const lastStepOf = (view, cycleRef) => {
  const one = view.timeline.find((c) => c.cycle_ref === cycleRef);
  return one && one.steps.length ? one.steps.at(-1).step_ref : null;
};

check("25. 점선이 실패 Cycle 의 마지막 Step 에서 목표 Cycle 의 마지막 Step 으로 간다", async () => {
  await show("fixture:reading-one");
  const view = await window.GIL_HOST.loadView("fixture:reading-one");
  const [only] = meant(view);
  if (!only) throw new Error("이 fixture 에 완료된 되돌아감이 없다");
  const drawn = C().plan().edges.filter((e) => e.kind === "revisit");
  if (drawn.length !== 1) throw new Error(`점선이 ${drawn.length}줄이다`);
  const [edge] = drawn;
  const wantFrom = lastStepOf(view, only.failed);
  const wantTo = lastStepOf(view, only.target);
  if (edge.from.ref !== wantFrom)
    throw new Error(`출발이 ${edge.from.ref} 다 — 실패 Cycle ${only.failed} 의 ${wantFrom} 여야 한다`);
  if (edge.to.ref !== wantTo)
    throw new Error(`도착이 ${edge.to.ref} 다 — 목표 Cycle ${only.target} 의 ${wantTo} 여야 한다`);
  const { head, route } = revisits()[0];
  if (Math.abs(head.x - route.land) > 0.01 || Math.abs(head.y - edge.to.y) > 0.01)
    throw new Error("화살촉이 목표에 닿지 않았다");
  return `${only.failed}/${wantFrom} → ${only.target}/${wantTo} · 화살촉 (${head.x}, ${head.y})`;
});

check("26. 새 Cycle 에서 실패 Cycle 로 향하는 점선은 없다", async () => {
  const told = [];
  for (const scope of ["fixture:reading-one", "fixture:dense"]) {
    await show(scope);
    const view = await window.GIL_HOST.loadView(scope);
    const facts = meant(view);
    // 판정은 **줄 하나하나**에 내린다. 한 Cycle 이 어떤 되돌아감의 새 Cycle 이면서
    // 다음 되돌아감의 실패 Cycle 일 수 있다(dense 의 C5 가 그렇다) — Cycle 단위로
    // 금지하면 정당한 줄까지 막는다.
    const drawn = C().plan().edges.filter((e) => e.kind === "revisit");
    if (drawn.length !== facts.length)
      throw new Error(`${scope}: 점선 ${drawn.length}줄, 사실 ${facts.length}건`);
    for (const edge of drawn) {
      // 뒤집힌 줄이면 금지다 — 새 Cycle 에서 나가 제 실패 Cycle 로 들어간다.
      const reversed = facts.find(
        (one) => edge.from.cycleRef === one.opened && edge.to.cycleRef === one.failed);
      if (reversed)
        throw new Error(`${scope}: ${reversed.opened} → ${reversed.failed} 로 관계가 뒤집혔다`);
      // 그리고 사실에 있는 (실패 → 목표) 짝과 정확히 맞아야 한다.
      const honest = facts.find(
        (one) => edge.from.cycleRef === one.failed && edge.to.cycleRef === one.target);
      if (!honest)
        throw new Error(`${scope}: ${edge.from.cycleRef} → ${edge.to.cycleRef} 는 사실에 없는 줄이다`);
      told.push(`${honest.failed}→${honest.target}`);
    }
  }
  return told.join(" · ");
});

check("27. 목표 Cycle 의 마지막 Step 에서 새 Cycle 의 첫 Step 으로 생성 실선이 남는다", async () => {
  const told = [];
  for (const scope of ["fixture:reading-one", "fixture:dense"]) {
    await show(scope);
    const view = await window.GIL_HOST.loadView(scope);
    for (const one of meant(view)) {
      const wantFrom = lastStepOf(view, one.target);
      const found = C().plan().edges.find(
        (e) => e.kind === "grow" && e.from.ref === wantFrom && e.to.ref === one.firstStep);
      if (!found)
        throw new Error(`${scope}: ${wantFrom} → ${one.firstStep} 생성 실선이 없다`);
      const drawn = all(".edge.grow").map((p) => p.getAttribute("d"));
      if (!drawn.length) throw new Error("생성 실선이 그려지지 않았다");
      told.push(`${wantFrom}→${one.firstStep}`);
    }
  }
  return told.join(" · ");
});

check("28. fixture 원본에서 revisit_from 과 parent 가 서로 다른 Cycle 이다", async () => {
  const told = [];
  for (const scope of ["fixture:reading-one", "fixture:dense"]) {
    const view = await window.GIL_HOST.loadView(scope);
    const found = meant(view);
    if (!found.length) throw new Error(`${scope} 에 완료된 되돌아감이 없다`);
    for (const one of found) {
      if (one.failed === one.target)
        throw new Error(`${scope}: ${one.opened} 의 revisit_from 과 parent 가 같다`);
      told.push(`${one.opened}: 실패 ${one.failed} ≠ 목표 ${one.target}`);
    }
  }
  return told.join(" · ");
});

check("29. 접었다 펴도 출발·도착의 뜻이 바뀌지 않는다", async () => {
  await show("fixture:dense");
  const view = await window.GIL_HOST.loadView("fixture:dense");
  // 접히면 anchor 는 그 Cycle 의 **원**이 대신한다 — 가리키는 Cycle 은 그대로다.
  const relation = () => C().plan().edges
    .filter((e) => e.kind === "revisit")
    .map((e) => `${e.from.cycleRef}→${e.to.cycleRef}`)
    .join(" · ");
  const want = meant(view).map((one) => `${one.failed}→${one.target}`).join(" · ");
  if (relation() !== want) throw new Error(`펼친 채로 ${relation()} 이다`);
  for (const cycle of ["cycle:C2", "cycle:C5"]) {
    C().collapseCycle(cycle);
    await wait(60);
    if (relation() !== want) throw new Error(`${cycle} 을 접자 ${relation()} 이 되었다`);
    const anchored = C().plan().edges.filter((e) => e.kind === "revisit")
      .some((e) => (e.from.cycleRef === cycle || e.to.cycleRef === cycle));
    if (anchored) {
      const node = C().plan().edges.find((e) => e.kind === "revisit" &&
        (e.from.cycleRef === cycle ? e.from : e.to).cycleRef === cycle);
      const anchor = node.from.cycleRef === cycle ? node.from : node.to;
      if (anchor.kind !== "cycle") throw new Error(`${cycle} 이 접혔는데 원이 anchor 가 아니다`);
    }
  }
  for (const cycle of ["cycle:C2", "cycle:C5"]) {
    C().expandCycle(cycle);
    await wait(60);
  }
  if (relation() !== want) throw new Error(`펼친 뒤 ${relation()} 이 되었다`);
  return `${want} — 접기 2회·펴기 2회 동안 그대로`;
});

check("30. Project 를 오가도 같은 관계가 복원된다", async () => {
  const relation = async (scope) => {
    await resume(scope);
    return C().plan().edges.filter((e) => e.kind === "revisit")
      .map((e) => `${e.from.ref}→${e.to.ref}`).join(" · ");
  };
  C().seats.clear();
  const first = { one: await relation("fixture:reading-one"), dense: await relation("fixture:dense") };
  C().collapseCycle("cycle:C3");
  await wait(60);
  await relation("fixture:first-interview");
  const again = { one: await relation("fixture:reading-one"), dense: await relation("fixture:dense") };
  if (again.one !== first.one) throw new Error("reading-one 의 관계가 달라졌다");
  if (again.dense !== first.dense) throw new Error("dense 의 관계가 달라졌다");
  return `reading-one ${first.one} | dense ${first.dense}`;
});

check("31. 접기 control 이 경계 안에 앉고 무엇과도 겹치지 않는다", async () => {
  const map = at(".map");
  const told = [];
  try {
    for (const width of [360, 520, 900]) {
      map.style.width = `${width}px`;
      await show("fixture:dense");
      for (const bound of all(".bound")) {
        const cycle = bound.dataset.cycle;
        const box = inStage(bound);
        const fold = bound.querySelector(".fold");
        const f = inStage(fold);
        // ① 경계 **안쪽**에 앉는다.
        if (f.l < box.l - 0.01 || f.r > box.r + 0.01)
          throw new Error(`${width}px: ${cycle} control 이 경계 밖으로 나갔다`);
        // ② focus ring 도 경계 안이다 — 잘리지 않는다.
        const style = getComputedStyle(fold);
        const ring = parseFloat(style.outlineWidth || 2) + parseFloat(style.outlineOffset || 2);
        if (f.r + ring > box.r + 0.01)
          throw new Error(`${width}px: ${cycle} focus ring 이 경계를 ${(f.r + ring - box.r).toFixed(1)}px 넘는다`);
        // ③ 이름과 겹치지 않는다.
        const name = inStage(bound.querySelector(".bound-name"));
        if (name.r > f.l && f.r > name.l && name.b > f.t && f.b > name.t)
          throw new Error(`${width}px: ${cycle} 이름과 control 이 겹친다`);
        // ④ 어떤 Step node 와도 겹치지 않는다.
        for (const node of all(".node")) {
          const n = inStage(node);
          if (n.l < f.r && f.l < n.r && n.t < f.b && f.t < n.b)
            throw new Error(`${width}px: ${cycle} control 이 ${node.dataset.step || node.dataset.cycle} 를 덮는다`);
        }
        // ⑤ 되돌아감 점선의 세로 통로와도 겹치지 않는다.
        for (const lane of corridorsNow()) {
          if (crosses(lane, f))
            throw new Error(`${width}px: ${cycle} control 이 통로 x=${lane.x} 를 가린다`);
        }
        // ⑥ 버튼 한가운데를 짚으면 **버튼 자신**이 나온다.
        //
        // `.map` 은 스크롤되는 창이다. 화면 밖으로 밀린 control 을 그 자리에서 짚으면
        // 거기 그려진 **다른 것**이 잡힌다 — 그건 겹침이 아니라 아직 보이지 않는 것이다.
        // 사람이 보는 자리에서 재려면 먼저 보이는 데까지 굴려 온다.
        fold.scrollIntoView({ block: "center", inline: "center" });
        const seen = boxOf(fold);
        const hit = document.elementFromPoint(
          seen.left + seen.width / 2, seen.top + seen.height / 2);
        if (hit !== fold)
          throw new Error(`${width}px: ${cycle} control 자리를 ${hit && hit.className} 가 가로챈다`);
      }
      told.push(`${width}✓`);
    }
  } finally {
    map.style.width = "";
  }
  return `${told.join(" ")} — 경계 안 · ring 안 · 이름·node·통로와 겹침 없음 · 눌린다`;
});

// ── ⑩ 방향은 왕복해도 절대적이다 ──────────────────────────────────
check("32. Project 를 오가도 절대 방향이 유지된다", async () => {
  const grammar = () => ({
    grow: C().plan().edges.filter((e) => e.kind === "grow" && e.from.col !== e.to.col)
      .every((e) => e.to.x > e.from.x),
    back: revisits().every(({ path, head }) => path[1][0] - path[0][0] < 0 && head.pointing === 1),
  });
  C().seats.clear();
  for (const round of [0, 1]) {
    for (const scope of ["fixture:reading-one", "fixture:dense", "fixture:first-interview"]) {
      await resume(scope);
      const now = grammar();
      if (!now.grow) throw new Error(`${round}회차 ${scope}: 형제 분기가 왼쪽으로 갔다`);
      if (!now.back) throw new Error(`${round}회차 ${scope}: 되돌아감이 오른쪽으로 갔다`);
    }
  }
  return "두 바퀴 · 세 Project — 생성 ▶ · 되돌아감 ◀ 그대로";
});

// ── ⑪ 고른 자리를 보여 준다 ────────────────────────────────────────
//
// 여기서 재는 것은 **bundle 의 자동 스크롤**이다. 시험이 측정을 위해 직접 굴리는 것과
// 섞지 않는다 — 아래 검사들은 스스로 스크롤하지 않고, 스크롤이 **저절로** 일어났는지만 본다.

const viewport = () => ({ left: at(".map").scrollLeft, top: at(".map").scrollTop });
const showsAll = (node) => {
  const room = boxOf(at(".map"));
  const box = boxOf(node);
  return box.left >= room.left - 0.5 && box.right <= room.right + 0.5 &&
         box.top >= room.top - 0.5 && box.bottom <= room.bottom + 0.5;
};

check("33. 화면 밖 Step 을 고르면 그 자리와 카드가 viewport 안으로 들어온다", async () => {
  await show("fixture:dense");
  at(".map").scrollTop = 0;
  at(".map").scrollLeft = 0;
  await wait(60);
  const far = C().plan().nodes.at(-1);            // 가장 아래 — 처음엔 보이지 않는다
  const node = at(`[data-step="${far.ref}"]`);
  if (showsAll(node)) throw new Error("고르기 전에 이미 보인다 — 잴 것이 없다");
  await C().selectStep(far.ref);
  await wait(340);
  const chosen = at(`[data-step="${far.ref}"]`);
  if (!showsAll(chosen)) throw new Error("고른 자리가 여전히 화면 밖이다");
  const card = at(".card");
  if (!card) throw new Error("카드가 없다");
  if (!showsAll(card)) throw new Error("카드가 화면 밖이다");
  const moved = viewport();
  if (moved.top === 0 && moved.left === 0) throw new Error("스크롤이 움직이지 않았다");
  return `${far.ref} 까지 scrollTop 0→${moved.top} · scrollLeft 0→${moved.left}`;
});

check("34. 이미 자리와 카드가 다 보이면 scroll 을 건드리지 않는다", async () => {
  await show("fixture:dense");
  at(".map").scrollTop = 0;
  at(".map").scrollLeft = 0;
  await wait(60);

  // 첫 선택은 **카드까지** 보이게 하려고 조금 움직일 수 있다 — 그것이 규칙이다.
  // 여기서 재는 것은 그다음이다: 이미 둘 다 보이는데도 또 움직이는가.
  const near = C().plan().nodes.find((n) => n.kind === "step");
  await C().selectStep(near.ref);
  await wait(340);
  const node = at(`[data-step="${near.ref}"]`);
  if (!showsAll(node)) throw new Error("고른 자리가 보이지 않는다");
  if (!showsAll(at(".card"))) throw new Error("카드가 보이지 않는다");
  const settled = viewport();

  // 같은 것을 다시 고른다. 이미 다 보이므로 **한 픽셀도 움직이면 안 된다.**
  await C().selectStep(near.ref);
  await wait(340);
  const again = viewport();
  if (again.top !== settled.top || again.left !== settled.left)
    throw new Error(`화면이 튀었다 — (${settled.left}, ${settled.top}) → (${again.left}, ${again.top})`);

  // 다시 그려도 마찬가지다 — 접기 하나를 넣었다 빼도 제자리로 돌아온다.
  C().collapseCycle("cycle:C6");
  await wait(80);
  C().expandCycle("cycle:C6");
  await wait(80);
  const after = viewport();
  if (after.top !== settled.top || after.left !== settled.left)
    throw new Error(`재배치가 화면을 옮겼다 — (${after.left}, ${after.top})`);
  return `${near.ref} · (${settled.left}, ${settled.top}) 에서 움직이지 않는다`;
});

check("35. 접기 재배치로 밀려난 선택이 다시 보인다", async () => {
  await show("fixture:dense");
  const far = C().plan().nodes.at(-1);
  await C().selectStep(far.ref);
  await wait(340);
  if (!showsAll(at(`[data-step="${far.ref}"]`))) throw new Error("고른 뒤에 보이지 않는다");
  const before = viewport();
  // 위쪽 Cycle 을 접으면 뒤의 것이 통째로 올라와 고른 자리가 화면 밖으로 밀린다.
  C().collapseCycle("cycle:C1");
  await wait(80);
  C().collapseCycle("cycle:C2");
  await wait(80);
  const seat = at(`[data-step="${far.ref}"]`);
  if (!seat) throw new Error("고른 Step 이 사라졌다");
  if (!showsAll(seat)) throw new Error("재배치 뒤 고른 자리가 화면 밖이다");
  if (!showsAll(at(".card"))) throw new Error("재배치 뒤 카드가 화면 밖이다");
  return `접기 2회 · scrollTop ${before.top}→${viewport().top}`;
});

check("36. 키보드로 고른 뒤에도 focus 가 그 자리에 남는다", async () => {
  await show("fixture:reading-one");
  const node = at('[data-step="step:C1/S2"]');
  node.focus();
  node.click();
  await wait(340);
  const still = document.activeElement;
  if (!still || still.dataset.step !== "step:C1/S2")
    throw new Error(`고른 뒤 focus 가 ${still && (still.dataset.step || still.tagName)} 로 갔다`);

  // 접어도 자리를 잃지 않는다 — 그 Cycle 의 원이 이어받는다.
  const fold = at('.bound[data-cycle="cycle:C1"] .fold');
  fold.focus();
  fold.click();
  await wait(100);
  // 그 Cycle 의 자리는 둘 중 하나다 — 접혀 있으면 원, 펼쳐져 있으면 그 상자의 접기 control.
  const seatedAt = (node) => node &&
    (node.dataset.cycle || (node.closest(".bound") && node.closest(".bound").dataset.cycle));
  const onCircle = document.activeElement;
  if (seatedAt(onCircle) !== "cycle:C1")
    throw new Error(`접은 뒤 focus 가 ${onCircle && onCircle.tagName} 로 떨어졌다`);
  if (!onCircle.classList.contains("cycle")) throw new Error("접힌 원이 자리를 잇지 않았다");
  onCircle.click();
  await wait(100);
  const back = document.activeElement;
  if (seatedAt(back) !== "cycle:C1")
    throw new Error(`편 뒤 focus 가 ${back && back.tagName} 로 떠났다`);
  return `선택·접기·펴기 내내 focus 가 제자리 (편 뒤 .${back.className})`;
});

// ── ⑫ 이름이 사실과 같은가 ────────────────────────────────────────
check("37. 고르개에 적힌 Cycle·Step 수가 실제 View 와 같다", async () => {
  const told = [];
  for (const one of await window.GIL_HOST.listProjects()) {
    const view = await window.GIL_HOST.loadView(one.scope_id);
    const cycles = view.timeline.length;
    const steps = view.timeline.reduce((sum, c) => sum + c.steps.length, 0);
    if (one.cycles !== cycles || one.steps !== steps)
      throw new Error(`${one.scope_id}: 등록부 ${one.cycles}·${one.steps} ≠ View ${cycles}·${steps}`);
    const option = [...at(".scope select").options].find((o) => o.value === one.scope_id);
    if (!option) throw new Error(`${one.scope_id} 가 고르개에 없다`);
    const shown = option.textContent;
    if (!shown.includes(`Cycle ${cycles}`) || !shown.includes(`Step ${steps}`))
      throw new Error(`고르개가 "${shown}" 라고 적었다 — 실제는 Cycle ${cycles} · Step ${steps}`);
    // 그리고 **낡은 숫자**가 이름 안에 따로 남아 있지 않다.
    const numbers = [...shown.matchAll(/\d+/g)].map((m) => Number(m[0]));
    if (numbers.some((n) => n !== cycles && n !== steps))
      throw new Error(`"${shown}" 에 View 와 무관한 숫자가 있다`);
    told.push(shown);
  }
  return told.join(" | ");
});

// ── ⑬ 실제 adapter 가 붙는 자리 ────────────────────────────────────
//
// 창을 띄우지 않고도 잴 수 있는 것만 여기서 잰다. **Host 문을 잠깐 갈아 끼우고** bundle 이
// 그 문을 어떻게 쓰는지를 본다 — Tauri 쪽 사실은 Rust 시험이 따로 지킨다.

/** 문을 잠깐 바꾸고, 끝나면 **반드시** 되돌린다 — 성공·throw·reject 모두 같은 길.
 *  되돌리지 못하면 다음 검사를 그대로 계속하지 않는다. 장치 오류로 suite 를 멈춘다. */
let depth = 0;
const withHost = async (door, body) => {
  const was = window.GIL_HOST;
  depth += 1;
  window.GIL_HOST = door;
  try {
    return await body();
  } finally {
    depth -= 1;
    window.GIL_HOST = was;
    if (depth === 0 && window.GIL_HOST !== REAL_HOST)
      throw new HarnessError("기준 문을 되돌리지 못했다");
    C().seats.clear();
    await C().listScopes();
  }
};
/** fixture 를 그대로 흉내 내되, 시험이 실패를 주입할 수 있는 문.
 *
 *  위임 대상은 **언제나** 기준점이거나 명시적으로 건네받은 문이다 — "지금
 *  `window.GIL_HOST` 가 무엇인가"를 보고 잡지 않는다. 그렇게 잡으면 스텁이
 *  스텁을 가리키고, 그 모양은 첫 호출에서 stack 을 태운다. 그 모양은 만드는
 *  자리에서 곧바로 거절한다. */
const STUB = Symbol("selftest stub");
const stubHost = (over = {}, delegate = REAL_HOST) => {
  if (!delegate) throw new HarnessError("위임할 문이 없다");
  if (delegate[STUB]) throw new HarnessError("스텁이 스텁에 위임한다 — 자기 자신을 가리키는 모양이다");
  return {
    [STUB]: true,
    listProjects: () => delegate.listProjects(),
    loadView: (scope) => delegate.loadView(scope),
    loadDetail: (scope, step) => delegate.loadDetail(scope, step),
    ...over,
  };
};

check("38. 새로고침이 완전한 View 로 통째로 갈아 끼운다", async () => {
  await show("fixture:dense");
  const before = C().plan().nodes.length;
  let asked = 0;
  await withHost(stubHost({
    loadView: async (scope) => {
      asked += 1;
      // 새로고침이 받는 것은 **또 하나의 완결된 View** 다 — 옛 것의 조각이 아니다.
      const view = await REAL_HOST.loadView(scope);
      view.timeline = view.timeline.slice(0, 2);
      view.current = { ...view.current, cycle_ref: view.timeline[1].cycle_ref,
                       step_ref: view.timeline[1].steps.at(-1).step_ref };
      return view;
    },
  }), async () => {
    await C().refresh();
    await wait(120);
    const after = C().plan().nodes.length;
    if (asked !== 1) throw new Error(`새로고침이 조회를 ${asked}번 했다`);
    if (after >= before) throw new Error("새 View 가 화면을 갈아 끼우지 못했다");
    if (at(".stale")?.dataset.shown === "true") throw new Error("성공했는데 낡았다고 적혔다");
  });
  await show("fixture:dense");
  return `node ${before} → 새 View 로 교체 · 조회 1회`;
});

check("39. 새로고침이 실패하면 마지막 View 를 지키고 오류를 따로 세운다", async () => {
  await show("fixture:reading-one");
  await C().selectStep("step:C2/S3");
  await wait(340);
  const kept = {
    nodes: C().plan().nodes.length,
    detail: at(".detail h2").textContent,
    intro: at(".intro h1").textContent,
  };
  await withHost(stubHost({
    loadView: async () => {
      const refusal = new Error("다른 GIL 명령이 이 Project 를 쥐고 있다");
      refusal.code = "busy";
      refusal.said = refusal.message;
      throw refusal;
    },
  }), async () => {
    await C().refresh();
    await wait(120);
    // ① 마지막으로 검증된 화면이 그대로다.
    if (C().plan().nodes.length !== kept.nodes) throw new Error("Graph 가 지워졌다");
    if (at(".detail h2").textContent !== kept.detail) throw new Error("상세가 지워졌다");
    if (at(".intro h1").textContent !== kept.intro) throw new Error("현재 자리가 바뀌었다");
    if (!at(".card")) throw new Error("선택이 사라졌다");
    // ② 그리고 **최신이라고 가장하지 않는다.**
    const banner = at(".stale");
    if (banner.dataset.shown !== "true") throw new Error("낡았다는 사실이 보이지 않는다");
    if (!banner.textContent.includes("다시 읽지 못했다")) throw new Error("이유가 없다");
    // ③ 실패를 dirty 나 빈 Graph 로 바꾸지 않는다.
    if (at(".intro .world").textContent.includes("dirty"))
      throw new Error("실패가 dirty 로 둔갑했다");
  });
  await show("fixture:reading-one");
  return `Graph·상세·선택 유지 · 낡음 표시 분리`;
});

check("40. 성공한 조회는 낡음 표시를 걷어 간다", async () => {
  await show("fixture:dense");
  let fail = true;
  await withHost(stubHost({
    loadView: async (scope) => {
      if (fail) {
        const refusal = new Error("잠시 막혔다");
        refusal.code = "busy";
        throw refusal;
      }
      return REAL_HOST.loadView(scope);
    },
  }), async () => {
    await C().refresh();
    await wait(100);
    if (at(".stale").dataset.shown !== "true") throw new Error("실패가 표시되지 않았다");
    fail = false;
    await C().refresh();
    await wait(120);
    if (at(".stale").dataset.shown === "true") throw new Error("성공했는데 낡음이 남았다");
  });
  await show("fixture:dense");
  return "실패 → 표시 · 성공 → 걷힘";
});

check("41. 폴더 고르기 취소는 아무것도 바꾸지 않는다", async () => {
  await show("fixture:reading-one");
  await C().selectStep("step:C1/S2");
  await wait(340);
  C().collapseCycle("cycle:C1");
  await wait(80);
  const kept = {
    scope: C().scopeId(),
    height: C().plan().height,
    detail: at(".detail h2").textContent,
    options: all(".scope select option").length,
    notice: at(".notice").dataset.shown,
  };
  let asked = 0;
  await withHost(stubHost({
    // 사람이 고르개를 닫았다 — `null` 이 곧 「아무 일도 없었다」다.
    addProject: async () => { asked += 1; return null; },
  }), async () => {
    await C().openProject();
    await wait(120);
    if (asked !== 1) throw new Error("고르개를 부르지 않았다");
    if (C().scopeId() !== kept.scope) throw new Error("취소가 Project 를 바꿨다");
    if (C().plan().height !== kept.height) throw new Error("취소가 접힘을 풀었다");
    if (at(".detail h2").textContent !== kept.detail) throw new Error("취소가 상세를 지웠다");
    if (all(".scope select option").length !== kept.options)
      throw new Error("취소가 목록을 바꿨다");
    if (at(".notice").dataset.shown !== kept.notice) throw new Error("취소가 오류로 보였다");
  });
  await show("fixture:reading-one");
  return "Project·접힘·상세·목록·알림 모두 그대로";
});

check("42. 거절은 종류로 갈리고 글을 뜯어 뜻을 짐작하지 않는다", async () => {
  await show("fixture:dense");
  const told = [];
  for (const code of ["not_a_project", "unsupported_format", "busy", "needs_recovery", "scope_collision", "damaged"]) {
    await withHost(stubHost({
      loadView: async () => {
        const refusal = new Error("HOST 가 준 원문 그대로");
        refusal.code = code;
        refusal.said = refusal.message;
        throw refusal;
      },
    }), async () => {
      await C().refresh();
      await wait(80);
      const said = at(".stale").textContent;
      if (!said.includes("HOST 가 준 원문 그대로"))
        throw new Error(`${code}: Host 의 말이 사라졌다`);
      told.push(`${code}✓`);
    });
  }
  // 네 갈래가 서로 **다른 말**로 보인다 — 한 덩이로 뭉개지 않는다.
  const shown = new Set();
  for (const code of ["not_a_project", "unsupported_format", "busy", "needs_recovery", "scope_collision", "damaged"]) {
    await withHost(stubHost({
      loadView: async () => { const e = new Error("x"); e.code = code; throw e; },
    }), async () => {
      await C().refresh();
      await wait(60);
      shown.add(at(".stale").textContent);
    });
  }
  if (shown.size !== 6) throw new Error(`여섯 갈래가 ${shown.size}가지 말로만 보인다`);
  await show("fixture:dense");
  return told.join(" ") + " · 여섯 갈래가 서로 다른 말";
});

check("43. 폴더 열기 손잡이는 그 문이 할 수 있을 때만 보인다", async () => {
  // fixture Host 에는 `addProject` 가 없다 — 그러면 손잡이도 없다.
  if (typeof window.GIL_HOST.addProject === "function")
    throw new Error("fixture Host 에 폴더 고르기가 생겼다");
  if (!at(".scope .open").hidden) throw new Error("할 수 없는 일의 손잡이가 보인다");
  // 새로고침은 어느 Host 에서나 뜻이 있다 — 완전한 View 를 다시 읽는 것뿐이다.
  if (at(".scope .refresh").hidden) throw new Error("새로고침 손잡이가 없다");
  if (at(".scope .refresh").tagName !== "BUTTON") throw new Error("눌릴 수 있는 것이 아니다");
  return "폴더 열기 숨김 · 새로고침 보임";
});

check("44. 화면 어디에도 Project 의 경로가 없다", async () => {
  // fixture 는 scope 이름이 곧 폴더 이름이라(이 Host 의 사정이다) 폴더 이름은 빼고,
  // **경로처럼 생긴 것**이 화면에 실렸는지를 본다. 실제 adapter 는 이름조차 한 조각뿐이다.
  await show("fixture:dense");
  await C().selectStep("step:C2/S1");
  await wait(340);

  const suspicious = /(^|[\s"'(])(\/[\w.-]+){2,}/;
  for (const one of all(".scope select option")) {
    if (one.title) throw new Error(`고르개가 tooltip 으로 무언가를 흘린다: ${one.title}`);
    if (suspicious.test(one.textContent)) throw new Error(`고르개에 경로가 있다: ${one.textContent}`);
    for (const name of one.getAttributeNames()) {
      if (name.startsWith("data-")) throw new Error(`고르개에 data 속성 ${name} 이 있다`);
    }
  }
  // DOM 전체에도 절대경로 모양이 없다.
  const painted = at("#gil-companion").innerHTML;
  const found = painted.match(suspicious);
  if (found) throw new Error(`화면에 경로처럼 보이는 것이 있다: ${found[0]}`);

  // scope 이름은 **주소**다. UI 가 그것으로 자리를 지어내지 않는다.
  const scope = C().scopeId();
  if (scope.includes("/")) throw new Error(`scope 에 경로가 들어 있다: ${scope}`);
  return `고르개 ${all(".scope select option").length}칸 · tooltip 없음 · data 속성 없음`;
});

check("45. UI 가 Host 에 건네는 것은 scope 와 StepRef 뿐이다", async () => {
  const seen = [];
  await withHost(stubHost({
    loadView: (scope, ...rest) => {
      seen.push(["loadView", scope, ...rest]);
      return REAL_HOST.loadView(scope);
    },
    loadDetail: (scope, step, ...rest) => {
      seen.push(["loadDetail", scope, step, ...rest]);
      return REAL_HOST.loadDetail(scope, step);
    },
  }), async () => {
    await C().showScope("fixture:reading-one");
    await wait(120);
    await C().selectStep("step:C1/S2");
    await wait(340);
    await C().refresh();
    await wait(200);
  });

  if (!seen.length) throw new Error("아무것도 부르지 않았다");
  // 둘 다 **주소**다. scope 에는 `/` 가 없고, StepRef 의 `/` 는 Cycle 과 Step 사이의 한 칸이라
  // 폴더 구분이 아니다. 그래서 「`/` 가 있는가」가 아니라 **그 모양인가**로 잰다.
  const isScope = (said) => /^[A-Za-z][\w.-]*:[\w.-]+$/.test(said);
  const isStep = (said) => /^step:[\w.-]+\/[\w.-]+$/.test(said);
  for (const [name, ...args] of seen) {
    if (name === "loadView" && args.length !== 1)
      throw new Error(`loadView 에 인자가 ${args.length}개 갔다`);
    if (name === "loadDetail" && args.length !== 2)
      throw new Error(`loadDetail 에 인자가 ${args.length}개 갔다`);
    for (const arg of args) {
      if (typeof arg !== "string") throw new Error(`${name} 에 글자가 아닌 것이 갔다`);
      if (arg.startsWith("/") || arg.startsWith("~") || arg.includes(".."))
        throw new Error(`${name} 에 경로가 갔다: ${arg}`);
    }
    if (!isScope(args[0])) throw new Error(`${name} 의 첫 인자가 scope 모양이 아니다: ${args[0]}`);
    if (name === "loadDetail" && !isStep(args[1]))
      throw new Error(`loadDetail 의 둘째 인자가 StepRef 모양이 아니다: ${args[1]}`);
  }
  await show("fixture:reading-one");
  return `${seen.length}번 · scope 와 StepRef 만`;
});

check("46. 이름이 같은 두 Project 가 View 와 상세를 섞지 않는다", async () => {
  // 같은 이름, 다른 주소 — 실제 adapter 에서 `~/a/일감` 과 `~/b/일감` 이 그렇다.
  const twins = [
    { scope_id: "project:aaaa", label: "일감", from: "fixture:reading-one" },
    { scope_id: "project:bbbb", label: "일감", from: "fixture:dense" },
  ];
  await withHost(stubHost({
    listProjects: async () => twins.map(({ scope_id, label }) => ({ scope_id, label })),
    loadView: async (scope) => {
      const one = twins.find((t) => t.scope_id === scope);
      if (!one) throw Object.assign(new Error("모르는 주소"), { code: "unknown_scope" });
      return REAL_HOST.loadView(one.from);
    },
    loadDetail: async (scope, step) => {
      const one = twins.find((t) => t.scope_id === scope);
      if (!one) throw Object.assign(new Error("모르는 주소"), { code: "unknown_scope" });
      return REAL_HOST.loadDetail(one.from, step);
    },
  }), async () => {
    await C().listScopes();
    const options = all(".scope select option");
    if (options.length !== 2) throw new Error("두 칸이 아니다");
    if (options[0].textContent === options[1].textContent === false) { /* 이름은 같아도 된다 */ }
    if (options[0].value === options[1].value) throw new Error("주소까지 같아졌다");

    await C().showScope("project:aaaa");
    await wait(120);
    const first = C().plan().nodes.length;
    await C().selectStep("step:C1/S2");
    await wait(340);
    const firstDetail = at(".detail h2").textContent;

    await C().showScope("project:bbbb");
    await wait(120);
    const second = C().plan().nodes.length;
    if (second === first) throw new Error("두 Project 가 같은 Graph 를 보여 준다");
    if (at(".detail h2")) throw new Error("앞 Project 의 상세가 넘어왔다");
    await C().selectStep("step:C6/S1");
    await wait(340);
    const secondDetail = at(".detail h2").textContent;
    if (secondDetail === firstDetail) throw new Error("상세가 섞였다");

    // 되돌아가면 제 것이 그대로다.
    await C().showScope("project:aaaa");
    await wait(160);
    if (C().plan().nodes.length !== first) throw new Error("돌아오니 Graph 가 달라졌다");
    if (at(".detail h2").textContent !== firstDetail) throw new Error("돌아오니 상세가 달라졌다");
  });
  await show("fixture:reading-one");
  return "같은 이름 · 다른 주소 · Graph 와 상세가 갈린다";
});

// ── ⑭ 기다리는 동안에도 창은 살아 있다 ──────────────────────────────
//
// 2026-09-12 실측: 고르개를 **기다리는 자리**가 event loop 위에 앉아 창이 통째로 멈췄다.
// Rust 쪽은 worker 로 옮겨 고쳤고, 여기서는 **화면이 그동안 무엇을 하는지**를 잰다.

/** 한참 뒤에야 답하는 문 — 기다리는 동안 무슨 일이 되는지 보려고. */
const slowHost = (over, delay = 900) => stubHost(Object.fromEntries(
  Object.entries(over).map(([name, make]) => [name, async (...args) => {
    await wait(delay);
    return make(...args);
  }]),
));

check("47. 고르개를 기다리는 동안에도 화면이 응답한다", async () => {
  await show("fixture:reading-one");
  const before = C().plan().nodes.length;
  await withHost(stubHost({
    addProject: async () => { await wait(900); return null; },
  }), async () => {
    const picking = C().openProject();           // 기다리게 둔다
    await wait(180);
    // ① 기다리는 중이라고 **적혀 있다**.
    if (at(".working").dataset.shown !== "true") throw new Error("진행 상태가 없다");
    if (C().working() !== "폴더를 고르는 중") throw new Error(`"${C().working()}" 라고 적혔다`);
    // ② 그 손잡이만 막힌다. 창 전체가 잠기지 않는다.
    if (!at(".scope .open").disabled) throw new Error("중복 눌림이 막히지 않는다");
    if (at(".scope select").disabled) throw new Error("고르개까지 잠갔다");
    // ③ **Graph 가 그대로 있다** — 기다린다고 지우지 않는다.
    if (C().plan().nodes.length !== before) throw new Error("기다리는 동안 Graph 가 사라졌다");
    // ④ 그리고 화면은 여전히 움직인다 — 같은 순간에 다른 일이 끝난다.
    let painted = 0;
    await frame();
    painted += 1;
    if (!painted) throw new Error("화면이 다시 그려지지 않는다");
    C().collapseCycle("cycle:C1");
    await wait(60);
    if (!at('[data-cycle="cycle:C1"].node.cycle')) throw new Error("기다리는 동안 조작이 막혔다");
    C().expandCycle("cycle:C1");
    await picking;
  });
  await show("fixture:reading-one");
  return `Graph 유지 · 진행 표시 · 그 손잡이만 disabled · 기다리는 중에도 접기가 된다`;
});

check("48. 느린 조회를 기다리는 동안 다른 일이 끝난다", async () => {
  await show("fixture:dense");
  const kept = C().plan().nodes.length;
  await withHost(slowHost({
    loadView: (scope) => REAL_HOST.loadView(scope),
  }), async () => {
    const reading = C().refresh();
    await wait(180);
    if (C().working() !== "다시 읽는 중") throw new Error(`"${C().working()}" 라고 적혔다`);
    if (!at(".scope .refresh").disabled) throw new Error("중복 눌림이 막히지 않는다");
    if (C().plan().nodes.length !== kept) throw new Error("읽는 동안 Graph 가 사라졌다");

    // **기다리는 그 시간 안에** 다른 일이 처음부터 끝까지 끝난다.
    const done = [];
    for (let i = 0; i < 5; i += 1) {
      await frame();
      done.push(i);
    }
    if (done.length !== 5) throw new Error("그동안 아무것도 끝나지 못했다");
    await reading;
  });
  if (at(".working").dataset.shown === "true") throw new Error("끝났는데 진행 표시가 남았다");
  await show("fixture:dense");
  return "다시 읽는 중 · Graph 유지 · 그사이 5프레임 완주";
});

check("49. 취소·실패 어느 길로 끝나도 진행 표시와 손잡이가 돌아온다", async () => {
  await show("fixture:reading-one");
  await C().selectStep("step:C2/S3");
  await wait(340);
  const kept = { nodes: C().plan().nodes.length, detail: at(".detail h2").textContent };

  // ① 취소.
  await withHost(stubHost({ addProject: async () => { await wait(300); return null; } }), async () => {
    await C().openProject();
  });
  if (at(".working").dataset.shown === "true") throw new Error("취소 뒤 진행 표시가 남았다");
  if (at(".scope .open").disabled) throw new Error("취소 뒤 손잡이가 잠긴 채다");
  if (at(".notice").dataset.shown === "true") throw new Error("취소가 오류로 보인다");

  // ② 고르개 자체가 거절.
  await withHost(stubHost({
    addProject: async () => {
      await wait(200);
      throw Object.assign(new Error("잠그지 못했다"), { code: "unreadable" });
    },
  }), async () => {
    await C().openProject();
  });
  if (at(".working").dataset.shown === "true") throw new Error("실패 뒤 진행 표시가 남았다");
  if (at(".scope .open").disabled) throw new Error("실패 뒤 손잡이가 잠긴 채다");

  // ③ 조회 실패 — 마지막 검증 View 는 그대로.
  await withHost(stubHost({
    loadView: async () => {
      await wait(200);
      throw Object.assign(new Error("쥐고 있다"), { code: "busy" });
    },
  }), async () => {
    await C().refresh();
  });
  if (at(".working").dataset.shown === "true") throw new Error("조회 실패 뒤 진행 표시가 남았다");
  if (at(".scope .refresh").disabled) throw new Error("조회 실패 뒤 손잡이가 잠긴 채다");
  if (C().plan().nodes.length !== kept.nodes) throw new Error("실패가 Graph 를 지웠다");
  if (at(".detail h2").textContent !== kept.detail) throw new Error("실패가 상세를 지웠다");
  if (at(".stale").dataset.shown !== "true") throw new Error("낡음이 표시되지 않았다");

  await show("fixture:reading-one");
  return "취소 · 고르개 거절 · 조회 실패 — 셋 다 원상 복구";
});

check("50. 연 Project 가 없으면 곧바로 그 사실이 보인다", async () => {
  await withHost(stubHost({ listProjects: async () => [] }), async () => {
    await C().listScopes();
    await wait(60);
    if (at(".empty").hidden) throw new Error("빈 상태가 보이지 않는다");
    if (!at(".empty").textContent.includes("아직 연 Project 가 없다"))
      throw new Error("빈 상태의 말이 다르다");
    // **「불러오는 중…」이 남아 있으면 안 된다** — 오지 않는 것을 기다리게 만든다.
    const painted = at("#gil-companion").innerText;
    if (painted.includes("불러오는 중")) throw new Error("불러오는 중이 남아 있다");
    if (!at(".intro").hidden) throw new Error("빈 화면에 현재 자리가 떠 있다");
    if (!at(".map").hidden) throw new Error("빈 화면에 Graph 자리가 떠 있다");
    if (!at(".detail").hidden) throw new Error("빈 화면에 상세 자리가 떠 있다");
    if (!at(".scope select").hidden) throw new Error("빈 고르개가 떠 있다");
  });
  // 그리고 Project 가 생기면 그 자리들이 돌아온다.
  await show("fixture:dense");
  if (!at(".empty").hidden) throw new Error("Project 가 있는데 빈 상태가 남았다");
  if (at(".map").hidden) throw new Error("Graph 가 돌아오지 않았다");
  return "빈 상태 즉시 · Project 가 생기면 되돌아옴";
});

// ── ⑮ 이 창의 사정 ──────────────────────────────────────────────────
//
// 설정 자체는 Rust 가 지닌다(파일·원자적 교체·손상 보존). 여기서 재는 것은 **화면이 그
// 사정을 어떻게 다루는가**다 — 마지막 하나만 열고, 못 여는 것은 못 연다고 말하고, 같은
// 이름을 구별하고, 목록에서 빼면 빈 선택으로 가는 것.

check("51. 시작할 때 마지막으로 보던 하나만 읽는다", async () => {
  const asked = [];
  await withHost(stubHost({
    listProjects: async () => [
      { scope_id: "fixture:reading-one", label: "하나" },
      { scope_id: "fixture:dense", label: "둘" },
      { scope_id: "fixture:first-interview", label: "셋" },
    ],
    opening: async () => ({ last_selected: "fixture:dense" }),
    loadView: async (scope) => {
      asked.push(scope);
      return REAL_HOST.loadView(scope);
    },
  }), async () => {
    C().seats.clear();
    await C().start();
    await wait(300);
    // **한 번뿐이다.** 등록됐다는 이유로 나머지를 읽지 않는다(§9.1.2).
    if (asked.length !== 1) throw new Error(`${asked.length}개를 읽었다: ${asked}`);
    if (asked[0] !== "fixture:dense") throw new Error(`${asked[0]} 를 읽었다`);
    if (C().scopeId() !== "fixture:dense") throw new Error("마지막 선택이 열리지 않았다");
    if (at(".scope select").value !== "fixture:dense") throw new Error("고르개가 따라오지 않았다");
  });
  await show("fixture:reading-one");
  return `Project 3개 등록 · 조회 1회 (${asked[0]})`;
});

check("52. 마지막 선택이 없거나 못 열리면 다른 Project 를 고르지 않는다", async () => {
  for (const [what, opened] of [
    ["마지막 선택 없음", { last_selected: null }],
    ["목록에 없는 것", { last_selected: "project:사라진주소" }],
  ]) {
    const asked = [];
    await withHost(stubHost({
      listProjects: async () => [{ scope_id: "fixture:dense", label: "하나" }],
      opening: async () => opened,
      loadView: async (scope) => {
        asked.push(scope);
        return REAL_HOST.loadView(scope);
      },
    }), async () => {
      C().seats.clear();
      await C().start();
      await wait(250);
      if (asked.length) throw new Error(`${what}: 아무거나 열었다 — ${asked}`);
      if (C().scopeId()) throw new Error(`${what}: 무언가를 골랐다`);
    });
  }

  // 못 여는 자리라면 **그렇다고 말하고** 물러서지 않는다.
  const asked = [];
  await withHost(stubHost({
    listProjects: async () => [
      { scope_id: "project:사라진것", label: "사라진 것", unavailable: "project_missing" },
      { scope_id: "fixture:dense", label: "멀쩡한 것" },
    ],
    opening: async () => ({ last_selected: "project:사라진것" }),
    loadView: async (scope) => {
      asked.push(scope);
      return REAL_HOST.loadView(scope);
    },
  }), async () => {
    C().seats.clear();
    await C().start();
    await wait(250);
    if (asked.length) throw new Error(`못 여는 자리인데 무언가를 읽었다: ${asked}`);
    if (C().scopeId()) throw new Error("옆의 멀쩡한 Project 로 물러섰다");
    if (at(".notice").dataset.shown !== "true") throw new Error("못 연다고 말하지 않았다");
    const said = at(".notice").textContent;
    if (!said.includes("찾을 수 없다")) throw new Error(`"${said}" 라고만 말했다`);
    // 목록에서 지우지도 않는다.
    const options = all(".scope select option");
    if (options.length !== 2) throw new Error("못 여는 항목을 목록에서 지웠다");
    if (!options[0].dataset.unavailable) throw new Error("못 연다는 표시가 없다");
  });
  await show("fixture:reading-one");
  return "선택 없음 · 없는 주소 · 못 여는 자리 — 셋 다 아무것도 고르지 않는다";
});

check("53. 이름이 같으면 보이는 데에만 짧은 꼬리를 붙이고 요청은 전체 scope 로 한다", async () => {
  const asked = [];
  const twins = [
    { scope_id: "project:aaaaaaaaaaaaaaaa1111", label: "일감" },
    { scope_id: "project:bbbbbbbbbbbbbbbb2222", label: "일감" },
    { scope_id: "project:cccccccccccccccc3333", label: "다른 것" },
  ];
  await withHost(stubHost({
    listProjects: async () => twins,
    loadView: async (scope) => {
      asked.push(scope);
      return REAL_HOST.loadView("fixture:dense");
    },
    loadDetail: async (scope, step) => {
      asked.push(scope);
      return REAL_HOST.loadDetail("fixture:dense", step);
    },
  }), async () => {
    await C().listScopes();
    const options = all(".scope select option");
    const shown = options.map((one) => one.textContent);
    // 같은 이름 둘은 서로 다르게 보인다.
    if (shown[0] === shown[1]) throw new Error(`둘이 같은 글자로 보인다: ${shown[0]}`);
    if (!shown[0].includes("일감") || !shown[1].includes("일감"))
      throw new Error("이름이 사라졌다");
    // 혼자인 이름에는 꼬리가 붙지 않는다.
    if (shown[2] !== "다른 것") throw new Error(`혼자인데 꼬리가 붙었다: ${shown[2]}`);
    // **값은 언제나 전체 scope 다.**
    for (const [at_, one] of options.entries()) {
      if (one.value !== twins[at_].scope_id) throw new Error(`고르개 값이 잘렸다: ${one.value}`);
    }
    await C().showScope(twins[1].scope_id);
    await wait(200);
    await C().selectStep("step:C2/S1");
    await wait(340);
    for (const said of asked) {
      if (said !== twins[1].scope_id) throw new Error(`잘린 주소로 청했다: ${said}`);
    }
  });
  await show("fixture:reading-one");
  return `"${twins[0].label}" 둘이 꼬리로 갈리고 요청은 전체 scope ${asked.length}건`;
});

check("54. 목록에서 빼면 빈 선택으로 가고 다른 Project 를 열지 않는다", async () => {
  const gone = [];
  let known = [
    { scope_id: "fixture:dense", label: "볼 것" },
    { scope_id: "fixture:reading-one", label: "남을 것" },
  ];
  const asked = [];
  await withHost(stubHost({
    listProjects: async () => known,
    loadView: async (scope) => {
      asked.push(scope);
      return REAL_HOST.loadView(scope);
    },
    forgetProject: async (scope) => {
      gone.push(scope);
      known = known.filter((one) => one.scope_id !== scope);
    },
  }), async () => {
    await C().listScopes();
    await C().showScope("fixture:dense");
    await wait(200);
    await C().selectStep("step:C2/S1");
    await wait(340);
    const read = asked.length;

    await C().forgetProject();
    await wait(200);

    if (gone.length !== 1 || gone[0] !== "fixture:dense")
      throw new Error(`무엇을 뺐는지 이상하다: ${gone}`);
    // **빈 선택**이다 — 남은 Project 를 추측해 열지 않는다(§9.1.2).
    if (C().scopeId()) throw new Error(`남은 Project 를 열어 버렸다: ${C().scopeId()}`);
    if (asked.length !== read) throw new Error("빼면서 다른 Project 를 읽었다");
    if (at(".detail h2")) throw new Error("뺀 Project 의 상세가 남았다");
    if (at(".card")) throw new Error("뺀 Project 의 카드가 남았다");
    const options = all(".scope select option");
    if (options.length !== 1 || options[0].value !== "fixture:reading-one")
      throw new Error("목록이 맞지 않다");
  });
  await show("fixture:reading-one");
  return "뺀 뒤 빈 선택 · 남은 것을 읽지 않는다";
});

check("55. 설정을 읽지 못하면 그 사실을 말하고 화면은 계속 돈다", async () => {
  await withHost(stubHost({
    listProjects: async () => [{ scope_id: "fixture:dense", label: "하나" }],
    opening: async () => ({
      last_selected: null,
      settings_refusal: {
        code: "settings_unsupported",
        said: "이 Companion 이 모르는 설정 판이다 — 원본을 그대로 두고 이번 실행은 저장하지 않는다",
      },
    }),
  }), async () => {
    C().seats.clear();
    await C().start();
    await wait(250);
    const banner = at(".settings-say");
    if (banner.dataset.shown !== "true") throw new Error("설정 거절이 보이지 않는다");
    if (!banner.textContent.includes("저장하지 않는다"))
      throw new Error(`"${banner.textContent}" 라고만 적혔다`);
    if (banner.textContent.includes("/")) throw new Error("설정 거절에 자리가 실렸다");
    // 그래도 창은 쓸 수 있다 — 목록도 손잡이도 살아 있다.
    if (!all(".scope select option").length) throw new Error("목록이 비었다");
    if (at(".scope .refresh").disabled) throw new Error("새로고침이 잠겼다");
    await C().showScope("fixture:dense");
    await wait(200);
    if (!C().plan()) throw new Error("설정이 없으면 Graph 도 못 그리나");
  });
  at(".settings-say").dataset.shown = "false";
  at(".settings-say").textContent = "";
  await show("fixture:reading-one");
  return "임시 상태를 알리되 창은 그대로 쓸 수 있다";
});

check("56. 헤더 표식은 소문자 `gil` 워드마크이고 단독 `G` 가 아니다", async () => {
  await show("fixture:reading-one");
  const mark = at(".mark");
  if (!mark) throw new Error("표식이 없다");
  const said = mark.textContent.trim();
  // **정확히 `gil`** 이다 — 따옴표도 대문자도 없다(§9.1).
  if (said !== "gil") throw new Error(`표식이 "${said}" 다`);
  if (/[A-Z]/.test(said)) throw new Error(`표식에 대문자가 있다: ${said}`);
  if (/['"`]/.test(said)) throw new Error(`표식에 따옴표가 있다: ${said}`);
  // 그리고 화면 어디에도 단독 `G` 를 브랜드 표식으로 두지 않는다.
  for (const node of all("#gil-companion *")) {
    if (node.children.length) continue;
    if (node.textContent.trim() === "G")
      throw new Error(`단독 G 가 남아 있다: .${node.className}`);
  }
  // 세 글자가 상자 안에 들어간다 — `l` 의 키도 `g` 의 꼬리도 잘리지 않는다.
  const box = boxOf(mark);
  const style = getComputedStyle(mark);
  if (box.width < 20 || box.height < 20) throw new Error("표식 상자가 너무 작다");
  if (mark.scrollWidth > Math.ceil(box.width) + 1)
    throw new Error(`글자가 상자를 넘는다 (${mark.scrollWidth} > ${box.width})`);
  if (mark.scrollHeight > Math.ceil(box.height) + 1)
    throw new Error(`글자가 상자 아래로 넘친다 (${mark.scrollHeight} > ${box.height})`);
  return `"${said}" · ${style.fontSize}/${style.letterSpacing} · ${box.width}×${box.height}px`;
});

// ── ⑯ 자동 갱신 ────────────────────────────────────────────────────
//
// watcher 는 Rust 가 쥔다. 여기서 재는 것은 **창이 hint 를 어떻게 다루는가** 다 —
// 완전한 조회 하나, single-flight, 그리고 선택 Step 의 운명.

check("57. 자동 갱신과 손 새로고침이 single-flight 를 함께 쓴다", async () => {
  await show("fixture:dense");
  let reading = 0;
  let release;
  await withHost(stubHost({
    loadView: async (scope) => {
      reading += 1;
      // 첫 조회를 붙들어 둔다 — 그 사이에 들어오는 것들이 무엇을 하는지 본다.
      if (reading === 1) await new Promise((go) => { release = go; });
      return REAL_HOST.loadView(scope);
    },
  }), async () => {
    const first = C().refresh();
    await wait(60);
    if (reading !== 1) throw new Error(`첫 조회가 ${reading}개다`);

    // 조회가 도는 동안 열 번이 더 들어온다 — 자동이든 손이든 같은 자리다.
    const piled = [];
    for (let i = 0; i < 10; i += 1) piled.push(C().refresh());
    await wait(60);
    if (reading !== 1) throw new Error(`도는 중에 조회가 ${reading}개로 늘었다`);

    release();
    await Promise.all([first, ...piled]);
    await wait(200);
    // **딱 한 번 더**다 — 열 번이 열 번을 만들지 않는다.
    if (reading !== 2) throw new Error(`후속 조회가 ${reading - 1}번이다 (한 번이어야 한다)`);
  });
  await show("fixture:dense");
  return `조회 2회 (첫 1 + 후속 1) · 그 사이 10번이 한 비트로 합쳐짐`;
});

check("58. 도는 중에 아무것도 안 오면 후속 조회가 없다", async () => {
  await show("fixture:dense");
  let reading = 0;
  await withHost(stubHost({
    loadView: async (scope) => {
      reading += 1;
      return REAL_HOST.loadView(scope);
    },
  }), async () => {
    await C().refresh();
    await wait(200);
    if (reading !== 1) throw new Error(`조회가 ${reading}번이다`);
  });
  await show("fixture:dense");
  return "조회 1회 · 헛된 후속 없음";
});

check("59. 새 View 뒤에도 고른 Step 이 남아 있으면 상세를 다시 읽는다", async () => {
  await show("fixture:reading-one");
  await C().selectStep("step:C2/S3");
  await wait(340);
  const kept = at(".detail h2").textContent;
  let details = 0;
  await withHost(stubHost({
    loadDetail: async (scope, step) => {
      details += 1;
      return REAL_HOST.loadDetail(scope, step);
    },
  }), async () => {
    await C().refresh();
    await wait(400);
    if (!details) throw new Error("상세를 다시 읽지 않았다");
    if (at(".detail h2").textContent !== kept) throw new Error("상세가 바뀌었다");
    if (!at(".card")) throw new Error("선택이 사라졌다");
  });
  await show("fixture:reading-one");
  return `${kept} 의 상세를 ${details}회 다시 읽음`;
});

check("60. 고른 Step 이 사라지면 다른 Step 을 추측하지 않고 비운다", async () => {
  await show("fixture:dense");
  await C().selectStep("step:C6/S1");
  await wait(340);
  if (!at(".detail h2")) throw new Error("고르지 못했다");

  await withHost(stubHost({
    loadView: async (scope) => {
      // 새 View 에는 그 Cycle 이 없다 — 사람이 되돌린 것과 같은 모양이다.
      const view = await REAL_HOST.loadView(scope);
      view.timeline = view.timeline.filter((one) => one.cycle_ref !== "cycle:C6");
      view.current = {
        ...view.current,
        cycle_ref: view.timeline.at(-1).cycle_ref,
        step_ref: view.timeline.at(-1).steps.at(-1).step_ref,
      };
      return view;
    },
  }), async () => {
    await C().refresh();
    await wait(400);
    // **비운다.** 가까운 Step 으로 물러서지 않는다(§7).
    if (at(".detail h2")) throw new Error(`상세가 ${at(".detail h2").textContent} 로 남았다`);
    if (at(".card")) throw new Error("카드가 남았다");
    if (all('[aria-selected="true"]').length) throw new Error("무언가가 골라진 채다");
    if (!C().plan().nodes.length) throw new Error("Graph 가 비었다");
  });
  await show("fixture:dense");
  return "선택과 상세를 비우고 Graph 는 남긴다";
});

check("61. 자동 갱신이 실패해도 마지막 Graph·상세를 지키고 낡음만 보인다", async () => {
  await show("fixture:reading-one");
  await C().selectStep("step:C2/S3");
  await wait(340);
  const kept = { nodes: C().plan().nodes.length, detail: at(".detail h2").textContent };
  let fail = true;
  await withHost(stubHost({
    loadView: async (scope) => {
      if (fail) throw Object.assign(new Error("쥐고 있다"), { code: "busy" });
      return REAL_HOST.loadView(scope);
    },
  }), async () => {
    await C().refresh();
    await wait(200);
    if (C().plan().nodes.length !== kept.nodes) throw new Error("Graph 가 지워졌다");
    if (at(".detail h2").textContent !== kept.detail) throw new Error("상세가 지워졌다");
    if (at(".stale").dataset.shown !== "true") throw new Error("낡음이 보이지 않는다");
    // 다음 성공에서 낡음이 걷힌다.
    fail = false;
    await C().refresh();
    await wait(400);
    if (at(".stale").dataset.shown === "true") throw new Error("성공했는데 낡음이 남았다");
  });
  await show("fixture:reading-one");
  return "실패에도 Graph·상세 유지 · 다음 성공에 낡음 걷힘";
});

check("62. 자동 갱신 도중 Project 를 바꾸면 앞의 결과가 새 화면에 닿지 않는다", async () => {
  C().seats.clear();
  await show("fixture:reading-one");
  await C().selectStep("step:C2/S3");
  await wait(340);

  const asked = [];
  let releaseA;
  await withHost(stubHost({
    loadView: async (scope) => {
      asked.push(scope);
      // A 의 조회를 붙들어 둔다 — 그 사이에 사람이 Project 를 바꾼다.
      if (scope === "fixture:reading-one" && asked.length === 1) {
        await new Promise((go) => { releaseA = go; });
      }
      return REAL_HOST.loadView(scope);
    },
  }), async () => {
    // ② A 의 watcher hint 로 느린 조회가 시작된다.
    const slow = C().refresh();
    await wait(80);
    if (asked.length !== 1) throw new Error(`A 의 조회가 ${asked.length}개다`);

    // ③ 끝나기 전에 B 로 바꾼다.
    await C().showScope("fixture:dense");
    await wait(200);
    // ④ B 가 보인다.
    if (C().scopeId() !== "fixture:dense") throw new Error("B 로 바뀌지 않았다");
    const seen = {
      scope: C().scopeId(),
      nodes: C().plan().nodes.length,
      detail: at(".detail h2") ? at(".detail h2").textContent : null,
      height: C().plan().height,
    };
    if (seen.detail) throw new Error("A 의 상세가 B 로 넘어왔다");

    // ⑤ 이제서야 A 의 조회가 성공한다.
    releaseA();
    await slow;
    await wait(300);

    // ⑥ **A 의 결과가 어디에도 닿지 않았다.**
    if (C().scopeId() !== seen.scope) throw new Error("scope 가 바뀌었다");
    if (C().plan().nodes.length !== seen.nodes)
      throw new Error(`Graph 가 A 의 것으로 바뀌었다 (${seen.nodes} → ${C().plan().nodes.length})`);
    if (C().plan().height !== seen.height) throw new Error("배치가 A 의 것으로 바뀌었다");
    if (at(".detail h2")) throw new Error(`A 의 상세가 늦게 들어왔다: ${at(".detail h2").textContent}`);
    if (at(".card")) throw new Error("A 의 선택이 늦게 들어왔다");
    // 접힘도 A 의 것이 아니다.
    if (all(".node.cycle").length) throw new Error("A 의 접힘이 넘어왔다");
  });

  // ⑦⑧ 은 Rust 쪽 `switching_projects_leaves_exactly_one_watcher` 가 잰다 —
  //     watcher 는 창이 아니라 Rust 가 쥐고 있기 때문이다.
  await show("fixture:reading-one");
  return `A 조회 ${asked.length}회 · 늦은 결과가 B 화면에 닿지 않음`;
});

// ── suite 를 돌리는 자리 ────────────────────────────────────────────

const BUDGET = 20000;   // 검사 하나에 주는 시간
const GRACE = 3000;     // 끊은 뒤 **정말로** 끝나기를 기다리는 시간

/** 검사가 남긴 것이 없는지 본다 — 있으면 장치가 오염된 것이다.
 *
 *  진행 표시는 **읽는 중인 조회가 남았는지**를 제품에 손대지 않고 볼 수 있는
 *  유일한 창이다(비어 있으면 논다). 막 끝난 조회가 표시를 지우는 데는 한 틱이
 *  걸리므로 한 번은 봐준다. */
const audit = async () => {
  if (window.GIL_HOST !== REAL_HOST) return "기준 문이 바뀐 채 남았다";
  if (depth !== 0) return `withHost 가 ${depth}겹 열린 채 남았다`;
  if (ledger) return "검사 장부가 닫히지 않았다";
  if (C().working() !== "") {
    await tick(150);
    if (C().working() !== "") return `조회가 끝나지 않은 채 남았다 — "${C().working()}"`;
  }
  return null;
};

/** 검사 하나를 돌린다.
 *
 *  `Promise.race` 로 실패만 적고 넘어가면 **뒤의 작업이 계속 살아** 다음 검사를
 *  오염시킨다. 그래서 시간이 지나면 먼저 장부를 끊어 모든 기다림을 되던지게 하고,
 *  본문이 정말 끝났는지 확인한 뒤에만 다음으로 간다. 끝나지 않으면 멈춘다. */
const runOne = async (body, budget = BUDGET, grace = GRACE) => {
  const mine = newLedger();
  ledger = mine;
  const spent = loads;
  let ended = false;
  const done = (async () => body())().finally(() => { ended = true; });
  const guard = done.then(
    (note) => ({ ok: true, note: note || "" }),
    (said) => ({ ok: false, note: String((said && said.message) || said) }),
  );

  let got = await Promise.race([guard, tick(budget).then(() => null)]);
  if (!got) {
    cutLedger(mine, `시간 초과 ${budget}ms`);
    const late = await Promise.race([guard, tick(grace).then(() => null)]);
    if (!late || !ended) {
      ledger = null;
      throw new HarnessError("시간 초과된 검사가 취소되지 않는다 — 다음 검사를 시작하지 않는다");
    }
    got = { ok: false, note: `시간 초과(${budget}ms) — 끊고 종료를 확인했다` };
  }
  ledger = null;
  cutLedger(mine, "끝났다");
  return { ...got, loads: loads - spent };
};

let running = null;   // 도는 suite 는 언제나 하나
let performed = 0;    // 본문이 실제로 불린 횟수 — 중복 실행을 계수로 잡는다

export function run() {
  // 두 suite 가 동시에 돌면 서로의 문을 밟는다 — 그것이 스텁 재귀의 지름길이었다.
  // 이미 돌고 있으면 **새로 시작하지 않고** 같은 것을 돌려준다. `async` 로 두면
  // 매 호출이 같은 값을 **새 Promise 로 감싸** 돌려주므로, 부른 쪽이 "같은 것인가"를
  // 확인할 수 없다. 그래서 이 문은 평범한 함수다.
  if (running) return running;
  running = (async () => {
    await C().ready;
    performed = 0;
    const results = [];
    for (const { name, body } of checks) {
      // 어디서 멈췄는지 밖에서 볼 수 있게. 멈춘 시험을 추측으로 찾지 않는다.
      window.GIL_SELFTEST_AT = name;
      // `elementFromPoint` 와 화면 안팎 판정은 **창 기준**이다. 앞선 시험이 `focus()` 나
      // `scrollIntoView()` 로 문서를 굴려 두면 그다음 시험이 엉뚱하게 실패한다 —
      // 제품이 아니라 시험 장치가 만든 실패다. 매번 처음으로 되돌리고 시작한다.
      window.scrollTo(0, 0);
      performed += 1;
      let got;
      try {
        got = await runOne(body);
      } catch (said) {
        if (!(said instanceof HarnessError)) throw said;
        results.push({ name, ok: false, note: `장치 오류 — ${said.message}` });
        break;                       // 오염된 장치로 뒤를 재지 않는다
      }
      results.push({ name, ok: got.ok, note: got.note, loads: got.loads });
      const dirty = await audit();
      if (dirty) {
        results.push({ name: `${name} · 뒤처리`, ok: false, note: `장치 오류 — ${dirty}` });
        break;
      }
    }
    // 시험이 남긴 접힘·선택을 치운다 — 사람이 이어서 볼 수도 있다.
    C().seats.clear();
    await C().showScope("fixture:reading-one");
    return results;
  })().finally(() => { running = null; });
  return running;
}


// ── 장치 자신을 재는 자리 ───────────────────────────────────────────
//
// suite 가 제품을 재려면 장치가 먼저 성해야 한다. 여기서 재는 것은 **장치**다:
// 기준점이 흔들리지 않는가, 문이 반드시 되돌아오는가, 끊은 검사가 정말 끝나는가.

export async function selfcheck() {
  const got = [];
  const probe = async (name, body) => {
    try { got.push({ name, ok: true, note: (await body()) || "" }); }
    catch (said) { got.push({ name, ok: false, note: String((said && said.message) || said) }); }
  };

  await probe("장치 1. 스텁이 스텁에 위임하면 만드는 자리에서 거절한다", async () => {
    const one = stubHost({});
    try { stubHost({}, one); } catch (said) {
      if (!(said instanceof HarnessError)) throw said;
      return "재귀가 되는 모양을 생성 시 거절";
    }
    throw new Error("자기 자신을 가리키는 스텁이 만들어졌다");
  });

  await probe("장치 2. 스텁은 지금 꽂힌 문이 아니라 기준점에 위임한다", async () => {
    const trap = { listProjects: () => { throw new Error("덫을 밟았다"); },
                   loadView: () => { throw new Error("덫을 밟았다"); },
                   loadDetail: () => { throw new Error("덫을 밟았다"); } };
    const was = window.GIL_HOST;
    window.GIL_HOST = trap;                 // 앞선 검사가 남긴 오염을 흉내 낸다
    try {
      const view = await stubHost({}).loadView("fixture:dense");
      if (!view || !view.timeline) throw new Error("기준점에 닿지 못했다");
      return "꽂힌 문이 덫이어도 기준점으로 간다";
    } finally { window.GIL_HOST = was; }
  });

  for (const [how, body] of [
    ["성공", async () => "값"],
    ["throw", async () => { throw new Error("일부러"); }],
    ["reject", () => Promise.reject(new Error("일부러"))],
  ]) {
    await probe(`장치 3-${how}. withHost 가 ${how} 뒤에도 문을 되돌린다`, async () => {
      await withHost(stubHost({}), body).catch(() => {});
      if (window.GIL_HOST !== REAL_HOST) throw new Error("문이 되돌아오지 않았다");
      if (depth !== 0) throw new Error(`withHost 가 ${depth}겹 남았다`);
      return "기준점 복원";
    });
  }

  await probe("장치 4. 끊긴 기다림은 매달리지 않고 되던진다", async () => {
    const mine = newLedger();
    ledger = mine;
    const waiting = wait(60000);
    cutLedger(mine, "시험");
    ledger = null;
    try { await waiting; } catch (said) {
      if (!(said instanceof Aborted)) throw said;
      return "60초 대기가 즉시 Aborted 로 깨어난다";
    }
    throw new Error("끊었는데 그냥 통과했다");
  });

  await probe("장치 5. 끊긴 frame 은 그리지 않는 창에서도 되던진다", async () => {
    const mine = newLedger();
    ledger = mine;
    const painting = frame();
    cutLedger(mine, "시험");
    ledger = null;
    try { await painting; } catch (said) {
      if (!(said instanceof Aborted)) throw said;
      return "rAF 가 오지 않아도 깨어난다";
    }
    throw new Error("끊었는데 그냥 통과했다");
  });

  await probe("장치 6. 시간 초과한 검사는 끊기고 **끝난 뒤에** 다음으로 간다", async () => {
    let alive = true;
    const verdict = await runOne(async () => { await wait(60000); alive = false; }, 60, 60);
    if (verdict.ok) throw new Error("시간 초과가 통과로 적혔다");
    if (!alive) throw new Error("본문이 끝까지 실행됐다");
    if (ledger) throw new Error("장부가 닫히지 않았다");
    return verdict.note;
  });

  await probe("장치 7. 취소되지 않는 검사는 다음을 시작하지 않고 멈춘다", async () => {
    let release;
    const stuck = new Promise((go) => { release = go; });   // 장부 밖 — 끊을 수 없다
    try {
      await runOne(() => stuck, 60, 60);
    } catch (said) {
      if (!(said instanceof HarnessError)) throw said;
      return "장치 오류로 suite 를 멈춘다";
    } finally { release(); }
    throw new Error("취소되지 않는데도 다음으로 넘어갔다");
  });

  await probe("장치 8. run() 이 도는 중 다시 부르면 같은 것을 돌려준다", async () => {
    const one = run();
    const two = run();
    if (one !== two) throw new Error("두 번째 호출이 새 suite 를 시작했다");
    await one;
    if (performed !== checks.length)
      throw new Error(`본문이 ${performed}번 불렸다 — ${checks.length}번이어야 한다`);
    return `본문 ${performed}회 · 중복 호출이 일을 늘리지 않았다`;
  });

  return got;
}

window.GIL_SELFTEST = {
  run, selfcheck, place,
  /** 폭주를 계수로 가르는 창 — `loadView` 가 지금까지 몇 번 불렸나. */
  loads: () => loads,
  /** 본문이 몇 번 불렸나 — 중복 `run()` 이 일을 두 배로 하지 않았음을 본다. */
  performed: () => performed,
  size: () => checks.length,
};
