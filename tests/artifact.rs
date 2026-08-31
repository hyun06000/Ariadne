//! format 4 — **Artifact 시간선이 처음부터 완전하다.**
//!
//! 여기서 재는 것은 하나다: 저장된 상태가 언제나 다음을 **동시에** 만족하는가.
//!
//! ```text
//! registry 가 있다 · 이름이 유일하다 · 가리키는 manifest 가 실재한다
//! 모든 Cycle 에 Entry 가 있다 · 열린 Cycle 에 Exit 이 없다 · 닫힌 Cycle 에 Exit 이 있다
//! 닫힌 Verify 에 세계가 있다 · 그 밖의 Kind 에는 없다
//! 자식의 Entry = 부모의 Exit · 뿌리의 Entry = gil start 의 최초 세계
//! ```
//!
//! 「나중에 채울 null」이 없다. 그래서 이 시험들의 대부분은 **없어야 할 것이 있는 파일**과
//! **있어야 할 것이 없는 파일**을 만들어 거절되는지 묻는다.

use std::fs;
use std::path::{Path, PathBuf};

use serde_norway::Value;

use gil::{
    CycleKind, ManifestAddress, NodeKind, Project, ProjectSession, RuleSet, SnapshotRef,
    StoreError, load, save,
};

mod common;
use common::{
    ACTION, REASON, bootstrap, bootstrap_from, close_here, cycle_report, first_world, full_report,
    imagined_world, opened, plan, scratch, snapshot, sow_world, spec, step_id, up_to_verify, walked,
};

// ── 연장 ───────────────────────────────────────────────────────────────────

fn state_in(dir: &Path) -> PathBuf {
    dir.join(gil::STATE_PATH)
}

/// 그 자리에 파일을 놓는다.
fn write(root: &Path, path: &str, bytes: &str) {
    let at = root.join(path);
    if let Some(parent) = at.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(&at, bytes).unwrap();
}

/// **빈 자리**를 하나 만든다 — [`scratch`] 와 달리 세계를 미리 심지 않는다.
fn bare(label: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("gil-artifact-{label}"));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).expect("시험이 쓸 자리를 만든다");
    dir
}

/// 저장했다 다시 세운다 — **manifest 객체까지 실재하는 자리에서.**
fn round_trip(label: &str, project: &Project) -> Project {
    let path = state_in(&scratch(label));
    save(project, &path).expect("눕힐 수 있어야 한다");
    load(spec(), &path).expect("다시 세울 수 있어야 한다")
}

/// 저장한 뒤 파일을 손으로 고쳐 다시 읽는다 — **파일은 두 번째 통로다.**
fn tampered(label: &str, project: &Project, edit: impl FnOnce(&mut Value)) -> StoreError {
    let path = state_in(&scratch(label));
    save(project, &path).expect("눕힐 수 있어야 한다");

    let mut file: Value = serde_norway::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
    edit(&mut file);
    fs::write(&path, serde_norway::to_string(&file).unwrap()).unwrap();

    load(spec(), &path).expect_err("손으로 고친 파일이 그대로 읽혔다")
}

fn rules() -> RuleSet {
    spec()
}

/// 열린 Verify 를 세계와 함께 닫는다.
fn close_verify(project: &mut Project, world: ManifestAddress) {
    let cycle = project.cycles().current();
    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Verify);
    project
        .close_verify_step(report, world)
        .expect("Verify 를 닫는다");
}

/// Verify 뒤부터 판정까지 걷고 Cycle 을 닫는다.
fn finish_experiment(project: &mut Project, verdict: &str) {
    walked(project, NodeKind::Analysis);
    let outcome = opened(project, NodeKind::Outcome);
    let cycle = project.cycles().current();
    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", verdict)
        .with("lesson", "배운 것")
        .with(REASON, "판정한 까닭");
    close_here(project, report).expect("판정을 닫는다");

    let at = step_id(project, outcome);
    let mut report = cycle_report(project.cycles().current(), verdict, at);
    report.insert(ACTION, "open_child");
    project.close_cycle(report).expect("Cycle 을 닫는다");
}

// ── ① `gil start` 의 최초 Snapshot ─────────────────────────────────────────

#[test]
fn starting_where_files_already_live_names_those_files_a1() {
    // **빈 세계로 만들지 않는다.** 이미 있는 파일이 곧 A1 이다 — 그러지 않으면 첫 Verify 가
    // 「전부 새로 생겼다」로 보이고, 그것은 일어난 일이 아니다.
    let full = bare("start-with-files");
    write(&full, "readme.md", "이미 여기 있었다");
    write(&full, "src/main.rs", "fn main() {}");
    let with_files = sow_world(&full);

    let empty = bare("start-empty");
    let without = sow_world(&empty);

    assert_ne!(
        with_files.hex(),
        without.hex(),
        "파일이 있는 자리와 빈 자리가 같은 세계로 관측됐다"
    );

    // 내용이 주소이므로, 같은 파일을 놓은 다른 자리는 **같은 세계**다.
    let elsewhere = bare("start-with-files-elsewhere");
    write(&elsewhere, "readme.md", "이미 여기 있었다");
    write(&elsewhere, "src/main.rs", "fn main() {}");
    assert_eq!(
        sow_world(&elsewhere).hex(),
        with_files.hex(),
        "절대 위치가 세계에 섞였다"
    );
}

