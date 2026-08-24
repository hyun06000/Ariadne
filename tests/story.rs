//! 걸어온 것을 사람의 말로 읽는다.
//!
//! 여기서 재는 것은 **문구가 아니라 규칙**이다. 이야기가 예쁜지는 상현님이 읽고 판정한다 —
//! 시험이 재는 것은 "적힌 것이 조용히 사라지지 않는가" 하나다. 문구를 다듬을 때마다
//! 빨개지는 시험은 무시되고, 무시되는 시험은 없는 것과 같다.

use std::collections::BTreeMap;

use gil::{CycleKind, NodeId, NodeKind, Project, Report, story};

mod common;
use common::{
    bootstrap,
    ACTION, REASON, TARGET, graph_at_the_exit, cycle_report, cycle_step, full_report, spec,
};

/// 한 줄기를 걷고, 되돌아가겠다고 적고, 갈래의 첫 가설을 연 Cycle Graph.
fn cycle_with_a_branch() -> Project {
    let mut project = bootstrap();
    let cycle = project.cycles_mut().current_mut();
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        cycle_step(cycle, kind);
    }
    let target = cycle.steps().nodes()[3].id;

    cycle.open_step(NodeKind::Outcome).unwrap();
    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", "failure")
        .with(ACTION, "revisit")
        .with(TARGET, cycle.step_ref(target).to_string())
        .with(REASON, "해석까지는 유효하다");
    cycle.close_step(report).unwrap();

    cycle.revisit_step().unwrap();
    cycle.open_step(NodeKind::Hypothesis).unwrap();
    project
}

#[test]
fn nothing_a_person_wrote_disappears_from_the_story() {
    // 사람이 제 말로 적은 칸은 한 글자도 사라지면 안 된다. 사라지면 그 칸은
    // 적으라고 요구해 놓고 아무도 안 읽는 칸이 된다.
    //
    // 명세가 값을 열거해 둔 칸은 여기서 재지 않는다 — 그건 우리가 정한 낱말이고,
    // 이야기가 사람의 말로 옮기는 것이 의도다. 그쪽은 아래 시험이 따로 잰다.
    let project = cycle_with_a_branch();
    let told = story(project.cycles());
    let rules = spec();

    let mut checked = 0;
    for node in project.cycles().current().steps().history() {
        let step = rules.rules(CycleKind::Experiment, node.kind).unwrap();
        let report = node.report.as_ref().unwrap();
        for field in &step.close_requires {
            let enumerated = step
                .field_constraints
                .get(field)
                .is_some_and(|constraint| !constraint.allowed_values.is_empty());
            if enumerated {
                continue;
            }
            let value = report.get(field).unwrap();
            assert!(
                told.contains(value),
                "{} 의 {field} 가 이야기에서 사라졌다:\n{told}",
                node.id
            );
            checked += 1;
        }
    }
    assert!(checked > 0, "잰 칸이 하나도 없다");
}

#[test]
fn a_word_the_spec_chose_still_changes_the_story() {
    // 열거된 값은 옮겨 적혀도 좋다. 다만 **이야기에 닿아야** 한다 —
    // 값이 달라졌는데 이야기가 같으면 그 칸은 화면에서 사라진 것이다.
    let rules = spec();
    let constraint = rules
        .rules(CycleKind::Experiment, NodeKind::Outcome)
        .unwrap()
        .field_constraints
        .get("verdict")
        .expect("판정의 결과는 값이 열거된 칸이다");
    assert!(
        constraint.allowed_values.len() >= 2,
        "값이 하나뿐이면 이 시험은 아무것도 재지 못한다"
    );

    let told: Vec<String> = constraint
        .allowed_values
        .iter()
        .map(|verdict| story(graph_at_the_exit(verdict).0.cycles()))
        .collect();

    assert_ne!(told[0], told[1], "결과가 달라졌는데 이야기가 같다:\n{}", told[0]);
}

#[test]
fn a_field_the_story_has_no_name_for_still_shows_up() {
    // 이름표가 없는 칸은 제 이름 그대로 나온다. 모르는 칸을 조용히 버리면
    // 명세에 칸이 늘어날 때 이야기가 말없이 낡는다.
    let mut project = bootstrap();
    let cycle = project.cycles_mut().current_mut();
    cycle.open_step(NodeKind::Define).unwrap();
    let report: Report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Define)
        .with("weather_at_the_time", "비가 왔다");
    cycle.close_step(report).unwrap();

    let told = story(project.cycles());
    assert!(
        told.contains("weather_at_the_time") && told.contains("비가 왔다"),
        "이름표 없는 칸이 사라졌다:\n{told}"
    );
}

