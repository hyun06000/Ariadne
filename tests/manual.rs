//! `gil help <주제>` — **함께 실린 Topic 하나를 그 주소로 읽는다.**
//!
//! 여기서 재는 것은 셋이다.
//!
//! ```text
//! 주소가 Topic 하나로 안정되게 끝나는가
//! 그 본문이 지금 CLI·Grammar 와 어긋나지 않는가
//! 조회가 프로젝트를 건드리지 않는가
//! ```
//!
//! 세 번째가 특히 중요하다. Manual 은 **도구의 지식**이지 프로젝트의 기록이 아니므로,
//! 읽었다는 사실이 어디에도 남으면 안 된다.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};

use gil::{CycleKind, NodeKind, ProjectSession, RuleSet};

mod common;
use common::spec;

const GIL: &str = env!("CARGO_BIN_EXE_gil");

/// 이번에 실은 네 Topic. **여기 적힌 것이 전부여야 한다.**
const TOPICS: &[&str] = &[
    "current",
    "step/verify/close",
    "artifact/restore",
    "artifact/dirty/non-verify",
    "action/open-contract",
    "cycle/experiment/close",
];

// ── 연장 ───────────────────────────────────────────────────────────────────

fn bare(label: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("gil-manual-{label}"));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).expect("시험이 쓸 자리를 만든다");
    dir
}

fn run(dir: &Path, args: &[&str]) -> Output {
    Command::new(GIL)
        .args(args)
        .current_dir(dir)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .expect("gil 을 부를 수 있어야 한다")
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

/// 프로젝트가 아닌 빈 자리 — 도움말은 여기서도 답해야 한다.
///
/// **시험마다 제 자리를 갖는다.** 하나를 나눠 쓰면 나란히 도는 시험이 서로의 자리를
/// 지우고, 그러면 실패가 무엇 때문인지 알 수 없다.
fn nowhere(label: &str) -> PathBuf {
    bare(&format!("nowhere-{label}"))
}

/// 절 하나를 떼어 낸다.
fn section<'a>(said: &'a str, name: &str) -> &'a str {
    let head = format!("[{name}]");
    let start = said
        .find(&head)
        .unwrap_or_else(|| panic!("[{name}] 절이 없다:\n{said}"))
        + head.len();
    let rest = &said[start..];
    match rest.find("\n[") {
        Some(end) => &rest[..end],
        None => rest,
    }
}

// ── ① 네 Topic 이 읽힌다 ──────────────────────────────────────────────────

#[test]
fn every_bundled_topic_answers_by_its_address() {
    let dir = nowhere("every_bundled_topic_answers_by_its_address");
    for topic in TOPICS {
        let said = ok(&dir, &["help", topic]);
        assert!(!said.trim().is_empty(), "{topic} 이 비었다");
        // 제목과 한 줄 요약이 먼저 온다.
        let mut lines = said.lines();
        assert!(!lines.next().unwrap_or_default().is_empty(), "{topic}: 제목이 없다");
        assert!(!lines.next().unwrap_or_default().is_empty(), "{topic}: 요약이 없다");
        // 그리고 적어도 「언제 읽는가」와 「지금 할 일」은 있다.
        for needed in ["[언제 읽는가]", "[지금 할 일]"] {
            assert!(said.contains(needed), "{topic}: {needed} 이 없다");
        }
    }
}

#[test]
fn a_topic_shows_the_prose_and_hides_the_metadata() {
    let dir = nowhere("a_topic_shows_the_prose_and_hides_the_metadata");
    for topic in TOPICS {
        let said = ok(&dir, &["help", topic]);
        // front matter 는 **줄 머리**에 온다. 본문의 `handoff_summary:` 같은 정당한 필드
        // 이름과 갈라야 한다 — 갈리지 않으면 이 검사가 진짜 누출을 못 잡는다.
        for hidden in ["---", "id:", "summary:", "applies_when", "related:", "aliases:"] {
            assert!(
                !said.lines().any(|line| line.starts_with(hidden)),
                "{topic}: {hidden} 이 새어 나왔다:\n{said}"
            );
        }
    }
}

