//! Cycle 계층의 되돌아감 — **논리 이동이 먼저고 세계가 뒤따른다.**
//!
//! 이 조각(M4-C)은 이동과 복원까지만 짓는다. pending 을 소비해 새 Cycle 을 여는 길은 아직
//! 없고, 그래서 **공개 명령에도 걸지 않았다.** 반쪽 기능을 표면에 내놓으면 사용자가
//! 정상적으로 빠져나올 수 없다.
//!
//! 여기서 재는 것은 넷이다.
//!
//! 1. **어디로 옮겨 서는가** — 대상 조상이지 실패 Cycle 이 아니다.
//! 2. **무엇이 바뀌지 않는가** — Graph·Report·Will·Journey·창고 전부.
//! 3. **어느 세계로 되돌아가는가** — `T.exit` 이지 `F.exit` 이 아니다.
//! 4. **끊기면 무엇이 남는가** — ②가 섰으면 그것은 확정이고, ③은 `gil restore` 로 수렴한다.
//!
//! # 죽음을 어떻게 만드는가
//!
//! ②와 ③ 사이는 프로세스가 죽는 그 순간에만 존재한다. `sleep` 과 운에 기대지 않고 두 자리를
//! 연다 — `before-state-save` 와 `after-state-save`. 그리고 ③ 안쪽의 진짜 죽음은 이미
//! 지어진 `gil restore` 의 failpoint 를 **자식 프로세스로** 재현한다.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};

use gil::{CycleKind, CycleRevisitError, NodeKind, ProjectSession, Report, SessionError};

mod common;
use common::{
    ACTION, CYCLE_TARGET, REASON, bootstrap_from, cycle_report, full_report, opened, spec,
    up_to_verify, walked,
};

const GIL: &str = env!("CARGO_BIN_EXE_gil");
const REVISIT_FAIL: &str = "GIL_REVISIT_FAIL";
const RESTORE_CRASH: &str = "GIL_RESTORE_CRASH";
const RESTORE_FAIL: &str = "GIL_RESTORE_FAIL";

// ── 연장 ───────────────────────────────────────────────────────────────────

fn state_in(dir: &Path) -> PathBuf {
    dir.join(gil::STATE_PATH)
}

fn bare(label: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("gil-revisit-{label}"));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).expect("시험이 쓸 자리를 만든다");
    dir
}

fn write(root: &Path, path: &str, bytes: &str) {
    fs::write(root.join(path), bytes).unwrap();
}

fn read(root: &Path, path: &str) -> String {
    fs::read_to_string(root.join(path)).unwrap_or_else(|err| panic!("{path}: {err}"))
}

/// 프로젝트 폴더의 **세계** — `.gil` 은 세계가 아니므로 뺀다.
fn world_of(root: &Path) -> BTreeMap<String, Vec<u8>> {
    let mut out = BTreeMap::new();
    for entry in fs::read_dir(root).expect("들여다본다") {
        let entry = entry.expect("한 자리");
        if entry.file_name() == ".gil" {
            continue;
        }
        if entry.file_type().expect("종류").is_file() {
            out.insert(
                entry.file_name().to_string_lossy().into_owned(),
                fs::read(entry.path()).expect("읽는다"),
            );
        }
    }
    out
}

fn state_bytes(root: &Path) -> Vec<u8> {
    fs::read(state_in(root)).expect("상태를 읽는다")
}

/// `.gil/artifacts` 아래 **모든 내부 객체**의 이름과 바이트.
fn objects_of(root: &Path) -> BTreeMap<String, Vec<u8>> {
    let mut out = BTreeMap::new();
    collect(&root.join(".gil/artifacts"), &root.join(".gil"), &mut out);
    out
}

fn collect(at: &Path, base: &Path, out: &mut BTreeMap<String, Vec<u8>>) {
    let Ok(entries) = fs::read_dir(at) else {
        return;
    };
    for entry in entries {
        let entry = entry.expect("한 자리");
        let path = entry.path();
        match entry.file_type().expect("종류").is_dir() {
            true => collect(&path, base, out),
            false => {
                let key = path.strip_prefix(base).expect("안이다").to_string_lossy().into_owned();
                out.insert(key, fs::read(&path).expect("읽는다"));
            }
        }
    }
}

/// 되돌아감을 부르는 **하나의 문.**
///
/// 지점을 심는 환경변수는 프로세스 전체의 것이라, 나란히 도는 시험 하나가 심어 두면
/// 다른 시험이 그것을 본다. 그래서 무장하는 쪽뿐 아니라 **부르는 쪽도 전부** 이 잠금을
/// 지난다 — 한쪽만 잠그면 잠그지 않은 것과 같다.
static FAILPOINT: std::sync::Mutex<()> = std::sync::Mutex::new(());

fn revisit(session: &mut ProjectSession) -> Result<gil::CycleRevisited, SessionError> {
    let _quiet = FAILPOINT.lock().unwrap_or_else(|err| err.into_inner());
    session.revisit_cycle()
}

