//! **`gil status` 가 사람에게 적는 말** — CLI 와 MCP 가 **같은 자리**에서 쓴다.
//!
//! 이 파일은 `main.rs` 에 있던 것을 그대로 옮긴 것이다. 옮긴 이유는 하나다 — 진입점이
//! 둘이 됐기 때문이다. 사람이 터미널에서 부르든 Agent 가 MCP 로 부르든 **같은 문장**이
//! 나와야 하고, 그러려면 문장을 짓는 자리가 하나여야 한다. 두 벌로 두면 한쪽이 낡는다.
//!
//! 나뉘는 것은 **Project 를 찾는 법**뿐이다(CLI 는 조상 탐색, MCP 는 정확 경로). 검증된
//! [`ProjectSession`] 을 손에 넣은 뒤부터는 두 길이 여기 하나로 합류한다.
//!
//! `state_is_elsewhere` 는 "기록:" 줄을 낼지를 부르는 쪽이 정한다 — 그 판정은 진입 계약에
//! 달렸고(CLI 는 cwd, MCP 는 project_root), 이 자리는 그것을 알지 못한다.

use crate::{NodeKind, ProjectSession, WorldState};

pub fn where_now(session: &ProjectSession, state_is_elsewhere: bool) -> String {
    let cycles = session.project().cycles();
    let cycle = cycles.current();
    let walk = cycle.steps();
    let mut out = String::new();

    if state_is_elsewhere {
        out.push_str(&format!("기록: {}\n", crate::said_path(session.state_path())));
    }

    // ① 어느 Cycle 인가 — 이름·종류·상태, 그리고 어디에서 이어받았는가.
    let state = match cycle.report().and_then(|report| report.get("verdict")) {
        Some(verdict) => format!("닫힘 · {verdict}"),
        None => "열림".to_string(),
    };
    out.push_str(&format!("{} {} ({state})", cycle.id(), cycle.kind()));
    match cycle.parent() {
        Some(parent) => out.push_str(&format!(" · 부모 {parent}\n")),
        None => out.push_str(" · 뿌리\n"),
    }
    // **되돌아온 자리인가.** 지금 서 있는 것은 닫힌 조상이고, 다음 수가 평소와 다르다.
    if let Some(from) = cycles.pending_revisit() {
        out.push_str(&format!(
            "되돌아옴: {} 에서 갈라져 여기 섰다 — 아직 새 Cycle 을 열지 않았다\n",
            from.to_ref()
        ));
    }
    // 갈래로 난 Cycle 이면 그 출처를 말한다 — 부모만 보면 평범히 이어 난 것과 같아 보인다.
    if let Some(from) = cycle.revisit_from() {
        out.push_str(&format!("갈래 출처: {} (계보의 변이 아니다)\n", from.to_ref()));
    }

    // ② 무엇을 이어받았는가. **원본은 부모에게 있다** — 여기서는 있다는 사실만 말한다.
    if let Some(parent) = cycle.parent() {
        match cycles.inherited_report(cycle.id()).is_some() {
            true => out.push_str(&format!(
                "이어받음: {parent} 의 Cycle Report — 그 내용은 `gil story` 에 있다\n"
            )),
            false => out.push_str(&format!("이어받음: {parent} (Cycle Report 가 없다)\n")),
        }
    }

    // ③ 그 Cycle 안에서 어느 Step 에 서 있는가.
    let here = walk.current().and_then(|id| walk.node(id));
    match here {
        Some(node) => out.push_str(&format!("자리: {} {} ({})\n", node.id, node.kind, node.status)),
        None => out.push_str("자리: 아직 아무것도 열지 않았다\n"),
    }
    out.push_str(&format!(
        "걸어온 것: Cycle {}개 · 이 Cycle 의 Step {}개 (닫힘 {})\n",
        cycles.nodes().len(),
        walk.nodes().len(),
        walk.history().count()
    ));

    // ④ 지금 누가 행동하며 무엇을 하려는가 — **짧게.** 전체 Journey 는 펼치지 않는다.
    let existence = session.project().current_existence();
    out.push_str(&format!(
        "존재: {} · {}\n",
        existence.id(),
        existence.current_journey()
    ));
    match session.project().active_will() {
        Some(will) => out.push_str(&format!(
            "하려는 것: {} · {} — {}\n",
            will.id(),
            will.target(),
            first_line(will.next_action())
        )),
        None => out.push_str("하려는 것: 걸린 행동이 없다\n"),
    }

    // ⑤ 지금 세계는 기준과 같은가 — **짧은 nudge 하나.**
    out.push_str(&world_nudge(session));

    // ⑥ 다음에 무엇을 할 수 있는가. **안내는 실행과 같은 자리에서 나온다.**
    out.push_str(&crate::next_moves(cycles));
    out
}

