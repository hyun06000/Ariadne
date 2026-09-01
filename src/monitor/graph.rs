//! **여정을 공간으로 옮긴다** — 좌표까지만.
//!
//! 2026-09-02 판독 실험 1 은 실패했고, 원인은 정보가 없어서가 아니었다. 화면이 전부 같은
//! 무게로 적혀 있어서 무엇이 지금이고 무엇이 지난 일인지 눈으로 갈라지지 않았다. 그래서
//! 이 파일이 생겼다 — **구조는 공간이 말하고, 글은 지금의 뜻만 말한다.**
//!
//! # 두 가지 일을 가른다
//!
//! ```text
//! graph.rs   Snapshot → VisualGraph    무엇을 어디에 놓을지 정한다 (이 파일)
//! svg.rs     VisualGraph → SVG 글자     정해진 자리를 그린다
//! ```
//!
//! 가른 까닭은 시험 때문이다. **좌표를 사실로 시험하지 않는다** — node 와 edge 의 목록을
//! 시험한다. 그림이 예뻐지느라 사실이 사라지는 일을 그래야 잡을 수 있다.
//!
//! # 여기서 하지 않는 일
//!
//! Project 도 Session 도 파일도 다시 읽지 않는다. 입력은 이미 손에 쥔 [`MonitorSnapshot`]
//! 하나뿐이고, 같은 Snapshot 이면 **바이트까지 같은** 결과가 나온다.

use crate::{CycleKind, CycleRelation, MonitorSnapshot, NodeKind, NodeStatus};

// ── 상한 ───────────────────────────────────────────────────────────────────

/// 그림에 놓을 수 있는 Cycle 의 최대 수.
///
/// 여정은 끝없이 자라지만 화면은 그렇지 않다. 상한이 없으면 오래 걸은 프로젝트가 **무한한
/// SVG** 를 만든다.
pub(crate) const MAX_VISUAL_CYCLES: usize = 64;

/// 현재 Cycle 안에 펼칠 수 있는 Step 의 최대 수.
pub(crate) const MAX_VISUAL_STEPS: usize = 32;

/// SVG 안의 글은 **짧은 이름표뿐**이다.
///
/// 사용자가 쓴 긴 문장이 node 에 들어가면 그림의 폭이 그 문장의 길이에 매인다. 긴 글은
/// 전부 옆의 focus panel 이 맡고, 여기서는 잘라서 맛만 보인다.
const HEADLINE_MAX: usize = 22;

// ── 칸의 크기 ──────────────────────────────────────────────────────────────
//
// 전부 renderer 가 정한 상수다. 사용자 값에서 나온 수는 좌표에 **한 번도** 닿지 않는다.

const NODE_W: i32 = 208;
const NODE_H: i32 = 66;
const ROW: i32 = 108;
const COL: i32 = 232;
/// 되돌아감의 점선이 지나갈 **왼쪽 여백.** node 를 뚫고 지나가지 않게 하는 자리다.
const GUTTER: i32 = 64;
const PAD: i32 = 16;
/// Step 이 늘어서는 아래 띠.
const LANE_H: i32 = 76;
const STEP_W: i32 = 84;
const STEP_GAP: i32 = 10;

// ── 무엇을 그리는가 ────────────────────────────────────────────────────────

/// 이 Cycle 이 지금 어디에 서 있는가. **색이 아니라 이것이 굵기와 이름표를 정한다.**
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Standing {
    /// 지금 여기.
    Here,
    /// 지금까지 걸어온 길 위.
    Active,
    /// 두고 온 갈래.
    LeftBehind,
}

/// 이 Cycle 이 어떻게 끝났는가 — 또는 아직 안 끝났는가.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Mark {
    Open,
    Succeeded,
    Failed,
    /// 닫혔는데 판정이 성공도 실패도 아니다.
    Closed,
}

impl Mark {
    /// 사람이 읽는 한 낱말. **색을 못 봐도 이것이 남는다.**
    pub(crate) fn word(self) -> &'static str {
        match self {
            Mark::Open => "열림",
            Mark::Succeeded => "성공",
            Mark::Failed => "실패",
            Mark::Closed => "닫힘",
        }
    }
}

