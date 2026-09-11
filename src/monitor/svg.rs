//! **정해진 자리를 그린다** — 그리기만 한다.
//!
//! [`super::graph`] 가 무엇을 어디에 놓을지 이미 정했다. 이 파일은 그 좌표를 SVG 글자로
//! 옮길 뿐, 무엇이 활성인지도 무엇이 실패했는지도 다시 판정하지 않는다.
//!
//! # 이 그림의 문법
//!
//! ```text
//! 행    Step 하나. 위에서 아래로만 자란다
//! lane  고정된 세로줄. 갈래는 옆 lane 으로 나가고 거기서 끝난다
//! 그룹  Cycle 하나가 제 행들을 감싸는 점선 테두리와 왼쪽 rail
//! 선    언제나 아래로만 간다 — 되돌아감도 위로 그리지 않는다
//! ```
//!
//! 모든 선은 lane 위의 직선이거나 lane 과 lane 사이의 직각 두 도막이다. **node 를 피해
//! 도는 곡선 경로를 찾지 않는다** — 자리가 고정돼 있으므로 그럴 필요가 없다.
//!
//! # 그림에 들어가는 글
//!
//! Step 요약만이 사용자 글이고, 그것은 [`super::graph`] 가 **이미 한 줄로 줄여 둔 것**이다.
//! 원문은 read model 에 온전히 남아 상세 영역에서 읽힌다. 그림의 폭은 상수라 글이 길어도
//! 늘어나지 않는다. 들어오는 모든 글은 [`text`] 를 지난다.
//!
//! # 색은 거들 뿐이다
//!
//! 열림·닫힘은 **점의 모양**으로, 성공·실패는 **체크와 X**로, 지나온 갈래는 **점선**으로,
//! 지금 자리는 **두 겹 테두리와 「현재」**로 가른다. 넷 다 낱말이 함께 적힌다.

use std::fmt::Write as _;

use super::graph::{
    CONTENT_X0, Folded, Mark, PAD, ROW_H, Standing, VisualEdge, VisualGraph,
    VisualGroup, VisualLane, VisualRow, WIDTH,
};

/// 화면 reader 가 먼저 읽는 두 줄. **고정된 글이다.**
const TITLE: &str = "현재 GIL 여정";
const DESC: &str =
    "위에서 아래로 흐르는 Step 시간선이다. 왼쪽 세로줄이 지금까지 이어지는 경로이고, \
     옆줄에서 끝난 것은 두고 온 시도다.";
/// 이 문서 안에서만 쓰는 이름표 — renderer 가 소유한 상수다.
const TITLE_ID: &str = "gil-graph-title";
const DESC_ID: &str = "gil-graph-desc";

/// 행 위의 점 반지름.
const DOT: i32 = 6;

/// [`VisualGraph`] 하나를 inline SVG 로.
pub(crate) fn render_monitor_svg(plan: &VisualGraph) -> String {
    let mut out = String::new();
    // `viewBox` 하나로 작은 화면까지 따라온다 — 폭은 CSS 가 100% 로 잡고 높이는 비율이
    // 정한다. 그래서 가로 scroll 에 기대지 않는다.
    let _ = writeln!(
        out,
        "<svg class=\"graph\" viewBox=\"0 0 {} {}\" role=\"img\" \
         aria-labelledby=\"{TITLE_ID} {DESC_ID}\" preserveAspectRatio=\"xMinYMin meet\">",
        span(plan.width),
        span(plan.height)
    );
    let _ = writeln!(out, "<title id=\"{TITLE_ID}\">{}</title>", text(TITLE));
    let _ = writeln!(out, "<desc id=\"{DESC_ID}\">{}</desc>", text(DESC));

    // 그리는 차례가 곧 겹침의 차례다 — 그룹, 줄, 선, 그리고 마지막에 점과 글.
    for group in &plan.groups {
        group_band(&mut out, group, plan);
    }
    for lane in &plan.lanes {
        lane_line(&mut out, lane, plan);
    }
    for edge in &plan.edges {
        step_edge(&mut out, edge, plan);
    }
    if let Some(folded) = &plan.folded {
        folded_note(&mut out, folded);
    }
    for row in &plan.rows {
        step_row(&mut out, row);
    }
    out.push_str("</svg>\n");
    out
}

