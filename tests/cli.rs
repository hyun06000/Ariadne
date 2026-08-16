//! `gil` 을 **프로세스로** 부른다.
//!
//! 여기서만 잴 수 있는 것이 하나 있다: **한 턴에 열고 다음 턴에 닫는 것.**
//! Agent 의 한 턴은 한 프로세스라, 라이브러리 시험은 이 경계를 못 넘어 본다.

use std::io::Write;
use std::path::Path;
use std::process::{Command, Output, Stdio};

mod common;
use common::scratch;

const GIL: &str = env!("CARGO_BIN_EXE_gil");

fn run(dir: &Path, args: &[&str], stdin: Option<&str>) -> Output {
    let mut child = Command::new(GIL)
        .args(args)
        .current_dir(dir)
        .stdin(match stdin {
            Some(_) => Stdio::piped(),
            // 아무것도 안 주면 빈 입력을 준다 — 터미널이 아니어야 close 가 기다리지 않는다.
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
            .expect("Report 를 넘긴다");
    }
    child.wait_with_output().expect("gil 이 끝나기를 기다린다")
}

fn ok(dir: &Path, args: &[&str], stdin: Option<&str>) -> String {
    let out = run(dir, args, stdin);
    assert!(
        out.status.success(),
        "gil {args:?} 가 실패했다:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    String::from_utf8(out.stdout).expect("사람이 읽는 글이어야 한다")
}

fn refused(dir: &Path, args: &[&str], stdin: Option<&str>) -> String {
    let out = run(dir, args, stdin);
    assert!(
        !out.status.success(),
        "거절돼야 하는데 통과했다: gil {args:?}\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
    let text = String::from_utf8(out.stderr).expect("사람이 읽는 글이어야 한다");
    assert!(!text.trim().is_empty(), "거절하면서 이유를 말하지 않았다");
    text
}

const DEFINE: &str = "problem: 이야기가 설명 없이 읽히는가\nsuccess_condition: 여덟 물음에 답하면 풀린 것이다\n";
const HYPOTHESIS: &str = "hypothesis: 칸을 늘어놓으면 읽힌다\nrationale: 데이터는 이미 다 있다\nguardrail: 내부 낱말이 새면 실패\n";

#[test]
fn a_step_opened_in_one_process_is_closed_in_the_next() {
    // 저장이 없으면 이 시험은 원리적으로 통과할 수 없다 — 여는 프로세스와 닫는 프로세스가
    // 다르기 때문이다. dogfooding 을 막고 있던 것이 정확히 이것이다.
    let dir = scratch("cli-across-processes");
    ok(&dir, &["start"], None);
    ok(&dir, &["open", "define"], None);

    let closed = ok(&dir, &["close"], Some(DEFINE));
    assert!(closed.contains("closed"), "다른 프로세스에서 닫히지 않았다:\n{closed}");

    let told = ok(&dir, &["story"], None);
    assert!(
        told.contains("이야기가 설명 없이 읽히는가"),
        "앞 프로세스가 적은 것이 이야기에 없다:\n{told}"
    );
}

#[test]
fn the_walk_lies_where_the_command_says_it_does() {
    let dir = scratch("cli-path");
    let said = ok(&dir, &["start"], None);
    assert!(
        said.contains(gil::WALK_PATH),
        "어디에 눕혔는지 말하지 않는다:\n{said}"
    );
    assert!(dir.join(gil::WALK_PATH).exists(), "말한 자리에 파일이 없다");
}

#[test]
fn starting_twice_does_not_wipe_what_was_written() {
    // 적힌 사고를 조용히 지우지 않는다. 지우는 것은 사람의 판단이다.
    let dir = scratch("cli-restart");
    ok(&dir, &["start"], None);
    ok(&dir, &["open", "define"], None);
    ok(&dir, &["close"], Some(DEFINE));

    refused(&dir, &["start"], None);

    let told = ok(&dir, &["story"], None);
    assert!(told.contains("이야기가 설명 없이 읽히는가"), "적은 것이 사라졌다");
}

#[test]
fn there_is_nothing_to_read_before_there_is_a_walk() {
    // 아직 시작하지 않은 것과 망가진 것은 다르다 — 그리고 무엇을 하면 되는지 말해야 한다.
    let dir = scratch("cli-nothing");
    let said = refused(&dir, &["status"], None);
    assert!(
        said.contains("gil start"),
        "다음 수를 가리키지 않는다:\n{said}"
    );
}

#[test]
fn a_refusal_from_the_grammar_arrives_word_for_word() {
    // 거절의 이유를 이 표면이 다시 쓰지 않는다 — 같은 판정이 두 얼굴로 도착하지 않게.
    let dir = scratch("cli-grammar");
    ok(&dir, &["start"], None);
    let said = refused(&dir, &["open", "verify"], None);

    let expected = gil::RuleSet::builtin()
        .unwrap()
        .validate_open(gil::Node::cycle_entry(), gil::NodeKind::Verify)
        .expect_err("시작 경계에서 verify 는 열리지 않는다")
        .to_string();
    assert!(
        said.contains(&expected),
        "라이브러리의 말과 다르게 거절했다:\n표면: {said}\n라이브러리: {expected}"
    );
}

#[test]
fn a_report_may_be_written_the_way_the_spec_names_its_fields() {
    // 명세는 칸을 `next_direction.action` 이라 부른다. 중첩해 적어도 그 이름이 돼야 한다.
    let dir = scratch("cli-nested");
    ok(&dir, &["start"], None);
    ok(&dir, &["open", "define"], None);
    ok(&dir, &["close"], Some(DEFINE));
    ok(&dir, &["open", "hypothesis"], None);
    ok(&dir, &["close"], Some(HYPOTHESIS));
    ok(&dir, &["open", "verify"], None);
    ok(&dir, &["close"], Some("execution: 걸어 봤다\nresult: 됐다\n"));
    ok(&dir, &["open", "analysis"], None);
    ok(
        &dir,
        &["close"],
        Some(
            "hypothesis_fit: 맞았다\nproblem_solved: 그렇다\nsuccess_condition_met: 그렇다\n\
             guardrail_triggered: 아니다\ninterpretation: 읽혔다\n",
        ),
    );
    ok(&dir, &["open", "outcome"], None);

    let closed = ok(
        &dir,
        &["close"],
        Some(
            "verdict: failure\nlesson: 갈래는 아직이다\n\
             next_direction:\n  action: revisit\n  target_node_id: 4\n  reason: 가설부터 다시\n",
        ),
    );
    assert!(closed.contains("closed"), "중첩해 적은 Report 가 안 받아들여졌다");

    // 적어 둔 되돌아감이 실제로 밟힌다.
    let moved = ok(&dir, &["revisit"], None);
    assert!(moved.contains("#4"), "적어 둔 자리로 옮겨가지 않았다:\n{moved}");
}

#[test]
fn what_status_offers_can_actually_be_opened() {
    // 실사용 보고 #123 — status 가 `outcome` 을 안내했고, 그대로 쳤더니 종료 코드 1이었다.
    // 안내를 믿은 Agent 가 한 번 실패하고서야 옳은 수를 알게 되면 그 안내는 없느니만 못하다.
    let dir = scratch("cli-status-truth");
    walk_to_a_revisit(&dir);
    ok(&dir, &["revisit"], None);

    let said = ok(&dir, &["status"], None);
    let offered: Vec<&str> = said
        .lines()
        .find(|line| line.starts_with("다음: 열 수 있는 것"))
        .unwrap_or_else(|| panic!("무엇을 열 수 있는지 말하지 않는다:\n{said}"))
        .rsplit_once("— ")
        .expect("안내는 목록을 낸다")
        .1
        .split(", ")
        .collect();

    assert!(!offered.is_empty(), "빈 목록을 안내한다");
    for kind in offered {
        // 안내한 것은 하나도 빠짐없이 실제로 열려야 한다.
        let out = run(&dir, &["open", kind], None);
        assert!(
            out.status.success(),
            "status 가 {kind} 를 안내했는데 실제로는 거절됐다:\n{}",
            String::from_utf8_lossy(&out.stderr)
        );
    }
}

/// `#5 Outcome` 이 `#4` 로 되돌아가겠다고 적고 닫힌 자리까지 걷는다.
fn walk_to_a_revisit(dir: &Path) {
    ok(dir, &["start"], None);
    ok(dir, &["open", "define"], None);
    ok(dir, &["close"], Some(DEFINE));
    ok(dir, &["open", "hypothesis"], None);
    ok(dir, &["close"], Some(HYPOTHESIS));
    ok(dir, &["open", "verify"], None);
    ok(dir, &["close"], Some("execution: 걸어 봤다\nresult: 안 됐다\n"));
    ok(dir, &["open", "analysis"], None);
    ok(
        dir,
        &["close"],
        Some(
            "hypothesis_fit: 어긋났다\nproblem_solved: 아니다\nsuccess_condition_met: 아니다\n\
             guardrail_triggered: 아니다\ninterpretation: 표현이 모자랐다\n",
        ),
    );
    ok(dir, &["open", "outcome"], None);
    ok(
        dir,
        &["close"],
        Some(
            "verdict: failure\nlesson: 갈래를 다시 세운다\n\
             next_direction:\n  action: revisit\n  target_node_id: 4\n  reason: 가설부터 다시\n",
        ),
    );
}

#[test]
fn a_sentence_with_a_node_name_in_it_survives_the_close() {
    // 실사용 보고 #124 — `#7` 부터 문장 끝까지 조용히 사라졌고 close 는 성공했다.
    let dir = scratch("cli-hash");
    let sentence = "기존 Walk의 #7 verify open 상태를 찾아 작업을 이어갈 수 있었다";
    ok(&dir, &["start"], None);
    ok(&dir, &["open", "define"], None);
    ok(
        &dir,
        &["close"],
        Some(&format!("problem: {sentence}\nsuccess_condition: 3.10 그대로\n")),
    );

    let told = ok(&dir, &["story"], None);
    assert!(told.contains(sentence), "문장이 잘렸다:\n{told}");
    assert!(told.contains("3.10"), "숫자처럼 보이는 값이 바뀌었다:\n{told}");
}

#[test]
fn a_command_gil_does_not_know_points_at_the_ones_it_does() {
    let dir = scratch("cli-unknown");
    let said = refused(&dir, &["fly"], None);
    for command in ["start", "open", "close", "revisit", "status", "story"] {
        assert!(said.contains(command), "{command} 를 안내에서 못 찾겠다:\n{said}");
    }
}

#[test]
fn gil_says_which_build_it_is() {
    // Codex 가 무엇을 설치했는지 확인할 수 있어야 한다.
    let dir = scratch("cli-version");
    let said = ok(&dir, &["--version"], None);
    assert!(
        said.contains(env!("CARGO_PKG_VERSION")),
        "판을 밝히지 않는다: {said}"
    );
}

#[test]
fn the_builtin_spec_is_the_repository_spec() {
    // 함께 실린 명세가 저장소의 그 파일인가. 사본이 되는 순간 한쪽이 낡는다.
    let on_disk = std::fs::read_to_string(common::SPEC_PATH).unwrap();
    assert_eq!(gil::BUILTIN_SPEC, on_disk, "실린 명세와 저장소의 명세가 갈렸다");
}
