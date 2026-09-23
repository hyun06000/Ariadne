//! **Host 로 나가는 사실** — 좌표 없는 판 있는 읽기 모델.
//!
//! [`MonitorSnapshot`] 은 GIL Core 의 **내부** read model 이다. 그대로 직렬화하면 안쪽을
//! 고칠 때마다 바깥이 깨진다 — 최근 두 조각만 해도 `timeline` 과 `summary` 로 두 번
//! 바뀌었다. 그래서 판 번호가 붙은 별도 타입 하나를 두고, 그 사이를 **순수 함수**가 잇는다.
//!
//! ```text
//! MonitorSnapshot        내부. 자유롭게 바뀐다
//!   → monitor_view_v1    순수 투영. 파일도 clock 도 잠금도 없다
//!   → MonitorViewV1      Host 중립. 판 번호가 지킨다
//! ```
//!
//! # 여기 들어가지 않는 것
//!
//! 좌표·lane·폭·SVG·HTML·CSS 는 **Project 의 사실이 아니라 공용 UI 의 파생 표현**이다.
//! 선택·접힘·filter·viewport 도 마찬가지로 UI 의 짧은 수명 상태다. 어느 것도 이 타입에
//! 칸을 갖지 않는다 — 칸이 없으면 실수로 실릴 수도 없다.
//!
//! 내부의 `active_lineage` 와 `inactive_cycles` 도 들어가지 않는다. 같은 Cycle 을 여러
//! 목록으로 보내면 UI 가 **어느 쪽을 진실로 삼을지** 다시 정해야 한다. [`MonitorViewV1`] 이
//! 아는 Cycle 목록은 `timeline` 하나다.
//!
//! # 닫힌 낱말은 enum 이 소유한다
//!
//! kind·state·relation·verdict 같은 낱말은 **이 판이 소유한 enum** 이다. `&'static str` 이나
//! `String` 으로 두지 않는다.
//!
//! ```text
//! CycleKindV1 · StepKindV1 · NodeStateV1 · TimelineRelationV1
//! WorldStateV1 · VerdictV1 · DirectionActionV1 · NextActionKindV1
//! ```
//!
//! 이유가 둘이다. **①** 사용자 글이 열거값 자리에 실릴 길이 문법적으로 없다 — 그 칸에는
//! 문자열을 넣을 수조차 없다. **②** 내부 domain enum(`CycleKind`·`NodeKind`…)을 그대로
//! 쓰지 않으므로, 안쪽에 값이 하나 늘어도 wire 계약이 조용히 넓어지지 않는다. 늘리려면
//! 이 파일의 enum 을 고쳐야 하고, 그것이 곧 판을 올릴지 정하는 자리다.
//!
//! `String` 으로 남는 것은 **참조의 canonical 표기와 사람이 쓴 글**뿐이다.

use std::time::SystemTime;

use serde::{Deserialize, Serialize};

use super::{
    ActionKind, CapturedAt, CycleReportFacts, ExperimentDefinition, MonitorSnapshot, NextAction,
    StepFacts, TimelineCycleFacts, TimelineRelation, WillFacts, WorldFacts, WorldMark,
};
use crate::cycle::CycleKind;
use crate::node::{NodeKind, NodeStatus};

/// 이 판의 번호. wire 의미의 판이며 **저장 format 번호와 다르다.**
pub const SCHEMA_VERSION: u32 = 1;

/// JSON 이 정수로 안전하게 나르는 최대값 — `2^53 - 1`.
const MAX_SAFE_INTEGER: u64 = (1 << 53) - 1;

// ── 이 판이 소유한 닫힌 낱말 ───────────────────────────────────────────────

/// 이 판의 낱말 하나 — wire 표기를 스스로 안다.
macro_rules! wire_words {
    ($(
        $(#[$about:meta])*
        $name:ident { $( $variant:ident => $word:literal ),+ $(,)? }
    )+) => {$(
        $(#[$about])*
        ///
        /// JSON 에서는 아래 낱말 그대로다. **모르는 낱말은 받지 않는다** — serde 가
        /// 알려진 값 밖을 거절하므로, 추측해 그리는 길이 문법적으로 없다.
        #[derive(
            Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
        )]
        pub enum $name { $( #[serde(rename = $word)] $variant ),+ }

        impl $name {
            /// canonical wire 표기 — ASCII lowercase snake_case.
            pub fn as_wire(self) -> &'static str {
                match self { $( $name::$variant => $word ),+ }
            }

            /// 이 판이 아는 낱말 전부. **시험이 하나도 빠뜨리지 않게 하는 자리다.**
            #[cfg(test)]
            pub(crate) const ALL: &'static [$name] = &[ $( $name::$variant ),+ ];

            /// 저장된 글자를 이 판의 값으로 되읽을 때 쓰는 표. **낱말은 한 자리에만 적힌다.**
            #[allow(dead_code)]
            pub(crate) const ALL_WORDS: &'static [(&'static str, $name)] =
                &[ $( ($word, $name::$variant) ),+ ];
        }

        impl std::fmt::Display for $name {
            fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                f.write_str(self.as_wire())
            }
        }
    )+};
}

wire_words! {
    /// Cycle 의 종류.
    CycleKindV1 {
        Interview => "interview",
        Experiment => "experiment",
    }

    /// Step 의 종류 — **여덟뿐이다.**
    ///
    /// `cycle_entry` 와 `cycle_exit` 는 여기 없다. 경계는 Step 이 아니라 **Cycle 의
    /// 자리**이고(`Walk::open` 이 `BoundaryIsNotAStep` 으로 거절한다), 그 자리에 서 있다는
    /// 사실은 [`CurrentV1::step_ref`] 가 없는 것과 Cycle 의 상태·다음 행동이 말한다.
    ///
    /// 그래서 JSON 이 받는 낱말에도 그 둘이 없다 — 밖에서 보내와도 되읽히지 않는다.
    StepKindV1 {
        Question => "question",
        Interpretation => "interpretation",
        Synthesis => "synthesis",
        Define => "define",
        Hypothesis => "hypothesis",
        Verify => "verify",
        Analysis => "analysis",
        Outcome => "outcome",
    }

    /// Node 가 열려 있는가 닫혔는가.
    NodeStateV1 {
        Open => "open",
        Closed => "closed",
    }

    /// 시간선 위의 Cycle 이 지금 걷는 갈래와 맺은 관계. **넷은 상호 배타적이다.**
    TimelineRelationV1 {
        ActivePath => "active_path",
        RevisitSource => "revisit_source",
        Abandoned => "abandoned",
        Other => "other",
    }

    /// 작업 폴더가 기준 세계와 같은가.
    WorldStateV1 {
        Clean => "clean",
        Dirty => "dirty",
        Unknown => "unknown",
    }

    /// 이 Interview 가 무엇을 묻고 있는가. **셋은 상호 배타적이다.**
    InterviewStateV1 {
        NotAsked => "not_asked",
        Asking => "asking",
        Asked => "asked",
    }

    /// 닫힌 Cycle 의 판정.
    VerdictV1 {
        Success => "success",
        Failure => "failure",
    }

    /// 그때 적어 둔 다음 방향. **지금의 행동이 아니다.**
    DirectionActionV1 {
        OpenChild => "open_child",
        Revisit => "revisit",
        CloseCycle => "close_cycle",
    }

    /// 지금 실제로 밟을 수 있는 동작의 종류.
    ///
    /// **아직 없는 전이는 여기 없다** — Chain close·임의 checkout·merge·승인은 담지 않는다.
    NextActionKindV1 {
        CloseStep => "close_step",
        OpenStep => "open_step",
        CloseCycle => "close_cycle",
        OpenCycle => "open_cycle",
        OpenBranch => "open_branch",
        Revisit => "revisit",
        Restore => "restore",
    }
}

