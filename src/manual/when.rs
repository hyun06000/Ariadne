//! `applies_when` — **검색식이 아니라 유한한 표지다.**
//!
//! 코어가 이미 판정해 둔 값만 쓴다(Manual Model §6). 임의 query 도, 정규식도, 표현식
//! 언어도, LLM 판정도 만들지 않는다 — 그런 것을 만드는 순간 Manual 이 **두 번째 전이
//! 엔진**이 되고, 코어와 다른 답을 말하기 시작한다.
//!
//! ```text
//! project                present · absent
//! cycle_kind             interview · experiment
//! cycle_status           open · closed
//! step_kind              question · … · analysis · none
//! step_status            open · closed · none
//! world_state            clean · dirty · unknown
//! artifact_confirmation  verify · unavailable
//! ```
//!
//! 적힌 조건만 **AND** 로 잰다. 모르는 key·모르는 값·문자열이 아닌 값은 index 를 세울 때
//! 거절한다 — 무시하거나 truthiness 로 다루면 아무 상태에나 붙는 Topic 이 생긴다.
//!
//! # 없는 것과 비어 있는 것은 다르다
//!
//! ```text
//! applies_when 필드 없음   모든 상태에 적용된다
//! applies_when: {}         실수다 — 거절한다
//! ```
//!
//! 빈 map 은 「모든 상태」를 적으려다 만 것이거나 조건을 지우다 만 것이다. 둘 다 사람이
//! 다시 봐야 할 자국이지 뜻이 아니다.

use std::fmt;

use crate::cycle::CycleKind;
use crate::node::{NodeKind, NodeStatus};

/// 프로젝트를 찾았는가.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Presence {
    Present,
    Absent,
}

/// 작업 폴더가 기준 세계와 어떤 관계인가 — [`WorldState`](crate::WorldState) 의 표지.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum WorldMark {
    Clean,
    Dirty,
    Unknown,
}

/// 지금 자리에서 Artifact 변경을 확정할 수 있는가.
///
/// **별도의 권한 규칙을 만들지 않는다.** 코어의 Verify 판정 하나를 그대로 옮긴 표지다.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Confirmation {
    /// 열린 Verify 다 — 닫으면 확정된다.
    Verify,
    /// 그 밖의 모든 자리.
    Unavailable,
}

/// 조건 하나. **값까지 타입이 진다** — 문자열 비교가 남지 않는다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum Condition {
    Project(Presence),
    CycleKind(CycleKind),
    CycleStatus(NodeStatus),
    /// `none` 은 **Cycle 경계**라는 뜻이다 — 「모른다」가 아니다.
    StepKind(Option<NodeKind>),
    StepStatus(Option<NodeStatus>),
    World(WorldMark),
    Confirmation(Confirmation),
}

impl Condition {
    /// key 와 값을 조건으로 읽는다.
    pub(crate) fn parse(key: &str, value: &str) -> Result<Condition, WhenError> {
        let unknown = || WhenError::UnknownValue {
            key: key.to_string(),
            value: value.to_string(),
        };
        match key {
            "project" => match value {
                "present" => Ok(Condition::Project(Presence::Present)),
                "absent" => Ok(Condition::Project(Presence::Absent)),
                _ => Err(unknown()),
            },
            "cycle_kind" => CycleKind::parse(value).map(Condition::CycleKind).ok_or_else(unknown),
            "cycle_status" => status(value).map(Condition::CycleStatus).ok_or_else(unknown),
            "step_kind" => match value {
                "none" => Ok(Condition::StepKind(None)),
                // **경계 표식은 자리가 아니다.** `cycle_entry`·`cycle_exit` 은 열고 닫는
                // 대상이 아니므로 여기 올 수 없다.
                _ => NodeKind::parse(value)
                    .filter(|kind| !kind.is_boundary())
                    .map(|kind| Condition::StepKind(Some(kind)))
                    .ok_or_else(unknown),
            },
            "step_status" => match value {
                "none" => Ok(Condition::StepStatus(None)),
                _ => status(value)
                    .map(|found| Condition::StepStatus(Some(found)))
                    .ok_or_else(unknown),
            },
            "world_state" => match value {
                "clean" => Ok(Condition::World(WorldMark::Clean)),
                "dirty" => Ok(Condition::World(WorldMark::Dirty)),
                "unknown" => Ok(Condition::World(WorldMark::Unknown)),
                _ => Err(unknown()),
            },
            "artifact_confirmation" => match value {
                "verify" => Ok(Condition::Confirmation(Confirmation::Verify)),
                "unavailable" => Ok(Condition::Confirmation(Confirmation::Unavailable)),
                _ => Err(unknown()),
            },
            _ => Err(WhenError::UnknownKey {
                key: key.to_string(),
            }),
        }
    }

