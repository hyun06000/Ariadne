//! **여정을 하나의 시간축에 세운다** — 좌표까지만.
//!
//! # 왜 다시 지었는가
//!
//! 첫 구현은 Cycle 을 큰 node 로 놓고 그 사이를 자유로운 2차원 선으로 이었다. 2026-09-05
//! 인간 검토에서 폐기됐다 — Cycle 셋과 변 둘뿐인 작은 예시에서도 선이 서로 감싸고 교차해
//! **진행 방향을 읽을 수 없었다.**
//!
//! 그래서 문법을 바꾼다. Git Graph 처럼 짓는다.
//!
//! ```text
//! node   Cycle 이 아니라 Step 이다
//! 시간   위에서 아래로만 흐른다 — 새로 난 것은 언제나 아래에 놓인다
//! 갈래   고정된 세로 lane 이다 — 임의의 곡선 경로를 찾지 않는다
//! Cycle  큰 node 가 아니라 제 Step 행들을 감싸는 시각적 그룹이다
//! ```
//!
//! # 되돌아감은 위로 그리지 않는다
//!
//! 뜻으로는 과거를 참조하지만, **화면에서 뒤로 가는 선을 만들지 않는다.** 되돌아가 연 새
//! 시도는 시간상 나중 행에서 새 lane 으로 시작하고, 그 lane 의 출발점에 「무엇에서 갈라져
//! 나왔는가」와 「어느 경계를 이어받았는가」를 짧은 표식으로 적는다. 인과는 남고 방향은
//! 하나로 유지된다.
//!
//! # 두 가지 일을 가른다
//!
//! ```text
//! graph.rs   Snapshot → VisualGraph    무엇을 어디에 놓을지 정한다 (이 파일)
//! svg.rs     VisualGraph → SVG 글자     정해진 자리를 그린다
//! ```
//!
//! 가른 까닭은 시험 때문이다. **좌표를 사실로 시험하지 않는다** — 행·lane·그룹·변의 목록을
//! 시험한다.
//!
//! # 여기서 하지 않는 일
//!
//! Project 도 Session 도 파일도 다시 읽지 않는다. 입력은 이미 손에 쥔 [`MonitorSnapshot`]
//! 하나뿐이고, 같은 Snapshot 이면 **바이트까지 같은** 결과가 나온다. 시간 순서는
//! [`MonitorSnapshot::timeline`] 의 벡터 순서가 정한다 — 참조의 **번호를 비교하지 않는다.**

use std::collections::BTreeMap;

use crate::{CycleKind, CycleRef, MonitorSnapshot, NodeKind, NodeStatus, TimelineRelation};

// ── 상한 ───────────────────────────────────────────────────────────────────

/// 그림에 놓을 수 있는 Step 행의 최대 수.
///
/// 여정은 끝없이 자라지만 화면은 그렇지 않다. 상한이 없으면 오래 걸은 프로젝트가 **무한한
/// SVG** 를 만든다. read model 은 완전하고, 접는 것은 여기서 한다.
pub(crate) const MAX_VISUAL_ROWS: usize = 96;

/// 나란히 놓을 수 있는 lane 의 최대 수.
pub(crate) const MAX_VISUAL_LANES: usize = 8;

/// 그림에 놓을 수 있는 Cycle 그룹의 최대 수.
///
/// 그룹마다 이름표가 앉을 머리 띠가 붙으므로, 행 상한만으로는 높이가 묶이지 않는다 —
/// Step 하나짜리 Cycle 이 아흔여섯 개면 머리 띠만으로 그림이 두 배가 된다.
pub(crate) const MAX_VISUAL_GROUPS: usize = 12;

/// SVG 안의 요약은 **한 줄로 줄인다.**
///
/// 원문은 read model 에 온전히 있고, 상세 영역에서 그대로 읽을 수 있다. 여기서 줄이는 것은
/// 그림의 폭이 사용자 글의 길이에 매이지 않게 하기 위해서다.
pub(crate) const SUMMARY_MAX: usize = 28;

// ── 칸의 크기 ──────────────────────────────────────────────────────────────
//
// 전부 renderer 가 정한 상수다. 사용자 값에서 나온 수는 좌표에 **한 번도** 닿지 않는다.

/// 한 행의 높이.
pub(crate) const ROW_H: i32 = 40;

// ── 두 층으로 나눈다 ───────────────────────────────────────────────────────
//
// **lane 은 Cycle 의 내부 요소가 아니다.** Journey 가 어느 길로 왔는지를 보이는 독립된
// 층이고, Cycle 은 그 오른쪽 내용 층에서 제 Step 행들을 감싸는 그룹이다.
//
// ```text
//  0        LANE_ZONE_W   CONTENT_X0                          WIDTH
//  │  lane 층   │   이음선   │            내용 층                  │
//  │  ● ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┤ 문제  점수로 정렬하면…   step:C2/S1 │
//  │  │ ●┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┤ 가설  …                            │
//  └───┴────────┴───────────┴────────────────────────────────────┘
// ```
//
// 그러지 않으면 지금까지 이어지는 lane 이 실패한 Cycle 의 테두리 **안을** 지나가고,
// 사람은 그 Cycle 이 활성 경로에 들어 있다고 읽는다. 실측으로 그 혼동이 났다.

/// lane 하나의 가로 간격.
pub(crate) const LANE_W: i32 = 22;
/// 첫 lane 의 가운데까지.
pub(crate) const LANE_X0: i32 = 18;
/// lane 층이 차지하는 폭. **lane 수와 무관하게 고정이다** — 그래야 Cycle 그룹이 언제나
/// 같은 자리에서 시작하고, 그림이 결정적으로 남는다.
pub(crate) const LANE_ZONE_W: i32 = LANE_X0 + LANE_W * (MAX_VISUAL_LANES as i32 - 1) + 12;
/// 내용 층이 시작하는 자리. **Cycle 그룹의 왼쪽 끝이기도 하다.**
pub(crate) const CONTENT_X0: i32 = LANE_ZONE_W + 26;
/// Cycle 그룹의 머리 — 이름표가 앉을 빈 띠. **행과 겹치지 않게 하는 자리다.**
pub(crate) const GROUP_HEAD: i32 = 36;
/// 그룹과 그룹 사이의 틈.
pub(crate) const GROUP_GAP: i32 = 10;
/// 그림 전체의 폭. **고정이다** — 글이 길어도 늘어나지 않는다.
pub(crate) const WIDTH: i32 = CONTENT_X0 + 540;
pub(crate) const PAD: i32 = 14;

// ── 무엇을 그리는가 ────────────────────────────────────────────────────────

