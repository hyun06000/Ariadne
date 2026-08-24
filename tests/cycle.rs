//! Cycle 하나 — 안의 Outcome 이 닫혀도 아직 열려 있고, Cycle Report 를 써야 닫힌다.
//!
//! 여기서 재는 것은 셋이다.
//!
//! 1. **언제 닫을 수 있는가** — 안이 끝나기 전에는 못 닫는다.
//! 2. **무엇을 적어야 닫히는가** — 빠진 칸·어긋난 판정·좁혀진 방향.
//! 3. **닫힌 뒤에는 아무것도 안 움직인다.**
//!
//! 길은 코드에 적지 않는다 — 무엇이 필요한지는 `spec/gil-spec.yaml` 이 말한다.

use gil::{
    BasisRefError, Cycle, CycleError, CycleKind, GrammarError, NodeKind, NodeStatus,
    OutcomeRefError,
    Report, Subject,
};

mod common;
use common::{
    ACTION, bootstrap, cycle_allowed_here, cycle_report, cycle_step, full_report,
    graph_at_the_exit, spec,
};

/// 끝 경계에 닿은 Cycle 하나 — Cycle 층만 재려고 Graph 에서 떠 온다.
///
/// 이름을 발급하는 자리는 [`Cycles`] 뿐이라 Cycle 을 직접 만들지 않는다.
fn cycle_at_the_exit(verdict: &str) -> (Cycle, gil::NodeId) {
    let (project, outcome) = graph_at_the_exit(verdict);
    (project.cycles().current().clone(), outcome)
}

/// 걷기의 전부 — 거절된 연산 뒤에도 이것이 그대로여야 한다.
fn snapshot(cycle: &Cycle) -> (NodeStatus, Option<Report>, Vec<gil::StepNode>) {
    (
        cycle.status(),
        cycle.report().cloned(),
        cycle.steps().nodes().to_vec(),
    )
}

// ── 열림 ───────────────────────────────────────────────────────────────────

#[test]
fn a_new_cycle_is_one_open_experiment() {
    // 완료 조건 1.
    let cycle = bootstrap().cycles().current().clone();

    assert_eq!(cycle.kind(), CycleKind::Experiment);
    assert_eq!(cycle.status(), NodeStatus::Open);
    assert!(!cycle.is_closed());
    assert!(cycle.report().is_none(), "열려 있는데 Report 를 지녔다");
    assert!(cycle.steps().nodes().is_empty(), "안이 비어 있어야 한다");
    assert!(!cycle.can_close(), "아무것도 안 걸었는데 닫을 수 있다고 한다");
}

#[test]
fn the_only_cycle_kind_we_can_open_is_the_one_the_spec_declares() {
    // 명세가 규칙을 적어 둔 Kind 만 만들 수 있다 — 닫을 방법 없는 Cycle 을 열지 않는다.
    let rules = spec();
    for kind in CycleKind::ALL {
        assert!(
            rules.cycle_rules(kind).is_some(),
            "{kind} 를 닫는 규칙이 명세에 없다"
        );
    }
}

// ── 언제 닫을 수 있는가 ────────────────────────────────────────────────────

#[test]
fn a_cycle_does_not_close_before_its_outcome_does() {
    // 완료 조건 2 — 걷는 내내 한 번도 닫히면 안 된다.
    let mut cycle = bootstrap().cycles().current().clone();
    let report = cycle_report_shape(&cycle);

    assert_eq!(cycle.clone().close(report.clone()), Err(CycleError::StepsNotDone));

    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        cycle.open_step(kind).unwrap();
        assert!(!cycle.can_close(), "{kind} 를 연 채로 닫을 수 있다고 한다");
        assert_eq!(
            cycle.clone().close(report.clone()),
            Err(CycleError::StepsNotDone),
            "{kind} 를 연 채로 Cycle 이 닫혔다"
        );

        let step = full_report(cycle.rules(), cycle.kind(), kind);
        cycle.close_step(step).unwrap();
        assert!(!cycle.can_close(), "{kind} 뒤에서 닫을 수 있다고 한다");
    }

    // 판정을 **열기만** 해도 아직이다.
    cycle.open_step(NodeKind::Outcome).unwrap();
    assert!(!cycle.can_close(), "열린 판정 위에서 닫을 수 있다고 한다");
    assert_eq!(cycle.close(report), Err(CycleError::StepsNotDone));
}

