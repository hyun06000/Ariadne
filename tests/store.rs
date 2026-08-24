//! 일이 프로세스를 넘는다 — 눕히고, 다시 세운다.
//!
//! 이번에 재는 것은 셋이다.
//!
//! 1. **건너간 것이 같은 것인가** — Cycle 의 상태부터 그래프·서 있는 자리·되돌아온 직후까지.
//! 2. **두 번째 통로를 막는가** — 파일은 도메인의 메서드를 거치지 않고 고칠 수 있다.
//!    걸어서 만들 수 없는 꼴을 담은 파일은 되살아나지 못해야 한다.
//! 3. **앞 형식을 조용히 무시하지 않는가.**
//!
//! 여기서도 길은 코드에 적지 않는다 — 어디로 갈 수 있는지는 `spec/gil-spec.yaml` 이 말한다.

use std::path::{Path, PathBuf};

use gil::{
    BasisRefError, Cycle, CycleError, CycleKind, NodeId, NodeKind, NodeStatus, OutcomeRefError,
    RestoreError, StoreError, SynthesisRefError, load, save, Project};
use serde_norway::Value;

mod common;
use common::{
    bootstrap,
    ACTION, REASON, SYNTHESIS_REF, TARGET, cycle_report, full_report, graph_at_the_exit, opened,
    scratch, spec, step_id, walked,
};

// ── 걸어서 만든 자리들 ─────────────────────────────────────────────────────

/// `#1 Define … #4 Analysis` 를 걷고 `#5 Outcome` 을 **열어 둔 채** 선다.
fn graph_with_an_open_outcome() -> Project {
    let mut project = bootstrap();
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        walked(&mut project, kind);
    }
    opened(&mut project, NodeKind::Outcome);
    project
}

/// 되돌아가겠다고 **적고** 닫은 자리 — 아직 밟지는 않았다.
fn graph_that_decided_to_revisit() -> (Project, NodeId, NodeId) {
    let mut project = graph_with_an_open_outcome();
    let target = first_of_kind(project.cycles().current(), NodeKind::Analysis);
    let cycle = project.cycles().current();
    let outcome = cycle.steps().current().expect("outcome 에 서 있다");

    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", "failure")
        .with(ACTION, "revisit")
        .with(TARGET, cycle.step_ref(target).to_string())
        .with(REASON, "가설이 반증됐다 — 해석까지는 유효하다");
    project
        .close_action_step(report)
        .expect("되돌아가겠다는 결정을 적고 닫는다");

    (project, target, outcome)
}

/// 되돌아감을 **밟은** 자리 — 아직 새 가설을 열지 않았다.
fn graph_that_revisited() -> (Project, NodeId, NodeId) {
    let (mut project, target, outcome) = graph_that_decided_to_revisit();
    project
        .cycles_mut()
        .current_mut()
        .revisit_step()
        .expect("적어 둔 되돌아감을 실행한다");
    (project, target, outcome)
}

/// 갈래의 첫 가설까지 연 자리 — `#6` 이 열려 있고 제 출처를 지닌다.
fn graph_with_a_branch() -> Project {
    let (mut project, _, _) = graph_that_revisited();
    opened(&mut project, NodeKind::Hypothesis);
    project
}

/// 첫 판정이 `failure` 라 되돌아가고, 두 번째 판정이 `success` 인 Cycle.
///
/// 돌려주는 것은 (Cycle, **지나간** failure 판정, **마지막** success 판정).
fn cycle_with_two_outcomes() -> (Project, NodeId, NodeId) {
    let (mut project, target, past) = graph_that_revisited();

    for kind in [NodeKind::Hypothesis, NodeKind::Verify, NodeKind::Analysis] {
        walked(&mut project, kind);
    }
    let _ = target;
    opened(&mut project, NodeKind::Outcome);
    let cycle = project.cycles().current();
    let last = cycle.steps().current().unwrap();
    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", "success")
        .with(ACTION, "close_cycle")
        .with(REASON, "이번 갈래가 풀었다");
    project.close_action_step(report).unwrap();

    (project, past, last)
}

/// Cycle Report 까지 써서 **닫힌** Cycle.
fn graph_that_closed() -> Project {
    let (mut project, outcome) = graph_at_the_exit("success");
    let report = cycle_report(project.cycles().current(), "success", outcome);
    project.close_cycle(report).expect("Cycle 을 닫는다");
    project
}

/// 첫 Cycle 을 성공으로 닫고 둘째 Cycle 을 연 Graph.
fn graph_with_two_cycles() -> Project {
    let mut project = graph_that_closed();
    project
        .open_child_cycle(CycleKind::Experiment)
        .expect("적어 둔 대로 다음 Cycle 을 연다");
    project
}

fn first_of_kind(cycle: &Cycle, kind: NodeKind) -> NodeId {
    cycle
        .steps()
        .nodes()
        .iter()
        .find(|node| node.kind == kind)
        .unwrap_or_else(|| panic!("{kind} 가 걷기에 없다"))
        .id
}

/// 저장 파일에서 **걸어 본 Experiment** 가 놓인 자리.
///
/// 0번은 언제나 Bootstrap Interview 다 — 프로젝트의 첫 Cycle 은 Interview 이므로, 손으로
/// 고쳐 볼 Experiment 는 그 다음에 온다.
const WALKED: usize = 1;

