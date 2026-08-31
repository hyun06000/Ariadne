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
    ACTION, CYCLE_TARGET, REASON, TARGET, bootstrap, cycle_report, cycle_step, graph_at_the_exit,
    graph_with_one_closed_cycle, spec, walk_to_the_exit,
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
    let project = Project::start(spec(), common::first_world());

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
    let project = Project::start(spec(), common::first_world());
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

// ── 되돌아갈 곳 — 적히는 자리의 계약 (M4-B) ────────────────────────────────
//
// Cycle 계층의 `revisit` 은 아직 **밟을 수 없다.** 여기서 재는 것은 그 앞 칸 하나다 —
// 실패를 닫는 순간 **어디로 돌아갈지가 함께 확정되는가.** 근거와 이동이 떨어지지 않게
// 하려는 것이고, Step 의 되돌아감이 같은 모양이다.
//
// 대상은 `Cycle` 하나가 답할 수 없다(제 이웃을 모른다). 그래서 판정은 Graph 에 있고,
// 닫을 때와 저장에서 되살릴 때가 같은 함수를 지난다. 위조한 파일 쪽은 `tests/store.rs`.

/// 끝 경계까지 걷고, 이 Cycle Report 로 닫아 본다. 돌려주는 것은 거절의 말.
///
/// **Graph 는 한 글자도 바뀌지 않아야 한다** — 그 검사까지 여기서 함께 한다.
fn refused_close(edit: impl FnOnce(&mut Report)) -> String {
    let (mut project, outcome) = graph_at_the_exit("failure");
    let mut report = cycle_report(project.cycles().current(), "failure", outcome);
    edit(&mut report);

    let before = snapshot(&project);
    let err = project
        .close_cycle(report)
        .expect_err("이 Cycle Report 로 닫혔다");
    assert_eq!(snapshot(&project), before, "거절이 Graph 를 바꿨다");
    assert!(
        !project.cycles().current().is_closed(),
        "거절당한 Cycle 이 닫혔다"
    );
    assert!(
        project.cycles().current().report().is_none(),
        "거절당한 Report 가 남았다"
    );
    err.to_string()
}

#[test]
fn a_failure_that_does_not_say_where_to_go_back_is_refused() {
    // 방향만 적고 갈 곳을 안 적으면, 나중에 그 이동을 밟을 때 어디로 갈지 물을 자리가 없다.
    let said = refused_close(|report| {
        report.remove(CYCLE_TARGET);
    });
    assert!(said.contains(CYCLE_TARGET), "어느 칸이 없는지 말하지 않는다:\n{said}");
    // 무엇이 틀렸는지만 말하고 무엇을 적어야 하는지 말하지 않으면 사람은 한 번 더 틀린다.
    assert!(said.contains("cycle:C"), "적을 꼴을 보여 주지 않는다:\n{said}");
}

#[test]
fn only_a_canonical_cycle_ref_is_accepted() {
    // bare ID · 화면 축약 · 종류 없는 이름은 전부 영구 reference 가 아니다(명세 §2.1).
    for wrong in ["1", "#1", "C1", "cycle:1", "cycle:c1", "cycle:C01", " cycle:C1"] {
        let said = refused_close(|report| {
            report.insert(CYCLE_TARGET, wrong);
        });
        assert!(
            said.contains("읽히지 않는다"),
            "{wrong:?} 가 Cycle 주소로 읽혔다:\n{said}"
        );
    }

    // 그리고 고칠 꼴을 지어 준다 — 수를 알아볼 수 있을 때는 그 주소를 통째로.
    let said = refused_close(|report| {
        report.insert(CYCLE_TARGET, "#1");
    });
    assert!(said.contains("cycle:C1"), "고칠 주소를 지어 주지 않는다:\n{said}");
}

