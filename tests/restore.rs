//! `gil restore` — **성공하거나, 실행 전 세계로 돌아가거나.**
//!
//! 중간에 멈춘 세계는 결과가 아니다. 그래서 이 파일의 절반은 「죽었을 때 무엇이 남는가」를
//! 잰다 — 그것만이 transaction 인지 아닌지를 가른다.
//!
//! # 죽음을 어떻게 만드는가
//!
//! `sleep` 과 운에 기대지 않는다. `gil` 을 **진짜 자식 프로세스로** 띄우고, 정해진 지점에서
//! `abort` 하도록 환경변수로 무장한다.
//!
//! ```text
//! prepared-not-armed   active 가 생기기 직전 — rollback 이 아직 안 걸렸다
//! after-prepare        active 가 생긴 직후 — 아직 아무 파일도 안 건드렸다
//! after-first-apply    한 자리만 바꾼 뒤
//! before-commit        전부 바꾸고 확인까지 끝난 뒤, 표식을 쓰기 직전
//! after-commit         표식이 durable 해진 직후
//! before-cleanup       잔해 자리로 옮긴 뒤, 지우기 직전
//! ```
//!
//! 이 지점들은 `debug_assertions` 빌드에만 있다. 배포 빌드에는 그 코드가 없다.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};

use gil::{CycleKind, NodeKind, ProjectSession, RuleSet};

mod common;
use common::{
    REASON, bootstrap_from, close_here, full_report, opened, spec, up_to_verify, walked,
};

const GIL: &str = env!("CARGO_BIN_EXE_gil");
const CRASH: &str = "GIL_RESTORE_CRASH";
const MEDDLE: &str = "GIL_RESTORE_MEDDLE";

// ── 연장 ───────────────────────────────────────────────────────────────────

fn rules() -> RuleSet {
    spec()
}

fn state_in(dir: &Path) -> PathBuf {
    dir.join(gil::STATE_PATH)
}

fn bare(label: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("gil-restore-{label}"));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).expect("시험이 쓸 자리를 만든다");
    dir
}

fn write(root: &Path, path: &str, bytes: &str) {
    let at = root.join(path);
    if let Some(parent) = at.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(&at, bytes).unwrap();
}

fn read(root: &Path, path: &str) -> String {
    fs::read_to_string(root.join(path)).unwrap_or_else(|err| panic!("{path} 를 읽는다: {err}"))
}

/// 프로젝트 폴더의 **세계** — `.gil` 은 세계가 아니므로 뺀다.
fn world_of(root: &Path) -> BTreeMap<String, Vec<u8>> {
    let mut out = BTreeMap::new();
    walk(root, root, &mut out);
    out
}

fn walk(root: &Path, at: &Path, out: &mut BTreeMap<String, Vec<u8>>) {
    for entry in fs::read_dir(at).expect("들여다본다") {
        let entry = entry.expect("한 자리");
        let path = entry.path();
        if path.file_name().is_some_and(|name| name == ".gil") {
            continue;
        }
        match entry.file_type().expect("종류").is_dir() {
            true => walk(root, &path, out),
            false => {
                let key = path
                    .strip_prefix(root)
                    .expect("루트 안이다")
                    .to_string_lossy()
                    .into_owned();
                out.insert(key, fs::read(&path).expect("읽는다"));
            }
        }
    }
}

/// `state.yaml` 의 바이트 — restore 는 이것을 **한 글자도** 건드리지 않는다.
fn state_bytes(root: &Path) -> Vec<u8> {
    fs::read(state_in(root)).expect("상태를 읽는다")
}

fn run(dir: &Path, args: &[&str], env: &[(&str, &str)]) -> Output {
    let mut command = Command::new(GIL);
    command
        .args(args)
        .current_dir(dir)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    for (key, value) in env {
        command.env(key, value);
    }
    command.output().expect("gil 을 부를 수 있어야 한다")
}