fn run(dir: &Path, args: &[&str], env: &[(&str, &str)]) -> Output {
    let mut command = Command::new(GIL);
    command
        .args(args)
        .current_dir(dir)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    // **심어 둔 지점을 자식에게 물려주지 않는다.** 나란히 도는 시험 하나가 무장한 순간에
    // 자식이 태어나면, 그 자식은 이 시험이 심지 않은 실패를 만난다.
    for key in [REVISIT_FAIL, RESTORE_FAIL, RESTORE_CRASH] {
        command.env_remove(key);
    }
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

// ── 시험이 서는 세계 ───────────────────────────────────────────────────────

/// **T.exit 과 F.exit 이 서로 다른** 프로젝트를 세운다.
///
/// ```text
/// C1 interview (closed · open_child)   Entry A1 · Exit A1   ← Artifact 에 투명하다
/// └─ C2 experiment (closed · failure)  Entry A1 · Exit A2   ← Verify 가 세계를 바꿨다
///        next_direction: revisit → cycle:C1
/// ```
///
/// 두 세계가 갈리는 이 배치가 이 조각의 핵심 판별기다. 「F.exit 으로 되돌린다」는 구현은
/// 여기서 다른 파일 내용을 남긴다.
fn failed_cycle(label: &str) -> (ProjectSession, PathBuf) {
    let dir = bare(label);
    write(&dir, "work.txt", "처음");
    let mut session = ProjectSession::start(spec(), state_in(&dir)).expect("시작한다");

    *session.project_mut() = bootstrap_from(session.project().clone());
    up_to_verify(session.project_mut());

    // Verify 가 세계를 바꾼다 → A2
    write(&dir, "work.txt", "실패한 시도가 남긴 세계");
    let verify = full_report(&spec(), CycleKind::Experiment, NodeKind::Verify);
    session.close_step(verify).expect("Verify 를 닫는다");
    assert_eq!(session.project().world_snapshot().to_string(), "snapshot:A2");

    walked(session.project_mut(), NodeKind::Analysis);
    opened(session.project_mut(), NodeKind::Outcome);
    let cycle = session.project().cycles().current();
    let outcome = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", "failure")
        .with("lesson", "이 접근으로는 안 된다")
        .with(ACTION, "close_cycle")
        .with(REASON, "판정을 Cycle 경계로 넘긴다");
    session.close_step(outcome).expect("판정을 닫는다");

    let cycle = session.project().cycles().current();
    let last = cycle.steps().current().expect("판정에 서 있다");
    let report = cycle_report(cycle, "failure", last);
    assert_eq!(report.get(ACTION), Some("revisit"));
    assert_eq!(report.get(CYCLE_TARGET), Some("cycle:C1"));
    session.close_cycle(report).expect("실패로 닫는다");
    session.commit().expect("눕힌다");

    (session, dir)
}

/// Experiment 하나를 **세션을 통해** 끝 경계까지 걷는다 — 세계는 건드리지 않는다.
///
/// `common::walk_to_the_exit` 는 순수 도메인용이라 Verify 에 지어낸 manifest 주소를 넣는다.
/// 여기서는 실제 창고가 있으므로 그 길을 쓸 수 없다.
fn walk_exit(session: &mut ProjectSession, verdict: &str) {
    for kind in [NodeKind::Define, NodeKind::Hypothesis, NodeKind::Verify, NodeKind::Analysis] {
        opened(session.project_mut(), kind);
        let cycle = session.project().cycles().current();
        let report = full_report(cycle.rules(), CycleKind::Experiment, kind);
        session
            .close_step(report)
            .unwrap_or_else(|err| panic!("{kind} 를 닫지 못했다: {err}"));
    }
    opened(session.project_mut(), NodeKind::Outcome);
    let cycle = session.project().cycles().current();
    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", verdict)
        .with("lesson", "이 갈래가 남긴 것")
        .with(ACTION, "close_cycle")
        .with(REASON, "판정을 Cycle 경계로 넘긴다");
    session.close_step(report).expect("판정을 닫는다");
}

/// 지금 서 있는 끝 경계를 이 판정으로 닫는다.
fn close_cycle_here(session: &mut ProjectSession, verdict: &str) {
    let cycle = session.project().cycles().current();
    let last = cycle.steps().current().expect("판정에 서 있다");
    let report = cycle_report(cycle, verdict, last);
    session
        .close_cycle(report)
        .unwrap_or_else(|err| panic!("Cycle 을 닫지 못했다: {err}"));
}

/// 되돌아가기 직전의 프로젝트 — 세계는 `A2`(= `F.exit`)이고 clean 이다.
fn ready(label: &str) -> (ProjectSession, PathBuf) {
    let (session, dir) = failed_cycle(label);
    assert_eq!(session.project().world_snapshot().to_string(), "snapshot:A2");
    assert_eq!(read(&dir, "work.txt"), "실패한 시도가 남긴 세계");
    (session, dir)
}

/// Graph 전부를 바이트로 — 거절이나 이동 뒤에도 이것이 그대로여야 한다.
fn graph_of(
    session: &ProjectSession,
) -> Vec<(String, String, Option<Report>, Option<u32>, Option<u32>, String, String)> {
    session
        .project()
        .cycles()
        .nodes()
        .iter()
        .map(|cycle| {
            (
                cycle.id().to_ref().to_string(),
                cycle.status().to_string(),
                cycle.report().cloned(),
                cycle.parent().map(|id| id.to_ref().number()),
                cycle.revisit_from().map(|id| id.to_ref().number()),
                cycle.entry_snapshot().to_string(),
                cycle
                    .exit_snapshot()
                    .map(|world| world.to_string())
                    .unwrap_or_default(),
            )
        })
        .collect()
}

/// Journey 쪽 전부 — Will 목록과 판.
fn journey_of(session: &ProjectSession) -> (String, usize, Option<String>, u32) {
    let existence = session.project().current_existence();
    (
        existence.current_journey().to_string(),
        existence.journey().done_wills().len(),
        session
            .project()
            .active_will()
            .map(|will| will.id().to_string()),
        session.project().next_will_id(),
    )
}

// ── ① 어디로 옮겨 서는가 ──────────────────────────────────────────────────

#[test]
fn a_revisit_moves_current_to_the_declared_target() {
    let (mut session, _dir) = ready("moves");
    let before = graph_of(&session);

    let done = revisit(&mut session).expect("적어 둔 되돌아감을 밟는다");

    assert_eq!(done.moved.from.to_string(), "cycle:C2", "어디서 갈라졌는가");
    assert_eq!(done.moved.target.to_string(), "cycle:C1", "어디에 섰는가");
    assert_eq!(
        done.moved.target_world.to_string(),
        "snapshot:A1",
        "되돌아갈 세계는 대상의 Exit 이다"
    );

    assert_eq!(session.project().cycles().current_id().to_ref().to_string(), "cycle:C1");
    assert_eq!(
        session.project().cycles().pending_revisit().map(|id| id.to_ref().to_string()),
        Some("cycle:C2".to_string()),
        "pending 이 실패 Cycle 을 가리켜야 한다"
    );
    assert_eq!(graph_of(&session), before, "Cycle 이 한 자리라도 바뀌었다");
}

#[test]
fn a_revisit_issues_no_name_and_makes_no_cycle() {
    let (mut session, dir) = ready("no-new-cycle");
    let names = session.project().cycles().nodes().len();
    let allocator = next_id_in(&dir);

    revisit(&mut session).expect("되돌아간다");
    session.commit().expect("눕힌다");

    assert_eq!(session.project().cycles().nodes().len(), names, "Cycle 이 늘었다");
    assert_eq!(next_id_in(&dir), allocator, "이름 발급기가 움직였다");
}

/// 저장 파일이 적어 둔 **다음 Cycle 이름**. 이름은 append-only 라 되감기지 않는다.
fn next_id_in(root: &Path) -> u64 {
    yaml_of(root)["cycles"]["next_id"]
        .as_u64()
        .expect("next_id 는 수다")
}

fn yaml_of(root: &Path) -> serde_norway::Value {
    serde_norway::from_str(&fs::read_to_string(state_in(root)).expect("상태를 읽는다"))
        .expect("저장 파일은 YAML 이다")
}

#[test]
fn a_second_revisit_from_the_same_place_is_refused() {
    let (mut session, _dir) = ready("twice");
    revisit(&mut session).expect("한 번은 밟는다");
    let before = graph_of(&session);

    let err = revisit(&mut session).expect_err("두 번째가 통과했다");
    let said = err.to_string();
    assert!(said.contains("cycle:C2") && said.contains("cycle:C1"), "{said}");
    assert!(said.contains("이미 되돌아온 자리"), "현재 상태를 말하지 않는다:\n{said}");
    // **밟을 수 있는 수를 내민다.** 되돌아온 자리에서 할 일은 갈래를 여는 것 하나뿐이다.
    assert!(said.contains("gil open"), "다음 수를 말하지 않는다:\n{said}");

    assert_eq!(graph_of(&session), before);
    assert_eq!(session.project().cycles().current_id().to_ref().to_string(), "cycle:C1");
}

#[test]
fn an_open_cycle_has_nothing_to_revisit() {
    let dir = bare("open-cycle");
    write(&dir, "work.txt", "처음");
    let mut session = ProjectSession::start(spec(), state_in(&dir)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());

    let err = revisit(&mut session).expect_err("열린 Cycle 에서 되돌아갔다");
    assert!(
        matches!(
            err,
            SessionError::Revisit(CycleRevisitError::StillOpen(_))
        ),
        "{err}"
    );
    assert!(session.project().cycles().pending_revisit().is_none());
}

#[test]
fn a_success_cycle_has_nothing_to_revisit() {
    // 성공은 `open_child` 를 적는다 — 되돌아감이 아니다. 같은 판정이 두 물음에 답한다.
    let dir = bare("success-cycle");
    write(&dir, "work.txt", "처음");
    let mut session = ProjectSession::start(spec(), state_in(&dir)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());
    walk_exit(&mut session, "success");
    close_cycle_here(&mut session, "success");

    let err = revisit(&mut session).expect_err("성공 Cycle 에서 되돌아갔다");
    let said = err.to_string();
    assert!(said.contains("open_child"), "무엇이 적혀 있었는지 말하지 않는다:\n{said}");
    assert!(session.project().cycles().pending_revisit().is_none());
}

// ── ② 무엇이 바뀌지 않는가 ────────────────────────────────────────────────

#[test]
fn a_revisit_touches_neither_will_nor_journey() {
    // 컨테이너 사이의 이동은 행동이 아니다 — Will 도 판도 만들지 않는다
    // (Will Model §5 · Existence Model §4).
    let (mut session, _dir) = ready("timelines");
    let before = journey_of(&session);

    revisit(&mut session).expect("되돌아간다");

    assert_eq!(journey_of(&session), before, "Journey 쪽이 움직였다");
    assert!(session.project().active_will().is_none(), "Will 이 생겼다");
}

#[test]
fn a_revisit_confirms_no_world_and_keeps_every_object() {
    let (mut session, dir) = ready("objects");
    let before = (
        session.project().next_snapshot_id(),
        session.project().snapshots().count(),
        objects_of(&dir),
    );

    revisit(&mut session).expect("되돌아간다");

    assert_eq!(session.project().next_snapshot_id(), before.0, "새 이름이 발급됐다");
    assert_eq!(session.project().snapshots().count(), before.1, "registry 가 늘었다");
    assert_eq!(objects_of(&dir), before.2, "창고의 객체가 달라졌다");
    // 버린 가지의 세계도 이름 그대로 남는다 — 사라지는 것은 폴더에 비친 모습뿐이다.
    assert!(
        session.project().world_manifest(common::snapshot(2)).is_some(),
        "실패 Cycle 이 확정한 A2 가 사라졌다"
    );
}

// ── ③ 어느 세계로 되돌아가는가 ────────────────────────────────────────────

#[test]
fn the_world_goes_back_to_the_target_exit_not_the_failed_one() {
    // **이 조각의 핵심 판별기.** F.exit 은 A2 이고 T.exit 은 A1 이다.
    let (mut session, dir) = ready("target-world");

    let done = revisit(&mut session).expect("되돌아간다");

    assert_eq!(done.world.world.to_string(), "snapshot:A1");
    assert!(!done.world.no_op, "바꿀 것이 있었는데 no-op 이라 했다");
    assert_eq!(
        read(&dir, "work.txt"),
        "처음",
        "실패한 시도가 남긴 세계가 그대로 남았다"
    );
}

#[test]
fn a_revisit_into_the_same_world_is_a_no_op() {
    // Interview 는 Artifact 를 확정할 권한이 없으므로, 아무것도 확정하지 않은 실패 Cycle 의
    // Exit 은 제 Entry 를 계승한다 — 대상의 Exit 과 같은 세계다.
    let dir = bare("no-op");
    write(&dir, "work.txt", "처음");
    let mut session = ProjectSession::start(spec(), state_in(&dir)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());
    walk_exit(&mut session, "failure");
    close_cycle_here(&mut session, "failure");
    session.commit().expect("눕힌다");

    let before = (world_of(&dir), objects_of(&dir));
    let done = revisit(&mut session).expect("되돌아간다");

    assert!(done.world.no_op, "바꿀 것이 없는데 만졌다");
    assert_eq!((world_of(&dir), objects_of(&dir)), before);
    assert!(
        !dir.join(".gil/restore").exists()
            || fs::read_dir(dir.join(".gil/restore")).unwrap().count() == 0,
        "no-op 이 transaction 을 남겼다"
    );
}

#[test]
fn a_dirty_world_refuses_and_moves_nothing() {
    let (mut session, dir) = ready("dirty");
    write(&dir, "work.txt", "손으로 바꿔 놓았다");
    let before = (graph_of(&session), state_bytes(&dir), world_of(&dir));

    let err = revisit(&mut session).expect_err("dirty 인데 되돌아갔다");
    let said = err.to_string();
    assert!(said.contains("snapshot:A2"), "기준 세계를 말하지 않는다:\n{said}");
    assert!(said.contains("gil restore"), "다음 수를 말하지 않는다:\n{said}");
    assert!(
        said.contains("움직이지 않았다"),
        "아무것도 안 바뀌었음을 말하지 않는다:\n{said}"
    );

    assert_eq!(session.project().cycles().current_id().to_ref().to_string(), "cycle:C2");
    assert!(session.project().cycles().pending_revisit().is_none());
    assert_eq!((graph_of(&session), state_bytes(&dir), world_of(&dir)), before);
}

#[test]
fn the_gil_dir_is_never_restored() {
    let (mut session, dir) = ready("gil-dir");
    let lock = dir.join(".gil/project.lock");
    let before = fs::metadata(&lock).map(|meta| meta.len());

    revisit(&mut session).expect("되돌아간다");

    assert_eq!(fs::metadata(&lock).map(|meta| meta.len()).ok(), before.ok());
    assert!(dir.join(".gil/state.yaml").exists(), ".gil 안이 지워졌다");
    assert!(!dir.join(".gil").join("work.txt").exists());
}

// ── ④ pending 동안 무엇이 막히는가 ────────────────────────────────────────

/// 되돌아온 상태의 프로젝트 — `current = C1`, `pending = C2`, 세계는 `A1`.
fn pending(label: &str) -> (ProjectSession, PathBuf) {
    let (mut session, dir) = ready(label);
    revisit(&mut session).expect("되돌아간다");
    session.commit().expect("눕힌다");
    (session, dir)
}

#[test]
fn pending_refuses_every_graph_change() {
    let (mut session, dir) = pending("gate");
    let before = (graph_of(&session), state_bytes(&dir), journey_of(&session));

    // Step 을 여는 것
    let err = session
        .open_action_step(NodeKind::Question, common::plan(NodeKind::Question))
        .expect_err("되돌아온 자리에서 Step 이 열렸다");
    assert_pending_says(&err.to_string());

    // Step 을 닫는 것
    let report = full_report(&spec(), CycleKind::Interview, NodeKind::Question);
    let err = session.close_step(report).expect_err("Step 이 닫혔다");
    assert_pending_says(&err.to_string());

    // Cycle 을 닫는 것
    let cycle = session.project().cycles().current();
    let last = cycle.steps().current().expect("판정에 서 있다");
    let report = cycle_report(cycle, "success", last);
    let err = session.close_cycle(report).expect_err("Cycle 이 닫혔다");
    assert_pending_says(&err.to_string());

    // 평범한 자식으로 여는 문은 **닫혀 있다** — 그 문으로 열면 갈래의 출처가 사라진다.
    let why = session
        .project()
        .cycles()
        .why_not_open_child()
        .expect("되돌아온 자리에서 평범한 자식을 열 수 있다고 안내했다");
    assert!(why.to_string().contains("갈래"), "{why}");
    let err = session
        .open_child_cycle(CycleKind::Experiment)
        .expect_err("평범한 자식이 열렸다");
    assert!(err.to_string().contains("갈래"), "{err}");

    assert_eq!(
        (graph_of(&session), state_bytes(&dir), journey_of(&session)),
        before,
        "거절이 무언가를 바꿨다"
    );
}

/// 되돌아온 자리의 거절은 **지금 상태**를 말하고, 실제로 밟을 수 있는 수를 내민다.
fn assert_pending_says(said: &str) {
    assert!(said.contains("cycle:C1"), "어디에 섰는지 말하지 않는다:\n{said}");
    assert!(
        said.contains("되돌아온") || said.contains("갈래"),
        "되돌아온 자리임을 말하지 않는다:\n{said}"
    );
    assert!(
        said.contains("gil open"),
        "지금 실제로 밟을 수 있는 수를 말하지 않는다:\n{said}"
    );
}

#[test]
fn pending_still_allows_reading_and_restoring() {
    let (session, dir) = pending("gate-allowed");
    drop(session); // 잠금을 놓는다 — 아래는 진짜 자식 프로세스다.

    for args in [
        &["status"][..],
        &["story"][..],
        &["context"][..],
        &["help"][..],
        &["restore"][..],
    ] {
        ok(&dir, args);
    }
    assert_eq!(read(&dir, "work.txt"), "처음", "읽기가 세계를 흔들었다");
}

// ── ⑤ 저장 호환 ───────────────────────────────────────────────────────────

#[test]
fn no_pending_writes_no_field() {
    let (_session, dir) = ready("field-absent");
    let cycles = yaml_of(&dir)["cycles"].clone();
    assert!(
        cycles.get("pending_cycle_revisit").is_none(),
        "pending 이 없는데 칸을 썼다:\n{cycles:?}"
    );
    assert_eq!(yaml_of(&dir)["format"].as_u64(), Some(4), "format 이 올랐다");
}

#[test]
fn a_pending_round_trips_and_keeps_format_four() {
    let (session, dir) = pending("round-trip");
    let before = graph_of(&session);
    drop(session);

    let file = yaml_of(&dir);
    assert_eq!(file["format"].as_u64(), Some(4), "format 이 올랐다");
    assert_eq!(
        file["cycles"]["pending_cycle_revisit"].as_u64(),
        Some(2),
        "저장 계층은 bare Cycle 이름을 쓴다"
    );
    assert_eq!(file["cycles"]["current"].as_u64(), Some(1));

    let again = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");
    assert_eq!(
        again.project().cycles().pending_revisit().map(|id| id.to_ref().to_string()),
        Some("cycle:C2".to_string())
    );
    assert_eq!(again.project().cycles().current_id().to_ref().to_string(), "cycle:C1");
    assert_eq!(graph_of(&again), before, "왕복이 Graph 를 바꿨다");
}

/// 저장 파일을 손으로 고치고, 되살리기가 거절하는 말을 돌려준다.
fn tampered(dir: &Path, edit: impl FnOnce(&mut serde_norway::Value)) -> String {
    let mut file = yaml_of(dir);
    edit(&mut file);
    fs::write(state_in(dir), serde_norway::to_string(&file).unwrap()).unwrap();
    match ProjectSession::open(spec(), state_in(dir)) {
        Err(err) => err.to_string(),
        Ok(_) => panic!("걸어서 만들 수 없는 파일이 되살아났다"),
    }
}

#[test]
fn a_pending_that_points_nowhere_is_refused() {
    let (session, dir) = pending("file-unknown");
    drop(session);
    let said = tampered(&dir, |file| {
        file["cycles"]["pending_cycle_revisit"] = serde_norway::Value::from(9u32);
    });
    assert!(said.contains("그런 Cycle 이 이 Graph 에 없다"), "{said}");
}

#[test]
fn a_pending_whose_source_is_open_is_refused() {
    // 열린 Cycle 은 Report 를 지니지 않는다 — 밟을 결정이 적혀 있을 수 없다.
    let (session, dir) = ready("file-open-source");
    drop(session);
    let said = tampered(&dir, |file| {
        file["cycles"]["pending_cycle_revisit"] = serde_norway::Value::from(2u32);
        file["cycles"]["current"] = serde_norway::Value::from(1u32);
        file["cycles"]["nodes"][1]["status"] = serde_norway::Value::from("open");
        file["cycles"]["nodes"][1]["report"] = serde_norway::Value::Null;
        file["cycles"]["nodes"][1]["exit_snapshot_ref"] = serde_norway::Value::Null;
    });
    assert!(
        said.contains("밟지 않은 되돌아감") || said.contains("열려 있는데"),
        "{said}"
    );
}

#[test]
fn a_pending_whose_source_did_not_declare_a_revisit_is_refused() {
    // 성공으로 닫힌 Cycle 에서 되돌아왔다는 파일 — 그 자리에 그 결정이 없다.
    let dir = bare("file-not-declared");
    write(&dir, "work.txt", "처음");
    let mut session = ProjectSession::start(spec(), state_in(&dir)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());
    walk_exit(&mut session, "success");
    close_cycle_here(&mut session, "success");
    session.commit().expect("눕힌다");
    drop(session);

    let said = tampered(&dir, |file| {
        file["cycles"]["pending_cycle_revisit"] = serde_norway::Value::from(2u32);
        file["cycles"]["current"] = serde_norway::Value::from(1u32);
    });
    assert!(said.contains("밟지 않은 되돌아감"), "{said}");
    assert!(said.contains("cycle:C2") || said.contains("Cycle 2"), "{said}");
}

#[test]
fn a_pending_whose_current_is_not_the_declared_target_is_refused() {
    let (session, dir) = pending("file-wrong-current");
    drop(session);
    let said = tampered(&dir, |file| {
        // pending 은 그대로 두고 서 있는 자리만 실패 Cycle 로 되돌린다.
        file["cycles"]["current"] = serde_norway::Value::from(2u32);
    });
    assert!(said.contains("밟지 않은 되돌아감"), "{said}");
}

#[test]
fn an_open_cycle_cannot_coexist_with_a_pending() {
    // 되돌아와 선 자리는 **닫힌 조상**이다. 그것을 열어 두면 그 아래 난 실패 Cycle 이
    // 설 자리를 잃는다 — 「자식은 자식을 열겠다고 적은 Cycle 아래에서만 난다」가 먼저
    // 잡는다. 어느 말로 거절하든 결과는 하나다: 이 꼴은 되살아나지 않는다.
    let (session, dir) = pending("file-open-cycle");
    drop(session);
    let said = tampered(&dir, |file| {
        file["cycles"]["nodes"][0]["status"] = serde_norway::Value::from("open");
        file["cycles"]["nodes"][0]["report"] = serde_norway::Value::Null;
        file["cycles"]["nodes"][0]["exit_snapshot_ref"] = serde_norway::Value::Null;
    });
    assert!(
        said.contains("열려 있다")
            || said.contains("밟지 않은 되돌아감")
            || said.contains("적은 Cycle 아래에서만 난다"),
        "{said}"
    );
}

#[test]
fn an_unknown_field_is_still_refused() {
    // 선택적 칸 하나가 format 4 를 임의 mapping 으로 바꾸지 않는다.
    let (session, dir) = pending("file-unknown-field");
    drop(session);
    let said = tampered(&dir, |file| {
        file["cycles"]["pending_cycle_merge"] = serde_norway::Value::from(1u32);
    });
    assert!(
        said.contains("pending_cycle_merge") || said.contains("unknown field"),
        "{said}"
    );
}

#[test]
fn an_older_format_four_without_the_field_still_loads() {
    // 앞서 저장된 파일에는 이 칸이 없다. 없는 것을 거절하면 기존 프로젝트가 막힌다.
    let (session, dir) = ready("file-legacy");
    drop(session);
    let mut file = yaml_of(&dir);
    let map = file["cycles"].as_mapping_mut().expect("mapping 이다");
    map.remove(serde_norway::Value::from("pending_cycle_revisit"));
    fs::write(state_in(&dir), serde_norway::to_string(&file).unwrap()).unwrap();

    let again = ProjectSession::open(spec(), state_in(&dir)).expect("칸이 없어도 읽힌다");
    assert!(again.project().cycles().pending_revisit().is_none());
    assert_eq!(again.project().cycles().current_id().to_ref().to_string(), "cycle:C2");
}

// ── ⑥ 순서와 중단 ─────────────────────────────────────────────────────────
//
// ②가 서기 전에 폴더를 만지지 않고, ②가 선 뒤에는 그것을 되돌리지 않는다.
// 어느 지점에서 끊겨도 남는 최악의 상태는 하나다 — 「상태는 대상, 폴더는 아직」.
// 그리고 그 처방은 이미 지어진 멱등 `gil restore` 하나다.

/// 정해진 지점에서 **오류를 내는** 되돌아감을 돌린다.
fn revisit_failing_at(session: &mut ProjectSession, point: &str) -> String {
    let _armed = FAILPOINT.lock().unwrap_or_else(|err| err.into_inner());
    // SAFETY: 되돌아감을 부르는 모든 자리가 이 잠금을 지나므로, 심은 지점을 다른 시험이
    // 보는 일이 없다. 부르자마자 지운다.
    unsafe { std::env::set_var(REVISIT_FAIL, point) };
    let said = session
        .revisit_cycle()
        .map(|_| ())
        .expect_err("심어 둔 실패가 통과했다");
    unsafe { std::env::remove_var(REVISIT_FAIL) };
    said.to_string()
}

#[test]
fn a_failure_before_the_state_save_changes_nothing() {
    // ② 이전 실패 — 논리도 폴더도 그대로다.
    let (mut session, dir) = ready("before-save");
    let before = (state_bytes(&dir), world_of(&dir), objects_of(&dir));

    revisit_failing_at(&mut session, "before-state-save");

    assert_eq!(state_bytes(&dir), before.0, "state 가 바뀌었다");
    assert_eq!(world_of(&dir), before.1, "작업 폴더가 바뀌었다");
    assert_eq!(objects_of(&dir), before.2, "창고가 바뀌었다");
    assert_eq!(read(&dir, "work.txt"), "실패한 시도가 남긴 세계");
    // 그리고 다시 부르면 정상적으로 밟힌다 — 남은 흔적이 없다.
    let done = revisit(&mut session).expect("다시 부르면 밟힌다");
    assert_eq!(done.moved.target_world.to_string(), "snapshot:A1");
}

#[test]
fn a_failure_after_the_state_save_keeps_the_move_and_converges() {
    // ②는 섰고 ③은 시작하지 못했다. **「아무것도 바뀌지 않았다」고 말하면 안 되는 자리다.**
    let (mut session, dir) = ready("after-save");
    let world_before = world_of(&dir);

    let said = revisit_failing_at(&mut session, "after-state-save");
    assert!(
        !said.contains("움직이지 않았다") && !said.contains("바뀌지 않았다"),
        "확정된 이동을 없던 일로 말했다:\n{said}"
    );

    // 논리는 이미 옮겨졌고 그것이 파일에 있다.
    let file = yaml_of(&dir);
    assert_eq!(file["cycles"]["current"].as_u64(), Some(1), "이동이 저장되지 않았다");
    assert_eq!(file["cycles"]["pending_cycle_revisit"].as_u64(), Some(2));
    // 폴더는 아직 옛 세계다 — 그리고 그것이 정상이다.
    assert_eq!(world_of(&dir), world_before, "③ 을 시작하지 않았는데 폴더가 바뀌었다");

    // 다음 명령이 수렴시킨다.
    drop(session);
    let said = ok(&dir, &["restore"]);
    assert!(said.contains("snapshot:A1"), "{said}");
    assert_eq!(read(&dir, "work.txt"), "처음", "수렴하지 않았다");
}

#[test]
fn a_failed_projection_never_rewinds_the_committed_move() {
    // **③이 실패해도 ②를 되돌리지 않는다.** 되돌리면 다음 `gil restore` 가 다시 F.exit 을
    // 목표로 삼고, 사용자는 되돌아간 적이 없는 자리에 서게 된다.
    //
    // 두 자리에서 끊는다 — 적용 도중(rollback 이 걸린다)과 표식 직전(다음 명령이 되돌린다).
    for point in ["after-first-apply", "before-commit"] {
        let (mut session, dir) = ready(&format!("projection-failed-{point}"));

        let said = {
            let _armed = FAILPOINT.lock().unwrap_or_else(|err| err.into_inner());
            // SAFETY: 되돌아감을 부르는 모든 자리가 이 잠금을 지나고, 자식에게도 물려주지
            // 않는다(`run` 이 지운다).
            unsafe { std::env::set_var(RESTORE_FAIL, point) };
            let said = session
                .revisit_cycle()
                .map(|_| ())
                .expect_err("심어 둔 복원 실패가 통과했다")
                .to_string();
            unsafe { std::env::remove_var(RESTORE_FAIL) };
            said
        };

        // 「확정된 것」을 먼저 말하고 「끝나지 않은 것」을 그 다음에 말한다 — 이 자리에서만은
        // 「아무것도 바뀌지 않았다」가 거짓이다.
        let confirmed = said.find("확정된 것").unwrap_or_else(|| panic!("{point}:\n{said}"));
        let unfinished = said.find("끝나지 않은 것").unwrap_or_else(|| panic!("{point}:\n{said}"));
        assert!(confirmed < unfinished, "{point}: 순서가 뒤집혔다:\n{said}");
        assert!(said.contains("이 이동은 저장됐다"), "{point}:\n{said}");
        // 안쪽 복원 receipt 의 「논리 상태는 바뀌지 않았다」가 이 이동까지 부정하는 것으로
        // 읽히면 안 된다 — 누구의 말인지 밝힌다.
        assert!(
            said.contains("복원 자체가 한 말이다"),
            "{point}: 안쪽 말과 바깥 사실을 가르지 않는다:\n{said}"
        );
        assert!(said.contains("cycle:C1"), "{point}: 어디에 섰는지 말하지 않는다:\n{said}");
        assert!(said.contains("snapshot:A1"), "{point}: 어느 세계인지 말하지 않는다:\n{said}");
        assert!(said.contains("gil restore"), "{point}: 다음 수를 말하지 않는다:\n{said}");

        // 저장된 논리 상태는 **여전히 옮겨진 채**다.
        let file = yaml_of(&dir);
        assert_eq!(file["cycles"]["current"].as_u64(), Some(1), "{point}: 이동이 되감겼다");
        assert_eq!(
            file["cycles"]["pending_cycle_revisit"].as_u64(),
            Some(2),
            "{point}: pending 이 지워졌다"
        );

        // 그리고 다음 명령이 — 복구를 먼저 하고 — 수렴시킨다.
        drop(session);
        let said = ok(&dir, &["restore"]);
        assert!(said.contains("snapshot:A1"), "{point}: {said}");
        assert_eq!(read(&dir, "work.txt"), "처음", "{point} 에서 수렴하지 않았다");
        let left: Vec<_> = fs::read_dir(dir.join(".gil/restore"))
            .map(|entries| entries.map(|e| e.unwrap().file_name()).collect())
            .unwrap_or_default();
        assert!(left.is_empty(), "{point}: 잔해가 남았다: {left:?}");
    }
}

/// 되돌아온 상태를 만들되 **③을 시작하지 않은 채로** 둔다.
fn moved_but_not_projected(label: &str) -> PathBuf {
    let (mut session, dir) = ready(label);
    revisit_failing_at(&mut session, "after-state-save");
    drop(session);
    dir
}

/// 정해진 지점에서 **죽는** `gil restore` 를 자식 프로세스로 돌린다.
fn restore_crashing_at(dir: &Path, point: &str) {
    let out = run(dir, &["restore"], &[(RESTORE_CRASH, point)]);
    assert!(
        !out.status.success(),
        "{point} 에서 죽어야 하는데 곱게 끝났다:\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
}

#[test]
fn every_interruption_inside_the_projection_converges() {
    // ③ 안쪽의 진짜 죽음은 이미 지어진 restore transaction 의 지점을 그대로 쓴다.
    // Cycle 되돌아감 전용 plan codec 을 만들지 않았으므로, 같은 복구가 그대로 적용된다.
    for point in [
        "prepared-not-armed", // active 가 걸리기 전
        "after-prepare",      // active 는 걸렸고 파일은 아직
        "after-first-apply",  // 한 자리만 바뀐 뒤 — rollback 이 필요하다
        "before-commit",      // 전부 바꾸고 표식 직전
        "after-commit",       // 표식이 durable 해진 뒤
        "before-cleanup",     // 잔해 자리로 옮긴 뒤
    ] {
        let dir = moved_but_not_projected(&format!("crash-{point}"));
        restore_crashing_at(&dir, point);

        // 다음 명령이 먼저 치우고, 그 다음 되돌린다.
        let said = ok(&dir, &["restore"]);
        assert!(said.contains("snapshot:A1"), "{point}: {said}");
        assert_eq!(read(&dir, "work.txt"), "처음", "{point} 에서 수렴하지 않았다");

        // 논리 이동은 어느 경우에도 그대로 남는다.
        let file = yaml_of(&dir);
        assert_eq!(file["cycles"]["current"].as_u64(), Some(1), "{point}");
        assert_eq!(file["cycles"]["pending_cycle_revisit"].as_u64(), Some(2), "{point}");

        // 잔해도 남지 않는다.
        let left: Vec<_> = fs::read_dir(dir.join(".gil/restore"))
            .map(|entries| entries.map(|e| e.unwrap().file_name()).collect())
            .unwrap_or_default();
        assert!(left.is_empty(), "{point}: 잔해가 남았다: {left:?}");
    }
}

#[test]
fn the_projection_never_runs_before_the_state_save() {
    // 순서가 뒤집힌 구현이라면, ②를 막았을 때 폴더가 이미 대상의 세계로 가 있다.
    let (mut session, dir) = ready("order");
    revisit_failing_at(&mut session, "before-state-save");
    assert_eq!(
        read(&dir, "work.txt"),
        "실패한 시도가 남긴 세계",
        "state 를 저장하기 전에 폴더를 먼저 만졌다"
    );
}

#[test]
fn a_half_done_revisit_never_rewinds_the_state() {
    // ③ 실패 때문에 ②를 되돌리면, 다음 `gil restore` 는 다시 F.exit 을 목표로 삼는다.
    let dir = moved_but_not_projected("no-rewind");
    let file = yaml_of(&dir);
    assert_eq!(
        file["cycles"]["current"].as_u64(),
        Some(1),
        "확정된 논리 이동이 되감겼다"
    );

    let session = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");
    assert_eq!(
        session.project().world_snapshot().to_string(),
        "snapshot:A1",
        "지금 자리가 유도하는 세계가 대상의 것이 아니다"
    );
}


// ── ⑦ 공개 표면 — 이제 밟을 수 있다 ──────────────────────────────────────

#[test]
fn the_public_command_walks_the_declared_revisit() {
    let (session, dir) = ready("surface");
    drop(session);

    let said = ok(&dir, &["revisit"]);
    assert!(said.contains("되돌아갔다"), "{said}");
    assert!(said.contains("출처: cycle:C2 · experiment · failure"), "{said}");
    assert!(said.contains("대상: cycle:C1"), "{said}");
    assert!(said.contains("snapshot:A1 로 복원했다"), "{said}");
    assert!(said.contains("gil open interview"), "{said}");
    assert!(said.contains("gil open experiment"), "{said}");
    // 파일 목록도 내부 주소도 전체 Context 도 내지 않는다.
    assert!(!said.contains("work.txt"), "파일 목록을 냈다:\n{said}");
    assert!(!said.contains("sha256"), "내부 주소를 냈다:\n{said}");
    assert!(!said.contains("═══"), "Context 를 통째로 복제했다:\n{said}");
    assert_eq!(read(&dir, "work.txt"), "처음");

    let file = yaml_of(&dir);
    assert_eq!(file["cycles"]["current"].as_u64(), Some(1));
    assert_eq!(file["cycles"]["pending_cycle_revisit"].as_u64(), Some(2));
}

#[test]
fn the_public_command_takes_no_argument() {
    let (session, dir) = ready("surface-args");
    drop(session);

    for extra in ["cycle:C1", "snapshot:A1", "--force", "C1", "experiment"] {
        let said = refused(&dir, &["revisit", extra]);
        assert!(said.contains("받지 않는다"), "{extra}: {said}");
        assert!(said.contains("이미 확정됐다"), "{extra}: {said}");
        // 복구할 Topic 을 함께 건다.
        assert!(said.contains("cycle/revisit"), "{extra}: {said}");
    }
    // 그리고 아무것도 옮겨지지 않았다.
    assert_eq!(yaml_of(&dir)["cycles"]["current"].as_u64(), Some(2));
}

// ── ⑧ 갈래를 연다 — pending 을 소비하는 한 전이 ──────────────────────────

/// 되돌아온 자리에서 새 갈래를 열고, 그 Cycle 의 주소를 돌려준다.
fn open_branch(session: &mut ProjectSession, kind: CycleKind) -> String {
    let id = session
        .open_branch_cycle(kind)
        .unwrap_or_else(|err| panic!("갈래를 열지 못했다: {err}"));
    session.commit().expect("눕힌다");
    id.to_ref().to_string()
}

#[test]
fn a_branch_records_parent_source_and_entry() {
    let (mut session, _dir) = pending("branch");
    let before = graph_of(&session);

    let born = open_branch(&mut session, CycleKind::Experiment);
    assert_eq!(born, "cycle:C3");

    let cycles = session.project().cycles();
    let n = cycles.current();
    assert_eq!(n.id().to_ref().to_string(), "cycle:C3");
    assert_eq!(n.parent().map(|id| id.to_ref().to_string()), Some("cycle:C1".into()), "부모는 대상이다");
    assert_eq!(
        n.revisit_from().map(|id| id.to_ref().to_string()),
        Some("cycle:C2".into()),
        "갈래의 출처는 버린 실패다"
    );
    assert_eq!(n.entry_snapshot().to_string(), "snapshot:A1", "출발 세계는 대상의 Exit 이다");
    assert!(!n.is_closed());
    assert!(n.steps().nodes().is_empty(), "Step Graph 가 비어 있지 않다");
    assert!(cycles.pending_revisit().is_none(), "pending 이 소비되지 않았다");

    // F 와 T 는 한 글자도 바뀌지 않았다.
    let after: Vec<_> = graph_of(&session).into_iter().take(before.len()).collect();
    assert_eq!(after, before, "기존 Cycle 이 바뀌었다");

    // 그리고 그 안에서 첫 Step 은 문법이 정한 그것이다.
    assert_eq!(n.openable_here(), vec![NodeKind::Define]);
}

#[test]
fn an_interview_branch_is_allowed_too() {
    let (mut session, _dir) = pending("branch-interview");
    open_branch(&mut session, CycleKind::Interview);
    let n = session.project().cycles().current();
    assert_eq!(n.kind(), CycleKind::Interview);
    assert_eq!(n.openable_here(), vec![NodeKind::Question], "Interview 는 질문부터다");
}

#[test]
fn a_branch_makes_no_will_and_no_revision_and_no_snapshot() {
    let (mut session, dir) = pending("branch-quiet");
    let before = (journey_of(&session), objects_of(&dir), session.project().next_snapshot_id());

    open_branch(&mut session, CycleKind::Experiment);

    assert_eq!(journey_of(&session), before.0, "Will 이나 판이 움직였다");
    assert!(session.project().active_will().is_none());
    assert_eq!(objects_of(&dir), before.1, "창고가 달라졌다");
    assert_eq!(session.project().next_snapshot_id(), before.2, "새 이름이 발급됐다");
    // 그리고 새 Cycle 을 여느라 폴더를 관측하지 않았다 — Entry 는 **저장된 값**을 읽는다.
    assert_eq!(read(&dir, "work.txt"), "처음");
}

#[test]
fn the_lineage_of_a_branch_never_walks_the_source() {
    let (mut session, _dir) = pending("branch-lineage");
    open_branch(&mut session, CycleKind::Experiment);

    let cycles = session.project().cycles();
    let lineage: Vec<String> = cycles
        .lineage(cycles.current_id())
        .unwrap()
        .iter()
        .map(|cycle| cycle.id().to_ref().to_string())
        .collect();
    assert_eq!(lineage, vec!["cycle:C1", "cycle:C3"], "계보가 출처를 따라갔다");
    assert!(!lineage.contains(&"cycle:C2".to_string()), "버린 갈래가 계보에 섞였다");
}

#[test]
fn a_branch_is_born_of_the_current_existence() {
    let (mut session, _dir) = pending("branch-owner");
    let owner = session.project().current_existence_ref();
    open_branch(&mut session, CycleKind::Experiment);
    let n = session.project().cycles().current();
    assert_eq!(n.existence(), owner);
    assert!(n.journey().is_none(), "열린 Cycle 에 닫은 판이 적혔다");
}

#[test]
fn opening_a_branch_without_a_pending_is_refused() {
    let (mut session, _dir) = ready("branch-nothing");
    let err = session
        .open_branch_cycle(CycleKind::Experiment)
        .expect_err("소비할 결정이 없는데 갈래가 열렸다");
    assert!(err.to_string().contains("되돌아온 적이 없다"), "{err}");
    assert_eq!(session.project().cycles().nodes().len(), 2, "Cycle 이 늘었다");
}

#[test]
fn a_branch_and_the_pending_land_in_one_save() {
    // 둘 중 하나만 저장되는 상태를 만들지 않는다. 도메인 전이가 하나이므로 중간이 없다.
    let (mut session, dir) = pending("branch-atomic");
    let before = yaml_of(&dir);
    assert_eq!(before["cycles"]["pending_cycle_revisit"].as_u64(), Some(2));
    assert_eq!(before["cycles"]["nodes"].as_sequence().unwrap().len(), 2);

    open_branch(&mut session, CycleKind::Experiment);

    let after = yaml_of(&dir);
    assert!(
        after["cycles"].get("pending_cycle_revisit").is_none(),
        "pending 이 파일에 남았다"
    );
    assert_eq!(after["cycles"]["nodes"].as_sequence().unwrap().len(), 3);
    assert_eq!(after["cycles"]["next_id"].as_u64(), Some(4), "이름 발급기가 함께 오르지 않았다");
    assert_eq!(after["cycles"]["nodes"][2]["revisit_from"].as_u64(), Some(2));
    assert_eq!(after["cycles"]["nodes"][2]["parent"].as_u64(), Some(1));
}

#[test]
fn a_refused_branch_moves_neither_the_allocator_nor_the_pending() {
    // 이름은 append-only 다. 거절이 발급기를 움직이면 다시 시도할 때 이름 하나가 비어 버린다.
    let (session, dir) = pending("branch-refused");
    drop(session);
    let before = yaml_of(&dir);

    // 모르는 종류로 여러 번 거절당한다.
    for name in ["chain", "define", "C1", ""] {
        refused(&dir, &["open", name]);
    }
    let after = yaml_of(&dir);
    assert_eq!(after["cycles"]["next_id"], before["cycles"]["next_id"], "발급기가 움직였다");
    assert_eq!(
        after["cycles"]["pending_cycle_revisit"],
        before["cycles"]["pending_cycle_revisit"],
        "pending 이 사라졌다"
    );
    assert_eq!(
        after["cycles"]["nodes"].as_sequence().unwrap().len(),
        before["cycles"]["nodes"].as_sequence().unwrap().len()
    );

    // 그리고 다시 열면 **원래 받았어야 할 이름**을 받는다.
    ok(&dir, &["open", "experiment"]);
    assert_eq!(yaml_of(&dir)["cycles"]["nodes"][2]["id"].as_u64(), Some(3));
}

#[test]
fn a_step_kind_at_a_branch_place_is_told_it_is_a_cycle_place() {
    let (session, dir) = pending("branch-step-kind");
    drop(session);
    let said = refused(&dir, &["open", "define"]);
    assert!(said.contains("Step 종류"), "계층을 설명하지 않는다:\n{said}");
    assert!(said.contains("interview") && said.contains("experiment"), "{said}");
}

#[test]
fn a_branch_survives_the_round_trip() {
    let (mut session, dir) = pending("branch-round-trip");
    open_branch(&mut session, CycleKind::Experiment);
    let before = graph_of(&session);
    drop(session);

    let again = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");
    assert_eq!(graph_of(&again), before, "왕복이 Graph 를 바꿨다");
    assert_eq!(
        again.project().cycles().current().revisit_from().map(|id| id.to_ref().to_string()),
        Some("cycle:C2".into())
    );
    assert!(again.project().cycles().pending_revisit().is_none());
}

// ── ⑨ 실제 시나리오 — 명세가 적은 그 걷기 ────────────────────────────────
//
//     C1 Interview success
//     └─ C2 Experiment success
//        └─ C3 Experiment failure → revisit(cycle:C2) → C4
//
// 그리고 C4 도 실패하면 같은 C2 를 **다시** 대상으로 삼을 수 있다.

/// `C1 → C2(success) → C3(open)` 까지 걷는다.
fn three_deep(label: &str) -> (ProjectSession, PathBuf) {
    let dir = bare(label);
    write(&dir, "work.txt", "처음");
    let mut session = ProjectSession::start(spec(), state_in(&dir)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());

    walk_exit(&mut session, "success");
    close_cycle_here(&mut session, "success");
    session.open_child_cycle(CycleKind::Experiment).expect("자식을 연다");
    session.commit().expect("눕힌다");
    (session, dir)
}

/// 지금 열린 Experiment 를 실패로 걷고 **이 대상**을 향해 닫는다.
fn fail_toward(session: &mut ProjectSession, target: &str) {
    walk_exit(session, "failure");
    let cycle = session.project().cycles().current();
    let last = cycle.steps().current().expect("판정에 서 있다");
    let report = cycle_report(cycle, "failure", last).with(CYCLE_TARGET, target);
    session.close_cycle(report).expect("실패로 닫는다");
    session.commit().expect("눕힌다");
}

#[test]
fn the_canonical_scenario_walks_end_to_end() {
    let (mut session, dir) = three_deep("scenario");
    fail_toward(&mut session, "cycle:C2");
    drop(session);

    // ── gil revisit ───────────────────────────────────────────────────────
    let said = ok(&dir, &["revisit"]);
    assert!(said.contains("출처: cycle:C3"), "{said}");
    assert!(said.contains("대상: cycle:C2"), "{said}");

    let file = yaml_of(&dir);
    assert_eq!(file["cycles"]["current"].as_u64(), Some(2), "current 가 C2 가 아니다");
    assert_eq!(file["cycles"]["pending_cycle_revisit"].as_u64(), Some(3));

    // ── gil open experiment ───────────────────────────────────────────────
    let said = ok(&dir, &["open", "experiment"]);
    assert!(said.contains("열었다: cycle:C4"), "{said}");
    assert!(said.contains("부모 cycle:C2"), "{said}");
    assert!(said.contains("갈래 출처: cycle:C3"), "{said}");
    assert!(said.contains("define"), "첫 Step 을 말하지 않는다:\n{said}");

    let session = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");
    let cycles = session.project().cycles();
    let c4 = cycles.current();
    assert_eq!(c4.parent().map(|id| id.to_ref().to_string()), Some("cycle:C2".into()));
    assert_eq!(c4.revisit_from().map(|id| id.to_ref().to_string()), Some("cycle:C3".into()));
    let c2 = &cycles.nodes()[1];
    assert_eq!(
        c4.entry_snapshot(),
        c2.exit_snapshot().expect("닫힌 대상은 확정한 세계를 지닌다"),
        "출발 세계가 대상의 Exit 이 아니다"
    );
    assert!(cycles.pending_revisit().is_none());

    // 계보는 부모만 따라간다 — C3 은 없다.
    let lineage: Vec<String> = cycles
        .lineage(cycles.current_id())
        .unwrap()
        .iter()
        .map(|cycle| cycle.id().to_ref().to_string())
        .collect();
    assert_eq!(lineage, vec!["cycle:C1", "cycle:C2", "cycle:C4"]);

    // 실패 Cycle 과 그 지식은 그대로 있다.
    let c3 = cycles.node(cycles.nodes()[2].id()).expect("C3 은 실재한다");
    assert!(c3.is_closed());
    assert_eq!(c3.report().and_then(|r| r.get("verdict")), Some("failure"));
    assert!(c3.report().and_then(|r| r.get("handoff_summary")).is_some());

    // Current 는 하나다.
    let open: Vec<_> = cycles.nodes().iter().filter(|c| !c.is_closed()).collect();
    assert_eq!(open.len(), 1);
    assert_eq!(open[0].id(), cycles.current_id());
}

#[test]
fn a_second_failure_may_target_the_same_ancestor_again() {
    let (mut session, dir) = three_deep("scenario-twice");
    fail_toward(&mut session, "cycle:C2");
    drop(session);

    ok(&dir, &["revisit"]);
    ok(&dir, &["open", "experiment"]); // C4

    // C4 도 실패한다 — 같은 C2 를 다시 대상으로 삼는다.
    let mut session = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");
    fail_toward(&mut session, "cycle:C2");
    drop(session);

    ok(&dir, &["revisit"]);
    let said = ok(&dir, &["open", "experiment"]); // C5
    assert!(said.contains("열었다: cycle:C5"), "{said}");
    assert!(said.contains("부모 cycle:C2"), "{said}");
    assert!(said.contains("갈래 출처: cycle:C4"), "{said}");

    // C3·C4·C5 가 모두 C2 의 자식으로 쌓인다.
    let session = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");
    let cycles = session.project().cycles();
    let target = cycles.nodes()[1].id();
    let children: Vec<String> = cycles
        .nodes()
        .iter()
        .filter(|cycle| cycle.parent() == Some(target))
        .map(|cycle| cycle.id().to_ref().to_string())
        .collect();
    assert_eq!(children, vec!["cycle:C3", "cycle:C4", "cycle:C5"]);
    // 그리고 세 시도는 **같은 세계에서** 출발했다.
    for id in [2usize, 3, 4] {
        assert_eq!(
            cycles.nodes()[id].entry_snapshot(),
            cycles.nodes()[1].exit_snapshot().unwrap(),
            "{id} 번째 시도가 다른 세계에서 출발했다"
        );
    }
}

#[test]
fn a_further_ancestor_branch_is_not_called_a_sibling() {
    // 대상이 조부모면 새 Cycle 은 실패 Cycle 의 **형제가 아니다.** 화면이 그렇게 부르면 안 된다.
    let (mut session, dir) = three_deep("scenario-grandparent");
    fail_toward(&mut session, "cycle:C1");
    drop(session);

    ok(&dir, &["revisit"]);
    let said = ok(&dir, &["open", "experiment"]);
    assert!(said.contains("부모 cycle:C1"), "{said}");
    assert!(said.contains("갈래 출처: cycle:C3"), "{said}");
    assert!(!said.contains("형제"), "형제라고 불렀다:\n{said}");

    let session = ProjectSession::open(spec(), state_in(&dir)).expect("되살린다");
    let cycles = session.project().cycles();
    let c4 = cycles.current();
    let c3 = &cycles.nodes()[2];
    assert_ne!(c4.parent(), c3.parent(), "형제가 되어 버렸다");
    assert_eq!(c4.parent(), Some(cycles.nodes()[0].id()));
    let lineage: Vec<String> = cycles
        .lineage(cycles.current_id())
        .unwrap()
        .iter()
        .map(|cycle| cycle.id().to_ref().to_string())
        .collect();
    assert_eq!(lineage, vec!["cycle:C1", "cycle:C4"], "C2 도 C3 도 계보에 없다");
}

// ── ⑩ 상태와 Context ─────────────────────────────────────────────────────

#[test]
fn pending_status_and_context_say_where_we_are_and_what_is_next() {
    let (session, dir) = pending("state");
    drop(session);

    let said = ok(&dir, &["status"]);
    assert!(said.contains("cycle:C2 에서 갈라져"), "어디서 왔는지 말하지 않는다:\n{said}");
    assert!(said.contains("gil open interview"), "다음 수를 말하지 않는다:\n{said}");
    assert!(said.contains("gil open experiment"), "{said}");

    let told = ok(&dir, &["story"]);
    assert!(told.contains("되돌아와"), "{told}");
    // 실패 Cycle 과 그 Report 는 이야기에서 사라지지 않는다.
    assert!(told.contains("Cycle 2"), "{told}");
    assert!(told.contains("다음 Cycle 이 알아야 할 것"), "{told}");

    let handed = ok(&dir, &["context"]);
    assert!(handed.contains("되돌아오며 버린 Cycle"), "버린 Cycle 절이 없다:\n{handed}");
    assert!(handed.contains("계보의 조상이 **아니다**"), "{handed}");
    assert!(handed.contains("다음 Cycle 에 넘긴 것"), "handoff 가 없다:\n{handed}");
    assert!(handed.contains("gil open"), "다음 수를 말하지 않는다:\n{handed}");
}

#[test]
fn a_branch_keeps_the_failure_in_the_handoff() {
    // 새 Cycle 을 연 뒤에도 실패 Report 는 인수인계에서 사라지지 않는다.
    let (mut session, dir) = pending("state-after");
    open_branch(&mut session, CycleKind::Experiment);
    drop(session);

    let handed = ok(&dir, &["context"]);
    assert!(handed.contains("되돌아오며 버린 Cycle"), "{handed}");
    assert!(handed.contains("Cycle 2"), "{handed}");
    assert!(handed.contains("다음 Cycle 에 넘긴 것"), "{handed}");

    let said = ok(&dir, &["status"]);
    assert!(said.contains("갈래 출처: cycle:C2"), "{said}");
    assert!(said.contains("계보의 변이 아니다"), "{said}");

    let told = ok(&dir, &["story"]);
    assert!(told.contains("Cycle 2 에서 갈라짐"), "{told}");
}

// ── ⑪ Help Topic 과 Router ───────────────────────────────────────────────

#[test]
fn the_two_topics_are_bundled_and_readable() {
    let (session, dir) = ready("topics");
    drop(session);

    let said = ok(&dir, &["help", "cycle/revisit"]);
    assert!(said.contains("gil revisit"), "{said}");
    assert!(said.contains("gil open"), "{said}");
    assert!(said.contains("조상"), "{said}");

    let said = ok(&dir, &["help", "cycle/revisit/target"]);
    assert!(said.contains("next_direction.target_cycle_ref"), "{said}");
    assert!(said.contains("cycle:C2"), "{said}");
}

#[test]
fn the_router_links_target_errors_to_the_target_topic() {
    // 실패로 닫으면서 갈 곳을 안 적으면 **그 칸 하나**의 Topic 이 붙는다.
    let dir = bare("router-target");
    write(&dir, "work.txt", "처음");
    let mut session = ProjectSession::start(spec(), state_in(&dir)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());
    walk_exit(&mut session, "failure");
    session.commit().expect("눕힌다");
    drop(session);

    let report = "verdict: failure\noutcome_ref: step:C2/S5\n\
                  handoff_summary: 다음 Cycle 이 알아야 할 것\n\
                  next_direction:\n  action: revisit\n  reason: 왜\n";
    let said = refused_with(&dir, &["close"], report);
    assert!(said.contains("cycle/revisit/target"), "{said}");
    assert!(!said.contains("cycle/experiment/close"), "Topic 이 둘 붙었다:\n{said}");
}

#[test]
fn a_target_error_without_the_field_name_still_links_the_topic() {
    // **문자열 검색으로 판정하지 않는다.** 자기 자신을 가리킨 거절의 글에는 칸 이름이
    // 나오지 않는데, 그것도 같은 Topic 으로 복구된다.
    let dir = bare("router-typed");
    write(&dir, "work.txt", "처음");
    let mut session = ProjectSession::start(spec(), state_in(&dir)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());
    walk_exit(&mut session, "failure");
    session.commit().expect("눕힌다");
    drop(session);

    let report = "verdict: failure\noutcome_ref: step:C2/S5\n\
                  handoff_summary: 다음 Cycle 이 알아야 할 것\n\
                  next_direction:\n  action: revisit\n  target_cycle_ref: cycle:C2\n  reason: 왜\n";
    let said = refused_with(&dir, &["close"], report);
    assert!(said.contains("자기 자신"), "{said}");
    assert!(
        !said.contains("next_direction.target_cycle_ref"),
        "이 글에 칸 이름이 있으면 이 시험이 문자열 검색을 못 잡는다:\n{said}"
    );
    assert!(said.contains("cycle/revisit/target"), "Topic 이 붙지 않았다:\n{said}");
}

#[test]
fn the_router_links_a_dirty_revisit_to_the_revisit_topic() {
    let (session, dir) = ready("router-dirty");
    drop(session);
    write(&dir, "work.txt", "손으로 바꿔 놓았다");

    let said = refused(&dir, &["revisit"]);
    assert!(said.contains("cycle/revisit"), "{said}");
    // 여기엔 닫을 Step 이 없다 — 그 자리의 Topic 을 붙이지 않는다.
    assert!(
        !said.contains("artifact/dirty/non-verify"),
        "남의 자리 Topic 을 붙였다:\n{said}"
    );
}

#[test]
fn a_corruption_gets_no_usage_topic() {
    // 손상·registry 누락에는 사용법 Topic 을 붙이지 않는다.
    let (session, dir) = ready("router-corrupt");
    drop(session);
    let mut file = yaml_of(&dir);
    file["cycles"]["nodes"][1]["exit_snapshot_ref"] = serde_norway::Value::from("snapshot:A9");
    fs::write(state_in(&dir), serde_norway::to_string(&file).unwrap()).unwrap();

    let said = refused(&dir, &["revisit"]);
    assert!(!said.contains("gil help"), "손상에 사용법 Topic 을 붙였다:\n{said}");
}

/// stdin 으로 Report 를 넘기며 거절을 받는다.
fn refused_with(dir: &Path, args: &[&str], report: &str) -> String {
    use std::io::Write as _;
    let mut child = Command::new(GIL)
        .args(args)
        .current_dir(dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("gil 을 부른다");
    child
        .stdin
        .as_mut()
        .expect("stdin")
        .write_all(report.as_bytes())
        .unwrap();
    let out = child.wait_with_output().expect("끝난다");
    assert!(!out.status.success(), "거절돼야 하는데 통과했다");
    String::from_utf8_lossy(&out.stderr).into_owned()
}
