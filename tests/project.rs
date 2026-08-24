//! format 3 — **세계와 자기 자신이 한 파일에 함께 눕는다.**
//!
//! 여기서 재는 것은 셋이다.
//!
//! 1. `gil start` 한 번이 **온전한 상태 전부**를 만드는가.
//! 2. 그 파일이 다른 프로세스에서 **그대로 다시 서는가.**
//! 3. 걸어서 만들 수 없는 파일을 **정확한 이유로 거절하는가.**
//!
//! 손으로 고친 파일을 되살려 보는 것은 이 레포의 오랜 규율이다 — 파일은 도메인의 메서드를
//! 거치지 않는 **두 번째 통로**이고, 막을 수 없으니 되살릴 때 처음부터 다시 잰다.

use std::path::Path;

use gil::{CycleKind, NodeKind, Project, ProjectError, StoreError, load, save};
use serde_norway::Value;

mod common;
use common::{bootstrap, scratch, spec};

/// 저장 파일을 손으로 고친다.
fn edit_file(path: &Path, edit: impl FnOnce(&mut Value)) {
    let text = std::fs::read_to_string(path).expect("저장된 파일을 읽을 수 있어야 한다");
    let mut file: Value = serde_norway::from_str(&text).expect("저장 파일은 YAML 이다");
    edit(&mut file);
    std::fs::write(path, serde_norway::to_string(&file).unwrap()).unwrap();
}

/// `gil start` 가 만든 것을 눕히고, 손으로 고친 뒤, 되살리기가 거절하는 이유를 돌려준다.
fn tampered(label: &str, edit: impl FnOnce(&mut Value)) -> StoreError {
    let path = scratch(label).join(gil::STATE_PATH);
    save(&Project::start(spec()), &path).expect("눕힐 수 있어야 한다");
    edit_file(&path, edit);

    match load(spec(), &path) {
        Err(err) => err,
        Ok(_) => panic!("걸어서 만들 수 없는 파일이 되살아났다"),
    }
}

/// 눕힌 파일을 YAML 로 읽는다 — 저장에 무엇이 실제로 적혔는지 보려고.
fn saved(label: &str, project: &Project) -> Value {
    let path = scratch(label).join(gil::STATE_PATH);
    save(project, &path).expect("눕힐 수 있어야 한다");
    let text = std::fs::read_to_string(&path).unwrap();
    serde_norway::from_str(&text).unwrap()
}

// ── ① `gil start` 한 번이 상태 전부를 만든다 ───────────────────────────────

#[test]
fn starting_makes_the_whole_state_in_one_save() {
    let project = Project::start(spec());
    let file = saved("f3-start", &project);

    assert_eq!(file["format"], Value::from(3), "저장 형식은 3 이다");
    assert_eq!(
        file["current_existence_ref"],
        Value::from("existence:X1"),
        "지금 누가 행동하는지가 typed reference 로 적혀야 한다"
    );

    // 최초 Existence 와 그 빈 초기 판.
    let x1 = &file["existences"]["X1"];
    assert_eq!(x1["current_journey_ref"], Value::from("journey:X1@J0"));
    let j0 = &x1["journey"]["revisions"]["J0"];
    assert_eq!(
        j0["existence_state_ref"],
        Value::from("state:ES0"),
        "J0 은 ES0 을 가리켜야 한다"
    );

    // 최초 Interview Cycle 하나 — X1 이 소유하고, 아직 닫히지 않았다.
    let cycles = file["cycles"]["nodes"].as_sequence().unwrap();
    assert_eq!(cycles.len(), 1, "첫 save 에 Cycle 은 하나다");
    assert_eq!(cycles[0]["kind"], Value::from("interview"));
    assert_eq!(cycles[0]["status"], Value::from("open"));
    assert_eq!(cycles[0]["existence_ref"], Value::from("existence:X1"));
    assert_eq!(
        cycles[0]["journey_ref"],
        Value::Null,
        "닫히기 전에는 확정된 판이 없다"
    );
}

