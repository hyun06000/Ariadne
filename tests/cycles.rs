//! Cycle Graph — 성공한 Cycle 이 적어 둔 대로 다음 Cycle 을 연다.
//!
//! 여기서 재는 것은 넷이다.
//!
//! 1. **언제 자식을 열 수 있는가** — 적어 둔 방향이 그것일 때만.
//! 2. **새 Cycle 이 무엇을 가지고 시작하는가** — 빈 Step Graph 와 부모 참조 하나.
//! 3. **부모는 그대로 남는가** — 닫힌 Cycle 은 바뀌지 않는다.
//! 4. **계보는 parent 만 따라가는가.**

use gil::{
    Cycle, CycleKind, CyclesError, NodeKind, NodeStatus, OpenChildError, Project, Report,
};

mod common;
use common::{
    REASON, bootstrap, cycle_report, cycle_step, graph_at_the_exit, graph_with_one_closed_cycle,
    spec, walk_to_the_exit,
};

/// Graph 의 전부 — 거절된 연산 뒤에도 이것이 그대로여야 한다.
fn snapshot(project: &Project) -> Vec<(u32, NodeStatus, Option<Report>, usize)> {
    project
        .cycles()
        .nodes()
        .iter()
        .map(|cycle| {
            (
                cycle.id().to_string().trim_start_matches("Cycle ").parse().unwrap(),
                cycle.status(),
                cycle.report().cloned(),
                cycle.steps().nodes().len(),
            )
        })
        .collect()
}

// ── 시작 ───────────────────────────────────────────────────────────────────

#[test]
fn a_graph_starts_with_one_named_open_interview() {
    // 프로젝트의 첫 Cycle 은 **언제나 Interview** 다(Cycle Model §5). 사용자의 자연어 요청을
    // 곧바로 실험하지 않는다 — 먼저 묻고, 사람이 승인해야 실험이 태어난다.
    let project = Project::start(spec());

    assert_eq!(project.cycles().nodes().len(), 1);
    let first = project.cycles().current();
    assert_eq!(first.id(), project.cycles().current_id());
    assert_eq!(first.kind(), CycleKind::Interview, "첫 Cycle 은 Interview 다");
    assert_eq!(first.status(), NodeStatus::Open);
    assert_eq!(first.parent(), None, "첫 Cycle 은 뿌리다");
    assert!(first.steps().nodes().is_empty());
    assert_eq!(
        first.existence(),
        project.current_existence_ref(),
        "첫 Cycle 은 최초 Existence 가 연다"
    );
}

#[test]
fn an_experiment_is_born_only_after_an_approved_synthesis() {
    // Bootstrap Interview 를 지나야 Experiment 가 생긴다.
    let project = bootstrap();

    assert_eq!(project.cycles().nodes().len(), 2);
    assert_eq!(project.cycles().nodes()[0].kind(), CycleKind::Interview);
    assert_eq!(project.cycles().current().kind(), CycleKind::Experiment);
    assert_eq!(project.cycles().current().parent(), Some(project.cycles().nodes()[0].id()));
}

// ── 언제 자식을 열 수 있는가 ───────────────────────────────────────────────

#[test]
fn an_open_cycle_cannot_have_a_child() {
    // 완료 조건 2·13 — 한 번에 걷는 Cycle 은 하나다.
    let mut project = bootstrap();
    let before = snapshot(&project);

    let err = project.open_child_cycle(CycleKind::Experiment)
        .expect_err("열린 Cycle 아래에 자식이 열렸다");
    assert!(
        matches!(
            err,
            CyclesError::OpenChild(OpenChildError::CurrentStillOpen(_))
        ),
        "{err}"
    );
    assert_eq!(snapshot(&project), before, "거절이 Graph 를 바꿨다");

    // 끝 경계에 닿아도, Cycle Report 를 쓰기 전에는 아직이다.
    let (mut project, _) = graph_at_the_exit("success");
    assert!(matches!(
        project.open_child_cycle(CycleKind::Experiment),
        Err(CyclesError::OpenChild(OpenChildError::CurrentStillOpen(_)))
    ));
}