#[test]
fn the_root_cycle_departs_from_a1_and_has_arrived_nowhere() {
    let dir = bare("start-root-cycle");
    write(&dir, "a.txt", "가");
    let session = ProjectSession::start(rules(), state_in(&dir)).expect("시작한다");
    let project = session.project();

    let root = project.cycles().current();
    assert_eq!(root.kind(), CycleKind::Interview);
    assert_eq!(root.entry_snapshot(), snapshot(1));
    assert_eq!(root.exit_snapshot(), None, "열린 Cycle 이 도착해 있다");
    assert_eq!(project.next_snapshot_id(), 2);
    assert_eq!(project.world_snapshot(), snapshot(1));

    // 그 이름이 가리키는 것은 방금 관측한 세계다.
    let named: Vec<SnapshotRef> = project.snapshots().map(|(id, _)| id).collect();
    assert_eq!(named, vec![snapshot(1)]);
}

#[test]
fn an_empty_project_is_a_world_too() {
    // 「빈 세계」는 세계가 없다는 뜻이 아니다. 아무 파일도 없는 상태가 A1 이다.
    let dir = bare("start-empty-valid");
    let session = ProjectSession::start(rules(), state_in(&dir)).expect("빈 자리에서도 선다");
    session.commit().expect("눕힌다");

    let after = load(rules(), state_in(&dir)).expect("다시 세운다");
    assert_eq!(after.cycles().current().entry_snapshot(), snapshot(1));
    assert_eq!(after.next_snapshot_id(), 2);
}

#[test]
fn a_start_that_fails_leaves_no_state_at_all() {
    let dir = bare("start-refused");
    fs::create_dir_all(dir.join(".gil")).unwrap();
    write(&dir, ".gil/누군가의노트.md", "소중한 것");

    ProjectSession::start(rules(), state_in(&dir)).expect_err("모르는 것 위에 세웠다");
    assert!(!state_in(&dir).exists(), "거절하고도 상태를 남겼다");
}

#[test]
fn retrying_a_start_shares_the_objects_the_first_try_left() {
    // 미참조 객체는 손상이 아니다. 다시 시작하면 **같은 객체를 나눠 쓰고** 빈 registry 에서
    // 다시 A1 을 발급한다.
    let dir = bare("start-retry");
    write(&dir, "a.txt", "같은 바이트");

    let once = sow_world(&dir);
    let twice = sow_world(&dir);
    assert_eq!(once.hex(), twice.hex(), "같은 세계가 두 주소를 얻었다");

    // manifest 객체는 하나뿐이다.
    let shard = dir.join(".gil/artifacts/manifests/sha256");
    let files: usize = fs::read_dir(&shard)
        .unwrap()
        .map(|entry| fs::read_dir(entry.unwrap().path()).unwrap().count())
        .sum();
    assert_eq!(files, 1, "같은 세계가 두 객체로 눕었다");
}

// ── ② registry 가 그대로 건너간다 ──────────────────────────────────────────

#[test]
fn the_registry_survives_the_round_trip() {
    let before = bootstrap();
    let after = round_trip("registry-round-trip", &before);

    assert_eq!(after.next_snapshot_id(), before.next_snapshot_id());
    let names: Vec<SnapshotRef> = after.snapshots().map(|(id, _)| id).collect();
    assert_eq!(names, vec![snapshot(1)]);
    assert_eq!(
        after.world_manifest(snapshot(1)).unwrap().hex(),
        before.world_manifest(snapshot(1)).unwrap().hex(),
        "세계의 주소가 달라졌다"
    );
}

#[test]
fn the_same_world_keeps_its_name_and_a_new_one_gets_the_next() {
    let mut project = bootstrap();
    up_to_verify(&mut project);

    // 아무것도 바꾸지 않은 Verify — **기존 이름을 그대로 쓴다.**
    close_verify(&mut project, first_world());
    assert_eq!(project.next_snapshot_id(), 2, "같은 세계가 새 이름을 받았다");
    assert_eq!(project.world_snapshot(), snapshot(1));

    finish_experiment(&mut project, "success");
    project.open_child_cycle(CycleKind::Experiment).unwrap();
    up_to_verify(&mut project);

    // 처음 보는 세계 — 다음 이름이 난다.
    close_verify(&mut project, imagined_world(9));
    assert_eq!(project.next_snapshot_id(), 3);
    assert_eq!(project.world_snapshot(), snapshot(2));

    // 그리고 다시 첫 세계로 돌아오면 **A3 을 만들지 않는다.**
    finish_experiment(&mut project, "success");
    project.open_child_cycle(CycleKind::Experiment).unwrap();
    up_to_verify(&mut project);
    close_verify(&mut project, first_world());
    assert_eq!(project.next_snapshot_id(), 3, "되돌아온 세계가 이름을 늘렸다");
    assert_eq!(project.world_snapshot(), snapshot(1));
}