/// 두 Cycle 을 잇는 줄의 종류.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Tie {
    /// 부모 — 실선.
    Parent,
    /// 되돌아감 — 점선. **계보의 변이 아니다.**
    Revisit,
}

impl Tie {
    /// 내부 칸 이름이 아니라 **사람의 말**로.
    ///
    /// `open_child` 나 `revisit_from` 을 그대로 크게 적으면 처음 보는 사람에게는 아무 뜻도
    /// 없다. 판독 실험 1 에서 실제로 걸린 자리다.
    pub(crate) fn says(self) -> &'static str {
        match self {
            Tie::Parent => "이 결과를 바탕으로 다음 실험을 시작함",
            Tie::Revisit => "이전 질문으로 돌아가 다른 방법을 시도함",
        }
    }
}

/// 그림 위의 Cycle 하나.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct VisualCycle {
    /// typed reference — **작은 글씨로만** 남긴다.
    pub(crate) address: String,
    /// 사람이 먼저 읽는 이름. `실험 C3` 처럼.
    pub(crate) name: String,
    pub(crate) kind: CycleKind,
    pub(crate) standing: Standing,
    pub(crate) mark: Mark,
    /// 짧게 자른 질문 한 조각. 없으면 없다.
    pub(crate) headline: Option<String>,
    /// **현재 Cycle 만** 채워진다.
    pub(crate) steps: Vec<VisualStep>,
    pub(crate) x: i32,
    pub(crate) y: i32,
}

/// 그림 위의 Step 하나.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct VisualStep {
    pub(crate) address: String,
    pub(crate) name: &'static str,
    pub(crate) open: bool,
    pub(crate) here: bool,
    pub(crate) x: i32,
    pub(crate) y: i32,
}

/// 두 Cycle 사이의 줄 하나.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct VisualEdge {
    /// [`VisualGraph::cycles`] 안의 자리.
    pub(crate) from: usize,
    pub(crate) to: usize,
    pub(crate) tie: Tie,
}

/// 자리가 모자라 접은 것들.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Folded {
    pub(crate) count: usize,
    pub(crate) x: i32,
    pub(crate) y: i32,
}

impl Folded {
    pub(crate) fn says(&self) -> String {
        format!("이전 Cycle {}개", self.count)
    }
}

/// 그릴 것 전부 — **좌표까지 정해진 채로.**
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct VisualGraph {
    pub(crate) cycles: Vec<VisualCycle>,
    pub(crate) edges: Vec<VisualEdge>,
    /// 상한에 걸려 접은 것. **지워진 것이 아니다** — 아래 상세 기록에 그대로 있다.
    pub(crate) folded: Option<Folded>,
    pub(crate) width: i32,
    pub(crate) height: i32,
}

// ── 짓는다 ─────────────────────────────────────────────────────────────────

