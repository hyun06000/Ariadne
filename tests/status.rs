//! `gil status` 의 **현재 세계** 표시.
//!
//! 이 한 화면이 네 물음에 답해야 한다.
//!
//! ```text
//! 지금 구조가 가리키는 Snapshot 은 무엇인가
//! 작업 폴더는 그것과 같은가 다른가
//! 다르다면 여기서 확정할 수 있는가
//! 없다면 지금 실제로 밟을 수 있는 수는 무엇인가
//! ```
//!
//! **새 규칙으로 계산하지 않는다.** dirty gate·Cycle Exit·`gil restore` 가 쓰는 그
//! 읽기 경로 하나를 그대로 지난다 — 세 자리가 각자 재면 언젠가 갈리고, 그러면
//! 「닫을 수 있다」와 「되돌아갈 곳」과 「지금 상태」가 서로 다른 세계를 말한다.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};

use gil::{CycleKind, NodeKind, ProjectSession, RuleSet, WorldState};

mod common;
use common::{
    REASON, bootstrap_from, close_here, full_report, opened, spec, up_to_verify, walked,
};

const GIL: &str = env!("CARGO_BIN_EXE_gil");

// ── 연장 ───────────────────────────────────────────────────────────────────

fn rules() -> RuleSet {
    spec()
}

fn state_in(dir: &Path) -> PathBuf {
    dir.join(gil::STATE_PATH)
}

fn bare(label: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("gil-status-{label}"));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).expect("시험이 쓸 자리를 만든다");
    dir
}

fn write(root: &Path, path: &str, text: &str) {
    let at = root.join(path);
    if let Some(parent) = at.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(&at, text).unwrap();
}

fn run(dir: &Path, args: &[&str], stdin: Option<&str>) -> Output {
    let mut child = Command::new(GIL)
        .args(args)
        .current_dir(dir)
        .stdin(match stdin {
            Some(_) => Stdio::piped(),
            None => Stdio::null(),
        })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("gil 을 부를 수 있어야 한다");
    if let Some(text) = stdin {
        use std::io::Write as _;
        child
            .stdin
            .as_mut()
            .expect("stdin")
            .write_all(text.as_bytes())
            .expect("넘긴다");
    }
    child.wait_with_output().expect("끝나기를 기다린다")
}

fn ok(dir: &Path, args: &[&str]) -> String {
    let out = run(dir, args, None);
    assert!(
        out.status.success(),
        "gil {args:?} 가 실패했다:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    String::from_utf8_lossy(&out.stdout).into_owned()
}

fn status(dir: &Path) -> String {
    ok(dir, &["status"])
}

/// `현재 세계` 절만 떼어 낸다 — 그 위의 자리 표시는 이 파일의 관심이 아니다.
fn world_block(said: &str) -> String {
    let start = said.find("현재 세계").expect("현재 세계 절이 없다");
    let rest = &said[start..];
    match rest.find("\n다음:") {
        Some(end) => rest[..end].trim_end().to_string(),
        None => rest.trim_end().to_string(),
    }
}

/// 열린 question 자리 하나를 둔 프로젝트.
fn started(label: &str, files: &[(&str, &str)]) -> PathBuf {
    let dir = bare(label);
    for (path, text) in files {
        write(&dir, path, text);
    }
    ok(&dir, &["start"]);
    let out = run(
        &dir,
        &["open", "question"],
        Some("objective: a\nnext_action: b\ndone_when: c\n"),
    );
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    dir
}

// ── ① 무엇을 기준으로 삼았는가 ────────────────────────────────────────────

#[test]
fn status_names_the_world_the_position_derives() {
    let dir = started("names-world", &[("a.txt", "가")]);
    let said = status(&dir);

    assert!(said.contains("현재 세계"), "{said}");
    assert!(said.contains("snapshot:A1"), "{said}");
}

#[test]
fn an_untouched_project_reads_clean() {
    let dir = started("clean", &[("a.txt", "가"), ("b/c.txt", "나")]);
    assert_eq!(world_block(&status(&dir)), "현재 세계\n  snapshot:A1 · clean");
}

#[test]
fn creating_editing_or_deleting_reads_dirty() {
    for (label, shake) in [
        ("dirty-create", 0usize),
        ("dirty-edit", 1),
        ("dirty-delete", 2),
    ] {
        let dir = started(label, &[("a.txt", "가"), ("b.txt", "나")]);
        match shake {
            0 => write(&dir, "새것.txt", "생김"),
            1 => write(&dir, "a.txt", "바꿨다"),
            _ => fs::remove_file(dir.join("b.txt")).unwrap(),
        }
        let block = world_block(&status(&dir));
        assert!(block.contains("기준: snapshot:A1"), "{label}: {block}");
        assert!(block.contains("상태: dirty"), "{label}: {block}");
    }
}

#[test]
fn permissions_mtime_and_empty_directories_are_not_dirty() {
    // 세계의 정체성은 **경로와 바이트**뿐이다(Artifact Model §3.1). 그 밖의 것이 dirty 를
    // 만들면, 파일을 하나도 안 바꾼 사람이 되돌리라는 말을 듣는다.
    let dir = started("not-dirty", &[("a.txt", "가")]);
    assert!(world_block(&status(&dir)).contains("clean"));

    // 빈 디렉터리를 만들고 지운다.
    fs::create_dir_all(dir.join("빈/폴더")).unwrap();
    assert!(world_block(&status(&dir)).contains("clean"), "빈 폴더가 dirty 다");
    fs::remove_dir_all(dir.join("빈")).unwrap();

    // 같은 바이트로 다시 쓴다 — mtime 만 움직인다.
    write(&dir, "a.txt", "가");
    assert!(world_block(&status(&dir)).contains("clean"), "mtime 이 dirty 다");

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(dir.join("a.txt"), fs::Permissions::from_mode(0o600)).unwrap();
        assert!(world_block(&status(&dir)).contains("clean"), "권한이 dirty 다");
    }
}

