//! **Companion fixture 가 진짜 GIL 에서 나왔는지.**
//!
//! 공용 UI bundle 은 canonical `MonitorViewV1`·`NodeDetailV1` JSON 만 먹는다. 그 JSON 을 손으로
//! 적으면 화면이 코드와 따로 낡는다 — 그래서 **실제 Project 를 걸어 만들고**, 저장된 fixture 가
//! 그것과 한 글자도 다르지 않은지 여기서 잰다.
//!
//! 다시 만들려면:
//!
//! ```text
//! GIL_WRITE_FIXTURES=1 cargo test --test companion
//! ```

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use gil::{
    CycleKind, NodeKind, ProjectSession, decode_detail_v1, decode_view_v1, encode_detail_v1,
    encode_view_v1, monitor_view_v1,
};

mod common;
use common::{bootstrap_from, contract, full_report, opened, spec};

/// 저장소 안의 fixture 자리 — 공용 bundle 옆이다.
fn fixtures() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("ui/fixtures")
}

fn scratch(label: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("gil-companion-{label}"));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).expect("시험이 쓸 자리를 만든다");
    dir
}

fn state_in(dir: &Path) -> PathBuf {
    dir.join(gil::STATE_PATH)
}

/// 한 Project 의 View 와 모든 Step 의 상세를 canonical JSON 으로.
fn canonical(dir: &Path) -> (String, String) {
    let session = ProjectSession::open(spec(), state_in(dir)).expect("되살린다");
    let seen = session.monitor().expect("Snapshot");
    let view = monitor_view_v1(&seen).expect("View");

    // 상세는 **Step 주소로 찾는 지도** 하나다. bundle 이 고른 Step 만 꺼내 쓴다.
    let mut details: BTreeMap<String, serde_json::Value> = BTreeMap::new();
    for entry in &seen.timeline {
        for step in &entry.steps {
            let one = session
                .node_detail_v1(step.step_ref)
                .expect("시간선에 있는 Step");
            let text = encode_detail_v1(&one).expect("옮긴다");
            details.insert(
                step.step_ref.to_string(),
                serde_json::from_str(&text).expect("JSON"),
            );
        }
    }
    drop(session);

    // **관측 시각 하나만 0 으로 눕힌다.** 그것은 Project 의 사실이 아니라 「언제 봤는가」라서
    // 돌릴 때마다 달라지고, 그대로 두면 fixture 가 매번 바뀌어 검토할 수 없다. `0` 은 이 판이
    // 허락하는 값(epoch)이므로 canonical 계약을 벗어나지 않는다.
    let mut wire: serde_json::Value =
        serde_json::from_str(&encode_view_v1(&view).expect("옮긴다")).expect("JSON");
    wire["captured_at_unix_ms"] = serde_json::json!(0);

    (
        serde_json::to_string(&wire).expect("옮긴다"),
        serde_json::to_string(&details).expect("옮긴다"),
    )
}