    /// 지금 상태가 이 조건을 만족하는가.
    pub(crate) fn holds(&self, here: &ManualContext) -> bool {
        match self {
            Condition::Project(want) => here.project == *want,
            // 프로젝트 밖에서는 **아무것도 모른다.** 「없다」가 아니라 「알 수 없다」이므로
            // 어떤 조건도 만족하지 않는다.
            Condition::CycleKind(want) => here.inside().is_some_and(|at| at.cycle_kind == *want),
            Condition::CycleStatus(want) => {
                here.inside().is_some_and(|at| at.cycle_status == *want)
            }
            Condition::StepKind(want) => here
                .inside()
                .is_some_and(|at| at.step.map(|(kind, _)| kind) == *want),
            Condition::StepStatus(want) => here
                .inside()
                .is_some_and(|at| at.step.map(|(_, status)| status) == *want),
            Condition::World(want) => here.inside().is_some_and(|at| at.world == *want),
            Condition::Confirmation(want) => {
                here.inside().is_some_and(|at| at.confirmation == *want)
            }
        }
    }
}

fn status(value: &str) -> Option<NodeStatus> {
    match value {
        "open" => Some(NodeStatus::Open),
        "closed" => Some(NodeStatus::Closed),
        _ => None,
    }
}

// ── 지금 상태 ──────────────────────────────────────────────────────────────

/// Topic 을 고르는 데 쓰는 **한 번 읽은 상태.**
///
/// 저장되는 도메인 객체가 아니라 읽기 전용 투영이다. `gil help` 한 번에 하나를 만들고,
/// Topic 을 재는 동안 **다시 읽지 않는다** — Topic 마다 프로젝트를 다시 관측하면 네 Topic 에
/// 네 번 폴더를 훑게 된다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ManualContext {
    project: Presence,
    /// 프로젝트 안에서만 아는 것들. 밖이면 `None`.
    inside: Option<Inside>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Inside {
    pub(crate) cycle_kind: CycleKind,
    pub(crate) cycle_status: NodeStatus,
    /// 열려 있든 닫혀 있든 **지금 서 있는 자리**. Cycle 경계면 `None`.
    pub(crate) step: Option<(NodeKind, NodeStatus)>,
    pub(crate) world: WorldMark,
    pub(crate) confirmation: Confirmation,
}

impl ManualContext {
    /// 프로젝트를 찾지 못한 자리.
    pub(crate) fn outside() -> ManualContext {
        ManualContext {
            project: Presence::Absent,
            inside: None,
        }
    }

    pub(crate) fn inside(&self) -> Option<&Inside> {
        self.inside.as_ref()
    }

    pub(crate) fn within(at: Inside) -> ManualContext {
        ManualContext {
            project: Presence::Present,
            inside: Some(at),
        }
    }
}

// ── 오류 ───────────────────────────────────────────────────────────────────

/// `applies_when` 이 표지가 아닌 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum WhenError {
    /// `applies_when: {}` — 조건을 적으려다 만 자국이다.
    Empty,
    UnknownKey { key: String },
    UnknownValue { key: String, value: String },
    /// 값이 글자가 아니다.
    NotText { key: String },
}

impl fmt::Display for WhenError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            WhenError::Empty => write!(
                f,
                "applies_when 이 비어 있다 — 모든 상태에 적용하려면 그 필드를 아예 적지 않는다"
            ),
            WhenError::UnknownKey { key } => write!(
                f,
                "{key:?} 는 이 gil 이 아는 상태 표지가 아니다 — 표지는 코어가 이미 판정한 \
                 것뿐이다"
            ),
            WhenError::UnknownValue { key, value } => {
                write!(f, "{key} 가 {value:?} 라는데 그런 값은 없다")
            }
            WhenError::NotText { key } => {
                write!(f, "{key} 의 값이 글자가 아니다 — 표지는 언제나 글자다")
            }
        }
    }
}

impl std::error::Error for WhenError {}

