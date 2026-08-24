//! Story — 한 Cycle 을 사람의 말로 옮긴다.
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

use crate::cycle::{Cycle, CycleKind};
use crate::cycles::Cycles;
use crate::node::{NodeKind, NodeStatus};
use crate::report::Report;
use crate::rules::RuleSet;
use crate::walk::StepNode;

/// 걸어 온 Cycle 들을 처음부터 끝까지 이야기로 옮긴다.
///
/// **부모의 Step 을 자식 아래에 다시 펼치지 않는다.** Cycle 은 제 Step 만 갖고, 이어받은 것은
/// `parent` 를 따라 읽은 Cycle Report 한 줄기다.
pub fn story(cycles: &Cycles) -> String {
    let mut out = String::new();
    for cycle in cycles.nodes() {
        write_cycle_banner(&mut out, cycles, cycle);
        write_steps(&mut out, cycle);
        write_cycle_report(&mut out, cycle);
    }
    write_where_we_stand(&mut out, cycles);
    out
}

/// 이 Cycle 이 어느 Cycle 인가 — 이름·종류·상태, 그리고 **어디에서 이어받았는가**.
fn write_cycle_banner(out: &mut String, cycles: &Cycles, cycle: &Cycle) {
    if !out.is_empty() {
        out.push('\n');
    }
    let state = match cycle.is_closed() {
        true => "닫힘",
        false => "걷는 중",
    };
    let _ = write!(out, "═══ {} · {} · {state}", cycle.id(), cycle.kind());
    match cycle.parent() {
        Some(parent) => {
            let _ = writeln!(out, " · {parent} 에서 이어받음 ═══");
        }
        None => {
            let _ = writeln!(out, " · 뿌리 ═══");
        }
    }
    write_inherited(out, cycles, cycle);
}

/// 부모에게서 이어받은 것 — **복제가 아니라 참조를 따라 읽은 것**이다.
///
/// 부모의 Step 을 여기 다시 펼치지 않는다. 다음 Cycle 이 실제로 받는 것은 부모의 Cycle Report
/// 하나이고, 그것이 무엇인지 여기서 한 번 보여 준다.
fn write_inherited(out: &mut String, cycles: &Cycles, cycle: &Cycle) {
    let Some(parent) = cycle.parent() else {
        return;
    };
    let Some(report) = cycles.inherited_report(cycle.id()) else {
        return;
    };
    let _ = writeln!(out, "\n[이어받은 것]");
    let _ = writeln!(out, "  {parent} 의 판정");
    if let Some(verdict) = report.get(VERDICT) {
        let _ = writeln!(out, "    {}", say(VERDICT, verdict));
    }
    if let Some(summary) = report.get(HANDOFF_SUMMARY) {
        out.push('\n');
        let _ = writeln!(out, "  {parent} 이(가) 넘긴 것");
        for line in summary.lines() {
            let _ = writeln!(out, "    {line}");
        }
    }
}

/// 이 Cycle 안의 Step 절들.
fn write_steps(out: &mut String, cycle: &Cycle) {
    let walk = cycle.steps();
    let mut attempt = 0;

    for node in walk.nodes() {
        match node.kind {
            NodeKind::Define => section(out, "문제", node, None),
            NodeKind::Hypothesis => {
                attempt += 1;
                let branched = node
                    .revisit_from
                    .map(|from| format!("{from} 에서 되돌아와 낸 갈래"));
                section(out, &format!("시도 {attempt}"), node, branched.as_deref());
            }
            NodeKind::Outcome => section(out, "판정", node, None),
            // Verify·Analysis 는 앞의 시도에 이어 적는다 — 같은 한 번의 시도다.
            _ => {}
        }

        match &node.report {
            Some(report) => write_report(out, cycle.rules(), cycle.kind(), node.kind, report),
            None => {
                let _ = writeln!(out, "  (아직 적지 않았다 — {} 은(는) 열려 있다)", node.id);
            }
        }
    }

}

