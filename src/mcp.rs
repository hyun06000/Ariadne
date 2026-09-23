//! **MCP stdio 표면** — 같은 GIL 을 Agent 가 직접 부르는 문.
//!
//! 이 조각이 묻는 것은 하나다: *Rust 단일 실행 파일이 기존 Core 의 진실과 출력 계약을 바꾸지
//! 않고 MCP tool 을 낼 수 있는가.* 그래서 여기 있는 것은 **배선뿐**이다. 판정도 문장도 짓지
//! 않는다 — 그것은 이미 [`crate::where_now`] 가 한다.
//!
//! ```text
//! CLI   cwd 에서 조상 탐색 → ProjectSession ┐
//!                                          ├→ where_now() → 같은 글자
//! MCP   project_root 정확 열기 → ProjectSession ┘
//! ```
//!
//! **stdout 은 JSON-RPC 의 것이다.** 이 파일은 stdout 에 한 글자도 쓰지 않는다. 진단은 전부
//! stderr 로 간다. `print!`·`println!`·`dbg!` 가 여기 들어오면 그 순간 frame 이 깨진다.
//!
//! `ACTION_SURFACE` 는 **올리지 않는다.** 그 수는 Agent 가 부를 수 있는 **domain action 계약**의
//! 판이지 transport 나 CLI subcommand 목록의 판이 아니다. `gil_status` 라는 의미 동작은 이미
//! surface 1 에 있고, 이 조각은 그것에 문 하나를 더 낼 뿐 새 action 을 만들지 않는다.

use std::path::PathBuf;

use rmcp::handler::server::router::tool::ToolRouter;
use rmcp::handler::server::wrapper::Parameters;
use rmcp::model::{CallToolResult, ContentBlock};
use rmcp::{ServerHandler, ServiceExt, tool, tool_handler, tool_router};
use serde::{Deserialize, Serialize};

/// `gil_status` 가 받는 것 — Project 자리 하나뿐이다.
#[derive(Debug, Clone, Deserialize, Serialize, rmcp::schemars::JsonSchema)]
// derive 가 짓는 경로를 rmcp 가 다시 내보낸 그것으로 묶는다 — schemars 를 직접 의존하면
// 판이 어긋날 때 조용히 두 개가 링크된다.
#[schemars(crate = "rmcp::schemars")]
pub struct StatusArgs {
    /// 이 GIL Project 의 **절대경로**. 찾기 시작할 곳이 아니라 Project 그 자체다.
    pub project_root: String,
}

#[derive(Debug, Clone)]
pub struct GilServer {
    tool_router: ToolRouter<Self>,
}

impl Default for GilServer {
    fn default() -> Self {
        Self::new()
    }
}

impl GilServer {
    pub fn new() -> Self {
        Self {
            tool_router: Self::tool_router(),
        }
    }

    /// tool 하나가 하는 일 전부 — **부르는 쪽에 돌려줄 글자를 만든다.**
    ///
    /// 시험이 transport 없이 이 자리를 직접 부를 수 있게 떼어 두었다. 성패는 `Result` 하나로
    /// 가르고, 어느 쪽이든 **Core 가 한 말을 그대로** 나른다.
    pub fn status_said(root: &str) -> Result<String, String> {
        let rules = crate::RuleSet::builtin()
            .map_err(|err| format!("함께 실린 명세를 읽지 못했다: {err}"))?;
        // **cwd 를 읽지 않는다.** 받은 글자를 그대로 경로로 쓴다 — `PathBuf::from` 은
        // 정규화하지도 현재 자리에 붙이지도 않는다. 반쪽 경로는 아래에서 거절된다.
        let session = crate::open_project_root(rules, &PathBuf::from(root))
            .map_err(|err| err.to_string())?;
        // 기록은 준 자리에 있다 — 정확 경로로만 열었으므로 "다른 곳" 이라는 경우가 없다.
        Ok(crate::where_now(&session, false))
    }
}

#[tool_router(router = tool_router)]
impl GilServer {
    /// 지금 여정이 어디에 서 있는지 세 줄로 답한다.
    #[tool(
        name = "gil_status",
        description = "Answer where the journey stands right now, in three lines."
    )]
    pub async fn gil_status(&self, args: Parameters<StatusArgs>) -> CallToolResult {
        match Self::status_said(&args.0.project_root) {
            Ok(said) => CallToolResult::success(vec![ContentBlock::text(said)]),
            Err(said) => CallToolResult::error(vec![ContentBlock::text(said)]),
        }
    }

}

