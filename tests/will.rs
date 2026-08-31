//! Current Will — **지금 무엇을 하려는가가 세계와 함께 눕는다.**
//!
//! 여기서 재는 것은 넷이다.
//!
//! 1. **행동 계약 없이는 실행형 자리가 열리지 않는다** — GIL 은 그것을 지어내지 않는다.
//! 2. **원자성** — Node·Will·판·allocator 는 함께 움직이거나 하나도 안 움직인다.
//! 3. **컨테이너는 다르다** — Cycle 은 Will 도 판도 만들지 않는다.
//! 4. **파일은 두 번째 통로다** — 손으로 고친 Will 과 판을 되살리기가 거절한다.
//!
//! 이 시험들이 있는 까닭은 실사용에서 값을 치렀기 때문이다(Roadmap M2C): `gil context` 로
//! 상태와 가설을 정확히 복원한 Agent 가, 열린 Verify 에서 무엇을 먼저 해야 하는지 몰라
//! **검증하기도 전에** `gil close` 를 불렀다.

use std::path::Path;

use gil::{
    ActionContract, ActionError, ContractError, CycleKind, NodeKind, Project, ProjectError, Report,
    StoreError, load, save,
};
use serde_norway::Value;

mod common;
use common::{
    bootstrap, contract, full_report, graph_at_the_exit, opened, plan, scratch, spec, step_id,
    walked,
};

/// 지금 이 프로젝트의 Journey 를 그대로 본다.
fn journey(project: &Project) -> &gil::Journey {
    project.current_existence().journey()
}

/// 판이 몇 개인가 — Open 으로는 늘지 않고 실행형 Close 로만 는다.
fn revisions(project: &Project) -> usize {
    journey(project).revisions().count()
}

/// 걷기와 존재의 전부 — 거절된 transaction 뒤에도 이것이 그대로여야 한다.
#[derive(Debug, PartialEq, Eq)]
struct Snapshot {
    next_will_id: u32,
    active: Option<String>,
    done: Vec<String>,
    revisions: usize,
    current_journey: String,
    steps: Vec<(String, gil::NodeStatus, Option<String>)>,
    cycle_closed: bool,
}

fn snapshot(project: &Project) -> Snapshot {
    let cycle = project.cycles().current();
    Snapshot {
        next_will_id: project.next_will_id(),
        active: project.active_will().map(|will| will.id().to_string()),
        done: journey(project)
            .done_wills()
            .iter()
            .map(|will| will.id().to_string())
            .collect(),
        revisions: revisions(project),
        current_journey: project.current_existence().current_journey().to_string(),
        steps: cycle
            .steps()
            .nodes()
            .iter()
            .map(|node| {
                (
                    node.id.to_string(),
                    node.status,
                    node.journey.map(|j| j.to_string()),
                )
            })
            .collect(),
        cycle_closed: cycle.is_closed(),
    }
}

// ── ① 행동 계약 ────────────────────────────────────────────────────────────

#[test]
fn all_three_contract_fields_are_required() {
    // GIL 은 Node Kind 만 보고 구체적인 Will 을 지어내지 않는다(Will Model §7).
    let whole = Report::new()
        .with("objective", "가설을 검증한다")
        .with("next_action", "테스트를 실행한다")
        .with("done_when", "결과를 관측한다");
    ActionContract::from_report(&whole).expect("셋 다 적혔으면 계약이 된다");

    for missing in ["objective", "next_action", "done_when"] {
        let mut report = whole.clone();
        report.remove(missing);
        let err = ActionContract::from_report(&report).expect_err("빠졌는데 통과했다");
        let ContractError::Missing { fields } = &err;
        assert_eq!(fields, &[missing], "무엇이 빠졌는지 틀리게 말한다: {err}");
    }
}

#[test]
fn a_blank_contract_field_is_the_same_failure_as_a_missing_one() {
    // 빠뜨린 것과 비워 둔 것은 사람이 할 일이 같다 — 그 칸을 적어라. 오류를 둘로 늘리지 않는다.
    for blank in ["", "   ", "\n\n"] {
        let report = Report::new()
            .with("objective", "가설을 검증한다")
            .with("next_action", blank)
            .with("done_when", "결과를 관측한다");
        let err = ActionContract::from_report(&report).expect_err("비었는데 통과했다");
        let ContractError::Missing { fields } = &err;
        assert_eq!(fields, &["next_action"], "{blank:?} 가 다르게 읽혔다");
    }
}