/// 이 행이 지금 어디에 서 있는가. **색이 아니라 이것이 굵기와 이름표를 정한다.**
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Standing {
    /// 지금 여기.
    Here,
    /// 지금까지 걸어온 길 위.
    Active,
    /// 두고 온 갈래.
    LeftBehind,
}

/// 이 Step 이 어떻게 끝났는가 — 또는 아직 안 끝났는가.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Mark {
    Open,
    Closed,
    /// 이 Cycle 이 성공으로 닫혔음을 알리는 마지막 Outcome.
    Succeeded,
    /// 이 Cycle 이 실패로 닫혔음을 알리는 마지막 Outcome.
    Failed,
}

impl Mark {
    /// 사람이 읽는 한 낱말. **색을 못 봐도 이것이 남는다.**
    pub(crate) fn word(self) -> &'static str {
        match self {
            Mark::Open => "열림",
            Mark::Closed => "닫힘",
            Mark::Succeeded => "성공",
            Mark::Failed => "실패",
        }
    }
}

/// 한 Step 행 — **화면에 찍히는 기본 node.**
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct VisualRow {
    /// typed reference — **작은 글씨로만** 남긴다.
    pub(crate) address: String,
    /// 사람이 먼저 읽는 이름. `검증` 처럼.
    pub(crate) kind: &'static str,
    /// Report 원문에서 온 한 줄. **여기서 이미 줄여 두었다.**
    pub(crate) summary: Option<String>,
    /// 원문이 잘렸는가 — 상세 영역에 전문이 있다는 표시.
    pub(crate) clipped: bool,
    pub(crate) standing: Standing,
    pub(crate) mark: Mark,
    /// 몇 번째 lane 인가.
    pub(crate) lane: usize,
    /// 위에서 몇 번째 행인가. **언제나 아래로만 자란다.**
    pub(crate) row: usize,
    pub(crate) x: i32,
    pub(crate) y: i32,
}

/// 한 시도 경로 — 고정된 세로 자리 하나.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct VisualLane {
    pub(crate) index: usize,
    /// 이 lane 이 시작하는 행.
    pub(crate) from_row: usize,
    /// 이 lane 이 끝나는 행. **실패한 lane 은 여기서 멈춘다.**
    pub(crate) to_row: usize,
    pub(crate) standing: Standing,
    /// 이 lane 이 어느 Cycle 의 것인가.
    pub(crate) cycle: String,
    pub(crate) x: i32,
}

/// Cycle 하나가 차지하는 행 범위 — **큰 node 가 아니라 감싸는 그룹이다.**
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct VisualGroup {
    pub(crate) address: String,
    /// 사람이 먼저 읽는 이름. `실험 C3` 처럼.
    pub(crate) name: String,
    pub(crate) kind: CycleKind,
    pub(crate) standing: Standing,
    pub(crate) mark: Mark,
    pub(crate) from_row: usize,
    pub(crate) to_row: usize,
    /// 이 Cycle 이 어느 lane 에 섰는가.
    pub(crate) lane: usize,
    /// 되돌아감으로 시작한 Cycle 이라면 그 출처와 이어받은 경계.
    ///
    /// **화면에서 위로 향하는 선을 만들지 않는다** — lane 출발점의 짧은 글로만 남는다.
    pub(crate) came_from: Option<Origin>,
    pub(crate) y: i32,
    pub(crate) height: i32,
}

/// 이 lane 이 어디서 비롯됐는가 — **글로만 적는다.**
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Origin {
    /// 어느 실패한 Cycle 의 판단에서 전환됐는가.
    pub(crate) after: String,
    /// 어느 Cycle 의 경계를 이어받아 시작했는가.
    pub(crate) resumed: Option<String>,
}

impl Origin {
    /// 사람이 읽는 한 줄.
    pub(crate) fn says(&self) -> String {
        match &self.resumed {
            Some(resumed) => format!("{} 실패 뒤 {} 자리에서 다시 시도", self.after, resumed),
            None => format!("{} 실패 뒤 다시 시도", self.after),
        }
    }
}

/// 두 행을 잇는 줄. **언제나 위 행에서 아래 행으로만 간다.**
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct VisualEdge {
    /// [`VisualGraph::rows`] 안의 자리. 언제나 `from.row < to.row` 다.
    pub(crate) from: usize,
    pub(crate) to: usize,
    /// 같은 lane 안의 곧은 진행인가, lane 을 옮기는 갈래인가.
    pub(crate) turn: bool,
}

/// 자리가 모자라 접은 것들.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Folded {
    pub(crate) rows: usize,
    pub(crate) cycles: usize,
}

impl Folded {
    pub(crate) fn says(&self) -> String {
        format!("이전 Cycle {}개 · Step {}개", self.cycles, self.rows)
    }
}

/// 그릴 것 전부 — **좌표까지 정해진 채로.**
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct VisualGraph {
    pub(crate) rows: Vec<VisualRow>,
    pub(crate) lanes: Vec<VisualLane>,
    pub(crate) groups: Vec<VisualGroup>,
    pub(crate) edges: Vec<VisualEdge>,
    /// 상한에 걸려 접은 것. **지워진 것이 아니다** — 아래 상세 기록에 그대로 있다.
    pub(crate) folded: Option<Folded>,
    pub(crate) width: i32,
    pub(crate) height: i32,
}

// ── 짓는다 ─────────────────────────────────────────────────────────────────

