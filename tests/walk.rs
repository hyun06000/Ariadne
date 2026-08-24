//! 한 Cycle 안의 Step 을 메모리에서 걷는다 — 열고, 적고, 닫고, 다음을 연다.
//!
//! 이번에 더 재는 것: **Node 마다 제 이름이 있고, 부모가 태어날 때 기록되는가.**
//!
//! 여기서도 **길은 코드에 적지 않는다**. 어디로 갈 수 있는지는 `spec/gil-spec.yaml` 이
//! 말하고, 시험은 그 말을 따라 걷는다.

use gil::{CycleKind, CycleRef, 
    GrammarError, NextDirectionError, Node, NodeId, NodeKind, NodeStatus, Report, StepNode, Walk,
    WalkError,
};

mod common;
/// 이 걷기가 담긴 Cycle. Step 의 영구 주소가 소속 Cycle 을 지니므로 걷기도 그것을 안다.
fn a_cycle() -> CycleRef {
    "cycle:C2".parse().expect("cycle:C2 는 주소다")
}

/// 이 걷기를 연 존재. **여기서 재는 것은 걷기의 불변식뿐이라** 어느 존재인지는 상관없다 —
/// 걷기는 Will 을 모른다. Will 과 Journey 는 [`Project`](gil::Project) 의 transaction 이 진다.
fn an_existence() -> gil::ExistenceRef {
    "existence:X1".parse().expect("existence:X1 은 주소다")
}

use common::{ACTION, REASON, TARGET, allowed_here, full_report, spec, step, step_close};

/// 걷기의 전부 — 실패한 연산 뒤에도 이 둘이 그대로여야 한다.
///
/// 끝났는지는 여기 없다. 그건 걷기의 사실이 아니라 그것을 담은 Cycle 의 사실이다.
fn snapshot(walk: &Walk) -> (Option<NodeId>, Vec<StepNode>) {
    (walk.current(), walk.nodes().to_vec())
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
    let allowed = walk.rules().allowed_children_of(CycleKind::Experiment, here);
    assert!(!allowed.is_empty(), "{here} 뒤에 갈 곳이 명세에 없다");

    let walked = kinds_of(walk.nodes());
    allowed
        .iter()
        .copied()
        .find(|kind| !walked.contains(kind))
        .unwrap_or(allowed[0])
}