// ── ② dirty 일 때 지금 밟을 수 있는 수 ───────────────────────────────────

#[test]
fn a_dirty_verify_is_told_that_closing_it_confirms_the_world() {
    let dir = bare("dirty-verify");
    write(&dir, "work.txt", "처음");
    let mut session = ProjectSession::start(rules(), state_in(&dir)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());
    up_to_verify(session.project_mut()); // Verify 를 열어 둔다
    session.commit().expect("눕힌다");
    drop(session);

    write(&dir, "work.txt", "바꿨다");
    let block = world_block(&status(&dir));

    assert!(block.contains("상태: dirty"), "{block}");
    assert!(block.contains("이 Verify 를 닫으면"), "{block}");
    assert!(block.contains("Snapshot 으로 확정한다"), "{block}");
    // **되돌리라고 하지 않는다.** 여기서는 확정이 정상적인 길이다.
    assert!(!block.contains("gil restore"), "확정할 수 있는 자리에 복원을 권했다: {block}");
}

#[test]
fn a_dirty_non_verify_step_is_told_to_restore_first() {
    let dir = started("dirty-step", &[("a.txt", "가")]);
    write(&dir, "a.txt", "바꿨다");
    let block = world_block(&status(&dir));

    assert!(block.contains("상태: dirty"), "{block}");
    assert!(block.contains("확정할 수 없다"), "{block}");
    assert!(block.contains("`gil restore` 로 기준 세계를 복원한다"), "{block}");
    assert!(block.contains("그대로 열린 채 남는다"), "{block}");
}

#[test]
fn an_interview_is_never_told_to_go_somewhere_it_cannot_reach() {
    // Interview 에는 verify 가 없고, 이 Cycle 을 닫는 것도 같은 gate 에 막힌다.
    // 「Experiment 로 가라」는 지금 밟을 수 없는 길이다.
    let dir = started("interview-guidance", &[("a.txt", "가")]);
    write(&dir, "a.txt", "바꿨다");
    let said = status(&dir);

    assert!(said.contains("interview"), "Interview 안이어야 한다: {said}");
    assert!(!said.contains("Experiment"), "밟을 수 없는 길을 안내한다: {said}");
    assert!(!said.contains("experiment"), "{said}");
    assert!(said.contains("gil restore"), "{said}");
}

// ── ③ 기준을 고르는 규칙은 하나뿐이다 ────────────────────────────────────

