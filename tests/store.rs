//! 걷기가 프로세스를 넘는다 — 눕히고, 다시 세운다.
//!
//! 이번에 재는 것은 둘이다.
//!
//! 1. **건너간 것이 같은 걷기인가** — 그래프·서 있는 자리·되돌아온 직후라는 사실까지.
//! 2. **두 번째 통로를 막는가** — 파일은 걷기의 메서드를 거치지 않고 고칠 수 있다.
//!    걷기가 만들 수 없는 꼴을 담은 파일은 되살아나지 못해야 한다.
//!
//! 여기서도 길은 코드에 적지 않는다 — 어디로 갈 수 있는지는 `spec/gil-spec.yaml` 이 말한다.

use std::path::{Path, PathBuf};

use gil::{
    NodeId, NodeKind, NodeStatus, RestoreError, StoreError, Walk, WalkError, load, save,
};
use serde_norway::Value;

mod common;
use common::{ACTION, REASON, TARGET, full_report, scratch, spec, step, step_close};

// ── 걸어서 만든 자리들 ─────────────────────────────────────────────────────

/// `#1 Define … #4 Analysis` 를 걷고 `#5 Outcome` 을 **열어 둔 채** 선다.
fn walk_with_an_open_outcome() -> Walk {
    let mut walk = Walk::start(spec());
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        step(&mut walk, kind);
    }
    walk.open(NodeKind::Outcome).expect("outcome 을 연다");
    walk
}

/// 되돌아가겠다고 **적고** 닫은 자리 — 아직 밟지는 않았다.
fn walk_that_decided_to_revisit() -> (Walk, NodeId, NodeId) {
    let mut walk = walk_with_an_open_outcome();
    let outcome = walk.current().expect("outcome 에 서 있다");
    let target = first_of_kind(&walk, NodeKind::Analysis);

    let report = full_report(walk.rules(), NodeKind::Outcome)
        .with("verdict", "failure")
        .with(ACTION, "revisit")
        .with(TARGET, target.to_string().trim_start_matches('#'))
        .with(REASON, "가설이 반증됐다 — 해석까지는 유효하다");
    walk.close(report).expect("되돌아가겠다는 결정을 적고 닫는다");

    (walk, target, outcome)
}

/// 되돌아감을 **밟은** 자리 — 아직 새 가설을 열지 않았다.
fn walk_that_revisited() -> (Walk, NodeId, NodeId) {
    let (mut walk, target, outcome) = walk_that_decided_to_revisit();
    walk.revisit().expect("적어 둔 되돌아감을 실행한다");
    (walk, target, outcome)
}

/// 갈래의 첫 가설까지 연 자리 — `#6` 이 열려 있고 제 출처를 지닌다.
fn walk_with_a_branch() -> Walk {
    let (mut walk, _, _) = walk_that_revisited();
    walk.open(NodeKind::Hypothesis).expect("갈래는 가설에서 시작한다");
    walk
}

/// 끝 경계를 지난 자리.
fn walk_that_finished() -> Walk {
    let mut walk = walk_with_an_open_outcome();
    step_close(&mut walk, NodeKind::Outcome);
    walk.open(NodeKind::CycleExit).expect("끝 경계를 지난다");
    walk
}

fn first_of_kind(walk: &Walk, kind: NodeKind) -> NodeId {
    walk.nodes()
        .iter()
        .find(|node| node.kind == kind)
        .unwrap_or_else(|| panic!("{kind} 가 걷기에 없다"))
        .id
}

// ── 건너가기 ───────────────────────────────────────────────────────────────

fn round_trip(walk: &Walk, label: &str) -> Walk {
    let path = scratch(label).join("walk.yaml");
    save(walk, &path).expect("걷기를 눕힐 수 있어야 한다");
    load(spec(), &path).expect("눕힌 걷기를 다시 세울 수 있어야 한다")
}

#[test]
fn a_saved_walk_comes_back_as_the_same_graph() {
    let before = walk_with_a_branch();
    let after = round_trip(&before, "same-graph");

    assert_eq!(after.nodes(), before.nodes(), "그래프가 건너가며 달라졌다");
    assert_eq!(after.current(), before.current(), "서 있는 자리가 달라졌다");
    assert_eq!(after.is_finished(), before.is_finished());
}