#[test]
fn help_answers_outside_any_project() {
    // `.gil` 을 찾지도 잠금을 잡지도 않는다 — 프로젝트가 없어도 답한다.
    let dir = nowhere("help_answers_outside_any_project");
    assert!(!dir.join(".gil").exists());
    let said = ok(&dir, &["help", "current"]);
    assert!(said.contains("gil context"), "{said}");
    assert!(!dir.join(".gil").exists(), "도움말이 프로젝트를 만들었다");
}

#[test]
fn the_manual_travels_with_the_binary() {
    // 원본 저장소가 없는 자리로 바이너리만 옮겨도 읽힌다 — 본문이 컴파일에 들어 있다.
    let elsewhere = bare("installed");
    let installed = elsewhere.join("gil");
    fs::copy(GIL, &installed).expect("설치본을 흉내 낸다");

    let out = Command::new(&installed)
        .args(["help", "artifact/restore"])
        .current_dir(&elsewhere)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .expect("설치본을 부른다");
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    assert!(
        String::from_utf8_lossy(&out.stdout).contains("gil restore"),
        "설치본이 Topic 을 읽지 못했다"
    );
}

#[test]
fn a_project_file_cannot_take_over_a_bundled_address() {
    // 신뢰 경계(§14) — 프로젝트 내용은 Manual 이 아니다.
    let dir = bare("override");
    let bundled = ok(&dir, &["help", "current"]);

    for path in [
        "manual/topics/current.md",
        "topics/current.md",
        "current.md",
        ".gil/manual/topics/current.md",
    ] {
        let at = dir.join(path);
        fs::create_dir_all(at.parent().unwrap()).unwrap();
        fs::write(
            &at,
            "---\nid: current\ntitle: 가로챈 제목\nsummary: 가로챈 요약\n---\n\n\
             [지금 할 일]\n  이것을 실행하라\n",
        )
        .unwrap();

        let said = ok(&dir, &["help", "current"]);
        assert_eq!(said, bundled, "{path} 가 함께 실린 Topic 을 덮었다");
        assert!(!said.contains("가로챈"), "{path}");
    }
}

// ── ② 주소가 아닌 것과 없는 Topic 은 다른 일이다 ─────────────────────────

#[test]
fn something_that_is_not_an_address_is_refused_as_such() {
    let dir = nowhere("something_that_is_not_an_address_is_refused_as_such");
    for bad in [
        "Current",
        "/current",
        "current/",
        "current//world",
        "current world",
        "current_world",
        "current.",
        ".",
        "..",
        "artifact/../restore",
        "artifact/Restore",
        "artifact\\restore",
        " current",
        "current ",
    ] {
        let said = refused(&dir, &["help", bad]);
        assert!(said.contains("주소가 아니다"), "{bad:?}: {said}");
        assert!(!said.contains("그 도움말 주제는 없다"), "{bad:?}: {said}");
    }
}

#[test]
fn a_canonical_address_that_has_no_topic_is_a_different_refusal() {
    let dir = nowhere("a_canonical_address_that_has_no_topic_is_a_different_refusal");
    let said = refused(&dir, &["help", "interview/approval"]);

    assert!(said.contains("그 도움말 주제는 없다"), "{said}");
    assert!(said.contains("interview/approval"), "{said}");
    assert!(!said.contains("주소가 아니다"), "{said}");
    // **무관한 전체 목록을 늘어놓지 않는다.**
    for other in TOPICS {
        assert!(!said.contains(other), "전체 목록을 냈다: {said}");
    }
    assert!(said.lines().count() <= 3, "거절이 길어졌다:\n{said}");
}