/// Snapshot 하나를 그림의 설계도로 옮긴다.
///
/// # 시간축
///
/// [`MonitorSnapshot::timeline`] 의 순서를 그대로 따른다. 그것이 구조가 주는 append-only
/// 발급 순서이고, 그래서 **번호를 비교할 일이 없다.** Cycle 안의 Step 도 만든 순서 그대로다.
///
/// ```text
/// row 0   C1 / 질문        ← 먼저 난 것이 위
/// row 1   C1 / 제안
/// row 2   C1 / 판정
/// row 3   C2 / 문제        ← 새 Cycle 은 언제나 아래에서 시작한다
/// ...
/// row 7   C2 / 판정  실패   ← 이 lane 은 여기서 끝난다
/// row 8   C3 / 문제        ← 되돌아가 연 새 시도는 **아래**의 새 lane
/// ```
///
/// # lane
///
/// Cycle 하나가 lane 하나를 쓴다. 지금까지 이어지는 계보는 **lane 0** 을 이어 쓰고, 두고 온
/// 갈래만 옆 lane 으로 나간다. 그래서 활성 경로가 하나의 끊기지 않는 세로줄로 읽힌다.
pub(crate) fn render_monitor_graph(seen: &MonitorSnapshot) -> VisualGraph {
    let here_cycle = seen.current_cycle.facts.cycle_ref.to_string();
    let here_step = seen.current_step.as_ref().map(|step| step.step_ref.to_string());

    // **여기서 사실을 조립하지 않는다.** 예전에는 `timeline`·`active_lineage`·
    // `inactive_cycles` 셋을 주소로 다시 이어 붙였는데, 그 조립은 layout 이 아니라 사실이라
    // read model 로 올라갔다. 이제 시간선 항목 하나가 제 Cycle 의 사실과 관계를 함께 지닌다.

    // ── 무엇을 남길지 먼저 정한다 ────────────────────────────────────────
    let kept = chosen(seen);
    let folded_cycles = seen.timeline.len() - kept.len();
    let folded_rows: usize = seen
        .timeline
        .iter()
        .filter(|entry| !kept.contains(&entry.facts.cycle_ref.to_string()))
        .map(|entry| entry.steps.len())
        .sum();

    // ── lane 을 나눈다 ───────────────────────────────────────────────────
    //
    // 계보는 lane 0 을 이어 쓴다. 두고 온 갈래만 옆으로 나간다 — 그래서 지금까지 이어지는
    // 길이 하나의 끊기지 않는 세로줄이 된다.
    let mut lane_of: BTreeMap<String, usize> = BTreeMap::new();
    let mut next_lane = 1usize;
    for entry in &seen.timeline {
        let address = entry.facts.cycle_ref.to_string();
        if !kept.contains(&address) {
            continue;
        }
        let lane = match entry.relation_to_current {
            TimelineRelation::ActivePath => 0,
            _ => {
                let lane = next_lane.min(MAX_VISUAL_LANES - 1);
                next_lane = (next_lane + 1).min(MAX_VISUAL_LANES - 1);
                lane
            }
        };
        lane_of.insert(address, lane);
    }

    // ── 행을 쌓는다 ──────────────────────────────────────────────────────
    let top = PAD + if folded_cycles > 0 { ROW_H } else { 0 };
    // **세로 자리는 하나의 커서가 정한다.** 그래서 그룹의 띠가 서로 겹칠 수 없고,
    // 이름표가 앉을 자리도 행이 시작하기 전에 확보된다.
    let mut y_at = top;
    let mut rows: Vec<VisualRow> = Vec::new();
    let mut groups: Vec<VisualGroup> = Vec::new();
    let mut lanes: Vec<VisualLane> = Vec::new();
    let mut edges: Vec<VisualEdge> = Vec::new();

    for entry in &seen.timeline {
        let facts = &entry.facts;
        let address = facts.cycle_ref.to_string();
        if !kept.contains(&address) {
            continue;
        }
        let Some(&lane) = lane_of.get(&address) else {
            continue;
        };
        // 지금 자리인지는 **현재 Cycle 의 참조와 견주어** 안다 — 시간선이 그것을 따로
        // 적어 두지 않는 까닭이고, 「지금 어디인가」를 말하는 자리는 하나뿐이어야 한다.
        let standing = match (address == here_cycle, entry.relation_to_current) {
            (true, _) => Standing::Here,
            (false, TimelineRelation::ActivePath) => Standing::Active,
            (false, _) => Standing::LeftBehind,
        };
        let verdict = facts.report.as_ref().map(|report| report.verdict.as_str());
        let closed = facts.state == NodeStatus::Closed;

        let first_row = rows.len();
        let group_y = y_at;
        y_at += GROUP_HEAD;
        let mut previous: Option<usize> = None;
        for step in &entry.steps {
            if rows.len() >= MAX_VISUAL_ROWS {
                break;
            }
            let row = rows.len();
            let step_address = step.step_ref.to_string();
            // Cycle 의 판정은 **마지막 Outcome** 이 진다 — 그 자리에만 성공·실패를 적는다.
            let last = std::ptr::eq(step, entry.steps.last().expect("비어 있지 않다"));
            let mark = mark_of(step.state, last && closed, verdict);
            let (summary, clipped) = shorten(step.summary.as_deref());
            rows.push(VisualRow {
                address: step_address.clone(),
                kind: korean(step.kind),
                summary,
                clipped,
                standing: match here_step.as_deref() == Some(step_address.as_str()) {
                    true => Standing::Here,
                    false => match standing {
                        Standing::Here => Standing::Active,
                        other => other,
                    },
                },
                mark,
                lane,
                row,
                x: LANE_X0 + lane as i32 * LANE_W,
                y: y_at,
            });
            y_at += ROW_H;
            // **아래로만 잇는다.** 앞 행에서 이 행으로.
            if let Some(from) = previous {
                edges.push(VisualEdge { from, to: row, turn: false });
            }
            previous = Some(row);
        }
        if rows.len() == first_row {
            y_at = group_y; // Step 이 하나도 없는 Cycle 은 자리도 차지하지 않는다
            continue;
        }
        let last_row = rows.len() - 1;

        // 앞 Cycle 의 마지막 행에서 이 Cycle 의 첫 행으로 — **lane 을 옮기는 갈래.**
        if let Some(parent) = facts.parent_cycle_ref.as_ref().map(CycleRef::to_string).as_deref()
            && let Some(from) = rows
                .iter()
                .rev()
                .find(|row| row.row < first_row && belongs(&groups, row.row, parent))
                .map(|row| row.row)
        {
            edges.push(VisualEdge { from, to: first_row, turn: true });
        }

        lanes.push(VisualLane {
            index: lane,
            from_row: first_row,
            to_row: last_row,
            standing,
            cycle: address.clone(),
            x: LANE_X0 + lane as i32 * LANE_W,
        });
        groups.push(VisualGroup {
            address: address.clone(),
            name: name_of(facts.kind, &address),
            kind: facts.kind,
            standing,
            mark: mark_of(facts.state, closed, verdict),
            from_row: first_row,
            to_row: last_row,
            lane,
            // **위로 향하는 선 대신 글 한 줄.** 인과는 남기고 방향은 하나로 둔다.
            came_from: facts.revisit_from_cycle_ref.as_ref().map(|after| Origin {
                after: named(seen, &after.to_string()),
                resumed: facts
                    .parent_cycle_ref
                    .as_ref()
                    .map(|parent| named(seen, &parent.to_string())),
            }),
            y: group_y,
            height: y_at - group_y - GROUP_GAP,
        });
        y_at += GROUP_GAP;
    }

    let height = y_at + PAD;
    VisualGraph {
        rows,
        lanes,
        groups,
        edges,
        folded: match folded_cycles {
            0 => None,
            _ => Some(Folded { rows: folded_rows, cycles: folded_cycles }),
        },
        width: WIDTH,
        height: height.max(ROW_H + PAD * 2),
    }
}