#[test]
fn every_node_keeps_its_parent_and_its_provenance() {
    // 계보와 출처는 **적힌 것**이다. 건너가면서 순서로 되계산되면 여기서 갈린다.
    let before = walk_with_a_branch();
    let after = round_trip(&before, "parents");

    for node in before.nodes() {
        let same = after.node(node.id).expect("건너가며 Node 가 사라졌다");
        assert_eq!(same.parent, node.parent, "{} 의 부모가 달라졌다", node.id);
        assert_eq!(
            same.revisit_from, node.revisit_from,
            "{} 의 출처가 달라졌다",
            node.id
        );
    }

    let branch = after.current().expect("갈래의 첫 가설에 서 있다");
    let lineage_before = before.lineage(branch).unwrap();
    let lineage_after = after.lineage(branch).unwrap();
    assert_eq!(
        lineage_after.iter().map(|n| n.id).collect::<Vec<_>>(),
        lineage_before.iter().map(|n| n.id).collect::<Vec<_>>(),
        "계보가 건너가며 달라졌다"
    );
}

#[test]
fn an_open_step_crosses_over_still_open_and_can_be_closed() {
    // 한 턴에 열고 다음 턴에 닫는 것 — 저장이 있어야 성립하는 바로 그것.
    let before = walk_with_an_open_outcome();
    let outcome = before.current().unwrap();
    let mut after = round_trip(&before, "open-step");

    let node = after.node(outcome).expect("열린 Node 가 건너와야 한다");
    assert_eq!(node.status, NodeStatus::Open);
    assert!(node.report.is_none(), "열린 Node 가 Report 를 지녔다");

    step_close(&mut after, NodeKind::Outcome);
    assert_eq!(after.node(outcome).unwrap().status, NodeStatus::Closed);
}

#[test]
fn the_walk_that_just_revisited_still_demands_a_hypothesis() {
    // 되돌아왔다는 사실이 안 실리면 "되돌아온 뒤엔 가설만" 이 프로세스 경계에서 증발한다.
    let (before, target, outcome) = walk_that_revisited();
    let mut after = round_trip(&before, "pending-revisit");
    assert_eq!(after.current(), Some(target));

    // 문법만 보면 Analysis 뒤에는 Outcome 도 열린다 — 되돌아온 자리에서는 아니다.
    let refused = after
        .open(NodeKind::Outcome)
        .expect_err("되돌아온 자리에서 outcome 이 열렸다");
    assert!(
        matches!(
            refused,
            WalkError::ExpectedHypothesis {
                opened: NodeKind::Outcome
            }
        ),
        "다른 이유로 거절됐다: {refused}"
    );

    after.open(NodeKind::Hypothesis).expect("갈래는 가설에서 시작한다");
    let branch = after.current().unwrap();
    assert_eq!(
        after.node(branch).unwrap().revisit_from,
        Some(outcome),
        "갈래의 첫 가설이 제 출처를 잃었다"
    );
}

#[test]
fn a_finished_walk_stays_finished() {
    let before = walk_that_finished();
    let mut after = round_trip(&before, "finished");

    assert!(after.is_finished());
    assert_eq!(after.current(), before.current(), "끝나도 서 있던 자리는 남는다");
    assert!(matches!(
        after.open(NodeKind::Hypothesis),
        Err(WalkError::AlreadyFinished)
    ));
}

