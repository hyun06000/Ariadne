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

// ── 실제 GIL Project 를 읽는 adapter ────────────────────────────────────
//
// Host UI Model §9.1.1 의 첫 조각. Companion 의 Tauri command 는 얇은 껍질이고, 실제로 읽는
// 차례는 여기 적은 것과 **같은 네 걸음**이다.
//
//   ProjectSession::open → monitor() → monitor_view_v1() → encode_view_v1()
//   ProjectSession::open → node_detail_v1() → encode_detail_v1()
//
// 그래서 이 시험이 지키는 것은 adapter 가 지키는 것이다. Tauri 를 세우지 않고도 잴 수 있는
// 자리에서 재는 이유는 하나다 — 창을 띄워야만 확인되는 사실은 회귀 시험이 되지 못한다.

/// adapter 가 View 를 얻는 그 차례 그대로 — **읽기만 하는 문**으로.
fn adapter_view(root: &Path) -> String {
    let session = ProjectSession::open_read_only(spec(), state_in(root)).expect("연다");
    let seen = session.monitor().expect("Snapshot");
    let view = monitor_view_v1(&seen).expect("View");
    encode_view_v1(&view).expect("옮긴다")
}

/// adapter 가 상세를 얻는 그 차례 그대로. 없으면 `None` — 물러서지 않는다.
fn adapter_detail(root: &Path, step_ref: &str) -> Option<String> {
    let session = ProjectSession::open_read_only(spec(), state_in(root)).expect("연다");
    let step: gil::StepRef = step_ref.parse().ok()?;
    match session.node_detail_v1(step) {
        Ok(detail) => Some(encode_detail_v1(&detail).expect("옮긴다")),
        Err(gil::DetailError::NotFound { .. }) => None,
    }
}

#[test]
fn a_real_project_gives_a_complete_monitor_view_v1() {
    let dir = reading_one("adapter-view");
    let view = decode_view_v1(&adapter_view(&dir)).expect("계약대로다");

    assert_eq!(view.schema_version, 1, "이 판이 아니다");
    assert!(!view.timeline.is_empty(), "시간선이 비었다");
    assert!(!view.current.cycle_ref.is_empty(), "지금 자리가 없다");
    assert!(view.captured_at_unix_ms > 1_700_000_000_000, "관측 시각이 비었다");
    // fixture 와 **같은 계약**이다 — 창에만 있는 Graph 사실을 따로 만들지 않는다(§9.1.1-3).
    let saved = decode_view_v1(
        &fs::read_to_string(fixtures().join("reading-one").join("view.json")).expect("view"),
    )
    .expect("View");
    assert_eq!(
        view.timeline.len(),
        saved.timeline.len(),
        "실제 Project 와 fixture 의 모양이 다르다"
    );
}

#[test]
fn a_closed_step_gives_every_report_field_it_has() {
    let dir = reading_one("adapter-detail");
    let view = decode_view_v1(&adapter_view(&dir)).expect("View");

    // 닫힌 Step 하나를 고른다 — Report 가 있는 자리다.
    let (cycle, step) = view
        .timeline
        .iter()
        .flat_map(|one| one.steps.iter().map(move |step| (one, step)))
        .find(|(_, step)| step.state == gil::NodeStateV1::Closed)
        .expect("닫힌 Step 이 하나는 있다");

    let said = adapter_detail(&dir, &step.step_ref).expect("있는 Step 이다");
    let detail = decode_detail_v1(&said).expect("계약대로다");
    assert_eq!(detail.step_ref, step.step_ref);
    assert_eq!(detail.cycle_ref, cycle.cycle_ref);
    let report = detail.report.expect("닫힌 Step 에는 Report 가 있다");
    assert!(!report.fields.is_empty(), "Report 가 비었다");

    // **한 칸도 빠지지 않는다.** 저장된 Report 의 이름이 전부 그대로 온다.
    let session = ProjectSession::open(spec(), state_in(&dir)).expect("연다");
    let found = session
        .project()
        .cycles()
        .nodes()
        .iter()
        .find(|one| one.id().to_ref().to_string() == cycle.cycle_ref)
        .expect("그 Cycle");
    let stored = found
        .steps()
        .nodes()
        .iter()
        .find(|node| found.step_ref(node.id).to_string() == step.step_ref)
        .and_then(|node| node.report.as_ref())
        .expect("저장된 Report");

    let seen: Vec<&str> = report.fields.iter().map(|one| one.name.as_str()).collect();
    let mut counted = 0usize;
    for name in stored.field_names() {
        assert!(seen.contains(&name), "{name} 칸이 상세에서 빠졌다");
        let given = report.fields.iter().find(|one| one.name == name).expect("칸");
        assert_eq!(Some(given.value.as_str()), stored.get(name), "{name} 의 값이 달라졌다");
        counted += 1;
    }
    assert_eq!(seen.len(), counted, "칸 수가 다르다");
}

