//! `gil` — 걷기를 부를 수 있게 하는 가장 얇은 표면.
//!
//! 여기에는 규칙도 판정도 없다. 하는 일은 셋뿐이다: 저장된 걷기를 세우고, 라이브러리에
//! 한 수를 넘기고, 결과를 사람의 말로 적는다. 거절의 이유도 라이브러리의 말을 그대로 옮긴다 —
//! 여기서 다시 쓰면 같은 판정이 두 자리에서 서로 다르게 말하게 된다.

use std::io::{self, IsTerminal, Read};
use std::path::PathBuf;
use std::process::ExitCode;

use gil::{NodeKind, Report, RuleSet, StoreError, Walk, load, save, story};

fn main() -> ExitCode {
    match run() {
        Ok(text) => {
            print!("{text}");
            ExitCode::SUCCESS
        }
        Err(message) => {
            eprintln!("{message}");
            ExitCode::FAILURE
        }
    }
}

fn run() -> Result<String, String> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let command = args.first().map(String::as_str).unwrap_or("--help");

    match command {
        "--help" | "-h" | "help" => Ok(help()),
        "--version" | "-V" | "version" => Ok(format!("gil {}\n", env!("CARGO_PKG_VERSION"))),
        "start" => start(),
        "open" => open(args.get(1)),
        "close" => close(),
        "revisit" => revisit(),
        "status" => status(),
        "story" => Ok(story(&read_walk()?)),
        other => Err(format!(
            "{other:?} 는 gil 이 아는 명령이 아니다.\n\n{}",
            help()
        )),
    }
}

/// 걷기가 눕는 자리 — 지금 서 있는 디렉터리 아래.
///
/// 위로 거슬러 찾지 않는다. 어느 파일을 쓰는지 늘 함께 적어, 남의 걷기를 제 것으로
/// 오해하는 일이 없게 한다.
fn walk_path() -> PathBuf {
    PathBuf::from(gil::WALK_PATH)
}

fn rules() -> Result<RuleSet, String> {
    RuleSet::builtin().map_err(|err| format!("함께 실린 명세를 읽지 못했다: {err}"))
}

fn read_walk() -> Result<Walk, String> {
    let path = walk_path();
    load(rules()?, &path).map_err(|err| match err {
        StoreError::NotFound { .. } => format!(
            "여기에는 걷기가 없다 ({}) — `gil start` 로 시작한다",
            path.display()
        ),
        other => other.to_string(),
    })
}

fn write_walk(walk: &Walk) -> Result<(), String> {
    save(walk, walk_path()).map_err(|err| err.to_string())
}

// ── 명령 ───────────────────────────────────────────────────────────────────

fn start() -> Result<String, String> {
    let path = walk_path();
    if path.exists() {
        return Err(format!(
            "여기에는 이미 걷기가 있다 ({}) — 지금 어디인지는 `gil status` 가 답한다.\n\
             다시 시작하려면 그 파일을 직접 치워라. gil 은 적힌 사고를 지우지 않는다.",
            path.display()
        ));
    }

    let walk = Walk::start(rules()?);
    write_walk(&walk)?;
    Ok(format!("{}\n\n{}", path.display(), where_now(&walk)))
}

fn open(kind: Option<&String>) -> Result<String, String> {
    let Some(name) = kind else {
        return Err(format!(
            "무엇을 열지 적어야 한다 — `gil open <종류>`.\n{}",
            kinds_line()
        ));
    };
    let Some(kind) = NodeKind::parse(name) else {
        return Err(format!(
            "{name:?} 는 gil 이 아는 종류가 아니다.\n{}",
            kinds_line()
        ));
    };

    let mut walk = read_walk()?;
    walk.open(kind).map_err(|err| err.to_string())?;
    write_walk(&walk)?;
    Ok(where_now(&walk))
}

fn close() -> Result<String, String> {
    let report = read_report()?;
    let mut walk = read_walk()?;
    walk.close(report).map_err(|err| err.to_string())?;
    write_walk(&walk)?;
    Ok(where_now(&walk))
}

fn revisit() -> Result<String, String> {
    let mut walk = read_walk()?;
    walk.revisit().map_err(|err| err.to_string())?;
    write_walk(&walk)?;
    Ok(where_now(&walk))
}

fn status() -> Result<String, String> {
    Ok(where_now(&read_walk()?))
}

