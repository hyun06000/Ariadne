//! Monitor 가 사람에게 쓰는 **낱말** — 두 renderer 가 함께 읽는 한 자리.
//!
//! plain text 와 HTML 은 모양이 다르지만 **같은 사실을 같은 말로** 불러야 한다. 상태와
//! 관계의 문장을 renderer 마다 따로 적으면, 같은 `verdict` 가 화면에 따라 다른 뜻으로
//! 읽히기 시작하고 그때부터 두 화면은 서로 다른 진실원이 된다.
//!
//! 여기 있는 것은 **낱말뿐이다.** 어느 절에 무엇을 싣고 어떻게 배치할지는 renderer 가
//! 정한다 — 그것이 두 표현이 갈라져도 되는 자리다(Monitor Model §7.1).

use crate::cycle::CycleKind;
use crate::node::NodeStatus;

use super::{ActionKind, CycleRelation, WorldMark};

// ── 절의 이름 ──────────────────────────────────────────────────────────────

pub(super) const ACTIVE_PATH: &str = "활성 경로";
pub(super) const LEFT_BEHIND: &str = "지나온 갈래";
pub(super) const DOING: &str = "현재 행동";
pub(super) const WORLD: &str = "현재 세계";
pub(super) const NEXT: &str = "다음 행동";

/// 지금 자리의 절 이름 — **Interview 를 「현재 실험」이라 부르지 않는다.**
pub(super) fn here_title(kind: CycleKind) -> &'static str {
    match kind {
        CycleKind::Experiment => "현재 실험",
        CycleKind::Interview => "현재 인터뷰",
    }
}

// ── 이름표 ─────────────────────────────────────────────────────────────────

pub(super) const CYCLE: &str = "Cycle";
pub(super) const STEP: &str = "Step";
pub(super) const PROBLEM: &str = "질문";
pub(super) const SUCCESS_CONDITION: &str = "성공 기준";
pub(super) const VERDICT: &str = "판정";
pub(super) const LESSON: &str = "판정의 교훈";
pub(super) const HANDOFF: &str = "넘긴 것";
pub(super) const NEXT_DIRECTION: &str = "다음 방향";
pub(super) const WHY: &str = "그 까닭";
pub(super) const PARENT: &str = "부모";
pub(super) const BRANCH_SOURCE: &str = "갈래 출처";
pub(super) const RELATION: &str = "관계";
pub(super) const OBJECTIVE: &str = "목표";
pub(super) const NEXT_ACTION: &str = "지금 할 일";
pub(super) const DONE_WHEN: &str = "완료 조건";
pub(super) const BASELINE: &str = "기준";
pub(super) const WORLD_STATE: &str = "상태";
pub(super) const WHY_UNKNOWN: &str = "보지 못한 까닭";
pub(super) const REASON: &str = "까닭";
pub(super) const RUN: &str = "실행";
pub(super) const HELP: &str = "도움말";

/// 아직 아무 자리도 열지 않았다는 사실 — 다음에 무엇을 할지와 곧바로 이어진다.
pub(super) const NO_STEP_YET: &str = "아직 아무것도 열지 않았다";
/// 밟을 수 있는 GIL 명령이 하나도 없다는 사실.
pub(super) const NO_MOVE: &str = "지금 밟을 수 있는 GIL 명령이 없다.";

/// 아직 실험이 정의되지 않았다 — **없는 질문을 지어내지 않는다.**
pub(super) const NO_DEFINITION: &str = "아직 이 Cycle 의 질문이 정의되지 않았다";

/// 지금 걸린 행동이 없다.
pub(super) const NO_WILL: &str = "지금 걸린 작업 행동이 없다";

