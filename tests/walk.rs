//! 한 Cycle 안의 Step 을 메모리에서 걷는다 — 열고, 적고, 닫고, 다음을 연다.
//!
//! 여기서도 **길은 코드에 적지 않는다**. 어디로 갈 수 있는지는 `spec/gil-spec.yaml` 이
//! 말하고, 시험은 그 말을 따라 걷는다.

use gil::{ClosedNode, GrammarError, Node, NodeKind, Report, Walk, WalkError};

mod common;
use common::{full_report, spec};

/// 걷기의 전부 — 실패한 연산 뒤에도 이 셋이 그대로여야 한다.
fn snapshot(walk: &Walk) -> (Option<Node>, Vec<ClosedNode>, bool) {
    (
        walk.current(),
        walk.history().to_vec(),
        walk.is_finished(),
    )
}

fn walked_kinds(walk: &Walk) -> Vec<NodeKind> {
    walk.history().iter().map(|node| node.kind).collect()
}

/// 지금 자리에서 명세가 허락하는 다음 Kind — 아직 안 걸어 본 쪽을 고른다.
fn next_kind(walk: &Walk) -> NodeKind {
    let here = walk
        .history()
        .last()
        .map(|node| node.kind)
        .unwrap_or(NodeKind::CycleEntry);
    let allowed = walk.rules().allowed_children_of(here);
    assert!(!allowed.is_empty(), "{here} 뒤에 갈 곳이 명세에 없다");

    let walked = walked_kinds(walk);
    allowed
        .iter()
        .copied()
        .find(|kind| !walked.contains(kind))
        .unwrap_or(allowed[0])
}

/// 한 Step 을 온전히 걷는다 — 열고, 명세가 받아들이는 Report 로 닫는다.
fn step(walk: &mut Walk, kind: NodeKind) {
    walk.open(kind)
        .unwrap_or_else(|err| panic!("{kind} 를 열지 못했다: {err}"));
    let report = full_report(walk.rules(), kind);
    walk.close(report)
        .unwrap_or_else(|err| panic!("{kind} 를 닫지 못했다: {err}"));
}

#[test]
fn a_step_opens_and_closes_and_then_the_next_one_opens() {
    let mut walk = Walk::start(spec());
    assert!(walk.current().is_none());
    assert!(walk.history().is_empty());

    walk.open(NodeKind::Define).unwrap();
    assert_eq!(walk.current(), Some(Node::open(NodeKind::Define)));
    assert!(walk.history().is_empty(), "열기만 해서는 기록이 남지 않는다");

    let report = full_report(walk.rules(), NodeKind::Define);
    walk.close(report.clone()).unwrap();
    assert!(walk.current().is_none());
    assert_eq!(walked_kinds(&walk), vec![NodeKind::Define]);
    assert_eq!(walk.history()[0].report, report);

    // 닫힌 Define 이 부모가 되어 다음이 열린다 — 부르는 쪽이 부모를 대지 않는다.
    walk.open(NodeKind::Hypothesis).unwrap();
    assert_eq!(walk.current(), Some(Node::open(NodeKind::Hypothesis)));
}

#[test]
fn the_walk_begins_at_the_cycle_entry() {
    let rules = spec();
    let opens_first = rules.allowed_children_of(NodeKind::CycleEntry);

    for kind in NodeKind::ALL {
        let mut walk = Walk::start(spec());
        let result = walk.open(kind);
        if opens_first.contains(&kind) {
            assert!(result.is_ok(), "{kind} 는 시작에서 열려야 한다");
        } else {
            assert!(result.is_err(), "{kind} 가 시작에서 열렸다");
        }
    }
}

#[test]
fn an_open_node_blocks_opening_another() {
    let mut walk = Walk::start(spec());
    walk.open(NodeKind::Define).unwrap();

    let err = walk
        .open(NodeKind::Hypothesis)
        .expect_err("Define 이 열려 있는데 다음이 열렸다");
    assert!(
        matches!(err, WalkError::Grammar(GrammarError::ParentNotClosed { .. })),
        "{err:?}"
    );
    // 이유를 사람이 읽을 수 있어야 한다.
    assert!(err.to_string().contains("define"), "{err}");
}

#[test]
fn closing_with_nothing_open_is_refused() {
    let mut walk = Walk::start(spec());
    let report = full_report(walk.rules(), NodeKind::Define);
    assert_eq!(walk.close(report), Err(WalkError::NothingToClose));
}

#[test]
fn a_report_missing_a_required_field_does_not_close_the_node() {
    let mut walk = Walk::start(spec());
    walk.open(NodeKind::Define).unwrap();

    let mut report = full_report(walk.rules(), NodeKind::Define);
    let dropped = walk.rules().rules(NodeKind::Define).unwrap().close_requires[0].clone();
    report.remove(&dropped);

    let err = walk.close(report).expect_err("칸이 빠졌는데 닫혔다");
    assert!(
        matches!(err, WalkError::Grammar(GrammarError::MissingReportFields { .. })),
        "{err:?}"
    );
    assert_eq!(
        walk.current(),
        Some(Node::open(NodeKind::Define)),
        "거절된 뒤에도 그 Node 는 열린 채다"
    );
}

