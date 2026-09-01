//! Context — **새 세션이 지금 자리에서 이어 걷기 위한 것.**
//!
//! [`story`](crate::story) 와 같은 Graph 를 읽지만 독자와 책임이 다르다. story 는 사람이
//! 지금을 이해하기 위한 것이고, 여기는 **아무 대화도 물려받지 않은 Agent 가 다시 시작하기**
//! 위한 것이다(Context Model §8).
//!
//! # 해상도는 거리가 정한다
//!
//! ```text
//! 이전 Cycle 들   → Cycle Report 까지
//! 현재 Cycle      → Step Report 까지
//! 서 있는 자리    → 상태 · 다음 행동 · 지금 지켜야 하는 규칙
//! ```
//!
//! Context Model §2 의 Context Resolution Rule 이고, §7 이 M2 에 남긴 몫이 그 셋뿐이다
//! (Chain 도 Artifact snapshot 도 아직 없으므로 없는 절을 있는 척 적지 않는다).
//!
//! **지나온 Cycle 의 Step 은 여기 펼치지 않는다.** 그것이 이 투영의 존재 이유다 — 같은 Step
//! 기록을 Cycle 마다 다시 실어 나르면 프로젝트가 길어질수록 문맥이 그것만으로 찬다.
//! 다만 압축은 삭제가 아니다(§3). 접힌 Step Graph 는 원본 Graph 에 그대로 보존된다.
//! **어느 명령으로 그것을 펼치는지는 이 자리가 약속하지 않는다** — 전체 Graph 를 훑는
//! 책임은 장차 `gil history` 의 것이고, 아직 없는 명령을 출력에서 안내하지 않는다.
//!
//! # 아무것도 새로 저장하지 않는다
//!
//! 여기에는 상태가 없다. Cycle Report 를 다시 요약해 어딘가에 적어 두지 않고, **Graph 의
//! 참조와 Report 원본에서 그때그때 읽는다** — 요약본을 따로 두면 원본이 자라도 그쪽은
//! 낡은 채로 남는다.


use std::fmt::Write as _;

use crate::cycle::{Cycle, CycleKind};
use crate::contract::CloseContract;
use crate::cycles::Cycles;
use crate::node::NodeKind;
use crate::project::Project;
use crate::report::Report;
use crate::rules::RuleSet;

/// 지금 자리에서 이어 걷기 위해 알아야 하는 것 전부.
///
/// 세 절이다 — 이전 Cycle · 현재 Cycle · 지금 자리. 첫 Cycle 이면 첫 절이 없다(§7).
pub fn context(project: &Project) -> String {
    let cycles = project.cycles();
    let mut out = String::new();
    write_preamble(&mut out);
    write_previous_cycles(&mut out, cycles);
    write_abandoned_cycle(&mut out, cycles);
    write_current_cycle(&mut out, cycles);
    write_here(&mut out, project);
    out
}

fn write_preamble(out: &mut String) {
    out.push_str(
        "GIL context — 지금 자리에서 이어 걷기 위해 알아야 하는 것.\n\n\
         해상도는 거리가 정한다: 지나온 Cycle 은 그 Cycle 을 대표하는 투영까지, 지금 Cycle 은\n\
         Step Report 까지, 서 있는 자리는 규칙까지. 지나온 Cycle 의 Step Graph 는 여기 접혀\n\
         있을 뿐 사라지지 않고 원본 Graph 에 보존된다.\n",
    );
}

// ── ① 이전 Cycle — Cycle Report 해상도 ─────────────────────────────────────

