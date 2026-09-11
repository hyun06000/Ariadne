//! Monitor 의 **안전한 standalone HTML** — 저장해서 바로 열 수 있는 문서 하나.
//!
//! server 도, build 도, JavaScript 도 없다. 파일 하나를 브라우저에 던지면 그대로 읽힌다.
//!
//! # 신뢰하지 않는 글을 다루는 자리다
//!
//! Report·Define·Will·world 의 이유는 전부 **사람이나 Agent 가 적은 글**이다. 그것이
//! markup 이 되면 화면이 문서가 아니라 실행기가 된다. 그래서 이 파일에는 규칙이 셋뿐이다.
//!
//! ```text
//! ① 사용자 글은 언제나 text node 로만 간다 — [`text`] 를 지나지 않는 값이 없다
//! ② tag·attribute·class·href·src·style 에는 사용자 글이 **한 글자도** 들어가지 않는다
//! ③ 문서 스스로가 CSP 로 script·외부 자원·form 을 전부 막는다
//! ```
//!
//! ①이 뚫려도 ③이 남고, ③이 무시되는 옛 브라우저에서도 ①이 남는다. 둘 중 하나에만
//! 기대지 않는다.
//!
//! # 색으로 뜻을 나르지 않는다
//!
//! 열림/닫힘·clean/dirty/unknown·success/failure·활성/비활성·부모/갈래 출처는 **전부
//! 낱말로도 적힌다**([`say`]). 색을 못 보는 눈에도, 색이 없는 인쇄에도 같은 사실이 남는다.
//! 그 낱말은 plain text renderer 와 **같은 자리에서** 온다.
//!
//! # DOM 이름은 아직 계약이 아니다
//!
//! class 와 요소 배치는 v0 의 공개 API 가 아니다. 지켜지는 것은 **절의 의미와 그 안의
//! 사실**이고, 그것을 두 renderer 가 함께 보존하는지는 시험이 잰다(Monitor Model §7.4).

use std::fmt::Write as _;

use super::{graph, say, svg};
use super::{
    CycleFacts, CycleReportFacts, InactiveCycle, MonitorSnapshot, NextAction, StepFacts, WillFacts,
    WorldFacts,
};

/// 문서가 스스로에게 거는 자물쇠.
///
/// **`style-src` 하나만 열려 있다.** 그것도 이 파일이 소유한 고정 상수를 위해서이고,
/// 사용자 글은 CSS 에 닿는 길이 없다 — [`STYLE`] 은 `const` 이므로 값이 끼어들 자리가
/// 문법적으로 없다.
const CSP: &str = "default-src 'none'; \
                   script-src 'none'; \
                   img-src 'none'; \
                   font-src 'none'; \
                   connect-src 'none'; \
                   object-src 'none'; \
                   base-uri 'none'; \
                   form-action 'none'; \
                   style-src 'unsafe-inline'";