#[test]
fn a_cycle_can_close_once_its_outcome_is_closed() {
    let (cycle, _) = cycle_at_the_exit("success");
    assert!(cycle.can_close(), "닫힌 판정 위에서도 못 닫는다고 한다");
    assert!(cycle.steps().at_exit());
}

/// 칸 이름만 맞춘 Cycle Report — 값은 아직 이 Cycle 과 안 맞을 수 있다.
fn cycle_report_shape(cycle: &Cycle) -> Report {
    common::full_cycle_report(cycle.rules(), CycleKind::Experiment)
        .with("outcome_ref", "1")
        .with("handoff_summary", "무엇이든")
        .with("next_direction.reason", "무엇이든")
}

// ── 무엇을 적어야 닫히는가 ─────────────────────────────────────────────────

#[test]
fn a_missing_field_is_named_one_by_one() {
    // 완료 조건 3 — 무엇이 빠졌는지 **그 칸의 이름**을 말해야 한다.
    let rules = spec();
    let required = rules
        .cycle_rules(CycleKind::Experiment)
        .unwrap()
        .close_requires
        .clone();
    assert!(!required.is_empty(), "잴 칸이 없다");

    for dropped in &required {
        let (mut cycle, outcome) = cycle_at_the_exit("success");
        let mut report = cycle_report(&cycle, "success", outcome);
        report.remove(dropped);

        let err = cycle
            .close(report)
            .expect_err("{dropped} 가 빠졌는데 닫혔다");
        match &err {
            CycleError::Grammar(GrammarError::MissingReportFields { subject, missing }) => {
                assert_eq!(*subject, Subject::Cycle(CycleKind::Experiment));
                assert_eq!(missing, &vec![dropped.clone()], "빠진 칸만 정확히 세야 한다");
            }
            other => panic!("거절 이유가 칸 누락이어야 한다: {other:?}"),
        }
        assert!(err.to_string().contains(dropped), "{err}");
        assert!(!cycle.is_closed(), "거절하고도 닫혔다");
    }
}

#[test]
fn a_field_that_must_not_be_empty_is_refused_when_empty() {
    let rules = spec();
    let constraints = &rules
        .cycle_rules(CycleKind::Experiment)
        .unwrap()
        .field_constraints;

    let mut checked = 0;
    for (field, constraint) in constraints {
        if !constraint.non_empty {
            continue;
        }
        let (mut cycle, outcome) = cycle_at_the_exit("success");
        let report = cycle_report(&cycle, "success", outcome).with(field.clone(), "   ");

        let err = cycle.close(report).expect_err("빈 값으로 닫혔다");
        assert!(
            matches!(
                err,
                CycleError::Grammar(GrammarError::EmptyReportField { .. })
            ),
            "{field} 가 다른 이유로 거절됐다: {err}"
        );
        checked += 1;
    }
    assert!(checked > 0, "비면 안 되는 칸이 명세에 없다");
}

/// 첫 판정이 `failure` 라 되돌아가고, 두 번째 판정이 `success` 인 Cycle.
///
/// 돌려주는 것은 (Cycle, **지나간** failure 판정, **마지막** success 판정).
fn cycle_with_two_outcomes() -> (Cycle, gil::NodeId, gil::NodeId) {
    let mut cycle = bootstrap().cycles().current().clone();
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        cycle_step(&mut cycle, kind);
    }
    let branch_point = cycle.steps().nodes()[3].id;

    // ① 첫 판정 — 못 풀었으니 해석으로 되돌아간다.
    cycle.open_step(NodeKind::Outcome).unwrap();
    let past = cycle.steps().current().unwrap();
    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", "failure")
        .with(ACTION, "revisit")
        .with(
            "next_direction.target_node_ref",
            cycle.step_ref(branch_point).to_string(),
        )
        .with("next_direction.reason", "다른 가설을 세운다");
    cycle.close_step(report).unwrap();
    cycle.revisit_step().unwrap();

    // ② 새 갈래를 끝까지 걷고 두 번째 판정을 success 로 닫는다.
    for kind in [NodeKind::Hypothesis, NodeKind::Verify, NodeKind::Analysis] {
        cycle_step(&mut cycle, kind);
    }
    cycle.open_step(NodeKind::Outcome).unwrap();
    let last = cycle.steps().current().unwrap();
    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", "success")
        .with(ACTION, "close_cycle")
        .with("next_direction.reason", "이번 갈래가 풀었다");
    cycle.close_step(report).unwrap();

    assert_ne!(past, last, "판정이 둘 나야 한다");
    (cycle, past, last)
}