// ── 나가는 모양 ────────────────────────────────────────────────────────────

/// Host UI 가 받는 사실 한 벌.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MonitorViewV1 {
    pub schema_version: u32,
    /// UTC Unix epoch 이후 밀리초.
    pub captured_at_unix_ms: u64,
    pub current: CurrentV1,
    /// 이 Journey 가 발급한 **모든 Cycle**, 발급 순서 그대로.
    pub timeline: Vec<TimelineCycleV1>,
    pub current_will: Option<WillV1>,
    pub world: WorldV1,
    /// **지금 실제로 성공할 수 있는 동작만.** 내부 read model 의 차례 그대로.
    pub next_actions: Vec<NextActionV1>,
}

/// 지금 어디에 서 있는가.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CurrentV1 {
    pub existence_ref: String,
    pub journey_ref: String,
    pub cycle_ref: String,
    /// Cycle 경계에 서 있으면 없다.
    pub step_ref: Option<String>,
}

/// 시간선 위의 Cycle 하나.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TimelineCycleV1 {
    pub cycle_ref: String,
    pub kind: CycleKindV1,
    pub state: NodeStateV1,
    pub relation_to_current: TimelineRelationV1,
    pub parent_cycle_ref: Option<String>,
    /// **부모와 다른 관계다.** 되돌아감을 parent 로 바꾸지 않는다.
    pub revisit_from_cycle_ref: Option<String>,
    pub experiment_definition: Option<DefinitionV1>,
    /// Interview 일 때만. Experiment 이면 없다.
    pub interview_question: Option<InterviewQuestionV1>,
    /// 닫힌 Cycle 의 선택적 투영. 열려 있으면 없다.
    pub report: Option<CycleReportV1>,
    /// 그 Cycle 이 만든 순서 그대로. 비어 있으면 빈 목록이다.
    pub steps: Vec<StepV1>,
}

/// 이 실험이 무엇을 풀려 하고 무엇이면 성공인가.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DefinitionV1 {
    pub problem: String,
    pub success_condition: String,
}

/// 이 Interview 의 출발 질문. `state` 가 무엇이 있는지 말한다.
///
/// `asked` 일 때만 `question` 이 있다. 읽는 쪽이 Step 목록을 뒤져 질문을 찾지 않도록
/// 여기에 실어 보낸다 — Experiment 의 `experiment_definition` 과 같은 이유다.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct InterviewQuestionV1 {
    pub state: InterviewStateV1,
    pub question: Option<String>,
    pub response: Option<String>,
}

/// 닫힌 Cycle 이 남긴 것.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CycleReportV1 {
    pub verdict: VerdictV1,
    pub handoff_summary: String,
    pub outcome_lesson: Option<String>,
    pub next_direction: Option<NextDirectionV1>,
}

/// 그때 적어 둔 다음 방향. **지금의 행동이 아니다.**
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NextDirectionV1 {
    pub action: DirectionActionV1,
    pub reason: Option<String>,
    pub target_cycle_ref: Option<String>,
}

/// Step 하나 — 초기 View 가 싣는 네 사실.
///
/// **전체 Report 는 여기 없다.** 선택한 Step 의 상세는 `NodeDetailV1` 이 따로 나른다.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StepV1 {
    pub step_ref: String,
    pub kind: StepKindV1,
    pub state: NodeStateV1,
    /// Report 원문의 대표 칸. **자르거나 다시 요약하지 않는다** — 줄임표와 줄바꿈은 UI 의
    /// 표현 책임이다.
    pub summary: Option<String>,
}

/// 지금 걸린 행동 단위.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct WillV1 {
    pub will_ref: String,
    pub objective: String,
    pub next_action: String,
    pub done_when: String,
    pub target_step_ref: String,
    pub existence_ref: String,
    pub journey_ref: String,
}

/// 기준 세계와 지금 세계.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct WorldV1 {
    pub baseline_snapshot_ref: String,
    pub state: WorldStateV1,
    /// `unknown` 의 까닭이 있을 때 그 원문. 그 밖에는 없다.
    pub reason: Option<String>,
    pub verify_can_confirm: bool,
}

/// 지금 밟을 수 있는 동작 하나.
///
/// # 대상 kind 두 칸은 서로 배타적이다
///
/// ```text
/// close_step · open_step      step_kind = Some(...)   cycle_kind = None
/// close_cycle · open_cycle
///            · open_branch    cycle_kind = Some(...)  step_kind = None
/// revisit · restore           둘 다 None
/// ```
///
/// 내부 `ActionKind` 는 값을 지닌 enum 이다. 그것을 `close_step_verify` 같은 합성 문자열로
/// 폭발시키지도, 인자를 버리지도 않는다 — **종류는 종류대로, 대상은 대상대로** 나른다.
///
/// `command` 는 **사람이 칠 글자**이지 동작의 구조를 판정하는 값이 아니다. 이 파일은 그것을
/// 파싱해 종류나 대상을 되짚지 않는다.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NextActionV1 {
    pub kind: NextActionKindV1,
    /// Step 을 대상으로 하는 동작일 때만.
    pub step_kind: Option<StepKindV1>,
    /// Cycle 을 대상으로 하는 동작일 때만.
    pub cycle_kind: Option<CycleKindV1>,
    /// 지금 CLI 에 그 명령이 실제로 있을 때만.
    pub command: Option<String>,
    pub reason: String,
    /// 함께 실린 Manual 의 canonical 주소. 설명하는 Topic 이 있을 때만.
    pub help_ref: Option<String>,
}

/// View 를 지을 수 없는 이유.
///
/// **둘 다 시각 하나 때문이다.** 사실이 모자란 것이 아니라 그 시각을 wire 의 정수로 옮길 수
/// 없다는 뜻이라, 조용히 `0` 으로 뭉개지 않고 거절한다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ViewError {
    /// 관측 시각이 Unix epoch 이전이다.
    BeforeEpoch,
    /// 밀리초가 JSON 정수의 안전 범위(`2^53-1`)를 넘었다.
    BeyondSafeInteger { millis: u128 },
    /// Cycle Report 의 판정이 이 판이 아는 낱말이 아니다.
    ///
    /// **지어내지 않는다.** Grammar 는 프로젝트마다 다를 수 있고, 모르는 낱말을 `closed`
    /// 같은 것으로 뭉개면 화면이 없는 사실을 말하게 된다. 어느 Cycle 인지와 함께 거절한다.
    UnknownVerdict { cycle_ref: String, said: String },
    /// Cycle Report 의 다음 방향이 이 판이 아는 낱말이 아니다.
    UnknownDirection { cycle_ref: String, said: String },
    /// Step 목록에 **경계가 Step 처럼** 실려 있다.
    ///
    /// 경계는 Step 이 아니므로 정상 Step 으로 표시하지 않는다. 다른 값으로 숨기지도
    /// 않는다 — 어느 자리의 어떤 경계인지와 함께 거절한다.
    BoundaryIsNotAStep { step_ref: String, kind: String },
    /// 다음 행동이 경계를 대상으로 삼고 있다.
    ///
    /// **지금 구조로는 일어나지 않는다** — `Walk::open` 이 경계를 거절하므로
    /// `openable_here` 도 `CloseStep`·`OpenStep` 도 경계를 담을 수 없다. 그래도 조용히
    /// 대상 없는 Step 동작으로 만들지 않는다.
    BoundaryInNextAction { action: String, kind: String },
}

