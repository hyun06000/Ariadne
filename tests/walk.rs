//! 한 Cycle 안의 Step 을 메모리에서 걷는다 — 열고, 적고, 닫고, 다음을 연다.
//!
//! 이번에 더 재는 것: **Node 마다 제 이름이 있고, 부모가 태어날 때 기록되는가.**
//!
//! 여기서도 **길은 코드에 적지 않는다**. 어디로 갈 수 있는지는 `spec/gil-spec.yaml` 이
//! 말하고, 시험은 그 말을 따라 걷는다.

use gil::{GrammarError, NodeId, NodeKind, NodeStatus, Report, StepNode, Walk, WalkError};

mod common;
use common::{full_report, spec};

/// 걷기의 전부 — 실패한 연산 뒤에도 이 셋이 그대로여야 한다.
fn snapshot(walk: &Walk) -> (Option<NodeId>, Vec<StepNode>, bool) {
    (walk.current(), walk.nodes().to_vec(), walk.is_finished())
}

fn kinds_of(nodes: &[StepNode]) -> Vec<NodeKind> {
    nodes.iter().map(|node| node.kind).collect()
}

fn at(walk: &Walk) -> &StepNode {
    walk.node(walk.current().expect("서 있는 자리가 있어야 한다"))
        .expect("current 는 실재하는 Node 를 가리킨다")
}

/// 지금 **서 있는 자리**에서 명세가 허락하는 다음 Kind — 아직 안 걸어 본 쪽을 고른다.
fn next_kind(walk: &Walk) -> NodeKind {
    let here = walk
        .current()
        .and_then(|id| walk.node(id))
        .map(|node| node.kind)
        .unwrap_or(NodeKind::CycleEntry);
    let allowed = walk.rules().allowed_children_of(here);
    assert!(!allowed.is_empty(), "{here} 뒤에 갈 곳이 명세에 없다");

    let walked = kinds_of(walk.nodes());
    allowed
        .iter()
        .copied()
        .find(|kind| !walked.contains(kind))
        .unwrap_or(allowed[0])
}

/// 한 Step 을 온전히 걷는다 — 열고, 명세가 받아들이는 Report 로 닫는다.
fn step(walk: &mut Walk, kind: NodeKind) -> NodeId {
    walk.open(kind)
        .unwrap_or_else(|err| panic!("{kind} 를 열지 못했다: {err}"));
    let id = walk.current().expect("연 뒤에는 서 있는 자리가 있다");
    let report = full_report(walk.rules(), kind);
    walk.close(report)
        .unwrap_or_else(|err| panic!("{kind} 를 닫지 못했다: {err}"));
    id
}

/// `#1 → … → #5` 까지 걷는다(설계에서 예로 든 시나리오 그대로).
fn walk_to_second_hypothesis() -> Walk {
    let mut walk = Walk::start(spec());
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        step(&mut walk, kind);
    }
    walk.open(NodeKind::Hypothesis).unwrap();
    walk
}

// ── lifecycle ──────────────────────────────────────────────────────────────

#[test]
fn a_step_opens_and_closes_and_then_the_next_one_opens() {
    let mut walk = Walk::start(spec());
    assert!(walk.current().is_none(), "시작에는 서 있는 Node 가 없다");
    assert!(walk.nodes().is_empty());

    walk.open(NodeKind::Define).unwrap();
    let define = walk.current().expect("연 뒤에는 자리가 있다");
    assert_eq!(at(&walk).status, NodeStatus::Open);
    assert!(at(&walk).report.is_none(), "열려 있는 동안 Report 는 없다");
    assert_eq!(walk.history().count(), 0, "열기만 해서는 닫힌 것이 없다");

    let report = full_report(walk.rules(), NodeKind::Define);
    walk.close(report.clone()).unwrap();
    assert_eq!(walk.current(), Some(define), "닫아도 그 자리에 서 있다");
    assert_eq!(at(&walk).status, NodeStatus::Closed);
    assert_eq!(at(&walk).report.as_ref(), Some(&report));

    walk.open(NodeKind::Hypothesis).unwrap();
    let hypothesis = walk.current().unwrap();
    assert_ne!(hypothesis, define);
    assert_eq!(at(&walk).parent, Some(define));
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
    assert!(err.to_string().contains("define"), "{err}");
}