#[test]
fn the_contract_that_was_written_is_the_contract_that_is_kept() {
    // 적은 글자가 그대로 값이 된다 — Report 와 같은 규율이다.
    let mut project = Project::start(spec(), common::first_world());
    let written = contract(
        "사용자의 프로젝트 목표를 확인한다",
        "목표의 종류를 선택지와 함께 질문한다",
        "사용자의 원문 응답을 얻는다",
    );
    let opened = project
        .open_action_step(NodeKind::Question, written)
        .expect("계약과 함께 열린다");

    let will = project.active_will().expect("걸린 행동이 있다");
    assert_eq!(will.id().to_string(), "will:W1");
    assert_eq!(will.target(), opened.step);
    assert_eq!(will.existence(), project.current_existence_ref());
    assert_eq!(will.objective(), "사용자의 프로젝트 목표를 확인한다");
    assert_eq!(will.next_action(), "목표의 종류를 선택지와 함께 질문한다");
    assert_eq!(will.done_when(), "사용자의 원문 응답을 얻는다");
}

// ── ② 원자적 Open ──────────────────────────────────────────────────────────

#[test]
fn a_refused_open_leaves_the_node_the_will_and_the_allocator_alone() {
    // Node 만 있거나 Will 만 있는 중간 상태를 허용하지 않는다(Will Model §7).
    let mut project = Project::start(spec(), common::first_world());
    let before = snapshot(&project);

    // Interview 의 시작 경계에서 define 은 열리지 않는다 — 문법이 먼저 거절한다.
    let err = project
        .open_action_step(NodeKind::Define, plan(NodeKind::Define))
        .expect_err("Interview 안에서 define 이 열렸다");
    assert!(matches!(err, ActionError::Cycle(_)), "{err}");

    assert_eq!(snapshot(&project), before, "거절된 Open 이 무언가를 남겼다");
    assert_eq!(project.next_will_id(), 1, "이름만 축났다");
    assert!(project.cycles().current().steps().nodes().is_empty());
}

#[test]
fn a_second_active_will_is_refused_and_opens_nothing() {
    // 지금 하려는 행동은 하나다(Will Model §5).
    let mut project = Project::start(spec(), common::first_world());
    opened(&mut project, NodeKind::Question);
    let before = snapshot(&project);

    let err = project
        .open_action_step(NodeKind::Interpretation, plan(NodeKind::Interpretation))
        .expect_err("두 번째 행동이 걸렸다");
    assert!(
        matches!(err, ActionError::WillAlreadyActive { .. }),
        "{err}"
    );
    assert_eq!(snapshot(&project), before, "거절된 Open 이 무언가를 남겼다");
}

#[test]
fn opening_does_not_raise_the_journey_revision() {
    // 판은 **확정된 내용이 바뀔 때만** 는다. Open 은 register 를 채울 뿐이다.
    let mut project = Project::start(spec(), common::first_world());
    let before = revisions(&project);
    opened(&mut project, NodeKind::Question);

    assert_eq!(revisions(&project), before, "Open 이 판을 올렸다");
    assert_eq!(
        project.current_existence().current_journey().to_string(),
        "journey:X1@J0",
        "Open 이 서 있는 판을 옮겼다"
    );
    assert!(
        journey(&project).done_wills().is_empty(),
        "열자마자 끝난 행동이 생겼다"
    );
}

// ── ③ 원자적 Close ─────────────────────────────────────────────────────────