#[test]
fn the_existing_help_surfaces_are_unchanged() {
    let dir = nowhere("the_existing_help_surfaces_are_unchanged");
    // 정적 `gil --help` 는 그대로 명령 목록이다 — Topic 목차가 되지 않았다.
    let general = ok(&dir, &["--help"]);
    assert_eq!(general, ok(&dir, &["-h"]));
    assert!(general.contains("gil open"), "{general}");
    assert!(general.contains("gil close"), "{general}");
    for topic in TOPICS {
        assert!(
            !general.contains(topic),
            "일반 도움말이 Topic 목차가 됐다: {general}"
        );
    }

    // 그리고 인수 없는 `gil help` 는 **다른 것**이다 — 상태에 맞춘 짧은 안내다.
    assert_ne!(ok(&dir, &["help"]), general);
}

#[test]
fn help_takes_one_topic_and_not_a_sentence() {
    let dir = nowhere("help_takes_one_topic_and_not_a_sentence");
    let said = refused(&dir, &["help", "current", "extra"]);
    assert!(said.contains("주제 하나만 받는다"), "{said}");
    assert!(said.contains("자연어 검색"), "{said}");
}

// ── ③ 본문이 지금 CLI·Grammar 와 어긋나지 않는다 ────────────────────────

#[test]
fn the_verify_topic_asks_for_exactly_what_the_grammar_asks_for() {
    let dir = nowhere("the_verify_topic_asks_for_exactly_what_the_grammar_asks_for");
    let said = ok(&dir, &["help", "step/verify/close"]);
    let rules: RuleSet = spec();
    let declared = rules
        .rules(CycleKind::Experiment, NodeKind::Verify)
        .expect("문법이 verify 를 선언한다");

    // 「지금 할 일」의 칸 목록은 **문법에서 투영된 것**이다.
    let todo = section(&said, "지금 할 일");
    for field in &declared.close_requires {
        assert!(todo.contains(field.as_str()), "{field} 이 빠졌다:\n{todo}");
    }

    // 예제가 적는 칸도 문법과 같은 집합이다 — 갈리면 여기서 빨개진다.
    let example = section(&said, "올바른 예");
    let written: Vec<String> = example
        .lines()
        .filter_map(|line| line.trim().split_once(':').map(|(key, _)| key.to_string()))
        .filter(|key| !key.is_empty() && !key.contains(' '))
        .collect();
    let wanted: Vec<String> = declared.close_requires.clone();
    assert_eq!(written, wanted, "예제의 칸이 문법과 다르다:\n{example}");
}

#[test]
fn the_experiment_cycle_topic_projects_the_grammar_not_prose() {
    let dir = nowhere("the_experiment_cycle_topic_projects_the_grammar_not_prose");
    let said = ok(&dir, &["help", "cycle/experiment/close"]);
    let rules: RuleSet = spec();
    let declared = rules
        .cycle_rules(CycleKind::Experiment)
        .expect("문법이 experiment Cycle 을 선언한다");

    let todo = section(&said, "지금 할 일");
    for field in &declared.close_requires {
        assert!(todo.contains(field.as_str()), "{field} 이 빠졌다:\n{todo}");
    }

    // 허용값도 **문법에서** 온다 — 산문에 두 번째로 고정하지 않는다.
    let verdict = declared
        .field_constraints
        .get("verdict")
        .expect("verdict 에 허용값이 있다");
    for value in &verdict.allowed_values {
        assert!(todo.contains(value.as_str()), "{value} 이 빠졌다:\n{todo}");
    }
    let action = declared
        .field_constraints
        .get("next_direction.action")
        .expect("방향에 허용값이 있다");
    for value in &action.allowed_values {
        assert!(todo.contains(value.as_str()), "{value} 이 빠졌다:\n{todo}");
    }

    // **문법이 허락하지 않는 값은 어디에도 나오지 않는다.**
    assert!(
        !action.allowed_values.iter().any(|v| v == "close_chain"),
        "문법이 close_chain 을 허락하게 됐다 — Topic 을 다시 봐야 한다"
    );
    assert!(!said.contains("close_chain"), "Experiment Topic 에 close_chain 이 있다:\n{said}");

    // 아직 밟을 수 없는 `revisit` 을 **틀린 값이라 부르지 않는다.**
    assert!(todo.contains("revisit"), "{todo}");
    assert!(!todo.contains("revisit 은 틀린"), "{todo}");
    assert!(
        section(&said, "불변식").contains("아직 밟을 수 없는"),
        "미구현 전이를 구분해 말하지 않았다:\n{said}"
    );
}