/// `#1 → … → #5` 까지 걷는다(설계에서 예로 든 시나리오 그대로).
fn walk_to_second_hypothesis() -> Walk {
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
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
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
    assert!(walk.current().is_none(), "시작에는 서 있는 Node 가 없다");
    assert!(walk.nodes().is_empty());

    walk.open(NodeKind::Define).unwrap();
    let define = walk.current().expect("연 뒤에는 자리가 있다");
    assert_eq!(at(&walk).status, NodeStatus::Open);
    assert!(at(&walk).report.is_none(), "열려 있는 동안 Report 는 없다");
    assert_eq!(walk.history().count(), 0, "열기만 해서는 닫힌 것이 없다");

    let report = full_report(walk.rules(), CycleKind::Experiment, NodeKind::Define);
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
    let opens_first = rules.allowed_children_of(CycleKind::Experiment, NodeKind::CycleEntry);

    for kind in NodeKind::ALL {
        let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
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
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
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
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
    let report = full_report(walk.rules(), CycleKind::Experiment, NodeKind::Define);

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
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
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
    let mut stumbled = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
    step(&mut stumbled, NodeKind::Define);
    assert!(stumbled.open(NodeKind::Verify).is_err());
    assert!(stumbled.open(NodeKind::Outcome).is_err());
    stumbled.open(NodeKind::Hypothesis).unwrap();

    let mut clean = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
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
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
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
    let report = full_report(walk.rules(), CycleKind::Experiment, NodeKind::Hypothesis);
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
    let report = full_report(walk.rules(), CycleKind::Experiment, NodeKind::Hypothesis);
    walk.close(report).unwrap();
    step(&mut walk, NodeKind::Verify);
    step(&mut walk, NodeKind::Analysis);
    step(&mut walk, NodeKind::Outcome);

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
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
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
    let report = full_report(walk.rules(), CycleKind::Experiment, NodeKind::Hypothesis);
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

// ── 계보 조회 ──────────────────────────────────────────────────────────────

/// §9 의 시나리오 — 가설을 두 번 세우고 마지막 Outcome 을 **열어 둔 채** 선다.
fn walk_with_an_open_outcome() -> Walk {
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        step(&mut walk, kind);
    }
    walk.open(NodeKind::Outcome).unwrap();
    walk
}

#[test]
fn lineage_runs_from_the_root_to_an_open_target() {
    let walk = walk_with_an_open_outcome();
    let target = walk.current().unwrap();

    let lineage = walk.lineage(target).expect("열린 Node 도 볼 수 있어야 한다");

    assert_eq!(
        lineage.iter().map(|node| node.id).collect::<Vec<_>>(),
        walk.nodes().iter().map(|node| node.id).collect::<Vec<_>>(),
        "뿌리에서 목표까지 차례로"
    );
    assert_eq!(
        lineage.iter().map(|node| node.kind).collect::<Vec<_>>(),
        vec![
            NodeKind::Define,
            NodeKind::Hypothesis,
            NodeKind::Verify,
            NodeKind::Analysis,
            NodeKind::Hypothesis,
            NodeKind::Verify,
            NodeKind::Analysis,
            NodeKind::Outcome,
        ]
    );

    let (last, ancestors) = lineage.split_last().expect("비어 있지 않다");
    for node in ancestors {
        assert_eq!(node.status, NodeStatus::Closed, "{} 가 닫혀 있지 않다", node.id);
        assert!(node.report.is_some(), "{} 의 확정 Report 가 없다", node.id);
    }
    assert_eq!(last.id, target);
    assert_eq!(last.status, NodeStatus::Open);
    assert!(
        last.report.is_none(),
        "열린 Node 의 Report 를 확정된 것처럼 보여서는 안 된다"
    );
}

#[test]
fn lineage_stops_at_the_target() {
    // 만든 것 전부가 아니라 **그 Node 까지**다. 뒤에 난 Node 는 계보가 아니다.
    let walk = walk_with_an_open_outcome();
    let third = walk.nodes()[2].id;

    let lineage = walk.lineage(third).unwrap();

    assert_eq!(
        lineage.iter().map(|node| node.id).collect::<Vec<_>>(),
        walk.nodes()[..3]
            .iter()
            .map(|node| node.id)
            .collect::<Vec<_>>()
    );
    assert!(lineage.len() < walk.nodes().len(), "전부를 돌려줬다");
}

#[test]
fn the_lineage_of_the_root_is_the_root_alone() {
    let walk = walk_with_an_open_outcome();
    let root = walk.nodes()[0].id;

    let lineage = walk.lineage(root).unwrap();

    assert_eq!(lineage.len(), 1);
    assert_eq!(lineage[0].id, root);
    assert_eq!(lineage[0].parent, None);
}

#[test]
fn the_same_target_gives_the_same_lineage_every_time() {
    let walk = walk_with_an_open_outcome();
    let target = walk.nodes()[6].id; // 닫힌 Node

    let first = walk.lineage(target).unwrap();
    let second = walk.lineage(target).unwrap();

    assert_eq!(first.len(), second.len());
    for (a, b) in first.iter().zip(second.iter()) {
        assert_eq!(a.id, b.id);
        assert_eq!(a.kind, b.kind);
        assert_eq!(a.status, b.status);
        assert_eq!(a.report, b.report, "{} 의 확정 Report 가 달라졌다", a.id);
    }
}

#[test]
fn inspecting_a_lineage_changes_nothing() {
    let walk = walk_with_an_open_outcome();
    let before = snapshot(&walk);

    for node in walk.nodes().iter().map(|node| node.id).collect::<Vec<_>>() {
        walk.lineage(node).unwrap();
    }
    assert_eq!(snapshot(&walk), before);

    // 이름을 태우지도 않는다 — 조회한 걷기와 안 한 걷기를 나란히 세워 이름 열을 대조한다.
    let mut queried = walk_to_second_hypothesis();
    let mut untouched = walk_to_second_hypothesis();
    for node in queried.nodes().iter().map(|node| node.id).collect::<Vec<_>>() {
        queried.lineage(node).unwrap();
    }

    let report = full_report(queried.rules(), CycleKind::Experiment, NodeKind::Hypothesis);
    queried.close(report.clone()).unwrap();
    untouched.close(report).unwrap();
    queried.open(NodeKind::Verify).unwrap();
    untouched.open(NodeKind::Verify).unwrap();

    assert_eq!(
        queried.nodes().iter().map(|n| n.id).collect::<Vec<_>>(),
        untouched.nodes().iter().map(|n| n.id).collect::<Vec<_>>(),
        "계보를 조회한 것이 이름을 태웠다"
    );
}

#[test]
fn a_node_this_graph_does_not_have_is_refused() {
    // 이름은 걷기마다 따로 매겨진다. 긴 걷기의 이름을 짧은 걷기에 물어 본다.
    let long = walk_with_an_open_outcome();
    let stranger = long.nodes().last().unwrap().id;

    let mut short = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
    step(&mut short, NodeKind::Define);

    let err = short
        .lineage(stranger)
        .expect_err("없는 Node 를 조용히 넘기면 안 된다");
    assert_eq!(err, WalkError::UnknownNode(stranger));
    assert!(err.to_string().contains(&stranger.to_string()), "{err}");
}

// ── 다음 방향 ──────────────────────────────────────────────────────────────

/// 열린 Outcome 앞에서, 다음 방향만 갈아 끼울 수 있는 Report.
fn outcome_report(walk: &Walk) -> Report {
    full_report(walk.rules(), CycleKind::Experiment, NodeKind::Outcome)
}

fn first_of_kind(walk: &Walk, kind: NodeKind) -> NodeId {
    walk.nodes()
        .iter()
        .find(|node| node.kind == kind)
        .unwrap_or_else(|| panic!("{kind} 가 걷기에 없다"))
        .id
}

fn expect_next_direction_error(walk: &mut Walk, report: Report) -> NextDirectionError {
    match walk.close(report) {
        Err(WalkError::NextDirection(err)) => err,
        other => panic!("다음 방향이 거절돼야 한다: {other:?}"),
    }
}

#[test]
fn a_failure_may_point_back_at_an_ancestor_that_can_branch() {
    // 명세가 "여기서 hypothesis 를 열 수 있다"고 말하는 조상만 복귀점이 된다.
    let rules = spec();
    let can_branch: Vec<NodeKind> = NodeKind::ALL
        .into_iter()
        .filter(|kind| {
            rules
                .validate_open(CycleKind::Experiment, Node::closed(*kind), NodeKind::Hypothesis)
                .is_ok()
        })
        .collect();
    assert!(!can_branch.is_empty(), "복귀점이 될 Kind 가 없다");

    let mut checked = 0;
    for kind in can_branch {
        let mut walk = walk_with_an_open_outcome();
        let target = first_of_kind(&walk, kind);
        let report = outcome_report(&walk)
            .with("verdict", "failure")
            .with(ACTION, "revisit")
            .with(TARGET, walk.step_ref(target).to_string())
            .with(REASON, "여기까지는 유효하다");

        walk.close(report)
            .unwrap_or_else(|err| panic!("{kind} 로 되돌아가는 것이 거절됐다: {err}"));
        checked += 1;
    }
    assert!(checked >= 2, "define 과 analysis 둘 다 재 봐야 한다");
}

#[test]
fn an_ancestor_that_cannot_open_a_hypothesis_is_refused() {
    let rules = spec();
    let cannot_branch: Vec<NodeKind> = NodeKind::ALL
        .into_iter()
        .filter(|kind| !kind.is_boundary())
        .filter(|kind| {
            rules
                .validate_open(CycleKind::Experiment, Node::closed(*kind), NodeKind::Hypothesis)
                .is_err()
        })
        .collect();

    let mut checked = 0;
    for kind in cannot_branch {
        let mut walk = walk_with_an_open_outcome();
        // 닫힌 조상만 여기까지 온다 — 열려 있는 자리는 앞 검사에서 먼저 걸린다.
        let Some(target) = walk
            .nodes()
            .iter()
            .find(|node| node.kind == kind && node.status == NodeStatus::Closed)
            .map(|node| node.id)
        else {
            continue;
        };
        let report = outcome_report(&walk)
            .with("verdict", "failure")
            .with(ACTION, "revisit")
            .with(TARGET, walk.step_ref(target).to_string())
            .with(REASON, "여기로 돌아가고 싶다");

        let err = expect_next_direction_error(&mut walk, report);
        assert_eq!(
            err,
            NextDirectionError::TargetCannotBranch { target, kind },
            "{kind} 는 복귀점이 될 수 없다"
        );
        assert!(err.to_string().contains("가설"), "{err}");
        checked += 1;
    }
    assert!(checked >= 2, "hypothesis 와 verify 둘 다 재 봐야 한다");
}

#[test]
fn a_successful_cycle_may_only_close_the_cycle() {
    let mut walk = walk_with_an_open_outcome();
    let target = first_of_kind(&walk, NodeKind::Analysis);

    // 이 좁힘은 명세가 적어 둔 것이다 — 시험이 코드에 다시 적지 않는다.
    let succeeded = outcome_report(&walk).with("verdict", "success");
    assert_eq!(
        allowed_here(walk.rules(), CycleKind::Experiment, NodeKind::Outcome, ACTION, &succeeded),
        vec!["close_cycle".to_string()],
        "success 는 Cycle 을 닫는 쪽으로만 간다"
    );

    // success + revisit 은 문법이 막는다(값이 좁혀진다).
    let report = outcome_report(&walk)
        .with("verdict", "success")
        .with(ACTION, "revisit")
        .with(TARGET, walk.step_ref(target).to_string())
        .with(REASON, "돌아가고 싶다");
    let err = walk.close(report).expect_err("success + revisit 이 통과했다");
    assert!(
        matches!(
            err,
            WalkError::Grammar(GrammarError::FieldValueNotAllowed { .. })
        ),
        "{err:?}"
    );

    // success + close_cycle 은 통과한다.
    let report = outcome_report(&walk)
        .with("verdict", "success")
        .with(ACTION, "close_cycle")
        .with(REASON, "성공적으로 결론났다");
    walk.close(report).expect("success + close_cycle 은 유효하다");
}

#[test]
fn a_failure_may_also_close_the_cycle() {
    let mut walk = walk_with_an_open_outcome();
    let report = outcome_report(&walk)
        .with("verdict", "failure")
        .with(ACTION, "close_cycle")
        .with(REASON, "이 Cycle 안에는 유효한 분기점이 없다");
    walk.close(report).expect("failure + close_cycle 은 유효하다");
}

#[test]
fn a_revisit_without_a_target_is_refused() {
    let mut walk = walk_with_an_open_outcome();
    let mut report = outcome_report(&walk)
        .with("verdict", "failure")
        .with(ACTION, "revisit")
        .with(REASON, "돌아가겠다");
    report.remove(TARGET);

    let err = expect_next_direction_error(&mut walk, report);
    assert!(
        matches!(err, NextDirectionError::TargetMissing { .. }),
        "{err}"
    );
    // 어디로 돌아갈지 적어야 하는지뿐 아니라 **어떤 꼴로** 적는지도 말한다.
    assert!(err.to_string().contains("step:C2/S"), "{err}");
}

#[test]
fn closing_the_cycle_with_a_target_is_refused() {
    let mut walk = walk_with_an_open_outcome();
    let target = first_of_kind(&walk, NodeKind::Analysis);
    let report = outcome_report(&walk)
        .with("verdict", "failure")
        .with(ACTION, "close_cycle")
        .with(TARGET, walk.step_ref(target).to_string())
        .with(REASON, "닫겠다");

    assert_eq!(
        expect_next_direction_error(&mut walk, report),
        NextDirectionError::TargetNotAllowed("close_cycle".to_string())
    );
}

#[test]
fn a_target_this_graph_does_not_have_is_refused() {
    let long = walk_with_an_open_outcome();
    let stranger = long.nodes().last().unwrap().id;

    // 짧은 걷기에는 그 이름이 없다.
    let mut short = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        step(&mut short, kind);
    }
    short.open(NodeKind::Outcome).unwrap();

    let report = outcome_report(&short)
        .with("verdict", "failure")
        .with(ACTION, "revisit")
        .with(TARGET, short.step_ref(stranger).to_string())
        .with(REASON, "저기로 돌아가겠다");

    assert_eq!(
        expect_next_direction_error(&mut short, report),
        NextDirectionError::UnknownTarget(stranger)
    );
}

