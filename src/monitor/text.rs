//! Monitor 의 **plain text 표현** — 다른 renderer 가 따를 의미 기준.
//!
//! 임시 debug dump 가 아니다. `Debug` 출력을 그대로 보이거나 필드 이름을 무차별로 늘어놓지
//! 않는다 — 여기 적힌 절과 낱말이 뒤에 올 HTML 이 지켜야 할 계약이다(Monitor Model §7.3).
//!
//! # 받는 것은 Snapshot 하나뿐이다
//!
//! ```text
//! render_monitor_text(&MonitorSnapshot) -> String
//! ```
//!
//! `Project` 도, `ProjectSession` 도, `.gil` 도, 작업 폴더도, 다른 명령의 출력도 받지 않는다.
//! **그럴 수 없다** — 서명에 그것들이 없기 때문이다. 그래서 「그리는 동안 원본이 움직였다」는
//! 상태가 이 함수에는 존재하지 않고, 잠금을 놓은 뒤에 불러도 안전하다.
//!
//! # 없는 것을 그리지 않는다
//!
//! Define 이 없으면 빈 질문을 지어내지 않고, Will 이 없으면 Step 에서 추측하지 않으며,
//! 계보 밖 Cycle 을 모두 「실패한 형제」라 부르지 않는다. 절 자체가 없는 것과 절 안이 빈
//! 것은 다르고, 사람의 판단에 부재가 필요한 자리에서만 「없음」이라고 적는다.
//!
//! # 꾸미지 않는다
//!
//! ANSI escape 도, terminal 폭 감지도, box-drawing 문자도 쓰지 않는다. 절과 관계는
//! **들여쓰기와 낱말**로만 갈린다 — 파이프로 넘기든 파일로 저장하든 같은 글이 나온다.
//! 긴 값을 억지로 접지 않는다. 사람이 적은 줄바꿈은 그대로 두되, 이어지는 줄에는 같은
//! 들여쓰기를 준다.

use std::fmt::Write as _;

use super::{
    CycleFacts, CycleReportFacts, InactiveCycle, MonitorSnapshot, NextAction, StepFacts, WillFacts,
    WorldFacts,
};
use super::say;
use crate::InterviewQuestion;

/// 절 안의 한 칸이 들어가는 깊이.
const INDENT: &str = "  ";
/// 이름표 아래 여러 줄 값이 들어가는 깊이.
const DEEPER: &str = "    ";

/// **Snapshot 하나를 사람이 읽는 글로.**
///
/// 같은 Snapshot 은 언제 불러도 **바이트까지 같은 글**을 만든다. 관측 시각을 싣지 않는
/// 까닭도 그것이다 — 시각을 적으면 같은 사실이 매번 다른 글이 되고, 두 화면이 같은지
/// 물을 수 없게 된다(`captured_at` 은 표시용이며 판정에 쓰지 않는다).
pub fn render_monitor_text(seen: &MonitorSnapshot) -> String {
    let mut out = String::from("GIL Monitor\n");
    write_here(&mut out, seen);
    write_active_lineage(&mut out, seen);
    write_left_behind(&mut out, seen);
    write_will(&mut out, seen);
    write_world(&mut out, &seen.world);
    write_next(&mut out, &seen.next_actions);
    out
}

// ── 지금 어디인가 ──────────────────────────────────────────────────────────