/// 이 renderer 가 소유한 **고정** stylesheet.
///
/// 바깥에서 아무것도 불러오지 않는다 — 글꼴은 시스템의 것을 쓰고, 그림도 아이콘도 없다.
/// 좁은 화면에서 가로로 밀리지 않도록 긴 값과 명령은 어디서든 접힌다.
const STYLE: &str = "\
:root { color-scheme: light dark; }
body {
  margin: 0 auto; padding: 1rem; max-width: 60rem; line-height: 1.6;
  font-family: system-ui, -apple-system, 'Segoe UI', 'Noto Sans KR', sans-serif;
}
h1 { font-size: 1.4rem; }
h2 { font-size: 1.1rem; margin: 2rem 0 0.5rem; padding-top: 0.5rem; border-top: 1px solid; }
h3 { font-size: 1rem; margin: 1rem 0 0.25rem; font-weight: 600; }
p.note { margin: 0.25rem 0 1rem; font-size: 0.9rem; }
dl { margin: 0.25rem 0; }
dt { font-weight: 600; margin-top: 0.5rem; }
dd { margin: 0 0 0 1rem; white-space: pre-wrap; overflow-wrap: anywhere; }
ol, ul { margin: 0.25rem 0; padding-left: 1.25rem; }
ol.path { list-style: none; padding-left: 0; }
ol.path ol.path { padding-left: 1.25rem; border-left: 2px solid; }
li { margin: 0.5rem 0; }
li.branch { border-left: 4px dotted; padding-left: 0.75rem; }
section.warn { border: 3px solid; padding: 0.5rem 1rem; margin-bottom: 1rem; }
section.warn h2 { border-top: none; padding-top: 0; margin-top: 0.5rem; }
section.focus dt { font-weight: 700; }
section.focus dd { margin-bottom: 0.6rem; }
details.record { margin-top: 1.5rem; }
details.record summary { font-weight: 700; padding: 0.5rem 0; cursor: default; }
details.record h2 { font-size: 1.05rem; }
ol.legend { padding-left: 1.25rem; }
ol.legend li { margin: 0.15rem 0; }
svg.graph { display: block; width: 100%; height: auto; max-width: 100%; overflow: visible; }
svg.graph text { font-family: inherit; fill: currentColor; }
svg.graph .g-kind { font-size: 13px; font-weight: 700; }
svg.graph .g-said { font-size: 12px; }
svg.graph .g-mark { font-size: 11px; font-weight: 700; }
svg.graph .g-ref { font-size: 10px; opacity: 0.6; text-anchor: end; }
svg.graph .g-here { font-size: 11px; font-weight: 700; }
svg.graph .g-cycle .g-here { text-anchor: end; }
svg.graph .g-group { font-size: 12px; font-weight: 700; }
svg.graph .g-group-mark { font-size: 11px; opacity: 0.8; }
svg.graph .g-origin { font-size: 11px; opacity: 0.85; }
svg.graph .g-folded { font-size: 11px; opacity: 0.6; }
svg.graph .g-off { opacity: 0.5; }
svg.graph .g-link { opacity: 0.4; }
ol.legend ol { font-size: 0.95rem; opacity: 0.9; }

/* 그림과 목록은 **같은 사실의 두 표현**이다. 그래서 둘 다 두되, 한 번에 하나만 보인다.
   숨는 쪽도 접근성 나무에서는 사라지지 않는다 — `display: none` 도 `aria-hidden` 도
   쓰지 않고 자리만 1px 로 접어 둔다. 전환은 CSS 뿐이고 JavaScript 는 없다.

   699px 은 재어서 고른 값이다. 700px 폭에서 그림의 가장 작은 글자가 아직 읽히고
   (kind 11.6px · 주소 8.9px), 그보다 좁아지면 읽을 수 없게 줄어든다. */
.for-readers {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}
@media (max-width: 699px) {
  svg.graph { display: none; }
  .for-readers {
    position: static;
    width: auto;
    height: auto;
    margin: 0;
    overflow: visible;
    clip-path: none;
    white-space: normal;
  }
}
code { font-family: ui-monospace, 'SFMono-Regular', Menlo, monospace; overflow-wrap: anywhere; }
";

/// **Snapshot 하나를 완전한 HTML5 문서로.**
///
/// 같은 Snapshot 은 언제 불러도 **바이트까지 같은 문서**를 만든다 — 관측 시각도, 무작위
/// id 도 싣지 않기 때문이다.
pub fn render_monitor_html(seen: &MonitorSnapshot) -> String {
    let mut out = open_document();
    facts(&mut out, seen);
    close_document(&mut out);
    out
}

/// 문서의 머리 — **모든 표현이 같은 자물쇠와 같은 stylesheet 를 쓴다.**
pub(super) fn open_document() -> String {
    open_document_refreshing(None)
}

/// 같은 문서 — 다만 **스스로를 다시 받아오는 표지** 하나를 달 수 있다.
///
/// `Some` 은 loopback server 만 쓴다. 저장해서 여는 standalone 문서에 이것이 들어가면 파일
/// 하나가 열릴 때마다 없는 주소를 두드리게 된다.
///
/// **주소는 server 가 정한 제 capability path 뿐이다.** 사용자 값에서 URL 을 만들지 않고,
/// 다른 곳으로 보내지도 않는다 — 그래서 이 표지가 새 바깥 통로가 되지 않는다.
/// JavaScript 도 외부 자원도 더하지 않는다.
pub(super) fn open_document_refreshing(refresh: Option<(u64, &str)>) -> String {
    let mut out = String::new();
    out.push_str("<!doctype html>\n<html lang=\"ko\">\n<head>\n");
    out.push_str("<meta charset=\"utf-8\">\n");
    out.push_str("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n");
    if let Some((seconds, path)) = refresh {
        let _ = writeln!(
            out,
            "<meta http-equiv=\"refresh\" content=\"{seconds}; url={}\">",
            text(path)
        );
    }
    let _ = writeln!(
        out,
        "<meta http-equiv=\"Content-Security-Policy\" content=\"{CSP}\">"
    );
    out.push_str("<title>GIL Monitor</title>\n");
    let _ = writeln!(out, "<style>\n{STYLE}</style>");
    out.push_str("</head>\n<body>\n<main>\n");
    out.push_str("<header>\n<h1>GIL Monitor</h1>\n</header>\n");
    out
}

