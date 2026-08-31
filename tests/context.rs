//! Context — 새 세션이 한 번 읽고 이어 걷는다.
//!
//! 여기서 재는 것은 **무엇이 실렸고 무엇이 안 실렸는가**이지 글의 모양이 아니다. 그래서
//! 절의 제목이나 줄 순서를 세지 않고, 사람이 적은 **값 자체**가 문맥에 있는지를 센다 —
//! 문구를 다듬을 때마다 빨개지는 시험은 무시되고, 무시되는 시험은 없는 것과 같다.
//!
//! 세 불변식(Context Model §7)을 그대로 옮긴다.
//!
//! ```text
//! 이전 Cycle 의 Step Graph 펼침 == 0
//! 이전 Cycle 의 투영 수         == 조상 수
//! 현재 Cycle 의 Step Report 수  == 지금까지 존재하는 Step Report 수
//! ```
//!
//! # "펼치지 않는다" 는 "아무것도 읽지 않는다" 가 아니다
//!
//! 첫 불변식을 "지나온 Cycle 의 Step 값이 하나도 안 나온다" 로 재면 **틀린 것을 잰다.**
//! 이전 Cycle 의 투영은 그 Cycle 의 유일한 Define 과 `outcome_ref` 가 가리킨 Outcome 을
//! 일부러 읽는다(§7). 그래서 넷을 갈라 잰다.
//!
//! ```text
//! 나와야 한다  Define 의 목적·성공 기준 · 가리켜진 Outcome 의 교훈
//! 나오면 안 된다  Hypothesis·Verify·Analysis · 가리켜지지 않은 Outcome · Step ID · Step 별 블록
//! ```
//!
//! 재려면 값이 **자리마다 달라야** 한다. 두 Cycle 이나 두 갈래가 같은 글자를 적어 두면
//! "버려진 갈래가 안 실렸다" 를 살아남은 갈래의 같은 자리 값으로 통과시켜 버린다. 그래서
//! 아래 걷기는 칸마다 그 자리에서만 나오는 글을 적는다.

use gil::{
    Cycle, CycleKind, NodeId, NodeKind, Project, Report, RuleSet, context, next_moves,
};

mod common;
use common::{
    ACTION, REASON, TARGET, allowed_here, bootstrap, cycle_report, full_report, spec,
};

// ── 잴 수 있게 걷는다 ──────────────────────────────────────────────────────

/// 명세가 값을 열거해 둔 칸인가. 열거된 칸은 우리가 정한 낱말이라 자리마다 다르게 적을 수
/// 없고, 따라서 "어느 자리의 것인가" 를 재는 데 쓸 수 없다.
fn enumerated(rules: &RuleSet, cycle: CycleKind, kind: NodeKind, field: &str) -> bool {
    rules
        .rules(cycle, kind)
        .and_then(|step| step.field_constraints.get(field))
        .is_some_and(|constraint| !constraint.allowed_values.is_empty())
}

/// 사람이 제 말로 적는 칸들 — 이 시험이 세는 것은 이 값들이다.
fn free_fields(rules: &RuleSet, cycle: CycleKind, kind: NodeKind) -> Vec<String> {
    rules
        .rules(cycle, kind)
        .unwrap_or_else(|| panic!("{cycle} 안에 선언된 Step Kind 여야 한다: {kind}"))
        .close_requires
        .iter()
        .filter(|field| !enumerated(rules, cycle, kind, field))
        .cloned()
        .collect()
}

/// 칸마다 **그 자리에서만 나오는 값**을 적은 Report.
fn tagged_report(rules: &RuleSet, cycle: CycleKind, kind: NodeKind, tag: &str) -> Report {
    let mut report = full_report(rules, cycle, kind);
    for field in free_fields(rules, cycle, kind) {
        report.insert(field.clone(), format!("{tag} 의 {kind} 가 {field} 에 적은 글"));
    }
    report
}

