//! Monitor — **원본에서 한 번 읽은, 사람이 보는 사실 Snapshot.**
//!
//! GIL 의 또 다른 진실 공급원이 아니다. Graph·Report·Journey·Artifact reference 만이
//! 진실이고, 여기서는 그 원본을 **한 조회 구간 안에서 한 번 읽어** 소유한 불변 값으로
//! 옮긴다. 그린 뒤에 원본을 다시 읽지 않으므로, 화면 위의 두 칸이 서로 다른 시점을
//! 말하는 일이 없다.
//!
//! ```text
//! 잠금 → 복구 → 검증된 Project → 세계 한 번 관측 → 소유한 값으로 복사 → 잠금 해제
//! ```
//!
//! # 하지 않는 것
//!
//! `.gil/state.yaml` 을 직접 읽지 않는다. `gil status`·`gil story`·`gil context` 의 글을
//! 파싱하지 않고 CLI 를 자식 프로세스로 부르지도 않는다. 그 셋과 이 Snapshot 은 **같은
//! 도메인 접근자**에서 각자 읽는다 — 문자열을 거쳐 읽으면 화면이 화면을 해석하게 되고,
//! 그때부터 표현을 고치는 것이 사실을 고치는 일이 된다.
//!
//! # 없는 것을 지어내지 않는다
//!
//! Chain 도, 승인 mode 도, 시각 자료도 이 모델에 없다. `chain: null` 같은 빈 자리조차
//! 두지 않는다 — 그 자리가 공개 계약이 되면, 아직 정하지 않은 것을 이미 정한 것처럼
//! 약속하게 된다(Monitor Model §5).
//!
//! # 판정을 새로 쓰지 않는다
//!
//! 「지금 무엇을 할 수 있는가」는 실행하는 그 자리에게 묻는다
//! ([`Cycle::openable_here`]·[`Cycle::can_close`]·[`Cycles::can_revisit`]). 여기서 규칙을
//! 다시 쓰면 화면이 약속한 수를 CLI 가 거절하는 날이 온다.

mod graph;
mod html;
pub mod refresh;
pub mod watch;
mod say;
mod serve;
mod svg;
mod text;
mod detail;
pub(crate) mod view;
mod wire;

pub use html::render_monitor_html;
pub use serve::{MonitorServer, serve_monitor};
pub use text::render_monitor_text;
pub use detail::{DetailError, NodeDetailV1, ReportFieldV1, ReportV1};
pub use wire::{
    WireError, decode_detail_v1, decode_view_v1, encode_detail_v1, encode_view_v1,
};
pub use view::{
    CurrentV1, CycleKindV1, CycleReportV1, DefinitionV1, DirectionActionV1, MonitorViewV1,
    NextActionKindV1, NextActionV1, NextDirectionV1, NodeStateV1, StepKindV1, StepV1,
    TimelineCycleV1, TimelineRelationV1, VerdictV1, ViewError, WillV1, WorldStateV1, WorldV1,
    monitor_view_v1,
};

use std::time::SystemTime;

use crate::cycle::{Cycle, CycleKind};
use crate::cycles::{CycleId, Cycles};
use crate::manual::{Bundled, TopicId};
use crate::node::{NodeKind, NodeStatus};
use crate::project::Project;
use crate::refs::{CycleRef, ExistenceRef, JourneyRef, SnapshotRef, StepRef, WillRef};
use crate::report::Report;
use crate::report::field::{
    HANDOFF_SUMMARY, HYPOTHESIS, INTERPRETATION, LESSON, NEXT_ACTION, NEXT_REASON, PROBLEM,
    QUESTION, RESPONSE, RESULT, STATEMENT, SUCCESS_CONDITION, VERDICT,
};
use crate::session::{ProjectSession, SessionError, WorldState};

// ── 시각 ───────────────────────────────────────────────────────────────────

/// 화면이 **언제 읽혔는지**. Graph 의 사건 시간이 아니다.
///
/// 견주기(`PartialEq`·`Ord`)를 일부러 짓지 않는다. 이 값으로 두 Snapshot 의 선후나 같음을
/// 판정할 수 있게 두면 언젠가 그렇게 쓰이고, 그 순간 벽시계가 GIL 의 판정에 끼어든다.
/// 사실이 같은지는 **사실끼리** 견준다.
#[derive(Debug, Clone, Copy)]
pub struct CapturedAt(SystemTime);

impl CapturedAt {
    /// 표시용 시각 하나. renderer 가 제 방식으로 적는다.
    pub fn instant(self) -> SystemTime {
        self.0
    }
}

// ── Snapshot ───────────────────────────────────────────────────────────────

/// 한 번의 조회가 만든 **불변 사실 한 벌.**
///
/// `PartialEq` 를 짓지 않는다 — 관측 시각이 들어 있어 「같은 Snapshot 인가」라는 물음이
/// 「같은 사실인가」와 갈리기 때문이다. 사실이 같은지는 아래 칸들을 견준다.
#[derive(Debug, Clone)]
pub struct MonitorSnapshot {
    pub captured_at: CapturedAt,
    pub current_existence: ExistenceFacts,
    pub current_cycle: CurrentCycleFacts,
    /// 지금 Cycle 에서 **`parent` 만 따라** 뿌리까지 간 구조적 경로. 뿌리가 먼저 온다.
    ///
    /// 참조 목록이 아니라 **Cycle 해상도의 사실**이다. 이름만 늘어놓으면 직렬로 성공한
    /// Cycle 들 사이에서 무엇을 이어받아 지금 실험에 왔는지 알 수 없다 — 「왜 여기 있는가」에
    /// 답하지 못하는 화면이 된다.
    ///
    /// **안의 Step Graph 는 펼치지 않는다.** 조상마다 Step 을 늘어놓으면 이 절이 곧 전체
    /// history 가 되고, 그것은 다른 독자(`gil history`)의 몫이다.
    ///
    /// 마지막 항목은 지금 Cycle 자신이며 [`MonitorSnapshot::current_cycle`] 과 **같은
    /// 정체성**을 지닌다.
    pub active_lineage: Vec<CycleFacts>,
    pub inactive_cycles: Vec<InactiveCycle>,
    pub pending_revisit: Option<PendingRevisit>,
    pub current_step: Option<StepFacts>,
    pub current_will: Option<WillFacts>,
    pub world: WorldFacts,
    pub next_actions: Vec<NextAction>,
    /// 이 Journey 가 만든 **모든 Cycle 을 발급 순서 그대로**, 각자의 Step 과 함께.
    ///
    /// # 벡터의 순서가 곧 시간이다
    ///
    /// 구조가 주는 append-only 발급 순서를 그대로 옮긴 것이라, 읽는 쪽은 `CycleRef` 나
    /// `StepRef` 의 **번호를 비교할 일이 없다.** 번호로 시간을 짐작하면 되돌아감이 섞인
    /// Graph 에서 곧바로 틀린다.
    ///
    /// # 왜 별도의 칸인가
    ///
    /// [`CycleFacts`] 는 여전히 Step 을 지니지 않는다. Cycle 해상도의 계약은 그대로 두고,
    /// **Step DAG 를 그리기 위한 투영 하나**를 옆에 둔다. 글 화면(`gil monitor`)은 이 칸을
    /// 펼치지 않는다 — 조상마다 Step 을 늘어놓는 것은 여전히 다른 독자의 몫이다.
    ///
    /// 여기서 자르지 않는다. 접기와 축약은 그리는 쪽이 한다.
    pub timeline: Vec<TimelineCycleFacts>,
}