impl std::fmt::Display for ViewError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ViewError::BeforeEpoch => {
                write!(f, "관측 시각이 Unix epoch 이전이라 wire 로 옮길 수 없다")
            }
            ViewError::BeyondSafeInteger { millis } => write!(
                f,
                "관측 시각 {millis}ms 가 정수의 안전 범위({MAX_SAFE_INTEGER})를 넘었다"
            ),
            ViewError::UnknownVerdict { cycle_ref, said } => write!(
                f,
                "{cycle_ref} 의 판정 {said:?} 은 이 판(v{SCHEMA_VERSION})이 아는 낱말이 아니다"
            ),
            ViewError::UnknownDirection { cycle_ref, said } => write!(
                f,
                "{cycle_ref} 의 다음 방향 {said:?} 은 이 판(v{SCHEMA_VERSION})이 아는 낱말이 아니다"
            ),
            ViewError::BoundaryIsNotAStep { step_ref, kind } => write!(
                f,
                "{step_ref} 의 {kind} 는 Cycle 경계이지 Step 이 아니다"
            ),
            ViewError::BoundaryInNextAction { action, kind } => write!(
                f,
                "다음 행동 {action} 이 Cycle 경계 {kind} 를 대상으로 삼았다"
            ),
        }
    }
}

impl std::error::Error for ViewError {}

// ── 투영 ───────────────────────────────────────────────────────────────────

/// Snapshot 하나를 Host 로 나갈 사실로 옮긴다.
///
/// # 순수하다
///
/// 입력은 [`MonitorSnapshot`] 하나뿐이다. 파일도, Project 도, 시계도 다시 읽지 않고 새
/// 잠금을 잡지 않는다 — **읽을 것이 인수 안에 전부 있다.** 시각조차 Snapshot 이 이미 지닌
/// 관측 시각에서 나오므로, 같은 Snapshot 은 언제 불러도 같은 View 가 된다.
///
/// # 순서를 다시 정하지 않는다
///
/// `timeline` 과 `steps` 의 차례가 곧 시간이다. 여기서 정렬하면 그 기준이 새 진실 판정이
/// 되고, 참조의 **번호로 시간을 짐작하는** 일이 다시 시작된다.
pub fn monitor_view_v1(seen: &MonitorSnapshot) -> Result<MonitorViewV1, ViewError> {
    // 서 있는 자리도 Step 이어야 한다. **[`CurrentV1`] 은 종류를 나르지 않으므로**
    // 여기서 보지 않으면 경계가 조용히 지나간다.
    if let Some(here) = &seen.current_step {
        check_is_a_step(here)?;
    }
    Ok(MonitorViewV1 {
        schema_version: SCHEMA_VERSION,
        captured_at_unix_ms: unix_millis(seen.captured_at)?,
        current: CurrentV1 {
            existence_ref: seen.current_existence.existence_ref.to_string(),
            journey_ref: seen.current_existence.journey_ref.to_string(),
            cycle_ref: seen.current_cycle.facts.cycle_ref.to_string(),
            // **없으면 없다.** 서 있는 자리가 없다고 아무 Step 이나 고르지 않는다.
            step_ref: seen
                .current_step
                .as_ref()
                .map(|step| step.step_ref.to_string()),
        },
        timeline: seen
            .timeline
            .iter()
            .map(cycle)
            .collect::<Result<Vec<_>, _>>()?,
        current_will: seen.current_will.as_ref().map(will),
        world: world(&seen.world),
        // 차례를 다시 정하지 않는다 — 내부 read model 이 고른 순서가 곧 이 순서다.
        next_actions: seen
            .next_actions
            .iter()
            .map(action)
            .collect::<Result<Vec<_>, _>>()?,
    })
}

/// 관측 시각을 wire 의 정수로.
fn unix_millis(at: CapturedAt) -> Result<u64, ViewError> {
    let since = at
        .instant()
        .duration_since(SystemTime::UNIX_EPOCH)
        .map_err(|_| ViewError::BeforeEpoch)?;
    let millis = since.as_millis();
    match u64::try_from(millis) {
        Ok(ms) if ms <= MAX_SAFE_INTEGER => Ok(ms),
        _ => Err(ViewError::BeyondSafeInteger { millis }),
    }
}

fn cycle(entry: &TimelineCycleFacts) -> Result<TimelineCycleV1, ViewError> {
    let facts = &entry.facts;
    let address = facts.cycle_ref.to_string();
    Ok(TimelineCycleV1 {
        kind: cycle_kind(facts.kind),
        state: state(facts.state),
        relation_to_current: relation(entry.relation_to_current),
        parent_cycle_ref: facts.parent_cycle_ref.map(|at| at.to_string()),
        revisit_from_cycle_ref: facts.revisit_from_cycle_ref.map(|at| at.to_string()),
        experiment_definition: facts.experiment_definition.as_ref().map(definition),
        interview_question: facts.interview_question.as_ref().map(interview_question),
        report: facts
            .report
            .as_ref()
            .map(|facts| report(&address, facts))
            .transpose()?,
        steps: entry
            .steps
            .iter()
            .map(step)
            .collect::<Result<Vec<_>, _>>()?,
        cycle_ref: address,
    })
}

fn step(facts: &StepFacts) -> Result<StepV1, ViewError> {
    Ok(StepV1 {
        step_ref: facts.step_ref.to_string(),
        kind: check_is_a_step(facts)?,
        state: state(facts.state),
        // **원문 그대로.** 자르는 것은 그리는 쪽의 일이다.
        summary: facts.summary.clone(),
    })
}

/// 이 사실이 정말 Step 인가 — 아니면 어느 자리의 어떤 경계인지와 함께 거절한다.
fn check_is_a_step(facts: &StepFacts) -> Result<StepKindV1, ViewError> {
    step_kind(facts.kind).ok_or_else(|| ViewError::BoundaryIsNotAStep {
        step_ref: facts.step_ref.to_string(),
        kind: facts.kind.as_str().to_string(),
    })
}

fn definition(facts: &ExperimentDefinition) -> DefinitionV1 {
    DefinitionV1 {
        problem: facts.problem.clone(),
        success_condition: facts.success_condition.clone(),
    }
}

fn report(address: &str, facts: &CycleReportFacts) -> Result<CycleReportV1, ViewError> {
    Ok(CycleReportV1 {
        verdict: verdict(address, &facts.verdict)?,
        handoff_summary: facts.handoff_summary.clone(),
        outcome_lesson: facts.outcome_lesson.clone(),
        next_direction: facts
            .next_direction
            .as_ref()
            .map(|at| {
                Ok(NextDirectionV1 {
                    action: direction(address, &at.action)?,
                    reason: at.reason.clone(),
                    target_cycle_ref: at.target_cycle_ref.map(|at| at.to_string()),
                })
            })
            .transpose()?,
    })
}