/// Step 하나를 그 이름표로 걷는다.
fn step_tagged(cycle: &mut Cycle, kind: NodeKind, tag: &str) -> NodeId {
    cycle
        .open_step(kind)
        .unwrap_or_else(|err| panic!("{kind} 를 열지 못했다: {err}"));
    let id = cycle.steps().current().expect("연 뒤에는 서 있는 자리가 있다");
    let report = tagged_report(cycle.rules(), cycle.kind(), kind, tag);
    common::close_cycle_step(cycle, kind, report)
        .unwrap_or_else(|err| panic!("{kind} 를 닫지 못했다: {err}"));
    id
}

/// 판정 하나 — 되돌아가겠다고 적을 수도 있다.
fn outcome_tagged(
    cycle: &mut Cycle,
    tag: &str,
    verdict: &str,
    revisit_to: Option<NodeId>,
) -> NodeId {
    cycle.open_step(NodeKind::Outcome).expect("판정을 연다");
    let id = cycle.steps().current().expect("판정에 서 있다");

    let mut report =
        tagged_report(cycle.rules(), cycle.kind(), NodeKind::Outcome, tag).with("verdict", verdict);
    let action = match revisit_to {
        Some(_) => "revisit",
        None => "close_cycle",
    };
    let allowed = allowed_here(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome, ACTION, &report);
    assert!(
        allowed.iter().any(|value| value == action),
        "{verdict} 에서 {action} 을 적을 수 없다면 이 걷기는 성립하지 않는다"
    );
    report.insert(ACTION, action);
    if let Some(target) = revisit_to {
        report.insert(TARGET, cycle.step_ref(target).to_string());
    }
    cycle.close_step(report).expect("판정을 닫는다");
    id
}

/// 한 번 실패해 되돌아가고 두 번째 갈래에서 성공하는 Cycle.
///
/// 돌려주는 것은 (버려진 판정, 근거가 될 판정). **버려진 판정은 `outcome_ref` 가 가리키지
/// 않는다** — 그것이 문맥에 실리는지가 이 시험의 관심이다.
fn walk_with_an_abandoned_branch(cycle: &mut Cycle, tag: &str) -> (NodeId, NodeId) {
    let first = format!("{tag} 첫 갈래");
    let second = format!("{tag} 둘째 갈래");

    step_tagged(cycle, NodeKind::Define, tag);
    step_tagged(cycle, NodeKind::Hypothesis, &first);
    step_tagged(cycle, NodeKind::Verify, &first);
    let branch_point = step_tagged(cycle, NodeKind::Analysis, &first);
    let abandoned = outcome_tagged(cycle, &first, "failure", Some(branch_point));

    cycle.revisit_step().expect("적어 둔 되돌아감을 밟는다");
    step_tagged(cycle, NodeKind::Hypothesis, &second);
    step_tagged(cycle, NodeKind::Verify, &second);
    step_tagged(cycle, NodeKind::Analysis, &second);
    let judged = outcome_tagged(cycle, &second, "success", None);

    (abandoned, judged)
}

/// 한 갈래로 곧장 걷는다 — 되돌아감이 필요 없는 Cycle 에 쓴다.
fn walk_straight(cycle: &mut Cycle, tag: &str) -> NodeId {
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        step_tagged(cycle, kind, tag);
    }
    outcome_tagged(cycle, tag, "success", None)
}

/// 지금 Cycle 을 성공으로 닫는다 — Cycle Report 의 사람 말도 이 Cycle 만의 값으로.
fn close_tagged(project: &mut Project, outcome: NodeId, tag: &str) {
    let mut report = cycle_report(project.cycles().current(), "success", outcome);
    report.insert("handoff_summary", format!("{tag} 이 다음 Cycle 에 넘긴 것"));
    report.insert(REASON, format!("{tag} 이 그 방향을 고른 까닭"));
    project
        .cycles_mut()
        .current_mut()
        .close(report)
        .expect("Cycle 을 닫는다");
}