fn ok(dir: &Path, args: &[&str]) -> String {
    let out = run(dir, args, &[]);
    assert!(
        out.status.success(),
        "gil {args:?} 가 실패했다:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    String::from_utf8_lossy(&out.stdout).into_owned()
}

fn refused(dir: &Path, args: &[&str]) -> String {
    let out = run(dir, args, &[]);
    assert!(
        !out.status.success(),
        "거절돼야 하는데 통과했다: gil {args:?}\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
    String::from_utf8_lossy(&out.stderr).into_owned()
}

/// 정해진 지점에서 **죽는** `gil restore` 를 돌린다.
fn crash_at(dir: &Path, point: &str) {
    let out = run(dir, &["restore"], &[(CRASH, point)]);
    assert!(
        !out.status.success(),
        "{point} 에서 죽어야 하는데 곱게 끝났다:\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
}

/// 이 자리에 restore transaction 이 남아 있는가.
fn leftovers(root: &Path) -> Vec<String> {
    match fs::read_dir(root.join(".gil/restore")) {
        Ok(entries) => entries
            .map(|entry| entry.unwrap().file_name().to_string_lossy().into_owned())
            .collect(),
        Err(_) => Vec::new(),
    }
}

/// 열린 question 자리 하나를 둔 프로젝트 — **세계는 이 파일들이다.**
fn started(label: &str, files: &[(&str, &str)]) -> PathBuf {
    let dir = bare(label);
    for (path, text) in files {
        write(&dir, path, text);
    }
    ok(&dir, &["start"]);
    let out = Command::new(GIL)
        .args(["open", "question"])
        .current_dir(&dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .and_then(|mut child| {
            use std::io::Write as _;
            child
                .stdin
                .as_mut()
                .expect("stdin")
                .write_all(b"objective: a\nnext_action: b\ndone_when: c\n")?;
            child.wait_with_output()
        })
        .expect("자리를 연다");
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    dir
}

// ── ① 목표는 고르는 것이 아니다 ───────────────────────────────────────────

#[test]
fn restore_takes_no_target_and_no_path() {
    let dir = started("no-arguments", &[("a.txt", "가")]);
    for extra in ["snapshot:A1", "a.txt", "--force", "--yes", "-f"] {
        let said = refused(&dir, &["restore", extra]);
        assert!(said.contains("받지 않는다"), "{extra}: {said}");
        assert!(said.contains("지금 위치가 이미 정한다"), "{extra}: {said}");
    }
}

#[test]
fn the_target_is_the_nearest_verify_not_the_largest_name() {
    // 버려진 가지의 세계가 **더 큰 이름**을 갖도록 배치한다. 「가장 큰 ID」를 고르는
    // 구현은 여기서 다른 세계로 복원한다.
    let dir = bare("target-lineage");
    write(&dir, "work.txt", "처음");
    let mut session = ProjectSession::start(rules(), state_in(&dir)).expect("시작한다");

    *session.project_mut() = bootstrap_from(session.project().clone());
    up_to_verify(session.project_mut());

    // 첫 가지: 파일을 바꾸고 Verify 로 확정한다 → A2
    write(&dir, "work.txt", "버려질 가지");
    let verify = full_report(&rules(), CycleKind::Experiment, NodeKind::Verify);
    session.close_step(verify).expect("Verify 를 닫는다");
    assert_eq!(session.project().world_snapshot().to_string(), "snapshot:A2");

    // 실패로 판정하고 define 으로 되돌아간다.
    walked(session.project_mut(), NodeKind::Analysis);
    let outcome = opened(session.project_mut(), NodeKind::Outcome);
    let _ = outcome;
    let cycle = session.project().cycles().current();
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
        .with("next_direction.action", "revisit")
        .with("next_direction.target_node_ref", target.to_string())
        .with(REASON, "가설이 틀렸다");
    close_here(session.project_mut(), report).expect("판정을 닫는다");
    session.revisit_step().expect("되돌아간다");

    // 새 가지: **처음 세계로 돌아와** 확정한다 → 기존 A1 을 다시 쓴다.
    write(&dir, "work.txt", "처음");
    walked(session.project_mut(), NodeKind::Hypothesis);
    opened(session.project_mut(), NodeKind::Verify);
    let verify = full_report(&rules(), CycleKind::Experiment, NodeKind::Verify);
    session.close_step(verify).expect("Verify 를 닫는다");
    assert_eq!(session.project().world_snapshot().to_string(), "snapshot:A1");
    session.commit().expect("눕힌다");

    // 이제 흔들어 놓고 되돌린다 — 목표는 **A1** 이어야 한다.
    write(&dir, "work.txt", "흔들었다");
    let done = session.restore().expect("되돌린다");
    assert_eq!(done.world.to_string(), "snapshot:A1");
    assert_eq!(read(&dir, "work.txt"), "처음", "버려진 가지의 세계로 갔다");
}

#[test]
fn a_cycle_with_no_verify_restores_to_its_entry() {
    // Interview 는 Artifact 를 확정할 권한이 없다 — 그러니 되돌아갈 곳은 Entry 뿐이다.
    let dir = started("target-entry", &[("a.txt", "처음")]);
    write(&dir, "a.txt", "흔들었다");

    let said = ok(&dir, &["restore"]);
    assert!(said.contains("snapshot:A1"), "{said}");
    assert_eq!(read(&dir, "a.txt"), "처음");
}

// ── ② 바꿀 것이 없으면 아무것도 만들지 않는다 ────────────────────────────

#[test]
fn a_clean_world_is_a_successful_no_op() {
    let dir = started("no-op", &[("a.txt", "그대로")]);
    let before = (world_of(&dir), state_bytes(&dir));

    let said = ok(&dir, &["restore"]);
    assert!(said.contains("복원할 변경이 없다"), "{said}");
    assert!(said.contains("snapshot:A1"), "{said}");

    assert_eq!(world_of(&dir), before.0, "no-op 이 파일을 건드렸다");
    assert_eq!(state_bytes(&dir), before.1, "no-op 이 상태를 저장했다");
    assert!(leftovers(&dir).is_empty(), "no-op 이 transaction 을 만들었다");
    // 객체도 늘지 않았다.
    assert_eq!(
        count_objects(&dir, "manifests"),
        1,
        "no-op 이 새 manifest 를 만들었다"
    );
}

fn count_objects(root: &Path, kind: &str) -> usize {
    let at = root.join(".gil/artifacts").join(kind).join("sha256");
    fs::read_dir(&at)
        .map(|shards| {
            shards
                .map(|shard| fs::read_dir(shard.unwrap().path()).unwrap().count())
                .sum()
        })
        .unwrap_or(0)
}

// ── ③ 실제로 되돌린다 ─────────────────────────────────────────────────────

#[test]
fn every_kind_of_change_comes_back() {
    let dir = started(
        "all-changes",
        &[
            ("keep.txt", "건드리지 않는다"),
            ("edit.txt", "처음"),
            ("gone.txt", "지워질 것"),
            ("deep/nested/file.txt", "깊은 곳"),
            ("empty.txt", ""),
            ("rename-me.txt", "이름이 바뀔 것"),
        ],
    );
    let before = world_of(&dir);

    // 고치고, 만들고, 지우고, 이름을 바꾼다.
    write(&dir, "edit.txt", "바꿨다");
    write(&dir, "new.txt", "새로 생김");
    fs::remove_file(dir.join("gone.txt")).unwrap();
    fs::remove_file(dir.join("deep/nested/file.txt")).unwrap();
    fs::rename(dir.join("rename-me.txt"), dir.join("renamed.txt")).unwrap();

    let said = ok(&dir, &["restore"]);
    assert_eq!(world_of(&dir), before, "되돌린 세계가 기준과 다르다");

    // 이름 바꾸기는 **삭제 + 생성**으로 관측된다(§3.1).
    assert!(said.contains("교체  1개"), "{said}");
    assert!(said.contains("생성  3개"), "{said}"); // gone · deep/nested/file · rename-me
    assert!(said.contains("삭제  2개"), "{said}"); // new · renamed
    assert!(leftovers(&dir).is_empty(), "transaction 잔해가 남았다");

    // 그리고 이제 clean 이므로 비-Verify 자리가 닫힌다 — 결과가 정말 목표 세계다.
    assert_eq!(read(&dir, "empty.txt"), "");
}

#[test]
fn a_large_file_streams_back() {
    let big: String = "가나다라마".repeat(200_000); // ≈ 3MB
    let dir = started("large", &[("big.txt", &big)]);

    write(&dir, "big.txt", "짧아졌다");
    ok(&dir, &["restore"]);
    assert_eq!(read(&dir, "big.txt"), big, "큰 파일이 되돌아오지 않았다");
}

#[cfg(unix)]
#[test]
fn permissions_survive_a_replace_and_new_files_get_the_default() {
    use std::os::unix::fs::PermissionsExt;
    let dir = started("permissions", &[("script.sh", "#!/bin/sh\necho 처음")]);
    fs::set_permissions(dir.join("script.sh"), fs::Permissions::from_mode(0o750)).unwrap();

    // 그 권한 그대로 세계를 확정해 두고, 내용만 흔든다.
    write(&dir, "script.sh", "echo 바꿨다");
    fs::set_permissions(dir.join("script.sh"), fs::Permissions::from_mode(0o600)).unwrap();

    ok(&dir, &["restore"]);
    // **실행 전 권한을 보존한다.** Snapshot 에는 권한이 없으므로 「과거 권한을 복원했다」고
    // 말하지 않는다 — 되돌리기 직전의 것을 그대로 둘 뿐이다.
    let mode = fs::metadata(dir.join("script.sh")).unwrap().permissions().mode() & 0o777;
    assert_eq!(mode, 0o600, "교체가 실행 전 권한을 버렸다");
    assert_eq!(read(&dir, "script.sh"), "#!/bin/sh\necho 처음");
}

#[cfg(unix)]
#[test]
fn a_restored_file_never_shares_an_inode_with_the_blob() {
    // 작업 파일이 immutable blob 과 inode 를 나눠 쓰면, 다음 편집이 **창고 안의 객체를
    // 함께 고친다** — 그 순간 그 주소의 내용이 주소와 달라진다.
    use std::os::unix::fs::MetadataExt;
    let dir = started("no-hard-link", &[("a.txt", "본문")]);
    write(&dir, "a.txt", "흔들었다");
    ok(&dir, &["restore"]);

    let working = fs::metadata(dir.join("a.txt")).unwrap();
    assert_eq!(working.nlink(), 1, "작업 파일이 blob 과 link 를 나눠 쓴다");

    // 그리고 작업 파일을 고쳐도 창고는 멀쩡하다.
    write(&dir, "a.txt", "다시 흔든다");
    ok(&dir, &["restore"]);
    assert_eq!(read(&dir, "a.txt"), "본문", "창고가 함께 바뀌었다");
}

// ── ④ preflight — 하나라도 이상하면 파일을 건드리지 않는다 ───────────────

/// 창고의 객체 파일 하나를 골라 낸다.
fn an_object(root: &Path, kind: &str) -> PathBuf {
    let at = root.join(".gil/artifacts").join(kind).join("sha256");
    fs::read_dir(&at)
        .unwrap()
        .flat_map(|shard| fs::read_dir(shard.unwrap().path()).unwrap())
        .map(|entry| entry.unwrap().path())
        .next()
        .expect("객체가 하나는 있다")
}

#[test]
fn a_missing_or_corrupt_blob_stops_before_anything_changes() {
    for (label, spoil) in [
        ("blob-missing", true),
        ("blob-corrupt", false),
    ] {
        let dir = started(label, &[("a.txt", "본문"), ("b.txt", "또 하나")]);
        write(&dir, "a.txt", "흔들었다");
        let before = world_of(&dir);

        let blob = an_object(&dir, "blobs");
        match spoil {
            true => fs::remove_file(&blob).unwrap(),
            false => fs::write(&blob, b"tampered").unwrap(),
        }

        let said = refused(&dir, &["restore"]);
        assert!(said.contains("멈춘 단계\n  사전 검사"), "{label}: {said}");
        assert!(
            said.contains("프로젝트 파일은 하나도 바뀌지 않았다"),
            "{label}: {said}"
        );
        assert_eq!(world_of(&dir), before, "{label}: 파일을 건드렸다");
        assert!(leftovers(&dir).is_empty(), "{label}: transaction 을 만들었다");
    }
}

#[test]
fn a_corrupt_manifest_stops_before_anything_changes() {
    let dir = started("manifest-corrupt", &[("a.txt", "본문")]);
    write(&dir, "a.txt", "흔들었다");
    let before = world_of(&dir);

    fs::write(an_object(&dir, "manifests"), b"not a manifest").unwrap();

    refused(&dir, &["restore"]);
    assert_eq!(world_of(&dir), before, "파일을 건드렸다");
    assert!(leftovers(&dir).is_empty());
}

#[cfg(unix)]
#[test]
fn a_symlink_in_the_project_stops_the_restore() {
    let dir = started("symlink", &[("a.txt", "본문")]);
    write(&dir, "a.txt", "흔들었다");
    std::os::unix::fs::symlink(dir.join("a.txt"), dir.join("link")).unwrap();
    let before = world_of(&dir);

    let said = refused(&dir, &["restore"]);
    assert!(said.contains("심볼릭"), "{said}");
    assert_eq!(world_of(&dir), before, "파일을 건드렸다");
    assert!(leftovers(&dir).is_empty());
}

#[test]
fn a_nested_gil_stops_the_restore() {
    let dir = started("nested-gil", &[("a.txt", "본문")]);
    write(&dir, "a.txt", "흔들었다");
    fs::create_dir_all(dir.join("sub/.gil")).unwrap();
    let before = world_of(&dir);

    refused(&dir, &["restore"]);
    assert_eq!(world_of(&dir), before);
    assert!(leftovers(&dir).is_empty());
}

// ── ⑤ 죽었을 때 무엇이 남는가 ─────────────────────────────────────────────

/// 흔들어 둔 프로젝트 하나 — 실행 전 세계와 목표 세계를 함께 돌려준다.
fn shaken(label: &str) -> (PathBuf, BTreeMap<String, Vec<u8>>, BTreeMap<String, Vec<u8>>) {
    let dir = started(
        label,
        &[("edit.txt", "처음"), ("gone.txt", "지워질 것"), ("keep.txt", "그대로")],
    );
    let target = world_of(&dir);

    write(&dir, "edit.txt", "바꿨다");
    write(&dir, "new.txt", "새로 생김");
    fs::remove_file(dir.join("gone.txt")).unwrap();
    let before = world_of(&dir);
    (dir, before, target)
}

#[test]
fn dying_before_rollback_is_armed_leaves_only_scraps() {
    let (dir, before, _) = shaken("crash-preparing");
    crash_at(&dir, "prepared-not-armed");

    // `active` 가 없다 — rollback 이 걸리기 전이다.
    let left = leftovers(&dir);
    assert!(
        left.iter().all(|name| name.starts_with("preparing-")),
        "rollback 이 걸리기 전인데 active 가 생겼다: {left:?}"
    );
    assert_eq!(world_of(&dir), before, "파일을 이미 건드렸다");

    // 다음 명령이 잔해를 치운다.
    ok(&dir, &["status"]);
    assert!(leftovers(&dir).is_empty(), "잔해가 남았다");
    assert_eq!(world_of(&dir), before);
}

#[test]
fn dying_after_the_transaction_is_armed_rolls_back() {
    for point in ["after-prepare", "after-first-apply", "before-commit"] {
        let (dir, before, _) = shaken(&format!("crash-{point}"));
        let state = state_bytes(&dir);
        crash_at(&dir, point);

        assert_eq!(leftovers(&dir), vec!["active"], "{point}: active 가 없다");
        assert!(
            !dir.join(".gil/restore/active/COMMITTED").exists(),
            "{point}: 확정 표식이 있다"
        );

        // 다음 명령이 **되돌린 뒤에** 진행한다.
        ok(&dir, &["status"]);
        assert_eq!(world_of(&dir), before, "{point}: 실행 전 세계로 안 돌아갔다");
        assert!(leftovers(&dir).is_empty(), "{point}: 잔해가 남았다");
        assert_eq!(state_bytes(&dir), state, "{point}: 상태가 바뀌었다");
    }
}

#[test]
fn dying_after_the_commit_marker_keeps_the_forward_world() {
    for point in ["after-commit", "before-cleanup"] {
        let (dir, _, target) = shaken(&format!("crash-{point}"));
        let state = state_bytes(&dir);
        crash_at(&dir, point);

        // 표식이 durable 해진 뒤다 — **되돌리지 않는다.**
        ok(&dir, &["status"]);
        assert_eq!(
            world_of(&dir),
            target,
            "{point}: 확정된 복원을 되돌렸다"
        );
        assert!(leftovers(&dir).is_empty(), "{point}: 잔해가 남았다");
        assert_eq!(state_bytes(&dir), state, "{point}: 상태가 바뀌었다");
    }
}

#[test]
fn recovery_runs_before_the_state_is_read() {
    // `state.yaml` 을 읽을 수 없게 만들어 둔다. 복구가 **먼저**라면 파일은 되돌아가고,
    // 그 다음에야 상태 오류가 난다. 순서가 뒤집혔다면 파일은 그대로일 것이다.
    let (dir, before, _) = shaken("recovery-first");
    crash_at(&dir, "after-first-apply");
    fs::write(state_in(&dir), "{{{ YAML 이 아니다".as_bytes()).unwrap();

    refused(&dir, &["status"]);
    assert_eq!(world_of(&dir), before, "복구가 state 읽기 뒤에 돌았다");
    assert!(leftovers(&dir).is_empty());
}

#[test]
fn every_state_command_recovers_first() {
    // 하나라도 빠지면 그 길로 미완의 세계가 지나간다.
    for args in [
        vec!["status"],
        vec!["story"],
        vec!["context"],
        vec!["close", "--help"],
    ] {
        let (dir, before, _) = shaken(&format!("recover-{}", args.join("-")));
        crash_at(&dir, "after-first-apply");

        let out = run(&dir, &args, &[]);
        assert!(
            out.status.success(),
            "gil {args:?}: {}",
            String::from_utf8_lossy(&out.stderr)
        );
        assert_eq!(world_of(&dir), before, "gil {args:?} 가 복구하지 않았다");
        assert!(leftovers(&dir).is_empty(), "gil {args:?}");
    }
}

#[test]
fn something_gil_did_not_make_in_the_restore_area_stops_everything() {
    let dir = started("strange-area", &[("a.txt", "본문")]);
    fs::create_dir_all(dir.join(".gil/restore")).unwrap();
    write(&dir, ".gil/restore/누군가의파일", "소중한 것");

    let said = refused(&dir, &["status"]);
    assert!(said.contains("GIL 이 만든 transaction 자료가 아니다"), "{said}");
    assert!(
        dir.join(".gil/restore/누군가의파일").exists(),
        "모르는 것을 지웠다"
    );

    // 치우면 다시 돈다 — 도구가 남의 것을 대신 치우지 않는다.
    fs::remove_file(dir.join(".gil/restore/누군가의파일")).unwrap();
    ok(&dir, &["status"]);
}

#[test]
fn a_file_changed_from_outside_between_prepare_and_apply_rolls_back() {
    // 프로젝트 잠금은 편집기의 쓰기를 막지 않는다. 그래서 건드리기 직전에 다시 묻고,
    // 다르면 **앞으로 가지 않는다.**
    let (dir, before, _) = shaken("meddled");
    let out = run(&dir, &["restore"], &[(MEDDLE, "after-prepare:edit.txt")]);

    assert!(!out.status.success(), "밖에서 바뀐 파일 위로 지나갔다");
    let said = String::from_utf8_lossy(&out.stderr);
    assert!(said.contains("밖에서 바뀌었다"), "{said}");
    assert!(said.contains("실행 전 세계로 돌아갔다"), "{said}");

    // 되돌아간 곳은 **실행 전 세계**다 — 보관해 둔 원본 그대로. 그 사이에 밖에서 끼어든
    // 편집은 함께 사라진다. 그것이 「실행 전 세계로 되돌린다」의 뜻이고, 그래서 오류가
    // 「다른 프로그램이 이 폴더를 쓰고 있지 않은지 확인하라」고 말한다.
    assert_eq!(world_of(&dir), before);
    assert!(leftovers(&dir).is_empty(), "잔해가 남았다");
}

#[test]
fn a_file_changed_from_outside_after_apply_is_caught_by_the_final_check() {
    // 적용을 마쳤어도 **결과를 다시 관측해** 목표와 견준다. 그 사이에 밖에서 누가 고쳤으면
    // 그것은 목표 세계가 아니고, 목표가 아닌 것을 성공이라고 말하지 않는다.
    let (dir, before, _) = shaken("meddled-after-apply");
    let out = run(&dir, &["restore"], &[(MEDDLE, "after-apply:edit.txt")]);

    assert!(!out.status.success(), "목표가 아닌 세계를 성공이라고 했다");
    let said = String::from_utf8_lossy(&out.stderr);
    assert!(said.contains("멈춘 단계\n  결과 확인"), "{said}");
    assert!(said.contains("결과가 목표 세계와 다르다"), "{said}");
    assert!(said.contains("실행 전 세계로 돌아갔다"), "{said}");

    assert_eq!(world_of(&dir), before, "되돌아가지 않았다");
    assert!(leftovers(&dir).is_empty(), "잔해가 남았다");
}

// ── ⑥ 논리 상태는 한 글자도 바뀌지 않는다 ────────────────────────────────

#[test]
fn a_restore_changes_no_logical_state_at_all() {
    let (dir, _, _) = shaken("logical-state");
    let before = state_bytes(&dir);
    let status = ok(&dir, &["status"]);
    let story = ok(&dir, &["story"]);

    let said = ok(&dir, &["restore"]);

    // **바이트가 완전히 같다.**
    assert_eq!(state_bytes(&dir), before, "restore 가 state.yaml 을 저장했다");
    assert_eq!(ok(&dir, &["story"]), story, "걸어온 것이 달라졌다");

    // status 의 **자리 표시**는 그대로다. 달라지는 것은 「현재 세계」 절 하나뿐이고,
    // 그것이 달라지는 것이 바로 restore 가 한 일이다.
    let position = |said: &str| said[..said.find("현재 세계").expect("세계 절")].to_string();
    let after = ok(&dir, &["status"]);
    assert_eq!(position(&after), position(&status), "서 있는 자리가 움직였다");
    assert!(status.contains("상태: dirty"), "복원 전이 dirty 가 아니었다");
    assert!(after.contains("· clean"), "복원 뒤가 clean 이 아니다:\n{after}");

    // receipt 는 그 사실을 말한다.
    assert!(said.contains("현재 위치"), "{said}");
    assert!(said.contains("· 유지"), "{said}");

    // 열린 자리와 걸린 행동이 **그대로 그 자리에 있다.**
    assert!(status.contains("question"), "{status}");
    assert!(after.contains("W1"), "걸린 행동이 사라졌다");
}

#[test]
fn a_restore_mints_no_snapshot_and_no_object() {
    let (dir, _, _) = shaken("no-new-names");
    let manifests = count_objects(&dir, "manifests");
    let blobs = count_objects(&dir, "blobs");
    let state = fs::read_to_string(state_in(&dir)).unwrap();

    ok(&dir, &["restore"]);

    assert_eq!(count_objects(&dir, "manifests"), manifests, "manifest 가 늘었다");
    assert_eq!(count_objects(&dir, "blobs"), blobs, "blob 이 늘었다");
    assert_eq!(fs::read_to_string(state_in(&dir)).unwrap(), state);
    // 지금의 dirty 세계를 자동 보존한 역사로 만들지 않는다.
    assert!(state.contains("next_snapshot_id: 2"), "{state}");
}

#[test]
fn a_restored_world_lets_the_open_step_close() {
    // 되돌린 결과가 **정말 목표 세계**라면 dirty gate 를 지날 수 있다.
    let (dir, _, _) = shaken("close-after-restore");
    ok(&dir, &["restore"]);

    let out = Command::new(GIL)
        .arg("close")
        .current_dir(&dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .and_then(|mut child| {
            use std::io::Write as _;
            child.stdin.as_mut().expect("stdin").write_all(
                "question: 무엇을 원하는가\nchoices: 가 · 나\nresponse: 가\n".as_bytes(),
            )?;
            child.wait_with_output()
        })
        .expect("닫는다");
    assert!(
        out.status.success(),
        "되돌린 뒤에도 dirty 라고 한다:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
}

// ── ⑦ 거절 안내가 밟을 수 있는 길을 말한다 ───────────────────────────────

#[test]
fn the_dirty_refusal_points_at_restore() {
    let dir = started("dirty-guidance", &[("a.txt", "처음")]);
    write(&dir, "a.txt", "바꿨다");

    let out = Command::new(GIL)
        .arg("close")
        .current_dir(&dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .and_then(|mut child| {
            use std::io::Write as _;
            child.stdin.as_mut().expect("stdin").write_all(
                "question: 무엇을 원하는가\nchoices: 가 · 나\nresponse: 가\n".as_bytes(),
            )?;
            child.wait_with_output()
        })
        .expect("닫으려 한다");
    assert!(!out.status.success());
    let said = String::from_utf8_lossy(&out.stderr);

    assert!(said.contains("`gil restore` 로 현재 변경을 되돌린 뒤"), "{said}");
    assert!(said.contains("Verify Step 에서 수행한다"), "{said}");
    assert!(said.contains("그대로 열려 있다"), "{said}");
    // **밟을 수 없는 길을 안내하지 않는다.** Interview 안에서 verify 로 갈 방법은 없다.
    assert!(
        !said.contains("Experiment Cycle 에서 확정한다"),
        "밟을 수 없는 길을 안내한다: {said}"
    );
}

#[test]
fn the_receipt_does_not_spell_out_every_file_or_any_digest() {
    let mut files: Vec<(String, String)> = (0..40)
        .map(|n| (format!("f{n:02}.txt"), format!("본문 {n}")))
        .collect();
    files.push(("keep.txt".to_string(), "그대로".to_string()));
    let borrowed: Vec<(&str, &str)> = files
        .iter()
        .map(|(path, text)| (path.as_str(), text.as_str()))
        .collect();

    let dir = started("receipt-shape", &borrowed);
    for n in 0..40 {
        write(&dir, &format!("f{n:02}.txt"), "전부 바꿨다");
    }

    let said = ok(&dir, &["restore"]);
    assert!(said.contains("교체  40개"), "{said}");
    // 개별 파일 이름을 늘어놓지 않는다.
    assert!(!said.contains("f01.txt"), "{said}");
    // raw digest 도 내보이지 않는다.
    assert!(
        !said.chars().collect::<String>().contains("sha256"),
        "{said}"
    );
    assert!(said.lines().count() < 15, "receipt 가 너무 길다:\n{said}");
}

#[test]
fn restore_is_in_the_top_level_help() {
    let dir = started("help", &[("a.txt", "가")]);
    let said = ok(&dir, &["--help"]);
    assert!(said.contains("gil restore"), "{said}");
    assert!(said.contains("인수를 받지 않는다"), "{said}");
}