#[test]
fn a_target_that_is_not_a_step_address_is_refused() {
    // 되돌아갈 자리는 **typed StepRef** 다. bare 도, 화면 축약도, Cycle 없는 이름도 아니다.
    let walk = walk_with_an_open_outcome();
    let analysis = first_of_kind(&walk, NodeKind::Analysis);
    let number = analysis.to_string().trim_start_matches('#').to_string();

    for bare in [
        number.clone(),
        format!("#{number}"),
        format!("S{number}"),
        "네 번째".to_string(),
        format!("step:C2/S1, step:C2/S{number}"),
    ] {
        let report = outcome_report(&walk)
            .with("verdict", "failure")
            .with(ACTION, "revisit")
            .with(TARGET, bare.clone())
            .with(REASON, "돌아가겠다");

        let err = expect_next_direction_error(&mut walk.clone(), report);
        assert!(
            matches!(err, NextDirectionError::TargetUnreadable { .. }),
            "{bare:?} 가 주소로 읽혔다: {err}"
        );
        // 그리고 **올바른 전체 주소**를 알려 준다.
        assert!(
            err.to_string().contains("step:C2/S"),
            "무엇을 적어야 하는지 안 말한다: {err}"
        );
    }
}

#[test]
fn a_target_in_another_cycle_is_refused() {
    let mut walk = walk_with_an_open_outcome();
    let analysis = first_of_kind(&walk, NodeKind::Analysis);
    let elsewhere = format!("step:C9/S{}", analysis.to_string().trim_start_matches('#'));
    let report = outcome_report(&walk)
        .with("verdict", "failure")
        .with(ACTION, "revisit")
        .with(TARGET, elsewhere.clone())
        .with(REASON, "돌아가겠다");

    let err = expect_next_direction_error(&mut walk, report);
    assert!(
        matches!(err, NextDirectionError::TargetOtherCycle { .. }),
        "{err}"
    );
    assert!(err.to_string().contains("step:C2/S"), "{err}");
}