// ── Cycle 그룹 ─────────────────────────────────────────────────────────────

/// Cycle 하나 — **큰 node 가 아니라 제 Step 행들을 감싸는 띠와 rail.**
///
/// 띠는 **내용 층에서만** 산다([`CONTENT_X0`] 부터). lane 을 감싸지 않는다 — 감싸면
/// 지금까지 이어지는 lane 이 실패한 Cycle 안을 지나가는 것처럼 읽힌다.
///
/// 그룹은 행의 자리를 한 칸도 바꾸지 않는다. 시간축은 Step 이 정하고, 그룹은 그 위에
/// 얹힌다.
fn group_band(out: &mut String, group: &VisualGroup, plan: &VisualGraph) {
    let _ = writeln!(out, "<g class=\"{}\">", group_class(group));
    let right = WIDTH - PAD;
    let dashes = match group.standing {
        Standing::LeftBehind => " stroke-dasharray=\"4 4\"",
        _ => "",
    };
    let weight = match group.standing {
        Standing::LeftBehind => 1,
        _ => 2,
    };
    let _ = writeln!(
        out,
        "<rect x=\"{CONTENT_X0}\" y=\"{}\" width=\"{}\" height=\"{}\" rx=\"6\" fill=\"none\" \
         stroke=\"currentColor\" stroke-width=\"1\"{dashes}/>",
        span(group.y),
        span(right - CONTENT_X0),
        span(group.height)
    );
    // 내용 층 왼쪽 모서리의 rail — 이 Cycle 이 차지한 세로 범위를 굵기로 말한다.
    let _ = writeln!(
        out,
        "<path class=\"g-rail\" d=\"M {CONTENT_X0} {} L {CONTENT_X0} {}\" fill=\"none\" \
         stroke=\"currentColor\" stroke-width=\"{weight}\"/>",
        span(group.y),
        span(group.y + group.height)
    );
    // 이름표는 띠의 머리, **글이 사는 칸에** 둔다. 왼쪽 lane 다발 위에 적으면 세로줄이
    // 글자를 관통한다(실측으로 이어지는 lane 이 「실험 C2」를 가로질렀다).
    let _ = writeln!(
        out,
        "<text class=\"g-group\" x=\"{}\" y=\"{}\">{}</text>",
        span(CONTENT_X0 + 12),
        span(group.y + 16),
        text(&group.name)
    );
    let _ = writeln!(
        out,
        "<text class=\"g-group-mark\" x=\"{}\" y=\"{}\">{}</text>",
        span(CONTENT_X0 + 78),
        span(group.y + 16),
        text(group.mark.word())
    );
    if group.standing == Standing::Here {
        let _ = writeln!(
            out,
            "<text class=\"g-here\" x=\"{}\" y=\"{}\">현재 Cycle</text>",
            span(right - 12),
            span(group.y + 16)
        );
    }
    // **되돌아감은 여기서 글이 된다.** 위로 향하는 선을 그리는 대신, 이 lane 이 어디서
    // 비롯됐는지를 출발점에 적는다.
    if let Some(origin) = &group.came_from {
        let _ = writeln!(
            out,
            "<text class=\"g-origin\" x=\"{}\" y=\"{}\">↳ {}</text>",
            span(CONTENT_X0 + 124),
            span(group.y + 16),
            text(&origin.says())
        );
    }
    let _ = plan;
    out.push_str("</g>\n");
}

fn group_class(group: &VisualGroup) -> &'static str {
    match group.standing {
        Standing::Here => "g-cycle g-now",
        Standing::Active => "g-cycle g-on",
        Standing::LeftBehind => "g-cycle g-off",
    }
}

// ── lane ───────────────────────────────────────────────────────────────────

