//! **정해진 자리를 그린다** — 그리기만 한다.
//!
//! [`super::graph`] 가 무엇을 어디에 놓을지 이미 정했다. 이 파일은 그 좌표를 SVG 글자로
//! 옮길 뿐, 무엇이 활성인지도 무엇이 실패했는지도 다시 판정하지 않는다.
//!
//! # 이 그림에 들어가는 글
//!
//! **사용자가 쓴 문장은 한 조각도 들어가지 않는다.** 들어가는 것은 renderer 가 소유한
//! 낱말(`실험`·`성공`·`현재`)과 typed reference(`cycle:C3`) 뿐이다. 그래서
//!
//! - 긴 문장이 그림의 폭을 늘릴 수 없고,
//! - 신뢰하지 않는 글이 markup 이 될 통로가 아예 없다.
//!
//! 그래도 [`text`] 로 모두 escape 한다. 저 규칙이 언젠가 느슨해지는 날 이 함수가 마지막
//! 방어선이 된다.
//!
//! # 색은 거들 뿐이다
//!
//! 열림·닫힘은 **모서리의 둥글기**로, 지나온 갈래는 **점선과 가는 선**으로, 지금 자리는
//! **이중 테두리**로 가른다. 그리고 셋 다 **낱말이 함께 적힌다.** 흑백으로 인쇄해도, 색을
//! 못 보는 눈으로도 같은 사실이 남는다.

use std::fmt::Write as _;

use super::graph::{Folded, Mark, Standing, Tie, VisualCycle, VisualGraph, VisualStep};

/// 화면 reader 가 먼저 읽는 두 줄. **고정된 글이다.**
const TITLE: &str = "현재 GIL 여정";
const DESC: &str = "현재 위치, 활성 경로, 실패한 갈래와 되돌아간 관계를 보여 준다.";
/// 이 문서 안에서만 쓰는 이름표 — renderer 가 소유한 상수다.
const TITLE_ID: &str = "gil-graph-title";
const DESC_ID: &str = "gil-graph-desc";

const NODE_W: i32 = 208;
const NODE_H: i32 = 66;
const STEP_W: i32 = 84;
const STEP_H: i32 = 34;
/// 되돌아감의 점선이 지나가는 세로 길.
const LANE_X: i32 = 26;

/// [`VisualGraph`] 하나를 inline SVG 로.
pub(crate) fn render_monitor_svg(plan: &VisualGraph) -> String {
    let mut out = String::new();
    // `viewBox` 하나로 작은 화면까지 따라온다 — 폭은 CSS 가 100% 로 잡고 높이는 비율이
    // 정한다. 그래서 가로 scroll 에 기대지 않는다.
    let _ = writeln!(
        out,
        "<svg class=\"graph\" viewBox=\"0 0 {} {}\" role=\"img\" \
         aria-labelledby=\"{TITLE_ID} {DESC_ID}\" preserveAspectRatio=\"xMidYMin meet\">",
        span(plan.width),
        span(plan.height)
    );
    let _ = writeln!(out, "<title id=\"{TITLE_ID}\">{}</title>", text(TITLE));
    let _ = writeln!(out, "<desc id=\"{DESC_ID}\">{}</desc>", text(DESC));

    // 줄을 먼저 긋는다 — node 가 그 위를 덮어 끝이 깔끔해진다.
    for edge in &plan.edges {
        let (from, to) = (&plan.cycles[edge.from], &plan.cycles[edge.to]);
        match edge.tie {
            Tie::Parent => parent_line(&mut out, from, to),
            Tie::Revisit => revisit_line(&mut out, from, to),
        }
    }
    if let Some(folded) = &plan.folded {
        folded_node(&mut out, folded);
    }
    for cycle in &plan.cycles {
        cycle_node(&mut out, cycle);
        for step in &cycle.steps {
            step_node(&mut out, step);
        }
    }
    out.push_str("</svg>\n");
    out
}

// ── node ───────────────────────────────────────────────────────────────────