/// 그 행이 이 Cycle 의 것인가.
fn belongs(groups: &[VisualGroup], row: usize, cycle: &str) -> bool {
    groups
        .iter()
        .any(|group| group.address == cycle && group.from_row <= row && row <= group.to_row)
}

/// 무엇을 남기고 무엇을 접는가.
///
/// 상한을 넘으면 **먼저 남길 것을 정하고** 나머지를 접는다. 접는 것은 언제나 **오래된
/// 쪽**이다 — 지금을 이해하는 데 가까운 것은 최근 쪽이므로.
///
/// **ID 의 크기로 짐작하지 않는다.** 무엇이 활성인지는 계보 목록이 이미 말해 준다.
fn chosen(seen: &MonitorSnapshot) -> Vec<String> {
    let total: usize = seen.timeline.iter().map(|entry| entry.steps.len()).sum();
    if total <= MAX_VISUAL_ROWS && seen.timeline.len() <= MAX_VISUAL_GROUPS {
        return seen
            .timeline
            .iter()
            .map(|entry| entry.facts.cycle_ref.to_string())
            .collect();
    }
    // 반드시 남길 것 — 지금, 지금의 부모, 지금으로 이어진 되돌아감의 출처.
    let here = &seen.current_cycle.facts;
    let mut must: Vec<String> = vec![here.cycle_ref.to_string()];
    must.extend(here.parent_cycle_ref.as_ref().map(CycleRef::to_string));
    must.extend(here.revisit_from_cycle_ref.as_ref().map(CycleRef::to_string));
    must.extend(seen.pending_revisit.iter().map(|p| p.from_cycle_ref.to_string()));

    // 그 다음은 **최근부터 거슬러** 채운다.
    let mut room = MAX_VISUAL_ROWS;
    let mut lanes = MAX_VISUAL_LANES - 1;
    let mut groups = MAX_VISUAL_GROUPS;
    let mut kept: Vec<String> = Vec::new();
    for entry in seen.timeline.iter().rev() {
        let address = entry.facts.cycle_ref.to_string();
        let needed = entry.steps.len();
        let required = must.contains(&address);
        let branch = entry.relation_to_current != TimelineRelation::ActivePath;
        if !required && (needed > room || groups == 0 || (branch && lanes == 0)) {
            continue;
        }
        room = room.saturating_sub(needed);
        groups = groups.saturating_sub(1);
        if branch {
            lanes = lanes.saturating_sub(1);
        }
        kept.push(address);
    }
    // 시간선의 순서로 되돌린다 — 고른 순서가 아니라.
    seen.timeline
        .iter()
        .map(|entry| entry.facts.cycle_ref.to_string())
        .filter(|address| kept.contains(address))
        .collect()
}

// ── 이름 짓기 ──────────────────────────────────────────────────────────────

/// 사람이 먼저 읽는 이름 — typed reference 는 작은 글씨로 따로 남는다.
pub(super) fn name_of(kind: CycleKind, address: &str) -> String {
    let word = match kind {
        CycleKind::Experiment => "실험",
        CycleKind::Interview => "인터뷰",
    };
    match address.rsplit(':').next() {
        Some(id) if !id.is_empty() && id != address => format!("{word} {id}"),
        _ => word.to_string(),
    }
}

/// 판정을 **글자 하나**로 — 색을 못 봐도 남는 표시.
pub(super) fn mark_of(state: NodeStatus, decides: bool, verdict: Option<&str>) -> Mark {
    match state {
        NodeStatus::Open => Mark::Open,
        NodeStatus::Closed => match (decides, verdict) {
            (true, Some(said)) if said.eq_ignore_ascii_case("success") => Mark::Succeeded,
            (true, Some(said)) if said.eq_ignore_ascii_case("failure") => Mark::Failed,
            _ => Mark::Closed,
        },
    }
}

/// 요약 한 줄 — **짧게 잘라서.**
///
/// 글자 단위로 자른다. 바이트로 자르면 한글 한 글자가 두 동강 나 깨진 글자가 화면에 남는다.
/// 줄바꿈은 한 칸으로 접는다 — 여러 줄이 그림의 행 높이를 깨뜨리지 않게.
fn shorten(summary: Option<&str>) -> (Option<String>, bool) {
    let Some(raw) = summary else {
        return (None, false);
    };
    let flat: String = raw
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    if flat.is_empty() || is_placeholder(&flat) {
        return (None, false);
    }
    let taken: String = flat.chars().take(SUMMARY_MAX).collect();
    match flat.chars().count() > SUMMARY_MAX {
        true => (Some(format!("{taken}…")), true),
        false => (Some(taken), false),
    }
}

/// 이 글이 **자리만 채워 둔 표식**인가 — `<question>` 처럼.
///
/// 그런 값은 아무것도 말하지 않으면서 진짜 요약이 있는 자리처럼 보인다. 화면에서는
/// 비워 둔다. **read model 은 건드리지 않는다** — 원문은 원문대로 남고, 지어낸 대체
/// 문장을 넣지도 않는다. 여기서 하는 일은 그리지 않기로 정하는 것뿐이다.
///
/// Step 의 kind·상태·주소는 그대로 남으므로 그 Step 이 있었다는 사실은 사라지지 않는다.
fn is_placeholder(said: &str) -> bool {
    said.starts_with('<') && said.ends_with('>') && !said.contains(' ') && said.len() > 2
}

/// Step 종류의 사람 이름.
fn korean(kind: NodeKind) -> &'static str {
    match kind {
        NodeKind::Question => "질문",
        NodeKind::Interpretation => "해석",
        NodeKind::Synthesis => "제안",
        NodeKind::Define => "문제",
        NodeKind::Hypothesis => "가설",
        NodeKind::Verify => "검증",
        NodeKind::Analysis => "해석",
        NodeKind::Outcome => "판정",
        NodeKind::CycleEntry => "시작",
        NodeKind::CycleExit => "끝",
    }
}

/// 주소 하나를 사람의 이름으로 — 시간선에 없으면 주소를 그대로 둔다.
fn named(seen: &MonitorSnapshot, address: &str) -> String {
    match seen
        .timeline
        .iter()
        .find(|entry| entry.facts.cycle_ref.to_string() == address)
    {
        Some(entry) => name_of(entry.facts.kind, address),
        None => address.to_string(),
    }
}