/// 이 자리로 이어진 **조상** Cycle 들. 조상마다 **투영 하나**씩.
///
/// 대상은 `parent` 사슬이 지나온 Cycle 뿐이다([`Cycles::lineage`]) — 만든 순서도, 형제
/// 가지도 아니다. 이어받을 것이 있는 Cycle 은 계보 위에 있는 것들이다.
///
/// # "Cycle 해상도" 는 저장된 칸만 뜻하지 않는다
///
/// Cycle Report 는 `problem`·`success_condition`·`lesson` 을 **일부러 갖지 않는다**
/// (Cycle Model §11 — 두 자리에 같은 것을 적으면 한쪽이 낡는다). 그래서 저장된 칸만 실으면
/// 새 세션은 그 Cycle 이 무엇을 실험했는지조차 모른 채 판정만 받는다.
///
/// Context Model §7 이 정한 것은 그래서 **선택적 투영**이다: Cycle 을 대표하는 정보를
/// 원본 Graph 의 구조적 참조에서 읽되, 안의 Step Graph 를 다시 펼치지 않는다.
///
/// ```text
/// 실험 목적·성공 기준 ← 그 Cycle 의 유일하고 immutable 한 Define
/// 판정의 교훈         ← Cycle Report 의 outcome_ref 가 가리킨 Outcome
/// 판정·인수인계·다음 방향 ← Cycle Report
/// ```
///
/// **펼치는 것과 대표를 읽는 것은 다르다.** Step 의 이름도, Hypothesis·Verify·Analysis 도,
/// 되돌아가 버린 갈래의 판정도, 시간순 전개도 여기 오지 않는다. 시작점과 끝점만 읽는다.
///
/// 조상은 언제나 성공한 Cycle 이다(실패한 Cycle 은 자식을 두지 못한다). 되돌아오며 버린
/// 실패 Cycle 은 계보 위에 없으므로 이 절에 오지 않고, 바로 다음 절이 따로 싣는다 —
/// **같은 실패를 되풀이하지 않으려면 그 Report 가 반드시 전해져야 한다**(Cycle Model §10).
fn write_previous_cycles(out: &mut String, cycles: &Cycles) {
    let lineage = cycles
        .lineage(cycles.current_id())
        .expect("current 는 언제나 실재하는 Cycle 을 가리킨다");
    let ancestors = &lineage[..lineage.len() - 1];
    if ancestors.is_empty() {
        // 첫 Cycle 이면 이 절이 없다(§7). 빈 제목만 남기면 읽는 쪽은 무언가 빠졌다고 읽는다.
        return;
    }

    let _ = write!(
        out,
        "\n═══ 이전 Cycle ═══\n\
         ({}개 · 이 자리로 이어진 조상만 · 조상마다 Cycle 해상도의 투영 하나)\n\
         읽은 원본 — 실험 목적·성공 기준: 그 Cycle 의 유일한 Define · 판정의 교훈:\n\
         그 Cycle 의 outcome_ref 가 가리킨 Outcome · 나머지: 그 Cycle 의 Report.\n\
         안의 Step Graph 는 펼치지 않는다 — 시도와 전환의 전개는 원본 Graph 에 그대로 있다.\n",
        ancestors.len()
    );

    for cycle in ancestors {
        write_one_previous_cycle(out, cycle);
    }
}

/// **되돌아오며 버린 실패 Cycle** — 계보 위에는 없지만 반드시 전해야 하는 것.
///
/// 실패 Cycle Report 는 늘 전달한다. 같은 실패를 되풀이할 수 있기 때문이다(Cycle Model §10).
/// 그러나 그 Cycle 은 **계보의 조상이 아니다** — 여기 실린다고 해서 `parent` 사슬에 낀 것이
/// 아니고, 그 사실을 절 이름과 한 줄로 함께 말한다.
///
/// 두 자리에서 온다.
///
/// ```text
/// pending 이 있다        방금 되돌아왔고 아직 새 Cycle 을 열지 않았다
/// 지금 Cycle 이 갈래다   그 Cycle 의 revisit_from 이 가리키는 실패
/// ```
///
/// 조상과 **같은 해상도**로 싣는다 — 안의 Step Graph 는 펼치지 않는다.
fn write_abandoned_cycle(out: &mut String, cycles: &Cycles) {
    let Some(from) = cycles
        .pending_revisit()
        .or_else(|| cycles.current().revisit_from())
    else {
        return;
    };
    let Some(cycle) = cycles.node(from) else {
        return; // 복원이 이미 막았을 자리다. 없는 것을 지어내지 않는다.
    };

    let _ = write!(
        out,
        "\n═══ 되돌아오며 버린 Cycle ═══\n\
         (계보의 조상이 **아니다** — 여기서 갈라져 나왔을 뿐이다. 같은 실패를 되풀이하지\n\
         않으려면 이 Report 를 읽어야 한다. 조상과 같은 해상도로 싣는다.)\n"
    );
    write_one_previous_cycle(out, cycle);
}