/// 첫 Project — 판독 실험 1 의 여정 그대로.
fn reading_one(label: &str) -> PathBuf {
    let dir = scratch(label);
    fs::write(dir.join("a.txt"), "가").expect("세계를 하나 둔다");
    let mut session = ProjectSession::start(spec(), state_in(&dir)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());
    session.commit().expect("눕힌다");

    let rules = spec();
    let define = |problem: &str, success: &str| {
        full_report(&rules, CycleKind::Experiment, NodeKind::Define)
            .with("problem", problem)
            .with("success_condition", success)
    };

    // 실패한 첫 실험.
    opened(session.project_mut(), NodeKind::Define);
    session
        .close_step(define(
            "병렬로 모은 결과를 점수로 정렬할 때 순서가 실행마다 달라진다",
            "같은 입력에 대해 100회 실행이 모두 같은 순서를 낸다",
        ))
        .expect("문제를 고정한다");
    for kind in [NodeKind::Hypothesis, NodeKind::Verify, NodeKind::Analysis] {
        opened(session.project_mut(), kind);
        session
            .close_step(full_report(&rules, CycleKind::Experiment, kind))
            .expect("걷는다");
    }
    opened(session.project_mut(), NodeKind::Outcome);
    session
        .close_step(
            full_report(&rules, CycleKind::Experiment, NodeKind::Outcome)
                .with("verdict", "failure")
                .with(
                    "lesson",
                    "점수만 사용하는 안정 정렬은 비결정적인 병렬 수집 순서를 그대로 보존함",
                )
                .with(common::ACTION, "close_cycle")
                .with(common::REASON, "이 갈래로는 순서를 고정할 수 없다"),
        )
        .expect("판정을 닫는다");
    {
        let cycle = session.project().cycles().current();
        let last = cycle.steps().current().expect("판정에 서 있다");
        let mut report = common::cycle_report(cycle, "failure", last);
        report.insert(common::CYCLE_TARGET, "cycle:C1");
        report.insert("handoff_summary", "점수만으로는 동점의 순서를 정할 수 없었다");
        session.close_cycle(report).expect("Cycle 을 닫는다");
        session.commit().expect("눕힌다");
    }
    drop(session);

    // 되돌아가 새 갈래를 연다.
    let mut session = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");
    session.revisit_cycle().expect("되돌아간다");
    session.commit().expect("눕힌다");
    session
        .open_branch_cycle(CycleKind::Experiment)
        .expect("새 갈래를 연다");
    session.commit().expect("눕힌다");

    opened(session.project_mut(), NodeKind::Define);
    session
        .close_step(define(
            "동점일 때 고유 ID를 보조 키로 사용하면 순서가 고정되는가",
            "100회 결과가 같고 ID의 고유성이 확인된다",
        ))
        .expect("새 문제를 고정한다");
    opened(session.project_mut(), NodeKind::Hypothesis);
    session
        .close_step(full_report(&rules, CycleKind::Experiment, NodeKind::Hypothesis))
        .expect("가설을 닫는다");
    session
        .open_action_step(
            NodeKind::Verify,
            contract(
                "동점 순서가 고정되는지 본다",
                "점수와 ID의 복합 정렬을 구현하고 100회 반복 실행한다",
                "100회 결과가 같고 ID의 고유성이 확인된다",
            ),
        )
        .expect("검증을 연다");
    session.commit().expect("눕힌다");
    drop(session);
    dir
}

/// 둘째 Project — **최소 크기.** 아직 Interview 안에 서 있고 세계가 dirty 하다.
fn first_interview(label: &str) -> PathBuf {
    let dir = scratch(label);
    fs::write(dir.join("notes.md"), "처음 적은 것").expect("세계를 하나 둔다");
    let mut session = ProjectSession::start(spec(), state_in(&dir)).expect("시작한다");
    session
        .open_action_step(
            NodeKind::Question,
            contract(
                "무엇부터 물어야 하는지 정한다",
                "사용자가 실제로 막힌 자리를 세 줄로 적는다",
                "막힌 자리 하나가 문장으로 적힌다",
            ),
        )
        .expect("첫 질문을 연다");
    session.commit().expect("눕힌다");
    drop(session);
    // 세계를 흔들어 둔다 — 두 Project 가 눈에 띄게 달라야 전환이 보인다.
    fs::write(dir.join("notes.md"), "손으로 고쳐 놓았다").expect("세계를 흔든다");
    dir
}