#[test]
fn the_same_bare_step_id_in_another_project_does_not_answer_for_this_one() {
    let mine = reading_one("adapter-mine");
    let other = first_interview("adapter-other");

    // 두 Project 모두 `step:C1/S1` 이라는 **같은 글자**를 지닌다.
    let here = adapter_detail(&mine, "step:C1/S1").expect("이쪽에 있다");
    let there = adapter_detail(&other, "step:C1/S1").expect("저쪽에도 있다");
    assert_ne!(here, there, "서로 다른 Project 가 같은 상세를 내놓았다");

    // 그리고 한쪽에만 있는 주소는 **다른 쪽에서 없다**. 가까운 Step 으로 물러서지 않는다.
    let deep = "step:C3/S3";
    assert!(adapter_detail(&mine, deep).is_some(), "이쪽에는 있어야 한다");
    assert_eq!(
        adapter_detail(&other, deep),
        None,
        "저쪽에 없는 주소가 무언가로 답했다"
    );
}

#[test]
fn a_manual_refresh_reads_the_whole_view_again_and_never_merges() {
    let dir = reading_one("adapter-refresh");
    let first = adapter_view(&dir);

    // 사람이 그 Project 에서 **실제로 한 걸음 더 걷는다** — 창 밖에서 일어난 일이다.
    // `reading_one` 은 열린 Verify 위에 서 있으므로, 그것을 닫는 것이 다음 한 걸음이다.
    {
        let mut session = ProjectSession::open(spec(), state_in(&dir)).expect("연다");
        session
            .close_step(full_report(&spec(), CycleKind::Experiment, NodeKind::Verify))
            .expect("검증을 닫는다");
        opened(session.project_mut(), NodeKind::Analysis);
        session.commit().expect("눕힌다");
    }

    // 새로고침은 **완전한 View** 를 다시 읽는다. 옛 것에 조각을 얹지 않는다(§9.1.1-5).
    let again = adapter_view(&dir);
    assert_ne!(first, again, "새로고침이 새 사실을 가져오지 못했다");

    let before = decode_view_v1(&first).expect("View");
    let after = decode_view_v1(&again).expect("View");
    let count = |view: &gil::MonitorViewV1| -> usize {
        view.timeline.iter().map(|one| one.steps.len()).sum()
    };
    assert_eq!(count(&after), count(&before) + 1, "걸은 한 걸음이 보이지 않는다");
    // 닫힌 Verify 가 실제로 닫힌 것으로 보인다 — 옛 View 의 「열림」이 남아 있지 않다.
    let closed = |view: &gil::MonitorViewV1| -> usize {
        view.timeline
            .iter()
            .flat_map(|one| one.steps.iter())
            .filter(|step| step.state == gil::NodeStateV1::Closed)
            .count()
    };
    assert!(closed(&after) > closed(&before), "닫힌 것이 닫힌 것으로 보이지 않는다");
    // 그리고 **통째로** 바뀐 것이다 — 두 View 는 각자 완결된 사실이다.
    assert_eq!(after.schema_version, 1);
    assert!(!after.timeline.is_empty());
}