/// 현재 Cycle 과 Step, 그리고 Experiment 라면 무엇을 묻고 무엇이면 성공인가.
///
/// 제목은 Cycle 의 종류를 따른다 — Interview 를 「현재 실험」이라 부르면 그 화면은 첫 줄부터
/// 거짓말이다.
fn write_here(out: &mut String, seen: &MonitorSnapshot) {
    let cycle = &seen.current_cycle.facts;
    section(out, say::here_title(cycle.kind));

    let _ = writeln!(out, "{INDENT}{}: {}", say::CYCLE, cycle_line(cycle));
    match &seen.current_step {
        Some(step) => {
            let _ = writeln!(out, "{INDENT}{}: {}", say::STEP, step_line(step));
        }
        // **부재가 판단에 필요한 자리다.** 이 Cycle 안에서 아직 아무것도 열지 않았다는
        // 사실은 다음에 무엇을 할지와 곧바로 이어진다.
        None => {
            let _ = writeln!(out, "{INDENT}{}: {}", say::STEP, say::NO_STEP_YET);
        }
    }

    // Define 이 없으면 빈 질문을 지어내지 않는다 — 절만 조용히 짧아진다.
    if let Some(define) = &cycle.experiment_definition {
        field(out, say::PROBLEM, &define.problem);
        field(out, say::SUCCESS_CONDITION, &define.success_condition);
    }

    // Interview 는 **제 질문**으로 말한다. Define 이 없다는 사실은 Interview 에 대해
    // 아무것도 말해 주지 않으므로, Experiment 의 규칙을 빌려 오지 않는다.
    match &cycle.interview_question {
        Some(InterviewQuestion::Asked { question, response }) => {
            field(out, say::PROBLEM, question);
            if let Some(response) = response {
                field(out, say::RESPONSE, response);
            }
        }
        Some(InterviewQuestion::Asking) => field(out, say::PROBLEM, say::ASKING),
        // 아직 묻지 않았으면 **이름표조차 붙이지 않는다** — `질문:` 이라고 적는 순간
        // 없는 것에 자리가 생기고, 그 자리는 언젠가 채워지고 싶어 한다. 「아직 묻지
        // 않았다」는 제목 자리가 말할 몫이지 이 절이 말할 몫이 아니다.
        Some(InterviewQuestion::NotAsked) | None => {}
    }

    // 되돌아온 자리라면 **새 Cycle 이 아직 없다**는 사실을 여기서 말한다.
    if let Some(pending) = &seen.pending_revisit {
        let _ = writeln!(
            out,
            "{INDENT}되돌아왔다: {} 에서 갈라져 {} 에 섰다 — 새 Cycle 은 아직 없다",
            pending.from_cycle_ref, pending.target_cycle_ref
        );
    }

    if let Some(report) = &cycle.report {
        write_report(out, INDENT, report);
    }
}

/// Cycle 한 줄 — **typed reference · 종류 · 열림/닫힘**은 어느 표현에서도 지킨다.
///
/// 부모와 갈래의 출처를 **같은 낱말로 잇지 않는다.** 하나는 누구의 사고와 세계를
/// 이어받았는가이고, 다른 하나는 어느 실패에서 갈라져 나왔는가다.
fn cycle_line(cycle: &CycleFacts) -> String {
    let mut line = format!(
        "{} · {} · {}",
        cycle.cycle_ref,
        cycle.kind,
        say::state_of(cycle.state)
    );
    if let Some(parent) = cycle.parent_cycle_ref {
        let _ = write!(line, " · {} {parent}", say::PARENT);
    }
    if let Some(from) = cycle.revisit_from_cycle_ref {
        let _ = write!(line, " · {from} 에서 갈라짐");
    }
    line
}

fn step_line(step: &StepFacts) -> String {
    format!("{} · {} · {}", step.step_ref, step.kind, say::state_of(step.state))
}

/// 닫힌 Cycle 이 남긴 판정과 인수인계 — **세 절이 이 한 자리를 쓴다.**
///
/// 현재 자리도, 활성 경로의 조상도, 지나온 갈래도 같은 낱말로 판정을 읽는다. 절마다 따로
/// 그리면 같은 `verdict` 가 자리에 따라 다른 뜻으로 읽히기 시작한다.
fn write_report(out: &mut String, indent: &str, report: &CycleReportFacts) {
    write_lines(out, indent, say::VERDICT, &report.verdict);
    if let Some(lesson) = &report.outcome_lesson {
        write_lines(out, indent, say::LESSON, lesson);
    }
    write_lines(out, indent, say::HANDOFF, &report.handoff_summary);
    if let Some(direction) = &report.next_direction {
        let mut line = direction.action.clone();
        if let Some(target) = direction.target_cycle_ref {
            let _ = write!(line, " → {target}");
        }
        write_lines(out, indent, say::NEXT_DIRECTION, &line);
        if let Some(reason) = &direction.reason {
            write_lines(out, indent, say::WHY, reason);
        }
    }
}

// ── 걸어온 길 ──────────────────────────────────────────────────────────────