#[test]
fn an_outcome_ref_must_point_at_the_last_outcome() {
    // 완료 조건 4 — 명세 §11: outcome_ref 는 **마지막** Outcome Report 를 가리키고,
    // 그 값은 `step:C1/S4` 꼴의 typed StepRef 다.
    let (cycle, outcome) = cycle_at_the_exit("success");
    let expected = cycle.step_ref(outcome);

    // ① 종류 없는 이름과 화면 축약은 주소가 아니다.
    for bare in ["4", "#4", "저기"] {
        let err = cycle
            .clone()
            .close(cycle_report(&cycle, "success", outcome).with("outcome_ref", bare))
            .unwrap_err_or_panic(&format!("{bare} 를 주소로 받았다"));
        assert!(
            matches!(
                err,
                CycleError::OutcomeRef(OutcomeRefError::Unreadable { .. })
            ),
            "{err}"
        );
        assert!(
            err.to_string().contains(&expected.to_string()),
            "무엇을 적어야 하는지 안 말한다: {err}"
        );
    }

    // ② 다른 Cycle 의 자리.
    let err = cycle
        .clone()
        .close(cycle_report(&cycle, "success", outcome).with("outcome_ref", "step:C9/S4"))
        .unwrap_err_or_panic("다른 Cycle 의 자리를 받았다");
    assert!(
        matches!(err, CycleError::OutcomeRef(OutcomeRefError::OtherCycle { .. })),
        "{err}"
    );

    // ③ 이 Cycle 에 없는 자리.
    let err = cycle
        .clone()
        .close(
            cycle_report(&cycle, "success", outcome)
                .with("outcome_ref", format!("step:{}/S99", cycle.id().to_ref().id())),
        )
        .unwrap_err_or_panic("없는 자리를 받았다");
    assert!(
        matches!(err, CycleError::OutcomeRef(OutcomeRefError::NotFound { .. })),
        "{err}"
    );

    // ④ 판정이 아닌 자리.
    let define = cycle.steps().nodes()[0].id;
    let err = cycle
        .clone()
        .close(
            cycle_report(&cycle, "success", outcome)
                .with("outcome_ref", cycle.step_ref(define).to_string()),
        )
        .unwrap_err_or_panic("판정이 아닌 자리를 받았다");
    match err {
        CycleError::OutcomeRef(OutcomeRefError::NotAnOutcome { kind, .. }) => {
            assert_eq!(kind, NodeKind::Define, "무엇이었는지 말해야 한다");
        }
        other => panic!("다른 이유로 거절됐다: {other}"),
    }

    // 어느 거절이든 **기대하는 그 주소**를 함께 말한다.
    for wrong in [
        "4".to_string(),
        "step:C9/S4".to_string(),
        cycle.step_ref(define).to_string(),
    ] {
        let err = cycle
            .clone()
            .close(cycle_report(&cycle, "success", outcome).with("outcome_ref", wrong.clone()))
            .unwrap_err_or_panic(&format!("{wrong} 이(가) 통과했다"));
        assert!(
            err.to_string().contains(&expected.to_string()),
            "마지막 판정의 주소를 안 말한다: {err}"
        );
    }
}