/// 한 시도 경로의 세로줄. **위에서 아래로.**
///
/// 두고 온 갈래는 점선이고, 마지막 행에서 **가로 막대로 닫힌다** — 이 lane 이 여기서
/// 끝났다는 뜻이다. 이어지는 lane 에는 그 막대가 없다.
fn lane_line(out: &mut String, lane: &VisualLane, plan: &VisualGraph) {
    let Some(from) = plan.rows.get(lane.from_row) else {
        return;
    };
    let Some(to) = plan.rows.get(lane.to_row) else {
        return;
    };
    let dashes = match lane.standing {
        Standing::LeftBehind => " stroke-dasharray=\"5 4\"",
        _ => "",
    };
    let weight = match lane.standing {
        Standing::LeftBehind => 2,
        _ => 4,
    };
    let _ = writeln!(
        out,
        "<path class=\"g-lane\" d=\"M {} {} L {} {}\" fill=\"none\" stroke=\"currentColor\" \
         stroke-width=\"{weight}\" stroke-linecap=\"round\"{dashes}/>",
        span(lane.x),
        span(from.y),
        span(lane.x),
        span(to.y)
    );
    if lane.standing == Standing::LeftBehind {
        // **여기서 끝난다.** 막다른 길임을 모양으로 말한다.
        let _ = writeln!(
            out,
            "<path class=\"g-stop\" d=\"M {} {} L {} {}\" fill=\"none\" stroke=\"currentColor\" \
             stroke-width=\"3\"/>",
            span(lane.x - 8),
            span(to.y + 13),
            span(lane.x + 8),
            span(to.y + 13)
        );
    }
}

// ── 선 ─────────────────────────────────────────────────────────────────────

/// 행과 행을 잇는다 — **언제나 아래로.**
///
/// 같은 lane 이면 lane 줄이 이미 잇고 있으므로 아무것도 더 그리지 않는다. lane 이 다르면
/// 직각 두 도막으로 내려가 옆으로 간다. 곡선도, 되돌아가는 도막도 없다.
fn step_edge(out: &mut String, edge: &VisualEdge, plan: &VisualGraph) {
    let (Some(from), Some(to)) = (plan.rows.get(edge.from), plan.rows.get(edge.to)) else {
        return;
    };
    if from.lane == to.lane {
        // **같은 lane 이면 곧게 잇는다.** Cycle 이 바뀌며 lane 줄이 끊긴 자리를 여기서
        // 메운다 — 그래야 지금까지 이어지는 길이 하나의 끊기지 않는 세로줄로 읽힌다.
        let _ = writeln!(
            out,
            "<path class=\"g-lane\" d=\"M {} {} L {} {}\" fill=\"none\" stroke=\"currentColor\" \
             stroke-width=\"4\" stroke-linecap=\"round\"/>",
            span(from.x),
            span(from.y),
            span(to.x),
            span(to.y)
        );
        return;
    }
    if !edge.turn {
        return;
    }
    // 아래로 반 칸 내려가, 옆으로, 다시 아래로.
    let mid = from.y + ROW_H / 2;
    let _ = writeln!(
        out,
        "<path class=\"g-turn\" d=\"M {} {} L {} {} L {} {} L {} {}\" fill=\"none\" \
         stroke=\"currentColor\" stroke-width=\"2\"/>",
        span(from.x),
        span(from.y),
        span(from.x),
        span(mid),
        span(to.x),
        span(mid),
        span(to.x),
        span(to.y - DOT)
    );
    // 아래를 가리키는 화살촉 — `marker` 도 `url(#…)` 도 쓰지 않는다.
    let _ = writeln!(
        out,
        "<path class=\"g-head\" d=\"M {} {} l -4 -7 l 8 0 z\" fill=\"currentColor\"/>",
        span(to.x),
        span(to.y - DOT)
    );
}

// ── 행 ─────────────────────────────────────────────────────────────────────

