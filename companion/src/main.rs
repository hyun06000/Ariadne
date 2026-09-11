//! **GIL Companion** — 계속 떠 있는 읽기 전용 창 하나.
//!
//! # 이 crate 가 하는 일의 전부
//!
//! 창을 열고, 그 안에 공용 UI bundle(`../ui`)을 싣고, 사람이 닫을 때까지 산다. Host UI
//! Model §9.1 이 정한 adapter 의 책임 중 이 조각이 지는 것은 **수명과 packaging** 뿐이다.
//!
//! ```text
//! Tauri        창을 열고 bundle 을 싣는다            ← 이 파일
//! 공용 bundle   DAG · Project switcher · detail      ← ../ui (정본)
//! fixture host  canonical MonitorViewV1 JSON 을 건넨다 ← ../ui/host.js
//! ```
//!
//! # 하지 않는 일
//!
//! Graph 의미도, Cycle 관계도, 요약도, 현재 위치도 여기서 계산하지 않는다. `.gil` 을 읽지도
//! 쓰지도 않는다. **server 도 port 도 capability URL 도 없다** — bundle 은 창 안에서 제
//! 자리의 파일을 읽을 뿐이다.
//!
//! # 아직 없는 것
//!
//! 실제 `.gil` Project 연결과 watcher 는 다음 조각이다. 그때 이 파일에 `invoke` 명령
//! 몇 개가 생기고, `../ui/host.js` 가 그것을 부르는 판으로 바뀐다. **공용 bundle 자체는
//! 그때도 Tauri 를 모른다** — 문의 이름(`window.GIL_HOST`)이 같기 때문이다.

fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("GIL Companion 창을 열지 못했다");
}