/// 지금 밟을 수 있는 동작 하나를 wire 로.
///
/// **`command` 를 읽지 않는다.** 종류와 대상은 오직 내부 [`ActionKind`] 의 모양에서 온다.
fn action(facts: &NextAction) -> Result<NextActionV1, ViewError> {
    let (kind, step_kind, cycle_kind) = match facts.kind {
        ActionKind::CloseStep(kind) => (NextActionKindV1::CloseStep, Some(kind), None),
        ActionKind::OpenStep(kind) => (NextActionKindV1::OpenStep, Some(kind), None),
        ActionKind::CloseCycle(kind) => (NextActionKindV1::CloseCycle, None, Some(kind)),
        ActionKind::OpenCycle(kind) => (NextActionKindV1::OpenCycle, None, Some(kind)),
        ActionKind::OpenBranch(kind) => (NextActionKindV1::OpenBranch, None, Some(kind)),
        ActionKind::Revisit => (NextActionKindV1::Revisit, None, None),
        ActionKind::Restore => (NextActionKindV1::Restore, None, None),
    };
    let step_kind = match step_kind {
        // 대상이 경계면 조용히 「대상 없음」으로 만들지 않는다 — 그러면 wire 가
        // 「대상 없는 Step 동작」이라는 있을 수 없는 모양을 말하게 된다.
        Some(inner) => Some(self::step_kind(inner).ok_or_else(|| {
            ViewError::BoundaryInNextAction {
                action: kind.as_wire().to_string(),
                kind: inner.as_str().to_string(),
            }
        })?),
        None => None,
    };
    Ok(NextActionV1 {
        kind,
        step_kind,
        cycle_kind: cycle_kind.map(self::cycle_kind),
        command: facts.command.clone(),
        reason: facts.reason.clone(),
        // canonical 주소 그대로. 여기서 다듬거나 붙이지 않는다.
        help_ref: facts.help_ref.as_ref().map(|at| at.to_string()),
    })
}

fn will(facts: &WillFacts) -> WillV1 {
    WillV1 {
        will_ref: facts.will_ref.to_string(),
        objective: facts.objective.clone(),
        next_action: facts.next_action.clone(),
        done_when: facts.done_when.clone(),
        target_step_ref: facts.target_step_ref.to_string(),
        existence_ref: facts.existence_ref.to_string(),
        journey_ref: facts.journey_ref.to_string(),
    }
}

fn world(facts: &WorldFacts) -> WorldV1 {
    WorldV1 {
        baseline_snapshot_ref: facts.baseline_snapshot_ref.to_string(),
        state: match facts.state {
            WorldMark::Clean => WorldStateV1::Clean,
            WorldMark::Dirty => WorldStateV1::Dirty,
            WorldMark::Unknown => WorldStateV1::Unknown,
        },
        reason: facts.reason.clone(),
        verify_can_confirm: facts.verify_can_confirm,
    }
}

// ── 안쪽 낱말을 이 판의 낱말로 ─────────────────────────────────────────────
//
// **한 자리에 하나씩.** `match` 가 남김없이 덮으므로, 안쪽에 값이 하나 늘면 여기가 먼저
// 컴파일되지 않는다 — 그때가 판을 올릴지 정하는 자리다.

pub(super) fn cycle_kind(kind: CycleKind) -> CycleKindV1 {
    match kind {
        CycleKind::Interview => CycleKindV1::Interview,
        CycleKind::Experiment => CycleKindV1::Experiment,
    }
}

/// 안쪽 Node 종류를 이 판의 Step 종류로 — **경계는 Step 이 아니므로 없다.**
///
/// 도메인에는 경계가 계속 산다(`NodeKind::CycleEntry`·`CycleExit`). 여기서 그것을
/// **다른 값으로 숨기지 않고** 없음으로 답한다. 무엇을 할지는 부르는 자리가 정한다 —
/// 투영은 거절하고, 상세 조회는 「그런 Step 이 없다」로 답한다.
pub(super) fn step_kind(kind: NodeKind) -> Option<StepKindV1> {
    Some(match kind {
        NodeKind::CycleEntry | NodeKind::CycleExit => return None,
        NodeKind::Question => StepKindV1::Question,
        NodeKind::Interpretation => StepKindV1::Interpretation,
        NodeKind::Synthesis => StepKindV1::Synthesis,
        NodeKind::Define => StepKindV1::Define,
        NodeKind::Hypothesis => StepKindV1::Hypothesis,
        NodeKind::Verify => StepKindV1::Verify,
        NodeKind::Analysis => StepKindV1::Analysis,
        NodeKind::Outcome => StepKindV1::Outcome,
    })
}

pub(super) fn state(state: NodeStatus) -> NodeStateV1 {
    match state {
        NodeStatus::Open => NodeStateV1::Open,
        NodeStatus::Closed => NodeStateV1::Closed,
    }
}

fn relation(relation: TimelineRelation) -> TimelineRelationV1 {
    match relation {
        TimelineRelation::ActivePath => TimelineRelationV1::ActivePath,
        TimelineRelation::RevisitSource => TimelineRelationV1::RevisitSource,
        TimelineRelation::Abandoned => TimelineRelationV1::Abandoned,
        TimelineRelation::Other => TimelineRelationV1::Other,
    }
}

/// 판정은 **Grammar 가 정한 글자**로 저장된다 — 그래서 열거가 아니라 대조다.
///
/// 모르는 낱말이면 거절한다. Grammar 는 프로젝트마다 다를 수 있고, 지어낸 값을 실으면
/// 화면이 없는 사실을 말하게 된다.
/// 읽기 모델의 세 상태를 그대로 옮긴다. 여기서 뜻을 더하지 않는다.
fn interview_question(one: &crate::InterviewQuestion) -> InterviewQuestionV1 {
    match one {
        crate::InterviewQuestion::NotAsked => InterviewQuestionV1 {
            state: InterviewStateV1::NotAsked,
            question: None,
            response: None,
        },
        crate::InterviewQuestion::Asking => InterviewQuestionV1 {
            state: InterviewStateV1::Asking,
            question: None,
            response: None,
        },
        crate::InterviewQuestion::Asked { question, response } => InterviewQuestionV1 {
            state: InterviewStateV1::Asked,
            question: Some(question.clone()),
            response: response.clone(),
        },
    }
}

fn verdict(cycle_ref: &str, said: &str) -> Result<VerdictV1, ViewError> {
    VerdictV1::ALL_WORDS
        .iter()
        .find(|(word, _)| *word == said)
        .map(|(_, value)| *value)
        .ok_or_else(|| ViewError::UnknownVerdict {
            cycle_ref: cycle_ref.to_string(),
            said: said.to_string(),
        })
}

fn direction(cycle_ref: &str, said: &str) -> Result<DirectionActionV1, ViewError> {
    DirectionActionV1::ALL_WORDS
        .iter()
        .find(|(word, _)| *word == said)
        .map(|(_, value)| *value)
        .ok_or_else(|| ViewError::UnknownDirection {
            cycle_ref: cycle_ref.to_string(),
            said: said.to_string(),
        })
}

#[cfg(test)]
mod tests {
    use super::super::graph::tests::reading_one;
    use super::*;

    fn viewed() -> MonitorViewV1 {
        monitor_view_v1(&reading_one()).expect("View 를 짓는다")
    }

    // ── ① 같은 사실, 같은 View ────────────────────────────────────────────

    #[test]
    fn the_same_snapshot_makes_the_same_view() {
        let seen = reading_one();
        assert_eq!(
            monitor_view_v1(&seen).expect("한 번"),
            monitor_view_v1(&seen).expect("두 번"),
            "같은 Snapshot 이 다른 View 를 냈다"
        );
        assert_eq!(viewed().schema_version, SCHEMA_VERSION);
        assert_eq!(SCHEMA_VERSION, 1, "v1 의 판 번호가 바뀌었다");
    }