#[test]
fn closing_moves_the_same_will_and_raises_exactly_one_revision() {
    let mut project = Project::start(spec(), common::first_world());
    let opened = project
        .open_action_step(
            NodeKind::Question,
            contract("호칭을 확인한다", "선택지와 함께 묻는다", "원문 응답을 얻는다"),
        )
        .expect("연다");
    let step = opened.step;
    let report = full_report(spec_of(&project), CycleKind::Interview, NodeKind::Question);

    let closed = project.close_action_step(report).expect("닫힌다");

    assert_eq!(closed.step, step);
    assert_eq!(closed.will.to_string(), "will:W1");
    assert_eq!(closed.journey.to_string(), "journey:X1@J1");

    // ⑥⑦ 같은 객체가 register 에서 목록 끝으로 **옮겨졌다** — 베껴지지 않았다.
    assert!(project.active_will().is_none(), "register 가 안 비었다");
    let done = journey(&project).done_wills();
    assert_eq!(done.len(), 1);
    assert_eq!(done[0].target(), step, "다른 자리의 행동이 끝난 것이 됐다");
    assert_eq!(
        done[0].next_action(),
        "선택지와 함께 묻는다",
        "옮기면서 내용이 바뀌었다"
    );

    // ⑧⑨⑩ 판이 하나 늘고, 머리만 옮겨 붙고, 서 있는 자리가 그리로 갔다.
    assert_eq!(revisions(&project), 2, "판이 하나만 늘어야 한다");
    let now = project.current_existence().current_revision().expect("판이 있다");
    let was = journey(&project).revision(0).expect("J0 이 있다");
    assert_eq!(now.will_head().map(|w| w.to_string()).as_deref(), Some("will:W1"));
    assert_eq!(
        now.existence_state(),
        was.existence_state(),
        "State 머리를 물려받지 않았다"
    );
    assert_eq!(now.knowledge_head(), was.knowledge_head());
    assert_eq!(now.memory_head(), was.memory_head());
    assert_eq!(now.relations_head(), was.relations_head());
    assert!(was.will_head().is_none(), "지난 판이 다시 쓰였다");

    // ⑪ 그리고 Node 가 그 판을 provenance 로 지닌다.
    let cycle = project.cycles().current();
    let node = cycle.steps().node(step_id(&project, step)).expect("자리가 있다");
    assert_eq!(node.journey.map(|j| j.to_string()).as_deref(), Some("journey:X1@J1"));
    assert_eq!(node.existence, project.current_existence_ref());
}

#[test]
fn a_refused_close_keeps_the_open_step_the_active_will_and_the_journey() {
    // 하나라도 실패하면 전부 이전 상태다(Will Model §7).
    let mut project = Project::start(spec(), common::first_world());
    opened(&mut project, NodeKind::Question);
    let before = snapshot(&project);

    let err = project
        .close_action_step(Report::new().with("question", "칸이 모자란다"))
        .expect_err("모자란 Report 로 닫혔다");
    assert!(matches!(err, ActionError::Cycle(_)), "{err}");

    assert_eq!(snapshot(&project), before, "거절된 Close 가 무언가를 남겼다");
    assert!(project.active_will().is_some(), "행동이 풀렸다");
    assert_eq!(revisions(&project), 1, "거절됐는데 판이 늘었다");
}

#[test]
fn closing_without_an_active_will_is_refused() {
    // 걸어서는 만들 수 없는 자리다 — Cycle 층으로 문법만 걷고 통합 Close 를 부르면 여기 온다.
    let mut project = Project::start(spec(), common::first_world());
    project
        .cycles_mut()
        .current_mut()
        .open_step(NodeKind::Question)
        .expect("Step Graph 만 보면 열린다");

    let report = full_report(spec_of(&project), CycleKind::Interview, NodeKind::Question);
    let err = project
        .close_action_step(report)
        .expect_err("행동 없이 닫혔다");
    assert!(matches!(err, ActionError::NoActiveWill { .. }), "{err}");
}

#[test]
fn a_done_will_does_not_mean_the_hypothesis_succeeded() {
    // Will 의 done 은 **행동을 했다**는 뜻이다(Will Model §6). 관측이 실패여도 행동은 끝난다.
    let (project, _) = graph_at_the_exit("failure");

    let outcome = project
        .cycles()
        .current()
        .steps()
        .nodes()
        .iter()
        .find(|node| node.kind == NodeKind::Outcome)
        .expect("판정이 있다");
    assert_eq!(
        outcome.report.as_ref().and_then(|r| r.get("verdict")),
        Some("failure"),
        "판정이 실패여야 이 시험이 뜻을 갖는다"
    );

    let done = journey(&project).done_wills();
    assert!(
        done.iter().any(|will| will.target()
            == project.cycles().current().step_ref(outcome.id)),
        "실패로 닫힌 자리의 행동이 끝난 것으로 남지 않았다"
    );
}

// ── ④ 이름은 프로젝트 전체에서 유일하다 ───────────────────────────────────