#[test]
fn the_story_says_where_a_branch_came_from() {
    // "왜 돌아갔나" 는 여덟 물음 중 하나다. 갈래가 어느 판정에서 났는지 말하지 않으면
    // 읽는 사람은 두 시도가 나란한 것인지 이어진 것인지 알 수 없다.
    let project = cycle_with_a_branch();
    let walk = project.cycles().current().steps();
    let outcome = walk
        .nodes()
        .iter()
        .find(|node| node.kind == NodeKind::Outcome)
        .unwrap();
    let branch = walk.nodes().last().unwrap();

    let told = story(project.cycles());
    let line = told
        .lines()
        .find(|line| line.contains(&branch.id.to_string()))
        .unwrap_or_else(|| panic!("갈래의 첫 가설이 이야기에 없다:\n{told}"));
    assert!(
        line.contains(&outcome.id.to_string()),
        "갈래가 어디서 났는지 말하지 않는다: {line}"
    );
}

#[test]
fn what_is_still_being_written_is_not_told_as_done() {
    let project = cycle_with_a_branch();
    let open = project.cycles().current().steps().nodes().last().unwrap();
    assert!(open.report.is_none(), "이 자리는 열려 있어야 한다");

    let told = story(project.cycles());
    assert!(
        told.contains("아직"),
        "열린 자리를 다 적은 것처럼 말한다:\n{told}"
    );
}

#[test]
fn an_empty_walk_still_tells_where_to_begin() {
    // 아무것도 안 적은 Cycle 도 이야기가 있다 — "여기서 시작한다" 는 것.
    let told = story(Project::start(spec()).cycles());
    assert!(!told.trim().is_empty(), "빈 Cycle 의 이야기가 비었다");
}

// ── Cycle 이 남긴 것 ───────────────────────────────────────────────────────

/// 첫 판정이 failure 라 되돌아가고, 두 번째 판정이 success 인 Cycle.
///
/// 돌려주는 것은 (Cycle, **지나간** 판정의 lesson, **마지막** 판정의 id).
fn cycle_with_two_outcomes() -> (Project, String, NodeId) {
    let mut project = bootstrap();
    let cycle = project.cycles_mut().current_mut();
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        cycle_step(cycle, kind);
    }
    let branch_point = cycle.steps().nodes()[3].id;

    let past_lesson = "지나간 판정의 교훈 — 이야기에 나오면 안 된다";
    cycle.open_step(NodeKind::Outcome).unwrap();
    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", "failure")
        .with("lesson", past_lesson)
        .with(ACTION, "revisit")
        .with(TARGET, cycle.step_ref(branch_point).to_string())
        .with(REASON, "다른 가설을 세운다");
    cycle.close_step(report).unwrap();
    cycle.revisit_step().unwrap();

    for kind in [NodeKind::Hypothesis, NodeKind::Verify, NodeKind::Analysis] {
        cycle_step(cycle, kind);
    }
    cycle.open_step(NodeKind::Outcome).unwrap();
    let last = cycle.steps().current().unwrap();
    let report = full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
        .with("verdict", "success")
        .with("lesson", "마지막 판정의 교훈")
        .with(ACTION, "close_cycle")
        .with(REASON, "결론에 닿았다");
    cycle.close_step(report).unwrap();

    (project, past_lesson.to_string(), last)
}

/// 이야기에서 **Cycle 절만** 떼어 낸다 — Step 을 펼치지 않은 협업자가 보는 것.
fn cycle_section(told: &str) -> String {
    // 이야기에는 Bootstrap Interview 의 절이 먼저 온다. 재려는 것은 **방금 닫은 Cycle** 이므로
    // 마지막 절을 떼어 낸다.
    let (_, tail) = told
        .rsplit_once("이 Cycle 이 남긴 것")
        .unwrap_or_else(|| panic!("Cycle 절이 없다:\n{told}"));
    // 제목줄의 나머지(종류·판정)는 절의 머리지 블록이 아니다.
    match tail.split_once('\n') {
        Some((_, body)) => body.to_string(),
        None => String::new(),
    }
}