    #[test]
    fn the_two_inner_lists_never_reach_the_wire() {
        // **두 목록을 통째로 비워도 같은 View 다.** 타입에 칸이 없다는 것과, 투영이 그것을
        // 읽지 않는다는 것은 다른 말이라 둘 다 잰다.
        let seen = reading_one();
        let mut alone = seen.clone();
        alone.active_lineage.clear();
        alone.inactive_cycles.clear();
        assert_eq!(
            monitor_view_v1(&seen).expect("원본"),
            monitor_view_v1(&alone).expect("비운 것"),
            "투영이 아직 두 목록을 읽고 있다"
        );
        // 그리고 그 View 가 빈 View 가 아니다.
        let view = monitor_view_v1(&alone).expect("비운 것");
        assert_eq!(view.timeline.len(), 3);
        assert!(
            view.timeline
                .iter()
                .any(|one| one.relation_to_current == TimelineRelationV1::RevisitSource)
        );
    }

    // ── ② 순서는 그대로 ──────────────────────────────────────────────────

    #[test]
    fn the_timeline_and_step_order_are_carried_through_untouched() {
        let seen = reading_one();
        let view = monitor_view_v1(&seen).expect("View");

        let inner: Vec<String> = seen
            .timeline
            .iter()
            .map(|one| one.facts.cycle_ref.to_string())
            .collect();
        let wire: Vec<String> = view.timeline.iter().map(|one| one.cycle_ref.clone()).collect();
        assert_eq!(wire, inner, "Cycle 의 차례가 바뀌었다");

        for (one, other) in view.timeline.iter().zip(&seen.timeline) {
            let inner: Vec<String> =
                other.steps.iter().map(|step| step.step_ref.to_string()).collect();
            let wire: Vec<String> = one.steps.iter().map(|step| step.step_ref.clone()).collect();
            assert_eq!(wire, inner, "{} 의 Step 차례가 바뀌었다", one.cycle_ref);
        }
        // 정렬한 결과가 아니다 — 이 시나리오에서 발급 순서와 이름순이 우연히 같을 수 있으므로
        // 구조로도 확인한다: 부모는 언제나 자식보다 앞이다.
        let at = |address: &str| wire_at(&view, address);
        assert!(at("cycle:C1") < at("cycle:C2") && at("cycle:C2") < at("cycle:C3"));
    }

    fn wire_at(view: &MonitorViewV1, address: &str) -> usize {
        view.timeline
            .iter()
            .position(|one| one.cycle_ref == address)
            .unwrap_or_else(|| panic!("{address} 이 없다"))
    }

    // ── ③ 네 관계 ────────────────────────────────────────────────────────

    #[test]
    fn the_four_relations_project_to_exactly_four_values() {
        // 값에서 값으로 가는 길이 넷뿐이고 서로 겹치지 않는다.
        let paired = [
            (TimelineRelation::ActivePath, TimelineRelationV1::ActivePath, "active_path"),
            (TimelineRelation::RevisitSource, TimelineRelationV1::RevisitSource, "revisit_source"),
            (TimelineRelation::Abandoned, TimelineRelationV1::Abandoned, "abandoned"),
            (TimelineRelation::Other, TimelineRelationV1::Other, "other"),
        ];
        for (inner, wire, word) in paired {
            assert_eq!(relation(inner), wire);
            assert_eq!(wire.as_wire(), word);
        }
        // 이 판이 아는 관계가 정확히 넷이고, 위에서 넷을 다 덮었다.
        assert_eq!(TimelineRelationV1::ALL.len(), 4);
        assert_eq!(paired.len(), TimelineRelationV1::ALL.len());

        let view = viewed();
        assert_eq!(view.timeline[1].relation_to_current, TimelineRelationV1::RevisitSource);
        assert_eq!(view.timeline[2].relation_to_current, TimelineRelationV1::ActivePath);
    }

    // ── ④ 참조는 왕복한다 ────────────────────────────────────────────────

    #[test]
    fn every_reference_round_trips_back_to_its_typed_form() {
        use crate::{CycleRef, ExistenceRef, JourneyRef, SnapshotRef, StepRef, WillRef};
        let view = viewed();

        view.current.existence_ref.parse::<ExistenceRef>().expect("존재");
        view.current.journey_ref.parse::<JourneyRef>().expect("판");
        let here: CycleRef = view.current.cycle_ref.parse().expect("Cycle");
        assert_eq!(here.to_string(), view.current.cycle_ref);
        if let Some(step) = &view.current.step_ref {
            assert_eq!(step.parse::<StepRef>().expect("Step").to_string(), *step);
        }
        view.world
            .baseline_snapshot_ref
            .parse::<SnapshotRef>()
            .expect("기준 세계");

        let mut checked = 0usize;
        for one in &view.timeline {
            assert_eq!(one.cycle_ref.parse::<CycleRef>().expect("Cycle").to_string(), one.cycle_ref);
            for at in [&one.parent_cycle_ref, &one.revisit_from_cycle_ref] {
                if let Some(at) = at {
                    assert_eq!(at.parse::<CycleRef>().expect("Cycle").to_string(), *at);
                    checked += 1;
                }
            }
            for step in &one.steps {
                assert_eq!(
                    step.step_ref.parse::<StepRef>().expect("Step").to_string(),
                    step.step_ref
                );
                checked += 1;
            }
        }
        assert!(checked >= 12, "왕복시킨 참조가 너무 적다: {checked}");

        // 걸린 행동의 참조도.
        let mut seen = reading_one();
        seen.current_will = Some(crate::WillFacts {
            will_ref: "will:W3".parse::<WillRef>().expect("Will"),
            objective: "가".to_string(),
            next_action: "나".to_string(),
            done_when: "다".to_string(),
            target_step_ref: "step:C3/S3".parse::<StepRef>().expect("Step"),
            existence_ref: "existence:X1".parse::<ExistenceRef>().expect("존재"),
            journey_ref: "journey:X1@J1".parse::<JourneyRef>().expect("판"),
        });
        let will = monitor_view_v1(&seen).expect("View").current_will.expect("걸린 행동");
        assert_eq!(will.will_ref.parse::<WillRef>().expect("Will").to_string(), will.will_ref);
        assert_eq!(
            will.target_step_ref.parse::<StepRef>().expect("Step").to_string(),
            will.target_step_ref
        );
    }

    // ── ⑤ 없는 것은 없다 ────────────────────────────────────────────────

    #[test]
    fn standing_at_a_cycle_boundary_leaves_the_step_empty() {
        let mut seen = reading_one();
        seen.current_step = None;
        let view = monitor_view_v1(&seen).expect("View");
        assert_eq!(view.current.step_ref, None, "없는 자리를 지어냈다");
        // 그래도 나머지 사실은 그대로다.
        assert_eq!(view.current.cycle_ref, "cycle:C3");
        assert_eq!(view.timeline.len(), 3);
    }

    #[test]
    fn an_open_cycle_carries_no_report_and_an_open_step_no_summary() {
        let view = viewed();
        let here = view.timeline.iter().find(|one| one.cycle_ref == "cycle:C3").expect("지금");
        assert_eq!(here.state, NodeStateV1::Open);
        assert_eq!(here.report, None, "열린 Cycle 이 Report 를 지녔다");
        let open = here
            .steps
            .iter()
            .find(|step| step.state == NodeStateV1::Open)
            .expect("열린 Step");
        assert_eq!(open.summary, None, "닫히기 전에 요약을 지녔다");
        // 닫힌 Cycle 은 Report 를 지닌다.
        let done = view.timeline.iter().find(|one| one.cycle_ref == "cycle:C2").expect("실패");
        assert_eq!(done.report.as_ref().expect("Report").verdict, VerdictV1::Failure);
    }