/// 확인 시나리오 — Cycle 1 을 성공으로 닫고, Cycle 2 를 열어 Step 을 둘 걷는다.
///
/// Cycle 1 은 한 번 되돌아갔다. 그래야 **가리켜지지 않은 판정**이 하나 생긴다.
/// 끝난 자리: Cycle 2 의 define·hypothesis 가 닫혀 있고 verify 가 열려 있다.
fn the_scenario() -> (Project, NodeId) {
    let mut project = bootstrap();
    let (abandoned, judged) =
        walk_with_an_abandoned_branch(project.cycles_mut().current_mut(), "Cycle 1");
    close_tagged(&mut project, judged, "Cycle 1");

    project
        .open_child_cycle(CycleKind::Experiment)
        .expect("성공한 Cycle 이 적어 둔 대로 다음 Cycle 을 연다");

    let cycle = project.cycles_mut().current_mut();
    step_tagged(cycle, NodeKind::Define, "Cycle 2");
    step_tagged(cycle, NodeKind::Hypothesis, "Cycle 2");
    cycle.open_step(NodeKind::Verify).expect("검증을 연다");
    (project, abandoned)
}

/// 조상이 둘인 자리 — Cycle 1 → Cycle 2 → Cycle 3.
fn a_longer_scenario() -> Project {
    let mut project = bootstrap();
    let (_, judged) = walk_with_an_abandoned_branch(project.cycles_mut().current_mut(), "Cycle 1");
    close_tagged(&mut project, judged, "Cycle 1");

    project
        .open_child_cycle(CycleKind::Experiment)
        .expect("Cycle 2 를 연다");
    let judged = walk_straight(project.cycles_mut().current_mut(), "Cycle 2");
    close_tagged(&mut project, judged, "Cycle 2");

    project
        .open_child_cycle(CycleKind::Experiment)
        .expect("Cycle 3 을 연다");
    step_tagged(project.cycles_mut().current_mut(), NodeKind::Define, "Cycle 3");
    project
}

/// 이 자리로 이어진 조상 Cycle 들 — 계보에서 현재를 뺀 것.
fn ancestors(project: &Project) -> Vec<&Cycle> {
    let cycles = project.cycles();
    let lineage = cycles.lineage(cycles.current_id()).expect("계보가 있다");
    lineage[..lineage.len() - 1].to_vec()
}

/// 이 Cycle 안의 Step 을 가리키는 주소 — 시험은 `NodeId` 를 만들 수 없다(발급은 걷기만 한다).
fn name_of(cycle: &Cycle, id: NodeId) -> String {
    cycle.step_ref(id).to_string()
}

/// 이 Cycle 의 Cycle Report 가 **가리킨** 판정의 주소.
fn referenced_outcome(cycle: &Cycle) -> String {
    cycle
        .report()
        .and_then(|report| report.get("outcome_ref"))
        .expect("닫힌 Cycle 은 근거가 된 판정을 가리킨다")
        .to_string()
}

/// 이전 Cycle 절만 — 현재 Cycle 절이 열리기 전까지.
///
/// 절을 가르는 표를 시험이 안다. 그 표가 사라지면 이 시험은 **조용히 통과하는 대신
/// 없다고 말한다** — 무엇을 재고 있었는지 모르게 되는 것이 가장 나쁘다.
fn previous_section(told: &str) -> &str {
    let (previous, _) = told
        .split_once("═══ 현재 Cycle ═══")
        .expect("현재 Cycle 절이 없다 — 절을 가르는 표가 바뀌었다");
    previous
}

/// 이 줄이 조상 하나의 투영이 시작되는 머리인가 — `Cycle <수> · …`.
fn is_projection_head(line: &str) -> bool {
    line.starts_with("Cycle ")
        && line
            .split(' ')
            .nth(1)
            .is_some_and(|word| word.parse::<u32>().is_ok())
}

/// 이전 Cycle 절에서 **투영들만** — 절머리의 안내문을 뺀 나머지.
///
/// 안내문은 무엇을 어디서 읽었는지 말하느라 `outcome_ref` 같은 칸 이름을 부른다. 그것까지
/// 세면 "칸의 값이 실렸는가" 를 안내문의 낱말로 잘못 판정한다.
fn previous_projections(told: &str) -> String {
    previous_section(told)
        .lines()
        .skip_while(|line| !is_projection_head(line))
        .collect::<Vec<_>>()
        .join("\n")
}

// ── 불변식 ① 이전 Cycle 의 Step Graph 를 펼치지 않는다 ─────────────────────