/// **이 조각의 합격 조건**(§9.1.1).
///
/// 열고, View 를 읽고, 상세를 읽고, 새로고침하고, 거절당한 뒤에도 `.gil` 의 Graph·Report·
/// Journey·Memory·Will, Artifact 파일, Snapshot 창고와 작업 파일이 **바이트 하나까지 같다**.
/// 관측이 객체를 새로 확정하지도, `state.yaml` 을 다시 눕히지도 않는다.
#[test]
fn opening_reading_and_refreshing_a_real_project_writes_nothing_at_all() {
    let dir = reading_one("adapter-read-only");
    let objects = |at: &Path| -> usize {
        every_file(&at.join(".gil").join("artifacts")).len()
    };

    let before = every_file(&dir);
    let before_objects = objects(&dir);
    assert!(before.len() >= 3, "볼 파일이 너무 적다: {}", before.len());
    assert!(before.keys().any(|name| name.contains("state.yaml")), "state.yaml 이 없다");
    assert!(before_objects > 0, "Snapshot 창고가 비었다");

    let view = decode_view_v1(&adapter_view(&dir)).expect("View");
    // 창이 하는 일을 **여러 번** 한다 — 열고, 읽고, 고르고, 새로고침한다.
    for _ in 0..3 {
        let _ = adapter_view(&dir);
        for one in &view.timeline {
            for step in &one.steps {
                let _ = adapter_detail(&dir, &step.step_ref);
            }
        }
    }
    // 거절도 아무것도 쓰지 않는다.
    assert_eq!(adapter_detail(&dir, "step:C99/S99"), None);
    assert_eq!(adapter_detail(&dir, "주소가 아니다"), None);

    let after = every_file(&dir);
    assert_eq!(before.len(), after.len(), "파일 수가 달라졌다");
    assert_eq!(before_objects, objects(&dir), "객체 수가 달라졌다");
    for (name, bytes) in &before {
        assert_eq!(Some(bytes), after.get(name), "{name} 의 바이트가 달라졌다");
    }
    // 그리고 잠금이 남지 않았다 — 사람의 다음 `gil` 명령이 곧바로 연다.
    assert!(ProjectSession::open(spec(), state_in(&dir)).is_ok(), "잠금이 남았다");
}

// ── 읽기만 하는 열기 ────────────────────────────────────────────────────
//
// §9.1.1 의 read-only 는 **건강한 Project 에서 바이트가 같았다**로 증명되지 않는다. 쓰는
// 쪽의 `ProjectSession::open` 은 미완의 복원을 되돌리고 tmp 잔해를 치우기 때문이다 — 그것이
// 옳지만, 관찰만 하는 창이 그러면 「보기만 했는데 달라졌다」가 된다.
//
// 그래서 **일부러 그 상태를 만들어 놓고** 재는 것이 여기 있는 시험들이다.

/// `.gil` 안의 모든 파일 — 잠금만 뺀다. 잠금은 논리 상태가 아니라 한 명령이 쥐었다 놓는 자리다.
fn gil_bytes(dir: &Path) -> BTreeMap<String, Vec<u8>> {
    every_file(&dir.join(".gil"))
        .into_iter()
        .filter(|(name, _)| !name.contains("lock"))
        .collect()
}

/// **끝나지 않은 복원**을 남긴다 — 준비 도중 `gil` 이 죽은 자리와 같은 모양.
///
/// `preparing-<pid>-<표>` 는 rollback 이 아직 걸리지 않은 단계라, 보통 명령이 열면 그냥
/// 치운다. 그래서 「읽기는 거절하고, 쓰는 명령은 여전히 복구한다」를 한 시험에서 잴 수 있다.
fn interrupted_restore(dir: &Path) -> PathBuf {
    let area = dir.join(".gil").join("restore");
    let half = area.join("preparing-4242-7");
    fs::create_dir_all(&half).expect("restore 영역을 만든다");
    fs::write(half.join("PLAN"), "끝나지 않은 계획").expect("계획을 남긴다");
    half
}

/// 되돌려야 할 **active** 를 남긴다 — 표식이 없으므로 보통 명령은 rollback 을 건다.
fn uncommitted_restore(dir: &Path) -> PathBuf {
    let active = dir.join(".gil").join("restore").join("active");
    fs::create_dir_all(&active).expect("restore 영역을 만든다");
    fs::write(active.join("PLAN"), "끝나지 않은 계획").expect("계획을 남긴다");
    active
}

/// **아무도 참조하지 않는 tmp 잔해**를 남긴다 — 확정 도중 죽은 자리와 같은 모양.
///
/// 이름이 `<pid>-<표>` 여야 GIL 이 제 잔해로 알아본다. 모르는 이름은 GIL 이 지우지 않고
/// 거절하므로(남의 파일을 치우지 않는다), 그 모양을 그대로 흉내 낸다.
fn tmp_residue(dir: &Path) -> PathBuf {
    let tmp = dir.join(".gil").join("artifacts").join("tmp");
    fs::create_dir_all(&tmp).expect("tmp 를 만든다");
    let leftover = tmp.join("4242-7");
    fs::write(&leftover, "확정되지 못한 바이트").expect("잔해를 남긴다");
    leftover
}