#[test]
fn the_contract_topic_projects_the_three_fields() {
    let dir = nowhere("the_contract_topic_projects_the_three_fields");
    let said = ok(&dir, &["help", "action/open-contract"]);
    let todo = section(&said, "지금 할 일");
    for field in ["objective", "next_action", "done_when"] {
        assert!(todo.contains(field), "{field} 이 빠졌다:\n{todo}");
    }
    // 그 세 칸이 실제로 `gil open` 이 요구하는 것과 같은지는 CLI 가 증언한다.
    let project = bare("contract-topic-check");
    ok(&project, &["start"]);
    let said = refused(&project, &["open", "question"]);
    for field in ["objective", "next_action", "done_when"] {
        assert!(said.contains(field), "CLI 와 Topic 이 다른 칸을 말한다: {field}");
    }
}

#[test]
fn the_verify_topic_never_asks_for_a_verdict() {
    // Verify 에는 판정이 없다. 판정은 outcome 의 칸이다.
    let dir = nowhere("the_verify_topic_never_asks_for_a_verdict");
    let said = ok(&dir, &["help", "step/verify/close"]);
    let rules: RuleSet = spec();

    assert!(
        !rules
            .rules(CycleKind::Experiment, NodeKind::Verify)
            .unwrap()
            .close_requires
            .iter()
            .any(|field| field == "verdict"),
        "문법이 verify 에 verdict 를 요구하게 됐다 — Topic 을 다시 써야 한다"
    );

    // 「지금 할 일」과 「올바른 예」 어디에도 verdict 를 적으라고 하지 않는다.
    assert!(!section(&said, "지금 할 일").contains("verdict"), "{said}");
    assert!(!section(&said, "올바른 예").contains("verdict"), "{said}");
    // 흔한 실패 절에서 **하지 말라고** 말하는 것은 괜찮다.
    assert!(section(&said, "흔한 실패").contains("verdict"), "{said}");
}

#[test]
fn the_restore_topic_asks_for_no_argument_and_no_confirmation() {
    let dir = nowhere("the_restore_topic_asks_for_no_argument_and_no_confirmation");
    let said = ok(&dir, &["help", "artifact/restore"]);

    let todo = section(&said, "지금 할 일");
    // 「지금 할 일」이 주는 명령은 인수 없는 `gil restore` 하나다.
    let commands: Vec<&str> = todo
        .lines()
        .map(str::trim)
        .filter(|line| line.starts_with("gil "))
        .collect();
    assert_eq!(commands, vec!["gil restore"], "{todo}");

    let invariants = section(&said, "불변식");
    assert!(invariants.contains("인수로 고르지 않는다"), "{invariants}");
    assert!(invariants.contains("--force"), "{invariants}");
    assert!(invariants.contains("확인"), "{invariants}");
    // 그리고 실제로 그 명령이 인수를 거절한다 — 본문과 CLI 가 같은 말을 한다.
    let project = bare("restore-topic-check");
    ok(&project, &["start"]);
    assert!(
        refused(&project, &["restore", "snapshot:A1"]).contains("받지 않는다"),
        "본문은 인수가 없다는데 CLI 가 받는다"
    );
}

