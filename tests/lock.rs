//! 프로젝트 트랜잭션 잠금을 **진짜 프로세스로** 잰다.
//!
//! 한 프로세스 안의 두 handle 로는 부족하다. 운영체제의 advisory lock 이 지키는 것은
//! 프로세스 경계이고, 이 잠금의 뜻 전부 — 죽으면 풀린다, 남은 파일은 잠금이 아니다 —
//! 는 그 경계 위에서만 확인된다.
//!
//! # 자식을 어떻게 세워 두는가
//!
//! `sleep` 과 운에 기대지 않는다. 이 시험 바이너리가 **스스로를 다시 부른다**:
//!
//! ```text
//! 부모: 자식을 띄운다 (환경변수로 「잠금을 쥐고 있어라」)
//! 자식: 잠금을 잡는다 → stdout 에 HELD → stdin 을 기다린다
//! 부모: HELD 를 읽는다              ← 여기서부터 잠금은 확실히 잡혀 있다
//! 부모: 경쟁 명령을 돌린다
//! 부모: 자식의 stdin 을 닫거나 죽인다
//! ```
//!
//! 자식이 잡는 것은 GIL 의 타입이 아니라 **그 파일에 건 OS 잠금**이다. 그래서 이 시험은
//! 우리 타입이 아니라 계약 자체를 잰다 — 구현을 바꿔도 이 시험은 같은 것을 묻는다.

use std::fs::{self, File};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdout, Command, Output, Stdio};

mod common;
use common::scratch;

const GIL: &str = env!("CARGO_BIN_EXE_gil");

/// 이 값이 있으면 아래 `holds_the_lock_for_its_parent` 가 실제로 실행된다.
const HOLD: &str = "GIL_TEST_HOLD_LOCK";
/// 자식이 「잡았다」고 알리는 한 줄.
const HELD: &str = "HELD";

const LOCK: &str = ".gil/project.lock";

// ── 자식 쪽 ────────────────────────────────────────────────────────────────

/// **부모가 부를 때만 실행된다.** 평소에는 아무것도 하지 않고 지나간다.
///
/// 잠금을 잡고 `HELD` 를 내보낸 뒤 stdin 이 올 때까지 붙잡고 있는다. 한 줄이 오거나
/// stdin 이 닫히면 정상 종료한다.
#[test]
fn holds_the_lock_for_its_parent() {
    let Ok(path) = std::env::var(HOLD) else {
        return;
    };
    let file = File::options()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(&path)
        .expect("자식이 잠금 파일을 연다");
    file.try_lock().expect("자식이 잠금을 잡는다");

    println!("{HELD}");
    std::io::stdout().flush().expect("신호를 흘려보낸다");

    let mut line = String::new();
    let _ = std::io::stdin().read_line(&mut line);
    // 잠금은 여기서 `file` 이 떨어지며 풀린다 — 죽여도 운영체제가 푼다.
}

// ── 부모 쪽 연장 ───────────────────────────────────────────────────────────

/// 잠금을 쥔 자식. **떨어질 때 반드시 거둔다.**
struct Holder {
    child: Option<Child>,
    /// 자식의 stdout 을 **계속 열어 둔다.** 여기서 닫으면 자식이 제 마무리 출력을 쓰다가
    /// 파이프가 끊겨 죽는다 — 정상 종료를 재려는 시험이 정상 종료를 못 만들게 된다.
    _out: BufReader<ChildStdout>,
}

impl Holder {
    /// 자식을 띄우고 **잠금을 실제로 잡을 때까지** 기다린다.
    fn take(lock: &Path) -> Holder {
        let mut child = Command::new(std::env::current_exe().expect("이 시험 바이너리의 자리"))
            .args(["--exact", "holds_the_lock_for_its_parent", "--nocapture"])
            .env(HOLD, lock)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .expect("자식을 띄운다");

        let out = child.stdout.take().expect("stdout 을 열어 뒀다");
        let mut out = BufReader::new(out);
        // libtest 가 먼저 제 말을 흘린다. 우리가 기다리는 것은 한 줄뿐이다.
        let mut held = false;
        let mut line = String::new();
        while out.read_line(&mut line).unwrap_or(0) > 0 {
            if line.trim() == HELD {
                held = true;
                break;
            }
            line.clear();
        }
        assert!(held, "자식이 잠금을 잡았다고 말하지 않았다");

        Holder {
            child: Some(child),
            _out: out,
        }
    }