#[test]
fn a_past_outcome_cannot_judge_the_cycle() {
    // 완료 조건 4 의 본론 — 마지막이 success 인데 지나간 failure 로 Cycle 을 닫을 수 있으면
    // Cycle Report 가 제 안의 기록과 다른 말을 하게 된다.
    let (cycle, past, last) = cycle_with_two_outcomes();

    let err = cycle
        .clone()
        .close(cycle_report(&cycle, "failure", past))
        .unwrap_err_or_panic("지나간 판정으로 Cycle 이 닫혔다");
    match err {
        CycleError::OutcomeRef(OutcomeRefError::NotTheLastOutcome { target, expected }) => {
            assert_eq!(target, cycle.step_ref(past));
            assert_eq!(expected, cycle.step_ref(last), "마지막 판정을 틀리게 말한다");
        }
        other => panic!("다른 이유로 거절됐다: {other}"),
    }
    // 메시지가 둘을 함께 말해야 사람이 무엇을 고쳐야 할지 안다.
    let message = err.to_string();
    assert!(message.contains(&cycle.step_ref(past).to_string()), "{message}");
    assert!(message.contains(&cycle.step_ref(last).to_string()), "{message}");
}

#[test]
fn the_last_outcome_closes_the_cycle_with_its_own_verdict() {
    // 그리고 마지막 판정을 가리키면 닫힌다 — 갈래를 지나온 Cycle 이라도.
    let (mut cycle, _, last) = cycle_with_two_outcomes();
    let report = cycle_report(&cycle, "success", last);

    cycle.close(report.clone()).expect("마지막 판정이 거절됐다");

    assert!(cycle.is_closed());
    assert_eq!(cycle.report(), Some(&report));
    assert_eq!(cycle.report().unwrap().get("verdict"), Some("success"));
}

#[test]
fn a_success_outcome_is_always_the_last_one() {
    // 반대 방향(지나간 success · 마지막 failure)은 **걸어서 만들 수 없다.**
    //
    // success 판정은 `close_cycle` 만 적을 수 있어 밟을 되돌아감이 없고, 그 자리에서 열리는
    // Step 도 없다. 그래서 지나간 판정은 언제나 failure 다 — 이 시험은 그 사실을 잰다.
    let (mut cycle, _) = cycle_at_the_exit("success");

    assert!(
        matches!(
            cycle.revisit_step(),
            Err(CycleError::Step(gil::WalkError::NothingToRevisit))
        ),
        "성공한 판정에서 되돌아갈 수 있다"
    );
    assert!(
        cycle.openable_here().is_empty(),
        "성공한 판정 뒤에 열 수 있는 것이 있다: {:?}",
        cycle.openable_here()
    );
}

#[test]
fn the_two_verdicts_must_agree() {
    // 완료 조건 5 — 두 판정은 계층이 다르지만 값은 같아야 한다.
    for (cycle_says, outcome_says) in [("success", "failure"), ("failure", "success")] {
        let (mut cycle, outcome) = cycle_at_the_exit(outcome_says);
        let mut report = cycle_report(&cycle, outcome_says, outcome);
        report.insert("verdict", cycle_says);
        // 방향은 이 Cycle 이 말하는 판정에 맞춘다 — 여기서 걸리면 안 된다.
        let allowed = cycle_allowed_here(cycle.rules(), CycleKind::Experiment, ACTION, &report);
        report.insert(ACTION, allowed.first().unwrap().clone());

        let err = cycle.close(report).expect_err("어긋난 판정으로 닫혔다");
        match err {
            CycleError::OutcomeRef(OutcomeRefError::VerdictDisagrees {
                cycle: ours,
                outcome: theirs,
                ..
            }) => {
                assert_eq!(ours, cycle_says);
                assert_eq!(theirs, outcome_says);
            }
            other => panic!("다른 이유로 거절됐다: {other}"),
        }
    }
}