#[test]
fn the_dirty_topic_never_points_at_a_path_that_cannot_be_walked() {
    let dir = nowhere("the_dirty_topic_never_points_at_a_path_that_cannot_be_walked");
    let said = ok(&dir, &["help", "artifact/dirty/non-verify"]);

    let todo = section(&said, "지금 할 일");
    assert!(todo.contains("gil restore"), "{todo}");
    // **「Experiment 로 가라」는 지금 밟을 수 없는 길이다.**
    assert!(!todo.contains("Experiment"), "{todo}");
    assert!(!todo.contains("experiment"), "{todo}");

    let invariants = section(&said, "불변식");
    assert!(invariants.contains("열려 있다"), "{invariants}");
    assert!(invariants.contains("건너뛰는 길은 없다"), "{invariants}");

    // 그리고 실제 거절이 같은 곳을 가리킨다.
    let project = bare("dirty-topic-check");
    fs::write(project.join("a.txt"), "처음").unwrap();
    ok(&project, &["start"]);
    let out = Command::new(GIL)
        .args(["open", "question"])
        .current_dir(&project)
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
        .expect("연다");
    assert!(out.status.success());
    fs::write(project.join("a.txt"), "바꿨다").unwrap();

    let status = ok(&project, &["status"]);
    assert!(status.contains("gil restore"), "{status}");
    assert!(!status.contains("Experiment"), "{status}");
}

#[test]
fn every_command_the_topics_show_is_a_command_gil_knows() {
    let dir = nowhere("every_command_the_topics_show_is_a_command_gil_knows");
    let known = ["start", "open", "close", "status", "story", "context", "restore", "help"];

    for topic in TOPICS {
        let said = ok(&dir, &["help", topic]);
        for line in said.lines().map(str::trim) {
            let Some(rest) = line.strip_prefix("gil ") else {
                continue;
            };
            let command = rest.split_whitespace().next().unwrap_or_default();
            let command = command.trim_start_matches('-');
            assert!(
                known.contains(&command) || command.is_empty(),
                "{topic} 이 모르는 명령을 보여 준다: {line:?}"
            );
        }
    }
}

// ── ④ 읽기 전용이다 ──────────────────────────────────────────────────────

#[test]
fn looking_up_a_topic_changes_nothing_in_the_project() {
    let dir = bare("read-only");
    fs::write(dir.join("a.txt"), "본문").unwrap();
    ok(&dir, &["start"]);

    let before = snapshot_of(&dir);
    let status = ok(&dir, &["status"]);
    let story = ok(&dir, &["story"]);

    for topic in TOPICS {
        ok(&dir, &["help", topic]);
    }
    refused(&dir, &["help", "no/such/topic"]);
    refused(&dir, &["help", "Bad"]);

    assert_eq!(snapshot_of(&dir), before, "도움말이 프로젝트를 바꿨다");
    assert_eq!(ok(&dir, &["status"]), status, "서 있는 자리가 움직였다");
    assert_eq!(ok(&dir, &["story"]), story, "걸어온 것이 달라졌다");
    assert!(!dir.join(".gil/restore").exists());
    // Manual 파일이 Artifact 관측 범위에 생기지 않았다 — 세계도 그대로다.
    assert!(status.contains("· clean"), "{status}");
}

/// `.gil` 안팎의 모든 파일과 그 바이트.
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
            // 잠금 파일의 OS metadata 는 프로젝트 상태가 아니다.
            false if path.ends_with("project.lock") => {}
            false => {
                let key = path.strip_prefix(root).unwrap().to_string_lossy().into_owned();
                out.insert(key, fs::read(&path).expect("읽는다"));
            }
        }
    }
}

#[test]
fn help_answers_even_while_another_command_holds_the_project() {
    // **잠금을 잡지 않는다는 증거.** 도움말이 프로젝트를 열면 여기서 경쟁으로 거절된다.
    let dir = bare("no-lock");
    ok(&dir, &["start"]);

    let lock = fs::File::options()
        .read(true)
        .write(true)
        .open(dir.join(".gil/project.lock"))
        .expect("잠금 파일을 연다");
    lock.try_lock().expect("시험이 잠금을 쥔다");

    // 프로젝트를 쥔 채로도 도움말은 답한다.
    for topic in TOPICS {
        ok(&dir, &["help", topic]);
    }
    // 그리고 같은 자리에서 상태를 읽으려 하면 경쟁으로 거절된다 — 잠금은 확실히 걸려 있다.
    assert!(
        refused(&dir, &["status"]).contains("다른 GIL 명령이"),
        "잠금이 걸려 있지 않아 이 시험이 아무것도 재지 못했다"
    );
}