#[test]
fn a_previous_cycle_projects_the_purpose_it_was_defined_with() {
    // 실험 목적과 성공 기준은 **나와야 한다** — 원본은 그 Cycle 의 유일하고 immutable 한
    // Define 이고, Cycle Report 는 그것을 복제해 갖지 않는다.
    let (project, _) = the_scenario();
    let told = context(&project);
    let previous = previous_section(&told);

    // Define 은 **Experiment 의 것**이다. Bootstrap Interview 에는 Define 이 없고, 그 자리에
    // 없는 것을 있는 척 투영하지도 않는다 — 그래서 있는 Cycle 에서만 잰다.
    let mut counted = 0;
    for ancestor in ancestors(&project) {
        let Some(define) = ancestor.define() else {
            assert_eq!(
                ancestor.kind(),
                CycleKind::Interview,
                "{} 이(가) Define 없이 닫혔다",
                ancestor.id()
            );
            continue;
        };
        for field in ["problem", "success_condition"] {
            let value = define.get(field).expect("Define 이 적어 둔 칸이다");
            assert!(
                previous.contains(value),
                "{} 의 Define.{field} 가 투영되지 않았다:\n{told}",
                ancestor.id()
            );
            counted += 1;
        }
    }
    assert!(counted > 0, "Define 을 가진 조상이 하나도 없어 아무것도 재지 못했다");
}

#[test]
fn a_previous_cycle_projects_the_lesson_it_was_judged_by() {
    // 판정의 교훈은 **가리켜진 그 Outcome** 에서 읽는다.
    let (project, _) = the_scenario();
    let told = context(&project);
    let previous = previous_section(&told);

    for ancestor in ancestors(&project) {
        let lesson = ancestor
            .judged_lesson()
            .expect("닫힌 Cycle 은 근거가 된 판정을 가리킨다");
        assert!(
            previous.contains(lesson),
            "{} 의 판정 교훈이 투영되지 않았다:\n{told}",
            ancestor.id()
        );
    }
}

#[test]
fn a_previous_cycle_keeps_its_verdict_handoff_and_direction() {
    let (project, _) = the_scenario();
    let told = context(&project);
    let previous = previous_section(&told);

    for ancestor in ancestors(&project) {
        let report = ancestor.report().expect("닫힌 Cycle 은 Report 를 지닌다");
        for field in ["verdict", "handoff_summary", ACTION, REASON] {
            let value = report.get(field).expect("Cycle Report 가 적어 둔 칸이다");
            assert!(
                previous.contains(value),
                "{} 의 Cycle Report {field} 가 문맥에 없다:\n{told}",
                ancestor.id()
            );
        }
    }
}