fn cycle_node(out: &mut String, cycle: &VisualCycle) {
    let (x, y) = (span(cycle.x), span(cycle.y));
    let _ = writeln!(out, "<g class=\"{}\">", class_of(cycle));
    // **모서리가 열림과 닫힘을 가른다** — 둥글면 아직 열려 있고, 각지면 닫혔다.
    let round = match cycle.mark {
        Mark::Open => 18,
        _ => 3,
    };
    let stroke = match cycle.standing {
        Standing::Here => 4,
        Standing::Active => 3,
        Standing::LeftBehind => 2,
    };
    let dashes = match cycle.standing {
        // 두고 온 갈래는 **점선 테두리**로 뒤로 물러난다.
        Standing::LeftBehind => " stroke-dasharray=\"5 4\"",
        _ => "",
    };
    let _ = writeln!(
        out,
        "<rect x=\"{x}\" y=\"{y}\" width=\"{NODE_W}\" height=\"{NODE_H}\" rx=\"{round}\" \
         fill=\"none\" stroke=\"currentColor\" stroke-width=\"{stroke}\"{dashes}/>"
    );
    // 지금 자리만 **테두리가 둘**이다. 색을 지워도 남는 표시다.
    if cycle.standing == Standing::Here {
        let _ = writeln!(
            out,
            "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" rx=\"{}\" fill=\"none\" \
             stroke=\"currentColor\" stroke-width=\"1\"/>",
            span(cycle.x + 6),
            span(cycle.y + 6),
            NODE_W - 12,
            NODE_H - 12,
            (round - 3).max(1)
        );
    }
    let _ = writeln!(
        out,
        "<text class=\"g-name\" x=\"{}\" y=\"{}\">{}</text>",
        span(cycle.x + 16),
        span(cycle.y + 25),
        text(&cycle.name)
    );
    // 판정은 **모양과 낱말이 함께** 간다.
    verdict_shape(out, cycle.x + 18, cycle.y + 40, cycle.mark);
    let _ = writeln!(
        out,
        "<text class=\"g-mark\" x=\"{}\" y=\"{}\">{}</text>",
        span(cycle.x + 34),
        span(cycle.y + 44),
        text(cycle.mark.word())
    );
    if cycle.standing == Standing::Here {
        let _ = writeln!(
            out,
            "<text class=\"g-here\" x=\"{}\" y=\"{}\">현재</text>",
            span(cycle.x + NODE_W - 16),
            span(cycle.y + 25)
        );
    }
    if cycle.standing == Standing::LeftBehind {
        let _ = writeln!(
            out,
            "<text class=\"g-aside\" x=\"{}\" y=\"{}\">지나온 갈래</text>",
            span(cycle.x + NODE_W - 16),
            span(cycle.y + 25)
        );
    }
    // typed reference — **가장 작은 글씨로.** 보존하되 초보자의 첫 읽기를 가로막지 않는다.
    let _ = writeln!(
        out,
        "<text class=\"g-ref\" x=\"{}\" y=\"{}\">{}</text>",
        span(cycle.x + 16),
        span(cycle.y + 58),
        text(&cycle.address)
    );
    out.push_str("</g>\n");
}

/// 성공은 체크, 실패는 X, 열림은 빈 동그라미, 닫힘은 찬 동그라미.
fn verdict_shape(out: &mut String, x: i32, y: i32, mark: Mark) {
    let (x, y) = (span(x), span(y));
    match mark {
        Mark::Succeeded => {
            let _ = writeln!(
                out,
                "<path class=\"g-sign\" d=\"M {} {} l 3 4 l 6 -8\" fill=\"none\" \
                 stroke=\"currentColor\" stroke-width=\"2\"/>",
                x - 4,
                y - 1
            );
        }
        Mark::Failed => {
            let _ = writeln!(
                out,
                "<path class=\"g-sign\" d=\"M {} {} l 8 8 M {} {} l -8 8\" fill=\"none\" \
                 stroke=\"currentColor\" stroke-width=\"2\"/>",
                x - 4,
                y - 5,
                x + 4,
                y - 5
            );
        }
        Mark::Open => {
            let _ = writeln!(
                out,
                "<circle class=\"g-sign\" cx=\"{x}\" cy=\"{}\" r=\"4\" fill=\"none\" \
                 stroke=\"currentColor\" stroke-width=\"2\"/>",
                y - 1
            );
        }
        Mark::Closed => {
            let _ = writeln!(
                out,
                "<circle class=\"g-sign\" cx=\"{x}\" cy=\"{}\" r=\"4\" fill=\"currentColor\"/>",
                y - 1
            );
        }
    }
}