#[test]
fn a_read_only_open_refuses_an_interrupted_restore_instead_of_repairing_it() {
    let dir = reading_one("read-only-interrupted");
    let half = interrupted_restore(&dir);
    let before = gil_bytes(&dir);

    // **고치지 않는다. 있다는 사실만 말한다.**
    let refused = ProjectSession::open_read_only(spec(), state_in(&dir))
        .err()
        .expect("끝나지 않은 복원 위에서는 읽지 않는다");
    match &refused {
        gil::SessionError::NeedsRecovery { found, .. } => {
            assert!(found.contains("preparing-"), "무엇이 남았는지 말하지 않았다: {found}");
        }
        other => panic!("다른 거절이 나왔다: {other}"),
    }
    // 거절이 **빈 Graph 나 dirty 로 둔갑하지 않았다** — 애초에 View 가 만들어지지 않았다.
    assert!(half.exists(), "읽기만 하는 열기가 복원 영역을 치웠다");
    assert!(half.join("PLAN").is_file(), "계획이 사라졌다");
    assert_eq!(before, gil_bytes(&dir), "파일이 달라졌다");

    // 그리고 **쓰는 명령의 복구는 그대로다** — 같은 Project 를 보통 명령으로 열면 제자리로
    // 돌아간다. 읽기 전용 문이 생겼다고 GIL 본래의 동작이 바뀌지 않는다.
    ProjectSession::open(spec(), state_in(&dir)).expect("쓰는 열기는 복구하고 연다");
    assert!(!half.exists(), "보통 열기가 복구하지 않았다");
    // 복구가 끝났으니 이제 읽기만 하는 열기도 선다.
    assert!(ProjectSession::open_read_only(spec(), state_in(&dir)).is_ok(), "복구 뒤에도 막힌다");
}

#[test]
fn a_read_only_open_leaves_tmp_residue_exactly_where_it_found_it() {
    let dir = reading_one("read-only-tmp");
    let leftover = tmp_residue(&dir);
    let before = gil_bytes(&dir);

    // 잔해가 있어도 **읽기는 선다** — 아무도 참조하지 않는 것들이라 사실을 해치지 않는다.
    let view = decode_view_v1(&adapter_view(&dir)).expect("View");
    assert!(!view.timeline.is_empty(), "잔해 때문에 Graph 가 비었다");

    assert!(leftover.is_file(), "읽기만 하는 열기가 tmp 잔해를 치웠다");
    assert_eq!(
        fs::read_to_string(&leftover).expect("잔해"),
        "확정되지 못한 바이트",
        "잔해의 바이트가 달라졌다"
    );
    assert_eq!(before, gil_bytes(&dir), "파일이 달라졌다");

    // 그리고 **쓰는 명령의 잔해 회수는 그대로다.**
    ProjectSession::open(spec(), state_in(&dir)).expect("쓰는 열기");
    assert!(!leftover.exists(), "보통 열기가 잔해를 치우지 않았다");
}

#[test]
fn reading_a_damaged_project_changes_not_one_byte_and_not_one_object() {
    let dir = reading_one("read-only-damaged");
    uncommitted_restore(&dir);
    tmp_residue(&dir);

    let objects = |at: &Path| -> usize { every_file(&at.join(".gil").join("artifacts")).len() };
    let before = every_file(&dir);
    let before_objects = objects(&dir);

    // 창이 하는 일을 여러 번 한다 — 열고, 거절당하고, 다시 연다.
    for _ in 0..3 {
        let refused = ProjectSession::open_read_only(spec(), state_in(&dir));
        assert!(
            matches!(refused, Err(gil::SessionError::NeedsRecovery { .. })),
            "복구가 필요한 상태에서 다른 답이 나왔다"
        );
    }

    let after = every_file(&dir);
    assert_eq!(before.len(), after.len(), "파일 수가 달라졌다");
    assert_eq!(before_objects, objects(&dir), "객체 수가 달라졌다");
    for (name, bytes) in &before {
        assert_eq!(Some(bytes), after.get(name), "{name} 의 바이트가 달라졌다");
    }
}