#[test]
fn the_verdict_narrows_the_direction() {
    // 완료 조건 6 — success + revisit 도, failure + open_child 도 안 된다.
    for (verdict, forbidden) in [("success", "revisit"), ("failure", "open_child")] {
        let (mut cycle, outcome) = cycle_at_the_exit(verdict);
        let report = cycle_report(&cycle, verdict, outcome).with(ACTION, forbidden);

        let err = cycle
            .close(report)
            .unwrap_err_or_panic(&format!("{verdict} + {forbidden} 이 통과했다"));
        assert!(
            matches!(
                err,
                CycleError::Grammar(GrammarError::FieldValueNotAllowed { .. })
            ),
            "{err}"
        );
        // 왜 좁혀졌는지를 말해야 한다.
        assert!(err.to_string().contains("verdict"), "{err}");
    }
}

/// 시험이 읽기 쉬우라고 두는 작은 도우미.
trait UnwrapErrOrPanic<T, E> {
    fn unwrap_err_or_panic(self, message: &str) -> E;
}

impl<T: std::fmt::Debug, E> UnwrapErrOrPanic<T, E> for Result<T, E> {
    fn unwrap_err_or_panic(self, message: &str) -> E {
        match self {
            Err(err) => err,
            Ok(value) => panic!("{message}: {value:?}"),
        }
    }
}

// ── 닫힘 ───────────────────────────────────────────────────────────────────

#[test]
fn a_report_that_holds_up_closes_the_cycle() {
    // 완료 조건 7.
    for verdict in ["success", "failure"] {
        let (mut cycle, outcome) = cycle_at_the_exit(verdict);
        let report = cycle_report(&cycle, verdict, outcome);

        cycle.close(report.clone()).expect("옳은 Report 가 거절됐다");

        assert!(cycle.is_closed());
        assert_eq!(cycle.status(), NodeStatus::Closed);
        assert_eq!(cycle.report(), Some(&report));
        assert!(!cycle.can_close(), "닫힌 것을 또 닫을 수 있다고 한다");
    }
}

#[test]
fn a_closed_cycle_moves_no_more() {
    // 완료 조건 8 — 열지도, 닫지도, 되돌아가지도 못한다.
    let (mut cycle, outcome) = cycle_at_the_exit("failure");
    cycle
        .close(cycle_report(&cycle, "failure", outcome))
        .unwrap();
    let after = snapshot(&cycle);

    for kind in NodeKind::ALL {
        assert_eq!(
            cycle.open_step(kind),
            Err(CycleError::AlreadyClosed),
            "닫힌 Cycle 에서 {kind} 가 열렸다"
        );
    }
    assert_eq!(
        cycle.close_step(full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)),
        Err(CycleError::AlreadyClosed)
    );
    assert_eq!(cycle.revisit_step(), Err(CycleError::AlreadyClosed));
    assert_eq!(
        cycle.close(cycle_report(&cycle, "failure", outcome)),
        Err(CycleError::AlreadyClosed)
    );
    assert!(cycle.openable_here().is_empty(), "닫힌 Cycle 이 무언가를 안내한다");
    assert_eq!(snapshot(&cycle), after, "거절이 Cycle 을 바꿨다");
}

#[test]
fn a_refused_close_leaves_the_cycle_exactly_as_it_was() {
    let (mut cycle, outcome) = cycle_at_the_exit("success");
    let before = snapshot(&cycle);

    for bad in [
        cycle_report(&cycle, "success", outcome).with("outcome_ref", "99"),
        cycle_report(&cycle, "success", outcome).with(ACTION, "revisit"),
        cycle_report(&cycle, "success", outcome).with("handoff_summary", " "),
    ] {
        assert!(cycle.close(bad).is_err());
        assert_eq!(snapshot(&cycle), before, "거절이 Cycle 을 바꿨다");
        assert!(!cycle.is_closed());
    }
}