#[test]
fn a_closed_cycle_boundary_reads_its_exit() {
    let dir = bare("closed-boundary");
    write(&dir, "work.txt", "처음");
    let mut session = ProjectSession::start(rules(), state_in(&dir)).expect("시작한다");

    // Interview 를 닫은 자리 — bootstrap_from 은 Experiment 까지 연다. 그 Experiment 를
    // Verify 로 확정하고 닫아 **닫힌 Cycle 경계**에 세운다.
    *session.project_mut() = bootstrap_from(session.project().clone());
    up_to_verify(session.project_mut());
    write(&dir, "work.txt", "확정할 세계");
    let verify = full_report(&rules(), CycleKind::Experiment, NodeKind::Verify);
    session.close_step(verify).expect("Verify 를 닫는다");

    walked(session.project_mut(), NodeKind::Analysis);
    let outcome = opened(session.project_mut(), NodeKind::Outcome);
    let cycle = session.project().cycles().current();
    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", "success")
        .with("lesson", "배운 것")
        .with(REASON, "판정한 까닭");
    close_here(session.project_mut(), report).expect("판정을 닫는다");

    let at = common::step_id(session.project(), outcome);
    let mut close = common::cycle_report(session.project().cycles().current(), "success", at);
    close.insert(common::ACTION, "open_child");
    session.close_cycle(close).expect("Cycle 을 닫는다");
    session.commit().expect("눕힌다");

    let exit = session
        .project()
        .cycles()
        .current()
        .exit_snapshot()
        .expect("닫힌 Cycle 은 도착한 세계를 지닌다");
    drop(session);

    // 닫힌 Cycle 경계에서 기준은 **Exit** 이다.
    let block = world_block(&status(&dir));
    assert!(block.contains(&exit.to_string()), "Exit 이 기준이 아니다: {block}");
    assert!(block.contains("clean"), "{block}");
}

#[test]
fn a_closed_cycle_reports_the_exit_it_recorded_not_a_recomputation() {
    // 닫힌 Cycle 의 Exit 은 **닫으면서 확정된 사실**이다. 자식이 물려받은 것도 그 값이다.
    // 그러니 지금 다시 계산해 답하면, 저장된 사실과 화면이 서로 다른 세계를 말할 수 있다.
    let dir = bare("recorded-exit");
    write(&dir, "work.txt", "처음");
    let mut session = ProjectSession::start(rules(), state_in(&dir)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());
    up_to_verify(session.project_mut());

    write(&dir, "work.txt", "확정할 세계");
    let verify = full_report(&rules(), CycleKind::Experiment, NodeKind::Verify);
    session.close_step(verify).expect("Verify 를 닫는다");

    walked(session.project_mut(), NodeKind::Analysis);
    let outcome = opened(session.project_mut(), NodeKind::Outcome);
    let cycle = session.project().cycles().current();
    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", "success")
        .with("lesson", "배운 것")
        .with(REASON, "판정한 까닭");
    close_here(session.project_mut(), report).expect("판정을 닫는다");
    let at = common::step_id(session.project(), outcome);
    let mut close = common::cycle_report(session.project().cycles().current(), "success", at);
    close.insert(common::ACTION, "open_child");
    session.close_cycle(close).expect("Cycle 을 닫는다");
    session.commit().expect("눕힌다");
    drop(session);

    // 계보가 말하는 것은 A2 다. 기록된 Exit 만 A1 로 바꾼다.
    let path = state_in(&dir);
    let mut file: serde_norway::Value =
        serde_norway::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
    let last = file["cycles"]["nodes"].as_sequence().unwrap().len() - 1;
    assert_eq!(
        file["cycles"]["nodes"][last]["exit_snapshot_ref"],
        serde_norway::Value::from("snapshot:A2")
    );
    file["cycles"]["nodes"][last]["exit_snapshot_ref"] =
        serde_norway::Value::from("snapshot:A1");
    fs::write(&path, serde_norway::to_string(&file).unwrap()).unwrap();

    // **기록된 값**을 말한다 — 다시 계산하지 않는다.
    let block = world_block(&status(&dir));
    assert!(block.contains("snapshot:A1"), "기록된 Exit 을 말하지 않았다: {block}");
    assert!(!block.contains("snapshot:A2"), "다시 계산했다: {block}");
}