pub(super) fn close_document(out: &mut String) {
    out.push_str("</main>\n</body>\n</html>\n");
}

/// Snapshot 하나가 만드는 절들 — **머리와 꼬리를 뺀 알맹이.**
pub(super) fn facts(out: &mut String, seen: &MonitorSnapshot) {
    focus_now(out, seen);
    focus_todo(out, seen);
    picture(out, seen);
    focus_why(out, seen);
    record(out, seen);
}

// ── 첫 30초 ────────────────────────────────────────────────────────────────
//
// 2026-09-02 판독 실험 1 이 실패한 자리다. 정보가 없어서가 아니라 **전부 같은 무게로**
// 적혀 있어서, 무엇이 지금이고 무엇이 지난 일인지 눈으로 갈라지지 않았다.
//
// 그래서 순서를 계약으로 둔다.
//
// ```text
// [지금]         무엇을 묻고 있고, 무엇이면 성공인가
// [지금 할 일]    손으로 할 일 · 끝났다고 볼 조건 · 그 뒤에 칠 GIL 명령
// [그림]         여정의 구조
// [왜 여기 왔는가] 무엇이 실패했고 무엇을 배워 어디로 돌아왔는가
// [지나온 기록]   나머지 전부 — 접어 둔다
// ```

/// **[지금]** — 묻고 있는 것과 성공의 기준.
///
/// 둘을 **떨어뜨리지 않는다.** 판독 실험 1 에서 사람은 질문은 찾았지만 성공 기준은 찾지
/// 못했다. 둘이 다른 절에 있었기 때문이다.
fn focus_now(out: &mut String, seen: &MonitorSnapshot) {
    let cycle = &seen.current_cycle.facts;
    out.push_str("<section class=\"focus\">\n");
    heading(out, "지금");
    if cycle.experiment_definition.is_none() {
        note(out, say::NO_DEFINITION);
    }
    out.push_str("<dl>\n");
    match &cycle.experiment_definition {
        Some(define) => {
            pair(out, say::PROBLEM, &define.problem);
            pair(out, say::SUCCESS_CONDITION, &define.success_condition);
        }
        // 없는 질문을 지어내지 않는다. **이름표조차 붙이지 않는다** — `질문:` 이라고
        // 적는 순간 없는 것에 자리가 생기고, 그 자리는 언젠가 채워지고 싶어 한다.
        None => {}
    }
    match &seen.current_step {
        Some(step) => pair(out, "여기", &format!("{} · {}", say::here_title(cycle.kind), step_line(step))),
        None => pair(out, "여기", &format!("{} · {}", say::here_title(cycle.kind), say::NO_STEP_YET)),
    }
    pair(out, say::WORLD, say::world_of(seen.world.state));
    out.push_str("</dl>\n</section>\n");
}

/// **[지금 할 일]** — 손으로 하는 일과 GIL 이 하는 일을 가른다.
///
/// 판독 실험 1 에서 사람은 **과거 Cycle Report 의 다음 방향을 현재 행동으로 오인했다.**
/// 그래서 여기서는 셋을 이름 붙여 나란히 둔다.
///
/// ```text
/// 작업 행동      Will.next_action   실제 세계에서 손으로 하는 일
/// 완료 조건      Will.done_when     그것이 끝났다고 볼 조건
/// 그 일이 끝나면  GIL 명령            그러고 나서 칠 것
/// ```
///
/// **하나를 다른 하나로 대신하지 않는다.** 셋은 서로 다른 일이다.
fn focus_todo(out: &mut String, seen: &MonitorSnapshot) {
    out.push_str("<section class=\"focus\">\n");
    heading(out, "지금 할 일");
    out.push_str("<dl>\n");
    match &seen.current_will {
        Some(will) => {
            pair(out, "작업 행동", &will.next_action);
            pair(out, say::DONE_WHEN, &will.done_when);
        }
        None => pair(out, "작업 행동", say::NO_WILL),
    }
    match seen
        .next_actions
        .iter()
        .find_map(|action| action.command.as_deref())
    {
        Some(command) => pair_code(out, "그 일이 끝나면", command),
        None => pair(out, "그 일이 끝나면", say::NO_MOVE),
    }
    out.push_str("</dl>\n</section>\n");
}

