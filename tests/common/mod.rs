//! 시험이 함께 쓰는 것 — **기대값은 저장소의 진짜 명세에서 만든다.**
//!
//! 여기 있는 것은 여러 시험 파일이 나눠 쓰는 연장이다. 한 파일이 안 쓰는 연장도 있어서
//! 안 쓰임 경고를 끈다 — 없는 연장으로 오해하지 않도록.
#![allow(dead_code)]

use std::path::{Path, PathBuf};

use std::collections::BTreeMap;

use gil::{
    ActionContract, Cycle, CycleKind, FieldConstraint, ManifestAddress, NodeId, NodeKind, Project,
    ProjectSession, Report, RuleSet, SnapshotRef, StepRef, Walk,
};

pub const SPEC_PATH: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/spec/gil-spec.yaml");

/// 지어낸 주소 — **창고에 실재하지 않는다.**
///
/// 저장을 거치지 않는 순수 도메인 시험에서만 쓴다. `load` 는 registry 가 가리키는 manifest
/// 가 실재하는지 보므로(format 4 §8), 저장을 거치는 시험은 [`first_world`] 를 쓴다.
pub fn imagined_world(seed: u8) -> ManifestAddress {
    ManifestAddress::from_parts("sha256", &[seed; 32]).expect("sha256 주소는 32 바이트다")
}

/// **빈 프로젝트의 세계** — 실제로 관측해서 얻은 주소.
///
/// 내용이 주소를 정하므로 빈 폴더의 세계는 **어디서 관측해도 같다**. 그래서 이 값 하나가
/// [`scratch`] 로 만든 모든 자리에서 통한다 — 각 자리의 창고에는 같은 manifest 객체가
/// 실제로 눕혀져 있다.
pub fn first_world() -> ManifestAddress {
    static EMPTY: std::sync::OnceLock<ManifestAddress> = std::sync::OnceLock::new();
    EMPTY
        .get_or_init(|| {
            let dir = std::env::temp_dir().join("gil-test-empty-world");
            let _ = std::fs::remove_dir_all(&dir);
            std::fs::create_dir_all(&dir).expect("빈 자리를 만든다");
            sow_world(&dir)
        })
        .clone()
}

/// 그 자리를 실제로 관측해 blob·manifest 를 눕히고 최초 세계의 주소를 돌려준다.
///
/// `ProjectSession::start` 를 지난다 — 관측·확정·재검증을 다시 적지 않기 위해서다.
/// `state.yaml` 은 쓰지 않는다(`commit` 을 부르지 않는다).
pub fn sow_world(root: &Path) -> ManifestAddress {
    let session = ProjectSession::start(spec(), root.join(gil::STATE_PATH))
        .expect("빈 자리에서 최초 세계를 세운다");
    session
        .project()
        .world_manifest(snapshot(1))
        .expect("A1 은 언제나 실재한다")
        .clone()
}

/// 이름으로 부르는 Snapshot.
pub fn snapshot(number: u32) -> SnapshotRef {
    SnapshotRef::new(number).expect("Snapshot 이름은 1 부터다")
}

pub fn spec() -> RuleSet {
    RuleSet::from_path(SPEC_PATH).expect("spec/gil-spec.yaml 을 읽을 수 있어야 한다")
}

/// close_requires 를 전부 채운, 명세가 받아들이는 Report.
///
/// 값에 제약이 걸린 칸은 **명세가 허락한 값 중 하나**로 채운다(여기서도 값을 지어내지 않는다).
/// 다른 칸에 따라 허용값이 좁아지는 칸은 **좁혀진 뒤에** 다시 고른다.
pub fn full_report(rules: &RuleSet, cycle: CycleKind, kind: NodeKind) -> Report {
    let step = rules
        .rules(cycle, kind)
        .unwrap_or_else(|| panic!("{cycle} 안에 선언된 Step Kind 여야 한다: {kind}"));
    fill(&step.close_requires, &step.field_constraints)
}