/// 지금 행동하는 존재와 그 판.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExistenceFacts {
    pub existence_ref: ExistenceRef,
    pub journey_ref: JourneyRef,
}

/// **Cycle 해상도의 사실 하나** — 계보의 항목과 지금 자리가 함께 쓴다.
///
/// Step Graph 를 담지 않는다. 그래서 이 타입을 계보에 늘어놓아도 과거 Cycle 의 Step 이
/// 따라오지 않고, 「Cycle 해상도」와 「Step 해상도」가 타입으로 갈린다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CycleFacts {
    pub cycle_ref: CycleRef,
    pub kind: CycleKind,
    pub state: NodeStatus,
    pub parent_cycle_ref: Option<CycleRef>,
    /// **어느 실패에서 갈라져 났는가.** 계보의 변이 아니다 — `active_lineage` 는 이것을
    /// 따라가지 않는다.
    pub revisit_from_cycle_ref: Option<CycleRef>,
    /// Experiment 이고 유일한 Define 이 닫혔을 때만. 없는 것은 정상이다.
    pub experiment_definition: Option<ExperimentDefinition>,
    /// Interview 일 때만. 이 Cycle 이 **무엇을 묻고 있는가**를 세 상태로 가른다.
    ///
    /// Experiment 의 `experiment_definition` 과 짝이다 — 한 Cycle 에 둘 중 하나만 산다.
    /// 읽는 쪽이 Step 목록을 뒤져 질문을 찾아내지 않도록 **여기서 정한다.**
    pub interview_question: Option<InterviewQuestion>,
    /// 닫힌 Cycle 의 Report 투영. 열려 있으면 없다.
    pub report: Option<CycleReportFacts>,
}

/// 지금 서 있는 Cycle — Cycle 해상도의 사실에 **그 안의 Step 목록** 하나를 더한다.
///
/// Step 목록을 이 타입만 지니는 까닭은 하나다: 계보의 항목과 같은 타입을 쓰면 과거 조상에도
/// Step 을 실을 수 있게 되고, 그러면 「펼치지 않는다」가 규율이 되어 언젠가 깨진다.
/// 여기서는 **타입이 그것을 막는다.**
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CurrentCycleFacts {
    pub facts: CycleFacts,
    pub steps: Vec<StepFacts>,
}

/// 이 실험이 무엇을 풀려 하고 무엇이면 성공인가 — **유일한 Define 에서 읽는다.**
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExperimentDefinition {
    pub problem: String,
    pub success_condition: String,
}

/// 이 Interview 가 무엇을 묻고 있는가 — **첫 Question 에서 읽는다.**
///
/// 세 상태를 가린다. 「아직 묻지 않았다」와 「묻는 중」은 다른 사실이고, 둘을 뭉치면 화면이
/// 존재하는 질문을 없다고 말하게 된다. 그것이 이 타입이 생긴 까닭이다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum InterviewQuestion {
    /// Question Step 을 아직 열지 않았다.
    NotAsked,
    /// Question 이 열려 있고 아직 Report 가 없다 — 질문 글은 닫을 때 적힌다.
    Asking,
    /// 닫힌 Question 이 있다. `response` 는 그 Report 가 지닌 답이다.
    Asked {
        question: String,
        response: Option<String>,
    },
}

/// 닫힌 Cycle 의 요약 — Cycle Report 의 **선택적 투영**(Monitor Model §4.5).
///
/// 안의 Step Graph 를 복제하지 않는다. `verdict` 와 `handoff_summary` 가 `Option` 이
/// 아닌 까닭은 하나다: 그 둘은 Cycle 을 닫는 조건이라, Report 가 있으면 언제나 있다.
/// 둘을 각자 `Option` 으로 두면 실제로는 갈릴 수 없는 상태를 표현할 수 있게 된다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CycleReportFacts {
    pub verdict: String,
    pub handoff_summary: String,
    /// 판정의 교훈 — `outcome_ref` 가 가리킨 Outcome 에서 읽는다.
    pub outcome_lesson: Option<String>,
    pub next_direction: Option<NextDirection>,
}

/// 그 Cycle 이 적어 둔 다음 방향.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NextDirection {
    pub action: String,
    pub reason: Option<String>,
    /// 되돌아가겠다고 적었을 때의 대상. **닫을 때 검증된 그 값을 다시 읽는다.**
    pub target_cycle_ref: Option<CycleRef>,
}

/// Cycle 안의 Step 하나.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StepFacts {
    pub step_ref: StepRef,
    pub kind: NodeKind,
    pub state: NodeStatus,
    /// 이 Step 을 한 줄로 대표하는 **Report 원문 그대로.**
    ///
    /// 지어낸 요약도, renderer 가 해석한 말도 아니다 — [`summary_field`] 가 정한 칸 하나를
    /// 그대로 옮긴다. 아직 닫히지 않았거나 그 칸이 없으면 `None` 이다.
    ///
    /// **여기서 자르지 않는다.** 화면에 맞춘 길이 제한과 줄임표는 그리는 쪽의 몫이고,
    /// escape 는 마지막 출력 경계에서 한다. read model 이 미리 자르면 상세 영역에서
    /// 원문을 되찾을 길이 사라진다.
    pub summary: Option<String>,
}