// ── 지금 어디인가 ──────────────────────────────────────────────────────────

/// 세 줄로 답한다: 어디에 서 있는가 · 무엇을 걸어왔는가 · 여기서 무엇을 열 수 있는가.
fn where_now(walk: &Walk) -> String {
    let mut out = String::new();

    let here = walk.current().and_then(|id| walk.node(id));
    match here {
        Some(node) => out.push_str(&format!("자리: {} {} ({})\n", node.id, node.kind, node.status)),
        None => out.push_str("자리: 아직 아무것도 열지 않았다\n"),
    }

    let closed = walk.history().count();
    out.push_str(&format!(
        "걸어온 것: {}개 (닫힘 {closed})\n",
        walk.nodes().len()
    ));

    if walk.is_finished() {
        out.push_str("다음: 이 사이클은 끝났다\n");
        return out;
    }

    if here.is_some_and(|node| !node.is_closed()) {
        out.push_str("다음: 여기를 먼저 닫는다 — `gil close` (Report 는 stdin 으로)\n");
        return out;
    }

    // 문법에게 묻지 않는다 — **여는 그 판정**에게 묻는다. 두 자리에 물으면 갈린다.
    let openable = walk.openable_here();
    let names: Vec<&str> = openable.iter().map(|kind| kind.as_str()).collect();
    match names.is_empty() {
        true => out.push_str("다음: 여기서 열 수 있는 것이 없다\n"),
        false => out.push_str(&format!("다음: 열 수 있는 것 — {}\n", names.join(", "))),
    }
    out
}

// ── stdin 에서 Report 를 받는다 ────────────────────────────────────────────

/// Report 는 stdin 으로만 받는다.
///
/// 통로를 하나로 둔다. 같은 것을 플래그로도 받으면 두 통로가 생기고, 그러면 둘이 어긋날 때
/// 무엇이 실제로 실렸는지 아무도 모른다 — 옛 도구가 가장 깊게 물린 상처가 그것이다.
fn read_report() -> Result<Report, String> {
    if io::stdin().is_terminal() {
        return Err(format!(
            "Report 는 stdin 으로 받는다 — 터미널에서 기다리지 않는다.\n\n{}",
            close_example()
        ));
    }

    let mut text = String::new();
    io::stdin()
        .read_to_string(&mut text)
        .map_err(|err| format!("stdin 을 읽지 못했다: {err}"))?;

    // 빈 글도 그대로 넘긴다 — 무엇이 빠졌는지는 문법이 말한다(여기서 짐작하지 않는다).
    Report::parse(&text).map_err(|err| format!("{err}\n\n{}", close_example()))
}

// ── 안내 ───────────────────────────────────────────────────────────────────

fn kinds_line() -> String {
    let names: Vec<&str> = NodeKind::ALL.iter().map(|kind| kind.as_str()).collect();
    format!("아는 종류: {}", names.join(", "))
}

fn close_example() -> String {
    "닫는 꼴 — 적은 글자가 그대로 값이 된다. 주석도, 인용도, 형 변환도 없다.\n\n  \
     gil close <<'EOF'\n  \
     problem: 줄 끝까지 그대로다 — #7 도 3.10 도 그냥 글자다\n  \
     next_direction:\n  \
     \x20 action: revisit          (들여쓰면 이름이 점으로 이어진다)\n  \
     interpretation: |\n  \
     \x20 여러 줄은 이렇게 연다.\n  \
     \x20 여기서도 #7 은 #7 이다.\n  \
     EOF"
        .to_string()
}

fn help() -> String {
    let mut out = String::from(
        "gil — 사고의 걷기를 열고, 적고, 닫고, 되돌아간다.\n\n\
         명령:\n  \
         gil start            여기(.gil/walk.yaml)에 빈 걷기를 시작한다\n  \
         gil open <종류>      지금 자리에서 다음 Step 을 연다\n  \
         gil close            열려 있는 Step 을 닫는다 (Report 는 stdin 으로)\n  \
         gil revisit          닫힌 판정에 **이미 적혀 있는** 되돌아감을 밟는다\n  \
         gil status           지금 어디인지 세 줄로 답한다\n  \
         gil story            걸어온 것을 사람의 말로 읽는다\n  \
         gil --version        판을 밝힌다\n\n",
    );
    out.push_str(&kinds_line());
    out.push_str("\n\n");
    out.push_str(&close_example());
    out.push('\n');
    out
}
