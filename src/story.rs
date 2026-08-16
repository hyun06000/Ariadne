//! Story — 걷기를 사람의 말로 옮긴다.
//!
//! 판정도, 규칙도 여기 없다. 이미 적힌 것을 **읽는 순서와 이름**만 정한다.
//!
//! 답해야 하는 것은 여덟이다: 무엇을 풀려 했나 · 어떤 접근을 했나 · 무엇을 해 봤나 ·
//! 무엇이 나왔나 · 그것을 어떻게 읽었나 · 무엇이 남았나 · 왜 돌아갔나 · 새 접근은 무엇인가.
//! 그 여덟에 필요한 값은 전부 Report 와 `parent` 사슬에 이미 있다.
//!
//! # 칸을 여기에 열거하지 않는다
//!
//! 어떤 칸이 있는지도, 어떤 순서인지도 `gil-spec.yaml` 이 정한다([`StepRules::close_requires`]).
//! 여기 있는 것은 **이름표**뿐이고, 이름표가 없는 칸은 제 이름 그대로 나온다 —
//! 명세에 칸이 늘어도 이야기에서 조용히 사라지지 않게.
//!
//! [`StepRules::close_requires`]: crate::StepRules::close_requires

use std::fmt::Write as _;

use crate::node::{NodeKind, NodeStatus};
use crate::report::Report;
use crate::walk::{StepNode, Walk};

/// 걷기를 처음부터 끝까지 이야기로 옮긴다.
pub fn story(walk: &Walk) -> String {
    let mut out = String::new();
    let mut attempt = 0;

    for node in walk.nodes() {
        match node.kind {
            NodeKind::Define => section(&mut out, "문제", node, None),
            NodeKind::Hypothesis => {
                attempt += 1;
                let branched = node
                    .revisit_from
                    .map(|from| format!("{from} 에서 되돌아와 낸 갈래"));
                section(&mut out, &format!("시도 {attempt}"), node, branched.as_deref());
            }
            NodeKind::Outcome => section(&mut out, "판정", node, None),
            // Verify·Analysis 는 앞의 시도에 이어 적는다 — 같은 한 번의 시도다.
            _ => {}
        }

        match &node.report {
            Some(report) => write_report(&mut out, walk, node.kind, report),
            None => {
                let _ = writeln!(out, "  (아직 적지 않았다 — {} 은(는) 열려 있다)", node.id);
            }
        }
    }

    write_where_we_stand(&mut out, walk);
    out
}

/// 새 마디를 연다. 이름 아래에 어느 Node 인지도 적는다 — 되돌아갈 자리를 고르려면 이름이 필요하다.
fn section(out: &mut String, title: &str, node: &StepNode, note: Option<&str>) {
    if !out.is_empty() {
        out.push('\n');
    }
    let _ = write!(out, "{title}  [{}", node.id);
    if let Some(note) = note {
        let _ = write!(out, " · {note}");
    }
    let _ = writeln!(out, "]");
}

fn write_report(out: &mut String, walk: &Walk, kind: NodeKind, report: &Report) {
    // 순서는 명세가 정한다. 명세에 없는 칸(다음 방향의 갈 곳 등)은 그 뒤에 붙는다.
    let declared: Vec<&str> = walk
        .rules()
        .rules(kind)
        .map(|rules| rules.close_requires.iter().map(String::as_str).collect())
        .unwrap_or_default();
    let extra: Vec<&str> = report
        .field_names()
        .filter(|name| !declared.contains(name))
        .collect();

    for field in declared.into_iter().chain(extra) {
        // 다음 방향은 칸마다 따로 적으면 문장이 안 된다 — 아래에서 한 문장으로 옮긴다.
        if field.starts_with(NEXT_DIRECTION) {
            continue;
        }
        let Some(value) = report.get(field) else {
            continue;
        };
        write_field(out, label(field), &say(field, value));
    }

    if let Some(sentence) = next_direction_sentence(report) {
        write_field(out, "그래서", &sentence);
    }
}