/// Cycle 절을 **블록으로 되읽는다.**
///
/// 색도, 표시도 없이 제목·빈 줄·들여쓰기만으로 구조가 갈리는지 재려면 되읽을 수 있어야 한다.
/// 되읽히지 않으면 사람 눈에도 안 갈린다.
///
/// `{ 블록 이름: { 칸 이름: 값 } }`. 값의 여러 줄은 줄바꿈으로 이어 붙인다.
fn blocks(section: &str) -> BTreeMap<String, BTreeMap<String, String>> {
    let mut parsed: BTreeMap<String, BTreeMap<String, String>> = BTreeMap::new();
    let mut block: Option<String> = None;
    let mut field: Option<String> = None;

    for line in section.lines() {
        if line.trim().is_empty() {
            continue;
        }
        let indent = line.len() - line.trim_start().len();
        let text = line.trim_end();

        match indent {
            0 => {
                // 블록의 제목이거나, 절이 끝나고 이어지는 다른 글이다.
                let trimmed = text.trim();
                block = trimmed
                    .strip_prefix('[')
                    .and_then(|rest| rest.strip_suffix(']'))
                    .map(str::to_string);
                if block.is_some() {
                    parsed.entry(block.clone().unwrap()).or_default();
                }
                field = None;
            }
            2 => {
                let Some(name) = block.clone() else {
                    panic!("블록 밖에 칸이 있다: {line:?}");
                };
                field = Some(text.trim().to_string());
                parsed
                    .entry(name)
                    .or_default()
                    .insert(field.clone().unwrap(), String::new());
            }
            4 => {
                let (Some(name), Some(label)) = (block.clone(), field.clone()) else {
                    panic!("칸 밖에 값이 있다: {line:?}");
                };
                let slot = parsed.entry(name).or_default().entry(label).or_default();
                if !slot.is_empty() {
                    slot.push('\n');
                }
                slot.push_str(text.trim_start());
            }
            _ => panic!("들여쓰기가 두 단이 아니다: {line:?}"),
        }
    }
    parsed
}

/// Define·마지막 Outcome·Cycle Report 를 알아볼 수 있는 값으로 채워 닫은 Cycle.
fn closed_cycle(verdict: &str) -> (Project, [String; 6]) {
    let mut project = bootstrap();
    let cycle = project.cycles_mut().current_mut();
    cycle.open_step(NodeKind::Define).unwrap();
    cycle
        .close_step(
            full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Define)
                .with("problem", "무엇을 실험했는가")
                .with("success_condition", "무엇이 되면 풀린 것인가"),
        )
        .unwrap();
    for kind in [NodeKind::Hypothesis, NodeKind::Verify, NodeKind::Analysis] {
        cycle_step(cycle, kind);
    }
    cycle.open_step(NodeKind::Outcome).unwrap();
    let outcome = cycle.steps().current().unwrap();
    cycle
        .close_step(
            full_report(cycle.rules(), CycleKind::Experiment, NodeKind::Outcome)
                .with("verdict", verdict)
                .with("lesson", "왜 그렇게 판정했는가")
                .with(ACTION, "close_cycle")
                .with(REASON, "Step 수준의 방향"),
        )
        .unwrap();
    let report = cycle_report(cycle, verdict, outcome)
        .with("handoff_summary", "다음 Cycle 에 무엇을 넘기는가")
        .with(REASON, "다음 방향의 까닭");
    cycle.close(report).unwrap();

    let expected = [
        "무엇을 실험했는가".to_string(),
        "무엇이 되면 풀린 것인가".to_string(),
        match verdict {
            "success" => "풀렸다".to_string(),
            _ => "못 풀었다".to_string(),
        },
        "왜 그렇게 판정했는가".to_string(),
        "다음 Cycle 에 무엇을 넘기는가".to_string(),
        "다음 방향의 까닭".to_string(),
    ];
    (project, expected)
}

#[test]
fn the_cycle_section_is_four_blocks_a_reader_can_tell_apart() {
    // 요구 ①·⑧ — 제목·빈 줄·들여쓰기만으로 네 블록이 갈린다. 색에 기대지 않는다.
    let (project, _) = closed_cycle("failure");
    let told = story(project.cycles());
    let parsed = blocks(&cycle_section(&told));

    let names: Vec<&str> = parsed.keys().map(String::as_str).collect();
    assert_eq!(
        names,
        vec!["다음 방향", "실험", "인수인계", "판정"],
        "네 블록이 아니다:\n{told}"
    );

    // 그리고 여섯 정보가 **각자의 블록 안에** 있다.
    for (block, field) in [
        ("실험", "질문"),
        ("실험", "성공 기준"),
        ("판정", "결과"),
        ("판정", "이유"),
        ("인수인계", "다음 Cycle 에 넘길 것"),
        ("다음 방향", "동작"),
        ("다음 방향", "이유"),
    ] {
        let value = parsed
            .get(block)
            .unwrap_or_else(|| panic!("[{block}] 이 없다:\n{told}"))
            .get(field)
            .unwrap_or_else(|| panic!("[{block}] 에 {field} 가 없다:\n{told}"));
        assert!(!value.is_empty(), "[{block}] 의 {field} 가 비었다:\n{told}");
    }
}