/// **[그림]** — 구조는 공간이 말한다.
///
/// SVG 를 보지 못하는 환경과 화면 reader 를 위해 같은 사실의 짧은 목록을 함께 남긴다.
/// **ASCII 그림의 대체물이 아니다** — 목록이다.
fn picture(out: &mut String, seen: &MonitorSnapshot) {
    let plan = graph::render_monitor_graph(seen);
    out.push_str("<section class=\"picture\">\n");
    heading(out, "여정");
    out.push_str(&svg::render_monitor_svg(&plan));
    // SVG 를 보지 못하는 환경과 화면 reader 를 위한 같은 사실의 목록 — **그림의 순서
    // 그대로.** ASCII 그림이 아니라 목록이다.
    out.push_str("<div class=\"for-readers\">\n");
    if let Some(folded) = &plan.folded {
        let _ = writeln!(out, "<p class=\"note\">{}</p>", text(&folded.says()));
    }
    out.push_str("<ol class=\"legend\">\n");
    for group in &plan.groups {
        let standing = match group.standing {
            graph::Standing::Here => "현재 Cycle",
            graph::Standing::Active => "활성 경로",
            graph::Standing::LeftBehind => "지나온 갈래",
        };
        let _ = writeln!(
            out,
            "<li>{} — {} · {} (<code>{}</code>){}",
            text(&group.name),
            text(standing),
            text(group.mark.word()),
            text(&group.address),
            match &group.came_from {
                Some(origin) => format!(" · {}", text(&origin.says())),
                None => String::new(),
            }
        );
        out.push_str("\n<ol>\n");
        for row in plan.rows.iter().filter(|row| {
            row.row >= group.from_row && row.row <= group.to_row
        }) {
            let _ = writeln!(
                out,
                "<li>{}{} — {} (<code>{}</code>){}</li>",
                text(row.kind),
                match row.standing {
                    graph::Standing::Here => " · 현재",
                    _ => "",
                },
                text(row.mark.word()),
                text(&row.address),
                match &row.summary {
                    Some(said) => format!(" · {}", text(said)),
                    None => String::new(),
                }
            );
        }
        out.push_str("</ol>\n</li>\n");
    }
    out.push_str("</ol>\n</div>\n</section>\n");
}

/// **[왜 여기 왔는가]** — 지금 자리로 이어진 전환 하나만.
///
/// 참조 두 개를 나란히 보이는 것으로는 아무도 이해하지 못한다. **무엇이 실패했고 → 무엇을
/// 배웠고 → 어떻게 옮겼고 → 지금 무엇을 시험하는가**를 한 묶음으로 적는다.
fn focus_why(out: &mut String, seen: &MonitorSnapshot) {
    let came_from = seen
        .current_cycle
        .facts
        .revisit_from_cycle_ref
        .as_ref()
        .or(seen.pending_revisit.as_ref().map(|p| &p.from_cycle_ref));
    let Some(came_from) = came_from else {
        return;
    };
    let source = seen
        .inactive_cycles
        .iter()
        .find(|cycle| &cycle.cycle_ref == came_from);

    out.push_str("<section class=\"focus\">\n");
    heading(out, "왜 여기 왔는가");
    out.push_str("<dl>\n");
    match source {
        Some(source) => {
            // 사람의 이름이 먼저, typed reference 는 괄호 안에.
            pair(
                out,
                "이전 시도",
                &format!(
                    "{} — {} ({})",
                        graph::name_of(source.kind, &source.cycle_ref.to_string()),
                    graph::mark_of(
                        source.state,
                        true,
                        source.report.as_ref().map(|r| r.verdict.as_str())
                    )
                    .word(),
                    source.cycle_ref
                ),
            );
            if let Some(report) = &source.report {
                pair(out, "실패 이유", &report.handoff_summary);
                if let Some(lesson) = &report.outcome_lesson {
                    pair(out, "배운 것", lesson);
                }
                // **과거의 방향은 과거의 것이다.** 지금 할 일 위가 아니라 여기, 그리고
                // 이름에 「당시」를 붙여 둔다.
                if let Some(direction) = &report.next_direction {
                    pair(out, "당시 다음 방향", say::direction_of(&direction.action));
                }
            }
        }
        None => pair(out, "이전 시도", &came_from.to_string()),
    }
    pair(
        out,
        "되돌아간 지점",
        &format!(
            "{} ({})",
            graph::name_of(
                seen.current_cycle.facts.kind,
                &seen.current_cycle.facts.cycle_ref.to_string()
            ),
            seen.current_cycle.facts.cycle_ref
        ),
    );
    if let Some(define) = &seen.current_cycle.facts.experiment_definition {
        pair(out, "현재의 새 가설", &define.problem);
    }
    out.push_str("</dl>\n</section>\n");
}