#[test]
fn a_registry_that_could_not_have_been_walked_is_refused() {
    let project = bootstrap();

    // next_snapshot_id 가 어긋나면 다음 발급이 이미 쓴 이름을 낸다.
    let err = tampered("registry-next-id", &project, |file| {
        file["artifacts"]["next_snapshot_id"] = Value::from(9);
    });
    assert!(matches!(err, StoreError::Registry(_)), "{err}");

    // 같은 이름이 두 번.
    let err = tampered("registry-dup-id", &project, |file| {
        let mut twin = file["artifacts"]["snapshots"][0].clone();
        twin["manifest"]["digest"] = Value::from("ab".repeat(32));
        file["artifacts"]["snapshots"]
            .as_sequence_mut()
            .unwrap()
            .push(twin);
        file["artifacts"]["next_snapshot_id"] = Value::from(3);
    });
    assert!(matches!(err, StoreError::Registry(_)), "{err}");

    // 서로 다른 이름이 같은 세계를 가리킨다.
    let err = tampered("registry-dup-manifest", &project, |file| {
        let mut twin = file["artifacts"]["snapshots"][0].clone();
        twin["id"] = Value::from("A2");
        file["artifacts"]["snapshots"]
            .as_sequence_mut()
            .unwrap()
            .push(twin);
        file["artifacts"]["next_snapshot_id"] = Value::from(3);
    });
    assert!(matches!(err, StoreError::Registry(_)), "{err}");

    // `A0` 은 이름이 아니다.
    let err = tampered("registry-a0", &project, |file| {
        file["artifacts"]["snapshots"][0]["id"] = Value::from("A0");
    });
    assert!(
        matches!(err, StoreError::Registry(_) | StoreError::BadRef { .. }),
        "{err}"
    );
}

#[test]
fn a_manifest_that_is_missing_or_corrupt_is_refused() {
    let dir = scratch("manifest-missing");
    let path = state_in(&dir);
    let project = bootstrap();
    save(&project, &path).unwrap();

    let address = project.world_manifest(snapshot(1)).unwrap().hex();
    let (shard, rest) = address.split_at(2);
    let at = dir
        .join(".gil/artifacts/manifests/sha256")
        .join(shard)
        .join(rest);

    // 내용이 주소와 갈리면 — 손상이다.
    let real = fs::read(&at).unwrap();
    fs::write(&at, "이건 manifest 가 아니다".as_bytes()).unwrap();
    let err = load(spec(), &path).expect_err("손상된 manifest 가 읽혔다");
    assert!(matches!(err, StoreError::Manifest { .. }), "{err}");
    assert!(err.to_string().contains("snapshot:A1"), "{err}");
    assert!(err.to_string().contains("닫히지도 움직이지도 않았다"), "{err}");

    // 아예 없으면 — 없다고 말한다.
    fs::remove_file(&at).unwrap();
    let err = load(spec(), &path).expect_err("없는 manifest 가 읽혔다");
    assert!(matches!(err, StoreError::Manifest { .. }), "{err}");

    // 되돌려 놓으면 다시 읽힌다 — 도구가 고치지 않았다는 뜻이다.
    fs::write(&at, real).unwrap();
    load(spec(), &path).expect("되돌려 놓은 창고는 읽힌다");
}

#[test]
fn a_manifest_digest_is_not_a_graph_reference() {
    // 내부 주소와 공개 이름은 다른 계층이다. 주소를 Graph 자리에 적은 파일은 거절된다.
    let project = bootstrap();
    let digest = project.world_manifest(snapshot(1)).unwrap().hex();

    let err = tampered("digest-as-ref", &project, |file| {
        file["cycles"]["nodes"][0]["entry_snapshot_ref"] = Value::from(digest.clone());
    });
    assert!(matches!(err, StoreError::BadRef { .. }), "{err}");
}

#[test]
fn a_digest_that_is_not_lowercase_canonical_hex_is_refused() {
    let project = bootstrap();
    let digest = project.world_manifest(snapshot(1)).unwrap().hex();

    for spoiled in [digest.to_uppercase(), digest[..63].to_string(), format!("{digest}zz")] {
        let err = tampered("digest-shape", &project, |file| {
            file["artifacts"]["snapshots"][0]["manifest"]["digest"] = Value::from(spoiled);
        });
        assert!(
            matches!(
                err,
                StoreError::DigestNotCanonical { .. } | StoreError::Registry(_)
            ),
            "{err}"
        );
    }

    let err = tampered("digest-algorithm", &project, |file| {
        file["artifacts"]["snapshots"][0]["manifest"]["algorithm"] = Value::from("blake3");
    });
    assert!(matches!(err, StoreError::Registry(_)), "{err}");
}

// ── ③ Cycle 의 Entry/Exit 과 Verify 의 세계 ────────────────────────────────

#[test]
fn every_cycle_carries_an_entry_and_only_closed_ones_carry_an_exit() {
    let mut project = bootstrap();
    for cycle in project.cycles().nodes() {
        assert_eq!(
            cycle.exit_snapshot().is_some(),
            cycle.is_closed(),
            "{:?} 의 Exit 이 상태와 어긋난다",
            cycle.id()
        );
    }
    // 지금 열려 있는 Experiment.
    assert_eq!(project.cycles().current().exit_snapshot(), None);

    up_to_verify(&mut project);
    close_verify(&mut project, imagined_world(7));
    finish_experiment(&mut project, "success");
    assert!(project.cycles().current().exit_snapshot().is_some());
}

