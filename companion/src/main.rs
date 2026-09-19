//! **GIL Companion** — 계속 떠 있는 읽기 전용 창 하나.
//!
//! # 이 crate 가 하는 일의 전부
//!
//! 창을 열고, 그 안에 공용 UI bundle(`../ui`)을 싣고, 사람이 고른 실제 GIL Project 를
//! **읽어서** 건넨다. 껐다 켜도 이어지도록 이 창의 사정을 앱 전용 설정에 적고, 창을 숨겨도
//! menu bar 에서 다시 찾을 수 있게 한다.
//!
//! ```text
//! Tauri          창 하나의 수명                          ← 이 파일
//! lifetime       숨기기 · 다시 열기 · 끝내기의 단 하나의 문  ← lifetime.rs
//! window         창을 세우고 그 자리를 기억한다             ← window.rs
//! tray           숨은 Companion 을 사람이 찾는 자리         ← tray.rs
//! autostart      로그인 시 시작 (기본 꺼짐)                ← autostart.rs
//! read adapter   고른 Project → MonitorViewV1 · 상세      ← adapter.rs (§9.1.1)
//! settings       등록 목록 · 마지막 선택 · 창의 자리        ← settings.rs (§9.1.2)
//! geometry       그 자리를 지금 화면 안으로                ← geometry.rs
//! Tauri 판 문     그 모두를 `window.GIL_HOST` 로 잇는다     ← host.js (주입)
//! 공용 bundle     DAG · Project switcher · detail         ← ../ui (정본)
//! ```
//!
//! # 하지 않는 일
//!
//! Graph 의미도, Cycle 관계도, 요약도, 현재 위치도 여기서 계산하지 않는다. `.gil/state.yaml`
//! 을 열지도 해석하지도 않는다. **server 도 port 도 capability URL 도 browser 도 없다.**
//! 그리고 Project 의 무엇도 쓰지 않는다 — 설정 파일 하나만 적는다.
//!
//! # 창은 닫혀도 죽지 않는다
//!
//! 빨간 버튼은 창을 **숨긴다**. 끝내는 것은 `⌘Q` 와 tray 의 종료뿐이다. 그래서 사람이 창을
//! 닫아도 Agent 가 「GIL 열어줘」라고 했을 때 **있던 창**이 앞으로 나온다 — 새 창도, 새
//! process 도, 새 server 도 만들지 않는다(§9.1).
//!
//! # 시작할 때의 차례
//!
//! ```text
//! 1. single-instance 가 먼저 선다        ← 둘째 실행은 여기서 끝난다
//! 2. 설정을 읽는다                       ← 파일 하나
//! 3. 등록부를 되살린다                    ← 자리를 펴서 주소만 다시 계산. Graph 는 안 읽는다
//! 4. 창의 자리를 지금 화면에 맞춰 연다
//! 5. tray 를 세운다
//! 6. 화면이 마지막 선택 **하나**를 읽는다   ← foreground read 는 여기 한 번뿐
//! ```

mod adapter;
mod appmenu;
mod autostart;
mod geometry;
mod handshake;
mod lifetime;
mod live;
mod settings;
mod tray;
mod window;

use tauri::Manager;

fn main() {
    // 설치 판정은 창을 띄우거나 Project를 읽기 전에 끝난다. launcher가 이 문으로
    // identity·protocol·wire 호환성을 확인한다.
    if let Some(answered) = handshake::answer_cli(std::env::args_os()) {
        match answered {
            Ok(said) => println!("{said}"),
            Err(said) => {
                eprintln!("{said}");
                std::process::exit(2);
            }
        }
        return;
    }

    tauri::Builder::default()
        // **가장 먼저 선다.** plugin 의 setup 은 등록 차례대로 돌고, 이미 창이 하나 떠
        // 있으면 이 plugin 이 그 자리에서 프로세스를 끝낸다. 그래서 둘째 실행은 `Desk` 도
        // 창도 만들지 못한다 — 설정을 적는 것은 **살아 있는 창 하나**뿐이다.
        .plugin(tauri_plugin_single_instance::init(Box::new(
            |app: &tauri::AppHandle, _argv: Vec<String>, _cwd: String| {
                // 둘째 실행이 하는 일은 **있던 창을 앞으로 데려오는 것**뿐이다. 숨어 있든
                // 최소화돼 있든 같은 문을 지난다. 인수도 cwd 도 보지 않는다 — 그것으로
                // Project 를 짐작하면 사람이 고르지 않은 것을 열게 된다(§9.1.1-1).
                let _ = lifetime::show_main_window(app);
            },
        )))
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .plugin(tauri_plugin_dialog::init())
        .manage(adapter::Registry::default())
        .manage(window::LastSeen::default())
        .manage(live::Live::default())
        .invoke_handler(tauri::generate_handler![
            adapter::pick_project,
            adapter::list_projects,
            adapter::load_view,
            adapter::load_detail,
            adapter::opening,
            adapter::forget_project,
            adapter::show_window,
        ])
        .setup(|app| {
            let handle = app.handle().clone();

            // 실행 중인 process만 답할 수 있는 challenge 문. 포트도 URL도 없고, 사용자 전용
            // local IPC 하나만 앱 수명 동안 연다.
            app.manage(handshake::RuntimeHandshake::start()?);

            // ① 설정을 읽는다. 읽지 못하면 **원본을 그대로 두고** 임시 상태로 선다.
            let dir = app.path().app_config_dir()?;
            let desk = settings::Desk::open(dir);

            // ② 등록부를 되살린다 — 자리를 펴서 주소만 다시 센다. Graph 는 읽지 않는다.
            let saved = desk.read(|one| one.projects.clone());
            adapter::restore_registry(app.state::<adapter::Registry>().inner(), &saved);
            app.manage(desk);

            // ③ 메뉴. `⌘W` 는 숨기고 `⌘Q` 는 끝낸다 — 각자 제 문으로 간다.
            app.set_menu(appmenu::build(&handle)?)?;

            // ④ 창. 자리와 최대화는 `window::build` 가 설정에서 읽는다.
            window::build(&handle)?;

            // ⑤ menu bar. 세우지 못해도 창과 Agent launcher 는 그대로 동작해야 하므로
            //    앱의 실패로 삼지 않는다.
            let on = autostart::enabled(&handle).unwrap_or(false);
            if let Err(err) = tray::install(&handle, on) {
                eprintln!("menu bar 자리를 만들지 못했다 — 창은 그대로 씁니다: {err}");
            }
            Ok(())
        })
        .on_menu_event(appmenu::on_menu)
        .build(tauri::generate_context!())
        .expect("GIL Companion 을 세우지 못했다")
        .run(|app, event| match event {
            // macOS: Dock 아이콘을 다시 눌렀다. **있던 창**을 보여 준다.
            #[cfg(target_os = "macos")]
            tauri::RunEvent::Reopen { .. } => {
                let _ = lifetime::show_main_window(app);
            }
            // 창을 다 닫아도 끝나지 않는다 — menu bar 에 남아 있어야 한다.
            tauri::RunEvent::ExitRequested { api, .. } => {
                if !lifetime::is_leaving() {
                    api.prevent_exit();
                }
            }
            // 정말 끝나기 직전. 지켜보던 것을 멈추고 미뤄 둔 마지막 자리를 거둔다.
            tauri::RunEvent::Exit => {
                app.state::<handshake::RuntimeHandshake>().stop();
                app.state::<live::Live>().stop();
                window::flush_now(app);
            }
            _ => {}
        });
}