/// **[지나온 기록]** — 나머지 전부. 기본으로 접혀 있다.
///
/// 줄이는 것은 기록의 양이 아니라 **첫 30초에 읽어야 하는 양**이다. 그래서 지우지 않고
/// 접는다. `<details>` 는 browser 가 이미 아는 것이라 JavaScript 를 더하지 않는다.
fn record(out: &mut String, seen: &MonitorSnapshot) {
    out.push_str("<details class=\"record\">\n<summary>지나온 기록</summary>\n");
    here(out, seen);
    active_path(out, seen);
    left_behind(out, seen);
    doing(out, seen);
    world(out, &seen.world);
    next(out, &seen.next_actions);
    out.push_str("</details>\n");
}

/// 화면 맨 위에 거는 **경고 한 장.**
///
/// stale 과 unavailable 이 Current 처럼 보이지 않게 하는 자리다. 색이 아니라 **제목과
/// 글**로 말한다 — 색을 못 보는 눈에도, 흑백 인쇄에도 같은 사실이 남아야 한다.
///
/// 오류 글은 사람이 쓴 것이 아니어도 **신뢰하지 않는 입력**으로 다룬다. 프로젝트의 경로나
/// Report 조각이 오류에 섞여 들어올 수 있고, 그것이 markup 이 되면 안 된다.
pub(super) fn banner(out: &mut String, title: &str, said: &str, rows: &[(&str, String)]) {
    out.push_str("<section class=\"warn\">\n");
    let _ = writeln!(out, "<h2>{}</h2>", text(title));
    let _ = writeln!(out, "<p class=\"note\">{}</p>", text(said));
    if !rows.is_empty() {
        out.push_str("<dl>\n");
        for (label, value) in rows {
            pair(out, label, value);
        }
        out.push_str("</dl>\n");
    }
    out.push_str("</section>\n");
}

// ── 안전한 글 ──────────────────────────────────────────────────────────────

/// 사용자 글을 **text node 로만** 만든다.
///
/// 다섯 글자를 모두 바꾼다. `"` 와 `'` 는 이 renderer 가 사용자 글을 attribute 에 넣지 않아
/// 당장은 필요 없지만, **그 규칙이 언젠가 깨질 때 이 함수가 마지막 방어선**이 된다.
///
/// `&` 를 **가장 먼저** 바꾼다. 나중에 바꾸면 방금 만든 `&lt;` 의 `&` 를 다시 바꿔
/// `&amp;lt;` 가 되고, 화면에는 `&lt;` 라는 글자가 나타난다.
fn text(raw: &str) -> String {
    let mut out = String::with_capacity(raw.len());
    for ch in raw.chars() {
        match ch {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&#39;"),
            _ => out.push(ch),
        }
    }
    out
}

/// 이름과 값 한 쌍. 값은 **언제나** [`text`] 를 지난다.
fn pair(out: &mut String, label: &str, value: &str) {
    let _ = writeln!(out, "<dt>{}</dt>", text(label));
    let _ = writeln!(out, "<dd>{}</dd>", text(value));
}

/// 이름과 **주소·명령** 한 쌍 — `<code>` 의 텍스트일 뿐 링크도 버튼도 아니다.
///
/// `href` 를 만들지 않는다. 만들면 `javascript:` 를 적어 넣을 자리가 생기고, 만들지 않으면
/// 그 자리 자체가 없다.
fn pair_code(out: &mut String, label: &str, value: &str) {
    let _ = writeln!(out, "<dt>{}</dt>", text(label));
    let _ = writeln!(out, "<dd><code>{}</code></dd>", text(value));
}