#[test]
fn an_abandoned_branch_and_the_largest_name_are_both_ignored() {
    // 버려진 가지의 세계가 **더 큰 이름**을 갖도록 배치한다. 「가장 큰 ID」를 고르는
    // 구현은 여기서 다른 기준을 말한다.
    let dir = bare("abandoned-branch");
    write(&dir, "work.txt", "처음");
    let mut session = ProjectSession::start(rules(), state_in(&dir)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());
    up_to_verify(session.project_mut());

    // 첫 가지 → A2 (버려질 것)
    write(&dir, "work.txt", "버려질 가지");
    let verify = full_report(&rules(), CycleKind::Experiment, NodeKind::Verify);
    session.close_step(verify).expect("Verify 를 닫는다");
    assert_eq!(session.project().world_snapshot().to_string(), "snapshot:A2");

    walked(session.project_mut(), NodeKind::Analysis);
    opened(session.project_mut(), NodeKind::Outcome);
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

    // 새 가지 → **처음 세계로 돌아와** A1 을 다시 쓴다.
    write(&dir, "work.txt", "처음");
    walked(session.project_mut(), NodeKind::Hypothesis);
    opened(session.project_mut(), NodeKind::Verify);
    let verify = full_report(&rules(), CycleKind::Experiment, NodeKind::Verify);
    session.close_step(verify).expect("Verify 를 닫는다");
    session.commit().expect("눕힌다");
    drop(session);

    let block = world_block(&status(&dir));
    assert!(block.contains("snapshot:A1"), "{block}");
    assert!(!block.contains("snapshot:A2"), "버려진 가지를 기준으로 삼았다: {block}");
    assert!(block.contains("clean"), "{block}");
}

#[test]
fn status_reads_the_same_world_the_gate_and_restore_read() {
    // **세 자리가 한 함수를 지난다.** 갈리면 status 가 clean 이라 말한 자리에서 close 가
    // dirty 로 거절하는 일이 생긴다.
    let dir = bare("one-read-model");
    write(&dir, "work.txt", "처음");
    let session = ProjectSession::start(rules(), state_in(&dir)).expect("시작한다");
    session.commit().expect("눕힌다");

    let state = session.world_state().expect("읽는다");
    assert_eq!(state, WorldState::Clean { world: state.world() });
    assert_eq!(state.world(), session.project().world_snapshot());

    // 흔들면 셋 다 같은 세계를 말한다.
    write(&dir, "work.txt", "바꿨다");
    let shaken = session.world_state().expect("읽는다");
    assert!(matches!(shaken, WorldState::Dirty { .. }));
    assert_eq!(shaken.world(), state.world());
    assert_eq!(
        session.restore().expect("되돌린다").world,
        state.world(),
        "restore 가 다른 세계를 목표로 삼았다"
    );
}

// ── ④ 모르는 것을 안다고 말하지 않는다 ───────────────────────────────────

#[test]
fn an_observation_failure_is_not_called_dirty() {
    let dir = started("cannot-tell", &[("a.txt", "가")]);

    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(dir.join("a.txt"), dir.join("link")).unwrap();
        let block = world_block(&status(&dir));

        assert!(block.contains("상태: 확인하지 못했다"), "{block}");
        assert!(!block.contains("dirty"), "모르는 것을 dirty 라 했다: {block}");
        assert!(block.contains("심볼릭 링크"), "무엇 때문인지 말하지 않았다: {block}");
        assert!(block.contains("현재 상태는 변경하지 않았다"), "{block}");
        // 그리고 **밟을 수 있는 수**를 준다.
        assert!(block.contains("치우거나"), "{block}");
        fs::remove_file(dir.join("link")).unwrap();
    }

    fs::create_dir_all(dir.join("sub/.gil")).unwrap();
    let block = world_block(&status(&dir));
    assert!(block.contains("확인하지 못했다"), "{block}");
    assert!(!block.contains("dirty"), "{block}");
    assert!(block.contains("중첩"), "{block}");
}

// ── ⑤ 읽기 명령이다 ──────────────────────────────────────────────────────