/// Step 하나 — **점 하나, 이음선, kind, 짧은 요약, 그리고 작은 주소.**
///
/// 점은 lane 층에, 글은 내용 층에 있다. 그 둘을 잇는 것이 **가로 이음선 하나**다 — 이
/// 행이 어느 길 위에 있는지를 말하는 유일한 연결이고, 세로 lane 을 가로지르되 점은
/// 지나지 않는다(한 y 에는 점이 하나뿐이므로).
fn step_row(out: &mut String, row: &VisualRow) {
    let _ = writeln!(out, "<g class=\"{}\">", row_class(row));
    let _ = writeln!(
        out,
        "<path class=\"g-link\" d=\"M {} {} L {} {}\" fill=\"none\" stroke=\"currentColor\" \
         stroke-width=\"1\" stroke-dasharray=\"2 3\"/>",
        span(row.x + 8),
        span(row.y),
        span(CONTENT_X0),
        span(row.y)
    );
    // 열린 Step 은 빈 점, 닫힌 Step 은 찬 점.
    match row.mark {
        Mark::Open => {
            let _ = writeln!(
                out,
                "<circle class=\"g-dot\" cx=\"{}\" cy=\"{}\" r=\"{DOT}\" fill=\"none\" \
                 stroke=\"currentColor\" stroke-width=\"3\"/>",
                span(row.x),
                span(row.y)
            );
        }
        _ => {
            let _ = writeln!(
                out,
                "<circle class=\"g-dot\" cx=\"{}\" cy=\"{}\" r=\"{DOT}\" fill=\"currentColor\"/>",
                span(row.x),
                span(row.y)
            );
        }
    }
    // 지금 서 있는 자리만 **테두리가 하나 더** 있다. 색을 지워도 남는 표시다.
    if row.standing == Standing::Here {
        let _ = writeln!(
            out,
            "<circle class=\"g-ring\" cx=\"{}\" cy=\"{}\" r=\"{}\" fill=\"none\" \
             stroke=\"currentColor\" stroke-width=\"2\"/>",
            span(row.x),
            span(row.y),
            DOT + 5
        );
    }
    // 판정은 점 옆의 모양과 낱말이 함께 진다.
    match row.mark {
        Mark::Succeeded => {
            let _ = writeln!(
                out,
                "<path class=\"g-sign\" d=\"M {} {} l 3 4 l 6 -8\" fill=\"none\" \
                 stroke=\"currentColor\" stroke-width=\"2\"/>",
                span(row.x + 12),
                span(row.y - 1)
            );
        }
        Mark::Failed => {
            let _ = writeln!(
                out,
                "<path class=\"g-sign\" d=\"M {} {} l 8 8 M {} {} l -8 8\" fill=\"none\" \
                 stroke=\"currentColor\" stroke-width=\"2\"/>",
                span(row.x + 12),
                span(row.y - 5),
                span(row.x + 20),
                span(row.y - 5)
            );
        }
        _ => {}
    }

    let mut at = CONTENT_X0 + 12;
    let _ = writeln!(
        out,
        "<text class=\"g-kind\" x=\"{}\" y=\"{}\">{}</text>",
        span(at),
        span(row.y + 5),
        text(row.kind)
    );
    at += 46;
    if row.standing == Standing::Here {
        let _ = writeln!(
            out,
            "<text class=\"g-here\" x=\"{}\" y=\"{}\">현재</text>",
            span(at),
            span(row.y + 5)
        );
        at += 36;
    }
    if matches!(row.mark, Mark::Succeeded | Mark::Failed) {
        let _ = writeln!(
            out,
            "<text class=\"g-mark\" x=\"{}\" y=\"{}\">{}</text>",
            span(at),
            span(row.y + 5),
            text(row.mark.word())
        );
        at += 40;
    }
    if let Some(said) = &row.summary {
        let _ = writeln!(
            out,
            "<text class=\"g-said\" x=\"{}\" y=\"{}\">{}</text>",
            span(at),
            span(row.y + 5),
            text(said)
        );
    }
    // typed reference — **가장 작은 글씨로, 오른쪽 끝에.**
    let _ = writeln!(
        out,
        "<text class=\"g-ref\" x=\"{}\" y=\"{}\">{}</text>",
        span(WIDTH - PAD - 10),
        span(row.y + 5),
        text(&row.address)
    );
    out.push_str("</g>\n");
}

