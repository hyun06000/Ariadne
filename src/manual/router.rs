//! 오류가 Manual 의 router 다 — **거절 하나가 복구 Topic 하나를 가리킨다.**
//!
//! ```text
//! Domain 오류        사실과 까닭만 지닌다
//!     ↓
//! Help Router        공개 거절을 복구 Topic 으로 대응한다   ← 여기
//!     ↓
//! Option<TopicId>
//!     ↓
//! Renderer           대응이 있을 때만 짧은 한 줄을 더한다
//! ```
//!
//! # 오류가 Manual 을 소유하지 않는다
//!
//! `SessionError::Dirty { help_topic }` 같은 꼴을 만들지 않는다. 그렇게 하면 도메인이
//! 문서를 알게 되고, Topic 주소를 바꾸는 일이 도메인 타입을 고치는 일이 된다.
//!
//! 대응표는 **여기 한 자리**에 있다. 여러 파일로 흩어지면 어느 오류가 어디를 가리키는지
//! 아무도 한눈에 못 본다.
//!
//! # 이름을 자동 변환하지 않는다
//!
//! 내부 error variant 이름을 Topic 주소로 옮기지 않는다(Manual Model §9). 오류 문구가
//! 바뀌어도 주소의 뜻은 그대로여야 하고, 그러려면 둘이 **따로** 정해져야 한다.
//!
//! 그리고 **문자열을 뒤져 고르지 않는다.** typed 구조만 본다 — 메시지 한 글자를 다듬는 일이
//! 링크를 끊는 일이 되면, 아무도 메시지를 못 고친다.

use crate::cycle::{CycleError, CycleKind};
use crate::cycles::{CycleRevisitError, OpenAfterRevisitError};
use crate::node::NodeKind;
use crate::project::ActionError;
use crate::session::{Gate, SessionError};
use crate::validate::{GrammarError, Subject};
use crate::walk::WalkError;
use crate::will::ContractError;

use super::TopicId;
#[cfg(test)]
use super::Manual;

/// Router 가 돌려줄 수 있는 **모든** 주소.
///
/// 한 자리에 모아 둔다 — Topic 주소가 바뀌면 [`tests::every_reachable_topic_exists`] 가
/// 먼저 빨개진다. 런타임에 조용히 링크를 빼는 것으로 끝내지 않는다(§5).
#[cfg(test)]
const REACHABLE: &[&str] = &[
    DIRTY_NON_VERIFY,
    VERIFY_CLOSE,
    RESTORE,
    OPEN_CONTRACT,
    EXPERIMENT_CLOSE,
    CYCLE_REVISIT,
    REVISIT_TARGET,
];

const DIRTY_NON_VERIFY: &str = "artifact/dirty/non-verify";
const VERIFY_CLOSE: &str = "step/verify/close";
const RESTORE: &str = "artifact/restore";
const OPEN_CONTRACT: &str = "action/open-contract";
const EXPERIMENT_CLOSE: &str = "cycle/experiment/close";
const CYCLE_REVISIT: &str = "cycle/revisit";
const REVISIT_TARGET: &str = "cycle/revisit/target";

/// Router 가 보는 **공개 거절**.
///
/// Domain 명령을 만들기 전에 CLI 가 거절하는 자리도 여기 온다 — 그런 거절도 사람이
/// 복구해야 하는 것은 같다.
#[derive(Debug)]
pub enum Refusal<'a> {
    Session(&'a SessionError),
    /// 실행형 자리를 열며 낸 **행동 계약**이 계약이 아니었다.
    ///
    /// 이 오류는 Domain 이 서기 전에 난다. 그래도 **어느 자리인지 typed 하게 안다** —
    /// 계약을 읽는 자리는 실행형 Step open 하나뿐이기 때문이다.
    Contract(&'a ContractError),
    Usage(Usage),
}

/// Domain 이 서기 전에 CLI 가 거절한 자리.
///
/// **모든 parser 오류를 여기 담지 않는다.** 담는 것은 Topic 하나로 복구되는 사용법
/// 오류뿐이다 — 모르는 명령이나 잘못된 Topic 주소는 읽을 Topic 이 따로 없다.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Usage {
    /// `gil restore` 에 허용되지 않은 인수를 주었다.
    RestoreTakesNoArgument,
    /// `gil revisit` 에 허용되지 않은 인수를 주었다.
    RevisitTakesNoArgument,
}