#[cfg(test)]
pub(super) mod tests {
    use super::*;
    use crate::{
        CurrentCycleFacts, CycleRelation, CycleReportFacts, ExistenceFacts, ExistenceRef,
        InactiveCycle, JourneyRef, MonitorSnapshot, TimelineCycleFacts, SnapshotRef, StepFacts, StepRef, WorldFacts, WorldMark,
    };

    // ── 손으로 짓는 Snapshot ──────────────────────────────────────────────
    //
    // 여기서는 프로젝트를 걷지 않는다. **layout 이 무엇을 어디에 놓는가**만 재는 자리라,
    // 입력을 정확히 손에 쥐는 편이 낫다. 파일도, 잠금도, 시각도 끼어들지 않는다.

    fn cycle_ref(id: u32) -> CycleRef {
        format!("cycle:C{id}").parse().expect("주소")
    }

    fn step_ref(cycle: u32, step: u32) -> StepRef {
        format!("step:C{cycle}/S{step}").parse().expect("주소")
    }

    pub(in crate::monitor) fn step(
        cycle: u32,
        id: u32,
        kind: NodeKind,
        state: NodeStatus,
        summary: Option<&str>,
    ) -> StepFacts {
        StepFacts {
            step_ref: step_ref(cycle, id),
            kind,
            state,
            summary: summary.map(str::to_string),
        }
    }

    fn facts(
        id: u32,
        kind: CycleKind,
        state: NodeStatus,
        parent: Option<u32>,
    ) -> crate::CycleFacts {
        crate::CycleFacts {
            cycle_ref: cycle_ref(id),
            kind,
            state,
            parent_cycle_ref: parent.map(cycle_ref),
            revisit_from_cycle_ref: None,
            experiment_definition: None,
            report: None,
        }
    }

    fn report(verdict: &str) -> CycleReportFacts {
        CycleReportFacts {
            verdict: verdict.to_string(),
            handoff_summary: "넘긴 것".to_string(),
            outcome_lesson: None,
            next_direction: None,
        }
    }

    fn aside(id: u32, parent: Option<u32>, relation: CycleRelation) -> InactiveCycle {
        InactiveCycle {
            cycle_ref: cycle_ref(id),
            kind: CycleKind::Experiment,
            state: NodeStatus::Closed,
            parent_cycle_ref: parent.map(cycle_ref),
            revisit_from_cycle_ref: None,
            report: Some(report("failure")),
            relation_to_current: relation,
        }
    }

    /// 계보 위의 시간선 항목 하나.
    pub(in crate::monitor) fn on_path(
        facts: crate::CycleFacts,
        steps: Vec<StepFacts>,
    ) -> TimelineCycleFacts {
        TimelineCycleFacts {
            facts,
            relation_to_current: TimelineRelation::ActivePath,
            steps,
        }
    }

    fn bare(
        lineage: Vec<crate::CycleFacts>,
        inactive: Vec<InactiveCycle>,
        timeline: Vec<TimelineCycleFacts>,
    ) -> MonitorSnapshot {
        let current = lineage.last().expect("계보의 끝이 지금이다").clone();
        MonitorSnapshot {
            captured_at: super::super::CapturedAt(std::time::SystemTime::UNIX_EPOCH),
            current_existence: ExistenceFacts {
                existence_ref: "existence:X1".parse::<ExistenceRef>().expect("주소"),
                journey_ref: "journey:X1@J1".parse::<JourneyRef>().expect("주소"),
            },
            current_cycle: CurrentCycleFacts { facts: current, steps: Vec::new() },
            active_lineage: lineage,
            inactive_cycles: inactive,
            pending_revisit: None,
            current_step: None,
            current_will: None,
            world: WorldFacts {
                baseline_snapshot_ref: "snapshot:A1".parse::<SnapshotRef>().expect("주소"),
                state: WorldMark::Clean,
                reason: None,
                verify_can_confirm: false,
            },
            next_actions: Vec::new(),
            timeline,
        }
    }

    /// 판독 실험 1 의 모양 — 뿌리 하나, 실패한 갈래 하나, 되돌아와 선 지금.
    ///
    /// ```text
    /// C1 인터뷰 성공
    /// C2 실험   실패   ← 옆 lane 에서 끝난다
    /// C3 실험   열림   ← 되돌아가 연 새 시도. **아래**에서 시작한다
    /// ```
    pub(in crate::monitor) fn reading_one() -> MonitorSnapshot {
        let mut root = facts(1, CycleKind::Interview, NodeStatus::Closed, None);
        root.report = Some(report("success"));
        let mut here = facts(3, CycleKind::Experiment, NodeStatus::Open, Some(1));
        here.revisit_from_cycle_ref = Some(cycle_ref(2));
        here.experiment_definition = Some(crate::ExperimentDefinition {
            problem: "동점일 때 고유 ID를 보조 키로 사용하면 순서가 고정되는가".to_string(),
            success_condition: "100회 결과가 같고 ID의 고유성이 확인된다".to_string(),
        });
        let here_steps = vec![
            step(3, 1, NodeKind::Define, NodeStatus::Closed, Some("동점일 때 고유 ID를 보조 키로")),
            step(3, 2, NodeKind::Hypothesis, NodeStatus::Closed, Some("보조 키가 순서를 고정한다")),
            step(3, 3, NodeKind::Verify, NodeStatus::Open, None),
        ];
        let mut failed = facts(2, CycleKind::Experiment, NodeStatus::Closed, Some(1));
        failed.report = Some(report("failure"));
        let timeline = vec![
            on_path(
                root.clone(),
                vec![
                    step(1, 1, NodeKind::Question, NodeStatus::Closed, Some("무엇이 문제인가")),
                    step(1, 2, NodeKind::Synthesis, NodeStatus::Closed, Some("정렬이 흔들린다")),
                    step(1, 3, NodeKind::Outcome, NodeStatus::Closed, Some("실험으로 넘긴다")),
                ],
            ),
            TimelineCycleFacts {
                facts: failed,
                relation_to_current: TimelineRelation::RevisitSource,
                steps: vec![
                    step(2, 1, NodeKind::Define, NodeStatus::Closed, Some("점수로 정렬하면 순서가 달라진다")),
                    step(2, 2, NodeKind::Hypothesis, NodeStatus::Closed, Some("안정 정렬이면 고정될 것이다")),
                    step(2, 3, NodeKind::Verify, NodeStatus::Closed, Some("100회 중 17회가 달랐다")),
                    step(2, 4, NodeKind::Analysis, NodeStatus::Closed, Some("수집 순서가 그대로 남는다")),
                    step(2, 5, NodeKind::Outcome, NodeStatus::Closed, Some("점수만으로는 정할 수 없다")),
                ],
            },
            on_path(here.clone(), here_steps.clone()),
        ];
        let mut seen = bare(
            vec![root, here],
            vec![aside(2, Some(1), CycleRelation::RevisitSource)],
            timeline,
        );
        seen.current_cycle.steps = here_steps;
        seen.current_step = Some(seen.current_cycle.steps[2].clone());
        seen
    }