/// 시간선 위의 Cycle 하나가 지금 걷는 갈래와 맺은 관계.
///
/// **넷은 서로 배타적이다.** boolean 두 개를 늘어놓으면 `활성이면서 버려진` 같은 있을 수
/// 없는 상태가 타입으로 표현 가능해지고, 그러면 읽는 쪽마다 그것을 어떻게 다룰지 다시
/// 정해야 한다. 하나의 enum 이면 그 물음 자체가 없다.
///
/// 판정하는 자리는 [`timeline_relation`] 하나뿐이고, 그마저 아래 셋은
/// [`relation`] 에 그대로 물어본다 — [`InactiveCycle::relation_to_current`] 와 **같은
/// 함수**라 한쪽만 낡을 수 없다.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TimelineRelation {
    /// 지금까지 걸어온 길 위에 있다(현재 Cycle 자신을 포함한다).
    ActivePath,
    /// 지금 걷는 갈래가 **이 Cycle 에서 갈라져 나왔다.**
    RevisitSource,
    /// 부모는 계보 위인데 저는 아니다 — 같은 자리에서 갈라져 두고 온 가지다.
    Abandoned,
    /// 그 밖. 두고 온 가지의 자손처럼 계보에서 더 멀리 떨어진 것들이다.
    Other,
}

/// 시간선 위의 Cycle 하나 — **Cycle 해상도의 사실과 그 안의 Step 전부.**
///
/// `kind`·`state`·`parent`·`revisit_from`·`definition`·`report` 를 여기 다시 적지 않는다.
/// [`CycleFacts`] 를 그대로 안는다 — 같은 사실을 두 타입에 적으면 한쪽이 낡는다.
///
/// **현재 Cycle 인지는 여기 없다.** [`MonitorSnapshot::current_cycle`] 의 참조와 견주어
/// 알아낸다 — 「지금 어디인가」를 말하는 자리는 하나뿐이어야 하기 때문이다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TimelineCycleFacts {
    pub facts: CycleFacts,
    pub relation_to_current: TimelineRelation,
    /// 만든 순서 그대로.
    pub steps: Vec<StepFacts>,
}

/// 이 Step kind 를 한 줄로 대표하는 Report 칸.
///
/// **대응표가 사는 자리는 여기 하나다.** 문법(`gil-spec.yaml`)은 어떤 칸이 *필요한지*는
/// 말하지만 어떤 칸이 그 Step 을 *대표하는지*는 말하지 않는다 — `close_requires` 의 첫
/// 칸도 아니다(verify 는 `execution` 이 먼저지만 사람이 읽고 싶은 것은 `result` 다).
/// 그러니 이 판단은 Monitor 의 것이고, 두 자리에 적으면 한쪽이 낡는다.
///
/// 경계 표식(Entry·Exit)에는 Report 가 없다.
fn summary_field(kind: NodeKind) -> Option<&'static str> {
    match kind {
        NodeKind::Question => Some(QUESTION),
        NodeKind::Interpretation => Some(INTERPRETATION),
        NodeKind::Synthesis => Some(STATEMENT),
        NodeKind::Define => Some(PROBLEM),
        NodeKind::Hypothesis => Some(HYPOTHESIS),
        NodeKind::Verify => Some(RESULT),
        NodeKind::Analysis => Some(INTERPRETATION),
        NodeKind::Outcome => Some(LESSON),
        NodeKind::CycleEntry | NodeKind::CycleExit => None,
    }
}

/// Step Node 하나를 사실로 — **Cycle 안이든 시간선 위든 같은 함수가 짓는다.**
fn step_facts(cycle: &Cycle, node: &crate::walk::StepNode) -> StepFacts {
    StepFacts {
        step_ref: cycle.step_ref(node.id),
        kind: node.kind,
        state: node.status,
        summary: summary_field(node.kind)
            .and_then(|field| node.report.as_ref()?.get(field))
            .map(str::to_string),
    }
}

/// 지금 계보 위에 있지 않은 Cycle.
///
/// **모두를 「실패한 형제」라고 부르지 않는다.** 실패인지는 Report 의 `verdict` 에서만 읽고,
/// 형제인지는 `parent_cycle_ref` 가 같은지로만 유도한다. 이 값 자체는 그 둘 중 어느 것도
/// 주장하지 않는다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InactiveCycle {
    pub cycle_ref: CycleRef,
    pub kind: CycleKind,
    pub state: NodeStatus,
    pub parent_cycle_ref: Option<CycleRef>,
    pub revisit_from_cycle_ref: Option<CycleRef>,
    /// Report 가 있을 때만. `verdict` 와 `handoff` 는 이 안에 있다.
    pub report: Option<CycleReportFacts>,
    pub relation_to_current: CycleRelation,
}

/// 계보 밖 Cycle 이 지금 자리와 맺는 **구조적** 관계.
///
/// 이름이 판정을 담지 않는다 — 어느 것도 「실패했다」고 말하지 않는다.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CycleRelation {
    /// 지금 걷는 갈래가 **이 Cycle 에서 갈라져 나왔다** — 계보 위의 어떤 Cycle 이 이것을
    /// 제 `revisit_from` 으로 지녔거나, 아직 소비되지 않은 되돌아감의 출처다.
    RevisitSource,
    /// 부모는 계보 위에 있는데 저는 아니다 — 같은 자리에서 갈라져 두고 온 가지다.
    Abandoned,
    /// 그 밖. 두고 온 가지의 자손처럼 계보에서 더 멀리 떨어진 것들이다.
    Other,
}

/// 되돌아왔고 **아직 새 Cycle 을 열지 않은** 상태.
///
/// 이 값이 있다는 것은 새 Cycle 이 아직 없다는 뜻이다. `current_cycle` 은 여전히 되돌아간
/// 대상이며, 그것을 새 Cycle 이 열린 것처럼 표현하지 않는다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PendingRevisit {
    pub from_cycle_ref: CycleRef,
    pub target_cycle_ref: CycleRef,
}

/// 지금 수행하려는 행동 한 단위.
///
/// **없으면 없다.** 열린 Step 에서 추측해 지어내지 않는다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WillFacts {
    pub will_ref: WillRef,
    pub objective: String,
    pub next_action: String,
    pub done_when: String,
    pub target_step_ref: StepRef,
    pub existence_ref: ExistenceRef,
    pub journey_ref: JourneyRef,
}

/// 지금 Artifact 세계.
///
/// 파일 목록도, 내부 digest 도, manifest·blob 주소도 없다. 공개 표면은 `snapshot:A*` 하나다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WorldFacts {
    pub baseline_snapshot_ref: SnapshotRef,
    pub state: WorldMark,
    /// `Unknown` 일 때 왜 못 봤는지. 그 밖에는 없다.
    pub reason: Option<String>,
    /// 지금 열린 자리가 Verify 인가 — 세계를 확정할 권한이 있는 자리인가.
    pub verify_can_confirm: bool,
}

