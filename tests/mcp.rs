//! **MCP stdio 표면의 시험** — 진짜 프로세스를 세워 진짜 frame 을 주고받는다.
//!
//! 여기서 재는 것은 배선이지 domain 이 아니다. GIL 이 무엇을 옳다고 판정하는가는 이미 다른
//! 시험들이 잡았다. 이 파일이 지키는 것은 넷이다.
//!
//! 1. **같은 글자** — 같은 Project 에서 CLI 와 MCP 의 `said` 가 byte 로 같다
//! 2. **정확 경로** — 자식 자리를 받고 부모 Project 로 물러서지 않는다
//! 3. **깨끗한 stdout** — JSON-RPC frame 말고는 한 글자도 없다
//! 4. **하나의 tool** — 표면이 조용히 늘지 않는다

use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};

fn gil() -> PathBuf {
    // 시험이 부르는 것은 **지금 지은 그 binary** 다.
    let mut at = std::env::current_exe().expect("시험 실행 파일");
    at.pop();
    if at.ends_with("deps") {
        at.pop();
    }
    at.join("gil")
}

fn scratch(name: &str) -> PathBuf {
    let at = std::env::temp_dir().join(format!(
        "gil-mcp-test-{name}-{}-{:?}",
        std::process::id(),
        std::thread::current().id()
    ));
    let _ = std::fs::remove_dir_all(&at);
    std::fs::create_dir_all(&at).expect("자리");
    at
}

/// 진짜 Project 하나를 만든다 — CLI 로. 시험이 저장 형식을 손으로 짓지 않는다.
fn started(at: &Path) {
    let done = Command::new(gil())
        .arg("start")
        .current_dir(at)
        .output()
        .expect("gil start");
    assert!(done.status.success(), "{}", String::from_utf8_lossy(&done.stderr));
}

fn cli_status(at: &Path) -> String {
    let done = Command::new(gil())
        .arg("status")
        .current_dir(at)
        .output()
        .expect("gil status");
    assert!(done.status.success(), "{}", String::from_utf8_lossy(&done.stderr));
    String::from_utf8(done.stdout).expect("utf-8")
}

// ── MCP 손님 ───────────────────────────────────────────────────────────────

struct Client {
    kid: Child,
    out: BufReader<std::process::ChildStdout>,
    next: i64,
}

impl Client {
    /// **Node 없이** 선다 — Rust binary 하나가 전부다.
    fn serve() -> Self {
        let mut kid = Command::new(gil())
            .args(["mcp", "--serve"])
            // cwd 를 **다른 자리**에 둔다. 요청 결과가 여기에 흔들리면 그것이 결함이다.
            .current_dir(std::env::temp_dir())
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .expect("gil mcp --serve");
        let out = BufReader::new(kid.stdout.take().expect("stdout"));
        Self { kid, out, next: 1 }
    }

    fn send(&mut self, frame: &serde_json::Value) {
        let line = serde_json::to_string(frame).expect("frame");
        let stdin = self.kid.stdin.as_mut().expect("stdin");
        writeln!(stdin, "{line}").expect("보낸다");
        stdin.flush().expect("흘린다");
    }

    fn read(&mut self) -> serde_json::Value {
        let mut line = String::new();
        self.out.read_line(&mut line).expect("받는다");
        assert!(!line.trim().is_empty(), "빈 줄을 받았다");
        serde_json::from_str(&line)
            .unwrap_or_else(|err| panic!("JSON-RPC 가 아닌 것이 stdout 에 있다: {line:?} ({err})"))
    }

    fn request(&mut self, method: &str, params: serde_json::Value) -> serde_json::Value {
        let id = self.next;
        self.next += 1;
        self.send(&serde_json::json!({
            "jsonrpc": "2.0", "id": id, "method": method, "params": params
        }));
        let got = self.read();
        assert_eq!(got["id"], serde_json::json!(id), "id 가 어긋났다");
        got
    }

    fn initialize(&mut self) -> serde_json::Value {
        let got = self.request(
            "initialize",
            serde_json::json!({
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": { "name": "gil-test", "version": "0" }
            }),
        );
        self.send(&serde_json::json!({
            "jsonrpc": "2.0", "method": "notifications/initialized"
        }));
        got
    }