#[test]
fn a_cycle_that_is_still_open_can_keep_walking() {
    // 닫히지 않은 Cycle 은 되돌아가 갈래를 낼 수 있다 — 지금까지 걸어온 방식 그대로.
    let mut cycle = bootstrap().cycles().current().clone();
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        cycle_step(&mut cycle, kind);
    }
    let target = cycle.steps().nodes()[3].id;

    cycle.open_step(NodeKind::Outcome).unwrap();
    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", "failure")
        .with(ACTION, "revisit")
        .with(
            "next_direction.target_node_ref",
            cycle.step_ref(target).to_string(),
        )
        .with("next_direction.reason", "가설부터 다시");
    cycle.close_step(report).unwrap();

    cycle.revisit_step().expect("적어 둔 되돌아감을 밟는다");
    cycle_step(&mut cycle, NodeKind::Hypothesis);
    assert!(!cycle.is_closed(), "걷는 중에 Cycle 이 닫혔다");
    assert!(!cycle.can_close(), "가설을 연 자리에서 닫을 수 있다고 한다");
}

// ── basis_refs — Synthesis 는 근거 없이 문장을 짓지 않는다 ────────────────

/// Question·Interpretation 을 하나씩 닫고 **Synthesis 를 열어 둔** Interview.
///
/// 돌려주는 것은 (Cycle, 닫힌 Question, 닫힌 Interpretation).
fn interview_at_a_synthesis() -> (Cycle, gil::NodeId, gil::NodeId) {
    let mut project = gil::Project::start(spec());
    let cycle = project.cycles_mut().current_mut();
    let question = cycle_step(cycle, NodeKind::Question);
    let interpretation = cycle_step(cycle, NodeKind::Interpretation);
    cycle.open_step(NodeKind::Synthesis).expect("제안을 연다");
    (cycle.clone(), question, interpretation)
}

/// 그 근거를 적은 Synthesis Report.
fn synthesis_with(cycle: &Cycle, basis: &str) -> gil::Report {
    full_report(cycle.rules(), CycleKind::Interview, NodeKind::Synthesis)
        .with("basis_refs", basis)
        .with("approved", "yes")
}

#[test]
fn one_basis_ref_on_its_own_line_is_enough() {
    let (cycle, question, _) = interview_at_a_synthesis();
    let basis = cycle.step_ref(question).to_string();
    cycle
        .clone()
        .close_step(synthesis_with(&cycle, &basis))
        .expect("닫힌 Question 하나면 근거가 된다");
}

#[test]
fn several_basis_refs_come_one_per_line() {
    // 명세 §16 — block scalar 안에 한 줄에 하나. 범용 list 문법을 만들지 않는다.
    let (cycle, question, interpretation) = interview_at_a_synthesis();
    let basis = format!(
        "{}\n{}",
        cycle.step_ref(question),
        cycle.step_ref(interpretation)
    );
    cycle
        .clone()
        .close_step(synthesis_with(&cycle, &basis))
        .expect("두 근거를 한 줄에 하나씩 적으면 닫힌다");

    // 빈 줄은 세지 않는다.
    let padded = format!("\n{basis}\n\n");
    cycle
        .clone()
        .close_step(synthesis_with(&cycle, &padded))
        .expect("빈 줄은 근거가 아니다");
}

#[test]
fn a_basis_ref_that_is_not_a_step_address_is_refused() {
    let (cycle, question, _) = interview_at_a_synthesis();
    let number = question.to_string().trim_start_matches('#').to_string();
    let good = cycle.step_ref(question).to_string();

    for bad in [
        number.clone(),
        format!("#{number}"),
        format!("S{number}"),
        // 쉼표로 이어 붙인 목록은 한 줄이 하나라는 규칙을 어긴다.
        format!("{good}, {good}"),
    ] {
        let err = cycle
            .clone()
            .close_step(synthesis_with(&cycle, &bad))
            .unwrap_err_or_panic(&format!("{bad:?} 가 근거로 받아들여졌다"));
        assert!(
            matches!(err, CycleError::BasisRefs(BasisRefError::Unreadable { .. })),
            "{bad:?}: {err}"
        );
        // 그리고 어떤 꼴로 적어야 하는지 보여 준다.
        assert!(err.to_string().contains("한 줄에 하나씩"), "{err}");
    }
}