/// 조상 하나의 투영 — **명세가 고른 자리만.**
///
/// 여기는 화이트리스트다. Cycle Report 에 칸이 늘어도 이 절은 자동으로 넓어지지 않는다 —
/// 새 칸이 story·context·history 중 어디에 필요한지는 명세가 정하고, 정해진 뒤에 이 자리에
/// 명시적으로 온다. 자동 노출은 편해 보이지만, 그러면 "새 세션이 무엇을 받는가" 를 정하는
/// 자리가 명세가 아니라 Report 를 적는 사람이 된다.
fn write_one_previous_cycle(out: &mut String, cycle: &Cycle) {
    let _ = write!(out, "\n{} · {}", cycle.id(), cycle.kind());
    let Some(report) = cycle.report() else {
        // 닫힌 Cycle 은 Report 를 지닌다(그것이 닫힘의 조건이다). 그래도 파일이 두 번째
        // 통로라 여기 닿을 수 있다 — 그때는 없다고 말한다. 조용히 건너뛰면 이어받을
        // 것이 하나 사라진 줄 모른다.
        let _ = writeln!(out, " (Cycle Report 가 없다)");
        return;
    };
    match report.get(VERDICT) {
        Some(verdict) => {
            let _ = writeln!(out, " · {verdict}");
        }
        None => {
            let _ = writeln!(out);
        }
    }

    let mut projected: Vec<(&str, String)> = Vec::new();
    if let Some(define) = cycle.define() {
        if let Some(problem) = define.get(PROBLEM) {
            projected.push(("실험 목적", problem.to_string()));
        }
        if let Some(condition) = define.get(SUCCESS_CONDITION) {
            projected.push(("성공 기준", condition.to_string()));
        }
    }
    if let Some(lesson) = cycle.judged_lesson() {
        projected.push(("판정의 교훈", lesson.to_string()));
    }
    if let Some(summary) = report.get(HANDOFF_SUMMARY) {
        projected.push(("다음 Cycle 에 넘긴 것", summary.to_string()));
    }
    if let Some(direction) = next_direction_of(report) {
        projected.push(("다음 방향", direction));
    }
    write_block(out, &projected);
}

/// 다음 방향 한 덩이 — 적힌 동작 그대로, 그 아래에 까닭.
///
/// 동작을 사람의 말로 옮기지 않는다. 이 글의 독자는 그 낱말 그대로 다음 Cycle Report 를
/// 적어야 하는 Agent 다(사람의 말로 옮기는 것은 `gil story` 의 몫이다).
fn next_direction_of(report: &Report) -> Option<String> {
    let action = report.get(NEXT_ACTION)?;
    Some(match report.get(NEXT_REASON) {
        Some(reason) if !reason.is_empty() => format!("{action}\n{reason}"),
        _ => action.to_string(),
    })
}

/// 이름표 붙은 값들 — 빈 줄로 갈리고, 값은 한 단 더 들여쓴다.
fn write_block(out: &mut String, fields: &[(&str, String)]) {
    for (label, value) in fields {
        let _ = writeln!(out, "\n  {label}");
        for line in value.lines() {
            let _ = writeln!(out, "    {line}");
        }
    }
}

// ── ② 현재 Cycle — Step Report 해상도 ──────────────────────────────────────