/// Cycle 을 닫는 규칙을 전부 채운 Cycle Report. **Step 과 같은 방식으로 채운다.**
pub fn full_cycle_report(rules: &RuleSet, kind: CycleKind) -> Report {
    let cycle = rules.cycle_rules(kind).expect("선언된 Cycle Kind 여야 한다");
    fill(&cycle.close_requires, &cycle.field_constraints)
}

/// 요구된 칸을 명세가 받아들이는 값으로 채운다 — 계층을 가리지 않는다.
fn fill(
    close_requires: &[String],
    field_constraints: &BTreeMap<String, FieldConstraint>,
) -> Report {
    // ① 먼저 각 칸을 제 허용값(또는 자리표시자)으로 채운다.
    let mut report: Report = close_requires
        .iter()
        .map(|field| {
            let value = match field_constraints.get(field) {
                Some(constraint) => constraint
                    .allowed_values
                    .first()
                    .cloned()
                    .unwrap_or_else(|| format!("<{field}>")),
                None => format!("<{field}>"),
            };
            (field.clone(), value)
        })
        .collect();

    // ② 다른 칸이 값을 좁히는 칸은, 그 값을 보고 다시 고른다.
    for (field, constraint) in field_constraints {
        if constraint.allowed_values_when.is_empty() {
            continue;
        }
        let (allowed, _) = constraint.allowed_here(|other| report.get(other));
        if let Some(value) = allowed.first() {
            report.insert(field.clone(), value.clone());
        }
    }

    report
}

/// 시험이 파일을 눕히는 빈 자리. 이름이 겹치지 않게 시험마다 다른 `label` 을 준다.
///
/// 들어가기 전에 지운다 — 앞 판이 남긴 것이 이번 판의 답이 되지 않도록.
/// 시험이 쓸 빈 프로젝트 자리 — **최초 세계의 객체까지 눕혀서.**
///
/// format 4 의 `state.yaml` 은 registry 가 가리키는 manifest 가 창고에 실재할 때만
/// 되살아난다(§8). 그래서 이 자리는 「`gil start` 가 방금 지나간 폴더」와 같은 모양으로
/// 선다 — `.gil/artifacts/` 에 빈 세계의 manifest 가 이미 있다.
pub fn scratch(label: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("gil-test-{label}"));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).expect("시험이 쓸 자리를 만들 수 있어야 한다");
    sow_world(&dir);
    dir
}

/// Report 가 다음 방향을 적는 칸의 이름 — `gil-spec.yaml` 이 부르는 그대로.
pub const ACTION: &str = "next_direction.action";
pub const TARGET: &str = "next_direction.target_node_ref";
pub const CYCLE_TARGET: &str = "next_direction.target_cycle_ref";
pub const REASON: &str = "next_direction.reason";

/// 이미 열려 있는 Node 를 명세가 받아들이는 Report 로 닫는다.
///
/// **Verify 는 세계와 함께 닫는다.** 세계를 확정하지 않은 Verify 는 닫힌 것이 아니므로
/// (Artifact Model §7.2), 시험이 그 자리를 지나려면 관측한 세계를 함께 줘야 한다.
pub fn step_close(walk: &mut Walk, kind: NodeKind) {
    let report = full_report(walk.rules(), walk.kind(), kind);
    match kind == NodeKind::Verify {
        true => walk.close_verify(report, snapshot(1)),
        false => walk.close(report),
    }
    .unwrap_or_else(|err| panic!("{kind} 를 닫지 못했다: {err}"));
}

/// 지금 열려 있는 자리가 Verify 인가 — 어느 문으로 닫을지 가른다.
pub fn open_is_verify(project: &Project) -> bool {
    let cycle = project.cycles().current();
    cycle
        .step_now_open()
        .and_then(|at| cycle.steps().node(at))
        .is_some_and(|node| node.kind == NodeKind::Verify)
}