#[test]
fn will_names_come_from_the_project_root_and_are_never_reused() {
    let mut project = Project::start(spec(), common::first_world());
    let mut names = Vec::new();
    for kind in [NodeKind::Question, NodeKind::Interpretation] {
        walked(&mut project, kind);
        names.push(
            journey(&project)
                .last_done_will()
                .expect("방금 끝냈다")
                .id()
                .to_string(),
        );
    }
    assert_eq!(names, ["will:W1", "will:W2"]);
    assert_eq!(project.next_will_id(), 3, "발급기가 안 올라갔다");

    // Cycle 이 바뀌어도 이어서 발급한다 — Existence 별이 아니라 프로젝트 전체다.
    let mut project = bootstrap();
    let before = project.next_will_id();
    walked(&mut project, NodeKind::Define);
    assert_eq!(
        journey(&project).last_done_will().unwrap().id().number(),
        before,
        "다음 Cycle 이 이름을 되감았다"
    );
}

// ── ⑤ 컨테이너 Cycle ───────────────────────────────────────────────────────

#[test]
fn opening_a_cycle_makes_no_will() {
    // 그릇은 장기 Active Will 을 점유하지 않는다(Will Model §5).
    let project = bootstrap();
    assert!(project.active_will().is_none(), "Cycle 을 여는데 행동이 걸렸다");
    assert_eq!(
        project.cycles().current().kind(),
        CycleKind::Experiment,
        "bootstrap 이 자식 Cycle 을 열어 둔다"
    );
}

#[test]
fn closing_a_cycle_makes_no_revision_and_records_the_current_one() {
    let (mut project, outcome) = graph_at_the_exit("success");
    let before = revisions(&project);
    let standing = project.current_existence().current_journey();
    let done = journey(&project).done_wills().len();

    let report = common::cycle_report(project.cycles().current(), "success", outcome);
    let closed = project.close_cycle(report).expect("Cycle 을 닫는다");

    assert_eq!(revisions(&project), before, "컨테이너 Close 가 판을 올렸다");
    assert_eq!(closed.journey, standing, "그때 서 있던 판이 아니다");
    assert_eq!(
        project.cycles().current().journey(),
        Some(standing),
        "Cycle 이 provenance 를 안 지녔다"
    );
    assert_eq!(
        journey(&project).done_wills().len(),
        done,
        "컨테이너 Close 가 행동을 끝냈다"
    );
}

#[test]
fn a_cycle_with_an_open_step_inside_is_not_closed() {
    let mut project = bootstrap();
    opened(&mut project, NodeKind::Define);
    let before = snapshot(&project);

    let report = full_report(spec_of(&project), CycleKind::Experiment, NodeKind::Outcome);
    let err = project
        .close_cycle(report)
        .expect_err("안이 열린 채로 그릇이 닫혔다");
    assert!(
        matches!(err, ActionError::InnerStepStillOpen { .. }),
        "{err}"
    );
    assert_eq!(snapshot(&project), before, "거절된 Close 가 무언가를 남겼다");
}

// ── ⑥ 파일은 두 번째 통로다 ───────────────────────────────────────────────

fn edit_file(path: &Path, edit: impl FnOnce(&mut Value)) {
    let text = std::fs::read_to_string(path).expect("저장된 파일을 읽을 수 있어야 한다");
    let mut file: Value = serde_norway::from_str(&text).expect("저장 파일은 YAML 이다");
    edit(&mut file);
    std::fs::write(path, serde_norway::to_string(&file).unwrap()).unwrap();
}

/// 걸어서 만든 것을 눕힌 뒤 손으로 고치고, 되살리기가 거절하는 이유를 돌려준다.
fn tampered(project: &Project, label: &str, edit: impl FnOnce(&mut Value)) -> ProjectError {
    let path = scratch(label).join(gil::STATE_PATH);
    save(project, &path).unwrap();
    edit_file(&path, edit);

    match load(spec(), &path) {
        Err(StoreError::NotWhole(err)) => err,
        other => panic!("걸어서 만들 수 없는 파일이 되살아났다: {other:?}"),
    }
}

/// `#1 question` 을 닫고 `#2 interpretation` 을 **열어 둔** 프로젝트 — W1 done · W2 active.
fn one_done_and_one_active() -> Project {
    let mut project = Project::start(spec(), common::first_world());
    walked(&mut project, NodeKind::Question);
    opened(&mut project, NodeKind::Interpretation);
    project
}

/// 그 존재의 Journey 를 손으로 가리킨다.
fn x1<'a>(file: &'a mut Value) -> &'a mut Value {
    &mut file["existences"]["X1"]["journey"]
}