/// 셋째 Project — **밀도 시험용.** Cycle 과 Step 이 많아 접기의 값이 드러난다.
///
/// 새 domain 사실을 만들지 않는다 — 기존 Grammar 로 평범하게 걸은 여정일 뿐이다.
fn dense(label: &str) -> PathBuf {
    let dir = scratch(label);
    fs::write(dir.join("src.txt"), "처음").expect("세계를 하나 둔다");
    let mut session = ProjectSession::start(spec(), state_in(&dir)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());
    session.commit().expect("눕힌다");

    let rules = spec();
    // 실험 하나를 끝까지 걷고 닫는다.
    let walk = |session: &mut ProjectSession, problem: &str, verdict: &str, target: Option<&str>| {
        opened(session.project_mut(), NodeKind::Define);
        session
            .close_step(
                full_report(&rules, CycleKind::Experiment, NodeKind::Define)
                    .with("problem", problem)
                    .with("success_condition", "재현되면 성공이다"),
            )
            .expect("문제를 고정한다");
        for kind in [NodeKind::Hypothesis, NodeKind::Verify, NodeKind::Analysis] {
            opened(session.project_mut(), kind);
            session
                .close_step(full_report(&rules, CycleKind::Experiment, kind))
                .expect("걷는다");
        }
        opened(session.project_mut(), NodeKind::Outcome);
        session
            .close_step(
                full_report(&rules, CycleKind::Experiment, NodeKind::Outcome)
                    .with("verdict", verdict)
                    .with("lesson", format!("{problem} — 여기까지 배웠다"))
                    // 되돌아감의 대상은 **Cycle Report** 가 진다 — Step 판정은 경계로 넘길
                    // 뿐이다(`reading_one` 과 같은 계약).
                    .with(common::ACTION, "close_cycle")
                    .with(common::REASON, "다음으로 넘긴다"),
            )
            .expect("판정을 닫는다");
        let cycle = session.project().cycles().current();
        let last = cycle.steps().current().expect("판정에 서 있다");
        let mut report = common::cycle_report(cycle, verdict, last);
        if let Some(target) = target {
            report.insert(common::CYCLE_TARGET, target);
        }
        session.close_cycle(report).expect("Cycle 을 닫는다");
        session.commit().expect("눕힌다");
    };

    // bootstrap 이 Interview(C1)를 닫고 **이미 실험 하나를 열어 두었다.** 그것부터 걷는다.
    walk(&mut session, "첫 실험", "success", None);
    // C3 · C4 — 곧게 이어지는 순차 자식 둘. 같은 열에 머문다.
    session.open_child_cycle(CycleKind::Experiment).expect("자식을 연다");
    walk(&mut session, "둘째 실험", "success", None);
    session.open_child_cycle(CycleKind::Experiment).expect("자식을 연다");
    walk(&mut session, "셋째 실험", "failure", Some("cycle:C2"));
    drop(session);

    // C5 — 되돌아가 연 형제. 새 열이 생긴다.
    let mut session = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");
    session.revisit_cycle().expect("되돌아간다");
    session.commit().expect("눕힌다");
    session
        .open_branch_cycle(CycleKind::Experiment)
        .expect("새 갈래를 연다");
    session.commit().expect("눕힌다");
    opened(session.project_mut(), NodeKind::Define);
    session
        .close_step(
            full_report(&rules, CycleKind::Experiment, NodeKind::Define)
                .with("problem", "되돌아와 다시 세운 문제")
                .with("success_condition", "이번에는 재현된다"),
        )
        .expect("문제를 고정한다");
    opened(session.project_mut(), NodeKind::Hypothesis);
    session
        .close_step(full_report(&rules, CycleKind::Experiment, NodeKind::Hypothesis))
        .expect("가설을 닫는다");
    for kind in [NodeKind::Verify, NodeKind::Analysis] {
        opened(session.project_mut(), kind);
        session
            .close_step(full_report(&rules, CycleKind::Experiment, kind))
            .expect("걷는다");
    }
    opened(session.project_mut(), NodeKind::Outcome);
    session
        .close_step(
            full_report(&rules, CycleKind::Experiment, NodeKind::Outcome)
                .with("verdict", "failure")
                .with("lesson", "갈래를 바꿔도 같은 곳에서 막혔다")
                .with(common::ACTION, "close_cycle")
                .with(common::REASON, "다음으로 넘긴다"),
        )
        .expect("판정을 닫는다");
    {
        let cycle = session.project().cycles().current();
        let last = cycle.steps().current().expect("판정에 서 있다");
        let mut report = common::cycle_report(cycle, "failure", last);
        report.insert(common::CYCLE_TARGET, "cycle:C2");
        session.close_cycle(report).expect("Cycle 을 닫는다");
    }
    session.commit().expect("눕힌다");
    drop(session);

    // C6 — **오른쪽 열의 실패에서 왼쪽 목표로** 되돌아간 갈래.
    //
    // C5 는 형제라 1번 열에 섰고 되돌아갈 목표 C2 는 0번 열에 있다. 그래서 이 여정에만
    // **열을 가로지르는 되돌아감**이 있다. 좌우 routing 을 재려면 이런 자리가 하나는
    // 있어야 한다 — 같은 열끼리의 되돌아감만으로는 방향 규칙을 잴 수 없다.
    let mut session = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");
    session.revisit_cycle().expect("되돌아간다");
    session.commit().expect("눕힌다");
    session
        .open_branch_cycle(CycleKind::Experiment)
        .expect("새 갈래를 연다");
    session.commit().expect("눕힌다");
    opened(session.project_mut(), NodeKind::Define);
    session
        .close_step(
            full_report(&rules, CycleKind::Experiment, NodeKind::Define)
                .with("problem", "세 번째로 다시 세운 문제")
                .with("success_condition", "이번에는 막히지 않는다"),
        )
        .expect("문제를 고정한다");
    opened(session.project_mut(), NodeKind::Hypothesis);
    session
        .close_step(full_report(&rules, CycleKind::Experiment, NodeKind::Hypothesis))
        .expect("가설을 닫는다");
    session
        .open_action_step(
            NodeKind::Verify,
            contract("다시 재현해 본다", "같은 입력으로 100회 돌린다", "100회가 모두 같다"),
        )
        .expect("검증을 연다");
    session.commit().expect("눕힌다");
    drop(session);
    dir
}