#[test]
fn a_basis_ref_outside_this_interview_is_refused() {
    let (cycle, question, _) = interview_at_a_synthesis();
    let elsewhere = format!(
        "step:C9/S{}",
        question.to_string().trim_start_matches('#')
    );
    let err = cycle
        .clone()
        .close_step(synthesis_with(&cycle, &elsewhere))
        .unwrap_err_or_panic("다른 Cycle 의 자리가 근거가 됐다");
    assert!(
        matches!(err, CycleError::BasisRefs(BasisRefError::OtherCycle { .. })),
        "{err}"
    );
}

#[test]
fn a_basis_ref_that_does_not_exist_is_refused() {
    let (cycle, _, _) = interview_at_a_synthesis();
    let ghost = format!("step:{}/S99", cycle.id().to_ref().id());
    let err = cycle
        .clone()
        .close_step(synthesis_with(&cycle, &ghost))
        .unwrap_err_or_panic("없는 자리가 근거가 됐다");
    assert!(
        matches!(err, CycleError::BasisRefs(BasisRefError::NotFound { .. })),
        "{err}"
    );
}

#[test]
fn a_basis_ref_of_the_wrong_kind_is_refused() {
    // 근거는 닫힌 Question 또는 Interpretation 이다 — 제 판정도, Experiment 의 Step 도 아니다.
    let (cycle, _, _) = interview_at_a_synthesis();
    let itself = cycle.steps().current().expect("제안에 서 있다");
    let basis = cycle.step_ref(itself).to_string();

    let err = cycle
        .clone()
        .close_step(synthesis_with(&cycle, &basis))
        .unwrap_err_or_panic("제안이 제 근거가 됐다");
    match err {
        CycleError::BasisRefs(BasisRefError::WrongKind { kind, .. }) => {
            assert_eq!(kind, NodeKind::Synthesis);
        }
        other => panic!("다른 이유로 거절됐다: {other}"),
    }
}

#[test]
fn a_basis_ref_that_is_still_open_is_refused() {
    // 아직 열려 있는 자리는 근거가 아니다 — 제 자신이 그 자리다.
    let (cycle, _, _) = interview_at_a_synthesis();
    let open = cycle.steps().current().expect("제안이 열려 있다");
    assert!(!cycle.steps().node(open).unwrap().is_closed());

    let err = cycle
        .clone()
        .close_step(synthesis_with(&cycle, &cycle.step_ref(open).to_string()))
        .unwrap_err_or_panic("열린 자리가 근거가 됐다");
    assert!(matches!(err, CycleError::BasisRefs(_)), "{err}");
}

#[test]
fn the_same_basis_ref_twice_is_refused() {
    let (cycle, question, _) = interview_at_a_synthesis();
    let once = cycle.step_ref(question).to_string();
    let twice = format!("{once}\n{once}");

    let err = cycle
        .clone()
        .close_step(synthesis_with(&cycle, &twice))
        .unwrap_err_or_panic("같은 근거를 두 번 적고 닫혔다");
    assert!(
        matches!(err, CycleError::BasisRefs(BasisRefError::Duplicated { .. })),
        "{err}"
    );
}

#[test]
fn a_synthesis_without_any_basis_is_refused() {
    // Synthesis 는 근거 없는 새 목표나 제약을 더하지 않는다(명세 §16).
    //
    // 칸을 아예 안 적은 것과 비워 둔 것은 **하나의 실패**다 — 파서는 그 둘을 구분할 수
    // 있지만 사람이 고쳐야 하는 것은 같다: 근거를 적어라. 도메인 오류를 둘로 늘리면
    // 같은 처방에 두 이름이 붙는다.
    let (cycle, _, _) = interview_at_a_synthesis();

    let mut missing = synthesis_with(&cycle, "");
    missing.remove("basis_refs");
    assert!(!missing.has("basis_refs"), "칸이 남아 있다");

    let empties = ["", "   ", "\n\n", "\n   \n\t\n"]
        .into_iter()
        .map(|empty| synthesis_with(&cycle, empty))
        .chain([missing]);

    for report in empties {
        let written = report.get("basis_refs").map(str::to_string);
        let err = cycle
            .clone()
            .close_step(report)
            .unwrap_err_or_panic("근거 없이 닫혔다");
        assert!(
            matches!(err, CycleError::BasisRefs(BasisRefError::Empty { .. })),
            "{written:?} 가 다른 이유로 거절됐다: {err}"
        );
    }
}