/// 열려 있는 자리를 **그 Kind 에 맞는 문으로** 닫는다.
///
/// Verify 에는 세계를 함께 준다. 시험이 주는 것은 언제나 [`first_world`] 라 registry 는
/// 기존 `A1` 을 그대로 재사용한다 — 「아무것도 바꾸지 않은 Verify」의 모양이다.
pub fn close_here(project: &mut Project, report: Report) -> Result<gil::Closed, gil::ActionError> {
    match open_is_verify(project) {
        true => project.close_verify_step(report, first_world()),
        false => project.close_action_step(report),
    }
}

/// 한 Step 을 온전히 걷는다 — 열고, 명세가 받아들이는 Report 로 닫는다.
pub fn step(walk: &mut Walk, kind: NodeKind) -> NodeId {
    walk.open(kind)
        .unwrap_or_else(|err| panic!("{kind} 를 열지 못했다: {err}"));
    let id = walk.current().expect("연 뒤에는 서 있는 자리가 있다");
    step_close(walk, kind);
    id
}

/// 이 자리에서 실제로 하려는 일 — **Kind 하나에 최소 계약 하나.**
///
/// 계약은 "지금 무엇을 하려는가" 다. GIL 은 그것을 지어내지 않지만(Will Model §7), *시험*은
/// 그 자리에서 사람이 무엇을 하는지 안다 — 그래서 그 문장을 **여기 한 자리에만** 적는다.
/// 시험마다 뜻 없는 더미를 베끼면 그 값들은 아무것도 재지 않으면서 갱신 비용만 만든다.
///
/// 시나리오가 다른 것을 하려 한다면 [`contract`] 로 직접 적는다.
pub fn plan(kind: NodeKind) -> ActionContract {
    let (objective, next_action, done_when) = match kind {
        NodeKind::Question => (
            "사용자의 의도를 확인한다",
            "선택지와 함께 질문을 건넨다",
            "사용자의 원문 응답을 얻는다",
        ),
        NodeKind::Interpretation => (
            "응답에서 확정된 것과 아직 모르는 것을 가른다",
            "받은 응답을 다시 읽고 명제로 정리한다",
            "정리한 명제와 남은 미해결이 적힌다",
        ),
        NodeKind::Synthesis => (
            "확인한 것을 하나의 제안 문장으로 모은다",
            "근거를 모아 제안을 짓고 사용자에게 승인을 구한다",
            "사용자의 승인 여부를 얻는다",
        ),
        NodeKind::Define => (
            "이 실험이 풀 문제를 정한다",
            "무엇이 문제이고 무엇이면 성공인지 적는다",
            "문제와 성공 기준이 문장으로 남는다",
        ),
        NodeKind::Hypothesis => (
            "원인 후보 하나를 세운다",
            "코드를 읽어 검증 가능한 원인 후보를 하나 고른다",
            "가설 한 문장이 남는다",
        ),
        NodeKind::Verify => (
            "가설을 실제로 검증한다",
            "테스트를 실행해 결과를 관측한다",
            "실행 결과를 확보한다",
        ),
        NodeKind::Analysis => (
            "관측을 가설과 맞춰 읽는다",
            "관측 결과가 가설과 맞는지 따진다",
            "맞았는지 아닌지 말할 수 있다",
        ),
        NodeKind::Outcome => (
            "이 Cycle 을 판정한다",
            "지금까지의 관측을 모아 판정과 다음 방향을 정한다",
            "판정과 다음 방향을 말할 수 있다",
        ),
        other => panic!("{other} 는 실행형 Step 이 아니라 계약을 갖지 않는다"),
    };
    contract(objective, next_action, done_when)
}

/// 세 칸을 직접 적는다 — 시나리오가 Kind 의 최소와 다를 때.
pub fn contract(objective: &str, next_action: &str, done_when: &str) -> ActionContract {
    ActionContract::new(objective, next_action, done_when)
}