#[test]
fn a_report_that_breaks_a_field_constraint_does_not_close_the_node() {
    let mut walk = Walk::start(spec());
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        step(&mut walk, kind);
    }
    walk.open(NodeKind::Outcome).unwrap();

    let report = full_report(walk.rules(), NodeKind::Outcome).with("verdict", "pending");
    let err = walk.close(report).expect_err("명세에 없는 값으로 닫혔다");
    assert!(
        matches!(err, WalkError::Grammar(GrammarError::FieldValueNotAllowed { .. })),
        "{err:?}"
    );
    assert_eq!(walk.current(), Some(Node::open(NodeKind::Outcome)));
}

#[test]
fn a_transition_the_grammar_refuses_is_refused_here_too() {
    let mut walk = Walk::start(spec());
    step(&mut walk, NodeKind::Define);

    let err = walk
        .open(NodeKind::Verify)
        .expect_err("define 뒤에 verify 가 열렸다");
    assert!(
        matches!(
            err,
            WalkError::Grammar(GrammarError::TransitionNotAllowed { .. })
        ),
        "{err:?}"
    );
    assert!(err.to_string().contains("hypothesis"), "갈 곳을 말해야 한다: {err}");
}

#[test]
fn a_failed_operation_changes_nothing() {
    let mut walk = Walk::start(spec());
    step(&mut walk, NodeKind::Define);
    walk.open(NodeKind::Hypothesis).unwrap();

    let before = snapshot(&walk);

    // ① 열려 있는데 또 연다
    assert!(walk.open(NodeKind::Verify).is_err());
    assert_eq!(snapshot(&walk), before);

    // ② 문법이 허락하지 않은 칸이 빠진 Report 로 닫는다
    let mut short = full_report(walk.rules(), NodeKind::Hypothesis);
    short.remove("guardrail");
    assert!(walk.close(short).is_err());
    assert_eq!(snapshot(&walk), before);

    // ③ 지금 열린 것과 다른 Kind 의 Report 로 닫는다
    let wrong = full_report(walk.rules(), NodeKind::Define);
    assert!(walk.close(wrong).is_err());
    assert_eq!(snapshot(&walk), before);
}

#[test]
fn history_keeps_the_closed_steps_and_their_reports_in_order() {
    let mut walk = Walk::start(spec());
    let mut given: Vec<(NodeKind, Report)> = Vec::new();

    for kind in [NodeKind::Define, NodeKind::Hypothesis, NodeKind::Verify] {
        walk.open(kind).unwrap();
        let report = full_report(walk.rules(), kind).with("note", format!("{kind} 를 지났다"));
        walk.close(report.clone()).unwrap();
        given.push((kind, report));
    }

    assert_eq!(walk.history().len(), given.len());
    for (recorded, (kind, report)) in walk.history().iter().zip(given) {
        assert_eq!(recorded.kind, kind);
        assert_eq!(recorded.report, report);
    }
}

#[test]
fn the_whole_cycle_walks_from_entry_to_exit() {
    let mut walk = Walk::start(spec());

    let mut guard = 0;
    while !walk.is_finished() {
        guard += 1;
        assert!(guard < 20, "걷기가 끝나지 않는다");

        let kind = next_kind(&walk);
        walk.open(kind)
            .unwrap_or_else(|err| panic!("{kind} 를 열지 못했다: {err}"));

        if !kind.is_boundary() {
            let report = full_report(walk.rules(), kind);
            walk.close(report)
                .unwrap_or_else(|err| panic!("{kind} 를 닫지 못했다: {err}"));
        }
    }

    assert_eq!(
        walked_kinds(&walk),
        vec![
            NodeKind::Define,
            NodeKind::Hypothesis,
            NodeKind::Verify,
            NodeKind::Analysis,
            NodeKind::Outcome,
        ]
    );
    assert!(walk.current().is_none(), "끝난 뒤에 열린 Node 가 남았다");
    assert!(walk.is_finished());
    assert!(
        !walk.history().iter().any(|node| node.kind.is_boundary()),
        "경계는 Step 이 아니라 기록에 남지 않는다"
    );
}

#[test]
fn analysis_can_open_a_second_hypothesis() {
    let mut walk = Walk::start(spec());
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
        // 여기서 되짚어 새 가설로 들어간다 — 문법이 이미 허락하는 길이다.
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
        NodeKind::Outcome,
    ] {
        step(&mut walk, kind);
    }

    let walked = walked_kinds(&walk);
    assert_eq!(
        walked.iter().filter(|k| **k == NodeKind::Hypothesis).count(),
        2,
        "한 Cycle 안에서 가설을 두 번 세웠다: {walked:?}"
    );

    walk.open(NodeKind::CycleExit).unwrap();
    assert!(walk.is_finished());
}

#[test]
fn nothing_happens_after_the_walk_is_finished() {
    let mut walk = Walk::start(spec());
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
        NodeKind::Outcome,
    ] {
        step(&mut walk, kind);
    }

    walk.open(NodeKind::CycleExit).unwrap();
    assert!(walk.is_finished());
    assert!(walk.current().is_none());

    let after = snapshot(&walk);
    for kind in NodeKind::ALL {
        assert_eq!(walk.open(kind), Err(WalkError::AlreadyFinished));
    }
    assert_eq!(
        walk.close(full_report(walk.rules(), NodeKind::Outcome)),
        Err(WalkError::AlreadyFinished)
    );
    assert_eq!(snapshot(&walk), after);
}