#[test]
fn a_walked_project_with_wills_comes_back_whole() {
    // 검사를 조인 만큼, 걸어서 만든 것은 그대로 되살아나야 한다.
    let before = one_done_and_one_active();
    let path = scratch("will-roundtrip").join(gil::STATE_PATH);
    save(&before, &path).unwrap();
    let after = load(spec(), &path).expect("걸어서 만든 것이 되살아나지 못했다");

    assert_eq!(after.next_will_id(), before.next_will_id());
    assert_eq!(
        after.active_will().map(|w| w.id()),
        before.active_will().map(|w| w.id())
    );
    assert_eq!(
        after.active_will().map(|w| w.next_action().to_string()),
        before.active_will().map(|w| w.next_action().to_string()),
        "하려는 일이 프로세스를 못 넘었다"
    );
    assert_eq!(
        journey(&after).done_wills().len(),
        journey(&before).done_wills().len()
    );
}

#[test]
fn an_allocator_that_already_gave_out_its_next_name_is_refused() {
    let err = tampered(&one_done_and_one_active(), "will-allocator", |file| {
        file["next_will_id"] = Value::from(2);
    });
    assert!(
        matches!(err, ProjectError::WillAllocatorTooSmall { .. }),
        "{err}"
    );
}

#[test]
fn the_same_will_name_twice_is_refused() {
    let err = tampered(&one_done_and_one_active(), "will-duplicate", |file| {
        x1(file)["active_will"]["id"] = Value::from("W1");
    });
    assert!(matches!(err, ProjectError::DuplicateWill(_)), "{err}");
}

#[test]
fn an_active_will_owned_by_another_existence_is_refused() {
    let err = tampered(&one_done_and_one_active(), "will-other-owner", |file| {
        x1(file)["active_will"]["existence_ref"] = Value::from("existence:X2");
    });
    assert!(
        matches!(err, ProjectError::WillOfAnotherExistence { .. }),
        "{err}"
    );
}

#[test]
fn an_active_will_that_targets_another_step_is_refused() {
    // Current Will 은 **가장 깊은 실행형 Open Node** 하나에 대응한다(Will Model §5).
    let err = tampered(&one_done_and_one_active(), "will-other-target", |file| {
        x1(file)["active_will"]["target_node_ref"] = Value::from("step:C1/S1");
    });
    assert!(
        matches!(err, ProjectError::ActiveWillTargetsElsewhere { .. }),
        "{err}"
    );
}

#[test]
fn an_open_action_step_without_an_active_will_is_refused() {
    let err = tampered(&one_done_and_one_active(), "will-missing", |file| {
        x1(file)["active_will"] = Value::Null;
    });
    assert!(
        matches!(err, ProjectError::OpenStepWithoutActiveWill(_)),
        "{err}"
    );
}

#[test]
fn an_active_will_without_an_open_action_step_is_refused() {
    let mut project = Project::start(spec(), common::first_world());
    walked(&mut project, NodeKind::Question);
    let err = tampered(&project, "will-orphan", |file| {
        x1(file)["active_will"] = serde_norway::from_str(
            "id: W2\nexistence_ref: existence:X1\ntarget_node_ref: step:C1/S1\n\
             objective: 무엇을\nnext_action: 무엇을\ndone_when: 무엇을\n",
        )
        .unwrap();
        file["next_will_id"] = Value::from(3);
    });
    assert!(
        matches!(err, ProjectError::ActiveWillWithoutOpenStep { .. }),
        "{err}"
    );
}

#[test]
fn a_done_will_that_is_also_in_the_register_is_refused() {
    // 옮기는 것이지 베끼는 것이 아니다 — 같은 객체가 두 자리에 동시에 있을 수 없다.
    let mut project = Project::start(spec(), common::first_world());
    walked(&mut project, NodeKind::Question);
    opened(&mut project, NodeKind::Interpretation);

    let err = tampered(&project, "will-in-both", |file| {
        let done = x1(file)["done_wills"][0].clone();
        x1(file)["active_will"] = done;
    });
    assert!(matches!(err, ProjectError::DuplicateWill(_)), "{err}");
}