/// Cycle 이 남긴 것 — **Step 을 펼치지 않고도 이 절만 읽으면 된다.**
///
/// Cycle Report 의 칸만 늘어놓으면, 이 Cycle 에 참여하지 않은 사람은 무엇을 실험했는지조차
/// 모른다. 그렇다고 Define 과 Outcome 의 내용을 Cycle Report 에 **복제하지 않는다** —
/// 두 자리에 같은 것을 적으면 한쪽이 낡는다.
///
/// 그래서 Cycle 의 구조적 참조를 따라 **원본에서 읽어 온다**(명세 §11 「Cycle story 의 선택적
/// 투영」). Step Report 전체를 펼치는 것이 아니라 시작점과 끝점만 읽는다.
///
/// ```text
/// [실험]      질문      ← 유일한 Define.problem
///             성공 기준 ← 유일한 Define.success_condition
/// [판정]      결과      ← Cycle Report.verdict
///             이유      ← outcome_ref 가 가리키는 Outcome.lesson
/// [인수인계]            ← Cycle Report.handoff_summary
/// [다음 방향] 동작·이유 ← Cycle Report.next_direction
/// ```
///
/// # 표현이지 저장이 아니다
///
/// 진실 원천은 Report 의 구조화된 원본과 Graph 의 참조다(명세 「Story 의 저장과 표현 분리」).
/// 여기 있는 것은 그 read model 을 **plain text 로 그리는 방식** 하나뿐이고, 제 판정을
/// 소유하지 않는다. 그래서 제목·빈 줄·일관된 들여쓰기만으로 블록이 갈려야 한다 —
/// **색에 기대지 않는다.** 터미널 폭을 보고 줄을 접지도 않는다(무엇이 원문인지 흐려진다).
fn write_cycle_report(out: &mut String, cycle: &Cycle) {
    let Some(report) = cycle.report() else {
        return;
    };
    if !out.is_empty() {
        out.push('\n');
    }
    let verdict = report.get(VERDICT);
    let _ = writeln!(
        out,
        "이 Cycle 이 남긴 것  [{} · {}]",
        title_case(cycle.kind().as_str()),
        title_case(verdict.unwrap_or("?"))
    );

    // ① 시작점 — 이 Cycle 의 유일한 Define 에서 읽는다.
    let mut experiment = Vec::new();
    if let Some(define) = cycle.define() {
        if let Some(problem) = define.get(PROBLEM) {
            experiment.push(("질문", problem.to_string()));
        }
        if let Some(condition) = define.get(SUCCESS_CONDITION) {
            experiment.push(("성공 기준", condition.to_string()));
        }
    }
    write_block(out, "실험", &experiment);

    // ② 판정과 그 근거 — 결과는 Cycle Node 자신의 것이고, 이유는 **가리킨 그 판정**의 것이다.
    let mut judged = Vec::new();
    if let Some(verdict) = verdict {
        judged.push(("결과", say(VERDICT, verdict)));
    }
    if let Some(lesson) = cycle.judged_lesson() {
        judged.push(("이유", lesson.to_string()));
    }
    write_block(out, "판정", &judged);

    // ③ 다음 Cycle 이 받을 것.
    let mut handoff = Vec::new();
    if let Some(summary) = report.get(HANDOFF_SUMMARY) {
        handoff.push(("다음 Cycle 에 넘길 것", summary.to_string()));
    }
    write_block(out, "인수인계", &handoff);

    // ④ 어디로 가는가 — 동작과 까닭을 갈라 적는다.
    let mut next = Vec::new();
    if let Some(action) = direction_head(report) {
        next.push(("동작", action));
    }
    if let Some(reason) = report.get(NEXT_REASON) {
        next.push(("이유", reason.to_string()));
    }
    write_block(out, "다음 방향", &next);
}

/// 블록 하나 — 앞에 빈 줄, `[제목]`, 그리고 빈 줄로 나뉜 칸들.
///
/// 들여쓰기는 두 단이다: 칸 이름 두 칸, 값 네 칸. **여러 줄 값의 뒷줄도 같은 네 칸**이라
/// 어디까지가 한 칸의 값인지 눈으로 갈린다.
fn write_block(out: &mut String, title: &str, fields: &[(&str, String)]) {
    if fields.is_empty() {
        return;
    }
    let _ = writeln!(out, "\n[{title}]");
    for (index, (label, value)) in fields.iter().enumerate() {
        if index > 0 {
            out.push('\n');
        }
        let _ = writeln!(out, "  {label}");
        for line in value.lines() {
            let _ = writeln!(out, "    {line}");
        }
    }
}

