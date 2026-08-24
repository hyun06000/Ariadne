//! `gil` 을 **프로세스로** 부른다.
//!
//! 여기서만 잴 수 있는 것이 하나 있다: **한 턴에 열고 다음 턴에 닫는 것.**
//! Agent 의 한 턴은 한 프로세스라, 라이브러리 시험은 이 경계를 못 넘어 본다.

use std::io::Write;
use std::path::{Path, PathBuf};
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


/// 이 자리에서 실제로 하려는 일 — **CLI 에도 행동 계약이 필요하다.**
///
/// 실행형 자리는 무엇을 하려는지 적지 않으면 열리지 않는다. 시험이 뜻 없는 더미를 곳곳에
/// 베끼지 않도록 Kind 하나에 최소 계약 하나를 **여기 한 자리에만** 적는다.
fn contract_for(kind: &str) -> String {
    let (objective, next_action, done_when) = match kind {
        "question" => (
            "사용자의 의도를 확인한다",
            "선택지와 함께 질문을 건넨다",
            "사용자의 원문 응답을 얻는다",
        ),
        "interpretation" => (
            "응답에서 확정된 것과 모르는 것을 가른다",
            "받은 응답을 다시 읽고 명제로 정리한다",
            "정리한 명제와 남은 미해결이 적힌다",
        ),
        "synthesis" => (
            "확인한 것을 하나의 제안으로 모은다",
            "근거를 모아 제안을 짓고 승인을 구한다",
            "사용자의 승인 여부를 얻는다",
        ),
        "define" => (
            "이 실험이 풀 문제를 정한다",
            "무엇이 문제이고 무엇이면 성공인지 적는다",
            "문제와 성공 기준이 문장으로 남는다",
        ),
        "hypothesis" => (
            "원인 후보 하나를 세운다",
            "코드를 읽어 검증 가능한 후보를 고른다",
            "가설 한 문장이 남는다",
        ),
        "verify" => (
            "가설을 실제로 검증한다",
            "테스트를 실행해 결과를 관측한다",
            "실행 결과를 확보한다",
        ),
        "analysis" => (
            "관측을 가설과 맞춰 읽는다",
            "관측 결과가 가설과 맞는지 따진다",
            "맞았는지 아닌지 말할 수 있다",
        ),
        "outcome" => (
            "이 Cycle 을 판정한다",
            "지금까지의 관측을 모아 판정과 다음 방향을 정한다",
            "판정과 다음 방향을 말할 수 있다",
        ),
        // 어느 자리인지 시험이 미리 정하지 않는 경우 — 안내를 따라가는 시험이 그렇다.
        _ => (
            "이 자리가 요구하는 일을 한다",
            "지금 자리가 요구하는 실제 작업을 수행한다",
            "그 자리의 Report 를 적을 수 있다",
        ),
    };
    format!("objective: {objective}\nnext_action: {next_action}\ndone_when: {done_when}\n")
}

/// 실행형 자리를 계약과 함께 연다 — Kind 를 적어서.
fn open_action(dir: &Path, kind: &str) -> String {
    ok(dir, &["open", kind], Some(&contract_for(kind)))
}

/// 갈 곳이 하나뿐이라 Kind 를 적지 않는 자리.
fn open_action_here(dir: &Path, kind: &str) -> String {
    ok(dir, &["open"], Some(&contract_for(kind)))
}

// ── Bootstrap Interview — 프로세스 경계를 넘어 걷는 최소 한 벌 ─────────────

const QUESTION: &str = "question: 무엇이라고 불러 드리면 좋을까요\n\
                        choices: |\n  1. 이름\n  2. 아직 잘 모르겠음 — 더 작은 질문 필요\n  3. 직접 입력\n\
                        response: 상현이라고 불러 주세요\n";
const INTERPRETATION: &str = "interpretation: 사용자는 상현이라는 호칭으로 불리기를 원한다\n\
                              unresolved: 무엇을 만들고 싶은지는 아직 묻지 않았다\n";
const SYNTHESIS: &str = "statement: 사용자를 상현이라 부르고 환경 변수 파싱 문제부터 다룬다\n\
                         basis_refs: |\n  step:C1/S1\n  step:C1/S2\n\
                         approved: yes\n";
const INTERVIEW_OUTCOME: &str = "verdict: success\n\
                                 lesson: 호칭과 첫 탐색 범위를 승인받았다\n\
                                 synthesis_ref: step:C1/S3\n\
                                 next_direction:\n  action: close_cycle\n  reason: 승인된 Synthesis 를 얻었다\n";
const INTERVIEW_CYCLE: &str = "verdict: success\n\
                               outcome_ref: step:C1/S4\n\
                               handoff_summary: 사용자는 상현이라 불리기를 원하고 환경 변수 문제를 먼저 본다\n\
                               next_direction:\n  action: open_child\n  reason: 승인된 탐색 범위의 첫 항목을 실험으로 연다\n";

/// `gil start` 부터 Experiment 자식을 열기까지 — **매 걸음이 다른 프로세스다.**
///
/// 프로젝트의 첫 Cycle 은 언제나 Interview 다. 그래서 Experiment 를 걷는 모든 시험은 먼저
/// 이 길을 지난다 — 묻고, 해석하고, 제안하고, 사람이 승인해야 실험이 태어난다.
fn bootstrap(dir: &Path) {
    ok(dir, &["start"], None);
    for (kind, report) in [
        ("question", QUESTION),
        ("interpretation", INTERPRETATION),
        ("synthesis", SYNTHESIS),
        ("outcome", INTERVIEW_OUTCOME),
    ] {
        open_action(dir, kind);
        ok(dir, &["close"], Some(report));
    }
    ok(dir, &["close"], Some(INTERVIEW_CYCLE));
    ok(dir, &["open", "experiment"], None);
}

const DEFINE: &str = "problem: 이야기가 설명 없이 읽히는가\nsuccess_condition: 여덟 물음에 답하면 풀린 것이다\n";
const HYPOTHESIS: &str = "hypothesis: 칸을 늘어놓으면 읽힌다\nrationale: 데이터는 이미 다 있다\nguardrail: 내부 낱말이 새면 실패\n";

#[test]
fn a_step_opened_in_one_process_is_closed_in_the_next() {
    // 저장이 없으면 이 시험은 원리적으로 통과할 수 없다 — 여는 프로세스와 닫는 프로세스가
    // 다르기 때문이다. dogfooding 을 막고 있던 것이 정확히 이것이다.
    let dir = scratch("cli-across-processes");
    bootstrap(&dir);
    open_action(&dir, "define");

    let closed = ok(&dir, &["close"], Some(DEFINE));
    assert!(closed.contains("닫았다"), "다른 프로세스에서 닫히지 않았다:\n{closed}");

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
        said.contains(gil::STATE_PATH),
        "어디에 눕혔는지 말하지 않는다:\n{said}"
    );
    assert!(dir.join(gil::STATE_PATH).exists(), "말한 자리에 파일이 없다");
}

#[test]
fn starting_twice_does_not_wipe_what_was_written() {
    // 적힌 사고를 조용히 지우지 않는다. 지우는 것은 사람의 판단이다.
    let dir = scratch("cli-restart");
    bootstrap(&dir);
    open_action(&dir, "define");
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
    let said = refused(&dir, &["open", "verify"], Some(&contract_for("verify")));

    let expected = gil::RuleSet::builtin()
        .unwrap()
        .validate_open(
            gil::CycleKind::Interview,
            gil::Node::cycle_entry(),
            gil::NodeKind::Verify,
        )
        .expect_err("시작 경계에서 verify 는 열리지 않는다")
        .to_string();
    assert!(
        said.contains(&expected),
        "라이브러리의 말과 다르게 거절했다:\n표면: {said}\n라이브러리: {expected}"
    );
}

#[test]
fn the_skeleton_gil_prints_names_its_fields_the_dotted_way() {
    // 접어 적은 것도 받아들이지만(아래 시험), **내보일 때의 canonical 표기는 dotted** 다.
    // 골격이 접힌 꼴이면 사람은 들여쓰기 폭을 다시 정해야 한다 — 표기가 하나여야 한다.
    let dir = scratch("cli-dotted-skeleton");
    bootstrap(&dir);
    open_action(&dir, "define");
    ok(&dir, &["close"], Some(DEFINE));
    open_action(&dir, "hypothesis");
    ok(&dir, &["close"], Some(HYPOTHESIS));
    open_action(&dir, "verify");
    ok(&dir, &["close"], Some("execution: 걸어 봤다\nresult: 됐다\n"));
    open_action(&dir, "analysis");
    ok(
        &dir,
        &["close"],
        Some(
            "hypothesis_fit: 맞았다\nproblem_solved: 그렇다\nsuccess_condition_met: 그렇다\n\
             guardrail_triggered: 아니다\ninterpretation: 읽혔다\n",
        ),
    );
    open_action(&dir, "outcome");

    let said = refused(&dir, &["close"], Some("verdict: success\n"));
    assert!(
        said.contains("next_direction.action: …") && said.contains("next_direction.reason: …"),
        "골격이 dotted 로 칸을 내보이지 않는다:\n{said}"
    );
    assert!(
        !said.contains("next_direction:"),
        "골격이 접힌 꼴을 내보였다 — canonical 표기는 dotted 다:\n{said}"
    );
}