#[test]
fn closing_is_refused_when_nothing_is_open() {
    let mut walk = Walk::start(spec());
    let report = full_report(walk.rules(), NodeKind::Define);

    // ① 아직 아무것도 열지 않았다.
    assert_eq!(walk.close(report.clone()), Err(WalkError::NothingToClose));

    // ② 서 있는 자리는 있지만 이미 닫혀 있다.
    step(&mut walk, NodeKind::Define);
    assert!(walk.current().is_some());
    assert_eq!(walk.close(report), Err(WalkError::NothingToClose));
}

// ── 이름 ───────────────────────────────────────────────────────────────────

#[test]
fn every_opened_node_gets_a_name_of_its_own() {
    let mut walk = Walk::start(spec());
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
        NodeKind::Hypothesis, // 같은 kind 가 두 번째로 온다
    ] {
        step(&mut walk, kind);
    }

    let ids: Vec<NodeId> = walk.nodes().iter().map(|node| node.id).collect();
    let unique: std::collections::BTreeSet<NodeId> = ids.iter().copied().collect();
    assert_eq!(ids.len(), unique.len(), "이름이 겹쳤다: {ids:?}");

    let hypotheses: Vec<&StepNode> = walk
        .nodes()
        .iter()
        .filter(|node| node.kind == NodeKind::Hypothesis)
        .collect();
    assert_eq!(hypotheses.len(), 2);
    assert_ne!(
        hypotheses[0].id, hypotheses[1].id,
        "같은 kind 라도 다른 Node 다"
    );
}

#[test]
fn a_failed_open_does_not_consume_a_name() {
    // 실패한 걷기와 깨끗한 걷기를 나란히 세운다. 실패가 이름을 태웠다면 두 줄기의
    // 이름이 어긋난다 — 구멍이 났는지를 `NodeId` 속을 들여다보지 않고 잰다.
    let mut stumbled = Walk::start(spec());
    step(&mut stumbled, NodeKind::Define);
    assert!(stumbled.open(NodeKind::Verify).is_err());
    assert!(stumbled.open(NodeKind::Outcome).is_err());
    stumbled.open(NodeKind::Hypothesis).unwrap();

    let mut clean = Walk::start(spec());
    step(&mut clean, NodeKind::Define);
    clean.open(NodeKind::Hypothesis).unwrap();

    let names = |walk: &Walk| -> Vec<NodeId> { walk.nodes().iter().map(|node| node.id).collect() };
    assert_eq!(
        names(&stumbled),
        names(&clean),
        "실패한 open 이 이름을 태워 구멍을 남겼다"
    );
    assert_eq!(stumbled.nodes().len(), 2, "실패가 Node 를 만들었다");
}

// ── 부모 ───────────────────────────────────────────────────────────────────

#[test]
fn the_first_step_comes_from_the_cycle_entry_boundary() {
    let mut walk = Walk::start(spec());
    walk.open(NodeKind::Define).unwrap();
    assert_eq!(
        at(&walk).parent,
        None,
        "첫 Step 은 Cycle Entry Boundary 에서 들어온다"
    );
}

#[test]
fn a_parent_of_none_marks_the_local_root_of_this_step_graph() {
    // `None` 은 고아가 아니라 이 Step Graph 의 뿌리다 — Cycle Entry Boundary 로 들어온 자리.
    let mut walk = walk_to_second_hypothesis();
    let report = full_report(walk.rules(), NodeKind::Hypothesis);
    walk.close(report).unwrap();
    step(&mut walk, NodeKind::Verify);

    let roots: Vec<&StepNode> = walk
        .nodes()
        .iter()
        .filter(|node| node.parent.is_none())
        .collect();

    // 지금 Walk 가 뿌리를 하나만 만든다는 구조적 성질을 잰다.
    // "모든 Step Graph 는 뿌리가 하나여야 한다"는 명세 규칙으로 읽지 않는다.
    assert_eq!(roots.len(), 1, "지금 Walk 는 뿌리를 하나만 만든다");
    assert_eq!(roots[0].id, walk.nodes()[0].id, "뿌리는 처음 연 Node 다");
    assert_eq!(
        roots[0].kind,
        NodeKind::Define,
        "뿌리는 Cycle Entry 가 허락한 Kind 다"
    );
}