// ── 건너가기 ───────────────────────────────────────────────────────────────

fn round_trip(project: &Project, label: &str) -> Project {
    let path = scratch(label).join(gil::STATE_PATH);
    save(project, &path).expect("눕힐 수 있어야 한다");
    load(spec(), &path).expect("눕힌 것을 다시 세울 수 있어야 한다")
}

#[test]
fn a_saved_cycle_comes_back_as_the_same_graph() {
    let before = graph_with_a_branch();
    let after = round_trip(&before, "same-graph");

    assert_eq!(after.cycles().current().kind(), before.cycles().current().kind(), "Cycle 의 종류가 달라졌다");
    assert_eq!(after.cycles().current().status(), before.cycles().current().status(), "Cycle 의 상태가 달라졌다");
    assert_eq!(after.cycles().current().steps().nodes(), before.cycles().current().steps().nodes(), "그래프가 달라졌다");
    assert_eq!(after.cycles().current().steps().current(), before.cycles().current().steps().current());
}

#[test]
fn every_node_keeps_its_parent_and_its_provenance() {
    // 계보와 출처는 **적힌 것**이다. 건너가면서 순서로 되계산되면 여기서 갈린다.
    let before = graph_with_a_branch();
    let after = round_trip(&before, "parents");

    for node in before.cycles().current().steps().nodes() {
        let same = after.cycles().current().steps().node(node.id).expect("건너가며 Node 가 사라졌다");
        assert_eq!(same.parent, node.parent, "{} 의 부모가 달라졌다", node.id);
        assert_eq!(
            same.revisit_from, node.revisit_from,
            "{} 의 출처가 달라졌다",
            node.id
        );
    }

    let branch = after.cycles().current().steps().current().expect("갈래의 첫 가설에 서 있다");
    assert_eq!(
        after
            .cycles()
            .current()
            .steps()
            .lineage(branch)
            .unwrap()
            .iter()
            .map(|n| n.id)
            .collect::<Vec<_>>(),
        before
            .cycles()
            .current()
            .steps()
            .lineage(branch)
            .unwrap()
            .iter()
            .map(|n| n.id)
            .collect::<Vec<_>>(),
        "계보가 건너가며 달라졌다"
    );
}

#[test]
fn an_open_step_crosses_over_still_open_and_can_be_closed() {
    // 한 턴에 열고 다음 턴에 닫는 것 — 저장이 있어야 성립하는 바로 그것.
    let before = graph_with_an_open_outcome();
    let outcome = before.cycles().current().steps().current().unwrap();
    let mut after = round_trip(&before, "open-step");

    let node = after.cycles().current().steps().node(outcome).expect("열린 Node 가 건너와야 한다");
    assert_eq!(node.status, NodeStatus::Open);
    assert!(node.report.is_none(), "열린 Node 가 Report 를 지녔다");

    let report = full_report(after.cycles().current().rules(), CycleKind::Experiment, NodeKind::Outcome);
    after.close_action_step(report).expect("다음 프로세스에서 닫는다");
    assert_eq!(
        after.cycles().current().steps().node(outcome).unwrap().status,
        NodeStatus::Closed
    );
}

#[test]
fn the_walk_that_just_revisited_still_demands_a_hypothesis() {
    // 되돌아왔다는 사실이 안 실리면 "되돌아온 뒤엔 가설만" 이 프로세스 경계에서 증발한다.
    let (before, target, outcome) = graph_that_revisited();
    let mut after = round_trip(&before, "pending-revisit");
    assert_eq!(after.cycles().current().steps().current(), Some(target));

    // 문법만 보면 Analysis 뒤에는 Outcome 도 열린다 — 되돌아온 자리에서는 아니다.
    after
        .cycles_mut()
        .current_mut()
        .open_step(NodeKind::Outcome)
        .expect_err("되돌아온 자리에서 outcome 이 열렸다");

    after
        .cycles_mut()
        .current_mut()
        .open_step(NodeKind::Hypothesis)
        .expect("갈래는 가설에서 시작한다");
    let branch = after.cycles().current().steps().current().unwrap();
    assert_eq!(
        after.cycles().current().steps().node(branch).unwrap().revisit_from,
        Some(outcome),
        "갈래의 첫 가설이 제 출처를 잃었다"
    );
}

#[test]
fn a_closed_cycle_stays_closed_and_keeps_its_report() {
    let before = graph_that_closed();
    let mut after = round_trip(&before, "closed-cycle");

    assert!(after.cycles().current().is_closed());
    assert_eq!(after.cycles().current().report(), before.cycles().current().report(), "Cycle Report 가 달라졌다");
    assert_eq!(
        after.cycles_mut().current_mut().open_step(NodeKind::Hypothesis),
        Err(CycleError::AlreadyClosed),
        "닫힌 Cycle 이 건너가며 열렸다"
    );
}