/// Snapshot 하나를 그림의 설계도로 옮긴다.
///
/// # 무엇을 남기고 무엇을 접는가
///
/// 상한을 넘으면 **먼저 남길 것을 정하고** 나머지를 접는다. 남길 것의 목록은 「지금을
/// 이해하는 데 필요한 것」이다.
///
/// ```text
/// 지금 Cycle · 그 부모
/// 지금으로 이어진 되돌아감의 출처와 대상
/// 아직 소비되지 않은 되돌아감
/// 그 전환을 설명하는 실패한 갈래
/// 그러고도 자리가 남으면 최근 계보부터 거슬러
/// ```
///
/// **ID 의 크기로 짐작하지 않는다.** 무엇이 활성인지는 계보 목록과 `relation_to_current`
/// 가 이미 말해 준다 — 번호는 그것을 말하지 않는다.
pub(crate) fn render_monitor_graph(seen: &MonitorSnapshot) -> VisualGraph {
    let spine = chosen_spine(seen);
    let branches = chosen_branches(seen, spine.len());
    let folded_count = (seen.active_lineage.len() - spine.len())
        + (seen.inactive_cycles.len() - branches.len());

    let mut cycles: Vec<VisualCycle> = Vec::new();
    let top = PAD + if folded_count > 0 { ROW } else { 0 };

    // ── 계보는 곧은 줄기다. 한 칸에 하나, 위에서 아래로. ──────────────────
    for (row, facts) in spine.iter().enumerate() {
        let here = row + 1 == spine.len();
        cycles.push(VisualCycle {
            address: facts.cycle_ref.to_string(),
            name: name_of(facts.kind, &facts.cycle_ref.to_string()),
            kind: facts.kind,
            standing: match here {
                true => Standing::Here,
                false => Standing::Active,
            },
            mark: mark_of(facts.state, facts.report.as_ref().map(|r| r.verdict.as_str())),
            headline: headline_of(facts.experiment_definition.as_ref().map(|d| &d.problem)),
            steps: Vec::new(),
            x: GUTTER + PAD,
            y: top + row as i32 * ROW,
        });
    }

    // ── 두고 온 갈래는 제 부모의 **한 칸 아래, 오른쪽**에 선다. ───────────
    //
    // 줄기와 같은 칸을 쓰지 않으므로 부모에서 내려오는 실선이 다른 node 를 뚫지 않는다.
    let mut taken: Vec<usize> = vec![0; spine.len() + branches.len() + 2];
    for branch in &branches {
        let parent_row = branch
            .parent_cycle_ref
            .as_ref()
            .and_then(|parent| spine.iter().position(|f| &f.cycle_ref == parent));
        let row = match parent_row {
            Some(parent) => parent + 1,
            // 부모가 그림에 없다 — 맨 아래 띠에 둔다. 짐작으로 계보에 끼워 넣지 않는다.
            None => spine.len(),
        };
        let slot = row.min(taken.len() - 1);
        let column = 1 + taken[slot];
        taken[slot] += 1;
        cycles.push(VisualCycle {
            address: branch.cycle_ref.to_string(),
            name: name_of(branch.kind, &branch.cycle_ref.to_string()),
            kind: branch.kind,
            standing: Standing::LeftBehind,
            mark: mark_of(branch.state, branch.report.as_ref().map(|r| r.verdict.as_str())),
            headline: None,
            steps: Vec::new(),
            x: GUTTER + PAD + column as i32 * COL,
            y: top + row as i32 * ROW,
        });
    }

    let edges = tie_them(&cycles, seen);

    // ── 현재 Cycle 안의 Step 은 맨 아래 띠에 늘어선다. ────────────────────
    let rows = cycles
        .iter()
        .map(|cycle| (cycle.y - top) / ROW + 1)
        .max()
        .unwrap_or(1);
    // Step 띠는 마지막 줄에서 **넉넉히 떨어뜨린다.** 붙여 두면 「현재」 표식이 위 node 의
    // 테두리에 닿는다(실측으로 2px 까지 붙었다).
    let lane_y = top + rows * ROW - (ROW - NODE_H) + PAD + 26;
    let steps = lay_steps(seen, lane_y);
    let has_steps = !steps.is_empty();
    if let Some(here) = cycles
        .iter()
        .position(|cycle| cycle.standing == Standing::Here)
    {
        cycles[here].steps = steps;
    }

    let columns = cycles
        .iter()
        .map(|cycle| (cycle.x - GUTTER - PAD) / COL + 1)
        .max()
        .unwrap_or(1);
    let width = GUTTER + PAD * 2 + columns * COL - (COL - NODE_W);
    let height = lane_y + if has_steps { LANE_H } else { 0 } + PAD;

    VisualGraph {
        cycles,
        edges,
        folded: match folded_count {
            0 => None,
            count => Some(Folded {
                count,
                x: GUTTER + PAD,
                y: PAD,
            }),
        },
        width: width.max(NODE_W + GUTTER + PAD * 2),
        height: height.max(NODE_H + PAD * 2),
    }
}