#[test]
fn a_child_departs_from_exactly_where_its_parent_arrived() {
    let mut project = bootstrap();
    up_to_verify(&mut project);
    close_verify(&mut project, imagined_world(7));
    finish_experiment(&mut project, "success");

    let parent = project.cycles().current().id();
    let exit = project.cycles().current().exit_snapshot().expect("도착했다");
    assert_eq!(exit, snapshot(2), "Verify 가 확정한 세계가 Exit 이어야 한다");

    project.open_child_cycle(CycleKind::Experiment).unwrap();
    let child = project.cycles().current();
    assert_eq!(child.entry_snapshot(), exit);
    assert_ne!(child.id(), parent);
    assert_eq!(child.exit_snapshot(), None);
}

#[test]
fn a_cycle_with_no_verify_hands_its_entry_on_as_its_exit() {
    // Interview 는 Artifact 를 바꿀 수 없다. 그래서 Entry 와 Exit 이 같다.
    let project = bootstrap();
    let interview = project.cycles().nodes()[0].clone();
    assert_eq!(interview.entry_snapshot(), snapshot(1));
    assert_eq!(interview.exit_snapshot(), Some(snapshot(1)));
    // 그리고 그 Exit 이 Experiment 의 Entry 다.
    assert_eq!(project.cycles().current().entry_snapshot(), snapshot(1));
}

#[test]
fn the_exit_is_the_nearest_verify_in_the_lineage_not_the_largest_name() {
    // 되돌아가 버린 가지에도 **더 큰 이름**이 있다. 그것을 고르면 Cycle 이 실제로 도착한
    // 세계가 아닌 곳을 가리킨다.
    let mut project = bootstrap();
    up_to_verify(&mut project);
    close_verify(&mut project, imagined_world(7)); // A2 — 버려질 가지
    walked(&mut project, NodeKind::Analysis);

    // 실패로 판정하고 가설로 되돌아간다.
    let outcome = opened(&mut project, NodeKind::Outcome);
    let cycle = project.cycles().current();
    // 되돌아갈 자리는 **새 가설이 갈라져 나올 수 있는 곳**이다.
    let define = cycle
        .steps()
        .nodes()
        .iter()
        .find(|node| node.kind == NodeKind::Define)
        .expect("정의가 있다");
    let target = cycle.step_ref(define.id);
    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", "failure")
        .with("lesson", "다시 세운다")
        .with(ACTION, "revisit")
        .with("next_direction.target_node_ref", target.to_string())
        .with(REASON, "가설이 틀렸다");
    close_here(&mut project, report).expect("판정을 닫는다");
    let _ = outcome;

    project
        .cycles_mut()
        .current_mut()
        .revisit_step()
        .expect("되돌아간다");

    // 새 가지 — 여기서는 **처음 세계로 돌아왔다.** 그래서 기존 `A1` 을 그대로 쓴다.
    //
    // 이 배치가 핵심이다. 살아남은 가지의 세계(`A1`)가 버려진 가지의 세계(`A2`)보다
    // **이름이 작다** — 「가장 큰 이름」을 고르는 구현은 여기서 A2 를 집는다.
    walked(&mut project, NodeKind::Hypothesis);
    opened(&mut project, NodeKind::Verify);
    close_verify(&mut project, first_world());
    assert_eq!(project.next_snapshot_id(), 3, "되돌아온 세계가 이름을 늘렸다");

    finish_experiment(&mut project, "success");
    assert_eq!(
        project.cycles().current().exit_snapshot(),
        Some(snapshot(1)),
        "버려진 가지의 세계나 가장 큰 이름을 Exit 으로 골랐다"
    );
}

#[test]
fn a_state_that_puts_a_world_where_it_cannot_belong_is_refused() {
    let mut project = bootstrap();
    up_to_verify(&mut project);
    close_verify(&mut project, imagined_world(7));

    // 닫힌 Verify 의 세계를 지운다.
    let err = tampered("verify-no-world", &project, |file| {
        let steps = file["cycles"]["nodes"][1]["steps"]["nodes"]
            .as_sequence_mut()
            .unwrap();
        for step in steps {
            if step["kind"] == Value::from("verify") {
                step["snapshot_ref"] = Value::Null;
            }
        }
    });
    assert!(err.to_string().contains("확정한 세계가 없다"), "{err}");

    // Verify 가 아닌 자리에 세계를 적는다.
    let err = tampered("non-verify-world", &project, |file| {
        let steps = file["cycles"]["nodes"][1]["steps"]["nodes"]
            .as_sequence_mut()
            .unwrap();
        for step in steps {
            if step["kind"] == Value::from("define") {
                step["snapshot_ref"] = Value::from("snapshot:A1");
            }
        }
    });
    assert!(err.to_string().contains("확정하는 것은 verify 뿐"), "{err}");

    // 열린 Cycle 에 Exit 을 적는다.
    let err = tampered("open-cycle-exit", &project, |file| {
        file["cycles"]["nodes"][1]["exit_snapshot_ref"] = Value::from("snapshot:A1");
    });
    assert!(err.to_string().contains("아직 열려 있는데"), "{err}");

    // 아무도 발급하지 않은 이름을 가리킨다.
    let err = tampered("unknown-world", &project, |file| {
        file["cycles"]["nodes"][0]["entry_snapshot_ref"] = Value::from("snapshot:A99");
    });
    assert!(err.to_string().contains("registry 에 없다"), "{err}");

    // 자식의 Entry 를 부모의 Exit 이 아닌 값으로 바꾼다.
    let err = tampered("entry-not-parent-exit", &project, |file| {
        file["artifacts"]["snapshots"]
            .as_sequence_mut()
            .unwrap()
            .push(
                serde_norway::from_str(&format!(
                    "id: A3\nmanifest:\n  algorithm: sha256\n  digest: {}\n",
                    "cd".repeat(32)
                ))
                .unwrap(),
            );
        file["artifacts"]["next_snapshot_id"] = Value::from(4);
        file["cycles"]["nodes"][1]["entry_snapshot_ref"] = Value::from("snapshot:A3");
    });
    assert!(err.to_string().contains("부모"), "{err}");
}