/// 저장된 fixture 와 지금 코드가 만드는 것이 같은가.
fn check(name: &str, made: &str) {
    let at = fixtures().join(name);
    if std::env::var("GIL_WRITE_FIXTURES").is_ok() {
        fs::create_dir_all(at.parent().expect("자리")).expect("자리를 만든다");
        fs::write(&at, made).expect("적는다");
        return;
    }
    let saved = fs::read_to_string(&at).unwrap_or_else(|_| {
        panic!("{name} 이 없다 — `GIL_WRITE_FIXTURES=1 cargo test --test companion` 로 만든다")
    });
    assert_eq!(
        saved.trim(),
        made.trim(),
        "{name} 이 지금 코드가 만드는 것과 다르다 — \
         `GIL_WRITE_FIXTURES=1 cargo test --test companion` 로 다시 만든다"
    );
}

#[test]
fn the_two_fixtures_are_what_gil_actually_produces() {
    // 고르개에 적히는 이름도 **여기서** 함께 난다. 사람이 손으로 적은 Cycle·Step 수는
    // fixture 가 자라는 순간 낡는다(실측: dense 가 5·22 에서 6·27 로 자라자 이름만 남았다).
    let mut listed = Vec::new();
    for (label, name, dir) in [
        ("reading-one", "Ariadne — 정렬 순서 실험", reading_one("reading-one")),
        ("first-interview", "새 프로젝트 — 첫 인터뷰", first_interview("first-interview")),
        ("dense", "밀도 시험", dense("dense")),
    ] {
        let (view, details) = canonical(&dir);
        check(&format!("{label}/view.json"), &view);
        check(&format!("{label}/details.json"), &details);

        let decoded = decode_view_v1(&view).expect("View");
        listed.push(serde_json::json!({
            "scope_id": format!("fixture:{label}"),
            "label": name,
            "origin": "fixture",
            "cycles": decoded.timeline.len(),
            "steps": decoded.timeline.iter().map(|one| one.steps.len()).sum::<usize>(),
        }));
    }
    let registry = serde_json::to_string_pretty(&serde_json::Value::Array(listed))
        .expect("등록부");
    check("projects.json", &format!("{registry}\n"));
}

#[test]
fn every_saved_fixture_decodes_as_the_canonical_contract() {
    for label in ["reading-one", "first-interview", "dense"] {
        let view = fs::read_to_string(fixtures().join(label).join("view.json"))
            .unwrap_or_else(|_| panic!("{label}/view.json"));
        let decoded = decode_view_v1(&view).expect("canonical View 다");
        assert_eq!(decoded.schema_version, 1);
        assert!(!decoded.timeline.is_empty(), "{label} 의 시간선이 비었다");

        let details: BTreeMap<String, serde_json::Value> = serde_json::from_str(
            &fs::read_to_string(fixtures().join(label).join("details.json")).expect("details"),
        )
        .expect("JSON");
        // 시간선의 **모든** Step 에 상세가 있다 — bundle 이 어느 것을 고르든 답이 있다.
        let mut counted = 0usize;
        for one in &decoded.timeline {
            for step in &one.steps {
                let at = details
                    .get(&step.step_ref)
                    .unwrap_or_else(|| panic!("{} 의 상세가 없다", step.step_ref));
                let detail = decode_detail_v1(&at.to_string()).expect("canonical 상세다");
                assert_eq!(detail.step_ref, step.step_ref);
                assert_eq!(detail.kind, step.kind, "{} 의 종류가 다르다", step.step_ref);
                counted += 1;
            }
        }
        assert!(counted >= 1, "{label} 에 Step 이 없다");
    }
}

#[test]
fn the_projection_itself_still_carries_a_real_observation_time() {
    // fixture 에서만 눕힌다 — 투영은 여전히 진짜 시각을 낸다.
    let dir = first_interview("real-time");
    let session = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");
    let view = monitor_view_v1(&session.monitor().expect("Snapshot")).expect("View");
    assert!(view.captured_at_unix_ms > 1_700_000_000_000, "시각이 비었다");
}