/// 작업 폴더가 기준 세계와 어떤 관계인가.
///
/// **못 본 것은 dirty 가 아니다.** 관측이 실패한 것을 「바뀌었다」로 옮기면, 사람은 바꾼
/// 적 없는 것을 되돌리려 한다.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WorldMark {
    Clean,
    Dirty,
    Unknown,
}

/// 지금 실제로 밟을 수 있는 수 하나.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NextAction {
    pub kind: ActionKind,
    /// 지금 CLI 에 그 명령이 **실제로 있을 때만.**
    pub command: Option<String>,
    pub reason: String,
    /// 이 수를 설명하는 함께 실린 Topic 이 있을 때만.
    pub help_ref: Option<TopicId>,
}

/// **아직 없는 전이를 담지 않는다** — Chain close·임의 checkout·merge·승인은 여기 없다.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ActionKind {
    /// 열려 있는 Step 을 Report 로 닫는다.
    CloseStep(NodeKind),
    /// 이 Cycle 안에서 다음 Step 을 연다.
    OpenStep(NodeKind),
    /// Step Graph 가 끝 경계에 닿았다 — Cycle Report 로 닫는다.
    CloseCycle(CycleKind),
    /// 닫힌 Cycle 이 적어 둔 대로 다음 Cycle 을 연다.
    OpenCycle(CycleKind),
    /// 되돌아온 자리에서 새 갈래를 연다.
    OpenBranch(CycleKind),
    /// 적어 둔 조상으로 되돌아간다.
    Revisit,
    /// 작업 폴더를 기준 세계로 되돌린다.
    Restore,
}

/// Snapshot 을 지을 수 없는 이유.
///
/// **여기 있는 것은 전부 「걸어서 만들 수 없는 상태」다.** 검증된 복원 경로를 지난 Project
/// 에서는 일어나지 않지만, 일어난다면 그것은 손상이고 손상은 조용히 그럴듯한 값으로
/// 덮이면 안 된다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MonitorError {
    /// 되돌아온 상태인데 그 결정이 출처에 적혀 있지 않다.
    ///
    /// 복원은 「적힌 대상 == 지금 자리」를 검사하므로(`Cycles::check_pending`) 되살아난
    /// 판에서는 일어나지 않는다. 그래도 **지금 Cycle 을 대신 넣지 않는다** — 그러면 읽지
    /// 못한 사실이 읽은 사실처럼 보이고, 화면은 그 둘을 구별할 방법이 없다.
    PendingTargetMissing { from: CycleRef },
}

impl std::fmt::Display for MonitorError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            MonitorError::PendingTargetMissing { from } => write!(
                f,
                "{from} 에서 되돌아왔다는데 {from} 이(가) 되돌아갈 곳을 적어 두지 않았다 — \
                 밟지 않은 되돌아감이다"
            ),
        }
    }
}

impl std::error::Error for MonitorError {}

// ── 한 번의 조회 ───────────────────────────────────────────────────────────

impl ProjectSession {
    /// **원본에서 한 번 읽어 Snapshot 하나를 만든다.**
    ///
    /// 잠금·복구·검증된 load 는 [`ProjectSession::open`] 이 이미 했다(Monitor Model §6 의
    /// 1~3). 여기서 하는 것은 4~5 다 — 세계를 **한 번** 관측하고, 모든 사실을 소유한 값으로
    /// 옮긴다. 잠금은 이 세션이 떨어질 때 풀리므로 화면이 열려 있는 동안 쥐고 있지 않는다.
    ///
    /// **의미론적으로 아무것도 쓰지 않는다.** Node·Cycle·Will·Journey·Report 를 만들거나
    /// 고치지 않고, Snapshot 을 발급하지 않고, 복원하지 않고, `state.yaml` 을 저장하지 않고,
    /// 작업 파일을 건드리지 않는다. 프로젝트를 여는 순간 이미 있던 중단 transaction 을
    /// 되돌리는 것은 Storage Model 의 원자성 복구이지 Monitor 의 쓰기가 아니다(§6).
    pub fn monitor(&self) -> Result<MonitorSnapshot, SessionError> {
        // **세계는 여기 한 번뿐이다.** 아래 어느 자리도 폴더를 다시 보지 않는다.
        let world = self.world_state()?;
        let verify_can_confirm = self.can_confirm_artifact();
        snapshot(self.project(), world, verify_can_confirm).map_err(SessionError::Monitor)
    }
}