#[test]
fn a_closed_cycle_without_an_exit_is_refused() {
    let project = bootstrap();
    let err = tampered("closed-cycle-no-exit", &project, |file| {
        file["cycles"]["nodes"][0]["exit_snapshot_ref"] = Value::Null;
    });
    assert!(err.to_string().contains("확정한 Artifact 세계가 없다"), "{err}");
}

// ── ④ Verify 만이 세계를 확정한다 ──────────────────────────────────────────

#[test]
fn a_non_verify_step_cannot_confirm_a_world_and_a_verify_must() {
    let mut project = bootstrap();

    // Interview 를 지나 온 자리들은 전부 세계 없이 닫혔다.
    for cycle in project.cycles().nodes() {
        for node in cycle.steps().nodes() {
            if node.kind != NodeKind::Verify {
                assert!(node.snapshot.is_none(), "{:?} 가 세계를 지녔다", node.kind);
            }
        }
    }

    up_to_verify(&mut project);
    // Verify 를 보통 문으로 닫으려 하면 거절된다.
    let cycle = project.cycles().current();
    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Verify);
    let err = project
        .clone()
        .close_action_step(report.clone())
        .expect_err("세계 없이 Verify 가 닫혔다");
    assert!(err.to_string().contains("관측한 세계 없이"), "{err}");

    // 세계와 함께면 닫힌다.
    project.close_verify_step(report, first_world()).expect("닫는다");
    let closed = project
        .cycles()
        .current()
        .steps()
        .nodes()
        .iter()
        .find(|node| node.kind == NodeKind::Verify)
        .expect("Verify 가 있다");
    assert_eq!(closed.snapshot, Some(snapshot(1)));
}

#[test]
fn a_verify_that_changed_nothing_still_closes() {
    // Verify 에는 verdict 가 없다. 파일이 바뀌었는지와 가설이 맞았는지는 다른 물음이다.
    let mut project = bootstrap();
    up_to_verify(&mut project);
    close_verify(&mut project, first_world());

    assert_eq!(project.next_snapshot_id(), 2, "새 이름이 났다");
    assert_eq!(project.world_snapshot(), snapshot(1));

    // 그리고 그 Cycle 은 Entry 와 같은 세계로 도착한다 — 아무것도 바꾸지 않았으므로.
    finish_experiment(&mut project, "success");
    let done = project.cycles().current();
    assert_eq!(done.exit_snapshot(), Some(snapshot(1)));
    assert_eq!(done.exit_snapshot(), Some(done.entry_snapshot()));
}

// ── ⑤ format 3 은 변환하지 않고 거절한다 ──────────────────────────────────

#[test]
fn a_format_three_file_is_kept_and_refused() {
    let dir = scratch("format-three");
    let path = state_in(&dir);
    let before = "format: 3\nnext_will_id: 1\ncurrent_existence_ref: existence:X1\n";
    fs::write(&path, before).unwrap();

    let err = load(spec(), &path).expect_err("앞 형식이 읽혔다");
    match err {
        StoreError::PreviousFormat { found, current, .. } => {
            assert_eq!(found, 3);
            assert_eq!(current, 4);
        }
        other => panic!("앞 형식을 앞 형식이라 말하지 않았다: {other:?}"),
    }
    // **건드리지 않는다.** 조용히 변환하지도, 치우지도 않는다.
    assert_eq!(fs::read_to_string(&path).unwrap(), before);
}

#[test]
fn format_four_is_what_this_gil_writes() {
    let project = bootstrap();
    let path = state_in(&scratch("format-four-line"));
    save(&project, &path).unwrap();

    let text = fs::read_to_string(&path).unwrap();
    assert!(
        text.starts_with("format: 4\n"),
        "형식은 첫 줄에서 제 이름을 말해야 한다:\n{text}"
    );
    assert_eq!(gil::FORMAT, 4);
}

// ── ⑥ tmp 회수와 창고 구조 ────────────────────────────────────────────────

#[test]
fn a_canonical_leftover_in_tmp_is_reaped() {
    let dir = bare("tmp-reap");
    let session = ProjectSession::start(rules(), state_in(&dir)).expect("시작한다");
    session.commit().unwrap();
    drop(session);

    let tmp = dir.join(".gil/artifacts/tmp");
    fs::create_dir_all(&tmp).unwrap();
    fs::write(tmp.join("1234-7"), "미완의 객체".as_bytes()).unwrap();
    fs::write(tmp.join("99999-0"), "또 하나".as_bytes()).unwrap();

    ProjectSession::open(rules(), state_in(&dir)).expect("잔해를 거두고 연다");
    assert_eq!(fs::read_dir(&tmp).unwrap().count(), 0, "잔해가 남았다");
}