#[test]
fn the_outcome_cannot_point_back_at_itself() {
    // 자기 자신은 조상이 아니고, 아직 닫히지도 않았다.
    let mut walk = walk_with_an_open_outcome();
    let itself = walk.current().unwrap();
    let report = outcome_report(&walk)
        .with("verdict", "failure")
        .with(ACTION, "revisit")
        .with(TARGET, walk.step_ref(itself).to_string())
        .with(REASON, "제자리로 돌아가겠다");

    assert_eq!(
        expect_next_direction_error(&mut walk, report),
        NextDirectionError::TargetIsOpen(itself)
    );
}

#[test]
fn a_rejected_next_direction_leaves_the_outcome_open() {
    let mut walk = walk_with_an_open_outcome();
    let outcome = walk.current().unwrap();
    let before = snapshot(&walk);

    let bad_reports = vec![
        outcome_report(&walk)
            .with("verdict", "failure")
            .with(ACTION, "revisit")
            .with(REASON, "target 이 없다"),
        outcome_report(&walk)
            .with("verdict", "failure")
            .with(ACTION, "revisit")
            .with(TARGET, "step:C2/S999")
            .with(REASON, "없는 Node 다"),
        outcome_report(&walk)
            .with("verdict", "failure")
            .with(ACTION, "revisit")
            .with(TARGET, walk.step_ref(first_of_kind(&walk, NodeKind::Verify)).to_string())
            .with(REASON, "분기할 수 없는 자리다"),
        outcome_report(&walk)
            .with("verdict", "failure")
            .with(ACTION, "close_cycle")
            .with(TARGET, "step:C2/S1")
            .with(REASON, "닫는데 target 을 적었다"),
        outcome_report(&walk)
            .with("verdict", "failure")
            .with(ACTION, "close_cycle")
            .with(REASON, "   "),
    ];

    for report in bad_reports {
        assert!(walk.close(report).is_err());
        assert_eq!(snapshot(&walk), before, "거절이 상태를 건드렸다");
        assert_eq!(walk.current(), Some(outcome));
        assert_eq!(
            walk.node(outcome).unwrap().status,
            NodeStatus::Open,
            "거절 뒤에도 Outcome 은 열린 채다"
        );
        assert!(walk.node(outcome).unwrap().report.is_none());
    }
}

// ── 되돌아감 ───────────────────────────────────────────────────────────────

/// §11 의 시나리오 — `#1…#7` 을 걷고 `#8 Outcome` 을 **`#4` 로 되돌아가겠다고 적고** 닫는다.
///
/// 돌려주는 것은 (걷기, 되돌아갈 자리 `#4`, 그 결정을 적은 Outcome `#8`).
fn walk_decided_to_revisit() -> (Walk, NodeId, NodeId) {
    let mut walk = walk_with_an_open_outcome();
    let outcome = walk.current().unwrap();
    let target = first_of_kind(&walk, NodeKind::Analysis);

    let report = outcome_report(&walk)
        .with("verdict", "failure")
        .with(ACTION, "revisit")
        .with(TARGET, walk.step_ref(target).to_string())
        .with(REASON, "#4 까지는 유효하지만 그 뒤 가설이 반증됐다");
    walk.close(report).expect("되돌아가겠다는 결정을 적고 닫는다");

    (walk, target, outcome)
}

/// 안내가 실행과 갈리지 않는가 — 실사용 보고 #123 이 재라고 한 것.
///
/// 안내를 믿은 Agent 가 한 번 실패하고서야 옳은 수를 알게 되면, 그 안내는 없는 것보다 나쁘다.
fn offered_is_what_opens(walk: &Walk, where_at: &str) {
    let offered = walk.openable_here();
    for kind in NodeKind::ALL {
        let opens = walk.clone().open(kind).is_ok();
        assert_eq!(
            offered.contains(&kind),
            opens,
            "{where_at}: {kind} 을(를) 안내는 {}, 실행은 {}",
            if offered.contains(&kind) { "된다 하고" } else { "안 된다 하는데" },
            if opens { "된다" } else { "안 된다" },
        );
    }
}