fn heading(out: &mut String, title: &str) {
    let _ = writeln!(out, "<h2>{}</h2>", text(title));
}

fn note(out: &mut String, said: &str) {
    let _ = writeln!(out, "<p class=\"note\">{}</p>", text(said));
}

// ── 지금 어디인가 ──────────────────────────────────────────────────────────

fn here(out: &mut String, seen: &MonitorSnapshot) {
    let cycle = &seen.current_cycle.facts;
    out.push_str("<section>\n");
    heading(out, say::here_title(cycle.kind));
    out.push_str("<dl>\n");

    pair_code(out, say::CYCLE, &cycle_line(cycle));
    match &seen.current_step {
        Some(step) => pair_code(out, say::STEP, &step_line(step)),
        None => pair(out, say::STEP, say::NO_STEP_YET),
    }

    // Define 이 없으면 빈 질문을 지어내지 않는다.
    if let Some(define) = &cycle.experiment_definition {
        pair(out, say::PROBLEM, &define.problem);
        pair(out, say::SUCCESS_CONDITION, &define.success_condition);
    }
    if let Some(pending) = &seen.pending_revisit {
        // **새 Cycle 이 아직 없다**는 사실을 여기서 말한다.
        pair(
            out,
            "되돌아왔다",
            &format!(
                "{} 에서 갈라져 {} 에 섰다 — 새 Cycle 은 아직 없다",
                pending.from_cycle_ref, pending.target_cycle_ref
            ),
        );
    }
    if let Some(report) = &cycle.report {
        report_pairs(out, report);
    }

    out.push_str("</dl>\n</section>\n");
}

/// Cycle 한 줄 — typed reference · 종류 · 열림/닫힘, 그리고 부모와 갈래 출처를 **가른다.**
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

/// 닫힌 Cycle 의 Report 투영 — **세 절이 이 한 자리를 쓴다.**
fn report_pairs(out: &mut String, report: &CycleReportFacts) {
    pair(out, say::VERDICT, &report.verdict);
    if let Some(lesson) = &report.outcome_lesson {
        pair(out, say::LESSON, lesson);
    }
    pair(out, say::HANDOFF, &report.handoff_summary);
    if let Some(direction) = &report.next_direction {
        let mut line = direction.action.clone();
        if let Some(target) = direction.target_cycle_ref {
            let _ = write!(line, " → {target}");
        }
        pair(out, say::NEXT_DIRECTION, &line);
        if let Some(reason) = &direction.reason {
            pair(out, say::WHY, reason);
        }
    }
}

// ── 걸어온 길 ──────────────────────────────────────────────────────────────

/// 뿌리부터 지금까지 — 깊이를 **중첩 목록**으로 그린다.
///
/// 들여쓰기가 장식이 아니라 구조다. 색을 못 봐도, CSS 가 없어도 목록의 중첩이 그대로
/// 남는다.
fn active_path(out: &mut String, seen: &MonitorSnapshot) {
    out.push_str("<section>\n");
    heading(out, say::ACTIVE_PATH);
    note(out, say::ACTIVE_PATH_IS);

    let last = seen.active_lineage.len().saturating_sub(1);
    for (depth, cycle) in seen.active_lineage.iter().enumerate() {
        out.push_str("<ol class=\"path\">\n<li>\n");
        let _ = writeln!(out, "<h3><code>{}</code></h3>", text(&cycle_line(cycle)));

        // 지금 자리의 질문과 성공 기준은 앞 절이 이미 말했다.
        if depth < last {
            out.push_str("<dl>\n");
            if let Some(define) = &cycle.experiment_definition {
                pair(out, say::PROBLEM, &define.problem);
                pair(out, say::SUCCESS_CONDITION, &define.success_condition);
            }
            if let Some(report) = &cycle.report {
                report_pairs(out, report);
            }
            out.push_str("</dl>\n");
        }
    }
    for _ in &seen.active_lineage {
        out.push_str("</li>\n</ol>\n");
    }
    out.push_str("</section>\n");
}