#[test]
fn the_next_name_is_read_from_the_file_not_recounted() {
    // 남은 이름은 실린 Node 들로부터 다시 셀 수 있는 값이 아니다 — 적힌 것이다.
    //
    // 재는 것은 **읽는 쪽**뿐이다. 쓰는 쪽은 아직 못 잰다 — 걸어서 만든 걷기에서는
    // next_id 가 언제나 가장 큰 이름+1 이라 다시 세도 같다(`Walk::next_id` 참고).
    let (cycle, _, _) = graph_that_revisited();
    let path = scratch("next-name").join(gil::STATE_PATH);
    save(&cycle, &path).unwrap();
    edit_file(&path, |file| {
        file["cycles"]["nodes"][WALKED]["steps"]["next_id"] = Value::from(99)
    });

    let mut cycle = load(spec(), &path).expect("이름이 넉넉한 파일은 되살아난다");
    cycle
        .cycles_mut()
        .current_mut()
        .open_step(NodeKind::Hypothesis)
        .expect("갈래는 가설에서 시작한다");

    assert_eq!(
        cycle.cycles().current().steps().current().unwrap().to_string(),
        "#99",
        "다음 이름을 파일에서 읽지 않고 다시 셌다"
    );
}

// ── 파일이 스스로 밝히는 것 ────────────────────────────────────────────────

#[test]
fn the_file_says_which_format_it_is() {
    let path = scratch("format-line").join(gil::STATE_PATH);
    save(&graph_with_a_branch(), &path).unwrap();

    let text = std::fs::read_to_string(&path).unwrap();
    assert!(
        text.starts_with(&format!("format: {}\n", gil::FORMAT)),
        "파일이 제 형식을 첫 줄에서 밝히지 않는다:\n{text}"
    );
}

#[test]
fn the_file_shows_the_graph_that_owns_the_walks() {
    // 파일을 열어 본 사람이 구조를 알 수 있어야 한다 —
    // Cycle Graph 가 Cycle 들을 담고, 각 Cycle 이 제 걷기를 담는다.
    let path = scratch("format-shape").join(gil::STATE_PATH);
    save(&graph_with_two_cycles(), &path).unwrap();

    let text = std::fs::read_to_string(&path).unwrap();
    for expected in [
        "cycles:",
        "next_id:",
        "current:",
        "kind: experiment",
        "parent: null",
        "revisit_from: null",
        "steps:",
    ] {
        assert!(text.contains(expected), "{expected:?} 가 파일에 없다:\n{text}");
    }
    // 그리고 부모를 가리키는 Cycle 이 실제로 있다.
    assert!(text.contains("parent: 1"), "자식이 부모를 안 가리킨다:\n{text}");
}

#[test]
fn an_unknown_format_is_refused_instead_of_guessed() {
    let path = scratch("format-unknown").join(gil::STATE_PATH);
    save(&graph_with_a_branch(), &path).unwrap();
    edit_file(&path, |file| file["format"] = Value::from(gil::FORMAT + 1));

    match load(spec(), &path) {
        Err(StoreError::UnknownFormat { found, known }) => {
            assert_eq!(found, gil::FORMAT + 1);
            assert_eq!(known, gil::FORMAT);
        }
        other => panic!("모르는 형식을 짐작해 읽었다: {other:?}"),
    }
}

#[test]
fn no_saved_state_is_not_a_broken_one() {
    // 아직 시작하지 않은 것과 망가진 것은 다르다 — 부르는 쪽이 갈라 말할 수 있어야 한다.
    let dir = scratch("nothing-saved");
    match load(spec(), dir.join(gil::STATE_PATH)) {
        Err(StoreError::NotFound { .. }) => {}
        other => panic!("저장이 없다는 사실이 다른 얼굴로 왔다: {other:?}"),
    }
}

#[test]
fn saving_leaves_nothing_half_written_beside_it() {
    // 재는 것은 **자국이 안 남는가**다. 쓰다 죽었을 때 온전한 파일이 남는가(진짜 원자성)는
    // 여기서 재지 못한다 — 그건 프로세스를 중간에 죽여야 재는 값이다.
    let dir = scratch("atomic");
    let path = dir.join(gil::STATE_PATH);
    save(&graph_with_a_branch(), &path).unwrap();
    save(&graph_that_closed(), &path).unwrap();

    let left: Vec<PathBuf> = std::fs::read_dir(path.parent().unwrap())
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .filter(|entry| entry != &path)
        .collect();
    assert!(left.is_empty(), "쓰다 만 자국이 남았다: {left:?}");
}

#[test]
fn the_path_is_made_when_it_is_missing() {
    let dir = scratch("mkdir");
    let path = dir.join(gil::STATE_PATH);
    save(&graph_with_a_branch(), &path).expect("없는 자리도 만들어 쓴다");
    assert!(path.exists());
}

// ── 두 번째 통로 ───────────────────────────────────────────────────────────

/// 파일을 열어 손으로 고친다 — Agent 가 Write 도구로 할 수 있는 바로 그것.
fn edit_file(path: &Path, edit: impl FnOnce(&mut Value)) {
    let text = std::fs::read_to_string(path).expect("저장된 파일을 읽을 수 있어야 한다");
    let mut file: Value = serde_norway::from_str(&text).expect("저장 파일은 YAML 이다");
    edit(&mut file);
    std::fs::write(path, serde_norway::to_string(&file).unwrap()).unwrap();
}