#[test]
fn every_parent_points_inside_this_step_graph() {
    // 계층이 다른 Node 나 바깥의 무엇도 Step 의 parent 가 되지 않는다.
    let mut walk = walk_to_second_hypothesis();
    let report = full_report(walk.rules(), NodeKind::Hypothesis);
    walk.close(report).unwrap();
    step(&mut walk, NodeKind::Verify);
    step(&mut walk, NodeKind::Analysis);
    step(&mut walk, NodeKind::Outcome);
    walk.open(NodeKind::CycleExit).unwrap();

    for node in walk.nodes() {
        let Some(parent) = node.parent else { continue };
        let resolved = walk
            .node(parent)
            .unwrap_or_else(|| panic!("{} 의 부모 {parent} 가 이 Step Graph 에 없다", node.id));
        assert!(
            !resolved.kind.is_boundary(),
            "경계가 parent 로 들어왔다: {} → {parent}",
            node.id
        );
        assert!(resolved.id < node.id, "부모가 자식보다 늦게 났다");
    }
}

#[test]
fn a_node_records_its_parent_when_it_is_born() {
    let mut walk = Walk::start(spec());
    let define = step(&mut walk, NodeKind::Define);

    let standing_here = walk.current();
    walk.open(NodeKind::Hypothesis).unwrap();

    assert_eq!(
        at(&walk).parent,
        standing_here,
        "부모는 여는 그 순간 서 있던 자리다"
    );
    assert_eq!(at(&walk).parent, Some(define));
}

#[test]
fn parents_are_written_once_and_never_recomputed() {
    let mut walk = walk_to_second_hypothesis();
    let before: Vec<Option<NodeId>> = walk.nodes().iter().map(|node| node.parent).collect();

    // 걷기를 이어간다 — 뒤에 무엇이 오든 앞의 부모는 그대로여야 한다.
    let report = full_report(walk.rules(), NodeKind::Hypothesis);
    walk.close(report).unwrap();
    step(&mut walk, NodeKind::Verify);
    step(&mut walk, NodeKind::Analysis);
    step(&mut walk, NodeKind::Outcome);

    let after: Vec<Option<NodeId>> = walk.nodes().iter().map(|node| node.parent).collect();
    assert_eq!(
        &after[..before.len()],
        &before[..],
        "앞선 Node 의 부모가 나중 실행 때문에 바뀌었다"
    );
}

#[test]
fn lineage_is_recoverable_by_following_parents() {
    let walk = walk_to_second_hypothesis();

    let ids: Vec<NodeId> = walk.nodes().iter().map(|node| node.id).collect();
    assert_eq!(
        kinds_of(walk.nodes()),
        vec![
            NodeKind::Define,
            NodeKind::Hypothesis,
            NodeKind::Verify,
            NodeKind::Analysis,
            NodeKind::Hypothesis,
        ]
    );

    // #5 에서 부모를 거슬러 올라간다 — 실행 순서가 아니라 기록된 관계만 쓴다.
    let mut lineage = Vec::new();
    let mut cursor = walk.current();
    while let Some(id) = cursor {
        lineage.push(id);
        cursor = walk.node(id).expect("실재하는 Node 여야 한다").parent;
    }
    lineage.reverse();

    assert_eq!(lineage, ids, "[#1, #2, #3, #4, #5] 가 복원되어야 한다");
}

// ── nodes 와 history ───────────────────────────────────────────────────────

#[test]
fn history_is_a_view_of_the_closed_nodes_not_a_second_store() {
    let mut walk = Walk::start(spec());
    step(&mut walk, NodeKind::Define);
    walk.open(NodeKind::Hypothesis).unwrap();

    assert_eq!(walk.nodes().len(), 2, "nodes 는 열린 것도 보여준다");
    let closed: Vec<&StepNode> = walk.history().collect();
    assert_eq!(closed.len(), 1, "history 는 닫힌 것만 보여준다");
    assert_eq!(closed[0].id, walk.nodes()[0].id, "같은 Node 를 가리킨다");
    assert!(closed.iter().all(|node| node.status == NodeStatus::Closed));
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

    let closed: Vec<&StepNode> = walk.history().collect();
    assert_eq!(closed.len(), given.len());
    for (recorded, (kind, report)) in closed.iter().zip(given) {
        assert_eq!(recorded.kind, kind);
        assert_eq!(recorded.report.as_ref(), Some(&report));
    }
}