/// 검증된 Project 하나와 이미 관측된 세계로 Snapshot 을 짓는다 — **읽기만 한다.**
///
/// 세계를 인자로 받는 까닭은 하나다: 관측은 파일을 보는 일이고 이 함수는 파일을 볼 수 없다.
/// 그래서 「한 Snapshot 에 관측 한 번」이 **부르는 쪽의 규율이 아니라 이 함수의 모양**이 된다.
fn snapshot(
    project: &Project,
    world: WorldState,
    verify_can_confirm: bool,
) -> Result<MonitorSnapshot, MonitorError> {
    let cycles = project.cycles();
    let here = cycles.current();

    // 계보는 `parent` 만 따라간다. 그 판정은 [`Cycles::lineage`] 하나에 있고, 여기서
    // 다시 세지 않는다 — 두 자리에 적으면 언젠가 한쪽이 `revisit_from` 을 타게 된다.
    let lineage = cycles
        .lineage(cycles.current_id())
        .expect("current 는 언제나 실재하는 Cycle 을 가리킨다");
    // **한 투영 함수를 계보와 지금 자리가 함께 쓴다.** 두 벌로 두면 같은 Cycle 이 두 절에서
    // 다른 판정을 말하는 날이 온다.
    let active_lineage: Vec<CycleFacts> = lineage
        .iter()
        .map(|cycle| cycle_facts(cycles, cycle))
        .collect();
    let on_lineage: Vec<CycleId> = lineage.iter().map(|cycle| cycle.id()).collect();

    // 대상은 그 실패 Cycle 이 **적어 둔 것**이다. 지금 자리로도, ID 순서로도, 폴더의
    // 내용으로도 추측하지 않는다 — 읽지 못하면 그 사실이 없는 것이고, 없는 것을 있는 척
    // 채우면 화면은 진짜와 지어낸 것을 구별할 수 없다.
    let pending = match cycles.pending_revisit() {
        None => None,
        Some(from) => Some(PendingRevisit {
            from_cycle_ref: from.to_ref(),
            target_cycle_ref: declared_target(cycles, from).ok_or(
                MonitorError::PendingTargetMissing {
                    from: from.to_ref(),
                },
            )?,
        }),
    };

    let inactive_cycles = cycles
        .nodes()
        .iter()
        .filter(|cycle| !on_lineage.contains(&cycle.id()))
        .map(|cycle| InactiveCycle {
            cycle_ref: cycle.id().to_ref(),
            kind: cycle.kind(),
            state: cycle.status(),
            parent_cycle_ref: cycle.parent().map(CycleId::to_ref),
            revisit_from_cycle_ref: cycle.revisit_from().map(CycleId::to_ref),
            report: report_facts(cycles, cycle),
            relation_to_current: relation(cycles, cycle.id(), &on_lineage),
        })
        .collect();

    let steps: Vec<StepFacts> = here
        .steps()
        .nodes()
        .iter()
        .map(|node| step_facts(here, node))
        .collect();

    // **발급 순서 그대로.** `Cycles::nodes()` 도 `Walk::nodes()` 도 「만든 순서대로」를
    // 계약으로 적어 둔 접근자다. 여기서 다시 정렬하지 않는다 — 정렬하는 순간 그 기준이
    // 새 진실 판정이 된다.
    let timeline: Vec<TimelineCycleFacts> = cycles
        .nodes()
        .iter()
        .map(|cycle| TimelineCycleFacts {
            facts: cycle_facts(cycles, cycle),
            relation_to_current: timeline_relation(cycles, cycle.id(), &on_lineage),
            steps: cycle
                .steps()
                .nodes()
                .iter()
                .map(|node| step_facts(cycle, node))
                .collect(),
        })
        .collect();
    // 서 있는 자리 — 닫혀 있어도 그 자리에 서 있다. 아직 아무것도 열지 않았으면 없다.
    let current_step = here
        .steps()
        .current()
        .and_then(|id| steps.iter().find(|step| step.step_ref == here.step_ref(id)))
        .cloned();

    let existence = project.current_existence();

    Ok(MonitorSnapshot {
        captured_at: CapturedAt(SystemTime::now()),
        current_existence: ExistenceFacts {
            existence_ref: existence.id(),
            journey_ref: existence.current_journey(),
        },
        // 계보의 마지막 항목과 **같은 정체성**이다 — 같은 함수가 지었다.
        current_cycle: CurrentCycleFacts {
            facts: cycle_facts(cycles, here),
            steps,
        },
        active_lineage,
        inactive_cycles,
        timeline,
        pending_revisit: pending,
        current_step,
        // **없으면 없다.** 열린 Step 이 있다고 Will 을 지어내지 않는다.
        current_will: project.active_will().map(|will| WillFacts {
            will_ref: will.id(),
            objective: will.objective().to_string(),
            next_action: will.next_action().to_string(),
            done_when: will.done_when().to_string(),
            target_step_ref: will.target(),
            existence_ref: will.existence(),
            journey_ref: existence.current_journey(),
        }),
        world: world_facts(&world, verify_can_confirm),
        next_actions: next_actions(project, mark(&world)),
    })
}

/// Cycle 하나를 **Cycle 해상도**로 옮긴다 — 계보의 항목과 지금 자리가 같은 문을 쓴다.
///
/// **Step Graph 를 보지 않는다.** 그것을 담을 자리가 반환 타입에 없으므로, 조상에 Step 을
/// 싣는 일은 여기서 일어날 수 없다.
fn cycle_facts(cycles: &Cycles, cycle: &Cycle) -> CycleFacts {
    CycleFacts {
        cycle_ref: cycle.id().to_ref(),
        kind: cycle.kind(),
        state: cycle.status(),
        parent_cycle_ref: cycle.parent().map(CycleId::to_ref),
        revisit_from_cycle_ref: cycle.revisit_from().map(CycleId::to_ref),
        experiment_definition: definition(cycle),
        interview_question: interview_question(cycle),
        report: report_facts(cycles, cycle),
    }
}

/// 그 실패 Cycle 이 **적어 둔** 되돌아갈 곳.
///
/// 닫을 때 검증한 그 한 경로를 그대로 쓴다([`Cycles::check_next_direction`]). 되살아난
/// 파일은 이미 같은 검사를 지났으므로 여기서 실패하지 않는다 — 그래도 `ok()` 로 받는 것은,
/// 못 읽은 것을 **지어내지 않기** 위해서다.
fn declared_target(cycles: &Cycles, from: CycleId) -> Option<CycleRef> {
    cycles
        .node(from)?
        .report()
        .and_then(|report| cycles.check_next_direction(from, report).ok())
        .flatten()
        .map(CycleId::to_ref)
}

/// 계보 밖 Cycle 이 지금 자리와 맺는 관계 — **구조로만 가른다.**
///
/// verdict 를 보지 않는다. 실패했는지는 Report 가 말할 몫이고, 이 값은 「지금 걷는 갈래와
/// 어떻게 이어져 있는가」만 말한다.
/// 시간선 위의 한 Cycle 이 맺은 관계 — **우선순위가 여기 하나에 적혀 있다.**
///
/// ```text
/// ① 계보 위인가            → ActivePath      (현재 Cycle 자신도 여기 든다)
/// ② 그 밖이면 relation() 에게 그대로 묻는다
///      RevisitSource  지금 갈래가 여기서 갈라져 나왔다
///      Abandoned      부모는 계보 위인데 저는 아니다
///      Other          그 밖
/// ```
///
/// ①이 먼저인 까닭은 계보 위의 Cycle 도 제 조상의 revisit 출처일 수 있기 때문이다. 그때
/// 「지금 걷는 길 위에 있다」가 더 중요한 사실이다 — 화면이 그것을 옆 갈래로 밀어내면
/// 활성 경로가 끊겨 보인다.
///
/// **아래 셋은 다시 판정하지 않는다.** [`relation`] 이 그 하나뿐인 자리이고, 그래서
/// [`InactiveCycle::relation_to_current`] 와 이 값이 갈릴 수 없다.
fn timeline_relation(cycles: &Cycles, id: CycleId, on_lineage: &[CycleId]) -> TimelineRelation {
    if on_lineage.contains(&id) {
        return TimelineRelation::ActivePath;
    }
    match relation(cycles, id, on_lineage) {
        CycleRelation::RevisitSource => TimelineRelation::RevisitSource,
        CycleRelation::Abandoned => TimelineRelation::Abandoned,
        CycleRelation::Other => TimelineRelation::Other,
    }
}