#[test]
fn a_previous_cycle_expands_no_step_graph() {
    // previous_cycle_step_graph_expansions_in_context == 0
    //
    // 투영이 읽는 둘(Define · 가리켜진 Outcome) 말고는 아무것도 오지 않는다.
    let (project, abandoned) = the_scenario();
    let told = context(&project);
    let previous = previous_projections(&told);
    let rules = spec();

    let mut counted = 0;
    let mut leaked = Vec::new();
    for ancestor in ancestors(&project) {
        // 무엇이 가리켜진 판정인가는 **적힌 참조**가 답한다 — 값을 견주어 짐작하지 않는다.
        let judged = referenced_outcome(ancestor);

        for node in ancestor.steps().history() {
            // 시도와 전환의 전개 — Hypothesis·Verify·Analysis 는 한 글자도 오지 않는다.
            // 판정 중에서는 **가리켜지지 않은 것**이 오지 않는다.
            let expands = match node.kind {
                NodeKind::Define => false,
                NodeKind::Outcome => name_of(ancestor, node.id) != judged,
                _ => true,
            };
            if !expands {
                continue;
            }
            let report = node.report.as_ref().expect("닫힌 Step 은 Report 를 지닌다");
            for field in free_fields(&rules, ancestor.kind(), node.kind) {
                let value = report.get(&field).expect("적어 둔 칸이다");
                counted += 1;
                if previous.contains(value) {
                    leaked.push(format!("{} {} 의 {field}", ancestor.id(), node.id));
                }
            }
        }

        // Step 의 이름도 오지 않는다 — 이름이 오면 그것은 Step 별 블록이라는 뜻이다.
        for node in ancestor.steps().nodes() {
            counted += 1;
            if previous.contains(&node.id.to_string()) {
                leaked.push(format!("{} 의 Step ID {}", ancestor.id(), node.id));
            }
        }
    }

    // `outcome_ref` 는 **따라가는 참조**이지 보여 줄 값이 아니다. 그 값은 이 Cycle 안에서만
    // 뜻이 있는 Step 의 이름이라, 실리면 그것이 곧 Step ID 가 새어 나온 것이다.
    counted += 1;
    if previous.contains("outcome_ref") {
        leaked.push("따라가기만 할 참조 outcome_ref".to_string());
    }

    assert!(counted > 0, "잰 것이 하나도 없다 — 이 시험은 아무것도 재지 못했다");
    assert!(
        leaked.is_empty(),
        "이전 Cycle 의 Step Graph 가 펼쳐졌다: {leaked:?}\n{told}"
    );

    // 버려진 갈래의 판정이 실제로 있었고 그것이 근거가 아니었음을 확인한다 —
    // 없으면 위 검사는 아무것도 거르지 못한다.
    let cycle_one = ancestors(&project)
        .into_iter()
        .find(|cycle| cycle.kind() == CycleKind::Experiment)
        .expect("첫 Experiment 조상이 있다");
    assert_ne!(
        name_of(cycle_one, abandoned),
        referenced_outcome(cycle_one),
        "버려진 판정이 근거가 되어 버렸다 — 이 시험은 재지 못한다"
    );
    assert!(
        cycle_one.steps().node(abandoned).is_some(),
        "버려진 판정이 Graph 에서 사라졌다 — 압축은 삭제가 아니다"
    );
}

// ── 불변식 ② 조상마다 투영 하나 ────────────────────────────────────────────

#[test]
fn every_ancestor_gets_exactly_one_projection() {
    // previous_cycle_projections_in_context == ancestor_count
    let project = a_longer_scenario();
    let told = context(&project);
    let previous = previous_section(&told);
    let ancestors = ancestors(&project);
    // Bootstrap Interview 하나와 그 뒤의 Experiment 둘.
    assert_eq!(ancestors.len(), 3, "조상이 셋일 때 세는 시험이다");

    // ① 투영의 머리는 조상마다 정확히 하나다.
    let mut heads = 0;
    for ancestor in &ancestors {
        let head = format!("{} · ", ancestor.id());
        let mine = previous
            .lines()
            .filter(|line| line.starts_with(&head))
            .count();
        assert_eq!(mine, 1, "{} 의 투영이 {mine}개다:\n{told}", ancestor.id());
        heads += mine;
    }
    assert_eq!(heads, ancestors.len(), "투영 수가 조상 수와 다르다:\n{told}");

    // ② 그리고 다른 머리는 없다 — 조상이 아닌 Cycle 이 이 절에 끼지 않는다.
    let all_heads = previous.lines().filter(|line| is_projection_head(line)).count();
    assert_eq!(all_heads, ancestors.len(), "이 절에 낯선 머리가 있다:\n{told}");

    // ③ 조상의 목적은 문맥 전체에서 한 번만 나온다 — 두 번 실으면 압축이 아니다.
    for ancestor in &ancestors {
        // Bootstrap Interview 에는 Define 이 없다 — 없는 것을 세지 않는다.
        let Some(problem) = ancestor.define().and_then(|define| define.get("problem")) else {
            continue;
        };
        assert_eq!(
            told.matches(problem).count(),
            1,
            "{} 의 실험 목적이 여러 번 실렸다:\n{told}",
            ancestor.id()
        );
    }
}

// ── 불변식 ③ 현재 Cycle 은 Step Report 해상도로 온다 ───────────────────────