#[test]
fn the_dense_fixture_really_is_dense() {
    let view = decode_view_v1(
        &fs::read_to_string(fixtures().join("dense").join("view.json")).expect("view"),
    )
    .expect("View");
    let steps: usize = view.timeline.iter().map(|one| one.steps.len()).sum();
    assert!(view.timeline.len() >= 5, "Cycle 이 적다: {}", view.timeline.len());
    assert!(steps >= 20, "Step 이 적다: {steps}");
    // 진짜 형제가 있어야 열이 갈린다 — 한 부모에 자식 둘.
    let mut children: BTreeMap<String, usize> = BTreeMap::new();
    for one in &view.timeline {
        if let Some(parent) = &one.parent_cycle_ref {
            *children.entry(parent.clone()).or_default() += 1;
        }
    }
    assert!(
        children.values().any(|count| *count >= 2),
        "형제가 없어 새 열이 생기지 않는다: {children:?}"
    );
    // 그리고 되돌아감이 **둘** 있다 — 하나는 같은 열끼리, 하나는 열을 가로지른다.
    // 좌우 routing 은 뒤의 것이 없으면 잴 수 없다.
    let back: Vec<_> = view
        .timeline
        .iter()
        .filter(|one| one.revisit_from_cycle_ref.is_some())
        .collect();
    assert!(back.len() >= 2, "되돌아감이 {}건뿐이다", back.len());
    // 하나는 **형제 열에서 실패한** Cycle 이 출처다. 그 Cycle 은 제 부모의 맏이가 아니다.
    let mut eldest: BTreeMap<String, String> = BTreeMap::new();
    for one in &view.timeline {
        if let Some(parent) = &one.parent_cycle_ref {
            eldest.entry(parent.clone()).or_insert_with(|| one.cycle_ref.clone());
        }
    }
    let crossing = back.iter().any(|one| {
        let failed = one.revisit_from_cycle_ref.as_ref().expect("실패 Cycle");
        view.timeline
            .iter()
            .find(|c| &c.cycle_ref == failed)
            .and_then(|c| c.parent_cycle_ref.clone())
            .is_some_and(|parent| eldest.get(&parent) != Some(failed))
    });
    assert!(crossing, "열을 가로지르는 되돌아감이 없다");
}

/// **완료된 revisit 의 두 참조는 서로 다른 것을 가리킨다** (Host UI Model §12-18).
///
///   `revisit_from`  이 갈래를 낳은 실패 Cycle
///   `parent`        실제로 되돌아간 목표 Cycle
///
/// 화면이 점선을 어느 쪽으로 그리든, 이 사실이 먼저 서 있어야 한다. 둘이 같아지면
/// "무엇이 실패했고 어디로 돌아갔는가"를 화면이 답할 방법이 없다.
#[test]
fn a_finished_revisit_names_a_failure_and_a_target_that_are_not_the_same() {
    for label in ["reading-one", "dense"] {
        let view = decode_view_v1(
            &fs::read_to_string(fixtures().join(label).join("view.json")).expect("view"),
        )
        .expect("View");
        let mut seen = 0;
        for one in &view.timeline {
            let Some(failed) = &one.revisit_from_cycle_ref else { continue };
            let parent = one
                .parent_cycle_ref
                .as_ref()
                .unwrap_or_else(|| panic!("{label}: {} 에 되돌아간 목표가 없다", one.cycle_ref));
            assert_ne!(
                failed, parent,
                "{label}: {} 의 실패 Cycle 과 목표 Cycle 이 같다",
                one.cycle_ref
            );
            // 그리고 둘 다 실재하는 Cycle 이다 — 화면이 anchor 로 쓸 자리가 있다.
            for named in [failed, parent] {
                let found = view.timeline.iter().find(|c| &c.cycle_ref == named);
                let found = found
                    .unwrap_or_else(|| panic!("{label}: {named} 가 timeline 에 없다"));
                assert!(!found.steps.is_empty(), "{label}: {named} 에 표시할 Step 이 없다");
            }
            seen += 1;
        }
        assert!(seen > 0, "{label} 에 완료된 되돌아감이 없다");
    }
}