#[test]
fn a_blank_line_stands_before_every_block_and_every_field() {
    // 요구 ① 의 나머지 절반 — 들여쓰기만으로는 칸이 이어 붙어 읽힌다. 빈 줄이 갈라 준다.
    let (project, _) = closed_cycle("failure");
    let section = cycle_section(&story(project.cycles()));
    let lines: Vec<&str> = section.lines().collect();

    let mut checked = 0;
    for (index, line) in lines.iter().enumerate() {
        let before = index.checked_sub(1).map(|i| lines[i]).unwrap_or("");
        let indent = line.len() - line.trim_start().len();

        if line.starts_with('[') {
            assert!(
                before.trim().is_empty(),
                "블록 [{}] 앞에 빈 줄이 없다:\n{section}",
                line.trim()
            );
            checked += 1;
        } else if indent == 2 && !line.trim().is_empty() {
            // 블록의 첫 칸은 제목 바로 아래, 그 뒤 칸들은 빈 줄 아래에 온다.
            assert!(
                before.starts_with('[') || before.trim().is_empty(),
                "{line:?} 앞이 빈 줄도 블록 제목도 아니다:\n{section}"
            );
            checked += 1;
        }
    }
    assert!(checked >= 8, "잰 줄이 너무 적다 — 구조가 안 그려졌다:\n{section}");
}

#[test]
fn the_header_says_the_kind_and_the_verdict() {
    for (verdict, shown) in [("success", "Success"), ("failure", "Failure")] {
        let (project, _) = closed_cycle(verdict);
        let told = story(project.cycles());
        assert!(
            told.contains(&format!("[Experiment · {shown}]")),
            "제목줄이 종류와 판정을 말하지 않는다:\n{told}"
        );
    }
}

#[test]
fn a_value_of_several_lines_keeps_its_indentation() {
    // 요구 ⑥ — 뒷줄도 같은 네 칸이라 어디까지가 한 칸의 값인지 갈린다.
    let (mut project, outcome) = graph_at_the_exit("failure");
    let report = cycle_report(project.cycles().current(), "failure", outcome)
        .with("handoff_summary", "첫 줄\n둘째 줄\n셋째 줄");
    project.cycles_mut().current_mut().close(report).unwrap();

    let told = story(project.cycles());
    let section = cycle_section(&told);
    for line in ["    첫 줄", "    둘째 줄", "    셋째 줄"] {
        assert!(
            section.lines().any(|shown| shown == line),
            "{line:?} 가 그 자리에 없다:\n{section}"
        );
    }
    // 되읽어도 세 줄 그대로다.
    assert_eq!(
        blocks(&section)["인수인계"]["다음 Cycle 에 넘길 것"],
        "첫 줄\n둘째 줄\n셋째 줄"
    );
}

#[test]
fn the_renderer_does_not_wrap_or_colour() {
    // 요구 ⑦·⑧ — 터미널 폭을 보고 접지 않고, 색 코드를 넣지 않는다.
    let long = "이 문장은 아주 길다. ".repeat(20);
    let (mut project, outcome) = graph_at_the_exit("failure");
    let report = cycle_report(project.cycles().current(), "failure", outcome).with("handoff_summary", long.clone());
    project.cycles_mut().current_mut().close(report).unwrap();

    let section = cycle_section(&story(project.cycles()));
    assert!(
        section.lines().any(|line| line.trim() == long.trim()),
        "긴 값이 접혔다:\n{section}"
    );
    assert!(!section.contains('\u{1b}'), "색 코드가 섞였다");
}

#[test]
fn the_cycle_section_shows_all_six_things() {
    // ① 여섯 정보가 모두 나타난다.
    for verdict in ["success", "failure"] {
        let (project, expected) = closed_cycle(verdict);
        let told = story(project.cycles());
        for value in &expected {
            assert!(told.contains(value.as_str()), "{value:?} 가 없다:\n{told}");
        }
        for label in ["질문", "성공 기준", "결과", "이유", "다음 Cycle 에 넘길 것", "동작"] {
            assert!(told.contains(label), "이름표 {label:?} 가 없다:\n{told}");
        }
    }
}