#[test]
fn the_first_state_object_really_exists() {
    // Existence 가 생겼는데 State 가 없다는 상태를 허용하지 않는다. ES0 은 **실재하는 빈
    // 객체**이며, 성격·역할·전문성을 대신 채우지 않는다.
    let project = Project::start(spec());
    let file = saved("f3-state", &project);

    let states = file["existence_states"].as_mapping().unwrap();
    assert_eq!(states.len(), 1, "State 는 ES0 하나다");
    assert_eq!(
        states[&Value::from("ES0")],
        Value::Mapping(Default::default()),
        "ES0 은 내용이 없는 객체다"
    );

    let revision = project.current_existence().current_revision().unwrap();
    assert!(project.has_state(revision.existence_state()), "ES0 이 없다");
}

#[test]
fn only_the_heads_that_do_not_exist_yet_are_null() {
    // Knowledge·Memory·Relations·Will 은 아직 짓지 않았다 — 그 넷만 비어 있을 수 있다.
    let file = saved("f3-heads", &Project::start(spec()));
    let j0 = &file["existences"]["X1"]["journey"]["revisions"]["J0"];

    assert_ne!(j0["existence_state_ref"], Value::Null, "State 는 비울 수 없다");
    for head in [
        "knowledge_head_ref",
        "memory_head_ref",
        "relations_head_ref",
        "will_head_ref",
    ] {
        assert_eq!(j0[head], Value::Null, "{head} 는 아직 없다");
    }
}

#[test]
fn there_is_no_will_yet() {
    let file = saved("f3-will", &Project::start(spec()));
    let journey = &file["existences"]["X1"]["journey"];

    assert_eq!(journey["active_will"], Value::Null, "Active Will 은 없다");
    assert_eq!(
        journey["done_wills"],
        Value::Sequence(Vec::new()),
        "Done Will 은 비어 있다"
    );
}

#[test]
fn the_first_cycle_is_an_interview_owned_by_the_first_existence() {
    let project = Project::start(spec());
    let cycle = project.cycles().current();

    assert_eq!(cycle.kind(), CycleKind::Interview);
    assert!(!cycle.is_closed(), "열려 있다");
    assert_eq!(cycle.parent(), None, "뿌리다");
    assert_eq!(
        cycle.existence(),
        project.current_existence_ref(),
        "연 것은 최초 Existence 다"
    );
    assert_eq!(cycle.journey(), None, "닫기 전에는 확정된 판이 없다");
}

#[test]
fn the_container_interview_gets_no_will_and_offers_only_its_own_steps() {
    // 컨테이너 Cycle 은 Active Will 을 점유하지 않는다(Will Model §5). 그리고 Interview 에서
    // Experiment 의 Step 은 열리지 않는다 — 미완성 기능을 다음 행동으로 안내하지 않는다.
    let project = Project::start(spec());
    assert_eq!(
        project.cycles().openable_here(),
        vec![NodeKind::Question],
        "Interview 의 첫 자리에서는 question 만 열린다"
    );
}

// ── ② 다른 프로세스에서 그대로 다시 선다 ──────────────────────────────────

#[test]
fn another_process_restores_the_same_existence_and_the_open_interview() {
    let path = scratch("f3-restore").join(gil::STATE_PATH);
    let before = Project::start(spec());
    save(&before, &path).expect("눕힐 수 있어야 한다");

    let after = load(spec(), &path).expect("다시 세울 수 있어야 한다");

    assert_eq!(
        after.current_existence_ref(),
        before.current_existence_ref(),
        "지금 행동하는 존재가 달라졌다"
    );
    assert_eq!(
        after.current_existence().current_journey(),
        before.current_existence().current_journey(),
        "서 있는 판이 달라졌다"
    );
    assert_eq!(
        after.current_existence().current_revision(),
        before.current_existence().current_revision(),
        "판의 내용이 달라졌다"
    );
    assert_eq!(after.cycles().current().kind(), CycleKind::Interview);
    assert!(!after.cycles().current().is_closed());
    assert_eq!(
        after.cycles().current().existence(),
        after.current_existence_ref(),
        "열린 Cycle 의 주인이 달라졌다"
    );
}