#[test]
fn a_report_may_be_written_the_way_the_spec_names_its_fields() {
    // 명세는 칸을 `next_direction.action` 이라 부른다. 중첩해 적어도 그 이름이 돼야 한다.
    let dir = scratch("cli-nested");
    bootstrap(&dir);
    open_action(&dir, "define");
    ok(&dir, &["close"], Some(DEFINE));
    open_action(&dir, "hypothesis");
    ok(&dir, &["close"], Some(HYPOTHESIS));
    open_action(&dir, "verify");
    ok(&dir, &["close"], Some("execution: 걸어 봤다\nresult: 됐다\n"));
    open_action(&dir, "analysis");
    ok(
        &dir,
        &["close"],
        Some(
            "hypothesis_fit: 맞았다\nproblem_solved: 그렇다\nsuccess_condition_met: 그렇다\n\
             guardrail_triggered: 아니다\ninterpretation: 읽혔다\n",
        ),
    );
    open_action(&dir, "outcome");

    let closed = ok(
        &dir,
        &["close"],
        Some(
            "verdict: failure\nlesson: 갈래는 아직이다\n\
             next_direction:\n  action: revisit\n  target_node_ref: step:C2/S4\n  reason: 가설부터 다시\n",
        ),
    );
    assert!(closed.contains("닫았다"), "중첩해 적은 Report 가 안 받아들여졌다");

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
        let out = run(&dir, &["open", kind], Some(&contract_for(kind)));
        assert!(
            out.status.success(),
            "status 가 {kind} 를 안내했는데 실제로는 거절됐다:\n{}",
            String::from_utf8_lossy(&out.stderr)
        );
    }
}

/// `#5 Outcome` 이 `#4` 로 되돌아가겠다고 적고 닫힌 자리까지 걷는다.
fn walk_to_a_revisit(dir: &Path) {
    bootstrap(dir);
    open_action(dir, "define");
    ok(dir, &["close"], Some(DEFINE));
    open_action(dir, "hypothesis");
    ok(dir, &["close"], Some(HYPOTHESIS));
    open_action(dir, "verify");
    ok(dir, &["close"], Some("execution: 걸어 봤다\nresult: 안 됐다\n"));
    open_action(dir, "analysis");
    ok(
        dir,
        &["close"],
        Some(
            "hypothesis_fit: 어긋났다\nproblem_solved: 아니다\nsuccess_condition_met: 아니다\n\
             guardrail_triggered: 아니다\ninterpretation: 표현이 모자랐다\n",
        ),
    );
    open_action(dir, "outcome");
    ok(
        dir,
        &["close"],
        Some(
            "verdict: failure\nlesson: 갈래를 다시 세운다\n\
             next_direction:\n  action: revisit\n  target_node_ref: step:C2/S4\n  reason: 가설부터 다시\n",
        ),
    );
}

#[test]
fn a_sentence_with_a_node_name_in_it_survives_the_close() {
    // 실사용 보고 #124 — `#7` 부터 문장 끝까지 조용히 사라졌고 close 는 성공했다.
    let dir = scratch("cli-hash");
    let sentence = "기존 Walk의 #7 verify open 상태를 찾아 작업을 이어갈 수 있었다";
    bootstrap(&dir);
    open_action(&dir, "define");
    ok(
        &dir,
        &["close"],
        Some(&format!("problem: {sentence}\nsuccess_condition: 3.10 그대로\n")),
    );

    let told = ok(&dir, &["story"], None);
    assert!(told.contains(sentence), "문장이 잘렸다:\n{told}");
    assert!(told.contains("3.10"), "숫자처럼 보이는 값이 바뀌었다:\n{told}");
}

// ── 어느 걷기를 이어 걷는가 ────────────────────────────────────────────────

/// 뿌리 아래 깊은 자리 하나를 만든다 — Agent 가 실제로 오가는 꼴.
fn below(root: &Path) -> PathBuf {
    let deep = root.join("pkg").join("src");
    std::fs::create_dir_all(&deep).expect("하위 폴더를 만들 수 있어야 한다");
    deep
}

#[test]
fn a_walk_is_continued_from_a_folder_below_it() {
    // 실사용 보고 #125 — Agent 는 소스·시험·하위 패키지를 계속 오간다.
    let root = scratch("cli-below");
    let deep = below(&root);
    bootstrap(&root);

    open_action(&deep, "define");
    ok(&deep, &["close"], Some(DEFINE));

    // 뿌리에서 봐도 같은 걷기여야 한다 — 적은 것이 다른 데로 가지 않았다.
    let told = ok(&root, &["story"], None);
    assert!(told.contains("이야기가 설명 없이 읽히는가"), "적은 것이 딴 데로 갔다:\n{told}");
}

#[test]
fn walking_from_below_does_not_leave_a_second_walk() {
    // 걷기가 둘이 되면 사고의 기록이 조용히 갈린다 — 마찰이 아니라 사고다.
    let root = scratch("cli-one-walk");
    let deep = below(&root);
    bootstrap(&root);
    open_action(&deep, "define");

    assert!(!deep.join(gil::STATE_PATH).exists(), "하위 폴더에 걷기가 또 생겼다");
}

#[test]
fn starting_below_an_existing_walk_is_refused_and_says_where_it_is() {
    let root = scratch("cli-start-below");
    let deep = below(&root);
    ok(&root, &["start"], None);

    let said = refused(&deep, &["start"], None);
    assert!(
        said.contains(&root.join(gil::STATE_PATH).display().to_string()),
        "이미 있는 걷기가 어디인지 말하지 않는다:\n{said}"
    );
    assert!(!deep.join(gil::STATE_PATH).exists(), "거절하면서 파일은 만들었다");
}

#[test]
fn a_walk_that_is_not_here_says_where_it_is() {
    // 어느 걷기를 보고 있는지 화면이 말하지 않으면, 남의 걷기를 보며 제 것이
    // 망가졌다고 오진하게 된다.
    let root = scratch("cli-which-walk");
    let deep = below(&root);
    ok(&root, &["start"], None);

    let from_root = ok(&root, &["status"], None);
    assert!(
        !from_root.contains("걷기:"),
        "여기 있는 걷기까지 자리를 밝힌다 — 예사로운 일에 줄을 쓰면 정작 알려야 할 때 안 읽힌다:\n{from_root}"
    );

    let from_below = ok(&deep, &["status"], None);
    assert!(
        from_below.contains(&root.join(gil::STATE_PATH).display().to_string()),
        "다른 자리의 걷기를 이어 걸으면서 어느 것인지 말하지 않는다:\n{from_below}"
    );
}