/// 줄기에 남길 계보 — **뒤에서부터** 자른다.
///
/// 잘라야 한다면 오래된 쪽을 접는다. 지금을 이해하는 데 가까운 것은 최근 쪽이다.
fn chosen_spine(seen: &MonitorSnapshot) -> Vec<&crate::CycleFacts> {
    let all = &seen.active_lineage;
    // 줄기가 쓸 수 있는 자리 — 갈래에게도 얼마쯤 남겨 둔다.
    let room = MAX_VISUAL_CYCLES.saturating_sub(seen.inactive_cycles.len().min(16));
    match all.len() <= room {
        true => all.iter().collect(),
        false => all[all.len() - room.max(2)..].iter().collect(),
    }
}

/// 그림에 남길 두고 온 갈래.
///
/// 지금의 전환을 설명하는 것부터 남긴다 — 되돌아감의 출처가 먼저다.
fn chosen_branches(seen: &MonitorSnapshot, spine: usize) -> Vec<&crate::InactiveCycle> {
    let room = MAX_VISUAL_CYCLES.saturating_sub(spine);
    let mut chosen: Vec<&crate::InactiveCycle> = Vec::new();
    // ① 지금 여기로 오게 만든 갈래.
    for cycle in &seen.inactive_cycles {
        if cycle.relation_to_current == CycleRelation::RevisitSource && chosen.len() < room {
            chosen.push(cycle);
        }
    }
    // ② 같은 자리에서 갈라진 형제.
    for cycle in &seen.inactive_cycles {
        if cycle.relation_to_current == CycleRelation::Abandoned && chosen.len() < room {
            chosen.push(cycle);
        }
    }
    // ③ 나머지.
    for cycle in &seen.inactive_cycles {
        if cycle.relation_to_current == CycleRelation::Other && chosen.len() < room {
            chosen.push(cycle);
        }
    }
    // 그림의 순서는 Snapshot 의 순서를 따른다 — 고른 순서가 아니라.
    let mut ordered: Vec<&crate::InactiveCycle> = seen
        .inactive_cycles
        .iter()
        .filter(|cycle| chosen.iter().any(|kept| kept.cycle_ref == cycle.cycle_ref))
        .collect();
    ordered.truncate(room);
    ordered
}

/// 줄들을 잇는다 — **부모는 실선, 되돌아감은 점선.**
///
/// 두 끝이 **모두 그림 위에 있을 때만** 긋는다. 한쪽이 접혀 있는데 줄만 그으면 그 줄은
/// 아무 데도 닿지 않은 채 뜬다.
fn tie_them(cycles: &[VisualCycle], seen: &MonitorSnapshot) -> Vec<VisualEdge> {
    let at = |address: &str| cycles.iter().position(|cycle| cycle.address == address);
    let mut edges = Vec::new();
    let mut add = |from: Option<usize>, to: Option<usize>, tie: Tie| {
        if let (Some(from), Some(to)) = (from, to)
            && from != to
        {
            edges.push(VisualEdge { from, to, tie });
        }
    };
    for facts in &seen.active_lineage {
        let child = at(&facts.cycle_ref.to_string());
        add(
            facts.parent_cycle_ref.as_ref().and_then(|r| at(&r.to_string())),
            child,
            Tie::Parent,
        );
        add(
            facts
                .revisit_from_cycle_ref
                .as_ref()
                .and_then(|r| at(&r.to_string())),
            child,
            Tie::Revisit,
        );
    }
    for cycle in &seen.inactive_cycles {
        let child = at(&cycle.cycle_ref.to_string());
        add(
            cycle.parent_cycle_ref.as_ref().and_then(|r| at(&r.to_string())),
            child,
            Tie::Parent,
        );
        add(
            cycle
                .revisit_from_cycle_ref
                .as_ref()
                .and_then(|r| at(&r.to_string())),
            child,
            Tie::Revisit,
        );
    }
    // 아직 소비되지 않은 되돌아감도 줄 하나다 — 출처에서 지금 자리로.
    if let Some(pending) = &seen.pending_revisit {
        add(
            at(&pending.from_cycle_ref.to_string()),
            at(&seen.current_cycle.facts.cycle_ref.to_string()),
            Tie::Revisit,
        );
    }
    edges
}