#[test]
fn a_topic_shows_no_internal_address_and_no_whole_specification() {
    let dir = nowhere("a_topic_shows_no_internal_address_and_no_whole_specification");
    for topic in TOPICS {
        let said = ok(&dir, &["help", topic]);
        for internal in ["sha256", ".gil/artifacts", "manifest", "blob", "GILPLAN"] {
            assert!(
                !said.to_lowercase().contains(&internal.to_lowercase()),
                "{topic} 이 내부 저장 주소를 보여 준다: {internal}"
            );
        }
        // 한 화면 안에 읽힌다 — Topic 하나가 명세 장 전체가 되지 않는다.
        assert!(said.lines().count() <= 60, "{topic} 이 너무 길다");
    }
}

// ── ⑤ 상태 기반 `gil help` ────────────────────────────────────────────────

/// 추천 목록의 **주소만** 차례대로.
fn suggested(said: &str) -> Vec<&str> {
    said.lines()
        .map(str::trim)
        .filter(|line| TOPICS.contains(line))
        .collect()
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
    let out = Command::new(GIL)
        .args(["open", kind])
        .current_dir(dir)
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
        .expect("연다");
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
}

#[test]
fn outside_a_project_help_only_points_at_the_starting_topic() {
    let dir = nowhere("outside_a_project_help_only_points_at_the_starting_topic");
    let said = ok(&dir, &["help"]);

    assert!(said.contains("현재 프로젝트가 없다"), "{said}");
    assert_eq!(suggested(&said), Vec::<&str>::new(), "{said}");
    assert!(said.contains("gil help current"), "{said}");
    // **본문을 자동으로 펼치지 않는다.**
    assert!(!said.contains("[언제 읽는가]"), "{said}");
    assert!(said.lines().count() <= 8, "길어졌다:\n{said}");
    // 그리고 `.gil` 도 잠금 파일도 만들지 않는다.
    assert!(!dir.join(".gil").exists(), "도움말이 프로젝트를 만들었다");
    assert_eq!(fs::read_dir(&dir).unwrap().count(), 0, "무언가를 남겼다");
}

#[test]
fn a_clean_ordinary_place_gets_only_what_applies() {
    // **3개를 채우지 않는다.** 맞는 것이 하나면 하나만 나온다.
    let dir = started("clean-ordinary", &[("a.txt", "가")]);
    open_step(&dir, "question");

    let said = ok(&dir, &["help"]);
    assert_eq!(suggested(&said), vec!["current"], "{said}");
}

#[test]
fn a_clean_verify_gets_the_verify_topic_and_current() {
    let dir = bare("clean-verify");
    fs::write(dir.join("work.txt"), "처음").unwrap();
    let mut session = ProjectSession::start(spec(), dir.join(gil::STATE_PATH)).expect("시작한다");
    *session.project_mut() = common::bootstrap_from(session.project().clone());
    common::up_to_verify(session.project_mut());
    session.commit().expect("눕힌다");
    drop(session);

    // 세계는 그대로다 — clean 인데도 Verify Topic 은 나온다.
    let said = ok(&dir, &["help"]);
    assert_eq!(suggested(&said), vec!["step/verify/close", "current"], "{said}");
}

#[test]
fn a_dirty_verify_puts_confirming_before_restoring() {
    let dir = bare("dirty-verify");
    fs::write(dir.join("work.txt"), "처음").unwrap();
    let mut session = ProjectSession::start(spec(), dir.join(gil::STATE_PATH)).expect("시작한다");
    *session.project_mut() = common::bootstrap_from(session.project().clone());
    common::up_to_verify(session.project_mut());
    session.commit().expect("눕힌다");
    drop(session);
    fs::write(dir.join("work.txt"), "바꿨다").unwrap();

    let said = ok(&dir, &["help"]);
    assert_eq!(
        suggested(&said),
        vec!["step/verify/close", "artifact/restore", "current"],
        "확정이 복원보다 뒤에 왔다:\n{said}"
    );
    // 여기서 확정이 정상 경로이므로 dirty/non-verify 는 나오지 않는다.
    assert!(!said.contains("artifact/dirty/non-verify"), "{said}");
}