fn relation(cycles: &Cycles, id: CycleId, on_lineage: &[CycleId]) -> CycleRelation {
    // ① 지금 걷는 갈래가 이 Cycle 에서 갈라져 나왔는가 — **가장 구체적인 사실이 먼저다.**
    let source_of_branch = on_lineage
        .iter()
        .filter_map(|at| cycles.node(*at))
        .any(|cycle| cycle.revisit_from() == Some(id));
    if source_of_branch || cycles.pending_revisit() == Some(id) {
        return CycleRelation::RevisitSource;
    }
    // ② 부모는 계보 위인데 저는 아니다 — 같은 자리에서 갈라져 두고 온 가지다.
    match cycles
        .node(id)
        .and_then(Cycle::parent)
        .is_some_and(|parent| on_lineage.contains(&parent))
    {
        true => CycleRelation::Abandoned,
        false => CycleRelation::Other,
    }
}

/// Experiment 의 유일한 Define 에서 목적과 성공 기준을 읽는다.
///
/// Interview 이거나 아직 Define 이 없으면 **빈 실험을 지어내지 않는다.**
fn definition(cycle: &Cycle) -> Option<ExperimentDefinition> {
    let define = cycle.define()?;
    Some(ExperimentDefinition {
        problem: define.get(PROBLEM)?.to_string(),
        success_condition: define.get(SUCCESS_CONDITION)?.to_string(),
    })
}

/// Interview 의 **출발 질문**을 세 상태로 읽는다. Experiment 이면 없다.
///
/// Experiment 의 규칙을 Interview 에 적용하지 않는다 — Define 이 없다는 사실은 Interview 에
/// 대해 아무것도 말해 주지 않는다.
fn interview_question(cycle: &Cycle) -> Option<InterviewQuestion> {
    if cycle.kind() != CycleKind::Interview {
        return None;
    }
    let Some(node) = cycle.opening_question() else {
        return Some(InterviewQuestion::NotAsked);
    };
    let Some(report) = node.report.as_ref() else {
        // 열려 있다 — 질문 글은 닫을 때 적히므로 아직 없다. 지어내지 않는다.
        return Some(InterviewQuestion::Asking);
    };
    match report.get(QUESTION) {
        Some(question) => Some(InterviewQuestion::Asked {
            question: question.to_string(),
            response: report.get(RESPONSE).map(str::to_string),
        }),
        // 닫혔는데 질문 칸이 없다 — 문법이 막는 자리다. 빈 글을 지어내느니 묻는 중으로 둔다.
        None => Some(InterviewQuestion::Asking),
    }
}

/// 닫힌 Cycle 의 Report 투영. 열려 있으면 없다.
fn report_facts(cycles: &Cycles, cycle: &Cycle) -> Option<CycleReportFacts> {
    let report = cycle.report()?;
    // **둘은 닫힘의 조건이다.** 문법의 `close_requires` 가 요구하고, 닫을 때와 저장에서
    // 되살릴 때 **같은 검사**(`RuleSet::validate_cycle_close`)가 둘을 잰다. 그러니 닫힌
    // Cycle 에 이 칸이 없는 판은 Monitor 에 닿기 전에 이미 거절된다.
    //
    // 빈 글로 낮추지 않는다 — 그러면 「적지 않았다」가 「빈칸을 적었다」로 둔갑해, 화면이
    // 손상을 정상으로 보여 준다.
    Some(CycleReportFacts {
        verdict: report
            .get(VERDICT)
            .expect("닫힌 Cycle 의 Report 는 verdict 를 지닌다 — 문법이 요구하고 복원이 다시 잰다")
            .to_string(),
        handoff_summary: report
            .get(HANDOFF_SUMMARY)
            .expect("닫힌 Cycle 의 Report 는 handoff_summary 를 지닌다 — 같은 검사가 잰다")
            .to_string(),
        outcome_lesson: cycle.judged_lesson().map(str::to_string),
        next_direction: next_direction(cycles, cycle, report),
    })
}

fn next_direction(cycles: &Cycles, cycle: &Cycle, report: &Report) -> Option<NextDirection> {
    Some(NextDirection {
        action: report.get(NEXT_ACTION)?.to_string(),
        reason: report.get(NEXT_REASON).map(str::to_string),
        target_cycle_ref: declared_target(cycles, cycle.id()),
    })
}

/// 관측한 세계를 표지 하나로 — **못 본 것은 dirty 가 아니다.**
fn mark(world: &WorldState) -> WorldMark {
    match world {
        WorldState::Clean { .. } => WorldMark::Clean,
        WorldState::Dirty { .. } => WorldMark::Dirty,
        WorldState::Unknown { .. } => WorldMark::Unknown,
    }
}

fn world_facts(world: &WorldState, verify_can_confirm: bool) -> WorldFacts {
    WorldFacts {
        baseline_snapshot_ref: world.world(),
        state: mark(world),
        // 왜 못 봤는지는 못 봤을 때만 있다.
        reason: match world {
            WorldState::Unknown { said, .. } => Some(said.clone()),
            _ => None,
        },
        verify_can_confirm,
    }
}

// ── 지금 밟을 수 있는 수 ───────────────────────────────────────────────────

/// 함께 실린 Topic 중 **그 수 자체를 설명하는** 것.
///
/// 주소는 여기 적지 않는다 — 정본은 [`Bundled`] 하나이고, Refusal Router 도 같은 것을
/// 쓴다. 두 파일에 같은 글자를 적으면 Topic 을 옮긴 날 한쪽만 고쳐진다.
///
/// 판정 함수를 Router 와 나눠 두는 까닭은 **묻는 것이 다르기** 때문이다 — Router 는
/// 「거절당했다, 무엇을 읽어야 하는가」이고 여기는 「밟을 수 있다, 어떻게 하는가」다.
fn topic_for(kind: ActionKind) -> Option<TopicId> {
    let topic = match kind {
        // 세계를 확정하는 자리는 그 자리만의 규칙이 있다.
        ActionKind::CloseStep(NodeKind::Verify) => Bundled::VerifyClose,
        ActionKind::CloseStep(_) => return None,
        // 실행형 자리를 여는 것은 행동 계약을 적는 일이다.
        ActionKind::OpenStep(_) => Bundled::OpenContract,
        // **Interview 에는 붙이지 않는다.** 두 Cycle 은 요구하는 칸도 허용값도 다르므로,
        // 한 Topic 으로 뭉뚱그리면 읽는 쪽이 남의 규칙을 배운다(Router 와 같은 규율).
        ActionKind::CloseCycle(CycleKind::Experiment) => Bundled::ExperimentClose,
        ActionKind::CloseCycle(CycleKind::Interview) => return None,
        ActionKind::OpenCycle(_) => return None,
        ActionKind::Revisit | ActionKind::OpenBranch(_) => Bundled::CycleRevisit,
        ActionKind::Restore => Bundled::Restore,
    };
    Some(topic.id())
}