/// 지금 Cycle 안에서 지금까지 난 Step 들. **닫힌 것은 Report 째로, 열린 것은 상태로.**
fn write_current_cycle(out: &mut String, cycles: &Cycles) {
    let cycle = cycles.current();
    let _ = write!(
        out,
        "\n═══ 현재 Cycle ═══\n{} · {} · {}",
        cycle.id(),
        cycle.kind(),
        match cycle.is_closed() {
            true => "닫힘",
            false => "열림",
        }
    );
    match cycle.parent() {
        Some(parent) => {
            let _ = writeln!(out, " · 부모 {parent}");
            // 이어받은 것을 여기 다시 적지 않는다 — 원본은 바로 위 절에 이미 있다.
            let _ = match cycles.inherited_report(cycle.id()).is_some() {
                true => writeln!(
                    out,
                    "이어받은 것: {parent} 의 Cycle Report — 바로 위 [이전 Cycle] 에 있다."
                ),
                false => writeln!(out, "이어받은 것: {parent} (Cycle Report 가 없다)"),
            };
        }
        None => {
            let _ = writeln!(out, " · 뿌리 (이어받은 Cycle 이 없다)");
        }
    }

    let walk = cycle.steps();
    if walk.nodes().is_empty() {
        let _ = writeln!(out, "\n아직 아무 Step 도 열지 않았다.");
        return;
    }

    for node in walk.nodes() {
        let _ = write!(out, "\n{} {} · {}", node.id, node.kind, node.status);
        if let Some(from) = node.revisit_from {
            let _ = write!(out, " · {from} 에서 되돌아와 낸 갈래");
        }
        let _ = writeln!(out);
        match &node.report {
            Some(report) => {
                let declared = step_close_requires(cycle.rules(), cycle.kind(), node.kind);
                write_report_fields(out, &declared, report, "  ");
            }
            None => {
                let _ = writeln!(out, "  (아직 Report 를 적지 않았다)");
            }
        }
    }

    if let Some(report) = cycle.report() {
        let _ = writeln!(out, "\n이 Cycle 의 Cycle Report");
        let declared = cycle_close_requires(cycle);
        write_report_fields(out, &declared, report, "  ");
    }
}

// ── ③ 지금 자리 — 상태 · 다음 행동 · 규칙 ──────────────────────────────────

fn write_here(out: &mut String, project: &Project) {
    let cycles = project.cycles();
    let cycle = cycles.current();
    let walk = cycle.steps();

    let _ = write!(
        out,
        "\n═══ 지금 자리 ═══\n{} · {} · {}\n",
        cycle.id(),
        cycle.kind(),
        match cycle.is_closed() {
            true => "닫힘",
            false => "열림",
        }
    );
    match walk.current().and_then(|id| walk.node(id)) {
        Some(node) => {
            let _ = writeln!(out, "자리: {} {} · {}", node.id, node.kind, node.status);
        }
        None => {
            let _ = writeln!(out, "자리: 이 Cycle 에서 아직 아무것도 열지 않았다");
        }
    }
    let _ = writeln!(
        out,
        "걸어온 것: Cycle {}개 · 이 Cycle 의 Step {}개 (닫힘 {})",
        cycles.nodes().len(),
        walk.nodes().len(),
        walk.history().count()
    );

    write_current_will(out, project);

    let _ = writeln!(out, "\n[다음에 할 수 있는 것]");
    out.push_str(&next_moves(cycles));

    write_rules_here(out, cycles);
    write_report_principles(out);
}

/// **지금 무엇을 하려는가.**
///
/// 이 절이 없어서 값을 치렀다(Roadmap M2C): 상태와 가설은 정확히 복원했는데 열린 Verify 에서
/// 무엇을 먼저 해야 하는지 몰라, 검증하기도 전에 `gil close` 를 부른 Agent 가 있었다.
///
/// 지나온 행동들을 여기서 펼치지 않는다 — 이어 걷는 데 필요한 것은 **지금 걸린 하나**다.
/// 없으면 없다고 말한다. GIL 은 다음 행동을 추측하지 않는다(Will Model §10).
fn write_current_will(out: &mut String, project: &Project) {
    let existence = project.current_existence();
    let _ = write!(
        out,
        "\n[지금 하려는 행동]\n존재: {} · {}\n",
        existence.id(),
        existence.current_journey()
    );
    let Some(will) = project.active_will() else {
        out.push_str("걸린 행동이 없다 — 다음에 무엇을 할지는 `gil open` 에서 적는다.\n");
        return;
    };
    let _ = write!(
        out,
        "{} · {}\n  목표: {}\n  지금 할 일: {}\n  완료 조건: {}\n",
        will.id(),
        will.target(),
        indent_more(will.objective()),
        indent_more(will.next_action()),
        indent_more(will.done_when())
    );
}

/// 여러 줄로 적힌 값이 다음 항목처럼 보이지 않게.
fn indent_more(value: &str) -> String {
    value.replace('\n', "\n    ")
}