/// 첫 글자를 큰 글자로 — 제목줄에서 Kind 와 판정을 눈에 띄게 한다.
fn title_case(word: &str) -> String {
    let mut chars = word.chars();
    match chars.next() {
        Some(first) => first.to_uppercase().collect::<String>() + chars.as_str(),
        None => String::new(),
    }
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

/// Step 하나의 Report 를 적는다.
fn write_report(
    out: &mut String,
    rules: &RuleSet,
    cycle_kind: CycleKind,
    kind: NodeKind,
    report: &Report,
) {
    // 순서는 명세가 정한다. 명세에 없는 칸(다음 방향의 갈 곳 등)은 그 뒤에 붙는다.
    let declared: Vec<&str> = rules
        .rules(cycle_kind, kind)
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

/// 다음 방향의 **동작**만 사람의 말로.
///
/// 동작을 말로 옮기는 자리는 여기 하나뿐이다 — Step 절의 한 문장도, Cycle 절의 `동작` 칸도
/// 같은 것을 읽는다. 두 자리에 적으면 한쪽이 낡는다.
fn direction_head(report: &Report) -> Option<String> {
    let action = report.get(NEXT_ACTION)?;
    Some(
        match (action, report.get(NEXT_TARGET)) {
            ("revisit", Some(target)) => format!("{target} 로 되돌아간다"),
            ("revisit", None) => "되돌아간다".to_string(),
            ("close_cycle", _) => "여기서 이 Cycle 을 닫는다".to_string(),
            ("open_child", _) => "이 Cycle 을 부모로 다음 Cycle 을 연다".to_string(),
            (other, _) => other.to_string(),
        },
    )
}

/// 되돌아갈지 닫을지를 한 문장으로 — Step 절이 쓴다.
fn next_direction_sentence(report: &Report) -> Option<String> {
    let head = direction_head(report)?;
    let reason = report.get(NEXT_REASON).unwrap_or("");

    // 까닭은 줄을 바꿔 적는다 — 까닭 안에도 줄표가 있어서 한 줄에 이으면 문장이 겹친다.
    Some(match reason.is_empty() {
        true => head,
        false => format!("{head}\n{reason}"),
    })
}

/// 지금 어디에 서 있는가. 이야기의 마지막 줄은 언제나 현재다.
fn write_where_we_stand(out: &mut String, cycles: &Cycles) {
    let cycle = cycles.current();
    let walk = cycle.steps();
    if !out.is_empty() {
        out.push('\n');
    }
    let _ = write!(out, "지금 {}", cycle.id());
    if let Some(parent) = cycle.parent() {
        let _ = write!(out, "({parent} 에서 이어받음)");
    }
    match walk.current().and_then(|id| walk.node(id)) {
        _ if cycle.is_closed() => {
            let _ = writeln!(
                out,
                " 은(는) 닫혔다.\n\
                 Cycle 을 되돌아가는 것과 실패 Cycle 의 형제 가지는 아직 짓지 않았다."
            );
        }
        None => {
            let _ = writeln!(out, " 에 서 있고, 아직 아무것도 적지 않았다 — 문제부터 적는다.");
        }
        Some(node) => {
            let standing = match node.status {
                NodeStatus::Open => "아직 적는 중이다",
                NodeStatus::Closed => "적기를 마쳤다",
            };
            let _ = writeln!(
                out,
                " 의 {}({})에 서 있고, {standing}.",
                node.id,
                korean(node.kind)
            );
        }
    }
}

const NEXT_DIRECTION: &str = "next_direction.";

/// Cycle 절이 원본에서 읽어 오는 칸의 이름 — `gil-spec.yaml` 이 부르는 그대로.
const PROBLEM: &str = "problem";
const SUCCESS_CONDITION: &str = "success_condition";
const VERDICT: &str = "verdict";
const HANDOFF_SUMMARY: &str = "handoff_summary";
const NEXT_ACTION: &str = "next_direction.action";
const NEXT_TARGET: &str = "next_direction.target_node_ref";
const NEXT_REASON: &str = "next_direction.reason";

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
        NodeKind::Question => "질문",
        NodeKind::Interpretation => "해석",
        NodeKind::Synthesis => "제안",
        NodeKind::Define => "문제",
        NodeKind::Hypothesis => "가설",
        NodeKind::Verify => "검증",
        NodeKind::Analysis => "해석",
        NodeKind::Outcome => "판정",
        NodeKind::CycleEntry => "시작 경계",
        NodeKind::CycleExit => "끝 경계",
    }
}