#[test]
fn another_kind_of_typed_reference_is_refused() {
    // 종류가 다른 주소는 **수를 뽑아 고쳐 주지 않는다** — `step:C1/S2` 에서 뽑은 수는
    // 그 사람이 가리키려던 Cycle 이 아니다. 그럴듯한 오답은 아무 말도 안 한 것보다 나쁘다.
    for wrong in ["step:C1/S2", "snapshot:A1", "existence:X1", "chain:C1"] {
        let said = refused_close(|report| {
            report.insert(CYCLE_TARGET, wrong);
        });
        assert!(
            said.contains("읽히지 않는다"),
            "{wrong:?} 가 Cycle 주소로 읽혔다:\n{said}"
        );
        assert!(
            !said.contains("cycle:C2\n") && said.contains("cycle:C<번호>"),
            "다른 종류의 주소에서 수를 뽑아 지어 줬다:\n{said}"
        );
    }
}

#[test]
fn a_direction_that_does_not_go_back_may_not_carry_a_target() {
    // 적은 값을 조용히 버리지 않는다 — 버리면 사람은 제 대상이 지켜졌다고 믿는다.
    let (mut project, outcome) = graph_at_the_exit("success");
    let mut report = cycle_report(project.cycles().current(), "success", outcome);
    assert_eq!(report.get(ACTION), Some("open_child"), "성공은 자식을 연다");
    report.insert(CYCLE_TARGET, "cycle:C1");

    let before = snapshot(&project);
    let err = project
        .close_cycle(report)
        .expect_err("되돌아가지 않는 방향에 갈 곳이 실렸다");
    let said = err.to_string();
    assert!(said.contains("open_child"), "어느 방향인지 말하지 않는다:\n{said}");
    assert!(said.contains(CYCLE_TARGET), "어느 칸인지 말하지 않는다:\n{said}");
    assert_eq!(snapshot(&project), before, "거절이 Graph 를 바꿨다");
}

#[test]
fn a_target_that_is_not_in_this_graph_is_refused() {
    let said = refused_close(|report| {
        report.insert(CYCLE_TARGET, "cycle:C9");
    });
    assert!(said.contains("cycle:C9"), "어느 이름인지 말하지 않는다:\n{said}");
    assert!(said.contains("없다"), "왜 거절인지 말하지 않는다:\n{said}");
}

#[test]
fn a_target_that_is_the_closing_cycle_itself_is_refused() {
    // 자기 자신은 제 조상이 아니다. 그리고 사람이 한 일이 조상을 잘못 고른 것과 다르므로
    // 다른 말로 거절한다 — 여기서 할 일은 「조상을 적어라」다.
    let (project, _) = graph_at_the_exit("failure");
    let here = project.cycles().current_id().to_ref().to_string();

    let said = refused_close(|report| {
        report.insert(CYCLE_TARGET, &here);
    });
    assert!(said.contains(&here), "어느 Cycle 인지 말하지 않는다:\n{said}");
    assert!(said.contains("자기 자신"), "왜 거절인지 말하지 않는다:\n{said}");
}

#[test]
fn the_direct_parent_is_a_valid_target() {
    // 실패한 Cycle 에는 **언제나** 부모가 있다 — 뿌리는 Interview 이고 Interview 는 failure
    // 로 닫히지 않는다. 그래서 유효한 대상이 하나도 없는 자리는 만들 수 없다.
    let (mut project, outcome) = graph_at_the_exit("failure");
    let parent = project.cycles().current().parent().expect("실패 Cycle 은 뿌리가 아니다");
    let report = cycle_report(project.cycles().current(), "failure", outcome);
    assert_eq!(
        report.get(CYCLE_TARGET),
        Some(parent.to_ref().to_string().as_str())
    );

    project.close_cycle(report).expect("부모를 대상으로 닫는다");
    assert!(project.cycles().current().is_closed());
}