#[test]
fn status_changes_nothing_at_all() {
    let dir = started("read-only", &[("a.txt", "가")]);
    write(&dir, "a.txt", "바꿨다");

    let before = (
        fs::read(state_in(&dir)).unwrap(),
        fs::read_to_string(dir.join("a.txt")).unwrap(),
        objects(&dir, "blobs"),
        objects(&dir, "manifests"),
    );
    let story = ok(&dir, &["story"]);

    // 여러 번 불러도 같다 — 그리고 아무것도 남기지 않는다.
    let once = status(&dir);
    let twice = status(&dir);
    assert_eq!(once, twice, "읽기 명령이 부를 때마다 다르다");

    assert_eq!(fs::read(state_in(&dir)).unwrap(), before.0, "state.yaml 이 바뀌었다");
    assert_eq!(fs::read_to_string(dir.join("a.txt")).unwrap(), before.1);
    assert_eq!(objects(&dir, "blobs"), before.2, "관측이 blob 을 만들었다");
    assert_eq!(objects(&dir, "manifests"), before.3, "관측이 manifest 를 만들었다");
    assert_eq!(ok(&dir, &["story"]), story, "걸어온 것이 달라졌다");
    assert!(
        !dir.join(".gil/restore").exists(),
        "status 가 transaction 자리를 만들었다"
    );
}

fn objects(root: &Path, kind: &str) -> usize {
    let at = root.join(".gil/artifacts").join(kind).join("sha256");
    fs::read_dir(&at)
        .map(|shards| {
            shards
                .map(|shard| fs::read_dir(shard.unwrap().path()).unwrap().count())
                .sum()
        })
        .unwrap_or(0)
}

#[test]
fn status_shows_no_digest_no_object_path_and_no_file_list() {
    let mut files: Vec<(String, String)> = (0..30)
        .map(|n| (format!("f{n:02}.txt"), format!("본문 {n}")))
        .collect();
    files.push(("keep.txt".to_string(), "그대로".to_string()));
    let borrowed: Vec<(&str, &str)> = files
        .iter()
        .map(|(path, text)| (path.as_str(), text.as_str()))
        .collect();

    let dir = started("no-internals", &borrowed);
    for n in 0..30 {
        write(&dir, &format!("f{n:02}.txt"), "전부 바꿨다");
    }

    let block = world_block(&status(&dir));
    assert!(block.contains("상태: dirty"), "{block}");
    // 내부 주소도, 객체 경로도, 파일 목록도 없다.
    assert!(!block.contains("sha256"), "{block}");
    assert!(!block.contains(".gil/artifacts"), "{block}");
    assert!(!block.contains("f01.txt"), "파일 목록을 늘어놓았다: {block}");
    assert!(block.lines().count() <= 8, "세계 절이 너무 길다:\n{block}");
}

#[test]
fn status_stays_a_nudge_and_does_not_become_the_context() {
    // `gil context` 는 온보딩이고 `gil status` 는 지금 자리의 짧은 nudge 다.
    let dir = started("not-context", &[("a.txt", "가")]);
    let said = status(&dir);
    let context = ok(&dir, &["context"]);

    assert!(said.len() < context.len(), "status 가 context 만큼 길다");
    assert!(said.lines().count() <= 16, "status 가 길어졌다:\n{said}");
    // 그리고 기존 표시는 그대로다.
    for line in ["Cycle 1 interview", "자리:", "걸어온 것:", "존재:", "하려는 것:", "다음:"] {
        assert!(said.contains(line), "{line} 이 사라졌다:\n{said}");
    }
}

// ── ⑥ 실제 시나리오 ──────────────────────────────────────────────────────

#[test]
fn clean_then_dirty_then_restore_then_clean_reads_as_a_story() {
    let dir = started("the-arc", &[("a.txt", "처음"), ("b.txt", "그대로")]);

    assert!(world_block(&status(&dir)).contains("· clean"), "시작이 clean 이 아니다");

    write(&dir, "a.txt", "바꿨다");
    let dirty = world_block(&status(&dir));
    assert!(dirty.contains("상태: dirty"));
    assert!(dirty.contains("gil restore"), "다음 수를 말하지 않았다");

    let restored = ok(&dir, &["restore"]);
    assert!(restored.contains("snapshot:A1"), "{restored}");

    assert_eq!(
        world_block(&status(&dir)),
        "현재 세계\n  snapshot:A1 · clean",
        "되돌린 뒤에도 clean 이 아니다"
    );

    // 그리고 이제 그 자리가 닫힌다 — status 가 말한 것이 실제로 참이었다.
    let out = run(
        &dir,
        &["close"],
        Some("question: 무엇을 원하는가\nchoices: 가 · 나\nresponse: 가\n"),
    );
    assert!(
        out.status.success(),
        "status 는 clean 이라 했는데 close 가 거절했다:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
}