    // ── ① Step 이 기본 node 다 ────────────────────────────────────────────

    #[test]
    fn every_visible_node_is_a_step_and_a_cycle_is_only_a_group() {
        let seen = reading_one();
        let plan = render_monitor_graph(&seen);

        // 행의 수 = Step 의 수. Cycle 이 행을 하나도 차지하지 않는다.
        let steps: usize = seen.timeline.iter().map(|entry| entry.steps.len()).sum();
        assert_eq!(plan.rows.len(), steps, "행이 Step 수와 다르다");
        // 그리고 모든 행의 주소가 실제 Step 주소다.
        let known: Vec<String> = seen
            .timeline
            .iter()
            .flat_map(|entry| &entry.steps)
            .map(|step| step.step_ref.to_string())
            .collect();
        for row in &plan.rows {
            assert!(known.contains(&row.address), "{} 는 Step 이 아니다", row.address);
        }
        // Cycle 은 그룹으로만 있다.
        assert_eq!(plan.groups.len(), seen.timeline.len(), "Cycle 그룹 수가 다르다");
    }

    #[test]
    fn time_runs_downward_and_never_back() {
        let plan = render_monitor_graph(&reading_one());
        // 행 번호도 y 도 위에서 아래로만 자란다.
        for pair in plan.rows.windows(2) {
            assert!(pair[0].row < pair[1].row, "행 번호가 거꾸로 간다");
            assert!(pair[0].y < pair[1].y, "y 가 거꾸로 간다: {} → {}", pair[0].y, pair[1].y);
        }
        // 그리고 **모든 변이 아래로만** 간다.
        for edge in &plan.edges {
            let (from, to) = (&plan.rows[edge.from], &plan.rows[edge.to]);
            assert!(from.row < to.row, "{} → {} 가 위로 간다", from.address, to.address);
            assert!(from.y < to.y, "{} → {} 의 y 가 위로 간다", from.address, to.address);
        }
    }

    #[test]
    fn a_cycle_group_wraps_exactly_its_own_steps() {
        let seen = reading_one();
        let plan = render_monitor_graph(&seen);
        for group in &plan.groups {
            let entry = seen
                .timeline
                .iter()
                .find(|entry| entry.facts.cycle_ref.to_string() == group.address)
                .expect("시간선에 있는 Cycle");
            let inside: Vec<&VisualRow> = plan
                .rows
                .iter()
                .filter(|row| row.row >= group.from_row && row.row <= group.to_row)
                .collect();
            let mine: Vec<String> =
                entry.steps.iter().map(|step| step.step_ref.to_string()).collect();
            assert_eq!(
                inside.iter().map(|row| row.address.clone()).collect::<Vec<_>>(),
                mine,
                "{} 의 그룹이 제 Step 범위와 다르다",
                group.address
            );
            // 그리고 남의 Step 을 한 줄도 품지 않는다.
            for row in &plan.rows {
                let within = row.row >= group.from_row && row.row <= group.to_row;
                assert_eq!(within, mine.contains(&row.address), "{} 의 경계가 샜다", group.address);
            }
        }
        // 그룹의 띠는 서로 겹치지 않는다.
        for (i, one) in plan.groups.iter().enumerate() {
            for other in plan.groups.iter().skip(i + 1) {
                let apart = one.y + one.height <= other.y || other.y + other.height <= one.y;
                assert!(apart, "{} 와 {} 의 띠가 겹친다", one.address, other.address);
            }
        }
    }

    // ── ② lane ───────────────────────────────────────────────────────────

    #[test]
    fn the_path_that_still_runs_keeps_one_lane_and_the_branch_takes_another() {
        let plan = render_monitor_graph(&reading_one());
        let lane_of = |address: &str| {
            plan.groups
                .iter()
                .find(|group| group.address == address)
                .unwrap_or_else(|| panic!("{address} 이 없다"))
                .lane
        };
        // 지금까지 이어지는 길은 **같은 lane** 을 이어 쓴다.
        assert_eq!(lane_of("cycle:C1"), 0);
        assert_eq!(lane_of("cycle:C3"), 0);
        // 두고 온 갈래만 옆으로 나간다.
        assert_ne!(lane_of("cycle:C2"), 0, "버린 갈래가 활성 lane 을 썼다");
        // 행의 lane 도 같다.
        for row in &plan.rows {
            let group = plan
                .groups
                .iter()
                .find(|group| group.from_row <= row.row && row.row <= group.to_row)
                .expect("어느 그룹엔가 속한다");
            assert_eq!(row.lane, group.lane, "{} 의 lane 이 제 Cycle 과 다르다", row.address);
            assert_eq!(row.x, LANE_X0 + row.lane as i32 * LANE_W, "lane 자리가 어긋났다");
        }
    }

    #[test]
    fn the_active_lane_is_unbroken_down_to_the_current_step() {
        let plan = render_monitor_graph(&reading_one());
        let here = plan
            .rows
            .iter()
            .find(|row| row.standing == Standing::Here)
            .expect("지금 서 있는 행");
        assert_eq!(here.address, "step:C3/S3");

        // lane 0 의 행들이 **변으로 끊김 없이** 이어진다 — 사이에 다른 Cycle 이 끼어도.
        let active: Vec<&VisualRow> = plan.rows.iter().filter(|row| row.lane == 0).collect();
        assert!(active.len() >= 6, "활성 lane 이 너무 짧다");
        for pair in active.windows(2) {
            let joined = plan.edges.iter().any(|edge| {
                plan.rows[edge.from].address == pair[0].address
                    && plan.rows[edge.to].address == pair[1].address
            });
            assert!(joined, "{} 와 {} 사이가 끊겼다", pair[0].address, pair[1].address);
        }
        assert_eq!(active.last().expect("끝").address, here.address, "활성 lane 이 지금에서 끝나지 않는다");
    }