#[test]
fn the_companion_reads_a_healthy_project_through_the_read_only_door_only() {
    let dir = reading_one("read-only-door");
    let before = every_file(&dir);

    // 읽기 전용 문으로 얻은 View 가 쓰는 문으로 얻은 것과 **같은 사실**이다.
    let strict = decode_view_v1(&adapter_view(&dir)).expect("View");
    let normal = {
        let session = ProjectSession::open(spec(), state_in(&dir)).expect("연다");
        let seen = session.monitor().expect("Snapshot");
        decode_view_v1(&encode_view_v1(&monitor_view_v1(&seen).expect("View")).expect("옮긴다"))
            .expect("View")
    };
    assert_eq!(strict.timeline.len(), normal.timeline.len(), "두 문이 다른 Graph 를 말한다");
    assert_eq!(strict.current.cycle_ref, normal.current.cycle_ref);

    // 그리고 상세도 같은 문으로 온다.
    let session = ProjectSession::open_read_only(spec(), state_in(&dir)).expect("연다");
    let step: gil::StepRef = strict.timeline[0].steps[0].step_ref.parse().expect("주소");
    let detail = session.node_detail_v1(step).expect("있는 Step");
    assert_eq!(detail.step_ref, strict.timeline[0].steps[0].step_ref);
    drop(session);

    assert_eq!(before, every_file(&dir), "읽기만 했는데 파일이 달라졌다");
    // 잠금이 남지 않았다 — 창이 떠 있어도 사람의 `gil` 명령이 막히지 않는다.
    assert!(ProjectSession::open(spec(), state_in(&dir)).is_ok(), "잠금이 남았다");
}

// ── Companion 설정이 Project 를 건드리지 않는다 ──────────────────────────
//
// Host UI Model §9.1.2 의 마지막 줄: 「시험은 설정 파일만 바뀌고 등록한 모든 Project 의
// 파일 수·바이트·Artifact 객체 수는 전혀 바뀌지 않음을 확인한다.」

/// 설정이 하는 일을 이 시험 안에서 그대로 밟는다 — 들이고, 차례를 바꾸고, 지운다.
///
/// Companion 의 `settings` 모듈은 `gil-companion` crate 안에 있어 여기서 부를 수 없다.
/// 그래서 여기서 재는 것은 **그 모듈이 무엇을 만지는가**가 아니라 **Project 가 무엇도
/// 겪지 않는가**다 — 후자가 명세가 요구한 것이다.
fn settings_like_work(config: &Path, roots: &[&Path]) {
    let file = config.join("companion-settings.json");
    for round in 0..3 {
        let listed: Vec<String> = roots
            .iter()
            .enumerate()
            .map(|(at, root)| {
                format!(
                    r#"{{"root":{:?},"scope_id":"project:{at}{round}","label":"이름{at}"}}"#,
                    root.display().to_string()
                )
            })
            .collect();
        let said = format!(
            r#"{{"schema_version":1,"projects":[{}],"last_selected":null,"window":{{"position":[10.0,20.0],"size":[520.0,900.0],"maximized":false}}}}"#,
            listed.join(",")
        );
        let beside = config.join(".companion-settings.json.tmp");
        fs::write(&beside, &said).expect("옆자리에 적는다");
        fs::rename(&beside, &file).expect("제자리로 옮긴다");
    }
    // 마지막에는 전부 지운 설정 — Project 제거와 같은 모양이다.
    fs::write(
        &file,
        r#"{"schema_version":1,"projects":[],"last_selected":null,"window":{"position":null,"size":[520.0,900.0],"maximized":false}}"#,
    )
    .expect("적는다");
}