#[test]
fn something_gil_did_not_make_in_tmp_stops_the_command() {
    let dir = bare("tmp-stranger");
    let session = ProjectSession::start(rules(), state_in(&dir)).expect("시작한다");
    session.commit().unwrap();
    drop(session);

    let tmp = dir.join(".gil/artifacts/tmp");
    fs::create_dir_all(&tmp).unwrap();

    // 이름이 GIL 의 것이 아니다.
    fs::write(tmp.join("누군가의파일"), b"x").unwrap();
    let err = ProjectSession::open(rules(), state_in(&dir)).expect_err("모르는 것을 지나쳤다");
    assert!(err.to_string().contains("GIL 이 만든 임시 파일이 아니다"), "{err}");
    assert!(tmp.join("누군가의파일").exists(), "모르는 것을 지웠다");
    fs::remove_file(tmp.join("누군가의파일")).unwrap();

    // 디렉터리도 거절한다.
    fs::create_dir(tmp.join("1-1")).unwrap();
    let err = ProjectSession::open(rules(), state_in(&dir)).expect_err("디렉터리를 지나쳤다");
    assert!(err.to_string().contains("임시 파일이 아니다"), "{err}");
    fs::remove_dir(tmp.join("1-1")).unwrap();

    // 심볼릭 링크는 **따라가지 않고** 거절한다 — 따라가면 남의 파일을 지운다.
    #[cfg(unix)]
    {
        let bait = dir.join("소중한파일.txt");
        fs::write(&bait, "지워지면 안 된다".as_bytes()).unwrap();
        std::os::unix::fs::symlink(&bait, tmp.join("7-7")).unwrap();

        let err = ProjectSession::open(rules(), state_in(&dir)).expect_err("링크를 지나쳤다");
        assert!(err.to_string().contains("임시 파일이 아니다"), "{err}");
        assert!(bait.exists(), "링크를 따라가 남의 파일을 지웠다");
    }
}

#[test]
fn a_missing_tmp_directory_is_normal() {
    let dir = bare("tmp-absent");
    let session = ProjectSession::start(rules(), state_in(&dir)).expect("시작한다");
    session.commit().unwrap();
    drop(session);

    let tmp = dir.join(".gil/artifacts/tmp");
    let _ = fs::remove_dir_all(&tmp);
    ProjectSession::open(rules(), state_in(&dir)).expect("tmp 가 없다고 멈췄다");
}

#[test]
fn something_gil_does_not_know_in_the_object_store_stops_a_start() {
    let dir = bare("store-stranger");
    fs::create_dir_all(dir.join(".gil/artifacts/누군가의폴더")).unwrap();

    let err = ProjectSession::start(rules(), state_in(&dir)).expect_err("모르는 것 위에 세웠다");
    assert!(err.to_string().contains("blobs·manifests·tmp"), "{err}");
    assert!(
        dir.join(".gil/artifacts/누군가의폴더").exists(),
        "모르는 것을 지웠다"
    );
    assert!(!state_in(&dir).exists());
}

#[test]
fn unreferenced_objects_do_not_stop_a_start() {
    // 미참조 blob·manifest 는 손상이 아니다 — 중단된 확정의 흔적일 뿐이다.
    let dir = bare("store-orphans");
    write(&dir, "a.txt", "가");
    sow_world(&dir); // state 를 쓰지 않고 객체만 남긴다

    let session = ProjectSession::start(rules(), state_in(&dir)).expect("미참조 객체가 막았다");
    session.commit().expect("눕힌다");
    load(rules(), state_in(&dir)).expect("다시 세운다");
}

// ── ⑦ 읽기 명령은 창고를 전수 해시하지 않는다 ────────────────────────────

#[test]
fn reading_the_state_does_not_rehash_every_blob() {
    // blob 하나를 손상시켜 둔다. load 가 **모든 바이트**를 다시 읽는다면 여기서 걸릴 것이고,
    // 그것은 `gil status` 한 번이 프로젝트 전체를 다시 읽는다는 뜻이다.
    let dir = bare("no-full-rehash");
    write(&dir, "big.txt", "아주 긴 내용이라 치자");
    let session = ProjectSession::start(rules(), state_in(&dir)).expect("시작한다");
    session.commit().unwrap();
    drop(session);

    let blobs = dir.join(".gil/artifacts/blobs/sha256");
    let victim = fs::read_dir(&blobs)
        .unwrap()
        .flat_map(|shard| fs::read_dir(shard.unwrap().path()).unwrap())
        .map(|entry| entry.unwrap().path())
        .next()
        .expect("blob 이 하나는 있다");
    fs::write(&victim, "손상".as_bytes()).unwrap();

    // manifest 는 온전하므로 상태는 읽힌다 — 이 보장의 경계를 여기 못 박는다.
    load(rules(), state_in(&dir)).expect("blob 손상이 상태 읽기를 막았다");
}

// ── ⑧ 새로 난 세계는 실제로 되읽힌다 ──────────────────────────────────────