#[test]
fn each_fixture_is_a_different_project() {
    let read = |label: &str| {
        decode_view_v1(&fs::read_to_string(fixtures().join(label).join("view.json")).expect("view"))
            .expect("View")
    };
    let one = read("reading-one");
    let other = read("first-interview");

    // 서로 다른 Journey 다 — 같은 Graph 를 두 번 보여 주는 것이 아니다.
    assert_ne!(one.timeline.len(), other.timeline.len(), "두 Project 가 같은 모양이다");
    assert_ne!(one.world.state, other.world.state, "세계 상태가 같아 전환이 눈에 띄지 않는다");
    assert!(one.timeline.len() >= 3, "첫 Project 는 갈래가 있어야 한다");
    assert_eq!(other.timeline.len(), 1, "둘째 Project 는 최소 크기다");

    // 셋째는 **크기**로 다르다 — 여럿을 접었을 때 정말 조밀해지는지 재는 자리다.
    let dense = read("dense");
    let steps = |view: &gil::MonitorViewV1| -> usize {
        view.timeline.iter().map(|c| c.steps.len()).sum()
    };
    assert!(dense.timeline.len() > one.timeline.len(), "밀도 fixture 에 Cycle 이 더 많지 않다");
    assert!(steps(&dense) > steps(&one), "밀도 fixture 에 Step 이 더 많지 않다");
}

/// 고르개에 적힌 Project 와 실제로 놓인 fixture 가 **정확히** 같다.
///
/// 한쪽만 고치면 창은 없는 파일을 읽으러 가거나, 있는 Project 를 영영 못 보여 준다.
#[test]
fn the_switcher_lists_exactly_the_fixtures_that_exist() {
    #[derive(serde::Deserialize)]
    struct Listed {
        scope_id: String,
        label: String,
        cycles: usize,
        steps: usize,
    }
    let listed: Vec<Listed> = serde_json::from_str(
        &fs::read_to_string(fixtures().join("projects.json")).expect("projects.json"),
    )
    .expect("등록부");

    let mut on_disk: Vec<String> = fs::read_dir(fixtures())
        .expect("fixtures")
        .filter_map(|entry| {
            let entry = entry.expect("entry");
            entry
                .file_type()
                .expect("type")
                .is_dir()
                .then(|| entry.file_name().to_string_lossy().into_owned())
        })
        .collect();
    on_disk.sort();

    let mut named: Vec<String> = listed
        .iter()
        .map(|one| {
            let folder = one.scope_id.split(':').next_back().expect("scope").to_string();
            assert!(one.scope_id.starts_with("fixture:"), "{} 가 fixture scope 가 아니다", one.scope_id);
            assert!(!one.label.trim().is_empty(), "{folder} 에 사람이 읽을 이름이 없다");
            for file in ["view.json", "details.json"] {
                assert!(fixtures().join(&folder).join(file).is_file(), "{folder}/{file} 이 없다");
            }
            // 그리고 적힌 수치가 **그 fixture 의 실제 View** 와 같다.
            let view = decode_view_v1(
                &fs::read_to_string(fixtures().join(&folder).join("view.json")).expect("view"),
            )
            .expect("View");
            assert_eq!(one.cycles, view.timeline.len(), "{folder}: Cycle 수가 어긋난다");
            assert_eq!(
                one.steps,
                view.timeline.iter().map(|c| c.steps.len()).sum::<usize>(),
                "{folder}: Step 수가 어긋난다"
            );
            folder
        })
        .collect();
    named.sort();
    assert_eq!(named, on_disk, "등록부와 실제 fixture 가 어긋난다");
}

// ── Companion 이 아무것도 바꾸지 않는다 ──────────────────────────────────
//
// 창이 읽기 전용이라는 것은 button 이 없다는 말로 증명되지 않는다. **그 창이 먹는 것이
// 무엇인지**로 증명한다 — fixture 는 정적 JSON 이고, 그것을 만드는 경로가 `.gil` 을
// 건드리지 않는다는 사실이 증거다.

/// 주석을 걷어낸 코드만 — `/* */`·`<!-- -->` 덩이와 `//` 줄을 지운다.
fn without_comments(source: &str) -> String {
    let mut text = source.to_string();
    for (open, close) in [("/*", "*/"), ("<!--", "-->")] {
        let mut kept = String::with_capacity(text.len());
        let mut rest = text.as_str();
        while let Some(at) = rest.find(open) {
            kept.push_str(&rest[..at]);
            rest = match rest[at..].find(close) {
                Some(end) => &rest[at + end + close.len()..],
                None => "",
            };
        }
        kept.push_str(rest);
        text = kept;
    }
    text.lines()
        .map(|line| line.split("//").next().unwrap_or(""))
        .collect::<Vec<_>>()
        .join("\n")
}