#[test]
fn remembering_and_forgetting_projects_changes_not_one_project_byte() {
    let one = reading_one("settings-project-one");
    let other = first_interview("settings-project-two");
    let config = scratch("settings-config");

    let objects = |at: &Path| -> usize { every_file(&at.join(".gil").join("artifacts")).len() };
    let before_one = every_file(&one);
    let before_other = every_file(&other);
    let before_objects = (objects(&one), objects(&other));
    assert!(before_one.len() >= 3 && before_other.len() >= 1, "볼 파일이 너무 적다");
    assert!(before_objects.0 > 0, "Snapshot 창고가 비었다");

    // 등록하고, 차례를 바꾸고, 지운다. 그리고 그 사이사이 **실제로 읽는다** —
    // 창이 하는 일과 같은 순서다.
    settings_like_work(&config, &[&one, &other]);
    for root in [&one, &other] {
        let view = decode_view_v1(&adapter_view(root)).expect("View");
        for cycle in &view.timeline {
            for step in &cycle.steps {
                let _ = adapter_detail(root, &step.step_ref);
            }
        }
    }
    settings_like_work(&config, &[&one]);

    // **두 Project 모두 바이트 하나 다르지 않다.**
    for (label, root, before, objects_before) in [
        ("첫째", &one, &before_one, before_objects.0),
        ("둘째", &other, &before_other, before_objects.1),
    ] {
        let after = every_file(root);
        assert_eq!(before.len(), after.len(), "{label} Project 의 파일 수가 달라졌다");
        assert_eq!(objects_before, objects(root), "{label} 의 객체 수가 달라졌다");
        for (name, bytes) in before.iter() {
            assert_eq!(Some(bytes), after.get(name), "{label} 의 {name} 바이트가 달라졌다");
        }
    }

    // 그리고 **바뀐 것은 설정 폴더 안의 파일 하나뿐**이다.
    let mut left: Vec<String> = fs::read_dir(&config)
        .expect("훑는다")
        .flatten()
        .map(|one| one.file_name().to_string_lossy().into_owned())
        .collect();
    left.sort();
    assert_eq!(left, ["companion-settings.json"], "설정 폴더에 다른 것이 생겼다");

    // 잠금도 남지 않았다.
    for root in [&one, &other] {
        assert!(ProjectSession::open(spec(), state_in(root)).is_ok(), "잠금이 남았다");
    }
}

#[test]
fn the_settings_file_never_lands_inside_a_project() {
    let root = reading_one("settings-not-inside");
    let config = scratch("settings-outside");
    settings_like_work(&config, &[&root]);

    // 설정은 **앱 전용 폴더**에만 있다. Project 안 어디에도 없다(§9.1.2).
    for (name, _) in every_file(&root) {
        assert!(
            !name.contains("companion-settings"),
            "Project 안에 설정이 생겼다: {name}"
        );
    }
    assert!(config.join("companion-settings.json").is_file(), "설정이 제자리에 없다");

    // 설정이 자리를 기억하는 동안에도 그 자리는 **파일 안에만** 있다. 화면으로 나가지
    // 않는다는 것은 `gil-companion` 의 시험이 따로 지킨다.
    let file = config.join("companion-settings.json");
    fs::write(
        &file,
        format!(
            r#"{{"schema_version":1,"projects":[{{"root":{:?},"scope_id":"project:하나","label":"하나"}}],"last_selected":null,"window":{{"position":null,"size":[520.0,900.0],"maximized":false}}}}"#,
            root.display().to_string()
        ),
    )
    .expect("적는다");
    let said = fs::read_to_string(&file).expect("읽는다");
    assert!(said.contains("\"root\""), "설정이 자리를 기억하지 않는다");
    // 그래도 Project 안에는 설정이 없다.
    assert!(
        every_file(&root).keys().all(|name| !name.contains("companion-settings")),
        "Project 안에 설정이 생겼다"
    );
}

// ── 감시는 프로젝트를 붙들지 않는다 ─────────────────────────────────────
//
// Host UI Model §8 · Monitor Model §8.3. watcher 가 보내는 것은 hint 한 마디이고, 그
// 갈래는 Project 를 열지도 잠그지도 않는다. 붙들기 시작하면 사람이 `gil` 명령 하나를
// 쓸 수 없게 된다.

#[test]
fn a_running_watcher_never_holds_the_project_lock() {
    let dir = reading_one("watch-no-lock");
    let seen = std::sync::Arc::new(std::sync::atomic::AtomicUsize::new(0));

    let watching = gil::watch_hints(&dir, {
        let seen = seen.clone();
        move || {
            seen.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        }
    })
    .expect("감시를 세운다");

    // **감시가 도는 동안에도** 사람의 명령이 프로젝트를 연다 — 읽는 것도 쓰는 것도.
    for _ in 0..3 {
        let session = ProjectSession::open(spec(), state_in(&dir)).expect("쓰는 열기");
        drop(session);
        let session =
            ProjectSession::open_read_only(spec(), state_in(&dir)).expect("읽는 열기");
        drop(session);
    }
    drop(watching);
}