#[test]
fn the_next_name_is_read_from_the_file_not_recounted() {
    // 남은 이름은 실린 Node 들로부터 다시 셀 수 있는 값이 아니다 — 적힌 것이다.
    // 파일이 "다음은 #99" 라고 말하면 건너간 뒤 나는 Node 는 #99 여야 한다.
    //
    // 재는 것은 **읽는 쪽**뿐이다. 쓰는 쪽(저장이 진짜 next_id 를 싣는가)은 아직 못 잰다 —
    // 걸어서 만든 걷기에서는 next_id 가 언제나 가장 큰 이름+1 이라 다시 세도 같다.
    // 언제 재게 되는지는 `Walk::next_id` 에 적어 뒀다.
    let (walk, _, _) = walk_that_revisited();
    let path = scratch("next-name").join("walk.yaml");
    save(&walk, &path).unwrap();
    edit_file(&path, |file| file["next_id"] = Value::from(99));

    let mut walk = load(spec(), &path).expect("이름이 넉넉한 파일은 되살아난다");
    walk.open(NodeKind::Hypothesis).expect("갈래는 가설에서 시작한다");

    assert_eq!(
        walk.current().unwrap().to_string(),
        "#99",
        "다음 이름을 파일에서 읽지 않고 다시 셌다"
    );
}

// ── 파일이 스스로 밝히는 것 ────────────────────────────────────────────────

#[test]
fn the_file_says_which_format_it_is() {
    let dir = scratch("format-line");
    let path = dir.join("walk.yaml");
    save(&walk_with_a_branch(), &path).unwrap();

    let text = std::fs::read_to_string(&path).unwrap();
    assert!(
        text.starts_with(&format!("format: {}\n", gil::FORMAT)),
        "파일이 제 형식을 첫 줄에서 밝히지 않는다:\n{text}"
    );
}