/// 한 자리 아래 모든 파일의 (경로, 내용) — 바뀐 것이 하나라도 있으면 다르게 나온다.
fn every_file(root: &Path) -> BTreeMap<String, Vec<u8>> {
    fn walk(at: &Path, base: &Path, into: &mut BTreeMap<String, Vec<u8>>) {
        let Ok(entries) = fs::read_dir(at) else { return };
        for entry in entries.flatten() {
            let path = entry.path();
            match path.is_dir() {
                true => walk(&path, base, into),
                false => {
                    let name = path
                        .strip_prefix(base)
                        .expect("아래에 있다")
                        .display()
                        .to_string();
                    into.insert(name, fs::read(&path).unwrap_or_default());
                }
            }
        }
    }
    let mut found = BTreeMap::new();
    walk(root, root, &mut found);
    found
}

#[test]
fn making_the_fixtures_touches_no_gil_state_no_artifact_no_journey() {
    let dir = reading_one("read-only-evidence");
    let before = every_file(&dir);
    assert!(before.len() >= 3, "볼 파일이 너무 적다: {}", before.len());
    assert!(
        before.keys().any(|name| name.contains("state.yaml")),
        "state.yaml 을 보지 못했다"
    );
    assert!(
        before.keys().any(|name| name.contains("artifacts")),
        "Artifact 창고를 보지 못했다"
    );

    // Companion 이 먹는 것을 **여러 번** 만든다 — 창이 여러 번 여는 일과 같다.
    for _ in 0..3 {
        let (view, details) = canonical(&dir);
        assert!(!view.is_empty() && !details.is_empty());
    }

    let after = every_file(&dir);
    assert_eq!(
        before.len(),
        after.len(),
        "파일 수가 달라졌다 — 무언가 생기거나 사라졌다"
    );
    for (name, bytes) in &before {
        assert_eq!(
            Some(bytes),
            after.get(name),
            "{name} 의 내용이 바뀌었다"
        );
    }
    // 그리고 잠금이 남지 않았다 — 다음 명령이 곧바로 연다.
    assert!(ProjectSession::open(spec(), state_in(&dir)).is_ok(), "잠금이 남았다");
}

#[test]
fn the_bundle_is_static_and_asks_for_no_server_no_port_no_capability_url() {
    let ui = Path::new(env!("CARGO_MANIFEST_DIR")).join("ui");
    let mut read = 0usize;
    for (name, bytes) in every_file(&ui) {
        // XML namespace 는 **주소가 아니다** — 아무도 그것을 받아오지 않는다. 이름일 뿐이라
        // 검사에서 빼고 본다(그러지 않으면 `createElementNS` 한 줄에 걸린다).
        let text = String::from_utf8_lossy(&bytes)
            .replace("http://www.w3.org/2000/svg", "")
            .replace("https://schema.tauri.app/config/2", "");
        // 그 밖에 바깥으로 나가는 길은 하나도 없다.
        for forbidden in ["http://", "https://", "ws://", "127.0.0.1", "localhost"] {
            assert!(
                !text.contains(forbidden),
                "{name} 에 바깥 주소 {forbidden} 이 있다"
            );
        }
        read += 1;
    }
    assert!(read >= 5, "bundle 파일이 너무 적다: {read}");

    // bundle 은 어느 Host 에도 묶이지 않는다 — **코드에** 그 이름이 없다.
    //
    // 주석은 세지 않는다. 계보를 적은 글에는 시제품이 무엇을 썼는지가 나오고, 그것을
    // 걷어냈다는 사실이야말로 이 시험이 지키려는 것이다.
    for name in ["companion.js", "companion.css", "index.html"] {
        let code = without_comments(&fs::read_to_string(ui.join(name)).expect(name));
        for host in ["tauri", "__TAURI__", "window.openai", "invoke("] {
            assert!(!code.contains(host), "{name} 의 코드가 {host} 에 묶였다");
        }
    }
    // 그리고 Host 로 가는 문은 하나다.
    let bundle = fs::read_to_string(ui.join("companion.js")).expect("bundle");
    assert!(bundle.contains("window.GIL_HOST"), "Host 문이 없다");
}