fn row_class(row: &VisualRow) -> &'static str {
    match row.standing {
        Standing::Here => "g-step g-now",
        Standing::Active => "g-step g-on",
        Standing::LeftBehind => "g-step g-off",
    }
}

fn folded_note(out: &mut String, folded: &Folded) {
    let _ = writeln!(
        out,
        "<text class=\"g-folded\" x=\"{}\" y=\"18\">{}</text>",
        span(CONTENT_X0 + 12),
        text(&folded.says())
    );
}

// ── 안전한 수와 글 ─────────────────────────────────────────────────────────

/// 좌표 하나를 글자로 — **유한하고 제정신인 수만 나간다.**
///
/// 여기 오는 값은 전부 renderer 가 정한 상수의 정수 연산이라 `NaN` 도 무한도 될 수 없다.
/// 그래도 문을 하나 두는 까닭은, layout 이 바뀌는 날 음수 좌표가 조용히 새어 나가지 않게
/// 하기 위해서다. 정수라 소수점도 지수 표기도 나타나지 않는다.
fn span(value: i32) -> i32 {
    value.clamp(0, 100_000)
}

/// SVG text node 안으로 들어가는 글.
///
/// HTML 과 같은 다섯 글자를 바꾼다. `&` 를 **가장 먼저** 바꾼다 — 나중에 바꾸면 방금 만든
/// `&lt;` 의 `&` 를 다시 바꿔 화면에 `&lt;` 라는 글자가 나타난다.
fn text(raw: &str) -> String {
    let mut out = String::with_capacity(raw.len());
    for glyph in raw.chars() {
        match glyph {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&#39;"),
            other => out.push(other),
        }
    }
    out
}


#[cfg(test)]
mod tests {
    use super::super::graph::{CONTENT_X0, render_monitor_graph, tests::reading_one};
    use super::*;

    fn drawn() -> String {
        render_monitor_svg(&render_monitor_graph(&reading_one()))
    }

    /// 이 그림이 실제로 쓰는 태그 안의 속성들.
    fn attributes(svg: &str, tag_class: &str) -> Vec<String> {
        svg.lines()
            .filter(|line| line.contains(tag_class))
            .map(str::to_string)
            .collect()
    }

    /// `d="…"` 안의 좌표를 (x, y) 쌍으로 — 절대 이동만 본다.
    fn absolute_points(path: &str) -> Vec<(i64, i64)> {
        let mut points = Vec::new();
        let mut words = path.split_whitespace().peekable();
        while let Some(word) = words.next() {
            if word != "M" && word != "L" {
                continue;
            }
            let (Some(x), Some(y)) = (words.next(), words.next()) else {
                break;
            };
            if let (Ok(x), Ok(y)) = (x.parse(), y.parse()) {
                points.push((x, y));
            }
        }
        points
    }

    #[test]
    fn the_picture_names_itself_for_a_reader_that_cannot_see_it() {
        let svg = drawn();
        assert!(svg.contains("role=\"img\""), "{svg}");
        assert!(
            svg.contains(&format!("aria-labelledby=\"{TITLE_ID} {DESC_ID}\"")),
            "이름표가 이어져 있지 않다"
        );
        assert!(svg.contains(&format!("<title id=\"{TITLE_ID}\">{TITLE}</title>")), "{svg}");
        assert!(svg.contains(&format!("id=\"{DESC_ID}\"")), "{svg}");
        // 설명이 이 그림의 문법을 말한다 — 위에서 아래로, 옆줄은 두고 온 것.
        assert!(svg.contains("위에서 아래로"), "{svg}");
    }

