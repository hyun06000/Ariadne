//! 사람이 적어 준 글을 Report 로 읽는다.
//!
//! 여기서 재는 것은 하나다: **적은 글자가 그대로 값이 되는가.**
//!
//! 이 시험들이 있는 까닭은 실사용 보고 #124 다 — YAML 로 받던 시절, ` #` 뒤가 주석으로
//! 먹혀 문장이 잘린 채 `gil close` 가 **성공했다.** 성공했는데 다른 데이터가 되는 것이
//! 이 프로젝트가 없애려는 병 그 자체다.

use gil::Report;

fn parse(text: &str) -> Report {
    Report::parse(text).unwrap_or_else(|err| panic!("읽히지 않았다: {err}\n---\n{text}"))
}

// ── 적은 글자가 그대로 값이 된다 ──────────────────────────────────────────

#[test]
fn a_node_name_inside_a_sentence_survives() {
    // #124 그대로. GIL 이 스스로 #7 이라 표시하니 사람이 그렇게 쓰는 것은 자연스럽다.
    let sentence = "기존 Walk의 #7 verify open 상태를 정상적으로 찾아 표시해 작업을 이어갈 수 있었다";
    let report = parse(&format!("execution: 걸었다\nresult: {sentence}\n"));
    assert_eq!(report.get("result"), Some(sentence));
}

#[test]
fn a_hash_anywhere_is_just_a_letter() {
    for value in ["#7", "앞 #7", "#", "a # b # c", "끝에 #"] {
        let report = parse(&format!("problem: {value}\n"));
        assert_eq!(report.get("problem"), Some(value), "{value:?} 가 바뀌었다");
    }
}

#[test]
fn nothing_is_read_as_a_number_or_a_yes_or_a_no() {
    // 형 변환이 없다는 것은 `3.10` 이 `3.1` 이 되지 않는다는 뜻이다.
    for value in ["3.10", "007", "no", "yes", "true", "null", "~", "0x10"] {
        let report = parse(&format!("problem: {value}\n"));
        assert_eq!(report.get("problem"), Some(value), "{value:?} 가 바뀌었다");
    }
}

#[test]
fn a_colon_in_the_value_stays_in_the_value() {
    // 값은 **첫 콜론 뒤부터 줄 끝까지**다. 그 안을 다시 해석하지 않는다.
    let report = parse("problem: 결론: 이것이 원인이다\n");
    assert_eq!(report.get("problem"), Some("결론: 이것이 원인이다"));
}

#[test]
fn a_value_may_start_with_anything() {
    for value in ["- 첫째 이유", "? 무엇을", "| 막대", "> 화살", "[하나]", "{둘}", "'따옴표'"] {
        let report = parse(&format!("problem: {value}\n"));
        assert_eq!(report.get("problem"), Some(value), "{value:?} 가 바뀌었다");
    }
}

// ── 꼴 ────────────────────────────────────────────────────────────────────

#[test]
fn an_indented_field_joins_its_name_with_a_dot() {
    // 명세는 칸을 `next_direction.action` 이라 부른다. 들여쓴 것이 그 이름이 돼야 한다.
    let report = parse(
        "verdict: failure\n\
         next_direction:\n  \
         action: revisit\n  \
         target_node_ref: step:C2/S4\n  \
         reason: 가설부터 다시\n",
    );
    assert_eq!(report.get("next_direction.action"), Some("revisit"));
    assert_eq!(
        report.get("next_direction.target_node_ref"),
        Some("step:C2/S4")
    );
    assert_eq!(report.get("next_direction.reason"), Some("가설부터 다시"));
    assert_eq!(report.get("verdict"), Some("failure"));
    assert!(!report.has("next_direction"), "가르는 이름이 칸으로도 남았다");
}

#[test]
fn nesting_goes_as_deep_as_it_is_written() {
    // 깊이를 코드에 적어 두지 않는다 — 적힌 만큼 깊어진다.
    let report = parse("a:\n  b:\n    c:\n      d: 값\n");
    assert_eq!(report.get("a.b.c.d"), Some("값"));
}

#[test]
fn a_block_keeps_every_line_it_was_given() {
    let report = parse(
        "result: |\n  \
         첫 줄\n  \
         둘째 줄 — 여기에도 #7 이 산다\n\
         next: 뒤\n",
    );
    assert_eq!(
        report.get("result"),
        Some("첫 줄\n둘째 줄 — 여기에도 #7 이 산다")
    );
    assert_eq!(report.get("next"), Some("뒤"), "블록이 뒤 칸까지 먹었다");
}