    /// 정상적으로 놓게 한다 — stdin 을 닫으면 자식이 끝난다.
    fn let_go(mut self) {
        let mut child = self.child.take().expect("아직 살아 있다");
        drop(child.stdin.take());
        let status = child.wait().expect("자식을 거둔다");
        assert!(status.success(), "자식이 곱게 끝나지 않았다");
    }

    /// 비정상 종료시킨다 — **이 시험이 띄운 자식만** 대상이다.
    fn kill(mut self) {
        let mut child = self.child.take().expect("아직 살아 있다");
        child.kill().expect("자식을 죽인다");
        let _ = child.wait();
    }
}

impl Drop for Holder {
    fn drop(&mut self) {
        // 시험이 중간에 실패해도 자식을 남기지 않는다.
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

fn run(dir: &Path, args: &[&str]) -> Output {
    run_with(dir, args, None)
}

fn run_with(dir: &Path, args: &[&str], stdin: Option<&str>) -> Output {
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
        child
            .stdin
            .as_mut()
            .expect("stdin 을 열어 뒀다")
            .write_all(text.as_bytes())
            .expect("계약을 넘긴다");
    }
    child.wait_with_output().expect("gil 이 끝나기를 기다린다")
}

/// 실행형 자리를 여는 **최소 행동 계약** — 여기 한 자리에만 적는다.
const CONTRACT: &str = "objective: 사용자의 의도를 확인한다\n\
                        next_action: 선택지와 함께 질문을 건넨다\n\
                        done_when: 사용자의 원문 응답을 얻는다\n";

/// 계약을 넘겨 실행형 자리를 연다.
fn open_action(dir: &Path, kind: &str) {
    let out = run_with(dir, &["open", kind], Some(CONTRACT));
    assert!(
        out.status.success(),
        "gil open {kind} 가 실패했다:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
}

fn ok(dir: &Path, args: &[&str]) -> String {
    let out = run(dir, args);
    assert!(
        out.status.success(),
        "gil {args:?} 가 실패했다:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    String::from_utf8_lossy(&out.stdout).into_owned()
}

fn refused(dir: &Path, args: &[&str]) -> String {
    let out = run(dir, args);
    assert!(
        !out.status.success(),
        "거절돼야 하는데 통과했다: gil {args:?}\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
    String::from_utf8_lossy(&out.stderr).into_owned()
}

/// 이 말이 경쟁 때문에 물러선 것인가 — **그리고 아무것도 건드리지 않았다고 말하는가.**
fn is_contention(said: &str) -> bool {
    said.contains("다른 GIL 명령이 이 프로젝트를 사용하고 있다")
        && said.contains("읽거나 변경하지 않았다")
        && said.contains("다시 시도한다")
}

/// 시작해 둔 프로젝트 하나.
fn started(label: &str) -> PathBuf {
    let dir = scratch(label);
    ok(&dir, &["start"]);
    dir
}

/// 프로젝트 안 모든 파일의 경로와 바이트 — **무엇도 바뀌지 않았음을 재기 위해.**
fn snapshot(dir: &Path) -> Vec<(PathBuf, Vec<u8>)> {
    let mut out = Vec::new();
    walk(dir, &mut out);
    out.sort_by(|a, b| a.0.cmp(&b.0));
    out
}

fn walk(at: &Path, out: &mut Vec<(PathBuf, Vec<u8>)>) {
    for entry in fs::read_dir(at).expect("들여다본다") {
        let entry = entry.expect("한 자리");
        let path = entry.path();
        match entry.file_type().expect("종류").is_dir() {
            true => walk(&path, out),
            // 잠금 파일 자체는 뺀다 — 그 파일의 OS metadata 는 잠금의 부산물이지
            // 프로젝트의 상태가 아니다. 내용이 비었는지는 따로 잰다.
            false if path.ends_with("project.lock") => {}
            false => out.push((path.clone(), fs::read(&path).expect("읽는다"))),
        }
    }
}

/// 상태를 읽는 CLI 경로 전부 — **하나라도 빠지면 그 길로 동시 실행이 샌다.**
const STATE_COMMANDS: &[&[&str]] = &[
    &["status"],
    &["story"],
    &["context"],
    &["open"],
    &["open", "question"],
    &["close"],
    &["revisit"],
    &["cycle", "open"],
    &["cycle", "close"],
    &["open", "--help"],
    &["close", "--help"],
];

// ── 잠금의 뜻 ──────────────────────────────────────────────────────────────

#[test]
fn a_started_project_carries_a_lock_file() {
    let dir = started("lock-file");
    assert!(dir.join(LOCK).exists(), "시작하고도 잠금 자리가 없다");
    // 정상 코드가 매번 만들고 지우며 경쟁하지 않는다 — 파일은 그냥 남는다.
    ok(&dir, &["status"]);
    assert!(dir.join(LOCK).exists());
}

#[test]
fn a_leftover_lock_file_blocks_nobody() {
    // 파일의 존재는 잠금 상태가 아니다. 사람이 손으로 지울 stale lock 을 만들지 않는다.
    let dir = started("leftover");
    fs::write(dir.join(LOCK), b"").expect("잔해를 남긴다");
    ok(&dir, &["status"]);
}

#[test]
fn a_second_process_is_refused_while_one_holds_it() {
    let dir = started("held");
    let holder = Holder::take(&dir.join(LOCK));

    let said = refused(&dir, &["status"]);
    assert!(is_contention(&said), "{said}");

    holder.let_go();
}

#[test]
fn letting_go_lets_the_next_one_in() {
    let dir = started("release");
    let holder = Holder::take(&dir.join(LOCK));
    assert!(is_contention(&refused(&dir, &["status"])));

    holder.let_go();
    ok(&dir, &["status"]);
}

#[test]
fn a_holder_that_is_killed_releases_it() {
    // 비정상 종료여도 **운영체제가 푼다.** 그래서 잔해를 치우는 명령이 필요 없다.
    let dir = started("killed");
    let holder = Holder::take(&dir.join(LOCK));
    assert!(is_contention(&refused(&dir, &["status"])));

    holder.kill();
    ok(&dir, &["status"]);
}

// ── 경쟁했을 때 무엇을 하지 않는가 ─────────────────────────────────────────

#[test]
fn contention_happens_before_the_state_is_read() {
    // state.yaml 을 읽을 수 없게 만들어 둔다. **잠금이 먼저**라면 그 사실을 모른 채
    // 경쟁으로 물러서야 한다. 파싱 오류가 나오면 순서가 뒤집힌 것이다.
    let dir = started("before-read");
    let holder = Holder::take(&dir.join(LOCK));
    fs::write(dir.join(".gil/state.yaml"), "{{{ 이건 YAML 이 아니다".as_bytes()).unwrap();

    let said = refused(&dir, &["status"]);
    assert!(is_contention(&said), "state 를 먼저 읽었다:\n{said}");

    holder.let_go();
}

#[test]
fn contention_changes_nothing_in_the_project() {
    let dir = started("unchanged");
    fs::write(dir.join("작업물.txt"), "사람의 파일".as_bytes()).unwrap();
    let holder = Holder::take(&dir.join(LOCK));

    let before = snapshot(&dir);
    for args in STATE_COMMANDS {
        assert!(
            is_contention(&refused(&dir, args)),
            "gil {args:?} 가 경쟁이 아닌 이유로 실패했다"
        );
    }
    // 창고는 `gil start` 가 이미 만들었다. 여기서 재는 것은 **경쟁이 그 안에 무엇도
    // 더하지 않았는가**다 — snapshot 이 `.gil/artifacts` 아래까지 바이트로 훑는다.
    assert_eq!(snapshot(&dir), before, "경쟁하고도 무언가를 바꿨다");

    holder.let_go();
}

#[test]
fn every_state_reading_command_goes_through_the_same_lock() {
    // 하나라도 빠지면 그 길로 동시 실행이 샌다.
    let dir = started("all-commands");
    let holder = Holder::take(&dir.join(LOCK));

    for args in STATE_COMMANDS {
        let said = refused(&dir, args);
        assert!(is_contention(&said), "gil {args:?} 가 잠금을 지나지 않았다:\n{said}");
    }

    holder.let_go();
}

#[test]
fn state_sensitive_help_takes_the_lock_too() {
    // `--help` 이지만 지금 자리의 계약을 말하려면 state 를 읽어야 한다.
    let dir = started("help-locks");
    let holder = Holder::take(&dir.join(LOCK));

    for args in [["open", "--help"], ["close", "--help"]] {
        assert!(is_contention(&refused(&dir, &args)), "gil {args:?}");
    }

    holder.let_go();
}

#[test]
fn the_version_and_the_static_help_need_no_project_lock() {
    // 프로젝트를 찾지도 읽지도 않는 것은 잠금과 무관하다.
    let dir = started("no-lock-needed");
    let holder = Holder::take(&dir.join(LOCK));

    assert!(ok(&dir, &["--version"]).contains("gil"));
    assert!(ok(&dir, &["--help"]).contains("gil"));
    assert!(ok(&dir, &["-V"]).contains("gil"));

    holder.let_go();
}

// ── start bootstrap ────────────────────────────────────────────────────────

#[test]
fn a_start_is_refused_while_someone_holds_the_place() {
    let dir = scratch("start-held");
    fs::create_dir_all(dir.join(".gil")).unwrap();
    let holder = Holder::take(&dir.join(LOCK));

    let said = refused(&dir, &["start"]);
    assert!(is_contention(&said), "{said}");
    assert!(!dir.join(".gil/state.yaml").exists(), "경쟁하며 초기화했다");

    holder.let_go();
    ok(&dir, &["start"]);
}

#[test]
fn many_starts_at_once_leave_exactly_one_project() {
    // 누가 이기든 상관없다. **둘이 각각 다른 최초 상태를 세우지 않는 것**이 규칙이다.
    let dir = scratch("start-race");
    let children: Vec<Child> = (0..6)
        .map(|_| {
            Command::new(GIL)
                .arg("start")
                .current_dir(&dir)
                .stdin(Stdio::null())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()
                .expect("gil start 를 띄운다")
        })
        .collect();

    let won = children
        .into_iter()
        .filter(|_| true)
        .map(|child| child.wait_with_output().expect("거둔다"))
        .filter(|out| out.status.success())
        .count();

    assert_eq!(won, 1, "{won} 개의 gil start 가 성공했다");
    // 세워진 것 하나가 온전하다.
    ok(&dir, &["status"]);
}

#[test]
fn a_lock_file_left_by_a_failed_start_is_not_damage() {
    let dir = scratch("start-leftover");
    fs::create_dir_all(dir.join(".gil")).unwrap();
    fs::write(dir.join(LOCK), b"").unwrap();

    // 잠금 파일의 존재는 초기화 완료도 잠금 보유도 뜻하지 않는다.
    ok(&dir, &["start"]);
}

#[test]
fn a_start_refuses_to_step_on_something_it_does_not_know() {
    let dir = scratch("start-stranger");
    fs::create_dir_all(dir.join(".gil")).unwrap();
    fs::write(dir.join(".gil/누군가의노트.md"), "소중한 것".as_bytes()).unwrap();

    let said = refused(&dir, &["start"]);
    assert!(said.contains("모르는 것"), "{said}");
    assert_eq!(
        fs::read(dir.join(".gil/누군가의노트.md")).unwrap(),
        "소중한 것".as_bytes(),
        "남의 파일을 건드렸다"
    );
    assert!(!dir.join(".gil/state.yaml").exists());
}

// ── 잃어버리는 변경이 없다 ─────────────────────────────────────────────────

#[test]
fn a_blocked_writer_leaves_no_half_written_change() {
    let dir = started("no-lost-update");
    let holder = Holder::take(&dir.join(LOCK));

    // 잠긴 동안의 쓰기 명령은 아무것도 남기지 않는다.
    assert!(is_contention(&refused(&dir, &["open", "question"])));
    holder.let_go();

    // 풀린 뒤 한 번 연다 — 열린 자리는 **하나**여야 한다.
    open_action(&dir, "question");
    let state = fs::read_to_string(dir.join(".gil/state.yaml")).unwrap();
    assert_eq!(
        state.matches("kind: question").count(),
        1,
        "막힌 쓰기가 자리를 남겼다:\n{state}"
    );
    assert_eq!(state.matches("id: W").count(), 1, "Will 이 두 번 발급됐다:\n{state}");
    assert!(state.contains("next_will_id: 2"), "Will 발급기가 어긋났다:\n{state}");
}

#[test]
fn an_error_inside_the_command_still_releases_the_lock() {
    // 오류로 나가는 길에서도 guard 가 떨어져야 다음 명령이 들어온다.
    let dir = started("error-path");
    refused(&dir, &["close"]); // 닫을 것이 없다
    refused(&dir, &["revisit"]); // 되돌아갈 자리가 없다
    refused(&dir, &["없는명령"]);

    ok(&dir, &["status"]);
    open_action(&dir, "question");
}

#[test]
fn one_project_lock_does_not_reach_another_project() {
    let one = started("neighbour-one");
    let two = started("neighbour-two");
    let holder = Holder::take(&one.join(LOCK));

    assert!(is_contention(&refused(&one, &["status"])));
    ok(&two, &["status"]);

    holder.let_go();
}