    // ── ⑥ 글은 원문 그대로 ──────────────────────────────────────────────

    #[test]
    fn a_long_summary_crosses_the_wire_whole() {
        let mut seen = reading_one();
        let long = "가".repeat(4000);
        let nasty = format!("</text>\n둘째 줄\t& \"셋\" {long}");
        for entry in &mut seen.timeline {
            for step in &mut entry.steps {
                step.summary = Some(nasty.clone());
            }
        }
        let view = monitor_view_v1(&seen).expect("View");
        for one in &view.timeline {
            for step in &one.steps {
                assert_eq!(step.summary.as_deref(), Some(nasty.as_str()), "원문이 바뀌었다");
            }
        }
        // 자르지도, escape 하지도, 줄바꿈을 접지도 않았다.
        let said = view.timeline[0].steps[0].summary.as_ref().expect("요약");
        assert!(said.contains('\n') && said.contains('\t'), "줄바꿈을 건드렸다");
        assert!(said.contains("</text>") && said.contains('"'), "escape 했다");
        assert_eq!(said.chars().count(), nasty.chars().count());
    }

    // ── ⑦ 시각 ───────────────────────────────────────────────────────────

    #[test]
    fn a_time_that_cannot_cross_the_wire_is_refused_not_flattened() {
        use std::time::Duration;

        let mut seen = reading_one();
        // epoch 이전.
        seen.captured_at = CapturedAt(SystemTime::UNIX_EPOCH - Duration::from_secs(1));
        assert_eq!(monitor_view_v1(&seen), Err(ViewError::BeforeEpoch));

        // 안전 범위 밖.
        seen.captured_at =
            CapturedAt(SystemTime::UNIX_EPOCH + Duration::from_millis(MAX_SAFE_INTEGER + 1));
        assert!(
            matches!(
                monitor_view_v1(&seen),
                Err(ViewError::BeyondSafeInteger { .. })
            ),
            "안전 범위를 넘었는데 통과했다"
        );

        // 경계값은 지난다.
        seen.captured_at = CapturedAt(SystemTime::UNIX_EPOCH + Duration::from_millis(MAX_SAFE_INTEGER));
        assert_eq!(
            monitor_view_v1(&seen).expect("경계는 지난다").captured_at_unix_ms,
            MAX_SAFE_INTEGER
        );
        // epoch 자신도.
        seen.captured_at = CapturedAt(SystemTime::UNIX_EPOCH);
        assert_eq!(monitor_view_v1(&seen).expect("epoch").captured_at_unix_ms, 0);
        // **0 으로 뭉개지 않는다** — 위의 두 실패가 `Ok(0)` 이 아니었다는 것이 그 증거다.
    }

    // ── ⑧ 좌표는 어디에도 없다 ──────────────────────────────────────────

    // ── ⑨ 안쪽 낱말이 하나도 빠짐없이 건너오는가 ─────────────────────────

    #[test]
    fn every_inner_word_lands_on_exactly_one_view_word() {
        // **안쪽 값을 전부 훑는다.** 하나라도 빠지면 여기서 걸린다.
        let cycles = [CycleKind::Interview, CycleKind::Experiment];
        assert_eq!(cycles.len(), CycleKindV1::ALL.len(), "Cycle 종류의 수가 다르다");
        for kind in cycles {
            assert_eq!(cycle_kind(kind).as_wire(), kind.as_str(), "{kind:?}");
        }

        // **여덟뿐이다.** 경계 둘은 Step 이 아니므로 이 판에 없다.
        let steps = [
            NodeKind::Question, NodeKind::Interpretation, NodeKind::Synthesis,
            NodeKind::Define, NodeKind::Hypothesis, NodeKind::Verify, NodeKind::Analysis,
            NodeKind::Outcome,
        ];
        assert_eq!(steps.len(), 8, "Step 종류가 여덟이 아니다");
        assert_eq!(steps.len(), StepKindV1::ALL.len(), "Step 종류의 수가 다르다");
        for kind in steps {
            assert_eq!(
                step_kind(kind).expect("Step 이다").as_wire(),
                kind.as_str(),
                "{kind:?}"
            );
        }
        // 경계는 없음으로 답한다 — 다른 값으로 숨기지 않는다.
        for boundary in [NodeKind::CycleEntry, NodeKind::CycleExit] {
            assert_eq!(step_kind(boundary), None, "{boundary:?} 를 Step 으로 봤다");
        }

        for one in [NodeStatus::Open, NodeStatus::Closed] {
            assert_eq!(state(one).as_wire(), one.to_string(), "{one:?}");
        }
        assert_eq!(NodeStateV1::ALL.len(), 2);

        for (one, word) in [
            (WorldMark::Clean, "clean"),
            (WorldMark::Dirty, "dirty"),
            (WorldMark::Unknown, "unknown"),
        ] {
            let mut seen = reading_one();
            seen.world.state = one;
            assert_eq!(
                monitor_view_v1(&seen).expect("View").world.state.as_wire(),
                word
            );
        }
        assert_eq!(WorldStateV1::ALL.len(), 3);

        // Interview 의 세 상태가 **상호 배타적**으로 남아 있는가. 값이 늘면 renderer 가
        // 모르는 상태를 만나게 되므로, 여기서 수를 못 박아 그 변화를 드러낸다.
        assert_eq!(InterviewStateV1::ALL.len(), 3);
        for (one, word) in [
            (crate::InterviewQuestion::NotAsked, "not_asked"),
            (crate::InterviewQuestion::Asking, "asking"),
            (
                crate::InterviewQuestion::Asked {
                    question: "물음".into(),
                    response: None,
                },
                "asked",
            ),
        ] {
            assert_eq!(interview_question(&one).state.as_wire(), word);
        }
        // 글은 `asked` 일 때만 실린다 — 없는 질문을 빈 글로 낮추지 않는다.
        assert_eq!(interview_question(&crate::InterviewQuestion::Asking).question, None);

        // 두 낱말 표는 Grammar 가 허용하는 글자와 짝이 맞는다.
        assert_eq!(VerdictV1::ALL.len(), 2);
        for (word, value) in VerdictV1::ALL_WORDS {
            assert_eq!(verdict("cycle:C1", word).expect("아는 낱말"), *value);
        }
        assert_eq!(DirectionActionV1::ALL.len(), 3);
        for (word, value) in DirectionActionV1::ALL_WORDS {
            assert_eq!(direction("cycle:C1", word).expect("아는 낱말"), *value);
        }
        // 그리고 **모르는 낱말은 지어내지 않고 거절한다.**
        assert!(matches!(
            verdict("cycle:C9", "inconclusive"),
            Err(ViewError::UnknownVerdict { .. })
        ));
        assert!(matches!(
            direction("cycle:C9", "close_chain"),
            Err(ViewError::UnknownDirection { .. })
        ));
    }

    // ── ⑨-2 경계는 Step 이 아니다 ────────────────────────────────────────

    #[test]
    fn a_boundary_smuggled_into_the_timeline_is_refused_not_disguised() {
        for boundary in [NodeKind::CycleEntry, NodeKind::CycleExit] {
            let mut seen = reading_one();
            let at = seen.timeline[1].steps[2].step_ref;
            seen.timeline[1].steps[2].kind = boundary;

            assert_eq!(
                monitor_view_v1(&seen),
                Err(ViewError::BoundaryIsNotAStep {
                    step_ref: at.to_string(),
                    kind: boundary.as_str().to_string(),
                }),
                "{boundary:?} 를 정상 Step 으로 그렸거나 다른 값으로 숨겼다"
            );
        }
    }