/// Cycle Report 에 적힌 **다음 방향의 낱말**을 사람의 말로.
///
/// `open_child` 나 `revisit` 은 저장된 값의 이름이지 사람의 말이 아니다. 판독 실험 1 에서
/// 사람은 바로 이 낱말을 보고 **지금 할 일로 오인했다.** 모르는 낱말은 지어내지 않고
/// 그대로 둔다 — 없는 뜻을 붙이는 것이 더 나쁘다.
pub(super) fn direction_of(action: &str) -> &str {
    match action {
        "open_child" => "이 결과를 바탕으로 다음 실험을 시작한다",
        "revisit" => "이전 질문으로 돌아가 다른 방법을 시도한다",
        "close_cycle" => "이 Cycle 을 판정으로 닫는다",
        other => other,
    }
}
/// 활성 경로가 무엇인지 한 줄로.
pub(super) const ACTIVE_PATH_IS: &str = "뿌리부터 지금까지 — 부모만 따라간 길이다.";
/// 지나온 갈래가 무엇인지 한 줄로.
pub(super) const LEFT_BEHIND_IS: &str =
    "계보 밖의 Cycle 이다 — 사라지지 않았고, 지금 걷는 길 위에 있지 않을 뿐이다.";
/// 갈래의 출처가 계보의 변이 아니라는 사실 — 두 화면 모두 이것을 말한다.
pub(super) const NOT_A_LINEAGE_EDGE: &str = "계보의 변이 아니다";
/// 지금 Cycle 과 부모가 같다는 사실.
pub(super) const SAME_PARENT: &str = "지금 Cycle 과 같은 부모 — 형제다";
/// 지금 열린 자리가 세계를 확정할 수 있다는 사실.
pub(super) const VERIFY_CAN_CONFIRM: &str = "지금 열린 자리는 Verify — 바뀐 세계를 확정할 수 있다";

// ── 상태와 관계 ────────────────────────────────────────────────────────────
//
// **색으로 가르지 않는다.** 어느 renderer 에서도 이 낱말이 화면에 그대로 있어야 하고,
// 그래서 상태를 아는 데 색이나 도형이 필요하지 않다.

pub(super) fn state_of(state: NodeStatus) -> &'static str {
    match state {
        NodeStatus::Open => "열림",
        NodeStatus::Closed => "닫힘",
    }
}

pub(super) fn world_of(state: WorldMark) -> &'static str {
    match state {
        WorldMark::Clean => "clean — 기준 세계와 같다",
        WorldMark::Dirty => "dirty — 기준 세계 이후 파일이 바뀌었다",
        WorldMark::Unknown => "unknown — 지금 폴더를 보지 못했다",
    }
}

/// 계보 밖 Cycle 이 지금 자리와 맺는 관계 — **셋을 서로 다른 말로.**
///
/// enum 이름을 그대로 내보이지 않는다. 사람이 읽는 것은 관계이지 Rust 의 variant 가 아니다.
pub(super) fn relation_of(relation: CycleRelation) -> &'static str {
    match relation {
        CycleRelation::RevisitSource => "지금 걷는 갈래가 여기서 갈라져 나왔다",
        CycleRelation::Abandoned => "같은 자리에서 갈라져 두고 온 가지다",
        // **Graph 가 끊겼다는 뜻이 아니다.** 두고 온 가지의 자손처럼, 같은 Graph 안에 있되
        // 지금 걷는 길과 곧바로 맞닿지 않는 자리다.
        CycleRelation::Other => "현재 활성 경로 밖에 있고, 그 경로와 직접 맞닿지 않는다",
    }
}

/// 그 수가 무엇을 하는가 — **variant 이름이 아니라 사람의 말로.**
pub(super) fn what_it_does(kind: ActionKind) -> String {
    match kind {
        ActionKind::CloseStep(step) => format!("열린 {step} 자리를 Report 로 닫는다"),
        ActionKind::OpenStep(step) => format!("{step} 자리를 연다"),
        ActionKind::CloseCycle(cycle) => format!("이 {cycle} Cycle 을 Cycle Report 로 닫는다"),
        ActionKind::OpenCycle(cycle) => format!("다음 {cycle} Cycle 을 연다"),
        ActionKind::OpenBranch(cycle) => format!("되돌아온 자리에 새 {cycle} 갈래를 연다"),
        ActionKind::Revisit => "적어 둔 조상으로 되돌아간다".to_string(),
        ActionKind::Restore => "작업 폴더를 기준 세계로 되돌린다".to_string(),
    }
}