// ── 시험 ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn at(step: Option<(NodeKind, NodeStatus)>, world: WorldMark) -> ManualContext {
        let confirmation = match step {
            Some((NodeKind::Verify, NodeStatus::Open)) => Confirmation::Verify,
            _ => Confirmation::Unavailable,
        };
        ManualContext::within(Inside {
            cycle_kind: CycleKind::Experiment,
            cycle_status: NodeStatus::Open,
            step,
            world,
            confirmation,
        })
    }

    #[test]
    fn every_key_and_value_the_model_lists_is_read() {
        for (key, value) in [
            ("project", "present"),
            ("project", "absent"),
            ("cycle_kind", "interview"),
            ("cycle_kind", "experiment"),
            ("cycle_status", "open"),
            ("cycle_status", "closed"),
            ("step_kind", "question"),
            ("step_kind", "interpretation"),
            ("step_kind", "synthesis"),
            ("step_kind", "outcome"),
            ("step_kind", "define"),
            ("step_kind", "hypothesis"),
            ("step_kind", "verify"),
            ("step_kind", "analysis"),
            ("step_kind", "none"),
            ("step_status", "open"),
            ("step_status", "closed"),
            ("step_status", "none"),
            ("world_state", "clean"),
            ("world_state", "dirty"),
            ("world_state", "unknown"),
            ("artifact_confirmation", "verify"),
            ("artifact_confirmation", "unavailable"),
        ] {
            Condition::parse(key, value)
                .unwrap_or_else(|err| panic!("{key}: {value} — {err}"));
        }
    }

    #[test]
    fn a_key_this_gil_does_not_know_is_refused() {
        for key in ["existence", "will", "snapshot", "kind", ""] {
            assert_eq!(
                Condition::parse(key, "present").unwrap_err(),
                WhenError::UnknownKey {
                    key: key.to_string()
                }
            );
        }
    }

    #[test]
    fn a_value_this_gil_does_not_know_is_refused() {
        // **문자열 truthiness 로 다루지 않는다.** 모르는 값은 아무 상태에나 붙지 않는다.
        for (key, value) in [
            ("project", "yes"),
            ("project", "true"),
            ("cycle_kind", "chain"),
            ("cycle_status", "open "),
            ("step_kind", "cycle_entry"),
            ("step_kind", "cycle_exit"),
            ("step_kind", "verify!"),
            ("step_status", "opened"),
            ("world_state", "not_verify"),
            ("artifact_confirmation", "yes"),
        ] {
            assert_eq!(
                Condition::parse(key, value).unwrap_err(),
                WhenError::UnknownValue {
                    key: key.to_string(),
                    value: value.to_string(),
                },
                "{key}: {value:?}"
            );
        }
    }

    #[test]
    fn outside_a_project_nothing_but_the_project_marker_can_match() {
        let outside = ManualContext::outside();
        assert!(Condition::parse("project", "absent").unwrap().holds(&outside));
        assert!(!Condition::parse("project", "present").unwrap().holds(&outside));

        // **「없다」가 아니라 「알 수 없다」다.** 밖에서는 자리도 세계도 모른다.
        for (key, value) in [
            ("step_kind", "none"),
            ("step_status", "none"),
            ("world_state", "clean"),
            ("world_state", "unknown"),
            ("cycle_kind", "interview"),
            ("artifact_confirmation", "unavailable"),
        ] {
            assert!(
                !Condition::parse(key, value).unwrap().holds(&outside),
                "프로젝트 밖에서 {key}: {value} 가 맞다고 했다"
            );
        }
    }

    #[test]
    fn a_cycle_boundary_is_a_step_kind_of_none() {
        let boundary = at(None, WorldMark::Dirty);
        assert!(Condition::parse("step_kind", "none").unwrap().holds(&boundary));
        assert!(Condition::parse("step_status", "none").unwrap().holds(&boundary));
        assert!(!Condition::parse("step_kind", "verify").unwrap().holds(&boundary));

        let standing = at(Some((NodeKind::Verify, NodeStatus::Open)), WorldMark::Dirty);
        assert!(!Condition::parse("step_kind", "none").unwrap().holds(&standing));
        assert!(Condition::parse("step_kind", "verify").unwrap().holds(&standing));
    }

    #[test]
    fn confirmation_follows_the_open_verify_and_nothing_else() {
        let verify = at(Some((NodeKind::Verify, NodeStatus::Open)), WorldMark::Dirty);
        assert!(
            Condition::parse("artifact_confirmation", "verify")
                .unwrap()
                .holds(&verify)
        );

        // 닫힌 Verify 도, 그 밖의 Kind 도, 경계도 전부 unavailable 이다.
        for step in [
            Some((NodeKind::Verify, NodeStatus::Closed)),
            Some((NodeKind::Define, NodeStatus::Open)),
            Some((NodeKind::Question, NodeStatus::Open)),
            None,
        ] {
            let here = at(step, WorldMark::Dirty);
            assert!(
                Condition::parse("artifact_confirmation", "unavailable")
                    .unwrap()
                    .holds(&here),
                "{step:?}"
            );
        }
    }

    #[test]
    fn unknown_is_not_dirty() {
        let cannot_tell = at(Some((NodeKind::Define, NodeStatus::Open)), WorldMark::Unknown);
        assert!(!Condition::parse("world_state", "dirty").unwrap().holds(&cannot_tell));
        assert!(!Condition::parse("world_state", "clean").unwrap().holds(&cannot_tell));
        assert!(Condition::parse("world_state", "unknown").unwrap().holds(&cannot_tell));
    }
}