#[test]
fn what_is_offered_is_exactly_what_opens() {
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
    offered_is_what_opens(&walk, "시작 경계");

    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        walk.open(kind).unwrap();
        offered_is_what_opens(&walk, &format!("{kind} 를 연 채"));
        step_close(&mut walk, kind);
        offered_is_what_opens(&walk, &format!("{kind} 를 닫은 뒤"));
    }
}

#[test]
fn after_a_revisit_only_a_new_hypothesis_is_offered() {
    // 되돌아온 자리가 Analysis 라 문법만 보면 Outcome 도 열린다. 실행은 아니다.
    let (mut walk, _, _) = walk_decided_to_revisit();
    walk.revisit().expect("적어 둔 되돌아감을 실행한다");

    offered_is_what_opens(&walk, "되돌아온 직후");
    assert_eq!(
        walk.openable_here(),
        vec![NodeKind::Hypothesis],
        "되돌아온 자리에서 가설 말고 다른 것을 안내한다"
    );
}

#[test]
fn a_walk_at_the_exit_offers_no_more_steps() {
    // 끝 경계에 닿으면 걷기 안에서 열 것이 없다. 그 다음은 Step 이 아니라 Cycle 의 일이다.
    let mut walk = walk_with_an_open_outcome();
    step_close(&mut walk, NodeKind::Outcome);

    assert!(walk.at_exit(), "닫힌 Outcome 은 끝 경계에 닿은 자리다");
    offered_is_what_opens(&walk, "끝 경계에 닿은 자리");
    assert!(
        walk.openable_here().is_empty(),
        "경계를 Step 인 것처럼 안내한다: {:?}",
        walk.openable_here()
    );
}

#[test]
fn asking_what_can_be_opened_changes_nothing() {
    let (walk, _, _) = walk_decided_to_revisit();
    let before = snapshot(&walk);
    let _ = walk.openable_here();
    assert_eq!(snapshot(&walk), before, "물어보는 것이 걷기를 바꿨다");
}

#[test]
fn a_recorded_revisit_moves_the_walk_to_its_target() {
    let (mut walk, target, outcome) = walk_decided_to_revisit();
    assert_eq!(walk.current(), Some(outcome));
    let graph_before = walk.nodes().to_vec();

    walk.revisit().expect("적어 둔 되돌아감을 실행한다");

    assert_eq!(walk.current(), Some(target), "서 있는 자리가 target 으로 옮겨간다");
    assert_eq!(walk.nodes(), &graph_before[..], "되돌아감이 그래프를 건드렸다");
    assert!(!walk.at_exit(), "해석으로 되돌아왔으니 끝 경계가 아니다");
}

#[test]
fn a_cycle_closing_outcome_has_nothing_to_revisit() {
    for verdict in ["success", "failure"] {
        let mut walk = walk_with_an_open_outcome();
        let report = outcome_report(&walk)
            .with("verdict", verdict)
            .with(ACTION, "close_cycle")
            .with(REASON, "이 Cycle 안에서는 더 갈 곳이 없다");
        walk.close(report).unwrap();

        assert_eq!(
            walk.revisit(),
            Err(WalkError::NothingToRevisit),
            "{verdict} + close_cycle 에서 되돌아갔다"
        );
    }
}

#[test]
fn an_open_outcome_cannot_revisit_yet() {
    let mut walk = walk_with_an_open_outcome();
    assert_eq!(walk.revisit(), Err(WalkError::NothingToRevisit));
}

#[test]
fn only_a_place_that_recorded_a_revisit_can_revisit() {
    // 갓 시작한 걷기 — 서 있는 자리가 없다.
    let mut empty = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
    assert_eq!(empty.revisit(), Err(WalkError::NothingToRevisit));

    // Outcome 이 아닌 닫힌 자리 — 되돌아감을 적는 칸 자체가 없다.
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        step(&mut walk, kind);
        assert_eq!(walk.revisit(), Err(WalkError::NothingToRevisit), "{kind}");
    }
}

#[test]
fn a_boundary_is_never_a_step() {
    // 경계는 지나가는 자리다. Step 으로 열면 이름도 안 받고 기록에도 안 남는 대신,
    // **거절된다** — 여는 척하는 자리를 남기면 그것으로 Cycle 을 닫으려 들게 된다.
    let mut walk = walk_with_an_open_outcome();
    step_close(&mut walk, NodeKind::Outcome);
    let before = snapshot(&walk);

    for boundary in NodeKind::ALL.into_iter().filter(|kind| kind.is_boundary()) {
        assert_eq!(
            walk.open(boundary),
            Err(WalkError::BoundaryIsNotAStep { kind: boundary }),
            "{boundary} 를 Step 으로 열 수 있었다"
        );
    }
    assert_eq!(snapshot(&walk), before, "거절이 걷기를 바꿨다");
}

#[test]
fn after_a_revisit_only_a_new_hypothesis_may_open() {
    let (mut walk, target, _) = walk_decided_to_revisit();
    walk.revisit().unwrap();
    let before = snapshot(&walk);

    for kind in NodeKind::ALL {
        if kind == NodeKind::Hypothesis {
            continue;
        }
        // 경계는 되돌아옴과 무관하게 Step 이 아니다. 두 거절은 다른 이유이므로 갈라 잰다.
        let expected = match kind.is_boundary() {
            true => WalkError::BoundaryIsNotAStep { kind },
            false => WalkError::ExpectedHypothesis { opened: kind },
        };
        assert_eq!(
            walk.open(kind),
            Err(expected),
            "되돌아온 자리에서 {kind} 가 열렸다"
        );
        assert_eq!(snapshot(&walk), before, "거절이 상태를 건드렸다");
    }

    // 거절이 반복돼도 되돌아온 상태는 풀리지 않는다 — 그 뒤에도 가설은 열린다.
    assert_eq!(walk.current(), Some(target));
    walk.open(NodeKind::Hypothesis)
        .expect("거절 뒤에도 새 가설은 열려야 한다");
}