    #[test]
    fn a_boundary_standing_as_the_current_step_is_refused() {
        // **`CurrentV1` 은 종류를 나르지 않는다.** 그래서 보지 않으면 조용히 지나간다.
        let mut seen = reading_one();
        let mut here = seen.current_step.clone().expect("열린 자리");
        here.kind = NodeKind::CycleExit;
        let at = here.step_ref.to_string();
        seen.current_step = Some(here);
        // 시간선 쪽은 깨끗하게 둔다 — 걸리는 자리가 정말 current 인지 가르려고.
        assert!(seen.timeline.iter().all(|one| one
            .steps
            .iter()
            .all(|step| !matches!(step.kind, NodeKind::CycleEntry | NodeKind::CycleExit))));

        assert_eq!(
            monitor_view_v1(&seen),
            Err(ViewError::BoundaryIsNotAStep {
                step_ref: at,
                kind: "cycle_exit".to_string(),
            }),
            "서 있는 자리의 경계를 지나쳤다"
        );
    }

    #[test]
    fn a_boundary_as_an_action_target_is_refused_not_flattened_to_none() {
        // 지금 구조로는 일어나지 않지만, 일어난다면 **대상 없는 Step 동작**이라는 있을 수
        // 없는 모양이 되므로 거절한다.
        let mut seen = reading_one();
        seen.next_actions = vec![crate::NextAction {
            kind: ActionKind::OpenStep(NodeKind::CycleEntry),
            command: None,
            reason: "까닭".to_string(),
            help_ref: None,
        }];
        assert_eq!(
            monitor_view_v1(&seen),
            Err(ViewError::BoundaryInNextAction {
                action: "open_step".to_string(),
                kind: "cycle_entry".to_string(),
            })
        );
    }

    #[test]
    fn a_cycle_boundary_shows_itself_by_the_missing_step_ref() {
        // 경계에 서 있다는 사실의 **정상적인** 표현. 거절이 아니다.
        let mut seen = reading_one();
        seen.current_step = None;
        let view = monitor_view_v1(&seen).expect("정상 View");
        assert_eq!(view.current.step_ref, None, "경계를 다른 것으로 말했다");
        // 그리고 Cycle 의 상태와 다음 행동은 그대로 있다.
        assert_eq!(view.current.cycle_ref, "cycle:C3");
        assert_eq!(
            view.timeline
                .iter()
                .find(|one| one.cycle_ref == "cycle:C3")
                .expect("지금")
                .state,
            NodeStateV1::Open
        );
        // Step 목록에는 경계가 하나도 없다.
        for one in &view.timeline {
            assert!(one.steps.iter().all(|step| StepKindV1::ALL.contains(&step.kind)));
        }
    }

    #[test]
    fn a_user_string_can_never_sit_in_an_enum_field() {
        // 이 시험이 **컴파일되는 것 자체**가 증거가 아니라, 아래 줄이 컴파일되지 **않는
        // 것**이 증거다. 그래서 대신 형을 확인한다 — 열거값 칸은 문자열을 받지 않는다.
        //
        //     view.timeline[0].kind = "내가 쓴 글".to_string();   // ← 컴파일되지 않는다
        //
        // 사용자 글이 닿는 칸은 참조 표기와 사람의 글뿐이고, 그 둘은 열거 칸이 아니다.
        let mut seen = reading_one();
        let nasty = "active_path\" onload=x".to_string();
        seen.timeline[0].facts.experiment_definition = Some(crate::ExperimentDefinition {
            problem: nasty.clone(),
            success_condition: nasty.clone(),
        });
        seen.timeline[0].steps[0].summary = Some(nasty.clone());
        let view = monitor_view_v1(&seen).expect("View");

        // 글은 글의 자리에 그대로 있다.
        let definition = view.timeline[0].experiment_definition.as_ref().expect("정의");
        assert_eq!(definition.problem, nasty);
        assert_eq!(view.timeline[0].steps[0].summary.as_deref(), Some(nasty.as_str()));
        // 그러나 열거 칸은 이 판의 값 중 하나다.
        assert!(CycleKindV1::ALL.contains(&view.timeline[0].kind));
        assert!(TimelineRelationV1::ALL.contains(&view.timeline[0].relation_to_current));
        assert!(StepKindV1::ALL.contains(&view.timeline[0].steps[0].kind));
        assert_eq!(StepKindV1::ALL.len(), 8, "Step 종류가 여덟이 아니다");
    }

    // ── ⑩ 값을 지닌 ActionKind ───────────────────────────────────────────

    /// 지금 있는 일곱 동작을 전부 담은 Snapshot.
    fn with_every_action() -> crate::MonitorSnapshot {
        let mut seen = reading_one();
        let make = |kind: ActionKind, command: Option<&str>| crate::NextAction {
            kind,
            command: command.map(str::to_string),
            reason: "까닭".to_string(),
            help_ref: None,
        };
        seen.next_actions = vec![
            make(ActionKind::CloseStep(NodeKind::Verify), Some("gil close")),
            make(ActionKind::OpenStep(NodeKind::Analysis), Some("gil open analysis")),
            make(ActionKind::CloseCycle(CycleKind::Experiment), Some("gil close")),
            make(ActionKind::OpenCycle(CycleKind::Experiment), Some("gil open experiment")),
            make(ActionKind::OpenBranch(CycleKind::Interview), Some("gil open interview")),
            make(ActionKind::Revisit, Some("gil revisit")),
            make(ActionKind::Restore, None),
        ];
        seen
    }

    #[test]
    fn a_valued_action_kind_loses_neither_its_kind_nor_its_target() {
        let view = monitor_view_v1(&with_every_action()).expect("View");
        let table: Vec<(&str, Option<&str>, Option<&str>)> = view
            .next_actions
            .iter()
            .map(|one| {
                (
                    one.kind.as_wire(),
                    one.step_kind.map(StepKindV1::as_wire),
                    one.cycle_kind.map(CycleKindV1::as_wire),
                )
            })
            .collect();
        assert_eq!(
            table,
            vec![
                ("close_step", Some("verify"), None),
                ("open_step", Some("analysis"), None),
                ("close_cycle", None, Some("experiment")),
                ("open_cycle", None, Some("experiment")),
                ("open_branch", None, Some("interview")),
                ("revisit", None, None),
                ("restore", None, None),
            ],
            "인자가 사라졌거나 합성 문자열로 뭉개졌다"
        );
        // 일곱 종류를 하나도 빠뜨리지 않았다.
        assert_eq!(view.next_actions.len(), NextActionKindV1::ALL.len());
    }

    #[test]
    fn the_two_target_kinds_are_never_both_set_and_never_both_missing_by_accident() {
        let view = monitor_view_v1(&with_every_action()).expect("View");
        for one in &view.next_actions {
            // **둘 다 채워지는 일이 없다.**
            assert!(
                !(one.step_kind.is_some() && one.cycle_kind.is_some()),
                "{} 가 두 대상을 함께 지녔다",
                one.kind
            );
            // 그리고 어느 쪽이 채워지는지는 종류가 정한다.
            let (step, cycle) = match one.kind {
                NextActionKindV1::CloseStep | NextActionKindV1::OpenStep => (true, false),
                NextActionKindV1::CloseCycle
                | NextActionKindV1::OpenCycle
                | NextActionKindV1::OpenBranch => (false, true),
                NextActionKindV1::Revisit | NextActionKindV1::Restore => (false, false),
            };
            assert_eq!(one.step_kind.is_some(), step, "{} 의 Step 대상", one.kind);
            assert_eq!(one.cycle_kind.is_some(), cycle, "{} 의 Cycle 대상", one.kind);
        }
    }