fn step_node(out: &mut String, step: &VisualStep) {
    let (x, y) = (span(step.x), span(step.y));
    let round = match step.open {
        true => 14,
        false => 3,
    };
    let stroke = match step.here {
        true => 3,
        false => 1,
    };
    let _ = writeln!(out, "<g class=\"g-step\">");
    let _ = writeln!(
        out,
        "<rect x=\"{x}\" y=\"{y}\" width=\"{STEP_W}\" height=\"{STEP_H}\" rx=\"{round}\" \
         fill=\"none\" stroke=\"currentColor\" stroke-width=\"{stroke}\"/>"
    );
    let _ = writeln!(
        out,
        "<text class=\"g-step-name\" x=\"{}\" y=\"{}\">{}</text>",
        span(step.x + STEP_W / 2),
        span(step.y + 22),
        text(step.name)
    );
    if step.here {
        // 위를 가리키는 작은 표식과 낱말이 함께 간다.
        let _ = writeln!(
            out,
            "<path class=\"g-sign\" d=\"M {} {} l 6 -8 l 6 8 z\" fill=\"currentColor\"/>",
            span(step.x + STEP_W / 2 - 6),
            span(step.y - 4)
        );
        let _ = writeln!(
            out,
            "<text class=\"g-here\" x=\"{}\" y=\"{}\">현재</text>",
            span(step.x + STEP_W / 2),
            span(step.y - 14)
        );
    }
    out.push_str("</g>\n");
}

fn folded_node(out: &mut String, folded: &Folded) {
    let _ = writeln!(out, "<g class=\"g-folded\">");
    let _ = writeln!(
        out,
        "<rect x=\"{}\" y=\"{}\" width=\"{NODE_W}\" height=\"34\" rx=\"3\" fill=\"none\" \
         stroke=\"currentColor\" stroke-width=\"1\" stroke-dasharray=\"3 3\"/>",
        span(folded.x),
        span(folded.y)
    );
    let _ = writeln!(
        out,
        "<text class=\"g-ref\" x=\"{}\" y=\"{}\">{}</text>",
        span(folded.x + 16),
        span(folded.y + 22),
        text(&folded.says())
    );
    out.push_str("</g>\n");
}

// ── 줄 ─────────────────────────────────────────────────────────────────────

/// 부모 → 자식. **실선.**
///
/// 같은 칸이면 곧게 내려가고, 칸이 다르면 팔꿈치로 꺾는다. 두 경우 모두 칸과 칸 사이의
/// 빈 띠만 지나므로 **다른 node 를 뚫지 않는다.**
fn parent_line(out: &mut String, from: &VisualCycle, to: &VisualCycle) {
    let (x1, y1) = (from.x + NODE_W / 2, from.y + NODE_H);
    let (x2, y2) = (to.x + NODE_W / 2, to.y);
    let mid = (y1 + y2) / 2;
    let d = match x1 == x2 {
        true => format!("M {} {} L {} {}", span(x1), span(y1), span(x2), span(y2 - 8)),
        false => format!(
            "M {} {} L {} {} L {} {} L {} {}",
            span(x1),
            span(y1),
            span(x1),
            span(mid),
            span(x2),
            span(mid),
            span(x2),
            span(y2 - 8)
        ),
    };
    let _ = writeln!(
        out,
        "<path class=\"g-parent\" d=\"{d}\" fill=\"none\" stroke=\"currentColor\" \
         stroke-width=\"2\"/>"
    );
    arrow_down(out, x2, y2);
}

/// 되돌아감. **점선이고, 왼쪽 길로 돌아간다.**
///
/// 계보의 변이 아니므로 실선과 섞이면 안 된다. 게다가 줄기를 가로질러야 하므로, node 를
/// 뚫지 않도록 왼쪽 여백의 세로 길로 나간다.
///
/// # 같은 줄에서 왼쪽으로 갈 때
///
/// 출처가 줄기 오른쪽에 있으면 **곧장 왼쪽으로 나갈 수 없다** — 같은 줄에 선 node 를
/// 관통한다(실측으로 되돌아감의 점선이 현재 Cycle 을 가로질렀다). 그럴 때는 아래 띠로
/// 한 칸 내려가 그 밑을 지나간다. 줄과 줄 사이는 비어 있는 자리다.
fn revisit_line(out: &mut String, from: &VisualCycle, to: &VisualCycle) {
    let (x2, y2) = (to.x, to.y + NODE_H / 2);
    let d = match from.x > to.x {
        // 아래로 내려가 그 밑을 지난다.
        true => {
            // 출처의 바로 아래 — 아래 줄이나 Step 띠의 이름표와 겹치지 않게 가깝게
            // 붙인다(실측으로 30 은 「현재」 표식 위를 지나갔다).
            let below = from.y + NODE_H + 14;
            format!(
                "M {} {} L {} {} L {} {} L {} {} L {} {}",
                span(from.x + NODE_W / 2),
                span(from.y + NODE_H),
                span(from.x + NODE_W / 2),
                span(below),
                span(LANE_X),
                span(below),
                span(LANE_X),
                span(y2),
                span(x2 - 9),
                span(y2)
            )
        }
        // 왼쪽이 비어 있다 — 곧장 나간다.
        false => {
            let y1 = from.y + NODE_H / 2;
            format!(
                "M {} {} L {} {} L {} {} L {} {}",
                span(from.x),
                span(y1),
                span(LANE_X),
                span(y1),
                span(LANE_X),
                span(y2),
                span(x2 - 9),
                span(y2)
            )
        }
    };
    let _ = writeln!(
        out,
        "<path class=\"g-revisit\" d=\"{d}\" fill=\"none\" stroke=\"currentColor\" \
         stroke-width=\"2\" stroke-dasharray=\"8 5\"/>"
    );
    // 오른쪽을 가리키는 화살촉 — `marker` 와 `url(#…)` 을 쓰지 않는다. 참조가 하나도 없는
    // 그림이 규칙을 지키기 쉽다.
    let _ = writeln!(
        out,
        "<path class=\"g-head\" d=\"M {} {} l -8 -5 l 0 10 z\" fill=\"currentColor\"/>",
        span(x2 - 1),
        span(y2)
    );
}