#[test]
fn done_wills_in_a_forged_order_are_refused() {
    // 한 존재는 한 번에 하나씩 걸고 끝내므로 끝낸 순서는 곧 발급 순서다.
    // 시각을 저장하지 않고도 순서 위조를 잡는 근거가 그것이다.
    let mut project = Project::start(spec(), common::first_world());
    walked(&mut project, NodeKind::Question);
    walked(&mut project, NodeKind::Interpretation);

    let err = tampered(&project, "will-reordered", |file| {
        let list = x1(file)["done_wills"].as_sequence().unwrap().clone();
        x1(file)["done_wills"] =
            Value::Sequence(list.into_iter().rev().collect());
    });
    assert!(
        matches!(err, ProjectError::DoneWillsOutOfOrder { .. }),
        "{err}"
    );
}

#[test]
fn a_revision_head_that_points_at_no_done_will_is_refused() {
    let mut project = Project::start(spec(), common::first_world());
    walked(&mut project, NodeKind::Question);

    let err = tampered(&project, "will-head-ghost", |file| {
        x1(file)["revisions"]["J1"]["will_head_ref"] = Value::from("will:W9");
        file["next_will_id"] = Value::from(10);
    });
    assert!(matches!(err, ProjectError::UnknownWillHead { .. }), "{err}");
}

#[test]
fn a_revision_head_that_looks_past_its_own_moment_is_refused() {
    // 앞선 판이 나중에 끝난 행동을 가리키면 그 판은 제 시점보다 뒤를 본 것이다.
    let mut project = Project::start(spec(), common::first_world());
    walked(&mut project, NodeKind::Question);
    walked(&mut project, NodeKind::Interpretation);

    let err = tampered(&project, "will-head-future", |file| {
        x1(file)["revisions"]["J1"]["will_head_ref"] = Value::from("will:W2");
        x1(file)["revisions"]["J2"]["will_head_ref"] = Value::from("will:W1");
    });
    assert!(
        matches!(err, ProjectError::WillHeadWentBackwards { .. }),
        "{err}"
    );
}

#[test]
fn a_current_head_that_is_not_the_last_done_will_is_refused() {
    let mut project = Project::start(spec(), common::first_world());
    walked(&mut project, NodeKind::Question);
    walked(&mut project, NodeKind::Interpretation);

    let err = tampered(&project, "will-head-stale", |file| {
        x1(file)["revisions"]["J2"]["will_head_ref"] = Value::from("will:W1");
    });
    assert!(
        matches!(err, ProjectError::CurrentWillHeadIsNotTheLast { .. }),
        "{err}"
    );
}

#[test]
fn a_closed_step_whose_journey_does_not_hold_its_will_is_refused() {
    // 실행형 Close 는 방금 끝낸 행동을 새 판의 머리로 둔다 — 그 둘이 갈리면 위조다.
    let mut project = Project::start(spec(), common::first_world());
    walked(&mut project, NodeKind::Question);
    walked(&mut project, NodeKind::Interpretation);

    let err = tampered(&project, "will-journey-mismatch", |file| {
        file["cycles"]["nodes"][0]["steps"]["nodes"][0]["journey_ref"] =
            Value::from("journey:X1@J2");
    });
    assert!(
        matches!(err, ProjectError::JourneyDoesNotHoldItsWill { .. }),
        "{err}"
    );
}

#[test]
fn a_provenance_that_points_at_no_revision_is_refused() {
    let mut project = Project::start(spec(), common::first_world());
    walked(&mut project, NodeKind::Question);

    let err = tampered(&project, "will-journey-ghost", |file| {
        file["cycles"]["nodes"][0]["steps"]["nodes"][0]["journey_ref"] =
            Value::from("journey:X1@J9");
    });
    assert!(
        matches!(err, ProjectError::UnknownProvenanceJourney(_)),
        "{err}"
    );
}

#[test]
fn a_closed_cycle_without_its_journey_is_refused() {
    let mut project = bootstrap();
    let outcome = common::walk_to_the_exit(&mut project, "success");
    let report = common::cycle_report(project.cycles().current(), "success", outcome);
    project.close_cycle(report).expect("Cycle 을 닫는다");

    let err = tampered(&project, "will-cycle-no-journey", |file| {
        file["cycles"]["nodes"][0]["journey_ref"] = Value::Null;
    });
    assert!(
        matches!(err, ProjectError::ClosedCycleWithoutJourney(_)),
        "{err}"
    );
}

// ── ⑦ 읽는 쪽 ──────────────────────────────────────────────────────────────