/// `#1 question · #2 interpretation · #3 synthesis(approved: no)` 를 지나
/// `#4 question · #5 interpretation · #6 synthesis` 까지 걸은 Interview.
///
/// 승인을 못 얻은 제안 뒤에는 다시 묻는다(§13) — 그래서 이 길은 **한 줄로 길어진다.**
fn interview_at_a_second_synthesis() -> Cycle {
    let (mut cycle, question, interpretation) = interview_at_a_synthesis();
    let basis = format!(
        "{}\n{}",
        cycle.step_ref(question),
        cycle.step_ref(interpretation)
    );
    let refused = synthesis_with(&cycle, &basis).with("approved", "no");
    cycle.close_step(refused).expect("승인 못 얻은 제안을 닫는다");

    cycle_step(&mut cycle, NodeKind::Question);
    cycle_step(&mut cycle, NodeKind::Interpretation);
    cycle.open_step(NodeKind::Synthesis).expect("다시 제안한다");
    cycle
}

#[test]
fn a_basis_ref_may_reach_past_its_parent_into_the_lineage() {
    // 근거는 **부모 하나**가 아니라 딛고 온 길 전체다 — 조부모도, 그 위도 근거가 된다.
    // 이름의 크기로 재던 시절과 여기서 갈린다: 재는 것은 `parent` 사슬이다.
    let cycle = interview_at_a_second_synthesis();
    let here = cycle.steps().current().expect("두 번째 제안에 서 있다");
    let lineage = cycle.steps().lineage(here).expect("길이 있다");
    let ancestors: Vec<String> = lineage
        .iter()
        .filter(|node| {
            node.id != here
                && matches!(node.kind, NodeKind::Question | NodeKind::Interpretation)
        })
        .map(|node| cycle.step_ref(node.id).to_string())
        .collect();

    assert_eq!(ancestors.len(), 4, "네 자리를 지나왔어야 한다: {ancestors:?}");
    cycle
        .clone()
        .close_step(synthesis_with(&cycle, &ancestors.join("\n")))
        .expect("딛고 온 길 위의 자리는 모두 근거가 된다");
}

#[test]
fn a_synthesis_report_written_nested_closes_the_same_as_dotted() {
    // 사람은 접어서도 적는다. 접어 적었다고 다른 Report 가 되면 문법이 두 벌이 된다.
    let (cycle, question, interpretation) = interview_at_a_synthesis();
    let dotted = synthesis_with(
        &cycle,
        &format!(
            "{}\n{}",
            cycle.step_ref(question),
            cycle.step_ref(interpretation)
        ),
    );
    let text = format!(
        "statement: {}\napproved: yes\nbasis_refs: |\n  {}\n  {}\n",
        dotted.get("statement").expect("제안 문장이 있다"),
        cycle.step_ref(question),
        cycle.step_ref(interpretation)
    );
    let parsed = Report::parse(&text).expect("읽힌다");

    assert_eq!(parsed, dotted, "접어 적은 것이 다른 Report 가 됐다");
    cycle.clone().close_step(parsed).expect("접어 적어도 닫힌다");
}

#[test]
fn the_report_keeps_what_was_written() {
    // 검사는 읽어서 재는 것이고, 적힌 원문은 그대로 남는다.
    let (cycle, question, interpretation) = interview_at_a_synthesis();
    let basis = format!(
        "{}\n{}",
        cycle.step_ref(question),
        cycle.step_ref(interpretation)
    );
    let mut cycle = cycle;
    cycle
        .close_step(synthesis_with(&cycle.clone(), &basis))
        .expect("닫힌다");

    let stored = cycle
        .steps()
        .node(cycle.steps().current().unwrap())
        .unwrap()
        .report
        .as_ref()
        .unwrap()
        .get("basis_refs")
        .expect("적어 둔 근거가 있다");
    assert_eq!(stored, basis, "적은 원문이 달라졌다");
}