// ── 거절과 원자성 ──────────────────────────────────────────────────────────

#[test]
fn a_report_missing_a_required_field_does_not_close_the_node() {
    let mut walk = Walk::start(spec());
    walk.open(NodeKind::Define).unwrap();
    let define = walk.current().unwrap();

    let mut report = full_report(walk.rules(), NodeKind::Define);
    let dropped = walk.rules().rules(NodeKind::Define).unwrap().close_requires[0].clone();
    report.remove(&dropped);

    let err = walk.close(report).expect_err("칸이 빠졌는데 닫혔다");
    assert!(
        matches!(
            err,
            WalkError::Grammar(GrammarError::MissingReportFields { .. })
        ),
        "{err:?}"
    );
    assert_eq!(walk.current(), Some(define));
    assert_eq!(at(&walk).status, NodeStatus::Open, "거절 뒤에도 열린 채다");
    assert!(at(&walk).report.is_none());
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
        matches!(
            err,
            WalkError::Grammar(GrammarError::FieldValueNotAllowed { .. })
        ),
        "{err:?}"
    );
    assert_eq!(at(&walk).status, NodeStatus::Open);
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
    assert!(
        err.to_string().contains("hypothesis"),
        "갈 곳을 말해야 한다: {err}"
    );
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

    // ② 필수 칸이 빠진 Report 로 닫는다
    let mut short = full_report(walk.rules(), NodeKind::Hypothesis);
    short.remove("guardrail");
    assert!(walk.close(short).is_err());
    assert_eq!(snapshot(&walk), before);

    // ③ 지금 열린 것과 다른 Kind 의 Report 로 닫는다
    let wrong = full_report(walk.rules(), NodeKind::Define);
    assert!(walk.close(wrong).is_err());
    assert_eq!(snapshot(&walk), before);
}

// ── 완주와 경계 ────────────────────────────────────────────────────────────

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
        kinds_of(walk.nodes()),
        vec![
            NodeKind::Define,
            NodeKind::Hypothesis,
            NodeKind::Verify,
            NodeKind::Analysis,
            NodeKind::Outcome,
        ]
    );
    assert!(walk.is_finished());
    assert!(
        !walk.nodes().iter().any(|node| node.kind.is_boundary()),
        "경계는 Step 이 아니라 Node 가 되지 않는다"
    );
}

#[test]
fn the_cycle_exit_leaves_the_walk_standing_on_the_outcome() {
    let mut walk = Walk::start(spec());
    let mut outcome = None;
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
        NodeKind::Outcome,
    ] {
        outcome = Some(step(&mut walk, kind));
    }

    let nodes_before = walk.nodes().to_vec();
    walk.open(NodeKind::CycleExit).unwrap();

    assert!(walk.is_finished(), "끝 경계를 지났다");
    assert_eq!(walk.current(), outcome, "서 있는 자리는 마지막 Outcome 이다");
    assert_eq!(
        at(&walk).kind,
        NodeKind::Outcome,
        "경계는 서 있을 수 있는 자리가 아니다"
    );
    assert_eq!(walk.nodes(), &nodes_before[..], "경계가 Node 를 만들었다");
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

    let kinds = kinds_of(walk.nodes());
    assert_eq!(
        kinds.iter().filter(|k| **k == NodeKind::Hypothesis).count(),
        2,
        "한 Cycle 안에서 가설을 두 번 세웠다: {kinds:?}"
    );

    // 두 가설은 서로 다른 Node 이고 부모도 다르다.
    let hypotheses: Vec<&StepNode> = walk
        .nodes()
        .iter()
        .filter(|node| node.kind == NodeKind::Hypothesis)
        .collect();
    assert_ne!(hypotheses[0].id, hypotheses[1].id);
    assert_ne!(hypotheses[0].parent, hypotheses[1].parent);

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