    #[test]
    fn a_failed_lane_stops_and_never_carries_on() {
        let plan = render_monitor_graph(&reading_one());
        let dead = plan
            .lanes
            .iter()
            .find(|lane| lane.cycle == "cycle:C2")
            .expect("버린 갈래의 lane");
        assert_eq!(dead.standing, Standing::LeftBehind);

        // 그 lane 의 마지막 행에서 나가는 변이 하나도 없다.
        let last = &plan.rows[dead.to_row];
        assert!(
            !plan.edges.iter().any(|edge| edge.from == dead.to_row),
            "끝난 갈래가 이후 Step 으로 이어졌다: {}",
            last.address
        );
        // 그리고 그 lane 을 쓰는 행은 그 Cycle 의 것뿐이다.
        for row in plan.rows.iter().filter(|row| row.lane == dead.index) {
            assert!(
                row.row >= dead.from_row && row.row <= dead.to_row,
                "{} 가 끝난 lane 을 이어 썼다",
                row.address
            );
        }
    }

    // ── ②-2 두 층이 겹치지 않는가 ────────────────────────────────────────

    #[test]
    fn the_lane_layer_and_the_cycle_layer_never_overlap() {
        let plan = render_monitor_graph(&reading_one());
        // 어떤 lane 도 내용 층에 발을 들이지 않는다.
        for lane in &plan.lanes {
            assert!(
                lane.x < CONTENT_X0,
                "lane {} 이 내용 층으로 넘어왔다: x={} ≥ {CONTENT_X0}",
                lane.index,
                lane.x
            );
            assert!(lane.x + LANE_W / 2 < CONTENT_X0, "lane 이 경계에 닿았다");
        }
        // 쓸 수 있는 **모든** lane 이 그렇다 — 지금 몇 개를 쓰든.
        for index in 0..MAX_VISUAL_LANES {
            let x = LANE_X0 + index as i32 * LANE_W;
            assert!(x + LANE_W / 2 < CONTENT_X0, "lane {index} 이 내용 층에 닿는다");
            assert!(x < LANE_ZONE_W, "lane {index} 이 제 층 밖에 있다");
        }
        // 그리고 Step 의 점도 전부 lane 층 안에 있다.
        for row in &plan.rows {
            assert!(row.x < LANE_ZONE_W, "{} 의 점이 lane 층 밖이다", row.address);
        }
    }

    #[test]
    fn a_cycle_group_wraps_no_lane_at_all() {
        let plan = render_monitor_graph(&reading_one());
        // 그룹은 세로 범위만 지닌다 — 가로로는 내용 층 하나뿐이고, 그 시작은 모든
        // lane 의 오른쪽이다. 그래서 이어지는 lane 이 실패한 Cycle 의 **안**을 지나는
        // 것처럼 읽힐 수 없다.
        let dead = plan
            .groups
            .iter()
            .find(|group| group.address == "cycle:C2")
            .expect("두고 온 Cycle");
        let active: Vec<&VisualLane> = plan.lanes.iter().filter(|lane| lane.index == 0).collect();
        assert!(!active.is_empty(), "이어지는 lane 이 없다");
        for lane in active {
            // 세로로는 겹친다 — 시간축이 그렇게 흐르므로.
            let overlaps_vertically = plan.rows[lane.from_row].y <= dead.y + dead.height
                && dead.y <= plan.rows[lane.to_row].y;
            // 그러나 **가로로는 결코 겹치지 않는다.**
            assert!(
                lane.x < CONTENT_X0,
                "이어지는 lane 이 두고 온 Cycle 의 띠 안으로 들어갔다"
            );
            let _ = overlaps_vertically;
        }
    }

    // ── ③ 되돌아감 ───────────────────────────────────────────────────────

    #[test]
    fn a_revisit_starts_a_later_lane_and_draws_no_line_backwards() {
        let plan = render_monitor_graph(&reading_one());
        let here = plan
            .groups
            .iter()
            .find(|group| group.address == "cycle:C3")
            .expect("지금 Cycle");
        let source = plan
            .groups
            .iter()
            .find(|group| group.address == "cycle:C2")
            .expect("실패한 갈래");

        // 새 시도는 **시간상 나중**에 있다.
        assert!(here.from_row > source.to_row, "되돌아간 시도가 출처보다 위에 있다");
        assert!(here.y > source.y, "되돌아간 시도의 y 가 위에 있다");

        // 인과는 **글로** 남는다 — 선이 아니라.
        let origin = here.came_from.as_ref().expect("어디서 왔는지가 적혀 있다");
        assert_eq!(origin.after, "실험 C2");
        assert_eq!(origin.resumed.as_deref(), Some("인터뷰 C1"));
        assert!(origin.says().contains("실패 뒤"), "{}", origin.says());
        assert!(origin.says().contains("다시 시도"), "{}", origin.says());

        // 그리고 출처에서 지금으로 가는 **변은 없다.**
        assert!(
            !plan.edges.iter().any(|edge| {
                plan.rows[edge.from].address.starts_with("step:C2")
                    && plan.rows[edge.to].address.starts_with("step:C3")
            }),
            "되돌아감을 선으로 그렸다"
        );
    }

    // ── ④ 결정적인가 ─────────────────────────────────────────────────────

    #[test]
    fn the_same_snapshot_draws_the_same_plan() {
        let seen = reading_one();
        assert_eq!(render_monitor_graph(&seen), render_monitor_graph(&seen));
    }

    #[test]
    fn the_layout_reads_only_the_timeline_for_its_order() {
        // 두 목록(계보·갈래)의 수집 순서가 달라져도 **자리는 그대로**여야 한다. 시간은
        // `timeline` 하나가 정하기 때문이다.
        let seen = reading_one();
        let mut shuffled = seen.clone();
        shuffled.active_lineage.reverse();
        shuffled.inactive_cycles.reverse();
        let places = |plan: &VisualGraph| -> Vec<(String, usize, usize, i32)> {
            plan.rows
                .iter()
                .map(|row| (row.address.clone(), row.row, row.lane, row.y))
                .collect()
        };
        assert_eq!(
            places(&render_monitor_graph(&seen)),
            places(&render_monitor_graph(&shuffled)),
            "목록의 순서가 자리를 바꿨다"
        );
    }

    // ── ⑤ 구조가 원본과 같은가 ───────────────────────────────────────────