/// 지금 할 수 있는 것들 — **판정을 여기서 새로 쓰지 않는다.**
///
/// 실행하는 그 자리에게 묻는다([`Cycles::openable_here`]·[`Cycles::can_close`]·
/// [`Cycles::why_not_open_child`]). 안내와 실행이 갈리면 안내를 믿은 Agent 가 한 번
/// 실패하고서야 옳은 수를 알게 된다(실사용 보고 #123).
///
/// `gil status` 와 `gil context` 가 **같은 이 함수**를 읽는다. 두 자리에 적으면 한쪽이 낡는다.
pub fn next_moves(cycles: &Cycles) -> String {
    let cycle = cycles.current();

    if !cycle.is_closed() {
        let here = cycle.steps().current().and_then(|id| cycle.steps().node(id));
        if here.is_some_and(|node| !node.is_closed()) {
            return "다음: 여기를 먼저 닫는다 — `gil close` (Report 는 stdin 으로)\n".to_string();
        }

        let mut out = String::new();
        let openable = cycle.openable_here();
        let names: Vec<&str> = openable.iter().map(|kind| kind.as_str()).collect();
        if !names.is_empty() {
            out.push_str(&format!("다음: 열 수 있는 것 — {}\n", names.join(", ")));
        }
        if cycle.can_close() {
            let lead = match names.is_empty() {
                true => "다음",
                false => "또는",
            };
            out.push_str(&format!(
                "{lead}: 이 Cycle 을 닫는다 — `gil close` (Cycle Report 는 stdin 으로)\n"
            ));
        }
        if out.is_empty() {
            out.push_str("다음: 여기서 할 수 있는 것이 없다\n");
        }
        return out;
    }

    // **되돌아온 자리** — 여기서 할 일은 하나뿐이다.
    if let Some(from) = cycles.pending_revisit() {
        return format!(
            "다음: {} 에서 되돌아왔다 — 이 자리 아래에 새 Cycle 을 연다\n\
             \x20     `gil open interview` · `gil open experiment`\n",
            from.to_ref()
        );
    }

    // 닫힌 Cycle 이 되돌아가겠다고 적었는가 — **밟아 보고 답한다.**
    if cycles.can_revisit() {
        return format!(
            "다음: {} 이(가) 적어 둔 대로 조상으로 되돌아간다 — `gil revisit` (인수 없음)\n\
             \x20     그 뒤 그 자리 아래에 새 Cycle 을 연다 — `gil open <종류>`\n",
            cycle.id()
        );
    }

    // 닫힌 Cycle — 적어 둔 방향을 밟을 수 있는가.
    match cycles.why_not_open_child() {
        None => format!(
            "다음: {} 이(가) 적어 둔 대로 다음 Cycle 을 연다 — `gil open <종류>`\n",
            cycle.id()
        ),
        Some(why) => format!(
            "다음: {why}\n\
             \x20     적어 둔 방향은 `gil story` 에서 읽을 수 있다.\n"
        ),
    }
}

/// 지금 무언가를 닫으려면 무엇이 있어야 하는가 — **명세에서 그대로 읽는다.**
///
/// 칸의 목록도, 값의 제약도 여기 옮겨 적지 않는다. `gil-spec.yaml` 이 자라면 이 절도 함께
/// 자란다 — 옮겨 적으면 명세가 바뀐 날부터 새 세션이 낡은 규칙을 받는다.
fn write_rules_here(out: &mut String, cycles: &Cycles) {
    let cycle = cycles.current();
    if cycle.is_closed() {
        // 닫힌 Cycle 에서는 아무 Report 도 쓰지 않는다. 다음 수는 Cycle 을 여는 것이고,
        // 그것은 바로 위 절이 이미 말했다.
        return;
    }

    let walk = cycle.steps();
    let here = walk.current().and_then(|id| walk.node(id));

    // 계약을 읽는 자리는 하나다([`CloseContract`]) — Receipt·help·거절과 같은 것을 본다.
    let mut blocks: Vec<CloseContract> = Vec::new();
    match here.filter(|node| !node.is_closed()) {
        // 열려 있는 자리가 있으면 지금 필요한 규칙은 그 자리를 닫는 규칙 하나뿐이다.
        Some(node) => blocks.extend(cycle.step_contract(node.id, node.kind)),
        None => {
            for kind in cycle.openable_here() {
                blocks.extend(cycle.contract_of_kind(kind));
            }
            if cycle.can_close() {
                blocks.extend(cycle.close_contract());
            }
        }
    }

    if blocks.is_empty() {
        return;
    }
    let _ = writeln!(out, "\n[닫는 데 필요한 칸]");
    for (index, contract) in blocks.into_iter().enumerate() {
        // 블록은 빈 줄로 갈린다 — 색에 기대지 않고 눈으로 갈려야 한다.
        if index > 0 {
            out.push('\n');
        }
        let _ = writeln!(out, "{}", contract.subject());
        out.push_str(&contract.constraints("  "));
    }
}