#[test]
fn the_new_branch_hangs_off_the_revisit_target_not_the_last_node() {
    let (mut walk, target, outcome) = walk_decided_to_revisit();
    walk.revisit().unwrap();
    walk.open(NodeKind::Hypothesis).unwrap();

    let fresh = walk.node(walk.current().unwrap()).unwrap();

    // ⭐ 직전에 실행한 Node 는 #8 인데, 구조적 부모는 #4 다.
    assert_eq!(fresh.parent, Some(target), "새 갈래는 되돌아간 자리에서 난다");
    assert_ne!(fresh.parent, Some(outcome), "직전 실행 Node 가 부모가 되면 안 된다");
    assert_eq!(fresh.kind, NodeKind::Hypothesis);

    // 되돌아온 상태는 풀렸다 — 이제 문법이 허락하는 대로 이어 걷는다.
    let fresh_id = fresh.id;
    step_close(&mut walk, NodeKind::Hypothesis);
    walk.open(NodeKind::Verify)
        .expect("갈래가 시작됐으니 평범하게 이어진다");
    assert_eq!(walk.node(walk.current().unwrap()).unwrap().parent, Some(fresh_id));
}

#[test]
fn the_new_branch_does_not_inherit_the_branch_it_left() {
    let (mut walk, target, outcome) = walk_decided_to_revisit();
    let abandoned: Vec<NodeId> = walk
        .lineage(outcome)
        .unwrap()
        .iter()
        .map(|node| node.id)
        .filter(|id| *id > target) // #5 … #8
        .collect();
    assert_eq!(abandoned.len(), 4, "버린 갈래는 #5~#8 넷이다");

    walk.revisit().unwrap();
    walk.open(NodeKind::Hypothesis).unwrap();
    let fresh = walk.current().unwrap();

    let lineage: Vec<NodeId> = walk
        .lineage(fresh)
        .unwrap()
        .iter()
        .map(|node| node.id)
        .collect();

    // lineage(#9) = [#1, #2, #3, #4, #9]
    let expected: Vec<NodeId> = walk
        .lineage(target)
        .unwrap()
        .iter()
        .map(|node| node.id)
        .chain(std::iter::once(fresh))
        .collect();
    assert_eq!(lineage, expected);

    for left in abandoned {
        assert!(
            !lineage.contains(&left),
            "버린 갈래의 {left} 가 새 갈래의 계보에 들어왔다"
        );
    }
}

#[test]
fn revisiting_leaves_the_branch_it_left_untouched() {
    let (mut walk, _, outcome) = walk_decided_to_revisit();
    let before = walk.nodes().to_vec();

    walk.revisit().unwrap();
    walk.open(NodeKind::Hypothesis).unwrap();

    for old in &before {
        let now = walk.node(old.id).expect("옛 Node 가 사라졌다");
        assert_eq!(now, old, "{} 가 되돌아감 때문에 바뀌었다", old.id);
    }
    // 버린 갈래의 Outcome 도 제 결정을 그대로 갖고 있다.
    assert_eq!(walk.node(outcome).unwrap().status, NodeStatus::Closed);
    assert!(walk.node(outcome).unwrap().report.is_some());
}

#[test]
fn a_target_on_the_branch_we_left_is_refused() {
    // 앞선 Step 들이 미뤄 둔 시험 — 형제 가지는 이제 실제로 만들 수 있다.
    let (mut walk, target, _) = walk_decided_to_revisit();
    let sibling = walk
        .nodes()
        .iter()
        .find(|node| node.kind == NodeKind::Analysis && node.id > target)
        .expect("버린 갈래에도 Analysis 가 있다")
        .id;

    // 새 갈래를 Outcome 까지 걷는다.
    walk.revisit().unwrap();
    walk.open(NodeKind::Hypothesis).unwrap();
    step_close(&mut walk, NodeKind::Hypothesis);
    for kind in [NodeKind::Verify, NodeKind::Analysis] {
        step(&mut walk, kind);
    }
    walk.open(NodeKind::Outcome).unwrap();

    // 버린 갈래의 Analysis 는 닫혀 있고 가설도 열 수 있지만 — 이 자리의 조상이 아니다.
    let sibling_node = walk.node(sibling).unwrap();
    assert_eq!(sibling_node.status, NodeStatus::Closed);
    assert!(
        walk.rules()
            .validate_open(CycleKind::Experiment, Node::closed(sibling_node.kind), NodeKind::Hypothesis)
            .is_ok()
    );
    assert!(
        !walk
            .lineage(walk.current().unwrap())
            .unwrap()
            .iter()
            .any(|node| node.id == sibling)
    );

    let report = outcome_report(&walk)
        .with("verdict", "failure")
        .with(ACTION, "revisit")
        .with(TARGET, walk.step_ref(sibling).to_string())
        .with(REASON, "저 갈래로 건너뛰겠다");

    assert_eq!(
        expect_next_direction_error(&mut walk, report),
        NextDirectionError::TargetNotAnAncestor(sibling)
    );
}

// ── 갈래의 출처 ────────────────────────────────────────────────────────────

#[test]
fn walking_straight_ahead_leaves_no_revisit_provenance() {
    let mut walk = walk_with_an_open_outcome();
    for node in walk.nodes() {
        assert_eq!(
            node.revisit_from, None,
            "{} 는 평범하게 이어 걸어 났는데 출처가 붙었다",
            node.id
        );
    }
    // 열려 있는 Outcome 도 마찬가지다.
    walk.open(NodeKind::CycleExit).unwrap_err();
    assert!(walk.nodes().iter().all(|node| node.revisit_from.is_none()));
}