    fn status(&mut self, root: &str) -> serde_json::Value {
        self.request(
            "tools/call",
            serde_json::json!({
                "name": "gil_status",
                "arguments": { "project_root": root }
            }),
        )
    }

    /// stdin 을 닫고 **깨끗이** 끝나는지 본다 — 남은 stdout 도 함께 돌려준다.
    fn eof(mut self) -> (std::process::ExitStatus, String) {
        drop(self.kid.stdin.take());
        let mut rest = String::new();
        use std::io::Read as _;
        self.out.read_to_string(&mut rest).ok();
        let done = self.kid.wait().expect("끝난다");
        (done, rest)
    }
}

fn text_of(reply: &serde_json::Value) -> String {
    reply["result"]["content"][0]["text"]
        .as_str()
        .unwrap_or_else(|| panic!("text 가 없다: {reply}"))
        .to_string()
}

// ── 시험 ───────────────────────────────────────────────────────────────────

#[test]
fn initialize_succeeds_and_says_who_is_answering() {
    let mut mcp = Client::serve();
    let got = mcp.initialize();
    assert_eq!(got["jsonrpc"], "2.0");
    assert!(got["result"]["serverInfo"]["name"].is_string(), "{got}");
    assert!(got["result"]["capabilities"]["tools"].is_object(), "{got}");
    let (done, _) = mcp.eof();
    assert!(done.success());
}

#[test]
fn tools_list_returns_exactly_one_tool_named_gil_status() {
    let mut mcp = Client::serve();
    mcp.initialize();
    let got = mcp.request("tools/list", serde_json::json!({}));
    let tools = got["result"]["tools"].as_array().expect("tools");
    assert_eq!(tools.len(), 1, "표면이 하나가 아니다: {got}");
    assert_eq!(tools[0]["name"], "gil_status");
    mcp.eof();
}

/// **이 조각의 목표 문장.** 같은 Project 에서 두 진입점이 같은 글자를 낸다.
#[test]
fn the_cli_and_the_mcp_say_the_very_same_bytes() {
    let at = scratch("same");
    started(&at);
    let by_cli = cli_status(&at);

    let mut mcp = Client::serve();
    mcp.initialize();
    let got = mcp.status(at.to_str().expect("utf-8"));
    assert_eq!(got["result"]["isError"], serde_json::json!(false), "{got}");
    let by_mcp = text_of(&got);
    mcp.eof();

    assert_eq!(
        by_mcp.as_bytes(),
        by_cli.as_bytes(),
        "같은 자리에서 다른 말을 했다\nCLI:\n{by_cli}\nMCP:\n{by_mcp}"
    );
    std::fs::remove_dir_all(&at).ok();
}

/// 부모가 Project 여도 **자식은 자식이다.** 말없이 위로 물러서지 않는다.
#[test]
fn a_child_directory_never_opens_the_parent_project() {
    let parent = scratch("parent");
    started(&parent);
    let child = parent.join("tmp");
    std::fs::create_dir_all(&child).expect("자리");

    let before = std::fs::read(parent.join(".gil/state.yaml")).expect("기록");
    let by_cli_at_parent = cli_status(&parent);

    let mut mcp = Client::serve();
    mcp.initialize();
    let got = mcp.status(child.to_str().expect("utf-8"));
    assert_eq!(got["result"]["isError"], serde_json::json!(true), "{got}");
    let said = text_of(&got);
    mcp.eof();

    // 거절이지, 부모의 상태가 아니다.
    assert_ne!(said, by_cli_at_parent, "자식 요청이 부모 Project 를 열었다");
    assert!(said.contains("위로 거슬러 오르지 않았다"), "{said}");
    // 거절문에 절대경로를 싣지 않는다.
    assert!(!said.contains('/'), "거절문에 경로가 새어 나왔다: {said}");

    // 부모의 bytes 와 Journey 는 그대로다.
    let after = std::fs::read(parent.join(".gil/state.yaml")).expect("기록");
    assert_eq!(before, after, "부모의 기록이 바뀌었다");
    assert_eq!(cli_status(&parent), by_cli_at_parent, "부모의 자리가 움직였다");

    std::fs::remove_dir_all(&parent).ok();
}

#[test]
fn a_relative_project_root_is_refused() {
    let mut mcp = Client::serve();
    mcp.initialize();
    let got = mcp.status("some/where");
    assert_eq!(got["result"]["isError"], serde_json::json!(true), "{got}");
    let said = text_of(&got);
    assert!(said.contains("온전한 경로"), "{said}");
    mcp.eof();
}

