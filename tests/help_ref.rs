//! 오류가 Manual 의 router 다 — **거절 하나가 복구 Topic 하나를 가리킨다.**
//!
//! ```text
//! 무엇이 거절됐는가
//! 이유
//! 지금 가능한 행동
//! 더 알아보기: gil help <topic>
//! ```
//!
//! 여기서 재는 것은 셋이다.
//!
//! ```text
//! 맞는 거절에만 붙는가          — 부정확한 링크를 붙이지 않는 것이 먼저다
//! Topic 본문을 끌고 오지 않는가
//! 링크를 고르느라 상태를 다시 읽지 않는가
//! ```

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};

use gil::{CycleKind, NodeKind, ProjectSession, RuleSet};

mod common;
use common::{bootstrap_from, full_report, spec, up_to_verify};

const GIL: &str = env!("CARGO_BIN_EXE_gil");
const MORE: &str = "더 알아보기";

// ── 연장 ───────────────────────────────────────────────────────────────────

fn rules() -> RuleSet {
    spec()
}

fn bare(label: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("gil-helpref-{label}"));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).expect("시험이 쓸 자리를 만든다");
    dir
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

fn refused(dir: &Path, args: &[&str], stdin: Option<&str>) -> String {
    let out = run(dir, args, stdin);
    assert!(
        !out.status.success(),
        "거절돼야 하는데 통과했다: gil {args:?}\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
    String::from_utf8_lossy(&out.stderr).into_owned()
}

/// 거절이 가리키는 Topic 주소 — 없으면 `None`.
///
/// **절이 하나뿐임을 여기서 함께 잰다.** 두 번 나오면 그 자체가 실패다.
fn pointed_at(said: &str) -> Option<String> {
    assert!(
        said.matches(MORE).count() <= 1,
        "`{MORE}` 가 두 번 나왔다:\n{said}"
    );
    let start = said.find(MORE)?;
    let block = &said[start..];
    let line = block
        .lines()
        .nth(1)
        .unwrap_or_default()
        .trim()
        .strip_prefix("gil help ")
        .unwrap_or_else(|| panic!("`{MORE}` 뒤에 조회 명령이 없다:\n{said}"));
    assert!(!line.contains(' '), "주소가 하나가 아니다: {line:?}");
    Some(line.to_string())
}

/// 열린 question 자리 하나를 둔 프로젝트.
fn started(label: &str, files: &[(&str, &str)]) -> PathBuf {
    let dir = bare(label);
    for (path, text) in files {
        let at = dir.join(path);
        fs::create_dir_all(at.parent().unwrap()).unwrap();
        fs::write(&at, text).unwrap();
    }
    ok(&dir, &["start"]);
    dir
}

fn open_step(dir: &Path, kind: &str) {
    let out = run(
        dir,
        &["open", kind],
        Some("objective: a\nnext_action: b\ndone_when: c\n"),
    );
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
}

/// 그 Kind 를 닫는 최소 Report 를 stdin 꼴로.
fn report_for(cycle: CycleKind, kind: NodeKind) -> String {
    let report = full_report(&rules(), cycle, kind);
    let names: Vec<String> = report.field_names().map(str::to_string).collect();
    names
        .iter()
        .map(|field| format!("{field}: {}\n", report.get(field).unwrap_or("…")))
        .collect()
}

/// Experiment 의 Verify 를 열어 둔 프로젝트.
fn at_open_verify(label: &str) -> PathBuf {
    let dir = bare(label);
    fs::write(dir.join("work.txt"), "처음").unwrap();
    let mut session =
        ProjectSession::start(rules(), dir.join(gil::STATE_PATH)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());
    up_to_verify(session.project_mut());
    session.commit().expect("눕힌다");
    dir
}

// ── ① 비-Verify dirty 거절 ────────────────────────────────────────────────

#[test]
fn a_dirty_interview_step_points_at_the_recovery_topic() {
    let dir = started("dirty-interview", &[("a.txt", "가")]);
    open_step(&dir, "question");
    fs::write(dir.join("a.txt"), "바꿨다").unwrap();

    let said = refused(
        &dir,
        &["close"],
        Some(&report_for(CycleKind::Interview, NodeKind::Question)),
    );
    assert_eq!(pointed_at(&said).as_deref(), Some("artifact/dirty/non-verify"));
    // 기존 이유와 지금 할 일이 사라지지 않았다.
    assert!(said.contains("확정할 수 없다"), "{said}");
    assert!(said.contains("`gil restore` 로 현재 변경을 되돌린 뒤"), "{said}");
    assert!(said.contains("그대로 열려 있다"), "{said}");
}

#[test]
fn a_dirty_experiment_define_points_at_the_same_topic() {
    let dir = at_open_verify("dirty-define");
    // Verify 를 닫고 analysis 로 간 뒤가 아니라, **define 이 열린 자리**를 새로 만든다.
    let dir2 = bare("dirty-define-2");
    fs::write(dir2.join("work.txt"), "처음").unwrap();
    let mut session =
        ProjectSession::start(rules(), dir2.join(gil::STATE_PATH)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());
    common::opened(session.project_mut(), NodeKind::Define);
    session.commit().expect("눕힌다");
    drop(session);
    let _ = dir;

    fs::write(dir2.join("work.txt"), "바꿨다").unwrap();
    let said = refused(
        &dir2,
        &["close"],
        Some(&report_for(CycleKind::Experiment, NodeKind::Define)),
    );
    assert_eq!(pointed_at(&said).as_deref(), Some("artifact/dirty/non-verify"));
}

#[test]
fn a_dirty_cycle_boundary_points_at_the_same_topic() {
    // **자리가 아예 없는 경계도 같은 Topic 이다.** 「비-Verify」가 부정 검색식이 아니라는
    // 뜻이다 — 자리가 없으면 비교할 Kind 도 없다.
    let dir = bare("dirty-boundary");
    fs::write(dir.join("work.txt"), "처음").unwrap();
    let mut session =
        ProjectSession::start(rules(), dir.join(gil::STATE_PATH)).expect("시작한다");

    // Experiment 를 판정까지 걸어 Cycle 을 닫을 자리에 세운다 — 세계는 그대로.
    *session.project_mut() = bootstrap_from(session.project().clone());
    up_to_verify(session.project_mut());
    session
        .close_step(full_report(&rules(), CycleKind::Experiment, NodeKind::Verify))
        .expect("Verify 를 닫는다");
    common::walked(session.project_mut(), NodeKind::Analysis);

    let outcome = common::opened(session.project_mut(), NodeKind::Outcome);
    let cycle = session.project().cycles().current();
    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", "success")
        .with("lesson", "배운 것")
        .with(common::REASON, "판정한 까닭");
    common::close_here(session.project_mut(), report).expect("판정을 닫는다");
    session.commit().expect("눕힌다");

    let at = common::step_id(session.project(), outcome);
    let close = common::cycle_report(session.project().cycles().current(), "success", at);
    drop(session);

    // 이제 열린 자리가 없다 — 그 상태에서 세계를 흔들고 Cycle 을 닫으려 한다.
    let status = ok(&dir, &["status"]);
    assert!(status.contains("아직 아무것도 열지 않았다") || status.contains("closed"), "{status}");
    fs::write(dir.join("work.txt"), "바꿨다").unwrap();

    let names: Vec<String> = close.field_names().map(str::to_string).collect();
    let stdin: String = names
        .iter()
        .map(|field| format!("{field}: {}\n", close.get(field).unwrap_or("…")))
        .collect();

    let said = refused(&dir, &["close"], Some(&stdin));
    assert!(said.contains("Cycle 을 닫는 것은 새 세계를 만들지 않는다"), "{said}");
    assert_eq!(pointed_at(&said).as_deref(), Some("artifact/dirty/non-verify"));
}

// ── ② Verify Report 계약 오류 ─────────────────────────────────────────────

#[test]
fn a_verify_report_missing_a_field_points_at_the_verify_topic() {
    for (label, report) in [
        ("verify-no-execution", "result: 관측한 것\n"),
        ("verify-no-result", "execution: 한 일\n"),
        ("verify-empty", "\n"),
        // 「잘못된 구조」 — 중첩하면 이름이 점으로 이어져 요구된 칸이 사라진다.
        ("verify-nested", "execution:\n  what: 한 일\nresult: 관측\n"),
    ] {
        let dir = at_open_verify(label);
        let said = refused(&dir, &["close"], Some(report));

        assert_eq!(
            pointed_at(&said).as_deref(),
            Some("step/verify/close"),
            "{label}: {said}"
        );
        // 기존 설명과 Report 골격이 남아 있다.
        assert!(said.contains("Report 에 다음 칸이 있어야 한다"), "{label}: {said}");
        assert!(said.contains("gil close <<'EOF'"), "{label}: {said}");
    }
}

#[test]
fn another_kinds_report_error_gets_no_topic() {
    // Analysis·Outcome 의 Report 오류를 Verify Topic 으로 뭉뚱그리지 않는다.
    let dir = started("other-report", &[("a.txt", "가")]);
    open_step(&dir, "question");
    let said = refused(&dir, &["close"], Some("question: 무엇\n"));

    assert!(said.contains("Report 에 다음 칸이 있어야 한다"), "{said}");
    assert_eq!(pointed_at(&said), None, "다른 자리의 Report 오류에 Topic 이 붙었다");
}

// ── ③ restore 사용법 오류 ─────────────────────────────────────────────────

#[test]
fn restore_with_any_argument_points_at_the_restore_topic() {
    let dir = started("restore-usage", &[("a.txt", "가")]);
    for extra in [
        vec!["restore", "snapshot:A1"],
        vec!["restore", "--force"],
        vec!["restore", "--yes"],
        vec!["restore", "extra"],
        vec!["restore", "a.txt", "b.txt"],
    ] {
        let said = refused(&dir, &extra, None);
        assert_eq!(
            pointed_at(&said).as_deref(),
            Some("artifact/restore"),
            "{extra:?}: {said}"
        );
        assert!(said.contains("받지 않는다"), "{extra:?}: {said}");
    }
}

#[test]
fn a_restore_that_fails_while_running_gets_no_usage_topic() {
    // 실행 중 실패는 사용법으로 복구되지 않는다 — 창고가 손상된 것이다.
    let dir = started("restore-broken", &[("a.txt", "가")]);
    open_step(&dir, "question");
    fs::write(dir.join("a.txt"), "바꿨다").unwrap();

    let blobs = dir.join(".gil/artifacts/blobs/sha256");
    let victim = fs::read_dir(&blobs)
        .unwrap()
        .flat_map(|shard| fs::read_dir(shard.unwrap().path()).unwrap())
        .map(|entry| entry.unwrap().path())
        .next()
        .expect("blob 이 있다");
    fs::remove_file(&victim).unwrap();

    let said = refused(&dir, &["restore"], None);
    assert!(said.contains("멈춘 단계"), "{said}");
    assert_eq!(pointed_at(&said), None, "실행 실패에 사용법 Topic 이 붙었다");
}

// ── ④ Topic 이 붙지 않아야 하는 거절들 ───────────────────────────────────

#[test]
fn a_lock_contention_gets_no_topic() {
    let dir = started("busy", &[("a.txt", "가")]);
    let lock = fs::File::options()
        .read(true)
        .write(true)
        .open(dir.join(".gil/project.lock"))
        .expect("잠금 파일을 연다");
    lock.try_lock().expect("시험이 잠금을 쥔다");

    for args in [vec!["status"], vec!["close"], vec!["restore"], vec!["help"]] {
        let said = refused(&dir, &args, None);
        assert!(said.contains("다른 GIL 명령이"), "{args:?}: {said}");
        // 「나중에 다시 실행하면 된다」가 이미 완결된 receipt 다 — 읽을 Topic 이 없다.
        assert_eq!(pointed_at(&said), None, "{args:?}: {said}");
    }
}

#[test]
fn the_refusals_that_have_no_recovery_topic_get_none() {
    // 프로젝트 없음.
    let empty = bare("no-project");
    for args in [vec!["status"], vec!["close"], vec!["restore"]] {
        let said = refused(&empty, &args, None);
        assert_eq!(pointed_at(&said), None, "{args:?}: {said}");
    }

    // 잘못된 Topic 주소와 없는 Topic.
    for bad in ["Current", "interview/approval"] {
        let said = refused(&empty, &["help", bad], None);
        assert_eq!(pointed_at(&said), None, "{bad}: {said}");
    }

    // 모르는 명령.
    let said = refused(&empty, &["없는명령"], None);
    assert_eq!(pointed_at(&said), None, "{said}");

    // 관측 실패.
    let dir = started("observe-fails", &[("a.txt", "가")]);
    open_step(&dir, "question");
    std::os::unix::fs::symlink(dir.join("a.txt"), dir.join("link")).unwrap();
    let said = refused(
        &dir,
        &["close"],
        Some(&report_for(CycleKind::Interview, NodeKind::Question)),
    );
    assert!(said.contains("심볼릭 링크"), "{said}");
    assert_eq!(pointed_at(&said), None, "관측 실패에 Topic 이 붙었다");

    // 모르는 `.gil` 내부 항목 (restore recovery 실패).
    fs::remove_file(dir.join("link")).unwrap();
    fs::create_dir_all(dir.join(".gil/restore")).unwrap();
    fs::write(dir.join(".gil/restore/누군가의파일"), "소중한 것").unwrap();
    let said = refused(&dir, &["status"], None);
    assert!(said.contains("GIL 이 만든 transaction 자료가 아니다"), "{said}");
    assert_eq!(pointed_at(&said), None, "복구 실패에 Topic 이 붙었다");
}

// ── ⑤ 표현 ────────────────────────────────────────────────────────────────

#[test]
fn the_link_is_one_line_and_never_the_topic_body() {
    let dir = started("one-line", &[("a.txt", "가")]);
    open_step(&dir, "question");
    fs::write(dir.join("a.txt"), "바꿨다").unwrap();

    let said = refused(
        &dir,
        &["close"],
        Some(&report_for(CycleKind::Interview, NodeKind::Question)),
    );

    // 절은 한 번, 주소는 하나.
    assert_eq!(said.matches(MORE).count(), 1, "{said}");
    assert_eq!(said.matches("gil help ").count(), 1, "{said}");

    // Topic 의 요약도 본문도 끌고 오지 않는다.
    let body = ok(&dir, &["help", "artifact/dirty/non-verify"]);
    let summary = body.lines().nth(1).expect("요약");
    assert!(!said.contains(summary), "요약을 함께 붙였다:\n{said}");
    for section in ["[언제 읽는가]", "[지금 할 일]", "[불변식]", "[흔한 실패]"] {
        assert!(!said.contains(section), "본문을 붙였다: {section}");
    }
    // 다른 후보를 늘어놓지도 않는다.
    for other in ["step/verify/close", "artifact/restore", "current"] {
        assert!(!said.contains(other), "여러 후보를 냈다: {other}");
    }
    // 내부 enum 이름도 error code 도 없다.
    for internal in ["SessionError", "GrammarError", "ActionError", "Dirty {"] {
        assert!(!said.contains(internal), "내부 이름이 샜다: {internal}");
    }
}

#[test]
fn a_refusal_without_a_topic_has_no_empty_section() {
    let empty = bare("no-empty-block");
    let said = refused(&empty, &["status"], None);
    assert!(!said.contains(MORE), "빈 절을 만들었다:\n{said}");
    assert!(!said.contains("gil help"), "{said}");
}

// ── ⑥ 링크를 고르느라 무언가를 더 하지 않는다 ────────────────────────────

#[test]
fn choosing_the_link_reads_and_locks_nothing_more() {
    let dir = started("read-only", &[("a.txt", "가")]);
    open_step(&dir, "question");
    fs::write(dir.join("a.txt"), "바꿨다").unwrap();

    let before = snapshot_of(&dir);
    let objects = (count(&dir, "blobs"), count(&dir, "manifests"));

    let said = refused(
        &dir,
        &["close"],
        Some(&report_for(CycleKind::Interview, NodeKind::Question)),
    );
    assert!(said.contains(MORE), "링크가 붙지 않아 이 시험이 잴 것이 없다");

    // **오류가 이미 보장하던 무변경성이 그대로다.**
    assert_eq!(snapshot_of(&dir), before, "링크를 고르며 무언가를 바꿨다");
    assert_eq!(count(&dir, "blobs"), objects.0, "blob 이 늘었다");
    assert_eq!(count(&dir, "manifests"), objects.1, "manifest 가 늘었다");
    assert!(!dir.join(".gil/restore").exists());

    // 그리고 잠금은 명령이 끝나며 풀렸다 — 링크가 새로 잡지 않았다.
    ok(&dir, &["status"]);
}

fn count(root: &Path, kind: &str) -> usize {
    let at = root.join(".gil/artifacts").join(kind).join("sha256");
    fs::read_dir(&at)
        .map(|shards| {
            shards
                .map(|shard| fs::read_dir(shard.unwrap().path()).unwrap().count())
                .sum()
        })
        .unwrap_or(0)
}

fn snapshot_of(root: &Path) -> BTreeMap<String, Vec<u8>> {
    let mut out = BTreeMap::new();
    walk(root, root, &mut out);
    out
}

fn walk(root: &Path, at: &Path, out: &mut BTreeMap<String, Vec<u8>>) {
    for entry in fs::read_dir(at).expect("들여다본다") {
        let entry = entry.expect("한 자리");
        let path = entry.path();
        match entry.file_type().expect("종류").is_dir() {
            true => walk(root, &path, out),
            false if path.ends_with("project.lock") => {}
            false => {
                let key = path.strip_prefix(root).unwrap().to_string_lossy().into_owned();
                out.insert(key, fs::read(&path).expect("읽는다"));
            }
        }
    }
}

#[test]
fn the_dirty_refusal_does_not_observe_the_project_twice() {
    // 링크를 고르려고 `world_state()` 를 다시 부르지 않는다 — gate 에 이미 실려 있다.
    //
    // 관측기는 `world_state()` 한 번마다 두 번 훑는다(안정된 관측). dirty close 한 번이
    // 정확히 그 한 벌이어야 한다.
    let dir = bare("observe-once");
    fs::write(dir.join("a.txt"), "가").unwrap();
    let mut session =
        ProjectSession::start(rules(), dir.join(gil::STATE_PATH)).expect("시작한다");
    session
        .open_action_step(NodeKind::Question, common::plan(NodeKind::Question))
        .expect("연다");
    session.commit().expect("눕힌다");

    fs::write(dir.join("a.txt"), "바꿨다").unwrap();
    let err = session
        .close_step(full_report(&rules(), CycleKind::Interview, NodeKind::Question))
        .expect_err("바뀐 세계 위에서 닫혔다");

    // 링크를 고르는 것은 순수하다 — 여기서 관측이 더 일어나면 아래가 달라진다.
    let once = gil::more_about(&gil::Refusal::Session(&err), &err.to_string());
    let twice = gil::more_about(&gil::Refusal::Session(&err), &err.to_string());
    assert_eq!(once, twice, "같은 오류가 부를 때마다 다른 답을 냈다");
    assert_eq!(
        once.as_deref(),
        Some("\n더 알아보기\n  gil help artifact/dirty/non-verify\n")
    );
}

#[test]
fn the_existing_help_commands_still_work() {
    let dir = started("help-unchanged", &[("a.txt", "가")]);
    // 정확 조회.
    assert!(ok(&dir, &["help", "artifact/restore"]).contains("[불변식]"));
    // 상태 기반 조회.
    assert!(ok(&dir, &["help"]).contains("현재 상태에 관련된 도움말"));
    // 정적 도움말.
    assert!(ok(&dir, &["--help"]).contains("gil open"));
    // 자리별 도움말.
    assert!(ok(&dir, &["close", "--help"]).contains("지금은 닫을 자리가 아니다"));
}

// ── ⑦ dogfood 에서 실제로 난 마찰 두 가지 ────────────────────────────────
//
// 오류 문자열만 보지 않는다. **공개 CLI 로 거절부터 복구까지** 걸어 본다 — Topic 이
// 가리켜졌다는 것만으로는 그 Topic 을 읽고 실제로 빠져나올 수 있는지 알 수 없다.

/// Verify 를 닫아 Analysis 앞에 선 프로젝트.
fn after_verify(label: &str) -> PathBuf {
    let dir = bare(label);
    fs::write(dir.join("work.txt"), "처음").unwrap();
    let mut session =
        ProjectSession::start(rules(), dir.join(gil::STATE_PATH)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());
    up_to_verify(session.project_mut());
    session
        .close_step(full_report(&rules(), CycleKind::Experiment, NodeKind::Verify))
        .expect("Verify 를 닫는다");
    session.commit().expect("눕힌다");
    dir
}

#[test]
fn opening_a_step_without_a_contract_points_at_the_contract_topic() {
    // dogfood 마찰 ①: Verify 를 닫은 뒤 `gil open analysis` 를 계약 없이 불렀다.
    for kind in ["analysis", "outcome"] {
        let dir = after_verify(&format!("contract-{kind}"));
        if kind == "outcome" {
            // Outcome 앞에 서려면 Analysis 를 먼저 닫는다.
            let out = run(
                &dir,
                &["open", "analysis"],
                Some("objective: a\nnext_action: b\ndone_when: c\n"),
            );
            assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
            let out = run(
                &dir,
                &["close"],
                Some(&report_for(CycleKind::Experiment, NodeKind::Analysis)),
            );
            assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
        }

        // 계약 없이 연다 — 거절되고 Topic 을 가리킨다.
        let said = refused(&dir, &["open", kind], Some(""));
        assert_eq!(
            pointed_at(&said).as_deref(),
            Some("action/open-contract"),
            "{kind}: {said}"
        );
        assert!(said.contains("무엇을 하려는지 적지 않았다"), "{kind}: {said}");

        // Topic 을 읽고 — 세 칸을 적어 다시 연다.
        let topic = ok(&dir, &["help", "action/open-contract"]);
        assert!(topic.contains("objective"), "{topic}");
        let out = run(
            &dir,
            &["open", kind],
            Some(
                "objective: 관측을 가설과 맞춰 읽는다\n\
                 next_action: 수정 전후의 실패 목록을 견준다\n\
                 done_when: 어느 가정이 맞고 틀렸는지 문장으로 적을 수 있다\n",
            ),
        );
        assert!(
            out.status.success(),
            "{kind}: Topic 을 읽고도 열리지 않았다:\n{}",
            String::from_utf8_lossy(&out.stderr)
        );
        // **원래 상태를 잃지 않았다.**
        assert!(ok(&dir, &["status"]).contains(kind), "{kind}");
    }
}

#[test]
fn an_open_that_fails_for_another_reason_gets_no_contract_topic() {
    // **모든 open 오류가 계약 오류는 아니다.** 여기서 읽어야 할 것은 「계약을 어떻게
    // 적는가」가 아니라 「지금 여기서 무엇을 열 수 있는가」다.
    let dir = after_verify("open-wrong-kind");
    let contract = "objective: a\nnext_action: b\ndone_when: c\n";

    // 지금 자리에서 열 수 없는 Kind — 전이 오류다.
    let said = refused(&dir, &["open", "define"], Some(contract));
    assert_eq!(pointed_at(&said), None, "전이 오류에 계약 Topic 이 붙었다:\n{said}");

    // 모르는 이름 — 계약을 읽기도 전에 거절된다.
    let said = refused(&dir, &["open", "없는종류"], Some(contract));
    assert_eq!(pointed_at(&said), None, "{said}");

    // 이미 열린 자리 위에서 또 열려는 것도 계약 문제가 아니다.
    let out = run(&dir, &["open", "analysis"], Some(contract));
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    let said = refused(&dir, &["open", "outcome"], Some(contract));
    assert_eq!(pointed_at(&said), None, "{said}");
}

#[test]
fn a_report_that_does_not_parse_gets_no_topic() {
    // **대상을 typed 하게 말하지 못하는 parser 오류**에는 무리하게 연결하지 않는다.
    // 여기서는 아직 계약인지 아닌지조차 모른다 — 이름과 값으로 갈리지도 않았다.
    let dir = after_verify("open-bad-report");
    for broken in [
        "이건 이름과 값이 아니다\n",
        "objective: a\n  갑자기 들여쓴 줄\n",
    ] {
        let said = refused(&dir, &["open", "analysis"], Some(broken));
        assert_eq!(pointed_at(&said), None, "{broken:?}: {said}");
    }
}

#[test]
fn a_verify_report_field_is_empty_not_just_missing() {
    // 「누락」과 「빈 값」이 같은 계약 오류다 — 셋 중 하나만 비워도 같은 Topic 이다.
    for blank in [
        "objective:  \nnext_action: b\ndone_when: c\n",
        "objective: a\nnext_action:  \ndone_when: c\n",
        "objective: a\nnext_action: b\ndone_when:  \n",
    ] {
        let dir = after_verify("contract-blank");
        let said = refused(&dir, &["open", "analysis"], Some(blank));
        assert_eq!(
            pointed_at(&said).as_deref(),
            Some("action/open-contract"),
            "{blank:?}: {said}"
        );
    }
}

#[test]
fn closing_the_experiment_cycle_without_a_report_points_at_its_topic() {
    // dogfood 마찰 ②: 마지막 Outcome 을 닫은 뒤 Cycle Report 없이 `gil close`.
    let dir = bare("cycle-report");
    fs::write(dir.join("work.txt"), "처음").unwrap();
    let mut session =
        ProjectSession::start(rules(), dir.join(gil::STATE_PATH)).expect("시작한다");
    *session.project_mut() = bootstrap_from(session.project().clone());
    up_to_verify(session.project_mut());
    session
        .close_step(full_report(&rules(), CycleKind::Experiment, NodeKind::Verify))
        .expect("Verify 를 닫는다");
    common::walked(session.project_mut(), NodeKind::Analysis);
    let outcome = common::opened(session.project_mut(), NodeKind::Outcome);
    let cycle = session.project().cycles().current();
    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", "success")
        .with("lesson", "배운 것")
        .with(common::REASON, "판정한 까닭");
    common::close_here(session.project_mut(), report).expect("판정을 닫는다");
    let last = session
        .project()
        .cycles()
        .current()
        .step_ref(common::step_id(session.project(), outcome));
    session.commit().expect("눕힌다");
    drop(session);

    // Cycle Report 없이 닫으려 한다.
    let said = refused(&dir, &["close"], Some(""));
    assert_eq!(pointed_at(&said).as_deref(), Some("cycle/experiment/close"), "{said}");

    // Topic 을 읽고 — 유효한 Report 로 실제로 닫는다.
    let topic = ok(&dir, &["help", "cycle/experiment/close"]);
    assert!(topic.contains("outcome_ref"), "{topic}");
    assert!(topic.contains("open_child"), "{topic}");
    let out = run(
        &dir,
        &["close"],
        Some(&format!(
            "verdict: success\n\
             outcome_ref: {last}\n\
             handoff_summary: 무효한 값이 다음 우선순위로 물러난다\n\
             next_direction.action: open_child\n\
             next_direction.reason: 검증이 끝나 다음 실험으로 넘어간다\n"
        )),
    );
    assert!(
        out.status.success(),
        "Topic 을 읽고도 닫히지 않았다:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let status = ok(&dir, &["status"]);
    assert!(status.contains("닫힘 · success"), "{status}");
}

#[test]
fn an_interview_cycle_report_error_gets_no_experiment_topic() {
    // 두 Cycle 은 요구하는 칸도 허용값도 다르다 — 한 Topic 으로 뭉뚱그리지 않는다.
    let dir = started("interview-cycle-report", &[("a.txt", "가")]);
    for kind in ["question", "interpretation", "synthesis"] {
        open_step(&dir, kind);
        let mut report = full_report(&rules(), CycleKind::Interview, NodeKind::parse(kind).unwrap());
        if kind == "synthesis" {
            report.insert("approved", "yes");
            report.insert("basis_refs", "step:C1/S1\nstep:C1/S2");
        }
        let names: Vec<String> = report.field_names().map(str::to_string).collect();
        let stdin: String = names
            .iter()
            .map(|f| match report.get(f).unwrap_or("…").contains('\n') {
                true => format!("{f}: |\n  step:C1/S1\n  step:C1/S2\n"),
                false => format!("{f}: {}\n", report.get(f).unwrap_or("…")),
            })
            .collect();
        let out = run(&dir, &["close"], Some(&stdin));
        assert!(out.status.success(), "{kind}: {}", String::from_utf8_lossy(&out.stderr));
    }
    open_step(&dir, "outcome");
    let out = run(
        &dir,
        &["close"],
        Some(
            "verdict: success\nlesson: 승인됐다\nsynthesis_ref: step:C1/S3\n\
             next_direction.action: close_cycle\nnext_direction.reason: 실험으로 간다\n",
        ),
    );
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));

    // 이제 Interview Cycle 을 Report 없이 닫으려 한다 — **Topic 이 붙지 않는다.**
    let said = refused(&dir, &["close"], Some(""));
    assert!(said.contains("Report 에 다음 칸이 있어야 한다"), "{said}");
    assert_eq!(pointed_at(&said), None, "Interview 에 Experiment Topic 이 붙었다");
}