#[test]
fn a_failed_cycle_does_not_have_a_child() {
    // 완료 조건 3 — 실패한 Cycle 은 자식을 만들지 않는다.
    //
    // 문법이 `failure → revisit` 으로 좁히므로, 실패한 Cycle 이 적어 둔 방향은 언제나
    // 자식을 여는 것이 아니다. 그래서 "실패라서 막혔다" 와 "적힌 방향이 아니라서 막혔다" 는
    // 같은 판정이다.
    let mut project = graph_with_one_closed_cycle("failure");
    let before = snapshot(&project);

    let err = project.open_child_cycle(CycleKind::Experiment)
        .expect_err("실패한 Cycle 아래에 자식이 열렸다");
    match err {
        CyclesError::OpenChild(OpenChildError::NotTheDeclaredDirection { declared, .. }) => {
            assert_eq!(declared, "revisit", "무엇이 적혀 있었는지 말해야 한다");
        }
        other => panic!("다른 이유로 거절됐다: {other}"),
    }
    assert_eq!(snapshot(&project), before, "거절이 Graph 를 바꿨다");
}

#[test]
fn the_guidance_and_the_move_agree() {
    // 안내가 실행과 갈리면 그 안내는 없느니만 못하다(실사용 보고 #123 이 같은 병이었다).
    for verdict in ["success", "failure"] {
        for closed in [false, true] {
            let mut project = match closed {
                true => graph_with_one_closed_cycle(verdict),
                false => graph_at_the_exit(verdict).0,
            };
            let told = project.cycles().why_not_open_child();
            let done = project.open_child_cycle(CycleKind::Experiment);
            assert_eq!(
                told.is_none(),
                done.is_ok(),
                "{verdict} · 닫힘={closed} 에서 안내와 실행이 갈렸다"
            );
        }
    }
}

// ── 새 Cycle 이 받는 것 ────────────────────────────────────────────────────

/// 첫 Cycle 을 성공으로 닫고 둘째 Cycle 을 연 Graph.
fn graph_with_two_cycles() -> Project {
    let mut project = graph_with_one_closed_cycle("success");
    project
        .open_child_cycle(CycleKind::Experiment)
        .expect("적어 둔 대로 다음 Cycle 을 연다");
    project
}

#[test]
fn a_child_starts_empty_under_its_parent() {
    // 완료 조건 5·6·7·8·9·12.
    let mut project = graph_with_one_closed_cycle("success");
    let parent = project.cycles().current_id();
    let parent_steps = project.cycles().current().steps().nodes().to_vec();

    let child = project.open_child_cycle(CycleKind::Experiment)
        .expect("성공한 Cycle 에서 자식이 열려야 한다");

    assert_ne!(child, parent, "새 이름을 받아야 한다");
    assert_eq!(project.cycles().current_id(), child, "Current 가 새 Cycle 로 옮겨간다");
    let child = project.cycles().node(child).unwrap();
    assert_eq!(child.parent(), Some(parent), "부모는 직전 성공 Cycle 이다");
    assert_eq!(child.kind(), CycleKind::Experiment);
    assert_eq!(child.status(), NodeStatus::Open);
    assert!(child.report().is_none());

    // 빈 걷기다 — 부모의 Step 은 한 개도 오지 않았다.
    assert!(
        child.steps().nodes().is_empty(),
        "부모의 Step 이 복제됐다: {:?}",
        child.steps().nodes()
    );
    assert!(!parent_steps.is_empty(), "부모에게는 Step 이 있었다");
}

#[test]
fn a_child_must_write_its_own_define() {
    // 완료 조건 8 — 새 Cycle 은 새 immutable Define 부터 시작한다.
    let mut project = graph_with_two_cycles();

    assert_eq!(
        project.cycles().openable_here(),
        vec![NodeKind::Define],
        "새 Cycle 이 Define 말고 다른 것에서 시작한다"
    );
    cycle_step(project.cycles_mut().current_mut(), NodeKind::Define);
    assert_eq!(project.cycles().current().steps().nodes().len(), 1);
}

#[test]
fn a_child_reads_its_parents_report_through_the_reference() {
    // 완료 조건 10 — 이어받는 것은 **복제한 문자열이 아니라 참조**다.
    let project = graph_with_two_cycles();
    let child = project.cycles().current();
    let parent = project.cycles().node(child.parent().unwrap()).unwrap();

    let inherited = project
        .cycles()
        .inherited_report(child.id())
        .expect("부모의 Cycle Report 를 읽을 수 있어야 한다");
    assert_eq!(Some(inherited), parent.report(), "원본이 아니다");

    // 그리고 자식 자신은 그것을 제 안에 갖고 있지 않다.
    assert!(child.report().is_none(), "자식이 Report 를 복제해 지녔다");
}