/// 뿌리부터 지금까지 — **`parent` 만 따라간 길.**
///
/// 참조만 늘어놓지 않는다. 직렬로 성공한 조상이 무엇을 실험했고 무엇을 넘겼는지가 여기
/// 없으면, 화면은 「지금 어디인가」에는 답해도 **「왜 여기 있는가」에는 답하지 못한다.**
///
/// 그러나 **Step 은 펼치지 않는다.** 조상의 Step 을 늘어놓으면 이 절이 곧 전체 history 가
/// 되고, 그것은 다른 독자의 몫이다. Snapshot 의 타입이 이미 그것을 막아 둔다 —
/// 계보의 항목에는 Step 목록을 담을 자리가 없다.
fn write_active_lineage(out: &mut String, seen: &MonitorSnapshot) {
    section(out, say::ACTIVE_PATH);
    let _ = writeln!(out, "{INDENT}{}", say::ACTIVE_PATH_IS);

    let last = seen.active_lineage.len().saturating_sub(1);
    for (depth, cycle) in seen.active_lineage.iter().enumerate() {
        out.push('\n');
        // 깊이는 **들여쓰기로만** 나타낸다. 선을 그리는 문자를 쓰지 않는다.
        let head = format!("{INDENT}{}", INDENT.repeat(depth));
        let body = format!("{head}{INDENT}");
        let _ = writeln!(out, "{head}{}", cycle_line(cycle));

        // **지금 자리는 앞 절이 이미 자세히 말했다.** 여기서 질문과 성공 기준을 다시
        // 길게 늘어놓지 않는다 — 같은 글이 한 화면에 두 번 있으면 어느 쪽이 최신인지
        // 묻게 된다.
        if depth == last {
            continue;
        }
        if let Some(define) = &cycle.experiment_definition {
            write_lines(out, &body, say::PROBLEM, &define.problem);
            write_lines(out, &body, say::SUCCESS_CONDITION, &define.success_condition);
        }
        if let Some(report) = &cycle.report {
            write_report(out, &body, report);
        }
    }
}

/// 계보 밖의 Cycle 들 — **하나도 없으면 절 자체가 없다.**
///
/// 여기 실린 것을 모두 「실패한 형제」라 부르지 않는다. 관계는 구조가 말하고, 실패했는지는
/// 그 Cycle 의 Report 만 말한다. 형제인지는 부모가 같은지로만 읽는다.
fn write_left_behind(out: &mut String, seen: &MonitorSnapshot) {
    if seen.inactive_cycles.is_empty() {
        return;
    }
    section(out, say::LEFT_BEHIND);
    let _ = writeln!(out, "{INDENT}{}", say::LEFT_BEHIND_IS);
    for cycle in &seen.inactive_cycles {
        out.push('\n');
        write_one_left_behind(out, cycle, &seen.current_cycle.facts);
    }
}

fn write_one_left_behind(out: &mut String, cycle: &InactiveCycle, here: &CycleFacts) {
    let _ = writeln!(
        out,
        "{INDENT}{} · {} · {}",
        cycle.cycle_ref,
        cycle.kind,
        say::state_of(cycle.state)
    );
    let _ = writeln!(
        out,
        "{DEEPER}{}: {}",
        say::RELATION,
        say::relation_of(cycle.relation_to_current)
    );
    if let Some(parent) = cycle.parent_cycle_ref {
        let mut line = format!("{}: {parent}", say::PARENT);
        // **형제는 부모가 같을 때만.** 그 판정을 여기서 새로 만들지 않고 두 부모를 견준다.
        if here.parent_cycle_ref == Some(parent) {
            let _ = write!(line, " ({})", say::SAME_PARENT);
        }
        let _ = writeln!(out, "{DEEPER}{line}");
    }
    if let Some(from) = cycle.revisit_from_cycle_ref {
        let _ = writeln!(
            out,
            "{DEEPER}{}: {from} ({})",
            say::BRANCH_SOURCE,
            say::NOT_A_LINEAGE_EDGE
        );
    }
    // **실패는 Report 만 말한다.** Report 가 없으면 판정도 없다.
    // 활성 조상과 **같은 문**을 쓴다 — 같은 verdict 가 절에 따라 다른 뜻으로 읽히지 않게.
    if let Some(report) = &cycle.report {
        write_report(out, DEEPER, report);
    }
}

// ── 지금 하려는 것 ─────────────────────────────────────────────────────────

/// 걸린 행동 하나. **없으면 절 자체가 없다** — 열린 Step 에서 추측해 만들지 않는다.
fn write_will(out: &mut String, seen: &MonitorSnapshot) {
    let Some(will) = &seen.current_will else {
        return;
    };
    section(out, say::DOING);
    write_one_will(out, will);
}

fn write_one_will(out: &mut String, will: &WillFacts) {
    let _ = writeln!(out, "{INDENT}{} · {} 에 걸려 있다", will.will_ref, will.target_step_ref);
    field(out, say::OBJECTIVE, &will.objective);
    field(out, say::NEXT_ACTION, &will.next_action);
    field(out, say::DONE_WHEN, &will.done_when);
}