/// **한 Step 을 통합 transaction 으로 온전히 걷는다** — 계약과 함께 열고, Report 로 닫는다.
///
/// [`cycle_step`] 과 나뉘어 있는 것이 일부러다. 저 아래는 Step Graph 의 불변식만 재는
/// 자리이고 Will 을 모른다. 이 자리는 Will·Journey 판·provenance 가 함께 확정되는 것을
/// 재는 자리다 — **저장을 거치는 시험은 반드시 이 문으로 걷는다.**
pub fn project_step(project: &mut Project, kind: NodeKind, contract: ActionContract) -> StepRef {
    let opened = project
        .open_action_step(kind, contract)
        .unwrap_or_else(|err| panic!("{kind} 를 열지 못했다: {err}"));
    let report = full_report(
        project.cycles().rules(),
        project.cycles().current().kind(),
        kind,
    );
    close_here(project, report)
        .unwrap_or_else(|err| panic!("{kind} 를 닫지 못했다: {err}"));
    opened.step
}

/// 그 Kind 의 최소 계약으로 한 Step 을 걷는다.
pub fn walked(project: &mut Project, kind: NodeKind) -> StepRef {
    project_step(project, kind, plan(kind))
}

/// 계약과 함께 열기만 한다 — 닫는 것은 부르는 쪽이 제 Report 로 한다.
pub fn opened(project: &mut Project, kind: NodeKind) -> StepRef {
    project
        .open_action_step(kind, plan(kind))
        .unwrap_or_else(|err| panic!("{kind} 를 열지 못했다: {err}"))
        .step
}

/// 이름으로 되돌린다 — 시험이 `NodeId` 로 재던 자리를 그대로 쓰기 위해.
pub fn step_id(project: &Project, step: StepRef) -> NodeId {
    project
        .cycles()
        .current()
        .steps()
        .nodes()
        .iter()
        .find(|node| project.cycles().current().step_ref(node.id) == step)
        .expect("방금 걸은 자리는 이 Cycle 에 있다")
        .id
}

/// Cycle 안에서 한 Step 을 온전히 걷는다 — 열고, 명세가 받아들이는 Report 로 닫는다.
pub fn cycle_step(cycle: &mut Cycle, kind: NodeKind) -> NodeId {
    cycle
        .open_step(kind)
        .unwrap_or_else(|err| panic!("{kind} 를 열지 못했다: {err}"));
    let id = cycle.steps().current().expect("연 뒤에는 서 있는 자리가 있다");
    let report = full_report(cycle.rules(), cycle.kind(), kind);
    close_cycle_step(cycle, kind, report)
        .unwrap_or_else(|err| panic!("{kind} 를 닫지 못했다: {err}"));
    id
}

/// Cycle 안의 열린 자리를 그 Kind 에 맞는 문으로 닫는다.
pub fn close_cycle_step(
    cycle: &mut Cycle,
    kind: NodeKind,
    report: Report,
) -> Result<(), gil::CycleError> {
    match kind == NodeKind::Verify {
        true => cycle.close_verify_step(report, snapshot(1)),
        false => cycle.close_step(report),
    }
}

/// 그 Cycle 을 닫을 수 있는 Cycle Report — 판정한 자리와 결과를 맞춰서.
pub fn cycle_report(cycle: &Cycle, verdict: &str, outcome: NodeId) -> Report {
    let mut report = full_cycle_report(cycle.rules(), cycle.kind())
        .with("verdict", verdict)
        .with("outcome_ref", cycle.step_ref(outcome).to_string())
        .with("handoff_summary", "다음 Cycle 이 알아야 할 것");
    let allowed = cycle_allowed_here(cycle.rules(), cycle.kind(), ACTION, &report);
    report.insert(ACTION, allowed.first().expect("갈 곳이 하나는 있다").clone());
    report.insert(REASON, "왜 그 방향인지");
    // 되돌아가겠다면 갈 곳을 함께 적는다 — **구조에서 고른다.** 이 Cycle 의 부모는 언제나
    // 조상이고, 자식을 열겠다고 적었기에 이 Cycle 이 났다. 그래서 늘 유효한 대상이다.
    if report.get(ACTION) == Some("revisit") {
        let parent = cycle.parent().expect("실패로 닫는 Cycle 은 뿌리가 아니다");
        report.insert(CYCLE_TARGET, parent.to_ref().to_string());
    }
    report
}