#[test]
fn the_context_carries_the_whole_action_contract() {
    // Context 는 지금 무엇이 참인지 말하고, Will 은 지금 무엇을 하려는지 말한다.
    let mut project = bootstrap();
    project
        .open_action_step(
            NodeKind::Define,
            contract(
                "환경 변수 파싱의 fallback 을 정한다",
                "지금 구현이 숫자가 아닌 값을 어떻게 다루는지 읽는다",
                "현재 동작을 한 문장으로 적을 수 있다",
            ),
        )
        .expect("연다");

    let told = gil::context(&project);
    for line in [
        "환경 변수 파싱의 fallback 을 정한다",
        "지금 구현이 숫자가 아닌 값을 어떻게 다루는지 읽는다",
        "현재 동작을 한 문장으로 적을 수 있다",
    ] {
        assert!(told.contains(line), "{line:?} 가 context 에 없다:\n{told}");
    }
    assert!(told.contains("step:C2/S1"), "어느 자리의 행동인지 안 말한다");
}

#[test]
fn the_context_does_not_unfold_past_wills() {
    // 이어 걷는 데 필요한 것은 **지금 걸린 하나**다.
    let mut project = Project::start(spec(), common::first_world());
    project
        .open_action_step(
            NodeKind::Question,
            contract("첫 목표", "지나간 행동이다", "지나간 완료 조건이다"),
        )
        .expect("연다");
    let report = full_report(spec_of(&project), CycleKind::Interview, NodeKind::Question);
    project.close_action_step(report).expect("닫는다");

    project
        .open_action_step(
            NodeKind::Interpretation,
            contract("지금 목표", "지금 하려는 일이다", "지금의 완료 조건이다"),
        )
        .expect("연다");

    let told = gil::context(&project);
    assert!(told.contains("지금 하려는 일이다"), "{told}");
    assert!(
        !told.contains("지나간 행동이다"),
        "끝난 행동까지 펼쳤다:\n{told}"
    );
}

#[test]
fn the_context_does_not_invent_a_missing_will() {
    // Current Will 이 없다면 GIL 은 다음 작업을 추측하지 않고 **없음을 명시한다**.
    let project = Project::start(spec(), common::first_world());
    let told = gil::context(&project);
    assert!(told.contains("걸린 행동이 없다"), "{told}");
}

fn spec_of(project: &Project) -> &gil::RuleSet {
    project.cycles().rules()
}

#[test]
fn a_new_revision_inherits_every_head_it_did_not_change() {
    // 판이 하나 늘었다는 이유로 **아직 짓지도 않은 머리**를 새로 만들지 않는다. 여기서는
    // Knowledge·Memory·Relations 를 아직 짓지 않아 걸어서는 그 차이를 낼 수 없으므로,
    // 파일에 머리를 심어 두고 그 다음 Close 가 그것을 그대로 물려받는지 잰다.
    let mut project = Project::start(spec(), common::first_world());
    walked(&mut project, NodeKind::Question);

    let path = scratch("will-inherit").join(gil::STATE_PATH);
    save(&project, &path).unwrap();
    edit_file(&path, |file| {
        let head = &mut x1(file)["revisions"]["J1"];
        head["knowledge_head_ref"] = Value::from("knowledge:K18");
        head["memory_head_ref"] = Value::from("memory:M11");
        head["relations_head_ref"] = Value::from("relation:R4");
    });

    let mut project = load(spec(), &path).expect("머리가 실린 파일은 되살아난다");
    walked(&mut project, NodeKind::Interpretation);

    let now = project
        .current_existence()
        .current_revision()
        .expect("판이 있다");
    assert_eq!(
        now.knowledge_head().map(|h| h.to_string()).as_deref(),
        Some("knowledge:K18"),
        "Knowledge 머리를 물려받지 않았다"
    );
    assert_eq!(
        now.memory_head().map(|h| h.to_string()).as_deref(),
        Some("memory:M11"),
        "Memory 머리를 물려받지 않았다"
    );
    assert_eq!(
        now.relations_head().map(|h| h.to_string()).as_deref(),
        Some("relation:R4"),
        "Relations 머리를 물려받지 않았다"
    );
    assert_eq!(
        now.will_head().map(|h| h.to_string()).as_deref(),
        Some("will:W2"),
        "옮겨야 하는 것은 Will 머리 하나다"
    );
}