#[test]
fn a_place_without_a_project_is_refused() {
    let empty = scratch("empty");
    let mut mcp = Client::serve();
    mcp.initialize();
    let got = mcp.status(empty.to_str().expect("utf-8"));
    assert_eq!(got["result"]["isError"], serde_json::json!(true), "{got}");
    assert!(text_of(&got).contains("걷기가 없다"), "{got}");
    mcp.eof();
    std::fs::remove_dir_all(&empty).ok();
}

/// server 의 cwd 가 **다른 GIL Project** 여도 답은 준 자리의 것이다.
#[test]
fn the_servers_own_working_directory_never_leaks_into_the_answer() {
    let asked = scratch("asked");
    let elsewhere = scratch("elsewhere");
    started(&asked);
    started(&elsewhere);

    let mut kid = Command::new(gil())
        .args(["mcp", "--serve"])
        .current_dir(&elsewhere) // ← 다른 Project 안에 서 있다
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("serve");
    let out = BufReader::new(kid.stdout.take().expect("stdout"));
    let mut mcp = Client { kid, out, next: 1 };
    mcp.initialize();
    let got = mcp.status(asked.to_str().expect("utf-8"));
    let said = text_of(&got);
    mcp.eof();

    assert_eq!(said.as_bytes(), cli_status(&asked).as_bytes(), "{said}");
    std::fs::remove_dir_all(&asked).ok();
    std::fs::remove_dir_all(&elsewhere).ok();
}

/// stdin 이 닫히면 **깨끗이** 끝난다 — 매달리지 않고, 뒤에 쓰레기를 남기지 않는다.
#[test]
fn closing_stdin_ends_the_server_cleanly_and_leaves_nothing_behind() {
    let at = scratch("eof");
    started(&at);
    let mut mcp = Client::serve();
    mcp.initialize();
    mcp.status(at.to_str().expect("utf-8"));
    let (done, rest) = mcp.eof();
    assert!(done.success(), "깨끗이 끝나지 않았다: {done:?}");
    assert!(rest.trim().is_empty(), "마지막 frame 뒤에 글자가 남았다: {rest:?}");
    std::fs::remove_dir_all(&at).ok();
}

/// **stdout 에는 JSON-RPC 말고 아무것도 없다.** 진단 한 줄이 새면 여기서 걸린다.
#[test]
fn stdout_carries_json_rpc_frames_and_nothing_else() {
    let at = scratch("clean");
    started(&at);

    let mut kid = Command::new(gil())
        .args(["mcp", "--serve"])
        .current_dir(std::env::temp_dir())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("serve");
    {
        let stdin = kid.stdin.as_mut().expect("stdin");
        for line in [
            r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}"#.to_string(),
            r#"{"jsonrpc":"2.0","method":"notifications/initialized"}"#.to_string(),
            r#"{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}"#.to_string(),
            serde_json::json!({
                "jsonrpc":"2.0","id":3,"method":"tools/call",
                "params":{"name":"gil_status","arguments":{"project_root": at.to_str().expect("utf-8")}}
            }).to_string(),
            // 일부러 거절당할 것 하나 — 거절의 말이 stdout 으로 새는지 본다.
            serde_json::json!({
                "jsonrpc":"2.0","id":4,"method":"tools/call",
                "params":{"name":"gil_status","arguments":{"project_root":"relative/path"}}
            }).to_string(),
        ] {
            writeln!(stdin, "{line}").expect("보낸다");
        }
    }
    drop(kid.stdin.take());
    let done = kid.wait_with_output().expect("끝난다");
    assert!(done.status.success());

    let said = String::from_utf8(done.stdout).expect("utf-8");
    let mut frames = 0;
    for line in said.lines() {
        if line.trim().is_empty() {
            continue;
        }
        let one: serde_json::Value = serde_json::from_str(line)
            .unwrap_or_else(|err| panic!("stdout 에 JSON-RPC 가 아닌 줄이 있다: {line:?} ({err})"));
        assert_eq!(one["jsonrpc"], "2.0", "frame 이 아니다: {line}");
        frames += 1;
    }
    assert_eq!(frames, 4, "답이 넷이어야 한다:\n{said}");

    std::fs::remove_dir_all(&at).ok();
}