    #[test]
    fn the_picture_says_what_the_typed_graph_says() {
        let seen = reading_one();
        let plan = render_monitor_graph(&seen);

        // 모든 Step 이 하나도 빠짐없이, 한 번씩만 있다.
        let mut drawn: Vec<&str> = plan.rows.iter().map(|row| row.address.as_str()).collect();
        drawn.sort_unstable();
        let mut truth: Vec<String> = seen
            .timeline
            .iter()
            .flat_map(|entry| &entry.steps)
            .map(|step| step.step_ref.to_string())
            .collect();
        truth.sort();
        assert_eq!(drawn, truth, "그림과 원본의 Step 집합이 다르다");

        // 지금 자리가 하나뿐이고 원본과 같다.
        let here: Vec<&VisualRow> = plan
            .rows
            .iter()
            .filter(|row| row.standing == Standing::Here)
            .collect();
        assert_eq!(here.len(), 1);
        assert_eq!(
            here[0].address,
            seen.current_step.as_ref().expect("열린 자리").step_ref.to_string()
        );
        // Cycle 의 판정도 원본과 같다.
        let mark = |address: &str| {
            plan.groups.iter().find(|g| g.address == address).expect("그룹").mark
        };
        assert_eq!(mark("cycle:C1"), Mark::Succeeded);
        assert_eq!(mark("cycle:C2"), Mark::Failed);
        assert_eq!(mark("cycle:C3"), Mark::Open);
        // 열린 Step 과 닫힌 Step 이 갈린다.
        let open: Vec<&str> = plan
            .rows
            .iter()
            .filter(|row| row.mark == Mark::Open)
            .map(|row| row.address.as_str())
            .collect();
        assert_eq!(open, ["step:C3/S3"], "열린 자리가 원본과 다르다");
    }

    // ── ⑥ 사용자 글이 자리를 깨뜨리지 않는가 ─────────────────────────────

    #[test]
    fn a_placeholder_is_not_a_summary() {
        let mut seen = reading_one();
        // 자리만 채워 둔 표식들.
        for (n, said) in ["<question>", "<hypothesis>", "<result>", "<statement>"]
            .iter()
            .enumerate()
        {
            seen.timeline[0].steps[n.min(2)].summary = Some(said.to_string());
        }
        // 그리고 진짜 요약 하나.
        seen.timeline[1].steps[0].summary = Some("점수로 정렬하면 순서가 달라진다".to_string());
        let plan = render_monitor_graph(&seen);

        for row in &plan.rows {
            if let Some(said) = &row.summary {
                assert!(
                    !(said.starts_with('<') && said.ends_with('>')),
                    "{} 가 자리표시를 요약이라고 내놓았다: {said}",
                    row.address
                );
            }
        }
        // 그러나 **Step 이 사라지지는 않는다** — 종류·상태·주소가 그대로 있다.
        let empty = plan
            .rows
            .iter()
            .find(|row| row.address == "step:C1/S1")
            .expect("첫 Step");
        assert_eq!(empty.summary, None, "자리표시가 비워지지 않았다");
        assert_eq!(empty.kind, "질문");
        assert_eq!(empty.mark, Mark::Closed);
        // 진짜 요약은 그대로 보인다.
        let real = plan
            .rows
            .iter()
            .find(|row| row.address == "step:C2/S1")
            .expect("실험의 문제");
        assert_eq!(real.summary.as_deref(), Some("점수로 정렬하면 순서가 달라진다"));
    }

    #[test]
    fn only_a_bare_angle_word_counts_as_a_placeholder() {
        // 꺾쇠로 시작하고 끝나도 **사람이 쓴 문장**이면 요약이다.
        for real in ["<a> 와 <b> 를 비교했다", "<>", "<", "> 이렇게 <"] {
            assert!(!is_placeholder(real), "{real:?} 를 자리표시로 봤다");
        }
        for fake in ["<question>", "<hypothesis>", "<result>"] {
            assert!(is_placeholder(fake), "{fake:?} 를 요약으로 봤다");
        }
    }

    #[test]
    fn long_and_nasty_and_multiline_summaries_do_not_move_anything() {
        let plain = render_monitor_graph(&reading_one());
        let mut seen = reading_one();
        let nasty = format!(
            "</text><script>alert(1)</script>\n둘째 줄\r\n\t셋째 & \"넷째\" 'x' {}",
            "가".repeat(4000)
        );
        for entry in &mut seen.timeline {
            for step in &mut entry.steps {
                step.summary = Some(nasty.clone());
            }
        }
        let plan = render_monitor_graph(&seen);

        // 자리는 한 칸도 움직이지 않는다.
        assert_eq!(plan.width, plain.width, "폭이 글을 따라 자랐다");
        assert_eq!(plan.height, plain.height, "높이가 글을 따라 자랐다");
        for (one, other) in plan.rows.iter().zip(&plain.rows) {
            assert_eq!((one.x, one.y, one.lane), (other.x, other.y, other.lane));
        }
        // 요약은 한 줄로 줄어 있고, 잘렸다는 표시가 붙는다.
        for row in &plan.rows {
            let said = row.summary.as_ref().expect("요약");
            assert!(said.chars().count() <= SUMMARY_MAX + 1, "{said}");
            assert!(!said.contains('\n') && !said.contains('\r') && !said.contains('\t'), "{said}");
            assert!(row.clipped, "잘렸는데 표시가 없다");
        }
    }

    // ── ⑦ 상한 ───────────────────────────────────────────────────────────

    #[test]
    fn a_long_journey_folds_instead_of_growing_without_end() {
        let mut lineage: Vec<crate::CycleFacts> = Vec::new();
        let mut timeline: Vec<TimelineCycleFacts> = Vec::new();
        for id in 1..=200 {
            let mut one = facts(
                id,
                CycleKind::Experiment,
                NodeStatus::Closed,
                (id > 1).then(|| id - 1),
            );
            one.report = Some(report("success"));
            lineage.push(one.clone());
            timeline.push(on_path(
                one,
                (1..=4)
                    .map(|n| step(id, n, NodeKind::Verify, NodeStatus::Closed, Some("걸었다")))
                    .collect(),
            ));
        }
        lineage.last_mut().expect("끝").state = NodeStatus::Open;
        let mut seen = bare(lineage, Vec::new(), timeline);
        seen.current_cycle.steps = seen.timeline.last().expect("끝").steps.clone();
        let plan = render_monitor_graph(&seen);

        assert!(plan.rows.len() <= 96, "행 상한을 넘었다: {}", plan.rows.len());
        assert_eq!(MAX_VISUAL_ROWS, 96, "상한이 조용히 바뀌었다");
        assert!(plan.height < 5_000, "그림이 끝없이 자랐다: {}", plan.height);
        // 접힌 것은 지워진 것이 아니라 세어져 있다.
        let folded = plan.folded.expect("접었으면 세어 두어야 한다");
        assert!(folded.cycles > 0 && folded.rows > 0);
        assert!(folded.says().contains("이전 Cycle"), "{}", folded.says());
        // 그리고 지금 자리는 무슨 일이 있어도 남는다.
        assert!(
            plan.groups.iter().any(|group| group.address == "cycle:C200"),
            "접다가 지금 Cycle 을 잃었다"
        );
    }
}