#[test]
fn watching_a_project_changes_not_one_byte() {
    let dir = reading_one("watch-read-only");
    let objects = |at: &Path| -> usize { every_file(&at.join(".gil").join("artifacts")).len() };
    let before = every_file(&dir);
    let before_objects = objects(&dir);

    let hints = std::sync::Arc::new(std::sync::atomic::AtomicUsize::new(0));
    let watching = gil::watch_hints(&dir, {
        let hints = hints.clone();
        move || {
            hints.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        }
    })
    .expect("감시를 세운다");

    // 사람이 Artifact 를 만진다. 감시는 그것을 **hint 한 마디**로만 받는다.
    fs::write(dir.join("사람이-고친-것.txt"), "바뀌었다").expect("적는다");
    // 그리고 우리가 읽는다 — 감시가 도는 동안에도 읽기는 읽기다.
    let _ = adapter_view(&dir);

    drop(watching);

    // 우리가 만든 파일 하나 말고는 **바이트 하나 다르지 않다.**
    fs::remove_file(dir.join("사람이-고친-것.txt")).expect("치운다");
    let after = every_file(&dir);
    assert_eq!(before.len(), after.len(), "파일 수가 달라졌다");
    assert_eq!(before_objects, objects(&dir), "객체 수가 달라졌다");
    for (name, bytes) in &before {
        assert_eq!(Some(bytes), after.get(name), "{name} 의 바이트가 달라졌다");
    }
    // 그리고 잠금이 남지 않았다.
    assert!(ProjectSession::open(spec(), state_in(&dir)).is_ok(), "잠금이 남았다");
}

#[test]
fn dropping_the_watch_really_stops_it() {
    let dir = reading_one("watch-stops");
    let hints = std::sync::Arc::new(std::sync::atomic::AtomicUsize::new(0));
    let watching = gil::watch_hints(&dir, {
        let hints = hints.clone();
        move || {
            hints.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        }
    })
    .expect("감시를 세운다");

    // 변화가 hint 로 닿는 것을 먼저 본다 — 감시가 정말 서 있었다는 증거다.
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
    fs::write(dir.join("하나.txt"), "가").expect("적는다");
    while hints.load(std::sync::atomic::Ordering::SeqCst) == 0 {
        assert!(std::time::Instant::now() < deadline, "감시가 변화를 알리지 못했다");
        std::thread::yield_now();
    }

    // **놓으면 멈춘다.**
    drop(watching);
    let after_stop = hints.load(std::sync::atomic::Ordering::SeqCst);
    for at in 0..5 {
        fs::write(dir.join(format!("뒤-{at}.txt")), "나").expect("적는다");
    }
    std::thread::sleep(std::time::Duration::from_millis(400));
    assert_eq!(
        hints.load(std::sync::atomic::Ordering::SeqCst),
        after_stop,
        "놓은 뒤에도 hint 가 왔다"
    );
}

#[test]
fn the_graph_file_and_ordinary_files_are_both_worth_a_hint() {
    let dir = reading_one("watch-both");
    let hints = std::sync::Arc::new(std::sync::atomic::AtomicUsize::new(0));
    let watching = gil::watch_hints(&dir, {
        let hints = hints.clone();
        move || {
            hints.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        }
    })
    .expect("감시를 세운다");

    let wait_for = |want: usize| {
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
        while hints.load(std::sync::atomic::Ordering::SeqCst) < want {
            assert!(
                std::time::Instant::now() < deadline,
                "hint {want} 개를 기다리다 지쳤다 (지금 {})",
                hints.load(std::sync::atomic::Ordering::SeqCst)
            );
            std::thread::yield_now();
        }
    };

    // ① 일반 Artifact 파일.
    fs::write(dir.join("보통-파일.txt"), "가").expect("적는다");
    wait_for(1);
    let after_ordinary = hints.load(std::sync::atomic::Ordering::SeqCst);

    // ② `state.yaml` 의 원자적 교체 — GIL 이 상태를 눕히는 그 모양.
    let state = state_in(&dir);
    let beside = dir.join(".gil").join("state.yaml.swap");
    fs::copy(&state, &beside).expect("옆에 적는다");
    fs::rename(&beside, &state).expect("제자리로 옮긴다");
    wait_for(after_ordinary + 1);

    drop(watching);
}