    #[test]
    fn the_command_is_never_read_to_guess_the_shape() {
        // 명령 글자를 지워도 종류와 대상은 그대로다 — 파싱하지 않는다는 증거다.
        let mut seen = with_every_action();
        let with = monitor_view_v1(&seen).expect("View");
        for one in &mut seen.next_actions {
            one.command = None;
        }
        let without = monitor_view_v1(&seen).expect("View");
        for (one, other) in with.next_actions.iter().zip(&without.next_actions) {
            assert_eq!((one.kind, one.step_kind, one.cycle_kind),
                       (other.kind, other.step_kind, other.cycle_kind));
        }
        assert!(without.next_actions.iter().all(|one| one.command.is_none()));
        // 있으면 원문 그대로 나른다.
        assert_eq!(with.next_actions[0].command.as_deref(), Some("gil close"));
    }

    #[test]
    fn the_help_address_crosses_as_the_canonical_string_itself() {
        let mut seen = reading_one();
        let topic = crate::manual::TopicId::parse("artifact/restore").expect("주소");
        seen.next_actions = vec![crate::NextAction {
            kind: ActionKind::Restore,
            command: Some("gil restore".to_string()),
            reason: "폴더가 바뀌었다".to_string(),
            help_ref: Some(topic.clone()),
        }];
        let view = monitor_view_v1(&seen).expect("View");
        assert_eq!(view.next_actions[0].help_ref.as_deref(), Some("artifact/restore"));
        assert_eq!(view.next_actions[0].help_ref.as_deref(), Some(topic.to_string().as_str()));
        // 없으면 없다.
        seen.next_actions[0].help_ref = None;
        assert_eq!(monitor_view_v1(&seen).expect("View").next_actions[0].help_ref, None);
    }

    #[test]
    fn the_next_actions_keep_the_order_the_read_model_chose() {
        let seen = with_every_action();
        let view = monitor_view_v1(&seen).expect("View");
        let inner: Vec<&str> = seen
            .next_actions
            .iter()
            .map(|one| match one.kind {
                ActionKind::CloseStep(_) => "close_step",
                ActionKind::OpenStep(_) => "open_step",
                ActionKind::CloseCycle(_) => "close_cycle",
                ActionKind::OpenCycle(_) => "open_cycle",
                ActionKind::OpenBranch(_) => "open_branch",
                ActionKind::Revisit => "revisit",
                ActionKind::Restore => "restore",
            })
            .collect();
        let wire: Vec<&str> = view.next_actions.iter().map(|one| one.kind.as_wire()).collect();
        assert_eq!(wire, inner, "차례가 바뀌었다");
        // 비어 있으면 빈 목록이다 — 사라지지 않는다.
        assert_eq!(monitor_view_v1(&reading_one()).expect("View").next_actions, vec![]);
    }

    #[test]
    fn the_wire_has_exactly_these_fields_and_no_others() {
        // **칸의 이름표를 통째로 센다.** 좌표나 선택 상태가 언젠가 끼어들면 이 목록이
        // 먼저 어긋난다 — 금지어를 찾는 것보다 확실하다(`summary:` 가 `y:` 를 품는 식의
        // 헛디딤도 없다).
        let printed = format!("{:?}", viewed());
        let mut seen = field_names(&printed);
        seen.sort_unstable();

        let allowed = [
            "action", "baseline_snapshot_ref", "captured_at_unix_ms", "command", "current",
            "current_will", "cycle_kind", "cycle_ref", "done_when", "existence_ref",
            "experiment_definition", "handoff_summary", "help_ref", "interview_question",
            "journey_ref", "kind",
            "next_action", "next_actions", "next_direction", "objective", "outcome_lesson",
            "parent_cycle_ref", "problem", "reason", "relation_to_current", "report",
            "question", "response",
            "revisit_from_cycle_ref", "schema_version", "state", "step_kind", "step_ref",
            "steps", "success_condition", "summary", "target_cycle_ref", "target_step_ref",
            "timeline", "verdict", "verify_can_confirm", "will_ref", "world",
        ];
        for name in &seen {
            assert!(allowed.contains(name), "View 에 모르는 칸 {name:?} 이 생겼다");
        }
        // 좌표·표현 상태·내부 중복 목록의 이름이 하나도 없다.
        for forbidden in [
            "x", "y", "lane", "width", "height", "svg", "path", "css", "class",
            "selected", "collapsed", "filter", "viewport", "zoom", "active_lineage",
            "inactive_cycles",
        ] {
            assert!(!seen.contains(&forbidden), "{forbidden:?} 칸이 생겼다");
        }
    }

    /// `Debug` 글에서 `이름: ` 꼴의 칸 이름만 뽑는다.
    fn field_names(printed: &str) -> Vec<&str> {
        let bytes = printed.as_bytes();
        let mut names: Vec<&str> = Vec::new();
        let mut at = 0usize;
        while let Some(found) = printed[at..].find(": ") {
            let end = at + found;
            let mut start = end;
            while start > 0 && (bytes[start - 1].is_ascii_alphanumeric() || bytes[start - 1] == b'_')
            {
                start -= 1;
            }
            let name = &printed[start..end];
            if !name.is_empty() && !names.contains(&name) {
                names.push(name);
            }
            at = end + 2;
        }
        names
    }
}

#[cfg(test)]
mod boundary {
    //! **serde 계약이 어디까지인가.**
    //!
    //! 내부 `MonitorSnapshot` 과 domain 타입에 직렬화를 붙이지 않는 것이 이 판의 전제다.
    //! 붙는 순간 안쪽을 고칠 때마다 바깥이 깨지고, 그러면 판 번호가 지킬 것이 없어진다.

    /// 그 소스에서 **실제 파생**만 훑는다 — 주석에 적힌 낱말은 세지 않는다.
    fn derives_serialize(source: &str) -> bool {
        source
            .lines()
            .map(str::trim)
            .filter(|line| line.starts_with("#[derive(") || line.starts_with("#["))
            .any(|line| line.contains("Serialize") || line.contains("Deserialize"))
    }

    #[test]
    fn the_internal_read_model_has_no_serde_contract() {
        assert!(
            !derives_serialize(include_str!("mod.rs")),
            "내부 read model 에 serde 파생이 생겼다"
        );
        // 그리고 View 쪽에는 있다 — 경계가 실제로 그어져 있다는 증거다.
        assert!(
            derives_serialize(include_str!("view.rs")),
            "View 에 계약이 없다 — 이 시험이 아무것도 재지 않는다"
        );
    }

    #[test]
    fn the_domain_types_that_the_view_names_have_no_serialize() {
        // `Deserialize` 는 문법을 읽으려고 이미 붙어 있다(`NodeKind` 등). 여기서 막는 것은
        // **`Serialize`** 다 — 그것이 붙는 순간 domain 타입이 곧 wire 가 된다.
        for (name, source) in [
            ("cycle.rs", include_str!("../cycle.rs")),
            ("node.rs", include_str!("../node.rs")),
            ("refs.rs", include_str!("../refs.rs")),
            ("report.rs", include_str!("../report.rs")),
        ] {
            let derived = source
                .lines()
                .map(str::trim)
                .filter(|line| line.starts_with("#["))
                .any(|line| line.contains("Serialize"));
            assert!(!derived, "{name} 의 domain 타입에 Serialize 가 생겼다");
        }
    }
}