#[test]
fn the_current_cycle_arrives_at_step_resolution() {
    // current_cycle_step_occurrences_in_context == 지금까지 존재하는 Step Report 수
    let (project, _) = the_scenario();
    let told = context(&project);
    let rules = spec();
    let current = project.cycles().current();

    let existing = current.steps().history().count();
    assert!(existing > 0, "적힌 Step Report 가 없으면 이 시험은 재지 못한다");

    let present = current
        .steps()
        .history()
        .filter(|node| {
            let report = node.report.as_ref().expect("닫힌 Step 은 Report 를 지닌다");
            free_fields(&rules, CycleKind::Experiment, node.kind)
                .iter()
                .all(|field| told.contains(report.get(field).expect("적어 둔 칸이다")))
        })
        .count();

    assert_eq!(
        present, existing,
        "지금 Cycle 의 Step Report {existing}개 중 {present}개만 문맥에 있다:\n{told}"
    );

    // 그리고 그것은 Step 별로 온다 — 이름이 붙어 있어야 되돌아갈 자리를 고를 수 있다.
    for node in current.steps().nodes() {
        assert!(
            told.contains(&node.id.to_string()),
            "지금 Cycle 의 {} 이(가) 이름 없이 실렸다:\n{told}",
            node.id
        );
    }
}

#[test]
fn an_open_step_comes_as_a_state_not_a_report() {
    // 현재 열려 있는 Step 이 있다면 그 상태도 보여 준다 — 아직 Report 는 없다.
    let (project, _) = the_scenario();
    let told = context(&project);
    let walk = project.cycles().current().steps();
    let here = walk
        .current()
        .and_then(|id| walk.node(id))
        .expect("서 있는 자리가 있다");

    assert!(!here.is_closed(), "이 시험은 열린 자리를 전제한다");
    assert!(
        told.contains(&here.id.to_string()) && told.contains(here.kind.as_str()),
        "열려 있는 자리가 문맥에 없다:\n{told}"
    );
}

// ── 첫 Cycle 에는 이전 절이 없다 ───────────────────────────────────────────

#[test]
fn the_first_cycle_has_nothing_before_it() {
    // "현재 Cycle이 첫 Cycle이라면 이전 Cycle 절은 없다"(Context Model §7).
    //
    // 프로젝트의 첫 Cycle 은 Bootstrap Interview 다 — 그 자리에서는 이어받을 것이 없다.
    let mut project = Project::start(spec(), common::first_world());
    step_tagged(
        project.cycles_mut().current_mut(),
        NodeKind::Question,
        "Cycle 1",
    );

    let told = context(&project);
    assert!(ancestors(&project).is_empty(), "뿌리에는 조상이 없다");
    assert!(
        !told.contains("이전 Cycle"),
        "이어받을 것이 없는데 빈 절을 냈다:\n{told}"
    );
    // 그래도 지금 Cycle 은 Step 해상도로 온다.
    assert!(told.contains("Cycle 1 의 question"), "{told}");
}

// ── 지금 자리 ──────────────────────────────────────────────────────────────

#[test]
fn the_context_says_where_we_stand() {
    let (project, _) = the_scenario();
    let told = context(&project);
    let current = project.cycles().current();
    let parent = current.parent().expect("이 시나리오의 현재 Cycle 은 자식이다");

    assert!(told.contains(&current.id().to_string()), "어느 Cycle 인지 없다:\n{told}");
    assert!(told.contains(&parent.to_string()), "어디에서 이어받았는지 없다:\n{told}");
    assert!(told.contains(current.kind().as_str()), "Cycle 의 종류가 없다:\n{told}");
}

#[test]
fn the_next_moves_are_the_ones_the_tool_will_actually_take() {
    // 안내가 실행과 갈리면 그 안내는 없느니만 못하다(실사용 보고 #123).
    // `gil status` 와 `gil context` 는 **같은 자리**에서 다음 수를 읽는다.
    let (mut project, _) = the_scenario();
    assert!(
        context(&project).contains(&next_moves(project.cycles())),
        "문맥의 다음 수가 도구의 다음 수와 다르다"
    );

    // 자리를 옮겨도 함께 옮겨간다.
    let cycle = project.cycles_mut().current_mut();
    let report = tagged_report(cycle.rules(), cycle.kind(), NodeKind::Verify, "Cycle 2");
    cycle
        .close_verify_step(report, common::snapshot(1))
        .expect("검증을 닫는다");
    assert!(
        context(&project).contains(&next_moves(project.cycles())),
        "자리를 옮기고 나서 갈렸다"
    );
}