/// 지금 Artifact 세계 — 기준이 무엇이고, 같은가 다른가, 다르면 지금 무엇을 할 수 있는가.
///
/// **전체 목록도 내부 주소도 내지 않는다.** 공개 표면은 `snapshot:A*` 하나이고, 여기서
/// 필요한 것은 네 가지 물음의 답뿐이다 — 기준·상태·확정 가능 여부·지금 밟을 수 있는 수.
fn world_nudge(session: &ProjectSession) -> String {
    let state = match session.world_state() {
        Ok(state) => state,
        // 세계를 읽는 것 자체가 안 되면(창고 손상 등) status 를 통째로 실패시키지 않는다 —
        // 서 있는 자리는 이미 위에서 말했고, 그것은 여전히 참이다.
        Err(err) => {
            return format!("\n현재 세계\n  읽지 못했다\n\n이유\n{}\n\n현재 상태는 변경하지 않았다.\n", indent(&err.to_string()));
        }
    };

    match state {
        WorldState::Clean { world } => format!("\n현재 세계\n  {world} · clean\n\n"),
        WorldState::Unknown { world, said } => format!(
            "\n현재 세계\n  기준: {world}\n  상태: 확인하지 못했다\n\n이유\n{}\n\n\
             현재 상태는 변경하지 않았다.\n\n",
            indent(&said)
        ),
        WorldState::Dirty { world, .. } => {
            let mut out = format!("\n현재 세계\n  기준: {world}\n  상태: dirty\n\n");
            out.push_str(&match open_verify(session) {
                // 세계를 확정할 권한은 Verify 에만 있다(Artifact Model §5).
                true => String::from(
                    "이 Verify 를 닫으면 바뀐 세계를 관측해 Snapshot 으로 확정한다.\n\n",
                ),
                // **밟을 수 있는 길만 말한다.** Interview 안에는 verify 가 없고, 이 Cycle 을
                // 닫는 것도 같은 gate 에 막힌다 — 그러니 먼저 되돌리는 수뿐이다.
                false => String::from(
                    "이 자리에서는 Artifact 변경을 확정할 수 없다.\n\
                     먼저 `gil restore` 로 기준 세계를 복원한다.\n\
                     현재 Step 과 Active Will 은 그대로 열린 채 남는다.\n\n",
                ),
            });
            out
        }
    }
}

/// 지금 열려 있는 자리가 Verify 인가.
fn open_verify(session: &ProjectSession) -> bool {
    let cycle = session.project().cycles().current();
    cycle
        .step_now_open()
        .and_then(|at| cycle.steps().node(at))
        .is_some_and(|node| node.kind == NodeKind::Verify)
}

/// 여러 줄이면 첫 줄만 — `gil status` 는 세 줄로 답하는 자리다.
fn first_line(text: &str) -> String {
    match text.lines().next() {
        Some(first) if first.len() < text.len() => format!("{first} …"),
        Some(first) => first.to_string(),
        None => String::new(),
    }
}

/// 여러 줄짜리 토막을 한 단 들여쓴다 — 뒷줄이 제목처럼 보이지 않게.
fn indent(text: &str) -> String {
    text.lines()
        .map(|line| match line.is_empty() {
            true => String::new(),
            false => format!("  {line}"),
        })
        .collect::<Vec<_>>()
        .join("\n")
}