#[test]
fn a_branch_born_of_a_revisit_records_where_it_came_from() {
    let (mut walk, target, outcome) = walk_decided_to_revisit();
    walk.revisit().unwrap();
    walk.open(NodeKind::Hypothesis).unwrap();

    let fresh = walk.node(walk.current().unwrap()).unwrap();
    assert_eq!(fresh.kind, NodeKind::Hypothesis, "갈래는 가설에서 시작한다");
    assert_eq!(fresh.parent, Some(target), "구조적 부모는 되돌아간 자리다");
    assert_eq!(fresh.revisit_from, Some(outcome), "출처는 그 결정을 내린 Outcome 이다");
    assert_ne!(
        fresh.parent, fresh.revisit_from,
        "두 변은 서로 다른 것을 가리킨다"
    );
}

#[test]
fn the_source_decision_and_the_new_parent_agree() {
    // provenance 의 정합성 조건: 출처가 적어 둔 target 이 곧 새 Node 의 부모다.
    let (mut walk, _, _) = walk_decided_to_revisit();
    walk.revisit().unwrap();
    walk.open(NodeKind::Hypothesis).unwrap();

    let fresh = walk.node(walk.current().unwrap()).unwrap();
    let source = walk.node(fresh.revisit_from.unwrap()).unwrap();

    assert_eq!(source.status, NodeStatus::Closed, "출처는 닫힌 자리다");
    let decision = source.report.as_ref().expect("닫힌 자리에는 Report 가 있다");
    assert_eq!(decision.get(ACTION), Some("revisit"));
    assert_eq!(
        decision.get(TARGET).map(str::to_string),
        fresh.parent.map(|id| walk.step_ref(id).to_string()),
        "출처가 가리킨 target 과 새 Node 의 부모가 같아야 한다"
    );
}

#[test]
fn provenance_marks_the_birth_and_is_not_passed_down() {
    let (mut walk, _, outcome) = walk_decided_to_revisit();
    walk.revisit().unwrap();
    walk.open(NodeKind::Hypothesis).unwrap();
    let first = walk.current().unwrap();
    step_close(&mut walk, NodeKind::Hypothesis);
    for kind in [NodeKind::Verify, NodeKind::Analysis] {
        step(&mut walk, kind);
    }

    let carriers: Vec<NodeId> = walk
        .nodes()
        .iter()
        .filter(|node| node.revisit_from.is_some())
        .map(|node| node.id)
        .collect();
    assert_eq!(carriers, vec![first], "출처는 갈래의 출생점에만 남는다");
    assert_eq!(walk.node(first).unwrap().revisit_from, Some(outcome));

    for node in walk.nodes().iter().filter(|node| node.id != first) {
        assert_eq!(node.revisit_from, None, "{} 가 출처를 물려받았다", node.id);
    }
}

#[test]
fn provenance_is_not_a_lineage_edge() {
    let (mut walk, target, outcome) = walk_decided_to_revisit();
    walk.revisit().unwrap();
    walk.open(NodeKind::Hypothesis).unwrap();
    let fresh = walk.current().unwrap();

    let lineage: Vec<NodeId> = walk
        .lineage(fresh)
        .unwrap()
        .iter()
        .map(|node| node.id)
        .collect();

    assert!(
        !lineage.contains(&outcome),
        "출처가 계보에 섞였다 — lineage 는 parent 만 따라간다: {lineage:?}"
    );
    // 계보는 되돌아간 자리까지의 길 + 자기 자신뿐이다.
    let expected: Vec<NodeId> = walk
        .lineage(target)
        .unwrap()
        .iter()
        .map(|node| node.id)
        .chain(std::iter::once(fresh))
        .collect();
    assert_eq!(lineage, expected);
}

#[test]
fn provenance_is_written_once_and_the_branch_left_behind_is_untouched() {
    let (mut walk, _, _) = walk_decided_to_revisit();
    let before = walk.nodes().to_vec();

    walk.revisit().unwrap();
    walk.open(NodeKind::Hypothesis).unwrap();
    let first = walk.current().unwrap();
    step_close(&mut walk, NodeKind::Hypothesis);
    step(&mut walk, NodeKind::Verify);

    // 옛 갈래는 id·parent·status·report·revisit_from 까지 한 글자도 안 바뀐다.
    for old in &before {
        assert_eq!(walk.node(old.id).unwrap(), old, "{} 가 바뀌었다", old.id);
    }
    // 새 갈래의 출생점도 그 뒤 걸음 때문에 바뀌지 않는다.
    assert!(walk.node(first).unwrap().revisit_from.is_some());
}

#[test]
fn a_refused_open_records_no_provenance() {
    let (mut walk, _, outcome) = walk_decided_to_revisit();
    walk.revisit().unwrap();
    let before = snapshot(&walk);

    assert!(walk.open(NodeKind::Outcome).is_err());
    assert_eq!(snapshot(&walk), before, "거절이 반쯤 만든 Node 를 남겼다");
    assert!(
        walk.nodes().iter().all(|node| node.revisit_from.is_none()),
        "거절이 출처를 남겼다"
    );

    // 되돌아온 상태가 살아 있어 정상적인 가설에서만 출처가 남는다.
    walk.open(NodeKind::Hypothesis).unwrap();
    assert_eq!(
        walk.node(walk.current().unwrap()).unwrap().revisit_from,
        Some(outcome)
    );
}