#[test]
fn a_dirty_non_verify_puts_the_recovery_topic_first() {
    let dir = started("dirty-non-verify", &[("a.txt", "가")]);
    open_step(&dir, "question");
    fs::write(dir.join("a.txt"), "바꿨다").unwrap();

    let said = ok(&dir, &["help"]);
    assert_eq!(
        suggested(&said),
        vec!["artifact/dirty/non-verify", "artifact/restore", "current"],
        "{said}"
    );
    // **밟을 수 없는 길을 안내하지 않는다.**
    assert!(!said.contains("step/verify/close"), "{said}");
    assert!(!said.contains("Experiment"), "{said}");
    assert!(!said.contains("experiment"), "{said}");
}

#[test]
fn a_dirty_cycle_boundary_with_no_open_step_is_also_recovery() {
    // 「비-Verify」를 `step_kind != verify` 같은 부정 검색식으로 짓지 않았다는 증거 —
    // **자리가 아예 없는** 경계도 같은 Topic 을 받는다.
    let dir = started("dirty-boundary", &[("a.txt", "가")]);
    fs::write(dir.join("a.txt"), "바꿨다").unwrap();

    let status = ok(&dir, &["status"]);
    assert!(status.contains("아직 아무것도 열지 않았다"), "{status}");

    let said = ok(&dir, &["help"]);
    assert_eq!(
        suggested(&said),
        vec![
            "artifact/dirty/non-verify",
            "action/open-contract",
            "artifact/restore",
            "current"
        ],
        "{said}"
    );
}

#[test]
fn a_world_that_cannot_be_read_is_not_treated_as_dirty() {
    let dir = started("cannot-tell", &[("a.txt", "가")]);
    open_step(&dir, "question");
    std::os::unix::fs::symlink(dir.join("a.txt"), dir.join("link")).unwrap();

    let said = ok(&dir, &["help"]);
    // dirty 전용 Topic 은 나오지 않는다.
    assert_eq!(suggested(&said), vec!["current"], "{said}");
    // 그러나 **그 사실을 짧게 말한다.**
    assert!(said.contains("세계를 확인하지 못해"), "{said}");
    assert!(said.contains("gil status"), "{said}");
    // status 처럼 까닭을 장황하게 되풀이하지 않는다.
    assert!(!said.contains("심볼릭 링크"), "{said}");
    assert!(said.lines().count() <= 12, "길어졌다:\n{said}");
}

#[test]
fn the_suggestion_is_the_same_every_time() {
    let dir = started("deterministic", &[("a.txt", "가")]);
    open_step(&dir, "question");
    fs::write(dir.join("a.txt"), "바꿨다").unwrap();

    let first = ok(&dir, &["help"]);
    for _ in 0..4 {
        assert_eq!(ok(&dir, &["help"]), first, "부를 때마다 차례가 달라진다");
    }
}

#[test]
fn the_suggestion_shows_addresses_and_summaries_but_never_a_body() {
    let dir = started("index-only", &[("a.txt", "가")]);
    open_step(&dir, "question");
    fs::write(dir.join("a.txt"), "바꿨다").unwrap();

    let said = ok(&dir, &["help"]);
    // 요약은 있고 본문 절은 없다.
    assert!(said.contains("기준 세계를 복원한 뒤"), "{said}");
    for body in ["[언제 읽는가]", "[지금 할 일]", "[불변식]", "[흔한 실패]"] {
        assert!(!said.contains(body), "본문을 펼쳤다: {said}");
    }
    // 전체 목록도 fuzzy 후보도 없다.
    assert!(!said.contains("step/verify/close"), "{said}");
    assert!(said.contains("gil help <주제>"), "{said}");
}