/// 이 거절을 복구하는 Topic 하나. 없으면 `None`.
///
/// # 순수하다
///
/// 파일을 읽지 않고, Project·Session·Graph 를 다시 읽지 않고, 잠금을 잡지 않고, Topic
/// 본문을 펴지 않는다. **이미 일어난 typed 오류만** 본다 — dirty 거절에서 어느 Topic 인지
/// 고르려고 `world_state()` 를 다시 부르지 않는다는 뜻이다. 그 정보는 오류의 `gate` 에
/// 이미 실려 있다.
///
/// 오류 하나에 Topic 은 **최대 하나**다.
pub(crate) fn help_for(refusal: &Refusal<'_>) -> Option<TopicId> {
    let address = match refusal {
        // ── CLI 사용법 ────────────────────────────────────────────────────
        Refusal::Usage(Usage::RestoreTakesNoArgument) => RESTORE,
        Refusal::Usage(Usage::RevisitTakesNoArgument) => CYCLE_REVISIT,

        // ── 행동 계약이 없거나 비었다 ─────────────────────────────────────
        //
        // Kind 선택 오류·전이 오류·이미 열린 자리는 여기 오지 않는다. 그것들은 계약을
        // 읽기도 전에 다른 자리에서 거절된다.
        Refusal::Contract(ContractError::Missing { .. }) => OPEN_CONTRACT,

        // ── 세계를 확정할 수 없는 자리에서 닫으려 함 ──────────────────────
        //
        // 열린 Verify 는 제외한다 — 거기서는 확정이 정상 경로다. (지금 구조에서는 그
        // gate 가 서지 않지만, 규칙을 코드에도 적어 둔다.)
        Refusal::Session(SessionError::Dirty { gate, .. }) => match gate {
            Gate::Step(_, NodeKind::Verify) => return None,
            Gate::Step(..) | Gate::Cycle(_) => DIRTY_NON_VERIFY,
        },

        // ── Experiment Cycle 을 닫으려다 Report 가 거절됐다 ───────────────
        //
        // **Interview 는 오지 않는다.** 두 Cycle 은 요구하는 칸도 허용값도 다르므로 한
        // Topic 으로 뭉뚱그리면 읽는 쪽이 남의 규칙을 배운다.
        Refusal::Session(SessionError::Action(ActionError::CycleReport { kind, source })) => {
            match (*kind == CycleKind::Experiment) && cycle_report(source) {
                true => EXPERIMENT_CLOSE,
                false => return None,
            }
        }

        // ── 되돌아갈 곳이 없거나 잘못 적혔다 ──────────────────────────────
        //
        // Cycle Report 의 **그 한 칸**의 문제다. `cycle/experiment/close` 는 Report 전체를
        // 말하므로, 이미 나머지를 옳게 적은 사람에게는 그 칸 하나가 정확하다.
        Refusal::Session(SessionError::Action(ActionError::CycleDirection { .. })) => {
            REVISIT_TARGET
        }

        // ── 되돌아감을 밟을 수 없다 ───────────────────────────────────────
        //
        // 적어 둔 갈 곳이 성립하지 않는 것만 target Topic 으로 간다. 그 밖(열려 있다·
        // 방향이 아니다·이미 되돌아왔다)은 **사용법**의 문제이므로 revisit Topic 이다.
        Refusal::Session(SessionError::Revisit(source)) => match source {
            CycleRevisitError::NextDirection(_) => REVISIT_TARGET,
            _ => CYCLE_REVISIT,
        },

        // ── 되돌아온 자리에서 갈래를 열지 못했다 ──────────────────────────
        Refusal::Session(SessionError::Branch(source)) => match source {
            OpenAfterRevisitError::NextDirection(_) => REVISIT_TARGET,
            _ => CYCLE_REVISIT,
        },

        // ── 되돌아가려는데 폴더가 dirty ───────────────────────────────────
        //
        // **되돌아감의 문제로 말한다.** `artifact/dirty/non-verify` 는 「이 Step 에서는
        // 확정할 수 없다」는 자리의 글이라 여기서는 남의 규칙이다 — 여기엔 닫을 Step 이
        // 없고, 되돌린 뒤 할 일도 `gil close` 가 아니라 `gil revisit` 이다.
        Refusal::Session(SessionError::RevisitNeedsCleanWorld { .. }) => CYCLE_REVISIT,

        // ── 되돌아온 자리라 Graph 를 바꿀 수 없다 ─────────────────────────
        Refusal::Session(SessionError::Action(ActionError::RevisitPending { .. })) => {
            CYCLE_REVISIT
        }

        // ── Verify Report 가 지금 Grammar 와 맞지 않음 ────────────────────
        //
        // **Verify 를 닫는 자리일 때만.** Analysis·Outcome 의 Report 오류를 같은 Topic 으로
        // 뭉뚱그리지 않는다. 관측 실패·창고 손상·잠금 경쟁도 여기 오지 않는다.
        Refusal::Session(SessionError::Action(action)) => match verify_report(action) {
            true => VERIFY_CLOSE,
            false => return None,
        },

        // ── 나머지는 붙이지 않는다 ────────────────────────────────────────
        //
        // 잠금 경쟁·프로젝트 없음·format 불일치·손상·rollback/recovery 실패·모르는 내부
        // 항목·관측 실패. **Topic 이 없다는 것은 문서가 부족하다는 뜻이 아니다** —
        // 부정확한 링크를 붙이지 않는 것이 먼저다(§3).
        Refusal::Session(_) => return None,
    };
    TopicId::parse(address).ok()
}