#[test]
fn a_bootstrapped_project_survives_the_round_trip() {
    // Interview 를 끝내고 Experiment 를 연 자리도 그대로 건너간다.
    let path = scratch("f3-round-trip").join(gil::STATE_PATH);
    let before = bootstrap();
    save(&before, &path).expect("눕힐 수 있어야 한다");

    let after = load(spec(), &path).expect("다시 세울 수 있어야 한다");
    assert_eq!(after.cycles().nodes().len(), before.cycles().nodes().len());
    assert_eq!(after.cycles().nodes()[0].kind(), CycleKind::Interview);
    assert_eq!(after.cycles().current().kind(), CycleKind::Experiment);
    assert_eq!(after.cycles().current_id(), before.cycles().current_id());
}

#[test]
fn a_previous_format_is_refused_not_converted() {
    let path = scratch("f3-format-2").join(gil::STATE_PATH);
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    std::fs::write(&path, "format: 2\ncycles:\n  next_id: 2\n").unwrap();

    match load(spec(), &path) {
        Err(StoreError::PreviousFormat { found, current, .. }) => {
            assert_eq!(found, 2);
            assert_eq!(current, 3);
        }
        other => panic!("앞 형식을 앞 형식이라 말하지 않았다: {other:?}"),
    }
    assert!(path.exists(), "앞 형식 파일을 도구가 치웠다");
}

// ── ③ 걸어서 만들 수 없는 파일을 정확한 이유로 거절한다 ───────────────────

#[test]
fn a_current_existence_that_does_not_exist_is_refused() {
    let err = tampered("f3-ghost-existence", |file| {
        file["current_existence_ref"] = Value::from("existence:X9");
    });
    assert!(
        matches!(err, StoreError::NotWhole(_)),
        "다른 이유로 거절됐다: {err}"
    );
    assert!(err.to_string().contains("X9"), "{err}");
}

#[test]
fn a_current_journey_that_does_not_exist_is_refused() {
    let err = tampered("f3-ghost-journey", |file| {
        file["existences"]["X1"]["current_journey_ref"] = Value::from("journey:X1@J7");
    });
    assert!(
        matches!(err, StoreError::NotWhole(_)),
        "다른 이유로 거절됐다: {err}"
    );
    assert!(err.to_string().contains("J7"), "{err}");
}