/// **Bootstrap Interview 를 마치고 Experiment 자식까지 연 프로젝트.**
///
/// 프로젝트의 첫 Cycle 은 언제나 Interview 다(Cycle Model §5). 그래서 Experiment 를 걷는
/// 모든 시험은 먼저 이 길을 지난다 — 물어보고, 해석하고, 제안하고, 사람이 승인해야 비로소
/// 실험할 수 있다. **이 prelude 를 건너뛰는 지름길을 두지 않는다** — 그러면 저장할 수 없는
/// 상태를 시험만 만들 수 있게 되고, 시험이 지키는 것이 실제와 갈린다.
pub fn bootstrap() -> Project {
    bootstrap_from(Project::start(spec(), first_world()))
}

/// 이미 선 프로젝트를 Interview 끝까지 걷고 Experiment 를 연다.
///
/// **세계를 바꾸지 않는다** — Interview 의 어느 자리도 Artifact 를 확정할 권한이 없으므로,
/// 이 길을 지나는 동안 registry 는 `A1` 하나 그대로다.
pub fn bootstrap_from(mut project: Project) -> Project {

    for kind in [
        NodeKind::Question,
        NodeKind::Interpretation,
        NodeKind::Synthesis,
    ] {
        project
            .open_action_step(kind, plan(kind))
            .unwrap_or_else(|err| panic!("{kind} 를 열지 못했다: {err}"));
        let cycle = project.cycles().current();
        let mut report = full_report(cycle.rules(), CycleKind::Interview, kind);
        if kind == NodeKind::Synthesis {
            // 승인이 없으면 판정을 열 수 없다 — 그것이 Interview 의 문지기다.
            report.insert(APPROVED, APPROVAL);
            // 근거는 이미 닫힌 Question·Interpretation 을 한 줄에 하나씩 가리킨다.
            let basis: Vec<String> = cycle
                .steps()
                .nodes()
                .iter()
                .filter(|node| {
                    matches!(node.kind, NodeKind::Question | NodeKind::Interpretation)
                        && node.is_closed()
                })
                .map(|node| cycle.step_ref(node.id).to_string())
                .collect();
            report.insert(BASIS_REFS, basis.join("\n"));
        }
        project
            .close_action_step(report)
            .unwrap_or_else(|err| panic!("{kind} 를 닫지 못했다: {err}"));
    }
    let synthesis = project
        .cycles()
        .current()
        .steps()
        .current()
        .expect("제안에 서 있다");
    let synthesis = project.cycles().current().step_ref(synthesis);

    let outcome = opened(&mut project, NodeKind::Outcome);
    let cycle = project.cycles().current();
    let report = full_report(cycle.rules(), CycleKind::Interview, NodeKind::Outcome)
        .with(SYNTHESIS_REF, synthesis.to_string())
        .with(REASON, "승인된 Synthesis 를 얻었다");
    project.close_action_step(report).expect("판정을 닫는다");

    let mut report = cycle_report(project.cycles().current(), "success", step_id(&project, outcome));
    report.insert(ACTION, "open_child");
    project.close_cycle(report).expect("Interview 를 닫는다");

    project
        .open_child_cycle(CycleKind::Experiment)
        .expect("승인된 Synthesis 뒤에는 Experiment 를 열 수 있다");
    project
}

/// Experiment 를 define → hypothesis 까지 걷고 **Verify 를 열어 둔다.**
///
/// 세계를 확정하는 것은 Verify 뿐이라, 시험이 세계를 다루려면 그 자리에 서 있어야 한다.
pub fn up_to_verify(project: &mut Project) {
    for kind in [NodeKind::Define, NodeKind::Hypothesis] {
        walked(project, kind);
    }
    opened(project, NodeKind::Verify);
}