fn action(kind: ActionKind, command: String, reason: &str) -> NextAction {
    NextAction {
        kind,
        command: Some(command),
        reason: reason.to_string(),
        help_ref: topic_for(kind),
    }
}

/// **이 수가 지금 성공하는가 — 세계가 거는 문 하나.**
///
/// `next_actions` 는 「구조적으로 가능한 전이」가 아니라 **「지금 실행하면 성공하는 명령」**
/// 이다. 둘을 섞으면 화면이 권한 수를 CLI 가 거절하고, 사람은 안내를 믿은 대가로 한 번
/// 실패한 뒤에야 옳은 수를 안다.
///
/// 여기 적힌 것은 전부 [`ProjectSession`] 의 실제 gate 를 옮긴 것이다.
///
/// ```text
/// 여는 것            세계를 보지 않는다 — 언제나 지난다
/// Verify close       세계를 확정하는 자리다. dirty 여도 지나고, 못 본 세계만 막는다
/// 그 밖의 close      require_clean — clean 일 때만
/// revisit            RevisitNeedsCleanWorld — clean 일 때만
/// restore            되돌릴 것이 있을 때만. 못 본 세계는 preflight 관측에서 막힌다
/// ```
fn world_allows(kind: ActionKind, world: WorldMark) -> bool {
    match kind {
        ActionKind::OpenStep(_) | ActionKind::OpenCycle(_) | ActionKind::OpenBranch(_) => true,
        ActionKind::CloseStep(NodeKind::Verify) => world != WorldMark::Unknown,
        ActionKind::CloseStep(_) | ActionKind::CloseCycle(_) | ActionKind::Revisit => {
            world == WorldMark::Clean
        }
        ActionKind::Restore => world == WorldMark::Dirty,
    }
}

/// **판정을 새로 쓰지 않는다.** 구조는 실행하는 그 자리에게 묻고, 세계는 위 문 하나가 건다.
///
/// `openable_here`·`can_close`·`can_revisit`·`pending_revisit`·`why_not_open_child` 는
/// CLI 가 쓰는 바로 그 함수들이다.
///
/// 밟을 수 있는 수가 없으면 **빈 목록**이다. 「할 수 있는 것이 없다」는 가짜 행동을 만들어
/// 채우지 않는다.
fn next_actions(project: &Project, world: WorldMark) -> Vec<NextAction> {
    let mut out = possible_here(project);
    // 되돌리는 것은 자리를 가리지 않는다 — 바뀐 세계가 있으면 어디서든 지난다.
    out.push(action(
        ActionKind::Restore,
        "gil restore".to_string(),
        "지금 폴더가 기준 세계와 다르다 — 기준 세계로 되돌린다",
    ));
    out.retain(|next| world_allows(next.kind, world));
    out
}

/// 이 자리에서 **구조적으로** 가능한 수들. 세계는 아직 보지 않는다.
fn possible_here(project: &Project) -> Vec<NextAction> {
    let cycles = project.cycles();
    let here = cycles.current();
    let mut out = Vec::new();

    // 되돌아온 자리 — 여기서 할 일은 갈래를 여는 것 하나뿐이다.
    if cycles.pending_revisit().is_some() {
        for kind in CycleKind::ALL {
            out.push(action(
                ActionKind::OpenBranch(kind),
                format!("gil open {}", kind.as_str()),
                "되돌아온 자리 아래에 새 갈래를 연다",
            ));
        }
        return out;
    }

    if here.is_closed() {
        if cycles.can_revisit() {
            out.push(action(
                ActionKind::Revisit,
                "gil revisit".to_string(),
                "이 Cycle 이 적어 둔 조상으로 되돌아가고 그 세계를 복원한다",
            ));
        }
        if cycles.why_not_open_child().is_none() {
            for kind in CycleKind::ALL {
                out.push(action(
                    ActionKind::OpenCycle(kind),
                    format!("gil open {}", kind.as_str()),
                    "이 Cycle 을 부모로 다음 Cycle 을 연다",
                ));
            }
        }
        return out;
    }

    // 열려 있는 자리가 있으면 그것을 먼저 닫는다.
    if let Some(at) = here.step_now_open() {
        let kind = here.steps().node(at).expect("방금 자리를 받아 왔다").kind;
        out.push(action(
            ActionKind::CloseStep(kind),
            "gil close".to_string(),
            "열려 있는 이 자리를 Report 로 닫는다",
        ));
        return out;
    }

    for kind in here.openable_here() {
        out.push(action(
            ActionKind::OpenStep(kind),
            format!("gil open {}", kind.as_str()),
            "이 Cycle 안에서 다음 걸음을 연다",
        ));
    }
    if here.can_close() {
        out.push(action(
            ActionKind::CloseCycle(here.kind()),
            "gil close".to_string(),
            "안의 판정이 끝났다 — Cycle Report 로 이 Cycle 을 닫는다",
        ));
    }
    out
}

// ── 시험 ───────────────────────────────────────────────────────────────────
//
// 「한 Snapshot 에 관측 한 번」은 결과만 봐서는 잴 수 없다 — 두 번 훑어도 답이 같기
// 때문이다. 그래서 횟수를 센다. 그 계수기는 crate 안에서만 컴파일되므로 이 시험은
// 통합 시험이 아니라 여기 산다.

#[cfg(test)]
mod tests {
    use super::*;
    use crate::rules::RuleSet;