/// 자기가 무엇인지 **이 제품의 이름으로** 말한다. 기본값은 SDK 의 이름이라, 그대로 두면
/// Host 의 로그와 오류가 GIL 이 아니라 rmcp 를 가리킨다.
///
/// 판 번호가 **글자로 적혀 있다** — 이 macro 는 `env!` 를 받지 않는다. 그래서 진실이 둘이
/// 될 수 있는 자리이고, 아래 시험(`the_version_it_reports_is_the_crate_version`)이 그 둘을
/// 묶는다. Cargo.toml 이 오르면 이 줄도 올라야 하고, 잊으면 시험이 막는다.
#[tool_handler(router = self.tool_router, name = "gil", version = "0.1.0")]
impl ServerHandler for GilServer {}

/// stdin/stdout 에 서서 EOF 까지 답한다.
///
/// 돌아오는 것은 **사람에게 적을 말이 아니다** — 이 함수가 끝나는 자리는 프로세스의 끝이고,
/// stdout 은 이미 JSON-RPC 가 다 썼다. 그래서 오류만 문자열로 돌려주고, 부르는 쪽이 그것을
/// stderr 로 적는다.
pub fn serve_stdio() -> Result<(), String> {
    // stdin/stdout 은 blocking pool 위에서 돈다 — IO driver(=`net`)는 필요 없다. 다만
    // rmcp 가 요청 수명에 타이머를 쓰므로 시계는 켠다. 끄면 첫 요청에서 패닉한다.
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_time()
        .build()
        .map_err(|err| format!("MCP 실행기를 세우지 못했다: {err}"))?;

    runtime.block_on(async {
        let service = match GilServer::new().serve(rmcp::transport::stdio()).await {
            Ok(service) => service,
            // **손님이 말없이 떠난 것은 고장이 아니다.** Host 가 server 를 세워 두고
            // 초기화 없이 닫는 일은 흔하다 — 조용히 0 으로 끝낸다.
            Err(rmcp::service::ServerInitializeError::ConnectionClosed(_)) => return Ok(()),
            Err(err) => return Err(format!("MCP 연결을 세우지 못했다: {err}")),
        };
        // stdin 이 닫히면 여기서 깨끗이 돌아온다. `Closed`·`Cancelled` 는 **끝난 것**이지
        // 실패가 아니다. 매달려 기다리지 않는다.
        match service.waiting().await {
            Ok(_) => Ok(()),
            Err(err) => Err(format!("MCP 연결이 끊겼다: {err}")),
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// tool 은 **하나뿐이다.** 이 조각에서 표면이 늘어나면 시험이 막는다.
    #[test]
    fn exactly_one_tool_is_registered_and_it_is_gil_status() {
        let tools = GilServer::new().tool_router.list_all();
        let names: Vec<&str> = tools.iter().map(|one| one.name.as_ref()).collect();
        assert_eq!(names, vec!["gil_status"], "tool 표면이 하나가 아니다");
    }

    #[test]
    fn the_tool_asks_for_a_project_root() {
        let tools = GilServer::new().tool_router.list_all();
        let schema = serde_json::to_string(&tools[0].input_schema).expect("schema");
        assert!(schema.contains("project_root"), "{schema}");
    }

    /// 판 번호를 두 자리에 적었으므로 **두 자리가 같다는 것**을 시험이 지킨다.
    #[test]
    fn the_version_it_reports_is_the_crate_version() {
        let info = GilServer::new().get_info();
        assert_eq!(info.server_info.name, "gil");
        assert_eq!(
            info.server_info.version,
            env!("CARGO_PKG_VERSION"),
            "Cargo.toml 의 판과 MCP 가 말하는 판이 갈렸다"
        );
    }

    #[test]
    fn a_relative_project_root_is_refused() {
        let said = GilServer::status_said("some/where").unwrap_err();
        assert_eq!(said, crate::RootError::NotAbsolute.to_string());
        assert!(!said.contains('/'), "거절문에 경로가 새어 나왔다");
    }

    #[test]
    fn a_place_without_a_project_is_refused() {
        let at = std::env::temp_dir().join(format!("gil-mcp-empty-{}", std::process::id()));
        std::fs::create_dir_all(&at).expect("자리");
        let said = GilServer::status_said(at.to_str().expect("utf-8")).unwrap_err();
        assert_eq!(said, crate::RootError::NoProjectHere.to_string());
        std::fs::remove_dir_all(&at).ok();
    }
}