#[test]
fn each_branch_off_the_same_point_knows_its_own_origin() {
    // 같은 자리로 두 번 되돌아가도 갈래마다 제 출처를 지닌다.
    let (mut walk, target, first_outcome) = walk_decided_to_revisit();

    walk.revisit().unwrap();
    walk.open(NodeKind::Hypothesis).unwrap();
    let first_branch = walk.current().unwrap();
    step_close(&mut walk, NodeKind::Hypothesis);
    for kind in [NodeKind::Verify, NodeKind::Analysis] {
        step(&mut walk, kind);
    }

    // 두 번째 Outcome 도 같은 자리를 가리킨다.
    walk.open(NodeKind::Outcome).unwrap();
    let second_outcome = walk.current().unwrap();
    let report = outcome_report(&walk)
        .with("verdict", "failure")
        .with(ACTION, "revisit")
        .with(TARGET, walk.step_ref(target).to_string())
        .with(REASON, "이 갈래도 아니었다 — 같은 자리에서 다시 시작한다");
    walk.close(report).unwrap();

    walk.revisit().unwrap();
    walk.open(NodeKind::Hypothesis).unwrap();
    let second_branch = walk.current().unwrap();

    assert_ne!(first_branch, second_branch);
    assert_eq!(walk.node(first_branch).unwrap().parent, Some(target));
    assert_eq!(walk.node(second_branch).unwrap().parent, Some(target));
    assert_eq!(
        walk.node(first_branch).unwrap().revisit_from,
        Some(first_outcome)
    );
    assert_eq!(
        walk.node(second_branch).unwrap().revisit_from,
        Some(second_outcome),
        "두 번째 갈래는 두 번째 결정에서 났다 — 순서로 짐작하지 않는다"
    );
}

#[test]
fn a_revisit_does_not_consume_a_name() {
    let (mut walk, _, _) = walk_decided_to_revisit();
    walk.revisit().unwrap();
    walk.open(NodeKind::Hypothesis).unwrap();

    // 이름에 구멍이 났다면 마지막 이름이 Node 수보다 커진다.
    let fresh = walk.node(walk.current().unwrap()).unwrap();
    assert_eq!(
        fresh.id.to_string(),
        format!("#{}", walk.nodes().len()),
        "되돌아감이 이름을 태웠다"
    );
}

// ── nodes 와 history ───────────────────────────────────────────────────────

#[test]
fn history_is_a_view_of_the_closed_nodes_not_a_second_store() {
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
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
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
    let mut given: Vec<(NodeKind, Report)> = Vec::new();

    for kind in [NodeKind::Define, NodeKind::Hypothesis, NodeKind::Verify] {
        walk.open(kind).unwrap();
        let report = full_report(walk.rules(), CycleKind::Experiment, kind).with("note", format!("{kind} 를 지났다"));
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
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
    walk.open(NodeKind::Define).unwrap();
    let define = walk.current().unwrap();

    let mut report = full_report(walk.rules(), CycleKind::Experiment, NodeKind::Define);
    let dropped = walk.rules().rules(CycleKind::Experiment, NodeKind::Define).unwrap().close_requires[0].clone();
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
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        step(&mut walk, kind);
    }
    walk.open(NodeKind::Outcome).unwrap();

    let report = full_report(walk.rules(), CycleKind::Experiment, NodeKind::Outcome).with("verdict", "pending");
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
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
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
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
    step(&mut walk, NodeKind::Define);
    walk.open(NodeKind::Hypothesis).unwrap();

    let before = snapshot(&walk);

    // ① 열려 있는데 또 연다
    assert!(walk.open(NodeKind::Verify).is_err());
    assert_eq!(snapshot(&walk), before);

    // ② 필수 칸이 빠진 Report 로 닫는다
    let mut short = full_report(walk.rules(), CycleKind::Experiment, NodeKind::Hypothesis);
    short.remove("guardrail");
    assert!(walk.close(short).is_err());
    assert_eq!(snapshot(&walk), before);

    // ③ 지금 열린 것과 다른 Kind 의 Report 로 닫는다
    let wrong = full_report(walk.rules(), CycleKind::Experiment, NodeKind::Define);
    assert!(walk.close(wrong).is_err());
    assert_eq!(snapshot(&walk), before);
}

// ── 완주와 경계 ────────────────────────────────────────────────────────────

#[test]
fn the_whole_cycle_walks_from_entry_to_exit() {
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());

    let mut guard = 0;
    while !walk.at_exit() {
        guard += 1;
        assert!(guard < 20, "걷기가 끝 경계에 닿지 않는다");

        let kind = next_kind(&walk);
        walk.open(kind)
            .unwrap_or_else(|err| panic!("{kind} 를 열지 못했다: {err}"));
        let report = full_report(walk.rules(), CycleKind::Experiment, kind);
        walk.close(report)
            .unwrap_or_else(|err| panic!("{kind} 를 닫지 못했다: {err}"));
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
    assert!(walk.at_exit());
    assert!(
        !walk.nodes().iter().any(|node| node.kind.is_boundary()),
        "경계는 Step 이 아니라 Node 가 되지 않는다"
    );
}

#[test]
fn reaching_the_exit_leaves_the_walk_standing_on_the_outcome() {
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
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

    assert!(walk.at_exit(), "끝 경계에 닿았다");
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
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
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
    assert!(walk.at_exit(), "두 갈래를 걷고도 끝 경계에 닿는다");
}

#[test]
fn nothing_opens_after_the_walk_reaches_the_exit() {
    // 끝 경계에 닿은 걷기는 스스로 멈춘다 — 그 뒤를 막는 것은 Cycle 의 몫이지만,
    // 걷기 안에서도 더 열 것이 없다는 사실은 여기서 재야 한다.
    let mut walk = Walk::start(spec(), a_cycle(), CycleKind::Experiment, an_existence());
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
        NodeKind::Outcome,
    ] {
        step(&mut walk, kind);
    }

    let after = snapshot(&walk);
    for kind in NodeKind::ALL {
        assert!(walk.open(kind).is_err(), "{kind} 가 끝 경계 뒤에서 열렸다");
    }
    assert_eq!(snapshot(&walk), after);
}