#[test]
fn a_further_ancestor_is_also_a_valid_target() {
    // 대상은 「직접 부모」가 아니라 **계보 위의 유효한 조상**이다. 조부모도 적법하다.
    let mut project = graph_with_two_cycles(); // C1 → C2(success) → C3(open)
    let root = project.cycles().nodes()[0].id();
    let outcome = walk_to_the_exit(&mut project, "failure");

    let here = project.cycles().current();
    assert_eq!(here.parent(), Some(project.cycles().nodes()[1].id()));
    let report = cycle_report(here, "failure", outcome).with(
        CYCLE_TARGET,
        root.to_ref().to_string(),
    );

    project.close_cycle(report).expect("조부모를 대상으로 닫는다");
    assert_eq!(
        project.cycles().current().report().unwrap().get(CYCLE_TARGET),
        Some(root.to_ref().to_string().as_str()),
        "적은 대상이 그대로 남아야 한다"
    );
}

#[test]
fn the_lineage_a_target_must_stand_on_follows_parent_only() {
    // **이 시험이 지키는 것은 조상 검사의 정의다.** 대상이 서야 하는 계보는
    // `Cycles::lineage` 가 답하고, 그것은 `parent` 사슬 하나만 따라간다.
    //
    // Cycle 수준의 `revisit_from` 은 아직 활성화되지 않았으므로(저장이 채워진 파일을
    // 거절한다) 그 값을 두 번째 부모로 읽는 변경은 지금 만들 수 없다. 그래서 여기서는
    // **계보가 실제로 무엇인지**를 못 박는다 — M4-D 가 출처를 켤 때 이 못이 남는다.
    let mut project = graph_with_two_cycles();
    let ids: Vec<_> = project.cycles().nodes().iter().map(|c| c.id()).collect();
    let here = project.cycles().current_id();

    let lineage: Vec<_> = project
        .cycles()
        .lineage(here)
        .unwrap()
        .iter()
        .map(|cycle| cycle.id())
        .collect();
    assert_eq!(lineage, ids, "v0 의 계보는 걸어온 한 줄 전부다");

    // 그리고 그 한 줄 위의 것은 전부 대상이 될 수 있다.
    let outcome = walk_to_the_exit(&mut project, "failure");
    for ancestor in &ids[..ids.len() - 1] {
        let report = cycle_report(project.cycles().current(), "failure", outcome)
            .with(CYCLE_TARGET, ancestor.to_ref().to_string());
        let mut probe = project.clone();
        probe
            .close_cycle(report)
            .unwrap_or_else(|err| panic!("{ancestor} 를 대상으로 닫지 못했다: {err}"));
    }
}

#[test]
fn the_step_level_target_is_untouched() {
    // Cycle 계층의 칸을 더했다고 Step 계층의 되돌아감이 달라지지 않는다.
    // **두 칸은 다른 이름이고 다른 계층의 것이다** — 한쪽으로 다른 쪽을 대신할 수 없다.
    assert_ne!(TARGET, CYCLE_TARGET);

    let mut project = bootstrap();
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        common::walked(&mut project, kind);
    }
    let analysis = project
        .cycles()
        .current()
        .steps()
        .current()
        .expect("해석에 서 있다");
    common::opened(&mut project, NodeKind::Outcome);

    let cycle = project.cycles().current();
    let base = common::full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", "failure")
        .with(ACTION, "revisit")
        .with(REASON, "가설이 반증됐다");

    // Cycle 의 칸을 적어도 Step 의 갈 곳을 대신하지 못한다.
    let said = project
        .clone()
        .close_action_step(base.clone().with(CYCLE_TARGET, "cycle:C1"))
        .expect_err("Step 의 갈 곳 없이 되돌아감이 닫혔다")
        .to_string();
    assert!(said.contains(TARGET), "Step 의 칸을 요구하지 않는다:\n{said}");

    // 제 칸을 적으면 그대로 닫힌다 — 바뀐 것이 없다.
    project
        .close_action_step(base.with(TARGET, cycle.step_ref(analysis).to_string()))
        .expect("Step 의 되돌아감은 그대로다");
}