fn arrow_down(out: &mut String, x: i32, y: i32) {
    let _ = writeln!(
        out,
        "<path class=\"g-head\" d=\"M {} {} l -5 -8 l 10 0 z\" fill=\"currentColor\"/>",
        span(x),
        span(y)
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

/// node 하나가 지니는 class 이름 — **renderer 가 소유한 상수뿐이다.**
fn class_of(cycle: &VisualCycle) -> &'static str {
    match cycle.standing {
        Standing::Here => "g-cycle g-now",
        Standing::Active => "g-cycle g-on",
        Standing::LeftBehind => "g-cycle g-off",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use super::super::graph::render_monitor_graph;

    /// 그림이 지어야 하는 자리 하나 — layout 시험이 쓰는 것과 같은 모양이다.
    fn drawn() -> String {
        let seen = super::super::graph::tests::reading_one();
        render_monitor_svg(&render_monitor_graph(&seen))
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
        assert!(svg.contains(&format!("<desc id=\"{DESC_ID}\">{DESC}</desc>")), "{svg}");
    }

    #[test]
    fn the_picture_carries_no_way_out_of_itself() {
        let svg = drawn();
        // 밖으로 나가는 길도, 도는 코드도, HTML 을 다시 여는 문도 없다.
        for forbidden in [
            "<script", "foreignObject", "<image", "<use", "<a ", "xlink", "href", "src=",
            "onload", "onclick", "onerror", "javascript:", "url(", "<style", "style=", "@import",
        ] {
            assert!(!svg.contains(forbidden), "{forbidden:?} 가 그림에 있다");
        }
        // 사건 처리기는 이름이 `on` 으로 시작한다 — 태그 안에 그런 속성이 하나도 없다.
        for tag in svg.split('<').skip(1) {
            let inside = tag.split('>').next().unwrap_or("");
            for word in inside.split_whitespace().skip(1) {
                let name = word.split('=').next().unwrap_or("");
                assert!(
                    !name.starts_with("on"),
                    "사건 처리기 {name:?} 가 생겼다: <{inside}>"
                );
            }
        }
    }

    #[test]
    fn every_number_in_the_picture_is_finite_and_sane() {
        let svg = drawn();
        assert!(!svg.contains("NaN") && !svg.contains("Infinity"), "{svg}");

        // 자리와 크기는 **0 이상의 정수**뿐이다. 음수 크기도, 소수도, 지수 표기도 없다.
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
        // `d` 안의 수도 전부 정수다. 상대 이동(`l`)은 음수일 수 있으므로 부호만 허용한다.
        for chunk in svg.split(" d=\"").skip(1) {
            let path = chunk.split('"').next().expect("닫는 따옴표");
            for word in path.split_whitespace() {
                if word.chars().all(|ch| ch.is_ascii_alphabetic()) {
                    continue; // 명령 글자
                }
                let number: i64 = word
                    .parse()
                    .unwrap_or_else(|_| panic!("경로에 정수가 아닌 {word:?} 가 있다"));
                assert!(number.abs() < 100_000, "경로의 수가 상한을 넘었다: {number}");
            }
        }
    }

    #[test]
    fn a_nasty_string_becomes_letters_not_markup() {
        // 사용자 글이 그림에 닿는 통로가 지금은 없다. 그래도 문을 재 둔다 — 규칙이
        // 느슨해지는 날 이 시험이 먼저 깨진다.
        let nasty = "</text><script>alert(1)</script> & \"x\" 'y' <b>";
        let escaped = text(nasty);
        assert!(!escaped.contains('<') && !escaped.contains('>'), "{escaped}");
        assert!(escaped.starts_with("&lt;/text&gt;"), "{escaped}");
        assert!(escaped.contains("&amp; &quot;x&quot; &#39;y&#39;"), "{escaped}");
        // `&` 를 먼저 바꿨다 — 두 번 바뀌지 않았다.
        assert!(!escaped.contains("&amp;lt;"), "탈출을 두 번 했다");
    }

    #[test]
    fn no_user_sentence_ever_reaches_the_picture() {
        // **폭이 사용자 글의 길이에 매이지 않는다는 보장이 여기 있다.**
        let mut seen = super::super::graph::tests::reading_one();
        let long = "가".repeat(4000);
        seen.current_cycle.facts.experiment_definition = Some(crate::ExperimentDefinition {
            problem: long.clone(),
            success_condition: long.clone(),
        });
        let plan = render_monitor_graph(&seen);
        let svg = render_monitor_svg(&plan);
        assert!(!svg.contains(&long), "긴 사용자 글이 그림에 들어갔다");
        assert!(!svg.contains("가가가가가가가가가가"), "사용자 글 조각이 들어갔다");
        assert!(plan.width < 1_200, "폭이 사용자 글을 따라 자랐다: {}", plan.width);
    }

    #[test]
    fn the_picture_scales_instead_of_fixing_its_size() {
        // 작은 화면이 가로 scroll 없이 따라오는 것은 **`viewBox` 덕분이다.** 고정 크기를
        // 적으면 390px 폭에서 그림이 잘린다.
        let svg = drawn();
        let open = svg.lines().next().expect("여는 태그");
        assert!(open.contains("viewBox=\"0 0 "), "viewBox 가 없다: {open}");
        assert!(open.contains("preserveAspectRatio="), "비율 규칙이 없다: {open}");
        assert!(!open.contains(" width=\""), "그림이 제 폭을 고정했다: {open}");
        assert!(!open.contains(" height=\""), "그림이 제 높이를 고정했다: {open}");
    }

    #[test]
    fn the_same_plan_draws_byte_identical_svg() {
        let seen = super::super::graph::tests::reading_one();
        let once = render_monitor_svg(&render_monitor_graph(&seen));
        let twice = render_monitor_svg(&render_monitor_graph(&seen));
        assert_eq!(once, twice, "같은 Snapshot 이 다른 그림을 냈다");
    }

    #[test]
    fn state_and_relation_survive_without_any_colour() {
        let svg = drawn();
        // 낱말로 남는다.
        for word in ["현재", "성공", "실패", "열림", "지나온 갈래"] {
            assert!(svg.contains(word), "{word:?} 가 글로 없다");
        }
        // 그리고 선의 모양으로도 남는다 — 되돌아감은 점선, 부모는 실선.
        assert!(svg.contains("class=\"g-revisit\""), "되돌아감의 줄이 없다");
        assert!(svg.contains("class=\"g-parent\""), "부모의 줄이 없다");
        let revisit = svg
            .lines()
            .find(|line| line.contains("g-revisit"))
            .expect("되돌아감의 줄");
        let parent = svg
            .lines()
            .find(|line| line.contains("g-parent"))
            .expect("부모의 줄");
        assert!(revisit.contains("stroke-dasharray"), "되돌아감이 실선이다: {revisit}");
        assert!(!parent.contains("stroke-dasharray"), "부모가 점선이다: {parent}");
        // **지금 자리는 테두리가 둘이다.** 색과 무관한 표시라, 색을 지워도 남는다.
        let now = svg
            .split("<g class=\"g-cycle g-now\">")
            .nth(1)
            .and_then(|rest| rest.split("</g>").next())
            .expect("지금 자리의 무리");
        assert_eq!(now.matches("<rect").count(), 2, "지금 자리의 이중 테두리가 사라졌다");
        let others = svg
            .split("<g class=\"g-cycle g-on\">")
            .nth(1)
            .and_then(|rest| rest.split("</g>").next())
            .expect("활성 조상의 무리");
        assert_eq!(others.matches("<rect").count(), 1, "조상까지 이중 테두리가 됐다");

        // 색을 정하는 attribute 를 renderer 가 직접 적지 않는다 — `currentColor` 뿐이다.
        for chunk in svg.split("stroke=\"").skip(1) {
            let value = chunk.split('"').next().expect("닫는 따옴표");
            assert_eq!(value, "currentColor", "그림이 색을 직접 정했다: {value}");
        }
    }
}