/// 걸어서 만든 것을 눕힌 뒤 손으로 고치고, 되살리기가 거절하는 이유를 돌려준다.
fn tampered(project: &Project, label: &str, edit: impl FnOnce(&mut Value)) -> RestoreError {
    let path = scratch(label).join(gil::STATE_PATH);
    save(project, &path).unwrap();
    edit_file(&path, edit);

    match load(spec(), &path) {
        Err(StoreError::NotValid(err)) => err,
        other => panic!("걸어서 만들 수 없는 파일이 되살아났다: {other:?}"),
    }
}

#[test]
fn a_parent_that_comes_later_is_refused() {
    // 순환과 앞뒤 뒤바뀜을 한 줄로 막는다 — 부모는 언제나 저보다 먼저 난다.
    let err = tampered(&graph_with_a_branch(), "parent-later", |file| {
        file["cycles"]["nodes"][WALKED]["steps"]["nodes"][1]["parent"] = Value::from(5);
    });
    assert!(
        matches!(err, RestoreError::ParentNotEarlier { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn an_edge_the_grammar_forbids_is_refused() {
    let err = tampered(&graph_with_a_branch(), "bad-edge", |file| {
        file["cycles"]["nodes"][WALKED]["steps"]["nodes"][1]["parent"] = Value::Null;
    });
    assert!(
        matches!(err, RestoreError::Grammar { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_closed_node_missing_a_required_field_is_refused() {
    let err = tampered(&graph_with_a_branch(), "thin-report", |file| {
        let report = file["cycles"]["nodes"][WALKED]["steps"]["nodes"][0]["report"]
            .as_mapping_mut()
            .unwrap();
        let field = spec()
            .rules(CycleKind::Experiment, NodeKind::Define)
            .unwrap()
            .close_requires
            .first()
            .expect("define 은 닫으려면 무언가를 요구한다")
            .clone();
        report.remove(Value::from(field)).expect("있던 칸을 뺀다");
    });
    assert!(
        matches!(err, RestoreError::Grammar { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_second_open_node_is_refused() {
    let err = tampered(&graph_with_a_branch(), "two-open", |file| {
        file["cycles"]["nodes"][WALKED]["steps"]["nodes"][0]["status"] = Value::from("open");
        file["cycles"]["nodes"][WALKED]["steps"]["nodes"][0]["report"] = Value::Null;
        file["cycles"]["nodes"][WALKED]["steps"]["nodes"][0]["journey_ref"] = Value::Null;
    });
    assert!(
        matches!(err, RestoreError::OpenNodeNotCurrent { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_report_on_an_open_node_is_refused() {
    let err = tampered(&graph_with_a_branch(), "open-with-report", |file| {
        file["cycles"]["nodes"][WALKED]["steps"]["nodes"][5]["report"] =
            file["cycles"]["nodes"][WALKED]["steps"]["nodes"][0]["report"].clone();
    });
    assert!(
        matches!(err, RestoreError::ReportOnOpenNode(_)),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_closed_node_without_a_report_is_refused() {
    let err = tampered(&graph_with_a_branch(), "closed-no-report", |file| {
        file["cycles"]["nodes"][WALKED]["steps"]["nodes"][0]["report"] = Value::Null;
    });
    assert!(
        matches!(err, RestoreError::ClosedWithoutReport(_)),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn standing_on_a_node_that_does_not_exist_is_refused() {
    let (cycle, _, _) = graph_that_revisited();
    let err = tampered(&cycle, "ghost-current", |file| {
        file["cycles"]["nodes"][WALKED]["steps"]["current"] = Value::from(99);
    });
    assert!(
        matches!(err, RestoreError::UnknownCurrent(_)),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn the_same_name_twice_is_refused() {
    let err = tampered(&graph_with_a_branch(), "duplicate", |file| {
        file["cycles"]["nodes"][WALKED]["steps"]["nodes"][5]["id"] =
            file["cycles"]["nodes"][WALKED]["steps"]["nodes"][0]["id"].clone();
    });
    assert!(
        matches!(err, RestoreError::DuplicateNode(_)),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_name_that_was_never_issued_is_refused() {
    let err = tampered(&graph_with_a_branch(), "unissued-name", |file| {
        file["cycles"]["nodes"][WALKED]["steps"]["next_id"] = Value::from(3);
    });
    assert!(
        matches!(err, RestoreError::NameBeyondNextId { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_boundary_marker_stored_as_a_step_is_refused() {
    // 경계는 지나가는 자리다. 기록에 남는 Node 가 아니다.
    let err = tampered(&graph_with_a_branch(), "boundary-as-step", |file| {
        file["cycles"]["nodes"][WALKED]["steps"]["nodes"][5]["kind"] = Value::from(NodeKind::CycleExit.as_str());
    });
    assert!(
        matches!(err, RestoreError::NotAStepKind { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn provenance_on_something_that_is_not_a_hypothesis_is_refused() {
    let err = tampered(&graph_with_a_branch(), "provenance-misplaced", |file| {
        file["cycles"]["nodes"][WALKED]["steps"]["nodes"][2]["revisit_from"] = Value::from(1);
    });
    assert!(
        matches!(err, RestoreError::RevisitFromOnNonHypothesis { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_next_direction_that_points_nowhere_is_refused() {
    let err = tampered(&graph_with_a_branch(), "bad-direction", |file| {
        file["cycles"]["nodes"][WALKED]["steps"]["nodes"][4]["report"][TARGET] =
            Value::from("step:C2/S99");
    });
    assert!(
        matches!(err, RestoreError::NextDirection { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_revisit_nobody_decided_is_refused() {
    let (cycle, _, _) = graph_that_revisited();
    let err = tampered(&cycle, "forged-revisit", |file| {
        file["cycles"]["nodes"][WALKED]["steps"]["pending_revisit"] =
            file["cycles"]["nodes"][WALKED]["steps"]["nodes"][0]["id"].clone();
    });
    assert!(
        matches!(err, RestoreError::PendingRevisitNotDeclared { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

// ── 두 번째 통로 · Cycle 층 ────────────────────────────────────────────────

#[test]
fn a_cycle_closed_without_a_report_is_refused() {
    let err = tampered(&graph_with_a_branch(), "cycle-no-report", |file| {
        file["cycles"]["nodes"][WALKED]["status"] = Value::from("closed");
    });
    assert!(
        matches!(err, RestoreError::CycleClosedWithoutReport),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_report_on_an_open_cycle_is_refused() {
    let closed = graph_that_closed();
    let err = tampered(&closed, "cycle-open-with-report", |file| {
        file["cycles"]["nodes"][WALKED]["status"] = Value::from("open");
    });
    assert!(
        matches!(err, RestoreError::ReportOnOpenCycle),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_cycle_closed_before_its_outcome_is_refused() {
    // 안이 끝나지 않았는데 닫힌 Cycle 은 걸어서 만들 수 없다.
    let open_outcome = graph_with_an_open_outcome();
    let closed = graph_that_closed();
    let report = closed.cycles().current().report().unwrap().clone();

    let err = tampered(&open_outcome, "cycle-too-early", move |file| {
        file["cycles"]["nodes"][WALKED]["status"] = Value::from("closed");
        file["cycles"]["nodes"][WALKED]["report"] = serde_norway::to_value(
            report
                .field_names()
                .map(|name| (name.to_string(), report.get(name).unwrap().to_string()))
                .collect::<std::collections::BTreeMap<_, _>>(),
        )
        .unwrap();
    });
    assert!(
        matches!(err, RestoreError::CycleClosedTooEarly),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_cycle_report_that_points_at_a_past_outcome_is_refused_on_restore() {
    // 되살릴 때도 같은 불변식을 받는다 — `outcome_ref` 는 **마지막 판정**이어야 한다.
    // 파일을 손으로 고쳐 지나간 판정을 가리키게 하면, 그 Cycle 은 되살아나지 못한다.
    let (mut cycle, past, last) = cycle_with_two_outcomes();
    let report = cycle_report(cycle.cycles().current(), "success", last);
    cycle
        .cycles_mut()
        .current_mut()
        .close(report)
        .expect("마지막 판정으로 닫는다");

    let err = tampered(&cycle, "cycle-past-ref", move |file| {
        // 같은 Cycle 안의 **지나간 판정**을 가리키게 한다 — 주소는 typed 그대로 두고
        // Step 번호만 옮긴다.
        file["cycles"]["nodes"][WALKED]["report"]["outcome_ref"] = Value::from(format!(
            "step:C2/S{}",
            past.to_string().trim_start_matches('#')
        ));
        // 두 판정이 어긋나지 않게 결과도 지나간 것에 맞춰 준다 —
        // 그래야 **가리킨 자리** 때문에 거절된 것이 분명해진다.
        file["cycles"]["nodes"][WALKED]["report"]["verdict"] = Value::from("failure");
        file["cycles"]["nodes"][WALKED]["report"]["next_direction.action"] = Value::from("revisit");
    });
    // **그 이유가 무엇인지까지** 잰다. 판정이 어긋나서 걸린 것이라면 이 시험은
    // 재려던 규칙을 안 재고 다른 규칙에 얹혀 통과하는 것이다.
    match &err {
        RestoreError::CycleReport { source } => assert!(
            matches!(
                **source,
                CycleError::OutcomeRef(OutcomeRefError::NotTheLastOutcome { .. })
            ),
            "가리킨 자리 때문에 거절된 것이 아니다: {source}"
        ),
        other => panic!("다른 이유로 거절됐다: {other}"),
    }
    // 메시지는 **기대하는 그 주소**를 그대로 말해야 한다 — 무엇이 틀렸는지 알아도
    // 무엇을 적어야 하는지 모르면 사람은 한 번 더 틀린다.
    let expected = format!("step:C2/S{}", last.to_string().trim_start_matches('#'));
    assert!(
        err.to_string().contains(&expected),
        "마지막 판정의 주소를 안 말한다: {err}"
    );
}

#[test]
fn a_cycle_report_that_points_at_the_wrong_place_is_refused() {
    let err = tampered(&graph_that_closed(), "cycle-bad-ref", |file| {
        file["cycles"]["nodes"][WALKED]["report"]["outcome_ref"] = Value::from("1");
    });
    assert!(
        matches!(err, RestoreError::CycleReport { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_cycle_revisit_we_cannot_check_is_refused() {
    // Cycle 수준의 되돌아감을 짓지 않았다. 검사할 수 없는 출처를 있는 척 읽지 않는다.
    let path = scratch("cycle-revisit").join(gil::STATE_PATH);
    save(&graph_that_closed(), &path).unwrap();
    edit_file(&path, |file| {
        file["cycles"]["nodes"][WALKED]["revisit_from"] = Value::from(1)
    });

    match load(spec(), &path) {
        Err(StoreError::CycleRevisitNotBuilt) => {}
        other => panic!("검사할 수 없는 출처를 읽었다: {other:?}"),
    }
}

// ── 두 번째 통로 · Cycle Graph 층 ─────────────────────────────────────────

#[test]
fn a_saved_graph_comes_back_with_its_lineage() {
    let before = graph_with_two_cycles();
    let after = round_trip(&before, "graph-lineage");

    assert_eq!(after.cycles().nodes().len(), 3);
    assert_eq!(after.cycles().current_id(), before.cycles().current_id());
    assert_eq!(
        after.cycles().current().parent(),
        before.cycles().current().parent(),
        "부모가 건너가며 달라졌다"
    );
    assert_eq!(
        after.cycles().inherited_report(after.cycles().current_id()),
        before.cycles().inherited_report(before.cycles().current_id()),
        "이어받은 Cycle Report 가 달라졌다"
    );
    // 그리고 자식은 부모의 Step 을 여전히 갖고 있지 않다.
    assert!(after.cycles().current().steps().nodes().is_empty());
}

#[test]
fn the_same_cycle_name_twice_is_refused() {
    // 마지막 Cycle 의 이름을 앞의 것과 겹치게 한다. 앞의 것은 아직 Report 가 없어
    // outcome_ref 검사보다 이름 검사가 먼저 걸린다.
    let err = tampered(&graph_with_two_cycles(), "cycle-duplicate", |file| {
        file["cycles"]["nodes"][2]["id"] = Value::from(1);
    });
    assert!(
        matches!(err, RestoreError::DuplicateCycle(_)),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_cycle_name_that_was_never_issued_is_refused() {
    let err = tampered(&graph_with_two_cycles(), "cycle-unissued", |file| {
        file["cycles"]["next_id"] = Value::from(2);
    });
    assert!(
        matches!(err, RestoreError::CycleNameBeyondNextId { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_cycle_parent_that_comes_later_is_refused() {
    // 순환과 앞뒤 뒤바뀜을 한 줄로 막는다 — 부모는 언제나 저보다 먼저 난다.
    let err = tampered(&graph_with_two_cycles(), "cycle-parent-later", |file| {
        file["cycles"]["nodes"][WALKED]["parent"] = Value::from(2);
    });
    assert!(
        matches!(err, RestoreError::CycleParentNotEarlier { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_second_root_is_refused() {
    let err = tampered(&graph_with_two_cycles(), "cycle-second-root", |file| {
        file["cycles"]["nodes"][1]["parent"] = Value::Null;
    });
    assert!(
        matches!(err, RestoreError::SecondRoot(_)),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_child_under_a_parent_that_did_not_open_one_is_refused() {
    // 완료 조건 4 — 부모가 `open_child` 를 적지 않았는데 자식이 실린 파일은 되살아나지 못한다.
    //
    // 부모를 **문법에는 맞는 실패 Cycle** 로 바꾼다(판정도 방향도 함께). 그래야 문법이 먼저
    // 잡지 않고, 재려던 Graph 층 검사가 실제로 돈다.
    let err = tampered(&graph_with_two_cycles(), "cycle-forged-child", |file| {
        let parent = &mut file["cycles"]["nodes"][WALKED];
        parent["report"]["verdict"] = Value::from("failure");
        parent["report"]["next_direction.action"] = Value::from("revisit");
        // 두 계층의 판정은 같아야 하므로 안의 마지막 Outcome 도 함께 바꾼다.
        parent["steps"]["nodes"][4]["report"]["verdict"] = Value::from("failure");
    });
    match err {
        RestoreError::ParentDidNotOpenAChild { declared, .. } => {
            assert_eq!(
                declared.as_deref(),
                Some("revisit"),
                "부모가 무엇을 적었는지 말해야 한다"
            );
        }
        other => panic!("Graph 층이 아니라 다른 규칙이 잡았다: {other}"),
    }
}

#[test]
fn two_open_cycles_are_refused() {
    // 완료 조건 13·17 — 한 번에 걷는 Cycle 은 하나다.
    let err = tampered(&graph_with_two_cycles(), "cycle-two-open", |file| {
        file["cycles"]["nodes"][WALKED]["status"] = Value::from("open");
        file["cycles"]["nodes"][WALKED]["report"] = Value::Null;
    });
    assert!(
        matches!(err, RestoreError::OpenCycleNotCurrent { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn standing_on_a_cycle_that_does_not_exist_is_refused() {
    // 서 있다는 그 자리를 아무도 쓰지 않는 이름으로 옮긴다.
    let err = tampered(&graph_with_two_cycles(), "cycle-ghost-current", |file| {
        file["cycles"]["current"] = Value::from(9);
        file["cycles"]["next_id"] = Value::from(10);
    });
    // 열린 Cycle 이 서 있는 자리가 아니게 되므로 그쪽이 먼저 잡는다 — 둘 다 같은 불변식이다.
    assert!(
        matches!(
            err,
            RestoreError::OpenCycleNotCurrent { .. } | RestoreError::UnknownCurrentCycle(_)
        ),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_graph_with_no_cycles_is_refused() {
    let err = tampered(&graph_that_closed(), "cycle-empty", |file| {
        file["cycles"]["nodes"] = Value::Sequence(Vec::new());
    });
    assert!(
        matches!(err, RestoreError::NoCycles),
        "다른 이유로 거절됐다: {err}"
    );
}

// ── Interview 의 참조 출처는 파일에서도 다시 잰다 ──────────────────────────

/// **Bootstrap Interview 가 놓인 자리.** 프로젝트의 첫 Cycle 은 언제나 Interview 다.
const INTERVIEW: usize = 0;

/// 두 번 물어본 Interview 하나 — `#1 q · #2 i · #3 s(no) · #4 q · #5 i · #6 s(yes) · #7 판정`.
///
/// 승인을 못 얻은 제안 뒤에는 다시 묻는다(Cycle Model §13). 걸어서 만들 수 있는 Interview 는
/// 언제나 이렇게 **한 줄**이다 — 갈래는 오직 손으로 고친 파일에서만 생긴다. 그래서 계보 검사가
/// 실제로 무엇을 막는지는 여기서만 잴 수 있다.
fn interview_asked_twice() -> Project {
    let mut project = Project::start(spec());

    let mut basis = Vec::new();
    for approval in ["no", "yes"] {
        for kind in [NodeKind::Question, NodeKind::Interpretation] {
            basis.push(walked(&mut project, kind).to_string());
        }
        opened(&mut project, NodeKind::Synthesis);
        let report = full_report(spec_of(&project), CycleKind::Interview, NodeKind::Synthesis)
            .with("approved", approval)
            .with("basis_refs", basis.join("\n"));
        project.close_action_step(report).expect("제안을 닫는다");
    }
    let cycle = project.cycles().current();
    let synthesis = cycle.step_ref(cycle.steps().current().expect("승인된 제안에 서 있다"));

    let outcome = opened(&mut project, NodeKind::Outcome);
    let report = full_report(spec_of(&project), CycleKind::Interview, NodeKind::Outcome)
        .with(SYNTHESIS_REF, synthesis.to_string())
        .with(REASON, "승인된 Synthesis 를 얻었다");
    project.close_action_step(report).expect("판정을 닫는다");

    let mut report = cycle_report(project.cycles().current(), "success", step_id(&project, outcome));
    report.insert(ACTION, "open_child");
    project.close_cycle(report).expect("Interview 를 닫는다");
    project
}

/// 지금 이 프로젝트가 따르는 문법.
fn spec_of(project: &Project) -> &gil::RuleSet {
    project.cycles().rules()
}

/// 그 Interview 의 Step 하나를 손으로 가리킨다 — `nodes[at]` 은 `#at+1` 이다.
fn step<'a>(file: &'a mut Value, at: usize) -> &'a mut Value {
    &mut file["cycles"]["nodes"][INTERVIEW]["steps"]["nodes"][at]
}

/// `#4` 의 부모를 끊어 **`#1 #2 #3` 을 버려진 가지로 만든다.**
///
/// question 의 부모로는 cycle_entry 도 허용되므로 문법은 이것을 통과시킨다. 남는 것은
/// 계보뿐이다 — 승인된 제안 `#6` 이 딛고 온 길은 이제 `#4 #5` 밖에 없다.
fn abandon_the_first_round(file: &mut Value) {
    step(file, 3)["parent"] = Value::Null;
    // 살아남은 가지만 근거로 남긴다 — 여기서 재려는 것은 그 다음 참조의 출처다.
    step(file, 5)["report"]["basis_refs"] = Value::from("step:C1/S4\nstep:C1/S5");
}

#[test]
fn a_basis_ref_on_an_abandoned_branch_is_refused_however_small_its_name() {
    // 이번 정합화의 핵심. #1 은 이름이 가장 작지만 #6 이 딛고 온 길 위에 없다.
    // 이름의 크기로 재던 검사는 이것을 통과시켰다.
    let err = tampered(&interview_asked_twice(), "basis-abandoned", |file| {
        abandon_the_first_round(file);
        step(file, 5)["report"]["basis_refs"] = Value::from("step:C1/S4\nstep:C1/S5\nstep:C1/S1");
    });
    let CycleError::BasisRefs(BasisRefError::NotInLineage { target, .. }) = inside(err) else {
        panic!("계보 밖의 근거가 다른 이유로 거절됐다");
    };
    assert_eq!(target.to_string(), "step:C1/S1");
}

#[test]
fn a_basis_ref_born_after_the_synthesis_is_refused() {
    // #3 이 #5 를 근거로 삼는다 — 아직 나지 않은 자리다. 이름의 크기가 아니라 계보가 막는다.
    let err = tampered(&interview_asked_twice(), "basis-later", |file| {
        step(file, 2)["report"]["basis_refs"] = Value::from("step:C1/S1\nstep:C1/S5");
    });
    let CycleError::BasisRefs(BasisRefError::NotInLineage { target, here }) = inside(err) else {
        panic!("뒤에 난 자리가 다른 이유로 거절됐다");
    };
    assert_eq!(target.to_string(), "step:C1/S5");
    assert_eq!(here.to_string(), "step:C1/S3");
}

#[test]
fn the_lineage_a_walked_interview_makes_is_still_accepted() {
    // 검사를 조인 만큼, 걸어서 만든 것은 그대로 되살아나야 한다.
    let project = interview_asked_twice();
    let path = scratch("interview-roundtrip").join(gil::STATE_PATH);
    save(&project, &path).unwrap();
    load(spec(), &path).expect("걸어서 만든 Interview 가 되살아나지 못했다");
}

#[test]
fn a_synthesis_ref_on_an_abandoned_branch_is_refused() {
    // synthesis_ref 도 같은 출처 원칙을 진다 — 이 판정이 딛고 온 길 위의 Synthesis 여야 한다.
    let err = tampered(&interview_asked_twice(), "synthesis-abandoned", |file| {
        abandon_the_first_round(file);
        step(file, 2)["report"]["approved"] = Value::from("yes");
        step(file, 6)["report"]["synthesis_ref"] = Value::from("step:C1/S3");
    });
    let other = inside(err);
    let CycleError::SynthesisRef(SynthesisRefError::NotInLineage { target, here }) = &other
    else {
        panic!("계보 밖의 Synthesis 가 다른 이유로 거절됐다: {other}");
    };
    assert_eq!(target.to_string(), "step:C1/S3");
    assert_eq!(here.to_string(), "step:C1/S7");
}

#[test]
fn a_synthesis_ref_to_an_unapproved_synthesis_is_refused_from_the_file_too() {
    // 승인 문지기는 전이 문법에만 있는 것이 아니다 — 파일로 우회할 수 없어야 한다.
    let err = tampered(&interview_asked_twice(), "synthesis-unapproved", |file| {
        step(file, 6)["report"]["synthesis_ref"] = Value::from("step:C1/S3");
    });
    let CycleError::SynthesisRef(SynthesisRefError::NotApproved { approved }) = inside(err) else {
        panic!("승인 없는 Synthesis 가 다른 이유로 거절됐다");
    };
    assert_eq!(approved, "no");
}

#[test]
fn a_synthesis_with_its_basis_emptied_out_is_refused_from_the_file_too() {
    // 닫을 때 막은 것을 파일에서도 막는다. 칸을 지우든 비우든 같은 실패다.
    for (label, edit) in [
        ("basis-blanked", Value::from("   \n\n")),
        ("basis-empty", Value::from("")),
    ] {
        let err = tampered(&interview_asked_twice(), label, |file| {
            step(file, 5)["report"]["basis_refs"] = edit;
        });
        assert!(
            matches!(
                inside(err),
                CycleError::BasisRefs(BasisRefError::Empty { .. })
            ),
            "{label} 이 다른 이유로 거절됐다"
        );
    }
}

/// 되살리기가 Step Report 때문에 멈췄다면, 그 안의 까닭.
fn inside(err: RestoreError) -> CycleError {
    match err {
        RestoreError::StepReport { source, .. } => *source,
        other => panic!("Step Report 가 아닌 이유로 거절됐다: {other}"),
    }
}

/// `#1 q · #2 i · #3 s(approved: no)` 를 닫고 **`#4 question` 을 열어 둔** Interview.
fn interview_with_an_open_question() -> Project {
    let mut project = Project::start(spec());

    let mut basis = Vec::new();
    for kind in [NodeKind::Question, NodeKind::Interpretation] {
        basis.push(walked(&mut project, kind).to_string());
    }
    opened(&mut project, NodeKind::Synthesis);
    let report = full_report(spec_of(&project), CycleKind::Interview, NodeKind::Synthesis)
        .with("approved", "no")
        .with("basis_refs", basis.join("\n"));
    project.close_action_step(report).expect("제안을 닫는다");
    opened(&mut project, NodeKind::Question);
    project
}

#[test]
fn a_basis_ref_that_is_still_open_is_refused_from_the_file_too() {
    // 열려 있는 자리는 근거가 아니다. 걸어서는 이렇게 적을 수 없다 — `#4` 는 `#3` 을 닫은
    // **뒤에** 났으니 그때는 이름조차 없었다. 파일에서는 적을 수 있으니 여기서 막는다.
    let err = tampered(&interview_with_an_open_question(), "basis-open", |file| {
        step(file, 2)["report"]["basis_refs"] = Value::from("step:C1/S1\nstep:C1/S4");
    });
    let other = inside(err);
    let CycleError::BasisRefs(BasisRefError::StillOpen { target, here }) = &other else {
        panic!("열려 있는 근거가 다른 이유로 거절됐다: {other}");
    };
    assert_eq!(target.to_string(), "step:C1/S4");
    assert_eq!(here.to_string(), "step:C1/S3");
}