/// Report 를 쓰는 원칙.
///
/// 문법이 판정하지 못하는 **의미의 불변식**이라 `gil-spec.yaml` 에 없다
/// (GIL Specification v0.1 「Report 작성 불변식」이 원본이고, 여기는 그 요약이다).
/// 새 세션에는 이것이 필요하다 — 없이 걸은 실제 dogfood 가 정의되지 않은 내부 단계명
/// `S1` 을 Report 에 남겼고, 그 Cycle 에 없던 사람은 그 Report 를 읽지 못했다.
fn write_report_principles(out: &mut String) {
    out.push_str(
        "\n[Report 를 쓰는 원칙]  (GIL Specification v0.1 「Report 작성 불변식」)\n\
         이 Node 에 참여하지 않은 협업자가 혼자 읽어도 같은 대상과 근거를 짚을 수 있게 적는다.\n\
         정의하지 않은 약어·내부 단계 코드·이슈 번호만으로 대상이나 결론을 말하지 않는다.\n\
         관측(verify)과 해석(analysis)을 섞지 않고, 성공·실패 주장은 미리 정한 기준과\n\
         Report·Artifact 증거로 이을 수 있게 적는다.\n",
    );
}

// ── 명세에서 읽어 오는 것들 ────────────────────────────────────────────────

/// 이전 Cycle 절이 원본에서 읽어 오는 칸의 이름 — `gil-spec.yaml` 이 부르는 그대로.
use crate::report::field::{
    HANDOFF_SUMMARY, NEXT_ACTION, NEXT_REASON, PROBLEM, SUCCESS_CONDITION, VERDICT,
};

fn step_close_requires(rules: &RuleSet, cycle: CycleKind, kind: NodeKind) -> Vec<String> {
    rules
        .rules(cycle, kind)
        .map(|rules| rules.close_requires.clone())
        .unwrap_or_default()
}

fn cycle_close_requires(cycle: &Cycle) -> Vec<String> {
    cycle
        .rules()
        .cycle_rules(cycle.kind())
        .map(|rules| rules.close_requires.clone())
        .unwrap_or_default()
}

// ── Report 를 적는 꼴 ──────────────────────────────────────────────────────

/// Report 의 칸들을 **명세가 정한 순서**로, 그 뒤에 명세가 모르는 칸을 이어서.
///
/// 이름을 사람의 말로 옮기지 않는다 — 이 글의 독자는 이 칸 이름 그대로 다음 Report 를
/// 적어야 하는 Agent 다(사람의 말로 읽는 것은 `gil story` 의 몫이다).
fn write_report_fields(out: &mut String, declared: &[String], report: &Report, indent: &str) {
    let extra: Vec<&str> = report
        .field_names()
        .filter(|name| !declared.iter().any(|field| field == name))
        .collect();

    for field in declared.iter().map(String::as_str).chain(extra) {
        let Some(value) = report.get(field) else {
            continue;
        };
        match value.contains('\n') {
            // 여러 줄은 이름만 두고 아래로 들여쓴다 — 어디까지가 한 칸의 값인지 눈으로 갈린다.
            true => {
                let _ = writeln!(out, "{indent}{field}:");
                for line in value.lines() {
                    let _ = writeln!(out, "{indent}  {line}");
                }
            }
            false => {
                let _ = writeln!(out, "{indent}{field}: {value}");
            }
        }
    }
}