#[test]
fn a_world_confirmed_by_a_verify_reads_back_from_disk() {
    let dir = bare("verify-roundtrip");
    write(&dir, "before.txt", "처음");

    let mut session = ProjectSession::start(rules(), state_in(&dir)).expect("시작한다");
    let first = session
        .project()
        .world_manifest(snapshot(1))
        .unwrap()
        .clone();

    // Interview 를 지나 Experiment 의 Verify 앞까지 — 세계를 바꾸지 않고.
    *session.project_mut() = bootstrap_from(session.project().clone());
    up_to_verify(session.project_mut());
    session.commit().expect("눕힌다");

    // 이제 파일을 바꾸고 Verify 를 닫는다 — **CLI 와 같은 문으로.**
    write(&dir, "after.txt", "새로 생김");
    fs::remove_file(dir.join("before.txt")).unwrap();

    let report = full_report(&rules(), CycleKind::Experiment, NodeKind::Verify);
    session.close_step(report).expect("Verify 를 닫는다");
    session.commit().expect("눕힌다");

    let project = session.project();
    assert_eq!(project.next_snapshot_id(), 3, "새 세계에 이름이 나지 않았다");
    assert_eq!(project.world_snapshot(), snapshot(2));
    assert_ne!(
        project.world_manifest(snapshot(2)).unwrap().hex(),
        first.hex(),
        "생성과 삭제가 세계에 반영되지 않았다"
    );

    drop(session);
    let after = load(rules(), state_in(&dir)).expect("객체까지 실재하는 상태가 읽힌다");
    assert_eq!(after.world_snapshot(), snapshot(2));
}

// ── ⑨ dirty gate ──────────────────────────────────────────────────────────

/// Interview 의 첫 자리를 연 채로, 파일 하나를 바꾼 세션.
fn dirty_session(label: &str) -> ProjectSession {
    let dir = bare(label);
    write(&dir, "work.txt", "처음");
    let mut session = ProjectSession::start(rules(), state_in(&dir)).expect("시작한다");
    session
        .open_action_step(NodeKind::Question, plan(NodeKind::Question))
        .expect("첫 자리를 연다");
    session.commit().expect("눕힌다");

    write(&dir, "work.txt", "바꿨다");
    session
}

#[test]
fn a_non_verify_step_will_not_close_over_a_changed_world() {
    let mut session = dirty_session("dirty-step");
    let before = fs::read_to_string(session.state_path()).unwrap();
    let project_before = session.project().clone();

    let report = full_report(&rules(), CycleKind::Interview, NodeKind::Question);
    let err = session.close_step(report).expect_err("바뀐 세계 위에서 닫혔다");

    assert!(err.is_receipt(), "이 거절은 그 자체로 완결된 receipt 다");
    let said = err.to_string();
    assert!(said.contains("snapshot:A1"), "{said}");
    assert!(said.contains("바뀜      work.txt"), "{said}");
    // **밟을 수 있는 길을 말한다.** M3-E 전에는 「Experiment 로 가라」고 했는데,
    // Interview 안에서는 그 길이 없다 — 이 Cycle 을 닫는 것도 같은 gate 에 막힌다.
    assert!(
        said.contains("`gil restore` 로 현재 변경을 되돌린 뒤"),
        "무엇을 해야 하는지 말하지 않았다: {said}"
    );
    assert!(said.contains("그대로 열려 있다"), "{said}");

    // **아무것도 움직이지 않았다.**
    let after = session.project();
    assert_eq!(after.next_snapshot_id(), project_before.next_snapshot_id());
    assert_eq!(
        after.active_will().map(|will| will.id()),
        project_before.active_will().map(|will| will.id()),
        "걸린 행동이 움직였다"
    );
    assert_eq!(
        after.current_existence().current_journey(),
        project_before.current_existence().current_journey(),
        "판이 늘었다"
    );
    assert!(
        after.cycles().current().step_now_open().is_some(),
        "열린 자리가 닫혔다"
    );
    assert_eq!(
        fs::read_to_string(session.state_path()).unwrap(),
        before,
        "거절하고도 state.yaml 이 바뀌었다"
    );
}

#[test]
fn a_dirty_refusal_mints_no_object_and_no_name() {
    let mut session = dirty_session("dirty-no-objects");
    let root = session.root().unwrap();
    let count = |dir: &str| -> usize {
        let at = root.join(".gil/artifacts").join(dir).join("sha256");
        fs::read_dir(&at)
            .map(|shards| {
                shards
                    .map(|shard| fs::read_dir(shard.unwrap().path()).unwrap().count())
                    .sum()
            })
            .unwrap_or(0)
    };
    let (blobs, manifests) = (count("blobs"), count("manifests"));

    let report = full_report(&rules(), CycleKind::Interview, NodeKind::Question);
    session.close_step(report).expect_err("바뀐 세계 위에서 닫혔다");

    assert_eq!(count("blobs"), blobs, "거절이 blob 을 만들었다");
    assert_eq!(count("manifests"), manifests, "거절이 manifest 를 만들었다");
    assert_eq!(session.project().next_snapshot_id(), 2, "이름이 났다");
}

