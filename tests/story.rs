//! 걸어온 것을 사람의 말로 읽는다.
//!
//! 여기서 재는 것은 **문구가 아니라 규칙**이다. 이야기가 예쁜지는 상현님이 읽고 판정한다 —
//! 시험이 재는 것은 "적힌 것이 조용히 사라지지 않는가" 하나다. 문구를 다듬을 때마다
//! 빨개지는 시험은 무시되고, 무시되는 시험은 없는 것과 같다.

use gil::{NodeKind, Report, Walk, story};

mod common;
use common::{ACTION, REASON, TARGET, full_report, spec, step};

/// 한 줄기를 걷고, 되돌아가겠다고 적고, 갈래의 첫 가설을 연 자리.
fn walk_with_a_branch() -> Walk {
    let mut walk = Walk::start(spec());
    for kind in [
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
    ] {
        step(&mut walk, kind);
    }
    let target = walk.nodes()[3].id;

    walk.open(NodeKind::Outcome).unwrap();
    let report = full_report(walk.rules(), NodeKind::Outcome)
        .with("verdict", "failure")
        .with(ACTION, "revisit")
        .with(TARGET, target.to_string().trim_start_matches('#'))
        .with(REASON, "해석까지는 유효하다");
    walk.close(report).unwrap();

    walk.revisit().unwrap();
    walk.open(NodeKind::Hypothesis).unwrap();
    walk
}

#[test]
fn nothing_a_person_wrote_disappears_from_the_story() {
    // 사람이 제 말로 적은 칸은 한 글자도 사라지면 안 된다. 사라지면 그 칸은
    // 적으라고 요구해 놓고 아무도 안 읽는 칸이 된다.
    //
    // 명세가 값을 열거해 둔 칸은 여기서 재지 않는다 — 그건 우리가 정한 낱말이고,
    // 이야기가 사람의 말로 옮기는 것이 의도다. 그쪽은 아래 시험이 따로 잰다.
    let walk = walk_with_a_branch();
    let told = story(&walk);
    let rules = spec();

    let mut checked = 0;
    for node in walk.history() {
        let step = rules.rules(node.kind).unwrap();
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
        .rules(NodeKind::Outcome)
        .unwrap()
        .field_constraints
        .get("verdict")
        .expect("판정의 결과는 값이 열거된 칸이다");
    assert!(
        constraint.allowed_values.len() >= 2,
        "값이 하나뿐이면 이 시험은 아무것도 재지 못한다"
    );

    // 결과가 다음 방향을 좁히므로, **어느 결과에서도 허락되는** 방향 하나를 고른다.
    // 그래야 두 이야기가 결과 말고는 같아진다.
    let action = shared_action(&constraint.allowed_values);

    let told: Vec<String> = constraint
        .allowed_values
        .iter()
        .map(|verdict| {
            let mut walk = Walk::start(spec());
            for kind in [
                NodeKind::Define,
                NodeKind::Hypothesis,
                NodeKind::Verify,
                NodeKind::Analysis,
            ] {
                step(&mut walk, kind);
            }
            walk.open(NodeKind::Outcome).unwrap();
            let report = full_report(walk.rules(), NodeKind::Outcome)
                .with("verdict", verdict)
                .with(ACTION, action.clone());
            walk.close(report).unwrap();
            story(&walk)
        })
        .collect();

    assert_ne!(told[0], told[1], "결과가 달라졌는데 이야기가 같다:\n{}", told[0]);
}

/// 어느 결과에서도 허락되는 다음 방향. 없으면 이 시험은 성립하지 않는다.
fn shared_action(verdicts: &[String]) -> String {
    let rules = spec();
    let per_verdict: Vec<Vec<String>> = verdicts
        .iter()
        .map(|verdict| {
            let report = full_report(&rules, NodeKind::Outcome).with("verdict", verdict);
            common::allowed_here(&rules, NodeKind::Outcome, ACTION, &report)
        })
        .collect();

    per_verdict[0]
        .iter()
        .find(|action| per_verdict.iter().all(|allowed| allowed.contains(action)))
        .expect("어느 결과에서도 허락되는 방향이 하나는 있어야 한다")
        .clone()
}

#[test]
fn a_field_the_story_has_no_name_for_still_shows_up() {
    // 이름표가 없는 칸은 제 이름 그대로 나온다. 모르는 칸을 조용히 버리면
    // 명세에 칸이 늘어날 때 이야기가 말없이 낡는다.
    let mut walk = Walk::start(spec());
    walk.open(NodeKind::Define).unwrap();
    let report: Report = full_report(walk.rules(), NodeKind::Define)
        .with("weather_at_the_time", "비가 왔다");
    walk.close(report).unwrap();

    let told = story(&walk);
    assert!(
        told.contains("weather_at_the_time") && told.contains("비가 왔다"),
        "이름표 없는 칸이 사라졌다:\n{told}"
    );
}

#[test]
fn the_story_says_where_a_branch_came_from() {
    // "왜 돌아갔나" 는 여덟 물음 중 하나다. 갈래가 어느 판정에서 났는지 말하지 않으면
    // 읽는 사람은 두 시도가 나란한 것인지 이어진 것인지 알 수 없다.
    let walk = walk_with_a_branch();
    let outcome = walk
        .nodes()
        .iter()
        .find(|node| node.kind == NodeKind::Outcome)
        .unwrap();
    let branch = walk.nodes().last().unwrap();

    let told = story(&walk);
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
    let walk = walk_with_a_branch();
    let open = walk.nodes().last().unwrap();
    assert!(open.report.is_none(), "이 자리는 열려 있어야 한다");

    let told = story(&walk);
    assert!(
        told.contains("아직"),
        "열린 자리를 다 적은 것처럼 말한다:\n{told}"
    );
}

#[test]
fn an_empty_walk_still_tells_where_to_begin() {
    // 아무것도 안 적은 걷기도 이야기가 있다 — "여기서 시작한다" 는 것.
    let told = story(&Walk::start(spec()));
    assert!(!told.trim().is_empty(), "빈 걷기의 이야기가 비었다");
}