/// `이름표: 값` 한 줄. 여러 줄짜리 값은 이름표 아래로 들여쓴다.
fn write_field(out: &mut String, label: &str, value: &str) {
    let mut lines = value.lines();
    let first = lines.next().unwrap_or("");
    let _ = writeln!(out, "  {label}: {first}");
    for line in lines {
        let _ = writeln!(out, "    {line}");
    }
}

/// 되돌아갈지 닫을지를 한 문장으로.
fn next_direction_sentence(report: &Report) -> Option<String> {
    let action = report.get("next_direction.action")?;
    let reason = report.get("next_direction.reason").unwrap_or("");

    let head = match (action, report.get("next_direction.target_node_id")) {
        ("revisit", Some(target)) => format!("#{target} 로 되돌아간다"),
        ("revisit", None) => "되돌아간다".to_string(),
        ("close_cycle", _) => "여기서 이 사이클을 닫는다".to_string(),
        (other, _) => other.to_string(),
    };

    // 까닭은 줄을 바꿔 적는다 — 까닭 안에도 줄표가 있어서 한 줄에 이으면 문장이 겹친다.
    Some(match reason.is_empty() {
        true => head,
        false => format!("{head}\n{reason}"),
    })
}

/// 지금 어디에 서 있는가. 이야기의 마지막 줄은 언제나 현재다.
fn write_where_we_stand(out: &mut String, walk: &Walk) {
    if !out.is_empty() {
        out.push('\n');
    }
    match walk.current().and_then(|id| walk.node(id)) {
        _ if walk.is_finished() => {
            let _ = writeln!(out, "여기서 이야기가 끝난다 — 이 사이클은 닫혔다.");
        }
        None => {
            let _ = writeln!(out, "아직 아무것도 적지 않았다 — 문제부터 적는다.");
        }
        Some(node) => {
            let standing = match node.status {
                NodeStatus::Open => "아직 적는 중이다",
                NodeStatus::Closed => "적기를 마쳤다",
            };
            let _ = writeln!(
                out,
                "지금 {}({})에 서 있고, {standing}.",
                node.id,
                korean(node.kind)
            );
        }
    }
}

const NEXT_DIRECTION: &str = "next_direction.";

/// 칸의 이름표. 없는 칸은 제 이름 그대로 — 조용히 사라지는 것보다 낫다.
fn label(field: &str) -> &str {
    match field {
        "problem" => "무엇을 풀려는가",
        "success_condition" => "풀렸다고 하려면",
        "hypothesis" => "세운 것",
        "rationale" => "그렇게 본 까닭",
        "guardrail" => "넘으면 멈추기로 한 선",
        "execution" => "해 본 것",
        "result" => "나온 것",
        "hypothesis_fit" => "가설과 맞았나",
        "problem_solved" => "문제가 풀렸나",
        "success_condition_met" => "기준을 넘었나",
        "guardrail_triggered" => "멈춤선이 울렸나",
        "interpretation" => "그것을 어떻게 읽었나",
        "verdict" => "결과",
        "lesson" => "남은 것",
        other => other,
    }
}

/// 명세가 정해 둔 낱말을 사람의 말로. 모르는 값은 그대로 둔다.
fn say(field: &str, value: &str) -> String {
    match (field, value) {
        ("verdict", "success") => "풀렸다".to_string(),
        ("verdict", "failure") => "못 풀었다".to_string(),
        _ => value.to_string(),
    }
}

fn korean(kind: NodeKind) -> &'static str {
    match kind {
        NodeKind::Define => "문제",
        NodeKind::Hypothesis => "가설",
        NodeKind::Verify => "검증",
        NodeKind::Analysis => "해석",
        NodeKind::Outcome => "판정",
        NodeKind::CycleEntry => "시작 경계",
        NodeKind::CycleExit => "끝 경계",
    }
}