#[test]
fn a_revision_without_a_state_is_refused() {
    // **비울 수 없는 자리다.** Existence 가 있는데 State 가 없는 상태는 없다.
    let err = tampered("f3-null-state", |file| {
        file["existences"]["X1"]["journey"]["revisions"]["J0"]["existence_state_ref"] = Value::Null;
    });
    assert!(
        matches!(err, StoreError::JourneyWithoutState),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_state_the_revision_points_at_but_does_not_exist_is_refused() {
    let err = tampered("f3-ghost-state", |file| {
        file["existence_states"] = Value::Mapping(Default::default());
    });
    assert!(
        matches!(err, StoreError::NotWhole(_)),
        "다른 이유로 거절됐다: {err}"
    );
    assert!(err.to_string().contains("ES0"), "{err}");
}

#[test]
fn an_open_cycle_owned_by_another_existence_is_refused() {
    // 하나의 Node 는 같은 Existence 가 열고 닫는다. 열린 Cycle 의 주인이 지금 행동하는
    // 존재가 아니라면 그 파일은 걸어서 만들 수 없다.
    let err = tampered("f3-other-owner", |file| {
        file["cycles"]["nodes"][0]["existence_ref"] = Value::from("existence:X2");
    });
    assert!(
        matches!(err, StoreError::NotWhole(_)),
        "다른 이유로 거절됐다: {err}"
    );
    let message = err.to_string();
    assert!(message.contains("X2") && message.contains("X1"), "{message}");
}

#[test]
fn a_bootstrap_state_without_a_cycle_is_refused() {
    let err = tampered("f3-no-cycle", |file| {
        file["cycles"]["nodes"] = Value::Sequence(Vec::new());
    });
    assert!(
        matches!(err, StoreError::NotValid(_)),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_root_cycle_that_is_an_experiment_is_refused() {
    // 프로젝트의 첫 Cycle 은 Interview 다. 사용자의 요청을 곧바로 실험한 Graph 는 걸어서
    // 만들 수 없다 — Experiment 는 승인된 Synthesis 뒤에만 태어난다.
    let err = tampered("f3-experiment-root", |file| {
        file["cycles"]["nodes"][0]["kind"] = Value::from("experiment");
    });
    assert!(
        matches!(err, StoreError::NotValid(_)),
        "다른 이유로 거절됐다: {err}"
    );
    let message = err.to_string();
    assert!(
        message.contains("interview") && message.contains("experiment"),
        "무엇이어야 하는지 말해야 한다: {message}"
    );
}

#[test]
fn an_experiment_step_inside_an_interview_is_refused() {
    // 두 문법은 섞이지 않는다. Interview Cycle 안에 define 이 실려 있으면 그 파일은
    // 걸어서 만들 수 없다.
    let err = tampered("f3-mixed-grammar", |file| {
        file["cycles"]["nodes"][0]["steps"]["nodes"] = serde_norway::from_str(
            "- id: 1\n  kind: define\n  parent: null\n  revisit_from: null\n  \
             status: open\n  existence_ref: existence:X1\n  journey_ref: null\n  \
             report: null\n",
        )
        .unwrap();
        file["cycles"]["nodes"][0]["steps"]["next_id"] = Value::from(2);
        file["cycles"]["nodes"][0]["steps"]["current"] = Value::from(1);
    });
    assert!(
        matches!(err, StoreError::NotValid(_)),
        "다른 이유로 거절됐다: {err}"
    );
    assert!(err.to_string().contains("define"), "{err}");
}

#[test]
fn a_journey_ref_on_an_open_cycle_is_refused() {
    // `journey_ref` 는 **닫을 때** 확정된다. 아직 열려 있는 그릇에 닫은 판이 적혀 있으면
    // 그 파일은 걸어서 만든 것이 아니다.
    let err = tampered("f3-journey-ref-too-early", |file| {
        file["cycles"]["nodes"][0]["journey_ref"] = Value::from("journey:X1@J0");
    });
    assert!(
        matches!(
            err,
            StoreError::NotWhole(ProjectError::JourneyOnOpenCycle(_))
        ),
        "다른 이유로 거절됐다: {err}"
    );
}

#[test]
fn a_reference_that_is_not_typed_is_refused() {
    // bare `X1` 은 영구 reference 가 아니다(Node Model §2.1).
    let err = tampered("f3-bare-ref", |file| {
        file["current_existence_ref"] = Value::from("X1");
    });
    match err {
        StoreError::BadRef { field, value, .. } => {
            assert_eq!(field, "current_existence_ref");
            assert_eq!(value, "X1");
        }
        other => panic!("다른 이유로 거절됐다: {other}"),
    }
}

// ── 저장은 원자적이다 ─────────────────────────────────────────────────────

#[test]
fn saving_leaves_no_half_written_file_behind() {
    // 완성된 새 파일을 임시 경로에 쓴 뒤 제자리로 옮긴다. 옆자리에 남는 것이 없어야 한다.
    let dir = scratch("f3-atomic");
    let path = dir.join(gil::STATE_PATH);
    save(&Project::start(spec()), &path).expect("눕힐 수 있어야 한다");
    save(&bootstrap(), &path).expect("다시 눕힐 수 있어야 한다");

    let leftovers: Vec<_> = std::fs::read_dir(path.parent().unwrap())
        .unwrap()
        .map(|entry| entry.unwrap().file_name())
        .filter(|name| name.to_string_lossy() != "state.yaml")
        .collect();
    assert!(leftovers.is_empty(), "중간 상태가 남았다: {leftovers:?}");

    // 그리고 마지막에 쓴 것이 그대로 읽힌다.
    let after = load(spec(), &path).expect("다시 세울 수 있어야 한다");
    assert_eq!(after.cycles().current().kind(), CycleKind::Experiment);
}