/// 현재 Cycle 의 Step 을 아래 띠에 늘어놓는다.
///
/// **현재 Cycle 만 펼친다.** 조상마다 Step 을 늘어놓으면 그림이 곧 전체 history 가 되고,
/// 그러면 지금이 어디인지가 다시 묻혀 버린다.
fn lay_steps(seen: &MonitorSnapshot, lane_y: i32) -> Vec<VisualStep> {
    let all = &seen.current_cycle.steps;
    let here = seen.current_step.as_ref().map(|step| &step.step_ref);
    // 상한을 넘으면 **끝쪽**을 남긴다 — 지금 자리가 거기 있다.
    let from = all.len().saturating_sub(MAX_VISUAL_STEPS);
    all[from..]
        .iter()
        .enumerate()
        .map(|(column, step)| VisualStep {
            address: step.step_ref.to_string(),
            name: korean(step.kind),
            open: step.state == NodeStatus::Open,
            here: here == Some(&step.step_ref),
            x: GUTTER + PAD + column as i32 * (STEP_W + STEP_GAP),
            y: lane_y,
        })
        .collect()
}

// ── 이름 짓기 ──────────────────────────────────────────────────────────────

/// 사람이 먼저 읽는 이름 — typed reference 는 작은 글씨로 따로 남는다.
pub(super) fn name_of(kind: CycleKind, address: &str) -> String {
    let word = match kind {
        CycleKind::Experiment => "실험",
        CycleKind::Interview => "인터뷰",
    };
    // `cycle:C3` 에서 `C3` 만. 없으면 종류 이름 하나로 둔다.
    match address.rsplit(':').next() {
        Some(id) if !id.is_empty() && id != address => format!("{word} {id}"),
        _ => word.to_string(),
    }
}

/// 판정을 **글자 하나**로 — 색을 못 봐도 남는 표시.
pub(super) fn mark_of(state: NodeStatus, verdict: Option<&str>) -> Mark {
    match state {
        NodeStatus::Open => Mark::Open,
        NodeStatus::Closed => match verdict {
            Some(said) if said.eq_ignore_ascii_case("success") => Mark::Succeeded,
            Some(said) if said.eq_ignore_ascii_case("failure") => Mark::Failed,
            _ => Mark::Closed,
        },
    }
}

/// 질문 한 조각 — **짧게 잘라서.**
///
/// 글자 단위로 자른다. 바이트로 자르면 한글 한 글자가 두 동강 나 깨진 글자가 화면에 남는다.
fn headline_of(problem: Option<&String>) -> Option<String> {
    let problem = problem?.trim();
    if problem.is_empty() {
        return None;
    }
    let taken: String = problem.chars().take(HEADLINE_MAX).collect();
    Some(match problem.chars().count() > HEADLINE_MAX {
        true => format!("{taken}…"),
        false => taken,
    })
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
        NodeKind::CycleEntry => "시작 경계",
        NodeKind::CycleExit => "끝 경계",
    }
}