#[test]
fn a_blank_line_inside_a_block_is_part_of_the_value() {
    // 빈 줄 뒤에 두 줄을 둔다 — 빈 줄이 **한 번만** 들어가는지까지 재려면 그래야 한다.
    let report = parse("result: |\n  위\n\n  가운데\n  아래\n");
    assert_eq!(report.get("result"), Some("위\n\n가운데\n아래"));
}

#[test]
fn a_blank_line_after_a_block_is_not() {
    // 값 뒤의 빈 줄까지 값에 넣으면 적지 않은 것이 값에 붙는다.
    let report = parse("result: |\n  위\n\nnext: 뒤\n");
    assert_eq!(report.get("result"), Some("위"));
    assert_eq!(report.get("next"), Some("뒤"));
}

#[test]
fn a_name_with_nothing_under_it_is_an_empty_field() {
    let report = parse("problem: 있다\nsuccess_condition:\n");
    assert_eq!(report.get("success_condition"), Some(""));
}

#[test]
fn an_empty_text_is_an_empty_report() {
    assert!(parse("").is_empty());
    assert!(parse("\n\n  \n").is_empty());
}

// ── 거절은 시끄럽게 ───────────────────────────────────────────────────────

fn refused(text: &str) -> gil::ReportSyntaxError {
    Report::parse(text).expect_err("거절돼야 하는데 읽혔다")
}

#[test]
fn a_line_without_a_name_is_refused() {
    let err = refused("problem: 있다\n그냥 문장\n");
    assert_eq!(err.line, 2, "몇 번째 줄인지 틀리게 말한다: {err}");
}

#[test]
fn an_indent_that_hangs_on_nothing_is_refused_and_says_how_to_fix_it() {
    // 여러 줄을 적으려다 `|` 를 빠뜨린 자리다. 여기서 조용히 삼키면 값이 사라진다.
    let err = refused("result: 첫 줄\n  둘째 줄\n");
    assert_eq!(err.line, 2);
    assert!(err.detail.contains('|'), "고치는 법을 말하지 않는다: {err}");
}

#[test]
fn a_tab_indent_is_refused() {
    // 탭의 폭은 보는 곳마다 다르다 — 값이 조용히 어긋나는 것보다 거절이 낫다.
    let err = refused("a:\n\tb: 값\n");
    assert_eq!(err.line, 2);
}

#[test]
fn a_name_with_a_space_in_it_is_refused() {
    let err = refused("두 낱말: 값\n");
    assert_eq!(err.line, 1);
}

#[test]
fn a_report_read_back_is_the_same_report() {
    // 한 번 읽은 것을 다시 적어 다시 읽어도 같아야 한다 — 값이 조용히 줄면 여기서 갈린다.
    let text = "problem: #7 을 찾았다\nnext_direction:\n  action: revisit\n  reason: 다시\n";
    let once = parse(text);
    let again = parse(
        &once
            .field_names()
            .map(|name| format!("{name}: {}\n", once.get(name).unwrap()))
            .collect::<String>(),
    );
    assert_eq!(once, again);
}

#[test]
fn the_dotted_form_and_the_nested_form_make_the_same_report() {
    // 사람은 둘 중 무엇으로도 적는다 — 둘이 다른 Report 가 되면 같은 문법이 두 벌이 된다.
    // GIL 이 골격과 예시를 내보일 때 쓰는 canonical 표기는 **dotted** 다.
    let dotted = parse(
        "verdict: success\n\
         next_direction.action: close_cycle\n\
         next_direction.reason: 여기서 끝난다\n",
    );
    let nested = parse(
        "verdict: success\n\
         next_direction:\n  \
           action: close_cycle\n  \
           reason: 여기서 끝난다\n",
    );

    assert_eq!(dotted, nested, "같은 것을 적었는데 다른 Report 가 됐다");
    assert_eq!(nested.get("next_direction.action"), Some("close_cycle"));
    let mut names: Vec<&str> = nested.field_names().collect();
    names.sort_unstable();
    assert_eq!(
        names,
        ["next_direction.action", "next_direction.reason", "verdict"],
        "중간 이름 next_direction 이 빈 칸으로 남았다"
    );
}

#[test]
fn a_block_scalar_reads_the_same_however_its_name_was_written() {
    // basis_refs 는 block scalar 다 — 이름을 접어 적어도 줄들은 그대로여야 한다.
    let flat = parse("basis_refs: |\n  step:C1/S1\n  step:C1/S2\n");
    let under = parse("synthesis:\n  basis_refs: |\n    step:C1/S1\n    step:C1/S2\n");

    assert_eq!(flat.get("basis_refs"), Some("step:C1/S1\nstep:C1/S2"));
    assert_eq!(
        under.get("synthesis.basis_refs"),
        flat.get("basis_refs"),
        "접어 적었더니 줄이 달라졌다"
    );
}