#[test]
fn a_walk_above_is_not_borrowed_from_outside_the_project() {
    // 위로 거슬러 오르는 것은 **가장 가까운 것 하나**다. 옆 프로젝트의 걷기를 끌어오면 안 된다.
    let root = scratch("cli-sibling");
    let mine = root.join("mine");
    let theirs = root.join("theirs");
    std::fs::create_dir_all(&mine).unwrap();
    std::fs::create_dir_all(&theirs).unwrap();

    ok(&mine, &["start"], None);
    refused(&theirs, &["status"], None);
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

// ── Cycle 하나를 프로세스로 닫는다 ─────────────────────────────────────────

const VERIFY: &str = "execution: 걸어 봤다\nresult: 안 됐다\n";
const ANALYSIS: &str = "hypothesis_fit: 어긋났다\nproblem_solved: 아니다\n\
                        success_condition_met: 아니다\nguardrail_triggered: 아니다\n\
                        interpretation: 표현이 모자랐다\n";
const OUTCOME: &str = "verdict: failure\nlesson: 갈래를 다시 세운다\n\
                       next_direction:\n  action: close_cycle\n  reason: 이 실험은 여기까지다\n";
/// Experiment Cycle 을 닫는 Report — `outcome_ref` 는 **그 Cycle 안의 주소**다.
///
/// 상수로 둘 수 없다. Step 이름은 소속 Cycle 안에서만 유일하므로 어느 Cycle 을 닫느냐에 따라
/// 가리킬 주소가 달라진다.
fn experiment_cycle(cycle: &str, verdict: &str, action: &str) -> String {
    format!(
        "verdict: {verdict}\noutcome_ref: step:{cycle}/S5\n\
         handoff_summary: 다음 Cycle 이 알아야 할 것\n\
         next_direction:\n  action: {action}\n  reason: 왜 그 방향인지\n"
    )
}

/// 걷고 나서 방금 닫은 Experiment 를 실패로 닫는 Report.
fn cycle_failed(cycle: &str) -> String {
    experiment_cycle(cycle, "failure", "revisit")
}

/// 같은 자리를 성공으로 닫는 Report.
fn cycle_succeeded(cycle: &str) -> String {
    experiment_cycle(cycle, "success", "open_child")
}

/// 안의 Outcome 까지 닫아 **끝 경계에 닿은** 자리까지 걷는다 — 매 걸음이 다른 프로세스다.
fn walk_to_the_exit(dir: &Path) {
    bootstrap(dir);
    open_action(dir, "define");
    ok(dir, &["close"], Some(DEFINE));
    open_action(dir, "hypothesis");
    ok(dir, &["close"], Some(HYPOTHESIS));
    open_action(dir, "verify");
    ok(dir, &["close"], Some(VERIFY));
    open_action(dir, "analysis");
    ok(dir, &["close"], Some(ANALYSIS));
    open_action(dir, "outcome");
    ok(dir, &["close"], Some(OUTCOME));
}

#[test]
fn a_cycle_walked_across_processes_is_closed_in_yet_another_one() {
    // 완료 조건 10 — 모든 걸음이 서로 다른 프로세스다.
    let dir = scratch("cli-cycle-close");
    walk_to_the_exit(&dir);

    let before = ok(&dir, &["status"], None);
    assert!(before.contains("Cycle 2 experiment (열림)"), "{before}");
    assert!(
        before.contains("gil close"),
        "닫을 수 있다는 것을 안내하지 않는다:\n{before}"
    );

    let closed = ok(&dir, &["close"], Some(&cycle_failed("C2")));
    assert!(closed.contains("닫았다: cycle:C2"), "Cycle 이 닫히지 않았다:\n{closed}");

    // 또 다른 프로세스에서 읽어도 닫혀 있다.
    let after = ok(&dir, &["status"], None);
    assert!(after.contains("닫힘"), "{after}");
}

#[test]
fn the_cli_refuses_to_close_a_cycle_before_its_outcome() {
    // 완료 조건 2.
    let dir = scratch("cli-cycle-early");
    bootstrap(&dir);
    refused(&dir, &["close"], Some(&cycle_failed("C2")));

    open_action(&dir, "define");
    ok(&dir, &["close"], Some(DEFINE));

    // 안의 판정에 닿기 전에는 Cycle 을 닫는 자리가 아니다 — 그리고 지금 무엇을 할지 말한다.
    let said = refused(&dir, &["close"], Some(&cycle_failed("C2")));
    assert!(said.contains("hypothesis"), "지금 무엇을 할지 말하지 않는다:\n{said}");
    assert!(said.contains("gil open"), "다음 명령을 말하지 않는다:\n{said}");

    // 그리고 실제로 닫히지 않았다.
    let still = ok(&dir, &["status"], None);
    assert!(still.contains("열림"), "Cycle 이 닫혔다:\n{still}");
}

#[test]
fn the_cli_names_the_missing_cycle_report_field() {
    // 완료 조건 3 — 어느 칸이 빠졌는지 그 이름을 말해야 한다.
    let dir = scratch("cli-cycle-thin");
    walk_to_the_exit(&dir);

    let said = refused(&dir, &["cycle", "close"], Some("verdict: failure\n"));
    for field in ["outcome_ref", "handoff_summary", "next_direction.reason"] {
        assert!(said.contains(field), "{field} 를 말하지 않는다:\n{said}");
    }
}

#[test]
fn the_cli_refuses_a_cycle_report_that_disagrees_with_its_outcome() {
    // 완료 조건 4·5·6 이 표면에서도 그대로 선다.
    let dir = scratch("cli-cycle-disagree");
    walk_to_the_exit(&dir);

    // ④ 이 Cycle 안의 닫힌 Outcome 이 아니다.
    let said = refused(
        &dir,
        &["close"],
        Some(&cycle_failed("C2").replace("S5", "S1")),
    );
    assert!(said.contains("outcome"), "{said}");

    // ⑤ 두 판정이 어긋난다. (success 로 바꾸면 방향도 함께 좁혀지므로 방향까지 맞춘다)
    let said = refused(
        &dir,
        &["close"],
        Some(&cycle_succeeded("C2")),
    );
    assert!(said.contains("success") && said.contains("failure"), "{said}");

    // ⑥ 판정이 방향을 좁힌다.
    let said = refused(
        &dir,
        &["close"],
        Some(&cycle_failed("C2").replace("action: revisit", "action: open_child")),
    );
    assert!(said.contains("verdict"), "왜 좁혀졌는지 말하지 않는다:\n{said}");
}

#[test]
fn a_closed_cycle_moves_no_more_from_the_cli() {
    // 완료 조건 8.
    let dir = scratch("cli-cycle-frozen");
    walk_to_the_exit(&dir);
    ok(&dir, &["close"], Some(&cycle_failed("C2")));

    refused(&dir, &["open", "hypothesis"], Some(&contract_for("hypothesis")));
    refused(&dir, &["close"], Some(DEFINE));
    refused(&dir, &["revisit"], None);
    refused(&dir, &["close"], Some(&cycle_failed("C2")));
}

#[test]
fn a_closed_cycle_says_what_cannot_be_done_yet() {
    // 방향을 적는 것과 실제로 옮기는 것이 다르다는 사실을 사람이 오해하지 않게.
    let dir = scratch("cli-cycle-honest");
    walk_to_the_exit(&dir);
    ok(&dir, &["close"], Some(&cycle_failed("C2")));

    let said = ok(&dir, &["status"], None);
    assert!(
        said.contains("아직 짓지 않았다"),
        "아직 못 하는 것을 밝히지 않는다:\n{said}"
    );

    let told = ok(&dir, &["story"], None);
    assert!(
        told.contains("다음 Cycle 이 알아야 할 것"),
        "Cycle Report 를 이야기에서 읽을 수 없다:\n{told}"
    );
    assert!(
        told.contains("아직 짓지 않았다"),
        "이야기도 아직 못 하는 것을 밝혀야 한다:\n{told}"
    );
}

#[test]
fn the_exit_boundary_is_not_something_you_open() {
    // Cycle Exit 은 Step 이 아니다. 여는 척하는 자리를 남기면 그것으로 Cycle 을 닫으려 든다.
    let dir = scratch("cli-boundary");
    bootstrap(&dir);
    open_action(&dir, "define");
    ok(&dir, &["close"], Some(DEFINE));

    let said = refused(&dir, &["open", "cycle_exit"], Some(&contract_for("cycle_exit")));
    assert!(said.contains("경계"), "{said}");

    // 끝 경계에 닿은 자리에서도 여는 것이 아니라 **닫는 것**이라고 말한다.
    for (kind, report) in [
        ("hypothesis", HYPOTHESIS),
        ("verify", VERIFY),
        ("analysis", ANALYSIS),
        ("outcome", OUTCOME),
    ] {
        open_action(&dir, kind);
        ok(&dir, &["close"], Some(report));
    }
    let said = refused(&dir, &["open", "cycle_exit"], Some(&contract_for("cycle_exit")));
    assert!(said.contains("gil close"), "{said}");

    let listed = ok(&dir, &["status"], None);
    assert!(
        !listed.contains("cycle_exit"),
        "열 수 없는 것을 안내한다:\n{listed}"
    );
}

#[test]
fn an_earlier_format_is_not_silently_ignored() {
    // 완료 조건 11 — 조용히 무시하면 사람은 제 기록이 사라진 줄 안다.
    let dir = scratch("cli-legacy");
    let legacy = dir.join(gil::LEGACY_WALK_PATH);
    std::fs::create_dir_all(legacy.parent().unwrap()).unwrap();
    std::fs::write(&legacy, "format: 0\nnext_id: 1\nnodes: []\n").unwrap();

    for args in [&["status"][..], &["story"][..], &["start"][..]] {
        let said = refused(&dir, args, None);
        assert!(
            said.contains(gil::LEGACY_WALK_PATH),
            "gil {args:?} 가 앞 형식을 말하지 않는다:\n{said}"
        );
    }
    // 지우지 않는다 — 적힌 것은 사람이 치운다.
    assert!(legacy.exists(), "앞 형식 파일을 도구가 치웠다");
}

// ── 여러 Cycle 을 잇는다 ───────────────────────────────────────────────────

/// 넘길 말이 여러 줄인 성공 Report — story·context 시험이 그 글자를 찾는다.
fn cycle_handed_off(cycle: &str) -> String {
    format!(
        "verdict: success\noutcome_ref: step:{cycle}/S5\n\
         handoff_summary: |\n  \
         숫자가 아닌 환경 변수는 기본값으로 떨어진다는 것을 확인했다.\n  \
         문자열 설정값은 아직 확인하지 않았다.\n\
         next_direction:\n  action: open_child\n  \
         reason: 확인하지 않은 문자열 설정값을 다음 실험에서 본다\n"
    )
}

/// 안의 Outcome 을 그 판정으로 닫아 끝 경계까지 걷는다 — 매 걸음이 다른 프로세스다.
fn walk_to_the_exit_with(dir: &Path, verdict: &str) {
    open_action(dir, "define");
    ok(dir, &["close"], Some(DEFINE));
    open_action(dir, "hypothesis");
    ok(dir, &["close"], Some(HYPOTHESIS));
    open_action(dir, "verify");
    ok(dir, &["close"], Some(VERIFY));
    open_action(dir, "analysis");
    ok(dir, &["close"], Some(ANALYSIS));
    open_action(dir, "outcome");
    let action = match verdict {
        "success" => "close_cycle",
        _ => "close_cycle",
    };
    ok(
        dir,
        &["close"],
        Some(&format!(
            "verdict: {verdict}\nlesson: 이 실험에서 무엇을 배웠는지\n\
             next_direction:\n  action: {action}\n  reason: 이 실험은 여기까지다\n"
        )),
    );
}

#[test]
fn a_second_cycle_is_opened_from_the_first_across_processes() {
    // 완료 조건 5·12·15·16.
    let dir = scratch("cli-second-cycle");
    bootstrap(&dir);
    walk_to_the_exit_with(&dir, "success");
    ok(&dir, &["close"], Some(&cycle_handed_off("C2")));

    // 닫힌 뒤 status 가 **다음 Cycle 을 열 수 있다**고 말한다.
    let said = ok(&dir, &["status"], None);
    assert!(said.contains("gil open"), "다음 수를 가리키지 않는다:\n{said}");
    assert!(
        !said.contains("gil cycle open"),
        "옛 이름을 기본 경로로 홍보한다:\n{said}"
    );

    let opened = ok(&dir, &["open", "experiment"], None);
    assert!(opened.contains("cycle:C3"), "새 Cycle 이 이름을 안 받았다:\n{opened}");
    assert!(opened.contains("부모 cycle:C2"), "부모를 안 말한다:\n{opened}");
    assert!(
        opened.contains("define"),
        "새 Cycle 이 새 Define 을 요구하지 않는다:\n{opened}"
    );

    // 또 다른 프로세스에서 읽어도 그대로다.
    let said = ok(&dir, &["status"], None);
    assert!(said.contains("Cycle 3") && said.contains("부모 Cycle 2"), "{said}");
    assert!(said.contains("이어받음"), "무엇을 이어받았는지 안 말한다:\n{said}");
}

#[test]
fn a_child_cannot_be_opened_while_a_cycle_is_still_walking() {
    // 완료 조건 2·13.
    let dir = scratch("cli-child-too-early");
    bootstrap(&dir);
    refused(&dir, &["open", "experiment"], None);

    walk_to_the_exit_with(&dir, "success");
    let said = refused(&dir, &["open", "experiment"], None);
    assert!(said.contains("gil close"), "무엇을 먼저 할지 안 말한다:\n{said}");

    // 옛 이름으로 불러도 같은 판정에 닿는다 — 끊지 않고 남겨 둔 자리다.
    let old = refused(&dir, &["cycle", "open", "experiment"], None);
    assert!(old.contains("gil close"), "{old}");
}

#[test]
fn a_failed_cycle_has_no_child() {
    // 완료 조건 3 — 그리고 무엇이 적혀 있었는지 말해야 한다.
    let dir = scratch("cli-failed-parent");
    bootstrap(&dir);
    walk_to_the_exit_with(&dir, "failure");
    ok(&dir, &["close"], Some(&cycle_failed("C2")));

    let said = refused(&dir, &["cycle", "open", "experiment"], None);
    assert!(said.contains("revisit"), "적어 둔 방향을 말하지 않는다:\n{said}");
    assert!(
        said.contains("실패한 Cycle 은 자식을 만들지 않는다"),
        "까닭을 말하지 않는다:\n{said}"
    );
}

#[test]
fn the_story_tells_the_two_cycles_apart() {
    // 완료 조건 15 — 그리고 부모의 Step 을 자식 아래에 다시 펼치지 않는다.
    let dir = scratch("cli-two-cycle-story");
    bootstrap(&dir);
    walk_to_the_exit_with(&dir, "success");
    ok(&dir, &["close"], Some(&cycle_handed_off("C2")));
    ok(&dir, &["open", "experiment"], None);

    let told = ok(&dir, &["story"], None);
    assert!(told.contains("Cycle 1"), "첫 Cycle 이 안 보인다:\n{told}");
    assert!(told.contains("Cycle 2"), "둘째 Cycle 이 안 보인다:\n{told}");
    assert!(
        told.contains("Cycle 1 에서 이어받음"),
        "부모 관계가 안 보인다:\n{told}"
    );
    assert!(
        told.contains("[이어받은 것]"),
        "무엇을 이어받았는지 안 보인다:\n{told}"
    );

    // 부모의 Define 은 첫 Cycle 절에 **한 번만** 나온다.
    let (first, second) = told
        .split_once("═══ Cycle 3")
        .expect("두 Experiment Cycle 이 갈리지 않는다");
    assert!(first.contains(DEFINE.lines().next().unwrap().trim_start_matches("problem: ")));
    assert!(
        !second.contains(DEFINE.lines().next().unwrap().trim_start_matches("problem: ")),
        "부모의 Step 이 자식 아래에 다시 펼쳐졌다:\n{second}"
    );
}

#[test]
fn an_unknown_cycle_kind_is_refused() {
    let dir = scratch("cli-cycle-kind");
    bootstrap(&dir);
    walk_to_the_exit_with(&dir, "success");
    ok(&dir, &["close"], Some(&cycle_handed_off("C2")));

    let said = refused(&dir, &["cycle", "open", "seminar"], None);
    assert!(said.contains("experiment"), "아는 종류를 안 말한다:\n{said}");
    assert!(said.contains("interview"), "아는 종류를 안 말한다:\n{said}");
    let said = refused(&dir, &["cycle", "open"], None);
    assert!(said.contains("experiment"), "{said}");
}

#[test]
fn the_previous_format_is_not_silently_read() {
    // 완료 조건 17 의 첫 자리 — 앞 형식(S1 의 단일 Cycle)을 만나면 말한다.
    let dir = scratch("cli-format-1");
    let path = dir.join(gil::STATE_PATH);
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    std::fs::write(&path, "format: 1\ncycle:\n  kind: experiment\n").unwrap();

    let said = refused(&dir, &["status"], None);
    assert!(said.contains("형식 1"), "앞 형식이라고 말하지 않는다:\n{said}");
    assert!(said.contains("2"), "지금 형식을 말하지 않는다:\n{said}");
    assert!(path.exists(), "앞 형식 파일을 도구가 치웠다");
}

// ── 새 세션이 한 번 읽고 이어 걷는다 ───────────────────────────────────────

/// Cycle 2 가 제 말로 적는 것들 — Cycle 1 의 글과 한 글자도 겹치지 않는다.
const SECOND_DEFINE: &str = "problem: 문자열 설정값이 기본값으로 떨어지는가\n\
                             success_condition: 잘못된 문자열에서 기본값이 나오면 풀린 것이다\n";
const SECOND_HYPOTHESIS: &str = "hypothesis: 문자열 파서도 같은 자리에서 떨어진다\n\
                                 rationale: 숫자 파서와 같은 함수를 지난다\n\
                                 guardrail: 파서를 고쳐야 하면 멈춘다\n";

/// 확인 시나리오 — Cycle 1 을 성공으로 닫고, Cycle 2 에서 Step 을 둘 걸은 뒤 검증을 연다.
fn the_scenario(dir: &Path) {
    bootstrap(dir);
    walk_to_the_exit_with(dir, "success");
    ok(dir, &["close"], Some(&cycle_handed_off("C2")));
    ok(dir, &["open", "experiment"], None);
    open_action(dir, "define");
    ok(dir, &["close"], Some(SECOND_DEFINE));
    open_action(dir, "hypothesis");
    ok(dir, &["close"], Some(SECOND_HYPOTHESIS));
    open_action(dir, "verify");
}

/// 그 글에서 값만 — `이름: 값` 의 첫 줄에서 값을 떼어 낸다.
fn value_of(report: &str, field: &str) -> String {
    report
        .lines()
        .find_map(|line| line.trim().strip_prefix(&format!("{field}: ")))
        .expect("그 칸이 있어야 한다")
        .to_string()
}

#[test]
fn the_context_projects_the_previous_cycle_without_expanding_its_step_graph() {
    let dir = scratch("cli-context");
    the_scenario(&dir);

    let told = ok(&dir, &["context"], None);
    let (previous, _) = told
        .split_once("═══ 현재 Cycle ═══")
        .expect("현재 Cycle 절이 없다 — 절을 가르는 표가 바뀌었다");

    // ① 이전 Cycle 이 무엇을 실험했고 무엇을 알아냈는가 — Cycle 해상도의 선택적 투영.
    assert!(previous.contains("Cycle 1"), "이전 Cycle 의 이름이 없다:\n{told}");
    for (source, field) in [(DEFINE, "problem"), (DEFINE, "success_condition")] {
        let value = value_of(source, field);
        assert!(
            previous.contains(&value),
            "이전 Cycle 의 Define.{field} 가 투영되지 않았다:\n{told}"
        );
    }
    assert!(
        previous.contains("이 실험에서 무엇을 배웠는지"),
        "가리켜진 Outcome 의 교훈이 투영되지 않았다:\n{told}"
    );
    assert!(
        previous.contains("숫자가 아닌 환경 변수는 기본값으로 떨어진다는 것을 확인했다."),
        "이전 Cycle 이 넘긴 것이 없다:\n{told}"
    );
    assert!(previous.contains("open_child"), "다음 방향이 없다:\n{told}");

    // ② 그러나 시도와 전환의 전개는 한 줄도 오지 않는다.
    for report in [HYPOTHESIS, VERIFY, ANALYSIS] {
        for line in report.lines().filter(|line| line.contains(": ")) {
            let value = line.split_once(": ").expect("방금 걸러 낸 줄이다").1.trim();
            assert!(
                !previous.contains(value),
                "이전 Cycle 의 Step Graph 가 펼쳐졌다: {value:?}\n{told}"
            );
        }
    }
    // Step 의 이름도, 가리키기만 한 참조의 값도 오지 않는다.
    for name in ["#1", "#2", "#3", "#4", "#5"] {
        assert!(
            !previous.contains(name),
            "이전 Cycle 의 Step ID {name} 이(가) 실렸다:\n{told}"
        );
    }
    assert!(
        !previous.contains("outcome_ref: 5"),
        "따라가기만 할 참조의 값이 실렸다:\n{told}"
    );

    // ③ 현재 Cycle 이 무엇을 이어받았고, 지금까지 무엇을 시도했는가.
    assert!(told.contains("Cycle 2"), "현재 Cycle 이 없다:\n{told}");
    assert!(
        told.contains(&value_of(SECOND_DEFINE, "problem")),
        "현재 Cycle 의 Define 이 없다:\n{told}"
    );
    assert!(
        told.contains(&value_of(SECOND_HYPOTHESIS, "hypothesis")),
        "현재 Cycle 의 Hypothesis 가 없다:\n{told}"
    );

    // ④ 지금 어디이고 다음에 무엇을 할 수 있는가.
    assert!(told.contains("verify"), "지금 열려 있는 자리가 없다:\n{told}");
    assert!(
        told.contains("gil close"),
        "다음에 무엇을 할 수 있는지 없다:\n{told}"
    );
    // ⑤ 그 자리를 닫으려면 무엇이 필요한가 — 명세에서 읽어 온 칸들.
    assert!(
        told.contains("execution") && told.contains("result"),
        "닫는 데 필요한 칸이 없다:\n{told}"
    );
}

#[test]
fn opening_a_node_does_not_reprint_the_whole_context() {
    // Context Model §9 — Node Open 은 전체 context 재전송 사건이 아니다. 같은 세션은 이미
    // 받은 것을 다시 받지 않는다. 전체는 사람이 `gil context` 를 부를 때만 나온다.
    let dir = scratch("cli-open-is-a-delta");
    the_scenario(&dir);
    ok(&dir, &["close"], Some(VERIFY));

    let opened = open_action(&dir, "analysis");
    assert!(
        !opened.contains("숫자가 아닌 환경 변수는 기본값으로 떨어진다는 것을 확인했다."),
        "Node 를 여는데 이전 Cycle 의 Report 가 딸려 나왔다:\n{opened}"
    );
    assert!(
        !opened.contains(&value_of(SECOND_DEFINE, "problem")),
        "Node 를 여는데 이 Cycle 의 지난 Step 이 딸려 나왔다:\n{opened}"
    );
    // 대신 지금 자리와 **지금 할 일**은 말한다 — 그것이 변화분이다.
    assert!(opened.contains("analysis"), "무엇을 열었는지 안 말한다:\n{opened}");
    assert!(opened.contains("지금 할 일"), "행동 계약을 안 되돌려 준다:\n{opened}");
    assert!(opened.contains("완료 조건"), "완료 조건을 안 되돌려 준다:\n{opened}");
}

#[test]
fn a_new_session_reads_the_context_in_another_process() {
    // 새 세션은 앞 프로세스의 대화를 하나도 물려받지 않는다. 그래도 한 번 읽고 이어 걸을 수
    // 있어야 한다 — 그 자리에서 실제로 다음 걸음을 뗀다.
    let dir = scratch("cli-context-across-processes");
    the_scenario(&dir);

    let told = ok(&dir, &["context"], None);
    assert!(told.contains("gil close"), "{told}");

    ok(&dir, &["close"], Some(VERIFY));
    let told = ok(&dir, &["context"], None);
    assert!(
        told.contains(&value_of(VERIFY, "execution")),
        "방금 적은 것이 문맥에 없다:\n{told}"
    );
    assert!(
        told.contains("analysis"),
        "다음에 열 수 있는 것을 안 말한다:\n{told}"
    );
}

#[test]
fn the_first_cycle_has_no_previous_section_in_the_cli() {
    let dir = scratch("cli-context-root");
    ok(&dir, &["start"], None);
    open_action(&dir, "question");
    ok(&dir, &["close"], Some(QUESTION));

    let told = ok(&dir, &["context"], None);
    assert!(
        !told.contains("이전 Cycle"),
        "이어받을 것이 없는데 빈 절을 냈다:\n{told}"
    );
    assert!(told.contains("뿌리"), "뿌리라고 말하지 않는다:\n{told}");
}

#[test]
fn the_context_needs_a_walk_to_read() {
    let dir = scratch("cli-context-without-a-walk");
    let said = refused(&dir, &["context"], None);
    assert!(said.contains("gil start"), "무엇부터 할지 안 말한다:\n{said}");
}

// ── Bootstrap Interview 부터 Experiment 까지, 프로세스 경계를 넘어 ─────────

#[test]
fn the_whole_path_from_start_to_an_experiment_works_across_processes() {
    // `gil start` → Interview 네 Step → Interview Close → Experiment 자식 →
    // define → hypothesis → verify → analysis → outcome.
    // **매 걸음이 다른 프로세스다.**
    let dir = scratch("cli-whole-path");

    let started = ok(&dir, &["start"], None);
    assert!(started.contains("interview"), "첫 Cycle 이 Interview 가 아니다:\n{started}");
    // 시작 출력은 **첫 행동으로 가는 길**을 가리킨다(Agent UX Model §4.1).
    assert!(
        started.contains("gil open"),
        "첫 행동으로 가는 길을 안 가리킨다:\n{started}"
    );
    // 이 Interview 와 무관한 Step Kind 를 늘어놓지 않는다.
    assert!(
        !started.contains("define"),
        "Interview 에서 define 을 안내했다:\n{started}"
    );

    for (kind, report) in [
        ("question", QUESTION),
        ("interpretation", INTERPRETATION),
        ("synthesis", SYNTHESIS),
        ("outcome", INTERVIEW_OUTCOME),
    ] {
        open_action(&dir, kind);
        ok(&dir, &["close"], Some(report));
    }

    let closed = ok(&dir, &["close"], Some(INTERVIEW_CYCLE));
    assert!(
        closed.contains("닫았다: cycle:C1"),
        "Interview 가 닫히지 않았다:\n{closed}"
    );

    let opened = ok(&dir, &["open", "experiment"], None);
    assert!(opened.contains("cycle:C2 · experiment"), "{opened}");
    assert!(opened.contains("부모 cycle:C1"), "부모를 안 말한다:\n{opened}");
    assert!(opened.contains("define"), "이제 define 을 열 수 있어야 한다:\n{opened}");

    walk_to_the_exit_with(&dir, "success");
    let said = ok(&dir, &["status"], None);
    assert!(
        said.contains("gil close"),
        "Experiment 를 닫을 수 있다고 말하지 않는다:\n{said}"
    );

    // 그리고 그 전부가 하나의 기록으로 남는다.
    let told = ok(&dir, &["story"], None);
    assert!(told.contains("Cycle 1 · interview"), "{told}");
    assert!(told.contains("Cycle 2 · experiment"), "{told}");
}

#[test]
fn an_interview_cannot_be_closed_before_a_synthesis_is_approved() {
    // 승인 없이는 판정을 열 수 없고, 판정이 없으면 Cycle 도 닫히지 않는다.
    let dir = scratch("cli-no-approval");
    ok(&dir, &["start"], None);
    open_action(&dir, "question");
    ok(&dir, &["close"], Some(QUESTION));
    open_action(&dir, "interpretation");
    ok(&dir, &["close"], Some(INTERPRETATION));

    // 사람이 아니라고 답한 제안.
    open_action(&dir, "synthesis");
    ok(
        &dir,
        &["close"],
        Some("statement: 이렇게 이해했다\nbasis_refs: |\n  step:C1/S1\napproved: no\n"),
    );

    let said = refused(&dir, &["open", "outcome"], Some(&contract_for("outcome")));
    assert!(
        said.contains("승인"),
        "왜 판정을 열 수 없는지 말하지 않는다:\n{said}"
    );
    refused(&dir, &["close"], Some(INTERVIEW_CYCLE));

    // 안내도 같은 말을 한다 — `no` 뒤에는 다시 묻는 길만 열린다.
    let status = ok(&dir, &["status"], None);
    assert!(status.contains("question"), "{status}");
    assert!(!status.contains("outcome"), "{status}");
}

#[test]
fn an_interview_outcome_must_point_at_the_approved_synthesis() {
    let dir = scratch("cli-synthesis-ref");
    ok(&dir, &["start"], None);
    for (kind, report) in [
        ("question", QUESTION),
        ("interpretation", INTERPRETATION),
        ("synthesis", SYNTHESIS),
    ] {
        open_action(&dir, kind);
        ok(&dir, &["close"], Some(report));
    }
    open_action(&dir, "outcome");

    // 화면의 축약은 저장 reference 가 아니다.
    let said = refused(
        &dir,
        &["close"],
        Some("verdict: success\nlesson: 배운 것\nsynthesis_ref: #3\n\
              next_direction:\n  action: close_cycle\n  reason: 끝났다\n"),
    );
    assert!(said.contains("종류"), "무엇이 틀렸는지 말하지 않는다:\n{said}");

    // 다른 Cycle 의 자리도 근거가 되지 않는다.
    let said = refused(
        &dir,
        &["close"],
        Some("verdict: success\nlesson: 배운 것\nsynthesis_ref: step:C9/S3\n\
              next_direction:\n  action: close_cycle\n  reason: 끝났다\n"),
    );
    assert!(said.contains("Cycle 1"), "어디여야 하는지 말하지 않는다:\n{said}");

    // 제안이 아닌 자리도 근거가 되지 않는다.
    let said = refused(
        &dir,
        &["close"],
        Some("verdict: success\nlesson: 배운 것\nsynthesis_ref: step:C1/S1\n\
              next_direction:\n  action: close_cycle\n  reason: 끝났다\n"),
    );
    assert!(said.contains("Synthesis"), "{said}");

    // 가리킨 것이 승인된 제안일 때만 닫힌다.
    ok(&dir, &["close"], Some(INTERVIEW_OUTCOME));
}

// ── Agent UX — 평상시 한 바퀴는 `start · open · close` 뿐이다 ──────────────

/// 그 명령이 실제로 부른 것을 세는 껍데기.
///
/// **부르지 않은 것을 부르지 않았다**는 것은 통과한 시험만으로는 증명되지 않는다.
/// 그래서 이 경로에서는 모든 호출을 여기로 지나게 하고 이름을 센다.
struct Walked {
    dir: PathBuf,
    called: Vec<String>,
}

impl Walked {
    fn new(label: &str) -> Walked {
        Walked {
            dir: scratch(label),
            called: Vec::new(),
        }
    }

    fn run(&mut self, args: &[&str], stdin: Option<&str>) -> String {
        self.called.push(args.join(" "));
        ok(&self.dir, args, stdin)
    }

    fn refuse(&mut self, args: &[&str], stdin: Option<&str>) -> String {
        self.called.push(args.join(" "));
        refused(&self.dir, args, stdin)
    }

    fn counted(&self, needle: &str) -> usize {
        self.called
            .iter()
            .filter(|call| call.starts_with(needle))
            .count()
    }
}

#[test]
fn the_daily_loop_needs_only_start_open_and_close() {
    // Agent UX Model §2 — 평상시에 반복하는 것은 셋뿐이고, 갈 곳이 하나인 자리에서는
    // 종류조차 적지 않는다. `gil context` 는 이 반복문에 들어가지 않는다.
    let mut gil = Walked::new("ux-daily-loop");

    let started = gil.run(&["start"], None);
    assert!(started.contains("gil open"), "첫 행동을 안 가리킨다:\n{started}");

    // ① 갈 곳이 하나 — 종류를 적지 않는다. 하려는 일은 **적는다.**
    let opened = gil.run(&["open"], Some(&contract_for("question")));
    assert!(opened.contains("열었다: step:C1/S1 · question"), "{opened}");
    for field in ["question", "choices", "response"] {
        assert!(opened.contains(field), "닫는 데 필요한 칸이 없다:\n{opened}");
    }
    // 여기서 `gil close` 를 강조하지 않는다 — 다음 수는 실제 세계에 있다.
    assert!(opened.contains("지금 할 일"), "행동 계약을 안 되돌려 준다:\n{opened}");

    let closed = gil.run(&["close"], Some(QUESTION));
    assert!(closed.contains("닫았다: step:C1/S1 · question"), "{closed}");
    assert!(closed.contains("interpretation"), "다음을 안 말한다:\n{closed}");

    // ② 또 하나뿐인 자리.
    let opened = gil.run(&["open"], Some(&contract_for("interpretation")));
    assert!(opened.contains("step:C1/S2 · interpretation"), "{opened}");
    let closed = gil.run(&["close"], Some(INTERPRETATION));

    // ③ 여기서만 갈래가 둘이다 — 고르라고 하고, 임의로 고르지 않는다.
    assert!(
        closed.contains("question") && closed.contains("synthesis"),
        "갈래를 안 보여 준다:\n{closed}"
    );
    assert!(closed.contains("gil open <종류>"), "{closed}");
    let asked = gil.refuse(&["open"], Some(&contract_for("synthesis")));
    assert!(asked.contains("무엇을 열지 정해야 한다"), "{asked}");

    gil.run(&["open", "synthesis"], Some(&contract_for("synthesis")));
    // ④ 승인이 다음 자리를 가른다 — yes 면 판정 하나뿐이다.
    let closed = gil.run(&["close"], Some(SYNTHESIS));
    assert!(
        closed.contains("열 수 있는 것: outcome"),
        "승인 뒤에도 갈래가 둘로 보인다:\n{closed}"
    );

    let opened = gil.run(&["open"], Some(&contract_for("outcome")));
    assert!(opened.contains("synthesis_ref"), "{opened}");
    let closed = gil.run(&["close"], Some(INTERVIEW_OUTCOME));

    // ⑤ 여기서 닫는 것은 Cycle 이다 — 그것도 `gil close` 가 판정한다.
    assert!(
        closed.contains("이 Cycle 의 Report") && closed.contains("gil close"),
        "Cycle 을 닫을 자리라고 말하지 않는다:\n{closed}"
    );
    let closed = gil.run(&["close"], Some(INTERVIEW_CYCLE));
    assert!(closed.contains("닫았다: cycle:C1 · interview · success"), "{closed}");
    assert!(closed.contains("gil open <종류>"), "{closed}");

    // ⑥ Cycle 을 여는 것도 같은 이름이다.
    let opened = gil.run(&["open", "experiment"], None);
    assert!(opened.contains("열었다: cycle:C2 · experiment"), "{opened}");
    let opened = gil.run(&["open"], Some(&contract_for("define")));
    assert!(opened.contains("step:C2/S1 · define"), "{opened}");

    // 그리고 이 경로가 실제로 쓴 명령은 셋뿐이다.
    assert_eq!(gil.counted("context"), 0, "평상시에 context 를 불렀다: {:?}", gil.called);
    assert_eq!(gil.counted("cycle"), 0, "옛 이름을 불렀다: {:?}", gil.called);
    assert_eq!(gil.counted("status"), 0, "{:?}", gil.called);
    assert!(
        gil.called
            .iter()
            .all(|call| call == "start" || call.starts_with("open") || call.starts_with("close")),
        "평상시 한 바퀴에 다른 명령이 섞였다: {:?}",
        gil.called
    );
}

#[test]
fn every_nudge_names_the_command_that_actually_works() {
    // 안내가 실행과 갈리면 그 안내는 없느니만 못하다(실사용 보고 #123).
    // **출력이 가리킨 그 명령을 그대로 쳐서** 한 바퀴를 돈다.
    let dir = scratch("ux-nudge-follows");
    let mut said = ok(&dir, &["start"], None);

    let reports = [
        QUESTION,
        INTERPRETATION,
        SYNTHESIS,
        INTERVIEW_OUTCOME,
        INTERVIEW_CYCLE,
    ];
    let mut next = 0;
    for _ in 0..14 {
        // Open Receipt 는 **일부러** 다음 명령을 가리키지 않는다(Agent UX Model §4.2) —
        // 다음 수는 CLI 가 아니라 실제 세계에 있다. 그 일을 마쳤다 치고 닫는다.
        let run = match nudge_of(&said) {
            Some(command) => command,
            None => {
                assert!(
                    said.starts_with("열었다") && said.contains("지금 할 일"),
                    "다음 수를 안 가리키는데 Open Receipt 도 아니다:\n{said}"
                );
                "gil close".to_string()
            }
        };

        // 고르라고 한 자리에서만 종류를 적는다.
        let args: Vec<&str> = match run.as_str() {
            "gil open <종류>" => vec!["open", "synthesis"],
            other => other.strip_prefix("gil ").expect("gil 명령이다").split(' ').collect(),
        };
        // 여는 자리에서는 행동 계약을, 닫는 자리에서는 Report 를 준다.
        let contract;
        let stdin = match args[0] {
            "close" => {
                let report = reports[next];
                next += 1;
                Some(report)
            }
            "open" if args.len() > 1 => {
                contract = contract_for(args[1]);
                Some(contract.as_str())
            }
            "open" => {
                contract = contract_for("");
                Some(contract.as_str())
            }
            _ => None,
        };
        said = ok(&dir, &args, stdin);
        if next == reports.len() {
            break;
        }
    }
    assert_eq!(next, reports.len(), "안내를 따라가 Interview 를 끝내지 못했다");
    let status = ok(&dir, &["status"], None);
    assert!(status.contains("닫힘"), "Interview 가 닫히지 않았다:\n{status}");
}

#[test]
fn a_typed_outcome_ref_is_the_only_one_accepted() {
    let dir = scratch("ux-typed-outcome-ref");
    bootstrap(&dir);
    walk_to_the_exit_with(&dir, "success");

    // bare 도, 화면 축약도 주소가 아니다.
    for bare in ["5", "#5"] {
        let said = refused(
            &dir,
            &["close"],
            Some(&cycle_handed_off("C2").replace("step:C2/S5", bare)),
        );
        assert!(said.contains("종류"), "왜 아닌지 안 말한다:\n{said}");
        assert!(
            said.contains("step:C2/S5"),
            "무엇을 적어야 하는지 안 말한다:\n{said}"
        );
    }
    // 다른 Cycle 의 자리도 아니다.
    let said = refused(
        &dir,
        &["close"],
        Some(&cycle_handed_off("C2").replace("step:C2/S5", "step:C1/S5")),
    );
    assert!(said.contains("step:C2/S5"), "{said}");

    // 판정이 아닌 자리도 아니다.
    let said = refused(
        &dir,
        &["close"],
        Some(&cycle_handed_off("C2").replace("step:C2/S5", "step:C2/S1")),
    );
    assert!(said.contains("step:C2/S5"), "{said}");

    ok(&dir, &["close"], Some(&cycle_handed_off("C2")));
}

#[test]
fn a_future_value_says_it_is_not_built_yet() {
    // Chain 을 아직 짓지 않았다. 명세에는 있지만 지금 밟을 수 있는 수가 아니다 —
    // 그 사실과 까닭을 함께 말한다.
    let dir = scratch("ux-close-chain");
    bootstrap_to_interview_exit(&dir);

    let said = refused(
        &dir,
        &["close"],
        Some(&INTERVIEW_CYCLE.replace("action: open_child", "action: close_chain")),
    );
    assert!(said.contains("아직"), "아직임을 말하지 않는다:\n{said}");
    assert!(said.contains("Chain"), "까닭을 말하지 않는다:\n{said}");
    assert!(said.contains("open_child"), "지금 쓸 수 있는 값을 안 말한다:\n{said}");
}

#[test]
fn an_empty_close_shows_the_shape_for_this_node() {
    // 빠진 칸만 말하지 않고 **지금 이 Node 의 골격**을 보여 준다.
    // 상관없는 예시를 보여 주면 읽는 쪽은 그것을 베끼고, 베낀 것은 또 거절당한다.
    let dir = scratch("ux-empty-close");
    ok(&dir, &["start"], None);
    open_action_here(&dir, "question");

    let said = refused(&dir, &["close"], Some(""));
    assert!(said.contains("step:C1/S1"), "어느 자리인지 안 말한다:\n{said}");
    for field in ["question", "choices", "response"] {
        assert!(said.contains(field), "{field} 가 골격에 없다:\n{said}");
    }
    assert!(said.contains("gil close <<'EOF'"), "골격이 없다:\n{said}");
    // 이 자리와 무관한 칸은 보여 주지 않는다.
    for other in ["problem", "hypothesis", "verdict"] {
        assert!(
            !said.contains(other),
            "이 Node 와 무관한 {other} 를 보여 준다:\n{said}"
        );
    }
}

/// 출력이 가리키는 **다음 명령**을 그대로 떼어 낸다.
///
/// 자리에 따라 두 꼴이다 — `실행` 블록이 있거나, 문장 안에 백틱으로 박혀 있거나.
/// 어느 쪽이든 출력은 다음에 칠 것을 반드시 말한다.
/// 출력이 가리키는 다음 명령. **가리키지 않는 출력도 있다** — Open Receipt 가 그렇다.
fn nudge_of(said: &str) -> Option<String> {
    if let Some((_, tail)) = said.rsplit_once("실행\n  ") {
        return Some(tail.lines().next().unwrap_or("").trim().to_string());
    }
    let (_, tail) = said.rsplit_once("`gil ")?;
    let (command, _) = tail.split_once('`')?;
    Some(format!("gil {command}"))
}

/// Interview 의 판정까지 닫아 **Cycle 을 닫을 자리**에 세운다.
fn bootstrap_to_interview_exit(dir: &Path) {
    ok(dir, &["start"], None);
    for (kind, report) in [
        ("question", QUESTION),
        ("interpretation", INTERPRETATION),
        ("synthesis", SYNTHESIS),
        ("outcome", INTERVIEW_OUTCOME),
    ] {
        open_action(dir, kind);
        ok(dir, &["close"], Some(report));
    }
}

// ── 고를 것이 여럿일 때만 설명이 나온다 ───────────────────────────────────

#[test]
fn choosing_a_cycle_kind_shows_the_descriptions_from_the_grammar() {
    // Cycle 을 여는 자리는 언제나 둘 중 하나다(Cycle Model §6). 그때만 설명이 나온다.
    let dir = scratch("ux-cycle-choices");
    bootstrap_to_interview_exit(&dir);
    let closed = ok(&dir, &["close"], Some(INTERVIEW_CYCLE));

    let rules = gil::RuleSet::builtin().unwrap();
    for kind in gil::CycleKind::ALL {
        let description = &rules.cycle_rules(kind).unwrap().description;
        assert!(
            closed.contains(kind.as_str()) && closed.contains(description.as_str()),
            "{kind} 의 설명이 문법에서 오지 않았다:\n{closed}"
        );
    }

    // 그리고 종류를 안 적으면 같은 설명으로 고르라고 한다.
    let asked = refused(&dir, &["open"], None);
    for kind in gil::CycleKind::ALL {
        let description = &rules.cycle_rules(kind).unwrap().description;
        assert!(asked.contains(description.as_str()), "{asked}");
    }
}

#[test]
fn a_single_choice_opens_without_repeating_any_description() {
    // 갈 곳이 하나면 묻지도, 설명하지도 않는다 — 설명은 **고를 때만** 필요하다.
    let dir = scratch("ux-single-choice");
    ok(&dir, &["start"], None);

    let opened = open_action_here(&dir, "question");
    assert!(opened.contains("step:C1/S1 · question"), "{opened}");

    let rules = gil::RuleSet::builtin().unwrap();
    for kind in gil::CycleKind::ALL {
        let description = &rules.cycle_rules(kind).unwrap().description;
        assert!(
            !opened.contains(description.as_str()),
            "고르지 않는 자리에서 {kind} 의 설명을 되풀이한다:\n{opened}"
        );
    }
}

#[test]
fn the_open_receipt_hands_control_to_the_real_work() {
    // Agent UX Model §4.2 — `gil open` 뒤의 다음 행동은 대개 CLI 명령이 아니다.
    // 별도 `실행` 블록으로 `gil close` 를 강조하면 Agent 가 **작업 전에** 닫는다.
    let dir = scratch("ux-open-hands-over");
    ok(&dir, &["start"], None);

    let opened = open_action_here(&dir, "question");
    assert!(
        !opened.contains("실행\n"),
        "열자마자 실행할 명령을 강조한다:\n{opened}"
    );
    // 대신 **적어 준 행동 계약**을 그대로 돌려준다 — 다음 수는 거기 적혀 있다.
    assert!(
        opened.contains("지금 할 일") && opened.contains("선택지와 함께 질문을 건넨다"),
        "무엇을 해야 하는지 안 말한다:\n{opened}"
    );
    assert!(
        opened.contains("완료 조건") && opened.contains("사용자의 원문 응답을 얻는다"),
        "무엇을 보면 끝인지 안 말한다:\n{opened}"
    );
    // objective 는 저장하되 Receipt 에서 무조건 되풀이하지 않는다(Agent UX Model §4.2).
    assert!(
        !opened.contains("사용자의 의도를 확인한다"),
        "objective 까지 장황하게 되풀이한다:\n{opened}"
    );

    // start 와 close 는 다음이 CLI 행동이므로 실행 블록을 그대로 갖는다.
    let closed = ok(&dir, &["close"], Some(QUESTION));
    assert!(closed.contains("실행\n"), "닫은 뒤 다음 명령을 안 가리킨다:\n{closed}");
}

#[test]
fn a_revisit_target_must_be_a_typed_step_address() {
    let dir = scratch("ux-typed-target");
    bootstrap(&dir);
    for (kind, report) in [
        ("define", DEFINE),
        ("hypothesis", HYPOTHESIS),
        ("verify", VERIFY),
        ("analysis", ANALYSIS),
    ] {
        open_action(&dir, kind);
        ok(&dir, &["close"], Some(report));
    }
    open_action(&dir, "outcome");

    let outcome = |target: &str| {
        format!(
            "verdict: failure\nlesson: 갈래를 다시 세운다\n\
             next_direction:\n  action: revisit\n  target_node_ref: {target}\n  reason: 가설부터 다시\n"
        )
    };
    // bare · 화면 축약 · Cycle 없는 이름 · 쉼표 목록 · 다른 Cycle.
    for bad in ["4", "#4", "S4", "step:C2/S4, step:C2/S1", "step:C9/S4"] {
        let said = refused(&dir, &["close"], Some(&outcome(bad)));
        assert!(
            said.contains("step:C2/S"),
            "{bad:?} 에 올바른 주소를 안 알려 준다:\n{said}"
        );
    }
    // 그리고 typed 주소는 통과한다.
    ok(&dir, &["close"], Some(&outcome("step:C2/S4")));
    let moved = ok(&dir, &["revisit"], None);
    assert!(moved.contains("#4"), "적어 둔 자리로 옮겨가지 않았다:\n{moved}");
}

// ── 행동 계약이 프로세스를 넘는다 ─────────────────────────────────────────

#[test]
fn an_action_step_without_a_contract_opens_nothing() {
    // 실행형 자리는 무엇을 하려는지 적지 않으면 열리지 않는다. 그리고 **아무것도 바뀌지
    // 않는다** — 상태를 반쯤 바꾸고 거절하면 다음 명령이 엉뚱한 자리에서 시작한다.
    let dir = scratch("will-no-contract");
    ok(&dir, &["start"], None);

    let said = refused(&dir, &["open"], None);
    assert!(said.contains("objective"), "무엇이 빠졌는지 안 말한다:\n{said}");
    assert!(said.contains("next_action") && said.contains("done_when"), "{said}");
    assert!(
        said.contains("gil open question <<'EOF'"),
        "적는 꼴을 안 보여 준다 — 어느 자리의 계약인지까지:\n{said}"
    );

    let status = ok(&dir, &["status"], None);
    assert!(
        status.contains("아직 아무것도 열지 않았다"),
        "거절됐는데 자리가 열렸다:\n{status}"
    );
    assert!(status.contains("걸린 행동이 없다"), "{status}");
}

#[test]
fn a_partial_contract_is_refused_as_one_failure() {
    let dir = scratch("will-partial-contract");
    ok(&dir, &["start"], None);
    let said = refused(
        &dir,
        &["open"],
        Some("objective: 사용자의 목표를 확인한다\nnext_action:   \n"),
    );
    assert!(
        said.contains("next_action") && said.contains("done_when"),
        "비운 칸과 빠뜨린 칸을 함께 말하지 않는다:\n{said}"
    );
    assert!(
        !said.contains("objective,"),
        "적은 칸까지 빠졌다고 말한다:\n{said}"
    );
}

#[test]
fn a_container_cycle_opens_without_a_contract() {
    // 그릇은 장기 Active Will 을 점유하지 않는다 — 계약을 요구하지 않는다.
    let dir = scratch("will-cycle-no-contract");
    bootstrap_to_interview_exit(&dir);
    ok(&dir, &["close"], Some(INTERVIEW_CYCLE));

    let opened = ok(&dir, &["open", "experiment"], None);
    assert!(opened.contains("열었다: cycle:C2 · experiment"), "{opened}");

    let status = ok(&dir, &["status"], None);
    assert!(
        status.contains("걸린 행동이 없다"),
        "Cycle 을 여는데 행동이 걸렸다:\n{status}"
    );
}

#[test]
fn the_action_contract_survives_the_process_boundary() {
    // **여기서만 잴 수 있는 것이다.** 여는 프로세스와 이어받는 프로세스가 다르다.
    // 이 절이 없어서 값을 치렀다: 상태는 복원했는데 무엇을 먼저 할지 몰라 작업 전에 닫았다.
    let dir = scratch("will-across-processes");
    ok(&dir, &["start"], None);
    ok(
        &dir,
        &["open"],
        Some(
            "objective: 사용자의 프로젝트 목표를 확인한다\n\
             next_action: 목표의 종류를 선택지와 함께 질문한다\n\
             done_when: 사용자의 원문 응답을 얻는다\n",
        ),
    );

    // 다른 프로세스가 짧게 묻는다 — 전체 Journey 를 펼치지 않는다.
    let status = ok(&dir, &["status"], None);
    assert!(status.contains("will:W1"), "행동의 이름이 없다:\n{status}");
    assert!(status.contains("step:C1/S1"), "어느 자리인지 없다:\n{status}");
    assert!(
        status.contains("목표의 종류를 선택지와 함께 질문한다"),
        "지금 할 일이 프로세스를 못 넘었다:\n{status}"
    );

    // 또 다른 프로세스가 이어받는다 — 여기서는 계약 전체가 온다.
    let told = ok(&dir, &["context"], None);
    for line in [
        "사용자의 프로젝트 목표를 확인한다",
        "목표의 종류를 선택지와 함께 질문한다",
        "사용자의 원문 응답을 얻는다",
        "step:C1/S1",
    ] {
        assert!(told.contains(line), "{line:?} 가 context 에 없다:\n{told}");
    }

    // 그리고 실제 작업을 마친 뒤에야 닫는다 — 그때 판이 하나 난다.
    let closed = ok(&dir, &["close"], Some(QUESTION));
    assert!(closed.contains("기록됨: journey:X1@J1"), "{closed}");

    let status = ok(&dir, &["status"], None);
    assert!(status.contains("걸린 행동이 없다"), "행동이 안 끝났다:\n{status}");
    assert!(status.contains("journey:X1@J1"), "판이 안 옮겨졌다:\n{status}");
}

#[test]
fn a_refused_close_keeps_the_will_active_across_processes() {
    // 실패한 transaction 뒤에도 열린 자리와 걸린 행동이 그대로여야 한다 — 그것이
    // 다음 프로세스가 보는 상태다.
    let dir = scratch("will-failed-close");
    ok(&dir, &["start"], None);
    open_action_here(&dir, "question");

    refused(&dir, &["close"], Some(""));
    refused(&dir, &["close"], Some("question: 칸이 모자란다\n"));

    let status = ok(&dir, &["status"], None);
    assert!(status.contains("will:W1"), "행동이 풀렸다:\n{status}");
    assert!(status.contains("#1 question (open)"), "자리가 닫혔다:\n{status}");
    assert!(status.contains("journey:X1@J0"), "판이 늘었다:\n{status}");
}

#[test]
fn a_cycle_close_makes_no_new_journey_revision() {
    // 컨테이너 Close 는 판을 만들지 않고 그때 서 있던 판을 provenance 로 적는다.
    let dir = scratch("will-cycle-no-revision");
    bootstrap_to_interview_exit(&dir);

    let before = ok(&dir, &["status"], None);
    let standing = before
        .lines()
        .find_map(|line| line.strip_prefix("존재: existence:X1 · "))
        .expect("서 있는 판을 말해야 한다")
        .to_string();
    assert_eq!(standing, "journey:X1@J4", "Interview 넷을 닫아 판이 넷 늘었다");

    let closed = ok(&dir, &["close"], Some(INTERVIEW_CYCLE));
    assert!(
        closed.contains(&format!("기록됨: {standing}")),
        "그때 서 있던 판을 안 적었다:\n{closed}"
    );
    assert!(closed.contains("판은 늘지 않는다"), "{closed}");

    let after = ok(&dir, &["status"], None);
    assert!(
        after.contains(&standing),
        "Cycle 을 닫으며 판이 옮겨졌다:\n{after}"
    );
}

// ── 상태에 민감한 도움말은 읽기만 한다 ────────────────────────────────────

/// 저장 파일을 바이트 그대로.
fn state_bytes(dir: &Path) -> Vec<u8> {
    std::fs::read(dir.join(gil::STATE_PATH)).expect("저장 파일이 있어야 한다")
}

#[test]
fn close_help_is_not_an_empty_close_request() {
    // 실사용 M2C — `gil close --help` 가 **stdin 없는 실제 Close** 로 처리됐다.
    // 계약을 물어본 사람이 빈 Report 를 낸 것으로 거절당했다.
    let dir = scratch("help-close-not-a-request");
    bootstrap(&dir);
    open_action(&dir, "define");

    let before = state_bytes(&dir);
    let said = ok(&dir, &["close", "--help"], None);
    assert_eq!(state_bytes(&dir), before, "help 가 저장을 건드렸다");

    assert!(said.contains("닫을 대상"), "{said}");
    assert!(said.contains("step:C2/S1 · define"), "{said}");
    assert!(said.contains("필요한 Report"), "{said}");
    assert!(said.contains("입력 골격"), "{said}");
    assert!(!said.contains("거절"), "도움말이 거절로 처리됐다:\n{said}");

    // 그리고 걸린 행동과 열린 자리가 그대로다.
    let status = ok(&dir, &["status"], None);
    assert!(status.contains("#1 define (open)"), "{status}");
    assert!(status.contains("하려는 것: will:"), "행동이 끝났다:\n{status}");
}

#[test]
fn open_help_changes_nothing_and_waits_for_nothing() {
    let dir = scratch("help-open-readonly");
    bootstrap(&dir);

    let before = state_bytes(&dir);
    // stdin 을 아예 닫아 둔다 — 기다리면 여기서 멈춘다.
    let said = ok(&dir, &["open", "--help"], None);
    assert_eq!(state_bytes(&dir), before, "help 가 저장을 건드렸다");
    assert!(said.contains("열 수 있는 것"), "{said}");
    assert!(said.contains("행동 계약"), "{said}");
    assert!(said.contains("objective") && said.contains("done_when"), "{said}");

    // 열린 자리도 걸린 행동도 생기지 않았다.
    let status = ok(&dir, &["status"], None);
    assert!(status.contains("아직 아무것도 열지 않았다"), "{status}");
    assert!(status.contains("걸린 행동이 없다"), "{status}");
}

#[test]
fn open_help_with_an_open_step_points_at_the_real_work() {
    let dir = scratch("help-open-while-open");
    bootstrap(&dir);
    open_action(&dir, "define");

    let before = state_bytes(&dir);
    let said = ok(&dir, &["open", "--help"], None);
    assert_eq!(state_bytes(&dir), before);

    assert!(said.contains("지금은 열 자리가 아니다"), "{said}");
    assert!(said.contains("step:C2/S1"), "{said}");
    assert!(said.contains("지금 할 일"), "행동 계약을 안 되짚어 준다:\n{said}");
    assert!(said.contains("gil close --help"), "{said}");
}

#[test]
fn open_help_at_a_cycle_boundary_asks_for_no_action_contract() {
    // 그릇은 행동 계약 없이 연다 — 그 차이가 이 자리에서 정확히 갈려야 한다.
    let dir = scratch("help-open-cycle");
    bootstrap_to_interview_exit(&dir);
    ok(&dir, &["close"], Some(INTERVIEW_CYCLE));

    let before = state_bytes(&dir);
    let said = ok(&dir, &["open", "--help"], None);
    assert_eq!(state_bytes(&dir), before);

    assert!(said.contains("열 수 있는 것 (Cycle)"), "{said}");
    assert!(said.contains("행동 계약 없이 연다"), "{said}");
    assert!(
        !said.contains("objective"),
        "Cycle 을 여는 자리에서 행동 계약을 요구한다:\n{said}"
    );

    let rules = gil::RuleSet::builtin().unwrap();
    for kind in gil::CycleKind::ALL {
        assert!(
            said.contains(rules.cycle_rules(kind).unwrap().description.as_str()),
            "{kind} 의 설명이 문법에서 오지 않았다:\n{said}"
        );
    }
}

#[test]
fn close_help_at_a_cycle_boundary_shows_the_cycle_contract() {
    let dir = scratch("help-close-cycle");
    bootstrap_to_interview_exit(&dir);

    let before = state_bytes(&dir);
    let said = ok(&dir, &["close", "--help"], None);
    assert_eq!(state_bytes(&dir), before);

    assert!(said.contains("cycle:C1 · interview"), "Cycle 계약이 아니다:\n{said}");
    assert!(said.contains("outcome_ref"), "{said}");
    assert!(said.contains("handoff_summary"), "{said}");
    // 계층이 갈린다 — Cycle Report 는 open_child 를 쓴다.
    assert!(said.contains("open_child"), "{said}");
    assert!(said.contains("다음 Cycle"), "계층을 안 밝힌다:\n{said}");
    assert!(!said.contains("close_cycle —"), "Step 계층의 값이 섞였다:\n{said}");
}

#[test]
fn close_help_where_there_is_nothing_to_close_says_what_comes_first() {
    let dir = scratch("help-close-nothing");
    bootstrap(&dir);

    let said = ok(&dir, &["close", "--help"], None);
    assert!(said.contains("닫을 자리가 아니다"), "{said}");
    assert!(said.contains("define"), "무엇을 먼저 해야 하는지 안 말한다:\n{said}");
    assert!(said.contains("gil open --help"), "{said}");
}

#[test]
fn help_without_a_project_points_at_start() {
    let dir = scratch("help-no-project");
    for command in [["close", "--help"], ["open", "--help"]] {
        let said = ok(&dir, &command, None);
        assert!(said.contains("프로젝트가 없다"), "{said}");
        assert!(said.contains("gil start"), "{said}");
        assert!(said.contains("start → open"), "한 바퀴를 안 알려 준다:\n{said}");
    }
    assert!(
        !dir.join(gil::STATE_PATH).exists(),
        "도움말이 걷기를 만들었다"
    );
}

// ── Receipt 가 닫기 전에 계약을 알려 준다 ─────────────────────────────────

#[test]
fn the_open_receipt_projects_the_allowed_values_before_the_error() {
    // 실사용 M2C — Agent 가 허용값을 오류를 통해서만 알아냈다. 그 자리가 여기다.
    let dir = scratch("receipt-constraints");
    bootstrap(&dir);
    for (kind, report) in [
        ("define", DEFINE),
        ("hypothesis", HYPOTHESIS),
        ("verify", VERIFY),
        ("analysis", ANALYSIS),
    ] {
        open_action(&dir, kind);
        ok(&dir, &["close"], Some(report));
    }

    let opened = open_action(&dir, "outcome");
    assert!(opened.contains("닫을 때 필요한 것"), "{opened}");
    for value in ["success", "failure", "revisit", "close_cycle"] {
        assert!(opened.contains(value), "{value} 를 미리 안 보여 준다:\n{opened}");
    }
    assert!(opened.contains("verdict가 success이면"), "조건부를 안 갈라 준다:\n{opened}");
    assert!(opened.contains("verdict가 failure이면"), "{opened}");

    // 다른 Node Kind 의 제약은 펼치지 않는다.
    for elsewhere in ["problem", "rationale", "handoff_summary", "outcome_ref"] {
        assert!(
            !opened.contains(elsewhere),
            "이 자리와 무관한 {elsewhere} 가 딸려 나왔다:\n{opened}"
        );
    }
}

#[test]
fn the_receipt_and_the_help_project_the_same_contract() {
    // 셋이 각자 문자열을 지으면 반드시 갈린다 — 하나만 고쳐 두고 다른 둘은 옛말을 한다.
    let dir = scratch("receipt-and-help-agree");
    bootstrap(&dir);
    let opened = open_action(&dir, "define");
    let helped = ok(&dir, &["close", "--help"], None);

    let block = |text: &str, head: &str| {
        let start = text.find(head).unwrap_or_else(|| panic!("{head} 가 없다:\n{text}"));
        text[start + head.len()..]
            .split("\n\n")
            .next()
            .unwrap_or_default()
            .trim_end()
            .to_string()
    };
    assert_eq!(
        block(&opened, "닫을 때 필요한 것\n"),
        block(&helped, "필요한 Report\n"),
        "Receipt 와 help 가 다른 계약을 말한다"
    );

    // 그리고 거절은 그 계약을 되풀이하지 않고 어디서 읽는지 가리킨다.
    let refused = refused(&dir, &["close"], Some(""));
    assert!(refused.contains("gil close --help"), "{refused}");
}

#[test]
fn a_step_choice_reads_its_one_line_from_the_grammar() {
    // 설명을 renderer 에 흩어 적지 않는다 — Kind 가 늘면 문법 한 자리만 고친다.
    let dir = scratch("choices-from-grammar");
    bootstrap(&dir);
    for (kind, report) in [
        ("define", DEFINE),
        ("hypothesis", HYPOTHESIS),
        ("verify", VERIFY),
        ("analysis", ANALYSIS),
    ] {
        open_action(&dir, kind);
        ok(&dir, &["close"], Some(report));
    }

    let said = ok(&dir, &["open", "--help"], None);
    let rules = gil::RuleSet::builtin().unwrap();
    for kind in [gil::NodeKind::Hypothesis, gil::NodeKind::Outcome] {
        let description = &rules
            .rules(gil::CycleKind::Experiment, kind)
            .unwrap()
            .description;
        assert!(
            said.contains(description.as_str()),
            "{kind} 의 설명이 문법에서 오지 않았다:\n{said}"
        );
    }
}