/// 계보 밖의 Cycle 들 — **하나도 없으면 절 자체가 없다.**
fn left_behind(out: &mut String, seen: &MonitorSnapshot) {
    if seen.inactive_cycles.is_empty() {
        return;
    }
    out.push_str("<section>\n");
    heading(out, say::LEFT_BEHIND);
    note(out, say::LEFT_BEHIND_IS);
    out.push_str("<ul>\n");
    for cycle in &seen.inactive_cycles {
        one_left_behind(out, cycle, &seen.current_cycle.facts);
    }
    out.push_str("</ul>\n</section>\n");
}

fn one_left_behind(out: &mut String, cycle: &InactiveCycle, here: &CycleFacts) {
    // 활성 경로와 **모양으로도** 갈린다 — 색 하나에 기대지 않는다.
    out.push_str("<li class=\"branch\">\n");
    let _ = writeln!(
        out,
        "<h3><code>{}</code></h3>",
        text(&format!(
            "{} · {} · {}",
            cycle.cycle_ref,
            cycle.kind,
            say::state_of(cycle.state)
        ))
    );
    out.push_str("<dl>\n");
    pair(out, say::RELATION, say::relation_of(cycle.relation_to_current));
    if let Some(parent) = cycle.parent_cycle_ref {
        let mut line = parent.to_string();
        // **형제는 부모가 같을 때만.**
        if here.parent_cycle_ref == Some(parent) {
            let _ = write!(line, " ({})", say::SAME_PARENT);
        }
        pair(out, say::PARENT, &line);
    }
    if let Some(from) = cycle.revisit_from_cycle_ref {
        pair(
            out,
            say::BRANCH_SOURCE,
            &format!("{from} ({})", say::NOT_A_LINEAGE_EDGE),
        );
    }
    // **실패는 Report 만 말한다.**
    if let Some(report) = &cycle.report {
        report_pairs(out, report);
    }
    out.push_str("</dl>\n</li>\n");
}

// ── 지금 하려는 것 ─────────────────────────────────────────────────────────

fn doing(out: &mut String, seen: &MonitorSnapshot) {
    let Some(will) = &seen.current_will else {
        return;
    };
    out.push_str("<section>\n");
    heading(out, say::DOING);
    one_will(out, will);
    out.push_str("</section>\n");
}

fn one_will(out: &mut String, will: &WillFacts) {
    out.push_str("<dl>\n");
    pair_code(
        out,
        "Will",
        &format!("{} · {} 에 걸려 있다", will.will_ref, will.target_step_ref),
    );
    pair(out, say::OBJECTIVE, &will.objective);
    pair(out, say::NEXT_ACTION, &will.next_action);
    pair(out, say::DONE_WHEN, &will.done_when);
    out.push_str("</dl>\n");
}

// ── 지금 세계 ──────────────────────────────────────────────────────────────

fn world(out: &mut String, world: &WorldFacts) {
    out.push_str("<section>\n");
    heading(out, say::WORLD);
    out.push_str("<dl>\n");
    pair_code(out, say::BASELINE, &world.baseline_snapshot_ref.to_string());
    pair(out, say::WORLD_STATE, say::world_of(world.state));
    if let Some(reason) = &world.reason {
        pair(out, say::WHY_UNKNOWN, reason);
    }
    out.push_str("</dl>\n");
    if world.verify_can_confirm {
        note(out, say::VERIFY_CAN_CONFIRM);
    }
    out.push_str("</section>\n");
}

// ── 다음 행동 ──────────────────────────────────────────────────────────────

/// **Snapshot 이 준 것만 적는다.** 그리고 명령은 **누를 수 없다** — `<code>` 의 글자다.
fn next(out: &mut String, actions: &[NextAction]) {
    out.push_str("<section>\n");
    heading(out, say::NEXT);
    if actions.is_empty() {
        note(out, say::NO_MOVE);
        out.push_str("</section>\n");
        return;
    }
    out.push_str("<ol>\n");
    for action in actions {
        out.push_str("<li>\n");
        let _ = writeln!(out, "<h3>{}</h3>", text(&say::what_it_does(action.kind)));
        out.push_str("<dl>\n");
        pair(out, say::REASON, &action.reason);
        // 명령이 없는 수는 실행할 글자를 지어내지 않는다.
        if let Some(command) = &action.command {
            pair_code(out, say::RUN, command);
        }
        if let Some(topic) = &action.help_ref {
            pair_code(out, say::HELP, &format!("gil help {}", topic.as_str()));
        }
        out.push_str("</dl>\n</li>\n");
    }
    out.push_str("</ol>\n</section>\n");
}