#[cfg(test)]
pub(super) mod tests {
    use super::*;
    use crate::{
        CurrentCycleFacts, CycleReportFacts, CycleRef, ExistenceFacts, ExistenceRef, InactiveCycle,
        JourneyRef, MonitorSnapshot, SnapshotRef, StepFacts, StepRef, WorldFacts, WorldMark,
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

    fn facts(id: u32, kind: CycleKind, state: NodeStatus, parent: Option<u32>) -> crate::CycleFacts {
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

    fn snapshot(lineage: Vec<crate::CycleFacts>, inactive: Vec<InactiveCycle>) -> MonitorSnapshot {
        let current = lineage.last().expect("계보의 끝이 지금이다").clone();
        MonitorSnapshot {
            captured_at: super::super::CapturedAt(std::time::SystemTime::UNIX_EPOCH),
            current_existence: ExistenceFacts {
                existence_ref: "existence:X1".parse::<ExistenceRef>().expect("주소"),
                journey_ref: "journey:X1@J1".parse::<JourneyRef>().expect("주소"),
            },
            current_cycle: CurrentCycleFacts {
                facts: current,
                steps: Vec::new(),
            },
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
        }
    }

    /// 판독 실험 1 의 모양 — 뿌리 하나, 실패한 갈래 하나, 되돌아와 선 지금.
    pub(in crate::monitor) fn reading_one() -> MonitorSnapshot {
        let mut root = facts(1, CycleKind::Interview, NodeStatus::Closed, None);
        root.report = Some(report("success"));
        let mut here = facts(3, CycleKind::Experiment, NodeStatus::Open, Some(1));
        here.revisit_from_cycle_ref = Some(cycle_ref(2));
        here.experiment_definition = Some(crate::ExperimentDefinition {
            problem: "동점일 때 고유 ID를 보조 키로 사용하면 순서가 고정되는가".to_string(),
            success_condition: "100회 결과가 같고 ID의 고유성이 확인된다".to_string(),
        });
        let mut seen = snapshot(
            vec![root, here],
            vec![aside(2, Some(1), CycleRelation::RevisitSource)],
        );
        seen.current_cycle.steps = vec![
            StepFacts { step_ref: step_ref(3, 1), kind: NodeKind::Define, state: NodeStatus::Closed },
            StepFacts { step_ref: step_ref(3, 2), kind: NodeKind::Hypothesis, state: NodeStatus::Closed },
            StepFacts { step_ref: step_ref(3, 3), kind: NodeKind::Verify, state: NodeStatus::Open },
        ];
        seen.current_step = Some(seen.current_cycle.steps[2].clone());
        seen
    }

    /// 두 상자가 겹치는가.
    fn overlaps(a: (i32, i32, i32, i32), b: (i32, i32, i32, i32)) -> bool {
        a.0 < b.0 + b.2 && b.0 < a.0 + a.2 && a.1 < b.1 + b.3 && b.1 < a.1 + a.3
    }

    // ── ① 무엇을 어디에 두는가 ────────────────────────────────────────────

    #[test]
    fn the_current_cycle_is_the_only_one_standing_here() {
        let plan = render_monitor_graph(&reading_one());
        let here: Vec<&VisualCycle> = plan
            .cycles
            .iter()
            .filter(|cycle| cycle.standing == Standing::Here)
            .collect();
        assert_eq!(here.len(), 1, "지금 자리가 하나가 아니다");
        assert_eq!(here[0].address, "cycle:C3");
        // 계보 위의 조상은 활성, 갈래는 뒤로.
        let standing = |address: &str| {
            plan.cycles
                .iter()
                .find(|cycle| cycle.address == address)
                .unwrap_or_else(|| panic!("{address} 가 그림에 없다"))
                .standing
        };
        assert_eq!(standing("cycle:C1"), Standing::Active);
        assert_eq!(standing("cycle:C2"), Standing::LeftBehind);
    }

    #[test]
    fn a_revisit_is_never_drawn_as_a_parent() {
        let plan = render_monitor_graph(&reading_one());
        let name = |at: usize| plan.cycles[at].address.as_str();
        let parents: Vec<(&str, &str)> = plan
            .edges
            .iter()
            .filter(|edge| edge.tie == Tie::Parent)
            .map(|edge| (name(edge.from), name(edge.to)))
            .collect();
        let revisits: Vec<(&str, &str)> = plan
            .edges
            .iter()
            .filter(|edge| edge.tie == Tie::Revisit)
            .map(|edge| (name(edge.from), name(edge.to)))
            .collect();
        assert_eq!(parents, [("cycle:C1", "cycle:C3"), ("cycle:C1", "cycle:C2")]);
        assert_eq!(revisits, [("cycle:C2", "cycle:C3")]);
        // 되돌아감이 계보의 변으로 새지 않았다.
        assert!(!parents.contains(&("cycle:C2", "cycle:C3")), "되돌아감을 부모로 그렸다");
    }

    #[test]
    fn the_two_ties_speak_human_words_not_field_names() {
        for tie in [Tie::Parent, Tie::Revisit] {
            let said = tie.says();
            for internal in ["open_child", "revisit_from", "next_direction", "parent_cycle_ref"] {
                assert!(!said.contains(internal), "{said:?} 에 내부 칸 이름이 있다");
            }
            assert!(said.chars().any(|ch| ch > '\u{7f}'), "{said:?} 가 사람의 말이 아니다");
        }
    }

    #[test]
    fn only_the_current_cycle_unfolds_its_steps() {
        let plan = render_monitor_graph(&reading_one());
        for cycle in &plan.cycles {
            match cycle.standing {
                Standing::Here => assert_eq!(cycle.steps.len(), 3, "지금 Cycle 이 접혀 있다"),
                _ => assert!(cycle.steps.is_empty(), "{} 가 Step 을 펼쳤다", cycle.address),
            }
        }
        let steps = &plan.cycles[plan
            .cycles
            .iter()
            .position(|c| c.standing == Standing::Here)
            .expect("지금")]
        .steps;
        // 지금 Step 하나만 표식을 가진다.
        assert_eq!(steps.iter().filter(|step| step.here).count(), 1);
        assert!(steps[2].here && steps[2].open, "지금 Step 이 마지막의 열린 것이 아니다");
        // 순서가 보인다 — 왼쪽에서 오른쪽으로.
        assert!(steps[0].x < steps[1].x && steps[1].x < steps[2].x, "Step 의 순서가 없다");
    }

    // ── ② 겹치지 않는가 ──────────────────────────────────────────────────

    #[test]
    fn no_two_boxes_sit_on_top_of_each_other() {
        // 넉넉히 벌린 여정 하나 — 계보 · 갈래 · Step 이 모두 있는 자리.
        let mut lineage: Vec<crate::CycleFacts> = Vec::new();
        for id in 1..=6 {
            let mut one = facts(
                id,
                CycleKind::Experiment,
                NodeStatus::Closed,
                (id > 1).then(|| id - 1),
            );
            one.report = Some(report("success"));
            lineage.push(one);
        }
        lineage.last_mut().expect("끝").state = NodeStatus::Open;
        let inactive = vec![
            aside(11, Some(1), CycleRelation::Abandoned),
            aside(12, Some(1), CycleRelation::Other),
            aside(13, Some(3), CycleRelation::RevisitSource),
        ];
        let mut seen = snapshot(lineage, inactive);
        seen.current_cycle.steps = (1..=5)
            .map(|n| StepFacts {
                step_ref: step_ref(6, n),
                kind: NodeKind::Verify,
                state: NodeStatus::Closed,
            })
            .collect();
        let plan = render_monitor_graph(&seen);

        let mut boxes: Vec<(i32, i32, i32, i32)> = plan
            .cycles
            .iter()
            .map(|cycle| (cycle.x, cycle.y, NODE_W, NODE_H))
            .collect();
        for cycle in &plan.cycles {
            for step in &cycle.steps {
                boxes.push((step.x, step.y, STEP_W, 34));
            }
        }
        for (i, one) in boxes.iter().enumerate() {
            for other in boxes.iter().skip(i + 1) {
                assert!(!overlaps(*one, *other), "{one:?} 와 {other:?} 가 겹친다");
            }
        }
        // 그리고 전부 그림 안에 있다.
        for (x, y, w, h) in boxes {
            assert!(x >= 0 && y >= 0, "음수 좌표가 나왔다");
            assert!(x + w <= plan.width, "가로로 잘렸다: {x}+{w} > {}", plan.width);
            assert!(y + h <= plan.height, "세로로 잘렸다: {y}+{h} > {}", plan.height);
        }
    }

    // ── ③ 상한 ───────────────────────────────────────────────────────────

    #[test]
    fn a_long_journey_folds_instead_of_growing_without_end() {
        let mut lineage: Vec<crate::CycleFacts> = Vec::new();
        for id in 1..=400 {
            let mut one = facts(
                id,
                CycleKind::Experiment,
                NodeStatus::Closed,
                (id > 1).then(|| id - 1),
            );
            one.report = Some(report("success"));
            lineage.push(one);
        }
        lineage.last_mut().expect("끝").state = NodeStatus::Open;
        let inactive: Vec<InactiveCycle> = (500..560)
            .map(|id| aside(id, Some(2), CycleRelation::Other))
            .collect();
        let plan = render_monitor_graph(&snapshot(lineage, inactive));

        assert!(plan.cycles.len() <= 64, "상한을 넘었다: {}", plan.cycles.len());
        assert_eq!(MAX_VISUAL_CYCLES, 64, "상한이 조용히 바뀌었다");
        // 접힌 것은 지워진 것이 아니라 **세어져 있다.**
        let folded = plan.folded.expect("접었으면 세어 두어야 한다");
        assert!(folded.count > 0);
        assert!(folded.says().contains("이전 Cycle"), "{}", folded.says());
        // 무슨 일이 있어도 지금 자리는 남는다.
        assert_eq!(
            plan.cycles
                .iter()
                .filter(|cycle| cycle.standing == Standing::Here)
                .count(),
            1,
            "접다가 지금 자리를 잃었다"
        );
        assert_eq!(
            plan.cycles
                .iter()
                .find(|cycle| cycle.standing == Standing::Here)
                .expect("지금")
                .address,
            "cycle:C400"
        );
        // 그리고 그림이 끝없이 자라지 않는다.
        assert!(plan.height < 8_000 && plan.width < 8_000, "{}x{}", plan.width, plan.height);
    }

    #[test]
    fn too_many_steps_keep_the_end_where_the_present_is() {
        let mut seen = reading_one();
        seen.current_cycle.steps = (1..=200)
            .map(|n| StepFacts {
                step_ref: step_ref(3, n),
                kind: NodeKind::Verify,
                state: NodeStatus::Closed,
            })
            .collect();
        seen.current_step = seen.current_cycle.steps.last().cloned();
        let plan = render_monitor_graph(&seen);
        let steps = &plan.cycles[plan
            .cycles
            .iter()
            .position(|c| c.standing == Standing::Here)
            .expect("지금")]
        .steps;
        // **상수를 상수로 재지 않는다.** 상한을 키우는 것만으로 통과하면 상한이 아니다.
        assert!(steps.len() <= 32, "Step 상한을 넘었다: {}", steps.len());
        assert_eq!(MAX_VISUAL_STEPS, 32, "상한이 조용히 바뀌었다");
        // 그리고 그림이 Step 수를 따라 자라지 않는다.
        let plan_width = plan.width;
        assert!(plan_width < 3_000, "그림이 Step 을 따라 자랐다: {plan_width}");
        assert!(
            steps.iter().any(|step| step.here),
            "Step 을 자르다 지금 자리를 잃었다"
        );
        assert_eq!(steps.last().expect("끝").address, "step:C3/S200");
    }

    // ── ④ 같은 입력이면 같은 그림 ────────────────────────────────────────

    #[test]
    fn the_same_snapshot_draws_the_same_plan() {
        let seen = reading_one();
        assert_eq!(render_monitor_graph(&seen), render_monitor_graph(&seen));
    }

    #[test]
    fn no_edge_points_at_something_that_is_not_drawn() {
        // 접힌 Cycle 을 가리키는 줄이 남으면 그 줄은 아무 데도 닿지 않은 채 뜬다.
        let mut seen = reading_one();
        seen.inactive_cycles.clear(); // C2 가 사라진다 — 되돌아감의 출처였다.
        let plan = render_monitor_graph(&seen);
        for edge in &plan.edges {
            assert!(edge.from < plan.cycles.len() && edge.to < plan.cycles.len());
            assert_ne!(edge.from, edge.to, "제 자신을 가리키는 줄이 생겼다");
        }
        assert!(
            !plan.edges.iter().any(|edge| edge.tie == Tie::Revisit),
            "출처가 없는데 되돌아감의 줄을 그렸다"
        );
    }
}