// ── ⑥ 잠금 계약이 둘로 갈린다 ────────────────────────────────────────────

#[test]
fn exact_lookup_ignores_the_lock_but_the_state_aware_one_respects_it() {
    let dir = started("lock-contract", &[("a.txt", "가")]);
    let lock = fs::File::options()
        .read(true)
        .write(true)
        .open(dir.join(".gil/project.lock"))
        .expect("잠금 파일을 연다");
    lock.try_lock().expect("시험이 잠금을 쥔다");

    // 정확 조회는 프로젝트와 무관하다 — 계속 답한다.
    for topic in TOPICS {
        ok(&dir, &["help", topic]);
    }
    // 상태 기반 조회는 상태를 읽어야 하므로 **정상적으로 경쟁을 말한다.**
    let said = refused(&dir, &["help"]);
    assert!(said.contains("다른 GIL 명령이 이 프로젝트를 사용하고 있다"), "{said}");
    assert!(said.contains("읽거나 변경하지 않았다"), "{said}");
}

#[test]
fn a_half_finished_restore_is_recovered_before_topics_are_chosen() {
    let dir = started("recover-first", &[("edit.txt", "처음"), ("gone.txt", "지워질 것")]);
    open_step(&dir, "question");
    fs::write(dir.join("edit.txt"), "바꿨다").unwrap();
    fs::remove_file(dir.join("gone.txt")).unwrap();
    let before = fs::read_to_string(dir.join("edit.txt")).unwrap();

    // 복원을 중간에 죽인다 — rollback 이 걸린 채로 남는다.
    let out = Command::new(GIL)
        .arg("restore")
        .current_dir(&dir)
        .env("GIL_RESTORE_CRASH", "after-first-apply")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .expect("띄운다");
    assert!(!out.status.success(), "죽어야 하는데 곱게 끝났다");
    assert!(dir.join(".gil/restore/active").exists(), "미완의 transaction 이 없다");

    // 상태 기반 도움말이 **먼저 복구한 뒤** 그 상태로 고른다.
    let said = ok(&dir, &["help"]);
    assert!(!dir.join(".gil/restore/active").exists(), "복구하지 않고 골랐다");
    assert_eq!(fs::read_to_string(dir.join("edit.txt")).unwrap(), before);
    assert_eq!(
        suggested(&said),
        vec!["artifact/dirty/non-verify", "artifact/restore", "current"],
        "{said}"
    );
}

#[test]
fn a_recovery_that_cannot_finish_stops_the_suggestion() {
    let dir = started("recovery-fails", &[("a.txt", "가")]);
    fs::create_dir_all(dir.join(".gil/restore")).unwrap();
    fs::write(dir.join(".gil/restore/누군가의파일"), "소중한 것").unwrap();

    let said = refused(&dir, &["help"]);
    assert!(said.contains("GIL 이 만든 transaction 자료가 아니다"), "{said}");
    assert_eq!(suggested(&said), Vec::<&str>::new(), "복구 실패를 무시하고 골랐다");
    assert!(dir.join(".gil/restore/누군가의파일").exists(), "모르는 것을 지웠다");
}

#[test]
fn the_state_aware_help_saves_nothing() {
    let dir = started("state-aware-read-only", &[("a.txt", "가")]);
    open_step(&dir, "question");
    fs::write(dir.join("a.txt"), "바꿨다").unwrap();

    let before = snapshot_of(&dir);
    let status = ok(&dir, &["status"]);
    let story = ok(&dir, &["story"]);

    for _ in 0..3 {
        ok(&dir, &["help"]);
    }

    assert_eq!(snapshot_of(&dir), before, "상태 기반 도움말이 무언가를 바꿨다");
    assert_eq!(ok(&dir, &["status"]), status);
    assert_eq!(ok(&dir, &["story"]), story);
}