#[test]
fn every_non_verify_kind_is_gated_the_same_way() {
    // Interview 의 셋과 Experiment 의 define·hypothesis·outcome — 어느 하나만 새면
    // 그 길로 확정되지 않은 변경이 지나간다.
    for (label, kind) in [
        ("gate-question", NodeKind::Question),
        ("gate-interpretation", NodeKind::Interpretation),
        ("gate-define", NodeKind::Define),
        ("gate-hypothesis", NodeKind::Hypothesis),
        ("gate-outcome", NodeKind::Outcome),
    ] {
        let dir = bare(label);
        write(&dir, "work.txt", "처음");
        let mut session = ProjectSession::start(rules(), state_in(&dir)).expect("시작한다");

        // 그 Kind 가 열리는 자리까지 걷는다 — **세계를 바꾸지 않고.**
        let cycle_kind = match kind {
            NodeKind::Question | NodeKind::Interpretation => CycleKind::Interview,
            _ => CycleKind::Experiment,
        };
        if cycle_kind == CycleKind::Experiment {
            *session.project_mut() = bootstrap_from(session.project().clone());
            if kind != NodeKind::Define {
                walked(session.project_mut(), NodeKind::Define);
            }
            if kind == NodeKind::Outcome {
                walked(session.project_mut(), NodeKind::Hypothesis);
                opened(session.project_mut(), NodeKind::Verify);
                // **세션의 문으로 닫는다** — 지어낸 주소가 아니라 실제 세계를 관측해야
                // 그 manifest 가 이 프로젝트의 창고에 눕는다.
                let verify = full_report(&rules(), CycleKind::Experiment, NodeKind::Verify);
                session.close_step(verify).expect("Verify 를 닫는다");
                walked(session.project_mut(), NodeKind::Analysis);
            }
        } else if kind == NodeKind::Interpretation {
            walked(session.project_mut(), NodeKind::Question);
        }
        session
            .open_action_step(kind, plan(kind))
            .unwrap_or_else(|err| panic!("{kind} 를 열지 못했다: {err}"));
        session.commit().expect("눕힌다");

        write(&dir, "work.txt", "바꿨다");
        let report = full_report(&rules(), cycle_kind, kind);
        let err = match session.close_step(report) {
            Ok(_) => panic!("{kind} 가 바뀐 세계 위에서 닫혔다"),
            Err(err) => err,
        };
        assert!(err.is_receipt(), "{kind}: {err}");
        assert!(
            err.to_string().contains("바뀜      work.txt"),
            "{kind} 의 거절이 무엇이 바뀌었는지 말하지 않았다:\n{err}"
        );
        assert!(
            session.project().cycles().current().step_now_open().is_some(),
            "{kind} 가 거절되고도 자리가 닫혔다"
        );
    }
}

#[test]
fn a_cycle_will_not_close_over_a_changed_world_either() {
    let dir = bare("dirty-cycle");
    write(&dir, "work.txt", "처음");
    let mut session = ProjectSession::start(rules(), state_in(&dir)).expect("시작한다");

    // Experiment 를 판정까지 걸어 Cycle 경계에 세운다 — **세계를 바꾸지 않고.**
    let mut project = bootstrap_from(session.project().clone());
    up_to_verify(&mut project);
    *session.project_mut() = project;

    // Verify 는 세션의 문으로 닫는다 — 실제 세계를 관측해 이 창고에 눕히기 위해.
    let verify = full_report(&rules(), CycleKind::Experiment, NodeKind::Verify);
    session.close_step(verify).expect("Verify 를 닫는다");

    let mut project = session.project().clone();
    walked(&mut project, NodeKind::Analysis);
    let outcome = opened(&mut project, NodeKind::Outcome);
    let cycle = project.cycles().current();
    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", "success")
        .with("lesson", "배운 것")
        .with(REASON, "판정한 까닭");
    close_here(&mut project, report).expect("판정을 닫는다");
    let at = step_id(&project, outcome);
    let cycle_close = cycle_report(project.cycles().current(), "success", at);

    *session.project_mut() = project;
    session.commit().expect("눕힌다");
    let before = fs::read_to_string(session.state_path()).unwrap();

    write(&dir, "work.txt", "바꿨다");
    let err = session
        .close_cycle(cycle_close)
        .expect_err("바뀐 세계 위에서 Cycle 이 닫혔다");

    let said = err.to_string();
    assert!(
        said.contains("Cycle 을 닫는 것은 새 세계를 만들지 않는다"),
        "{said}"
    );
    assert!(said.contains("바뀜      work.txt"), "{said}");
    assert!(!session.project().cycles().current().is_closed(), "닫혔다");
    assert_eq!(fs::read_to_string(session.state_path()).unwrap(), before);
}

#[test]
fn a_clean_world_lets_a_non_verify_step_close() {
    // gate 가 **막기만 하는 것이 아니라 지나가게도 하는가.**
    let dir = bare("clean-close");
    write(&dir, "work.txt", "그대로 둔다");
    let mut session = ProjectSession::start(rules(), state_in(&dir)).expect("시작한다");
    session
        .open_action_step(NodeKind::Question, plan(NodeKind::Question))
        .expect("연다");

    let report = full_report(&rules(), CycleKind::Interview, NodeKind::Question);
    session.close_step(report).expect("바뀌지 않은 세계에서 닫힌다");
    session.commit().expect("눕힌다");

    assert_eq!(session.project().next_snapshot_id(), 2, "이름이 났다");
    assert!(session.project().cycles().current().step_now_open().is_none());
}