    #[test]
    fn no_connecting_line_ever_goes_upward() {
        // **이 그림에서 위로 가는 선은 없다.** 되돌아감조차도.
        let svg = drawn();
        for line in svg.lines() {
            if !line.contains("class=\"g-lane\"") && !line.contains("class=\"g-turn\"") {
                continue;
            }
            let path = line
                .split(" d=\"")
                .nth(1)
                .and_then(|rest| rest.split('"').next())
                .expect("경로");
            let points = absolute_points(path);
            for pair in points.windows(2) {
                assert!(
                    pair[1].1 >= pair[0].1,
                    "선이 위로 간다: {:?} → {:?} in {path}",
                    pair[0],
                    pair[1]
                );
            }
        }
        // 화살촉도 아래를 가리킨다 — 위를 가리키는 것은 하나도 없다.
        assert!(svg.contains("class=\"g-head\""), "화살촉이 없다");
        for line in attributes(&svg, "class=\"g-head\"") {
            assert!(line.contains("l -4 -7 l 8 0 z"), "아래를 가리키는 모양이 아니다: {line}");
        }
    }

    #[test]
    fn the_picture_carries_no_way_out_of_itself() {
        let svg = drawn();
        for forbidden in [
            "<script", "foreignObject", "<image", "<use", "<a ", "xlink", "href", "src=",
            "onload", "onclick", "onerror", "javascript:", "url(", "<style", "style=", "@import",
        ] {
            assert!(!svg.contains(forbidden), "{forbidden:?} 가 그림에 있다");
        }
        for tag in svg.split('<').skip(1) {
            let inside = tag.split('>').next().unwrap_or("");
            for word in inside.split_whitespace().skip(1) {
                let name = word.split('=').next().unwrap_or("");
                assert!(!name.starts_with("on"), "사건 처리기 {name:?} 가 생겼다");
            }
        }
    }

    #[test]
    fn every_number_in_the_picture_is_finite_and_sane() {
        let svg = drawn();
        assert!(!svg.contains("NaN") && !svg.contains("Infinity"), "{svg}");
        for name in ["x", "y", "width", "height", "cx", "cy", "r", "rx"] {
            for chunk in svg.split(&format!(" {name}=\"")).skip(1) {
                let value = chunk.split('"').next().expect("닫는 따옴표");
                let number: i64 = value
                    .parse()
                    .unwrap_or_else(|_| panic!("{name}={value:?} 가 정수가 아니다"));
                assert!(number >= 0, "{name}={number} 이 음수다");
                assert!(number < 100_000, "{name}={number} 이 상한을 넘었다");
            }
        }
        for chunk in svg.split(" d=\"").skip(1) {
            let path = chunk.split('"').next().expect("닫는 따옴표");
            for word in path.split_whitespace() {
                if word.chars().all(|ch| ch.is_ascii_alphabetic()) {
                    continue;
                }
                let number: i64 = word
                    .parse()
                    .unwrap_or_else(|_| panic!("경로에 정수가 아닌 {word:?} 가 있다"));
                assert!(number.abs() < 100_000, "경로의 수가 상한을 넘었다: {number}");
            }
        }
    }

    #[test]
    fn a_nasty_summary_becomes_letters_and_never_widens_the_picture() {
        let mut seen = reading_one();
        let nasty = format!(
            "</text><script>alert(1)</script>\n둘 & \"셋\" 'x' {}",
            "가".repeat(3000)
        );
        for entry in &mut seen.timeline {
            for step in &mut entry.steps {
                step.summary = Some(nasty.clone());
            }
        }
        let plan = render_monitor_graph(&seen);
        let svg = render_monitor_svg(&plan);

        assert!(!svg.contains("<script"), "글이 태그가 됐다");
        assert!(svg.contains("&lt;/text&gt;&lt;script&gt;"), "탈출되지 않았다");
        assert!(!svg.contains("&amp;lt;"), "탈출을 두 번 했다");
        assert!(!svg.contains(&"가".repeat(60)), "긴 글이 통째로 들어갔다");
        // 폭은 상수다 — 글이 아무리 길어도.
        assert!(svg.contains(&format!("viewBox=\"0 0 {WIDTH} ")), "폭이 글을 따라 바뀌었다");
    }

