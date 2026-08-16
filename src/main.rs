//! `gil` — 걷기를 부를 수 있게 하는 가장 얇은 표면.
//!
//! 여기에는 규칙도 판정도 없다. 하는 일은 셋뿐이다: 저장된 걷기를 세우고, 라이브러리에
//! 한 수를 넘기고, 결과를 사람의 말로 적는다. 거절의 이유도 라이브러리의 말을 그대로 옮긴다 —
//! 여기서 다시 쓰면 같은 판정이 두 자리에서 서로 다르게 말하게 된다.

use std::io::{self, IsTerminal, Read};
use std::path::{Path, PathBuf};
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
        "story" => Ok(story(&open_session()?.walk)),
        other => Err(format!(
            "{other:?} 는 gil 이 아는 명령이 아니다.\n\n{}",
            help()
        )),
    }
}

/// 지금 이어 걷고 있는 걷기 — 그리고 **그것이 어느 파일인지**.
///
/// 자리를 함께 들고 다닌다. 읽은 파일과 쓰는 파일이 갈리면 적은 것이 다른 데로 간다.
struct Session {
    walk: Walk,
    path: PathBuf,
}

/// 여기서 위로 거슬러 오르며 **가장 가까운** 걷기를 찾는다.
///
/// Agent 는 소스·시험·하위 패키지 폴더를 계속 오간다. 서 있는 자리에서만 찾으면 명령마다
/// 뿌리로 돌아가야 하고, 잊으면 **같은 프로젝트에 두 번째 걷기가 조용히 생긴다**
/// (실사용 보고 #125). 사고의 기록이 두 갈래로 갈리는 것이라 마찰이 아니라 사고다.
fn find_walk() -> Result<Option<PathBuf>, String> {
    let here = std::env::current_dir().map_err(|err| format!("지금 어디인지 알 수 없다: {err}"))?;
    Ok(here
        .ancestors()
        .map(|dir| dir.join(gil::WALK_PATH))
        .find(|candidate| candidate.exists()))
}

/// 여기에 새로 눕힐 자리. **언제나 온전한 경로다** — 어느 걷기인지 화면이 흔들림 없이
/// 말할 수 있어야 하고, 반쪽 경로는 서 있는 자리에 따라 다른 것을 가리킨다.
fn walk_path_here() -> Result<PathBuf, String> {
    let here = std::env::current_dir().map_err(|err| format!("지금 어디인지 알 수 없다: {err}"))?;
    Ok(here.join(gil::WALK_PATH))
}

/// 이 걷기가 서 있는 자리가 아닌 곳에 누워 있는가.
fn found_above(path: &Path) -> bool {
    match walk_path_here() {
        Ok(here) => path != here,
        Err(_) => false,
    }
}

fn rules() -> Result<RuleSet, String> {
    RuleSet::builtin().map_err(|err| format!("함께 실린 명세를 읽지 못했다: {err}"))
}

fn open_session() -> Result<Session, String> {
    let Some(path) = find_walk()? else {
        return Err(format!(
            "여기서도 그 위 어디에서도 걷기를 못 찾았다 ({}) — `gil start` 로 시작한다",
            gil::WALK_PATH
        ));
    };
    let walk = load(rules()?, &path).map_err(|err| match err {
        // 방금 있는 것을 보고 왔다. 그새 사라졌다면 그건 다른 이야기다.
        StoreError::NotFound { .. } => format!("걷기가 사라졌다: {}", path.display()),
        other => other.to_string(),
    })?;
    Ok(Session { walk, path })
}

impl Session {
    /// 읽어 온 **그 파일**에 도로 눕힌다.
    fn write(&self) -> Result<(), String> {
        save(&self.walk, &self.path).map_err(|err| err.to_string())
    }
}

// ── 명령 ───────────────────────────────────────────────────────────────────

fn start() -> Result<String, String> {
    // 위에 이미 걷기가 있으면 여기서 새로 시작하지 않는다 — 그러면 한 프로젝트에
    // 걷기가 둘이 되고, 어느 쪽에 적히는지는 서 있는 자리가 정하게 된다.
    if let Some(existing) = find_walk()? {
        return Err(format!(
            "이미 걷고 있다 ({}) — 지금 어디인지는 `gil status` 가 답한다.\n\
             여기서 따로 시작하면 한 프로젝트에 걷기가 둘이 된다.\n\
             정말 다시 시작하려면 그 파일을 직접 치워라. gil 은 적힌 사고를 지우지 않는다.",
            existing.display()
        ));
    }

    let session = Session {
        walk: Walk::start(rules()?),
        path: walk_path_here()?,
    };
    session.write()?;
    Ok(format!(
        "{}\n\n{}",
        session.path.display(),
        where_now(&session)
    ))
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

    let mut session = open_session()?;
    session.walk.open(kind).map_err(|err| err.to_string())?;
    session.write()?;
    Ok(where_now(&session))
}

fn close() -> Result<String, String> {
    let report = read_report()?;
    let mut session = open_session()?;
    session.walk.close(report).map_err(|err| err.to_string())?;
    session.write()?;
    Ok(where_now(&session))
}

fn revisit() -> Result<String, String> {
    let mut session = open_session()?;
    session.walk.revisit().map_err(|err| err.to_string())?;
    session.write()?;
    Ok(where_now(&session))
}

fn status() -> Result<String, String> {
    Ok(where_now(&open_session()?))
}

// ── 지금 어디인가 ──────────────────────────────────────────────────────────

/// 세 줄로 답한다: 어디에 서 있는가 · 무엇을 걸어왔는가 · 여기서 무엇을 열 수 있는가.
///
/// 걷기가 **서 있는 자리에 없으면** 어느 파일인지를 먼저 말한다. 있으면 말하지 않는다 —
/// 예사로운 일에 줄을 쓰면 정작 알려야 할 때 그 줄이 안 읽힌다.
fn where_now(session: &Session) -> String {
    let walk = &session.walk;
    let mut out = String::new();

    if found_above(&session.path) {
        out.push_str(&format!("걷기: {}\n", session.path.display()));
    }

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