/// 그 Cycle 안의 Step 을 가리키는 typed reference — `step:C1/S3`.
pub fn step_ref(cycle: &Cycle, step: NodeId) -> String {
    cycle.step_ref(step).to_string()
}

/// Synthesis 가 인간의 승인을 적는 칸과 그 값.
pub const APPROVED: &str = "approved";
pub const APPROVAL: &str = "yes";
/// Interview Outcome 이 근거를 가리키는 칸.
pub const SYNTHESIS_REF: &str = "synthesis_ref";
/// Synthesis 가 근거를 가리키는 칸.
pub const BASIS_REFS: &str = "basis_refs";

/// 안의 Outcome 까지 닫아 **끝 경계에 닿은** Experiment. 아직 그 Cycle 은 열려 있다.
pub fn graph_at_the_exit(verdict: &str) -> (Project, NodeId) {
    let mut project = bootstrap();
    let outcome = walk_to_the_exit(&mut project, verdict);
    (project, outcome)
}

/// 그 Cycle 안을 끝 경계까지 걷는다. 돌려주는 것은 마지막 판정의 이름.
pub fn walk_to_the_exit(project: &mut Project, verdict: &str) -> NodeId {
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        walked(project, kind);
    }
    let outcome = opened(project, NodeKind::Outcome);

    let cycle = project.cycles().current();
    let mut report =
        full_report(cycle.rules(), cycle.kind(), NodeKind::Outcome).with("verdict", verdict);
    let allowed = allowed_here(cycle.rules(), cycle.kind(), NodeKind::Outcome, ACTION, &report);
    report.insert(ACTION, allowed.last().expect("갈 곳이 하나는 있다").clone());
    if report.get(ACTION) == Some("revisit") {
        let target = cycle
            .steps()
            .nodes()
            .iter()
            .find(|node| node.kind == NodeKind::Analysis)
            .expect("해석이 있다")
            .id;
        report.insert(TARGET, cycle.step_ref(target).to_string());
    }
    project.close_action_step(report).expect("판정을 닫는다");
    step_id(project, outcome)
}

/// Bootstrap 을 지나 **Experiment 하나를 그 판정으로 닫은** 프로젝트.
pub fn graph_with_one_closed_cycle(verdict: &str) -> Project {
    let (mut project, outcome) = graph_at_the_exit(verdict);
    let report = cycle_report(project.cycles().current(), verdict, outcome);
    project.close_cycle(report).expect("Cycle 을 닫는다");
    project
}

/// 지금 이 Cycle Report 에서 그 칸이 가질 수 있는 값 — 좁혀진 뒤의 것.
pub fn cycle_allowed_here(
    rules: &RuleSet,
    cycle: CycleKind,
    field: &str,
    report: &Report,
) -> Vec<String> {
    let constraint = rules
        .cycle_rules(cycle)
        .expect("선언된 Cycle Kind 여야 한다")
        .field_constraints
        .get(field)
        .expect("값 제약이 걸린 칸이어야 한다");
    let (allowed, _) = constraint.allowed_here(|other| report.get(other));
    allowed.to_vec()
}

/// 지금 이 Report 에서 그 칸이 가질 수 있는 값 — 좁혀진 뒤의 것.
pub fn allowed_here(
    rules: &RuleSet,
    cycle: CycleKind,
    kind: NodeKind,
    field: &str,
    report: &Report,
) -> Vec<String> {
    let step = rules.rules(cycle, kind).expect("선언된 Step Kind 여야 한다");
    let constraint = step
        .field_constraints
        .get(field)
        .expect("값 제약이 걸린 칸이어야 한다");
    let (allowed, _) = constraint.allowed_here(|other| report.get(other));
    allowed.to_vec()
}