    #[test]
    fn the_renderer_no_longer_joins_the_cycle_lists() {
        // 예전에는 `active_lineage` 와 `inactive_cycles` 를 주소로 다시 이어 붙여 Cycle 의
        // 종류·판정·활성 여부를 알아냈다. 이제 시간선 항목이 그것을 지니고 온다.
        //
        // **두 목록을 통째로 비워도 같은 그림이 나오면** 그 조립이 사라진 것이다.
        let seen = reading_one();
        let mut alone = seen.clone();
        alone.active_lineage.clear();
        alone.inactive_cycles.clear();

        assert_eq!(
            render_monitor_svg(&render_monitor_graph(&seen)),
            render_monitor_svg(&render_monitor_graph(&alone)),
            "renderer 가 아직 두 목록을 읽고 있다"
        );
        // 그리고 그 그림이 빈 그림이 아니다 — 시험이 아무것도 재지 않는 일이 없게.
        let drawn = render_monitor_svg(&render_monitor_graph(&alone));
        assert!(drawn.contains("실험 C2") && drawn.contains("실패"), "{drawn}");
        assert!(drawn.contains("다시 시도"), "되돌아감의 유래가 사라졌다");
    }

    #[test]
    fn the_same_plan_draws_byte_identical_svg() {
        let seen = reading_one();
        assert_eq!(
            render_monitor_svg(&render_monitor_graph(&seen)),
            render_monitor_svg(&render_monitor_graph(&seen))
        );
        // 그리고 두 목록의 수집 순서가 달라도 같은 그림이다.
        let mut shuffled = seen.clone();
        shuffled.active_lineage.reverse();
        shuffled.inactive_cycles.reverse();
        assert_eq!(
            render_monitor_svg(&render_monitor_graph(&seen)),
            render_monitor_svg(&render_monitor_graph(&shuffled)),
            "수집 순서가 그림을 바꿨다"
        );
    }

    #[test]
    fn the_picture_scales_instead_of_fixing_its_size() {
        let svg = drawn();
        let open = svg.lines().next().expect("여는 태그");
        assert!(open.contains("viewBox=\"0 0 "), "viewBox 가 없다: {open}");
        assert!(open.contains("preserveAspectRatio="), "비율 규칙이 없다: {open}");
        assert!(!open.contains(" width=\""), "그림이 제 폭을 고정했다: {open}");
        assert!(!open.contains(" height=\""), "그림이 제 높이를 고정했다: {open}");
    }

    #[test]
    fn a_placeholder_never_reaches_the_picture() {
        let mut seen = reading_one();
        for entry in &mut seen.timeline {
            for step in &mut entry.steps {
                step.summary = Some("<question>".to_string());
            }
        }
        let svg = render_monitor_svg(&render_monitor_graph(&seen));
        assert!(!svg.contains("question"), "자리표시가 그림에 실렸다");
        assert!(!svg.contains("&lt;"), "꺾쇠가 그림에 실렸다");
        // 그래도 Step 은 전부 있다 — 종류와 주소로.
        assert!(svg.contains(">질문<") && svg.contains(">step:C1/S1<"), "Step 이 사라졌다");
    }

    #[test]
    fn state_and_relation_survive_without_any_colour() {
        let svg = drawn();
        for word in ["현재", "성공", "실패", "열림", "다시 시도"] {
            assert!(svg.contains(word), "{word:?} 가 글로 없다");
        }
        // 지금 서 있는 자리만 테두리가 하나 더 있다.
        assert_eq!(svg.matches("class=\"g-ring\"").count(), 1, "지금 표식이 하나가 아니다");
        // 두고 온 갈래의 lane 은 점선이고, 끝을 막는 막대가 있다.
        let dead = svg
            .lines()
            .find(|line| line.contains("g-lane") && line.contains("stroke-dasharray"))
            .expect("두고 온 lane");
        assert!(dead.contains("stroke-width=\"2\""), "{dead}");
        assert!(svg.contains("class=\"g-stop\""), "끝난 lane 을 막지 않았다");
        // 이어지는 lane 은 실선이고 굵다.
        let alive = svg
            .lines()
            .find(|line| line.contains("g-lane") && !line.contains("stroke-dasharray"))
            .expect("이어지는 lane");
        assert!(alive.contains("stroke-width=\"4\""), "{alive}");
        // 색은 renderer 가 직접 정하지 않는다.
        for chunk in svg.split("stroke=\"").skip(1) {
            let value = chunk.split('"').next().expect("닫는 따옴표");
            assert_eq!(value, "currentColor", "그림이 색을 직접 정했다: {value}");
        }
    }