/// 이 거절이 **Verify 를 닫으려다 난 Report 계약 오류**인가.
fn verify_report(action: &ActionError) -> bool {
    let ActionError::Cycle(cycle) = action else {
        return false;
    };
    let grammar = match cycle {
        CycleError::Step(WalkError::Grammar(grammar)) => grammar,
        // Cycle Report 의 문법 오류는 Step 의 것이 아니다.
        _ => return false,
    };
    subject(grammar) == Some(Subject::Step(NodeKind::Verify))
}

/// 이 거절이 **Cycle Report 자체의 계약 오류**인가.
///
/// 아직 끝 경계에 닿지 않았다거나 이미 닫혔다는 것은 Report 의 문제가 아니다 — 그때 읽어야
/// 할 것은 「어떻게 적는가」가 아니라 「지금 여기가 아니다」이다.
fn cycle_report(source: &CycleError) -> bool {
    match source {
        // 칸이 없거나 값이 문법과 다르다.
        CycleError::Grammar(_) => true,
        // `outcome_ref` 가 이 Cycle 의 마지막 판정을 가리키지 않는다.
        CycleError::OutcomeRef(_) => true,
        CycleError::Step(_)
        | CycleError::AlreadyClosed
        | CycleError::StepsNotDone
        | CycleError::SynthesisRef(_)
        | CycleError::BasisRefs(_) => false,
    }
}

/// 그 문법 오류가 **어느 자리의 Report** 를 말하는가.
///
/// 자리를 말하지 않는 전이 오류(`ParentNotClosed` 등)는 Report 계약 오류가 아니다.
fn subject(grammar: &GrammarError) -> Option<Subject> {
    match grammar {
        GrammarError::MissingReportFields { subject, .. }
        | GrammarError::EmptyReportField { subject, .. }
        | GrammarError::FieldValueNotYetBuilt { subject, .. }
        | GrammarError::FieldValueNotAllowed { subject, .. } => Some(*subject),
        GrammarError::UnknownStepKind(_)
        | GrammarError::UnknownCycleKind(_)
        | GrammarError::ParentNotClosed { .. }
        | GrammarError::TransitionNotAllowed { .. } => None,
    }
}

// ── 렌더 ───────────────────────────────────────────────────────────────────