    fn scratch(label: &str) -> std::path::PathBuf {
        let root = std::env::temp_dir().join(format!("gil-monitor-unit-{label}"));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).expect("시험이 쓸 자리를 만든다");
        std::fs::write(root.join("a.txt"), "가").expect("세계를 하나 둔다");
        root
    }

    fn session(label: &str) -> ProjectSession {
        let root = scratch(label);
        let session = ProjectSession::start(
            RuleSet::builtin().expect("함께 실린 명세"),
            root.join(crate::STATE_PATH),
        )
        .expect("시작한다");
        session.commit().expect("눕힌다");
        session
    }

    #[test]
    fn one_snapshot_observes_the_project_exactly_once() {
        // 관측기는 한 번의 `world_state()` 마다 **두 번** 훑는다(안정된 관측). 그러니
        // 여기서 재는 것은 「그 두 번이 정확히 한 벌」이라는 사실이다 — Snapshot 을 짓는
        // 어느 칸도 폴더를 다시 보지 않는다.
        let session = session("observe-once");
        let before = crate::artifact::scan_count::now();

        let seen = session.monitor().expect("Snapshot 을 만든다");

        assert_eq!(
            crate::artifact::scan_count::now() - before,
            2,
            "한 Snapshot 을 짓는 동안 프로젝트를 한 벌 넘게 훑었다"
        );
        // 그리고 그 한 번의 관측이 실제로 실렸다.
        assert_eq!(seen.world.state, WorldMark::Clean);
    }

    #[test]
    fn the_timeline_costs_no_extra_look() {
        // 전체 Step 시간선은 `Cycles` 와 `Walk` 만 읽는다 — 폴더를 다시 보지 않는다.
        let session = session("timeline-observe-once");
        let before = crate::artifact::scan_count::now();

        let seen = session.monitor().expect("Snapshot 을 만든다");

        assert_eq!(
            crate::artifact::scan_count::now() - before,
            2,
            "시간선을 짓느라 프로젝트를 한 벌 넘게 훑었다"
        );
        assert!(!seen.timeline.is_empty(), "시간선이 비었다");
    }

    #[test]
    fn projecting_the_view_costs_no_look_no_write_and_no_lock() {
        // 투영은 **인수 안의 것만** 읽는다. 파일도, Project 도, 시계도 다시 보지 않는다.
        let session = session("view-costs-nothing");
        let root = session.state_path().parent().expect("루트").to_path_buf();
        let state = std::fs::read(session.state_path()).expect("상태를 읽는다");
        let world = std::fs::read(root.parent().expect("작업 폴더").join("a.txt")).ok();

        let seen = session.monitor().expect("Snapshot 을 만든다");
        let before = crate::artifact::scan_count::now();

        let view = crate::monitor_view_v1(&seen).expect("View 를 짓는다");

        assert_eq!(
            crate::artifact::scan_count::now() - before,
            0,
            "투영이 세계를 훑었다"
        );
        assert!(!view.timeline.is_empty(), "View 가 비었다");
        // 아무것도 쓰지 않았다.
        assert_eq!(state, std::fs::read(session.state_path()).expect("다시 읽는다"));
        assert_eq!(
            world,
            std::fs::read(root.parent().expect("작업 폴더").join("a.txt")).ok()
        );
        // 그리고 같은 Snapshot 을 두 번 투영해도 시각이 흔들리지 않는다 — 시계를 읽지
        // 않는다는 증거다.
        assert_eq!(
            view.captured_at_unix_ms,
            crate::monitor_view_v1(&seen).expect("두 번째").captured_at_unix_ms
        );
    }

    #[test]
    fn two_snapshots_observe_twice_and_never_share_one() {
        // 갱신은 이전 Snapshot 을 고치지 않고 **새로 짓는다.** 그러므로 관측도 새로 한다.
        let session = session("observe-twice");
        let before = crate::artifact::scan_count::now();
        let _ = session.monitor().expect("첫 Snapshot");
        let _ = session.monitor().expect("둘째 Snapshot");
        assert_eq!(crate::artifact::scan_count::now() - before, 4);
    }

    #[test]
    fn captured_at_cannot_be_compared() {
        // 이 시험은 **컴파일되는 것 자체**가 증거가 아니다 — 오히려 그 반대다.
        // `CapturedAt` 에 `PartialEq` 나 `Ord` 가 생기면 아래 주석의 코드가 컴파일되고,
        // 그 순간 벽시계로 두 Snapshot 의 선후를 판정하는 길이 열린다.
        //
        // ```compile_fail
        // let a = session.monitor()?.captured_at;
        // let b = session.monitor()?.captured_at;
        // assert!(a < b);      // Ord 가 없다
        // assert_eq!(a, b);    // PartialEq 가 없다
        // ```
        //
        // 여기서는 그 값이 **표시용으로만** 나간다는 것을 확인한다.
        let session = session("captured-at");
        let seen = session.monitor().expect("Snapshot");
        let _: std::time::SystemTime = seen.captured_at.instant();
    }

    #[test]
    fn a_pending_without_a_declared_target_is_refused_not_guessed() {
        // **fallback 을 되살리면 여기서 걸린다.** 지금 Cycle 을 대신 넣는 구현은 이 자리에서
        // `Ok(...)` 를 돌려주고, 그 Snapshot 의 target 은 지금 자리와 같아 보인다 —
        // 읽지 못한 사실이 읽은 사실처럼 보이는 바로 그 병이다.
        //
        // 걸어서는 만들 수 없는 상태이므로 시험이 직접 짓는다(`force_pending_for_test`).
        let mut session = session("pending-no-target");
        let root = session.project().cycles().current_id();
        // 뿌리는 아직 열려 있고 되돌아가겠다고 적은 적이 없다 — 적힌 대상이 없다.
        session
            .project_mut()
            .cycles_mut()
            .force_pending_for_test(root);

        let err = session.monitor().expect_err("없는 대상을 지어냈다");
        match err {
            SessionError::Monitor(MonitorError::PendingTargetMissing { from }) => {
                assert_eq!(from, root.to_ref(), "어느 Cycle 인지 말해야 한다");
            }
            other => panic!("다른 이유로 거절됐다: {other}"),
        }
    }

    #[test]
    fn a_snapshot_writes_nothing() {
        let session = session("read-only");
        let path = session.state_path().to_path_buf();
        let before = std::fs::read(&path).expect("상태를 읽는다");
        let names: Vec<String> = session
            .project()
            .cycles()
            .nodes()
            .iter()
            .map(|cycle| cycle.id().to_ref().to_string())
            .collect();
        let ids = session.project().next_snapshot_id();

        let _ = session.monitor().expect("Snapshot");

        assert_eq!(std::fs::read(&path).unwrap(), before, "state.yaml 이 바뀌었다");
        assert_eq!(session.project().next_snapshot_id(), ids, "새 Snapshot 이 발급됐다");
        let after: Vec<String> = session
            .project()
            .cycles()
            .nodes()
            .iter()
            .map(|cycle| cycle.id().to_ref().to_string())
            .collect();
        assert_eq!(after, names, "Graph 가 바뀌었다");
    }

}