    #[test]
    fn every_cycle_band_starts_where_the_lane_layer_ends() {
        let svg = drawn();
        // 그룹의 띠와 rail 은 **내용 층에서만** 산다.
        let bands: Vec<&str> = svg
            .lines()
            .filter(|line| line.starts_with("<rect x="))
            .collect();
        assert_eq!(bands.len(), 3, "띠가 Cycle 수와 다르다");
        for band in bands {
            assert!(
                band.starts_with(&format!("<rect x=\"{CONTENT_X0}\"")),
                "띠가 lane 층까지 넘어왔다: {band}"
            );
        }
        for rail in svg.lines().filter(|line| line.contains("class=\"g-rail\"")) {
            assert!(rail.contains(&format!("M {CONTENT_X0} ")), "rail 이 lane 층에 있다: {rail}");
        }
        // 그리고 lane 은 전부 그 왼쪽에 있다.
        for lane in svg.lines().filter(|line| line.contains("class=\"g-lane\"")) {
            let path = lane
                .split(" d=\"")
                .nth(1)
                .and_then(|rest| rest.split('"').next())
                .expect("경로");
            for (x, _) in absolute_points(path) {
                assert!(x < CONTENT_X0 as i64, "lane 이 내용 층으로 넘어왔다: x={x}");
            }
        }
    }

    #[test]
    fn each_step_row_is_joined_to_its_own_lane_by_one_short_line() {
        let plan = render_monitor_graph(&reading_one());
        let svg = render_monitor_svg(&plan);
        let links: Vec<&str> = svg
            .lines()
            .filter(|line| line.contains("class=\"g-link\""))
            .collect();
        assert_eq!(links.len(), plan.rows.len(), "이음선 수가 Step 수와 다르다");

        for (link, row) in links.iter().zip(&plan.rows) {
            let path = link
                .split(" d=\"")
                .nth(1)
                .and_then(|rest| rest.split('"').next())
                .expect("경로");
            let points = absolute_points(path);
            assert_eq!(points.len(), 2, "이음선이 곧지 않다: {path}");
            // **제 lane 에서 출발해** 내용 층에서 끝난다. 그리고 수평이다.
            assert_eq!(points[0].1, row.y as i64, "{} 의 이음선이 제 행에 없다", row.address);
            assert_eq!(points[1].1, row.y as i64, "이음선이 기울었다");
            assert_eq!(points[0].0, (row.x + 8) as i64, "{} 의 이음선이 남의 lane 에서 온다", row.address);
            assert_eq!(points[1].0, CONTENT_X0 as i64, "이음선이 내용 층에 닿지 않는다");
        }
    }

    #[test]
    fn a_cycle_is_a_band_and_a_rail_never_a_node_of_its_own() {
        let svg = drawn();
        // 그룹마다 띠 하나와 rail 하나.
        assert_eq!(svg.matches("class=\"g-rail\"").count(), 3, "rail 수가 Cycle 수와 다르다");
        assert_eq!(svg.matches("class=\"g-cycle").count(), 3, "그룹 수가 다르다");
        // 그러나 Cycle 이름이 점(node)으로 그려지지는 않는다 — 점은 Step 의 것뿐이다.
        let plan = render_monitor_graph(&reading_one());
        assert_eq!(
            svg.matches("class=\"g-dot\"").count(),
            plan.rows.len(),
            "점의 수가 Step 수와 다르다"
        );
    }
}