/// 거절 뒤에 붙는 **한 줄짜리 다음 문**. 대응이 없으면 아무것도 붙이지 않는다.
///
/// ```text
/// 더 알아보기
///   gil help artifact/dirty/non-verify
/// ```
///
/// Topic 의 요약도 본문도 함께 붙이지 않는다. 여러 후보를 늘어놓지도 않는다 — 읽어야 할
/// 것이 셋이면 사람은 셋 다 안 읽는다.
///
/// `said` 는 이미 지어진 오류 본문이다. 같은 문이 거기 이미 있으면 **되풀이하지 않는다.**
pub fn more_about(refusal: &Refusal<'_>, said: &str) -> Option<String> {
    let topic = help_for(refusal)?;
    let line = format!("gil help {topic}");
    match said.contains(&line) {
        true => None,
        false => Some(format!("\n더 알아보기\n  {line}\n")),
    }
}

/// 오류 본문 뒤에 [`more_about`] 을 붙인 글.
pub fn with_help(refusal: &Refusal<'_>, said: String) -> String {
    match more_about(refusal, &said) {
        Some(more) => {
            let mut out = said;
            if !out.ends_with('\n') {
                out.push('\n');
            }
            out.push_str(&more);
            out
        }
        None => said,
    }
}

// ── 시험 ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cycle::CycleKind;
    use crate::refs::{CycleRef, StepRef};

    fn step(kind: NodeKind) -> Gate {
        let cycle = CycleRef::new(1).expect("Cycle 주소");
        Gate::Step(StepRef::new(cycle, 1).expect("자리 주소"), kind)
    }

    fn dirty(gate: Gate) -> SessionError {
        SessionError::Dirty {
            gate,
            world: crate::refs::SnapshotRef::new(1).expect("세계 이름"),
            changes: Vec::new(),
        }
    }

    fn report_error(subject: Subject) -> SessionError {
        SessionError::Action(ActionError::Cycle(CycleError::Step(WalkError::Grammar(
            GrammarError::MissingReportFields {
                subject,
                missing: vec!["execution".to_string()],
            },
        ))))
    }

    fn topic_of(error: &SessionError) -> Option<String> {
        help_for(&Refusal::Session(error)).map(|id| id.to_string())
    }

    #[test]
    fn every_reachable_topic_exists_in_the_bundled_manual() {
        // **배포 전에 빨개진다.** Manual source 에서 주소를 바꾸면 여기서 걸린다 —
        // 런타임에 조용히 링크를 빼는 것으로 끝내지 않는다.
        let manual = Manual::bundled().expect("함께 실린 Manual");
        for address in REACHABLE {
            let id = TopicId::parse(address)
                .unwrap_or_else(|err| panic!("{address:?} 가 주소가 아니다: {err}"));
            assert!(
                manual.resolve(&id).is_some(),
                "{address} 를 가리키는데 그런 Topic 이 없다"
            );
        }
    }

    #[test]
    fn a_place_that_cannot_confirm_points_at_the_recovery_topic() {
        // Interview 의 넷, Experiment 의 넷, 그리고 **자리가 없는 Cycle 경계**.
        for kind in [
            NodeKind::Question,
            NodeKind::Interpretation,
            NodeKind::Synthesis,
            NodeKind::Define,
            NodeKind::Hypothesis,
            NodeKind::Analysis,
            NodeKind::Outcome,
        ] {
            assert_eq!(
                topic_of(&dirty(step(kind))).as_deref(),
                Some(DIRTY_NON_VERIFY),
                "{kind}"
            );
        }
        assert_eq!(
            topic_of(&dirty(Gate::Cycle(CycleRef::new(1).expect("Cycle 주소")))).as_deref(),
            Some(DIRTY_NON_VERIFY)
        );
    }

    #[test]
    fn an_open_verify_is_not_sent_to_the_recovery_topic() {
        // 거기서는 확정이 정상 경로다.
        assert_eq!(topic_of(&dirty(step(NodeKind::Verify))), None);
    }

    #[test]
    fn a_verify_report_contract_error_points_at_the_verify_topic() {
        assert_eq!(
            topic_of(&report_error(Subject::Step(NodeKind::Verify))).as_deref(),
            Some(VERIFY_CLOSE)
        );
    }

    #[test]
    fn another_kinds_report_error_is_not_the_verify_topic() {
        // Analysis·Outcome 의 Report 오류를 같은 Topic 으로 뭉뚱그리지 않는다.
        for kind in [
            NodeKind::Analysis,
            NodeKind::Outcome,
            NodeKind::Define,
            NodeKind::Question,
        ] {
            assert_eq!(topic_of(&report_error(Subject::Step(kind))), None, "{kind}");
        }
        // Cycle Report 오류도 아니다.
        assert_eq!(
            topic_of(&report_error(Subject::Cycle(CycleKind::Experiment))),
            None
        );
    }

    #[test]
    fn a_transition_error_is_not_a_report_contract_error() {
        // 자리를 말하지 않는 오류는 Report 계약 오류가 아니다.
        let moved = SessionError::Action(ActionError::Cycle(CycleError::Step(
            WalkError::Grammar(GrammarError::ParentNotClosed {
                parent: NodeKind::Hypothesis,
                child: NodeKind::Verify,
            }),
        )));
        assert_eq!(topic_of(&moved), None);
    }

    fn cycle_report_error(kind: CycleKind, source: CycleError) -> SessionError {
        SessionError::Action(ActionError::CycleReport { kind, source })
    }

    #[test]
    fn a_missing_action_contract_points_at_the_contract_topic() {
        for fields in [
            vec!["objective"],
            vec!["next_action"],
            vec!["done_when"],
            vec!["objective", "next_action", "done_when"],
        ] {
            let err = ContractError::Missing { fields };
            assert_eq!(
                help_for(&Refusal::Contract(&err)).map(|id| id.to_string()).as_deref(),
                Some(OPEN_CONTRACT)
            );
        }
    }

    #[test]
    fn an_experiment_cycle_report_error_points_at_its_own_topic() {
        for source in [
            CycleError::Grammar(GrammarError::MissingReportFields {
                subject: Subject::Cycle(CycleKind::Experiment),
                missing: vec!["verdict".to_string()],
            }),
            CycleError::Grammar(GrammarError::FieldValueNotAllowed {
                subject: Subject::Cycle(CycleKind::Experiment),
                field: "next_direction.action".to_string(),
                value: "open_child".to_string(),
                allowed: vec!["revisit".to_string()],
                narrowed_by: Some(("verdict".to_string(), "failure".to_string())),
            }),
            CycleError::OutcomeRef(crate::cycle::OutcomeRefError::NotTheLastOutcome {
                target: a_step(),
                expected: a_step(),
            }),
        ] {
            assert_eq!(
                topic_of(&cycle_report_error(CycleKind::Experiment, source)).as_deref(),
                Some(EXPERIMENT_CLOSE)
            );
        }
    }

    #[test]
    fn an_interview_cycle_report_error_is_not_the_experiment_topic() {
        // 두 Cycle 은 요구하는 칸도 허용값도 다르다.
        for source in [
            CycleError::Grammar(GrammarError::MissingReportFields {
                subject: Subject::Cycle(CycleKind::Interview),
                missing: vec!["verdict".to_string()],
            }),
            CycleError::OutcomeRef(crate::cycle::OutcomeRefError::NotTheLastOutcome {
                target: a_step(),
                expected: a_step(),
            }),
        ] {
            assert_eq!(topic_of(&cycle_report_error(CycleKind::Interview, source)), None);
        }
    }

    #[test]
    fn a_cycle_refusal_that_is_not_about_the_report_gets_no_topic() {
        // 「아직 끝 경계가 아니다」와 「이미 닫혔다」는 Report 를 어떻게 적는가의 문제가 아니다.
        for source in [
            CycleError::StepsNotDone,
            CycleError::AlreadyClosed,
            CycleError::Step(WalkError::NothingToClose),
        ] {
            assert_eq!(
                topic_of(&cycle_report_error(CycleKind::Experiment, source)),
                None
            );
        }
    }

    #[test]
    fn a_step_outcome_report_error_is_not_the_cycle_topic() {
        // Step 의 Outcome Report 오류를 Cycle close Topic 으로 보내지 않는다.
        assert_eq!(topic_of(&report_error(Subject::Step(NodeKind::Outcome))), None);
    }

    fn a_step() -> StepRef {
        StepRef::new(CycleRef::new(2).unwrap(), 5).unwrap()
    }

    #[test]
    fn restore_called_with_an_argument_points_at_the_restore_topic() {
        assert_eq!(
            help_for(&Refusal::Usage(Usage::RestoreTakesNoArgument))
                .map(|id| id.to_string())
                .as_deref(),
            Some(RESTORE)
        );
    }

    #[test]
    fn the_errors_that_get_no_topic_get_none() {
        // **부정확한 링크를 붙이지 않는 것이 먼저다.**
        for error in [
            SessionError::Busy {
                path: "/어딘가".to_string(),
            },
            SessionError::LockUnavailable {
                path: "/어딘가".to_string(),
                source: "…".to_string(),
            },
            SessionError::AlreadyStarted {
                path: "/어딘가".to_string(),
            },
            SessionError::LegacyFormat {
                path: "/어딘가".to_string(),
            },
            SessionError::NotEmpty {
                path: "/어딘가".to_string(),
                found: "누군가의파일".to_string(),
            },
            SessionError::NoProjectDir {
                path: "/어딘가".to_string(),
            },
            SessionError::Unreadable {
                path: "/어딘가".to_string(),
                source: "…".to_string(),
            },
            SessionError::Observe {
                said: "심볼릭 링크다".to_string(),
            },
            SessionError::Object {
                said: "손상됐다".to_string(),
            },
            SessionError::Manifest {
                world: crate::refs::SnapshotRef::new(1).unwrap(),
                said: "없다".to_string(),
            },
            SessionError::UnknownWorld {
                world: crate::refs::SnapshotRef::new(1).unwrap(),
            },
            SessionError::StrangeTemp {
                path: "/어딘가".to_string(),
            },
            SessionError::StrangeObjectStore {
                path: "/어딘가".to_string(),
                found: "누군가의폴더".to_string(),
            },
            // restore **실행** 실패는 사용법으로 복구되지 않는다 — 창고가 손상된 것이다.
            SessionError::Restore(crate::restore::RestoreFailure::Blob {
                world: crate::refs::SnapshotRef::new(1).unwrap(),
                path: "a.txt".to_string(),
                said: "없다".to_string(),
            }),
            SessionError::Restore(crate::restore::RestoreFailure::NotTheTargetWorld),
        ] {
            assert_eq!(topic_of(&error), None, "{error:?} 에 Topic 이 붙었다");
        }
    }

    #[test]
    fn the_router_never_reads_the_message() {
        // 문자열을 뒤져 고르지 않는다는 증거 — 본문이 무엇이든 판정이 같다.
        let mut said = dirty(step(NodeKind::Question));
        assert_eq!(topic_of(&said).as_deref(), Some(DIRTY_NON_VERIFY));
        if let SessionError::Dirty { changes, .. } = &mut said {
            changes.push("artifact/restore 라고 적힌 파일".to_string());
            changes.push("step/verify/close".to_string());
        }
        assert_eq!(
            topic_of(&said).as_deref(),
            Some(DIRTY_NON_VERIFY),
            "본문의 글자가 판정을 바꿨다"
        );
    }

    #[test]
    fn the_block_is_added_once_and_only_when_there_is_a_topic() {
        let error = dirty(step(NodeKind::Question));
        let refusal = Refusal::Session(&error);

        let said = with_help(&refusal, "거절: 무언가.\n".to_string());
        assert_eq!(said.matches("더 알아보기").count(), 1, "{said}");
        assert!(said.contains("gil help artifact/dirty/non-verify"), "{said}");

        // 같은 문이 이미 있으면 되풀이하지 않는다.
        let already = with_help(
            &refusal,
            "거절: 무언가.\n\n더 알아보기\n  gil help artifact/dirty/non-verify\n".to_string(),
        );
        assert_eq!(already.matches("더 알아보기").count(), 1, "{already}");

        // Topic 이 없으면 **빈 절을 만들지 않는다.**
        let busy = SessionError::Busy {
            path: "/어딘가".to_string(),
        };
        let plain = with_help(&Refusal::Session(&busy), "다른 GIL 명령이 …\n".to_string());
        assert!(!plain.contains("더 알아보기"), "{plain}");
        assert_eq!(plain, "다른 GIL 명령이 …\n");
    }
}