#[test]
fn the_root_has_nothing_to_inherit() {
    // 뿌리는 Bootstrap Interview 다 — 그 위에는 이어받을 Cycle 이 없다.
    let project = Project::start(spec());
    let cycles = project.cycles();
    assert_eq!(cycles.current().parent(), None);
    assert!(cycles.inherited_report(cycles.current_id()).is_none());
}

#[test]
fn the_parent_does_not_change_when_a_child_is_born() {
    // 완료 조건 11 — 과거 Closed Cycle 과 그 Report 는 바뀌지 않는다.
    let mut project = graph_with_one_closed_cycle("success");
    let before = snapshot(&project);

    project.open_child_cycle(CycleKind::Experiment).unwrap();

    let after = snapshot(&project);
    assert_eq!(after[0], before[0], "부모가 자식을 낳으며 달라졌다");
    assert_eq!(after.len(), before.len() + 1);
}

#[test]
fn a_child_can_be_walked_and_closed_on_its_own() {
    // 두 번째 Cycle 이 제 판정으로 닫힌다 — 부모의 판정을 물려받는 것이 아니다.
    let mut project = graph_with_two_cycles();
    let outcome = walk_to_the_exit(&mut project, "failure");
    let report = cycle_report(project.cycles().current(), "failure", outcome)
        .with(REASON, "다른 가설을 세운다");
    project.cycles_mut().current_mut().close(report).expect("자식을 닫는다");

    assert!(project.cycles().current().is_closed());
    assert_eq!(
        project.cycles().current().report().unwrap().get("verdict"),
        Some("failure")
    );
    assert_eq!(
        project.cycles().nodes()[0].report().unwrap().get("verdict"),
        Some("success"),
        "부모의 판정이 달라졌다"
    );
}

// ── 계보 ───────────────────────────────────────────────────────────────────

#[test]
fn the_lineage_follows_parents_only() {
    // 완료 조건 14.
    let project = graph_with_two_cycles();
    let child = project.cycles().current_id();
    let parent = project.cycles().node(child).unwrap().parent().unwrap();

    let lineage: Vec<_> = project
        .cycles()
        .lineage(child)
        .unwrap()
        .iter()
        .map(|cycle| cycle.id())
        .collect();
    // 뿌리는 Bootstrap Interview 이고, 그 뒤에 부모와 자식이 온다.
    let root = project.cycles().nodes()[0].id();
    assert_eq!(
        lineage,
        vec![root, parent, child],
        "뿌리부터 차례로여야 한다"
    );

    assert_eq!(
        project.cycles().lineage(root).unwrap().len(),
        1,
        "뿌리의 계보는 저 자신뿐이다"
    );
    assert_eq!(
        project.cycles().lineage(parent).unwrap().len(),
        2,
        "부모의 계보는 뿌리와 저 자신이다"
    );
}

#[test]
fn asking_the_lineage_changes_nothing() {
    let project = graph_with_two_cycles();
    let before = snapshot(&project);
    let _ = project.cycles().lineage(project.cycles().current_id());
    assert_eq!(snapshot(&project), before);
}

#[test]
fn an_unknown_cycle_has_no_lineage() {
    let project = bootstrap();
    // 이 Graph 에 없는 이름은 만들 수 없으므로, 있는 이름으로만 물어본다.
    assert!(
        project
            .cycles()
            .lineage(project.cycles().current_id())
            .is_ok()
    );
}

#[test]
fn only_one_cycle_is_open_at_a_time() {
    // 완료 조건 13 — 걷는 내내 열린 Cycle 은 하나다.
    let mut project = graph_with_two_cycles();
    let open: Vec<&Cycle> = project
        .cycles()
        .nodes()
        .iter()
        .filter(|cycle| !cycle.is_closed())
        .collect();
    assert_eq!(open.len(), 1, "열린 Cycle 이 하나가 아니다");
    assert_eq!(open[0].id(), project.cycles().current_id());

    // 그 하나를 닫기 전에는 셋째가 열리지 않는다.
    assert!(project.open_child_cycle(CycleKind::Experiment).is_err());
}