#[test]
fn an_unknown_format_is_refused_instead_of_guessed() {
    let dir = scratch("format-unknown");
    let path = dir.join("walk.yaml");
    save(&walk_with_a_branch(), &path).unwrap();
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
fn no_saved_walk_is_not_a_broken_one() {
    // 아직 시작하지 않은 것과 망가진 것은 다르다 — 부르는 쪽이 갈라 말할 수 있어야 한다.
    let dir = scratch("nothing-saved");
    match load(spec(), dir.join("walk.yaml")) {
        Err(StoreError::NotFound { .. }) => {}
        other => panic!("저장이 없다는 사실이 다른 얼굴로 왔다: {other:?}"),
    }
}

#[test]
fn saving_leaves_nothing_half_written_beside_it() {
    // 재는 것은 **자국이 안 남는가**다. 쓰다 죽었을 때 온전한 파일이 남는가(진짜 원자성)는
    // 여기서 재지 못한다 — 그건 프로세스를 중간에 죽여야 재는 값이다.
    let dir = scratch("atomic");
    let path = dir.join("walk.yaml");
    save(&walk_with_a_branch(), &path).unwrap();
    save(&walk_that_finished(), &path).unwrap();

    let left: Vec<PathBuf> = std::fs::read_dir(&dir)
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .filter(|entry| entry != &path)
        .collect();
    assert!(left.is_empty(), "쓰다 만 자국이 남았다: {left:?}");
}

#[test]
fn the_path_is_made_when_it_is_missing() {
    let dir = scratch("mkdir");
    let path = dir.join(gil::WALK_PATH);
    save(&walk_with_a_branch(), &path).expect("없는 자리도 만들어 쓴다");
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

/// 걸어서 만든 걷기를 눕힌 뒤 손으로 고치고, 되살리기가 거절하는 이유를 돌려준다.
fn tampered(walk: &Walk, label: &str, edit: impl FnOnce(&mut Value)) -> RestoreError {
    let path = scratch(label).join("walk.yaml");
    save(walk, &path).unwrap();
    edit_file(&path, edit);

    match load(spec(), &path) {
        Err(StoreError::NotAWalk(err)) => err,
        other => panic!("걷기가 만들 수 없는 파일이 되살아났다: {other:?}"),
    }
}

#[test]
fn a_parent_that_comes_later_is_refused() {
    // 순환과 앞뒤 뒤바뀜을 한 줄로 막는다 — 부모는 언제나 저보다 먼저 난다.
    let err = tampered(&walk_with_a_branch(), "parent-later", |file| {
        file["nodes"][1]["parent"] = Value::from(5);
    });
    assert!(
        matches!(err, RestoreError::ParentNotEarlier { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn an_edge_the_grammar_forbids_is_refused() {
    // 뿌리에 설 수 있는 것은 명세가 정한다 — 파일이 정하지 않는다.
    let err = tampered(&walk_with_a_branch(), "bad-edge", |file| {
        file["nodes"][1]["parent"] = Value::Null;
    });
    assert!(
        matches!(err, RestoreError::Grammar { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_closed_node_missing_a_required_field_is_refused() {
    let err = tampered(&walk_with_a_branch(), "thin-report", |file| {
        let report = file["nodes"][0]["report"].as_mapping_mut().unwrap();
        let field = spec()
            .rules(NodeKind::Define)
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
    // 열린 Node 아래로는 아무것도 열 수 없으니, 걷기에 열린 것은 서 있는 자리뿐이다.
    let err = tampered(&walk_with_a_branch(), "two-open", |file| {
        file["nodes"][0]["status"] = Value::from("open");
        file["nodes"][0]["report"] = Value::Null;
    });
    assert!(
        matches!(err, RestoreError::OpenNodeNotCurrent { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_report_on_an_open_node_is_refused() {
    let err = tampered(&walk_with_a_branch(), "open-with-report", |file| {
        file["nodes"][5]["report"] = file["nodes"][0]["report"].clone();
    });
    assert!(
        matches!(err, RestoreError::ReportOnOpenNode(_)),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_closed_node_without_a_report_is_refused() {
    let err = tampered(&walk_with_a_branch(), "closed-no-report", |file| {
        file["nodes"][0]["report"] = Value::Null;
    });
    assert!(
        matches!(err, RestoreError::ClosedWithoutReport(_)),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn standing_on_a_node_that_does_not_exist_is_refused() {
    let (walk, _, _) = walk_that_revisited();
    let err = tampered(&walk, "ghost-current", |file| {
        file["current"] = Value::from(99);
    });
    assert!(
        matches!(err, RestoreError::UnknownCurrent(_)),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn the_same_name_twice_is_refused() {
    let err = tampered(&walk_with_a_branch(), "duplicate", |file| {
        file["nodes"][5]["id"] = file["nodes"][0]["id"].clone();
    });
    assert!(
        matches!(err, RestoreError::DuplicateNode(_)),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_name_that_was_never_issued_is_refused() {
    let err = tampered(&walk_with_a_branch(), "unissued-name", |file| {
        file["next_id"] = Value::from(3);
    });
    assert!(
        matches!(err, RestoreError::NameBeyondNextId { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_boundary_marker_stored_as_a_step_is_refused() {
    // 경계는 지나가는 자리다. 기록에 남는 Node 가 아니다.
    let err = tampered(&walk_with_a_branch(), "boundary-as-step", |file| {
        file["nodes"][5]["kind"] = Value::from(NodeKind::CycleExit.as_str());
    });
    assert!(
        matches!(err, RestoreError::NotAStepKind { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn provenance_on_something_that_is_not_a_hypothesis_is_refused() {
    let err = tampered(&walk_with_a_branch(), "provenance-misplaced", |file| {
        file["nodes"][2]["revisit_from"] = Value::from(1);
    });
    assert!(
        matches!(err, RestoreError::RevisitFromOnNonHypothesis { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_next_direction_that_points_nowhere_is_refused() {
    let err = tampered(&walk_with_a_branch(), "bad-direction", |file| {
        file["nodes"][4]["report"][TARGET] = Value::from("99");
    });
    assert!(
        matches!(err, RestoreError::NextDirection { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_revisit_nobody_decided_is_refused() {
    // 되돌아옴은 **적힌 것을 밟은** 결과다. 출처에 그 결정이 없으면 밟지 않은 되돌아감이다.
    let (walk, _, _) = walk_that_revisited();
    let err = tampered(&walk, "forged-revisit", |file| {
        file["pending_revisit"] = file["nodes"][0]["id"].clone();
    });
    assert!(
        matches!(err, RestoreError::PendingRevisitNotDeclared { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn finishing_from_a_place_the_exit_is_not_reachable_is_refused() {
    let err = tampered(&walk_with_a_branch(), "forged-finish", |file| {
        file["finished"] = Value::from(true);
    });
    assert!(
        matches!(err, RestoreError::FinishedFromNowhere { .. }),
        "다른 이유로 거절됐다: {err}"
    );
}