#[test]
fn the_cycle_section_alone_carries_everything() {
    // ② Step 절을 떼어 내고 Cycle 절만 읽어도 여섯이 그대로 있다.
    let (project, expected) = closed_cycle("failure");
    let told = story(project.cycles());
    let section = cycle_section(&told);

    for value in &expected {
        assert!(
            section.contains(value.as_str()),
            "Cycle 절만 읽으면 {value:?} 를 알 수 없다:\n{section}"
        );
    }
}

#[test]
fn the_projection_reads_from_the_originals() {
    // ③ 값은 Define · 마지막 Outcome · Cycle Report 의 원본에서 온다.
    let (project, _) = closed_cycle("failure");
    let section = cycle_section(&story(project.cycles()));
    let walk = project.cycles().current().steps();

    let define = walk
        .nodes()
        .iter()
        .find(|node| node.kind == NodeKind::Define)
        .unwrap()
        .report
        .as_ref()
        .unwrap();
    let last = walk.node(walk.current().unwrap()).unwrap().report.as_ref().unwrap();
    let report = project.cycles().current().report().unwrap();

    for (source, field) in [
        (define, "problem"),
        (define, "success_condition"),
        (last, "lesson"),
        (report, "handoff_summary"),
        (report, "next_direction.reason"),
    ] {
        let value = source.get(field).unwrap();
        assert!(
            section.contains(value),
            "{field} 를 원본에서 읽지 않았다:\n{section}"
        );
    }
}

#[test]
fn the_cycle_report_does_not_duplicate_what_it_projects() {
    // ④ 투영한다고 해서 Cycle Report 에 칸을 늘리지 않는다 — 원본은 한 자리에만 있다.
    let rules = spec();
    let required = &rules
        .cycle_rules(CycleKind::Experiment)
        .unwrap()
        .close_requires;

    for duplicated in ["problem", "success_condition", "lesson"] {
        assert!(
            !required.contains(&duplicated.to_string()),
            "Cycle Report 가 {duplicated} 를 복제한다"
        );
    }
}

#[test]
fn the_projection_uses_the_outcome_the_report_points_at() {
    // ⑤ 지나간 판정이 아니라 outcome_ref 가 가리키는 마지막 판정의 lesson 이다.
    let (mut project, past_lesson, last) = cycle_with_two_outcomes();
    let report = cycle_report(project.cycles().current(), "success", last);
    project.cycles_mut().current_mut().close(report).unwrap();

    let section = cycle_section(&story(project.cycles()));
    assert!(
        section.contains("마지막 판정의 교훈"),
        "마지막 판정의 lesson 이 없다:\n{section}"
    );
    assert!(
        !section.contains(past_lesson.as_str()),
        "지나간 판정의 lesson 이 Cycle 절에 섞였다:\n{section}"
    );
    // 지나간 판정은 Step 절에는 그대로 남는다 — 실패는 지워지지 않는다.
    assert!(
        story(project.cycles()).contains(past_lesson.as_str()),
        "지나간 판정이 이야기에서 사라졌다"
    );
}

#[test]
fn an_open_cycle_has_no_such_section() {
    // ⑥ 열린 Cycle 의 이야기는 그대로다 — 남긴 것이 아직 없다.
    //
    // 이야기에는 이미 닫힌 Bootstrap Interview 의 절이 있다. 그래서 **지금 Cycle 의 자리부터**
    // 보고, 그 뒤에 남긴 것이 없어야 한다.
    let (project, _) = graph_at_the_exit("failure");
    let told = story(project.cycles());
    let here = project.cycles().current().id().to_string();
    let (_, mine) = told
        .rsplit_once(here.as_str())
        .unwrap_or_else(|| panic!("지금 Cycle 의 절이 없다:\n{told}"));

    assert!(!project.cycles().current().is_closed());
    assert!(
        !mine.contains("이 Cycle 이 남긴 것"),
        "닫히지도 않았는데 남긴 것을 보여 준다:\n{mine}"
    );
    assert!(told.contains("판정"), "Step 절이 사라졌다:\n{told}");
}

#[test]
fn a_closed_cycle_still_says_what_cannot_be_done_yet() {
    let (project, _) = closed_cycle("failure");
    let told = story(project.cycles());
    // 다음 Cycle 을 여는 것은 이제 지었다. 아직 못 하는 것만 밝혀야 한다.
    assert!(
        told.contains("되돌아가는 것") && told.contains("아직 짓지 않았다"),
        "아직 못 하는 것을 밝히지 않는다:\n{told}"
    );
}