#[test]
fn the_rules_here_come_from_the_spec() {
    // 지금 닫아야 하는 것이 요구하는 칸은 **명세에서 읽는다.** 옮겨 적으면 명세가 바뀐
    // 날부터 새 세션이 낡은 규칙을 받는다.
    let (project, _) = the_scenario();
    let told = context(&project);
    let rules = spec();

    // 지금 열려 있는 것은 verify 다 — 그것을 닫는 규칙이 나와야 한다.
    let verify = rules.rules(CycleKind::Experiment, NodeKind::Verify).expect("선언된 Step Kind");
    for field in &verify.close_requires {
        assert!(told.contains(field.as_str()), "{field} 가 규칙에 없다:\n{told}");
    }
}

#[test]
fn the_allowed_values_come_with_the_field() {
    // 판정을 앞둔 자리에서는 어떤 값이 올 수 있는지까지 알아야 한다.
    let (mut project, _) = the_scenario();
    let cycle = project.cycles_mut().current_mut();
    let report = tagged_report(cycle.rules(), cycle.kind(), NodeKind::Verify, "Cycle 2");
    cycle
        .close_verify_step(report, common::snapshot(1))
        .expect("검증을 닫는다");
    step_tagged(cycle, NodeKind::Analysis, "Cycle 2");

    let told = context(&project);
    let rules = spec();
    let constraint = rules
        .rules(CycleKind::Experiment, NodeKind::Outcome)
        .expect("선언된 Step Kind")
        .field_constraints
        .get("verdict")
        .expect("판정의 결과는 값이 열거된 칸이다");

    assert!(
        project.cycles().openable_here().contains(&NodeKind::Outcome),
        "이 시험은 판정을 열 수 있는 자리를 전제한다"
    );
    for value in &constraint.allowed_values {
        assert!(
            told.contains(value.as_str()),
            "verdict 가 가질 수 있는 값 {value} 가 규칙에 없다:\n{told}"
        );
    }
}

// ── 읽기는 아무것도 바꾸지 않는다 ──────────────────────────────────────────

#[test]
fn asking_for_the_context_changes_nothing() {
    let (project, _) = the_scenario();
    let before = format!("{:?}", project.cycles());
    let _ = context(&project);
    assert_eq!(format!("{:?}", project.cycles()), before, "읽기가 Graph 를 바꿨다");
}

#[test]
fn the_context_stores_nothing_of_its_own() {
    // Cycle Report 를 다시 요약해 어딘가에 적어 두지 않는다 — 두 번 부르면 같은 글이 나오고,
    // 그 글은 언제나 원본에서 다시 만들어진다.
    let (project, _) = the_scenario();
    assert_eq!(context(&project), context(&project));
}

#[test]
fn a_closed_cycle_still_says_what_comes_next() {
    // 마지막 Cycle 을 닫아 둔 자리에서도 새 세션은 다음 수를 알아야 한다.
    let (mut project, _) = the_scenario();
    let cycle = project.cycles_mut().current_mut();
    let report = tagged_report(cycle.rules(), cycle.kind(), NodeKind::Verify, "Cycle 2");
    cycle
        .close_verify_step(report, common::snapshot(1))
        .expect("검증을 닫는다");
    step_tagged(cycle, NodeKind::Analysis, "Cycle 2");
    let judged = outcome_tagged(cycle, "Cycle 2", "success", None);
    close_tagged(&mut project, judged, "Cycle 2");

    let told = context(&project);
    assert!(told.contains(&next_moves(project.cycles())), "닫힌 자리에서 다음 수가 갈렸다");
    // 그리고 지금 Cycle 의 Cycle Report 도 함께 온다 — 그것이 다음 Cycle 이 받을 것이다.
    assert!(
        told.contains("Cycle 2 이 다음 Cycle 에 넘긴 것"),
        "지금 Cycle 이 적어 둔 handoff 가 문맥에 없다:\n{told}"
    );
}