// ── 지금 세계 ──────────────────────────────────────────────────────────────

/// 기준 Snapshot 과 지금 폴더의 관계.
///
/// 파일 목록도, 내부 주소도, digest 도 적지 않는다 — 공개 표면은 `snapshot:A*` 하나다.
/// **못 본 것을 dirty 라 하지 않고**, 왜 못 봤는지를 함께 남긴다.
fn write_world(out: &mut String, world: &WorldFacts) {
    section(out, say::WORLD);
    let _ = writeln!(out, "{INDENT}{}: {}", say::BASELINE, world.baseline_snapshot_ref);
    let _ = writeln!(
        out,
        "{INDENT}{}: {}",
        say::WORLD_STATE,
        say::world_of(world.state)
    );
    if let Some(reason) = &world.reason {
        write_lines(out, INDENT, say::WHY_UNKNOWN, reason);
    }
    if world.verify_can_confirm {
        let _ = writeln!(out, "{INDENT}{}", say::VERIFY_CAN_CONFIRM);
    }
}

// ── 다음 행동 ──────────────────────────────────────────────────────────────

/// **Snapshot 이 준 것만 적는다.** 여기서 수를 더하거나 빼지 않는다.
///
/// 목록이 비었다는 것은 지금 밟을 수 있는 GIL 명령이 없다는 뜻이고, 그 사실은 사람의
/// 판단에 필요하므로 「없음」이라 적는다.
fn write_next(out: &mut String, actions: &[NextAction]) {
    section(out, say::NEXT);
    if actions.is_empty() {
        let _ = writeln!(out, "{INDENT}{}", say::NO_MOVE);
        return;
    }
    for (at, next) in actions.iter().enumerate() {
        // 수와 수 **사이**만 띄운다. 절 제목 바로 아래 빈 줄을 두면 절이 비어 보인다.
        if at > 0 {
            out.push('\n');
        }
        let _ = writeln!(out, "{INDENT}{}", say::what_it_does(next.kind));
        write_lines(out, DEEPER, say::REASON, &next.reason);
        // 명령이 없는 수는 실행할 글자를 지어내지 않는다.
        if let Some(command) = &next.command {
            let _ = writeln!(out, "{DEEPER}{}: {command}", say::RUN);
        }
        if let Some(topic) = &next.help_ref {
            let _ = writeln!(out, "{DEEPER}{}: gil help {}", say::HELP, topic.as_str());
        }
    }
}

// ── 글의 모양 ──────────────────────────────────────────────────────────────

fn section(out: &mut String, title: &str) {
    let _ = write!(out, "\n[{title}]\n");
}

/// 이름표 하나와 그 값 — 한 칸 깊이에서.
fn field(out: &mut String, label: &str, value: &str) {
    write_lines(out, INDENT, label, value);
}

/// **여러 줄 값의 뒷줄에도 같은 들여쓰기를 준다.**
///
/// 사람이 적은 줄바꿈은 그대로 둔다. 억지로 접지 않으므로 terminal 폭을 묻지 않는다 —
/// 접으려면 폭을 알아야 하고, 폭을 알려면 이 함수가 화면을 봐야 한다.
///
/// 첫 줄은 이름표 옆에, 나머지는 **한 칸 더 깊이** 들어간다. 값이 어디서 시작해 어디서
/// 끝나는지가 색 없이도 보이게 하려는 것이다.
fn write_lines(out: &mut String, indent: &str, label: &str, value: &str) {
    let mut lines = value.lines();
    let first = lines.next().unwrap_or_default();
    let _ = writeln!(out, "{indent}{label}: {first}");
    for line in lines {
        let _ = writeln!(out, "{indent}{INDENT}{line}");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_text_never_reads_the_timeline() {
        // 새 칸이 생겼다고 글 화면이 전체 history 가 되면 안 된다. **바이트로 잰다** —
        // 시간선을 통째로 비워도 글이 한 글자도 달라지지 않으면, 글은 그것을 읽지 않는다.
        let full = super::super::graph::tests::reading_one();
        assert!(!full.timeline.is_empty(), "이 fixture 는 시간선을 지녀야 한다");

        let mut emptied = full.clone();
        emptied.timeline.clear();

        assert_eq!(
            render_monitor_text(&full),
            render_monitor_text(&emptied),
            "글 화면이 시간선을 읽고 있다"
        );
    }
}
