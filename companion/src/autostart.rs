//! **로그인 시 시작** — 사람이 명시적으로 켜는 것.
//!
//! 기본은 꺼짐이다. 켜면 OS 의 정식 자동 시작 자리에 등록한다 — macOS 는 Login Item,
//! Windows 는 레지스트리의 Run 키다. shell profile 을 고치거나 LaunchAgent plist 를 손으로
//! 조립하는 우회는 하지 않는다. 그런 우회는 앱을 지워도 남고, 사람이 OS 의 설정 화면에서
//! 껐을 때 그 사실을 알 수 없다.
//!
//! # 조용히 성공하지 않는다
//!
//! 사람의 뜻(`설정의 값`)과 OS 의 실제 등록 상태가 어긋날 수 있다 — 권한이 없거나, 사람이
//! OS 설정에서 직접 껐거나, 이 판이 지원하지 않는 자리일 수 있다. 그래서 켜고 끈 **뒤에**
//! 실제 상태를 다시 물어 그것을 표시한다.

use tauri::AppHandle;
use tauri_plugin_autostart::ManagerExt;

/// OS 가 말하는 지금의 등록 상태. 모르면 `None` — 「아니오」로 가장하지 않는다.
pub fn enabled(app: &AppHandle) -> Option<bool> {
    app.autolaunch().is_enabled().ok()
}

/// 사람이 tray 에서 켜고 껐다.
///
/// 지금 상태의 **반대**로 만들고, 그 뒤에 OS 에 다시 물어 표시를 맞춘다. 뜻과 실제가
/// 어긋나면 tray 의 check 는 **실제**를 보여 준다 — 사람이 껐다고 믿는데 켜져 있는 것이
/// 가장 나쁜 결과이기 때문이다.
pub fn toggle(app: &AppHandle) {
    let want = !enabled(app).unwrap_or(false);
    let manager = app.autolaunch();
    let asked = if want { manager.enable() } else { manager.disable() };

    let real = enabled(app);
    match (asked, real) {
        (Ok(()), Some(now)) if now == want => crate::tray::say_autostart(app, now),
        // 청했지만 그렇게 되지 않았다. **성공으로 보이지 않게** 실제 상태를 그린다.
        (_, Some(now)) => {
            crate::tray::say_autostart(app, now);
            crate::window::tell(app, "autostart_mismatch", &autostart_said(want, Some(now)));
        }
        (_, None) => {
            crate::tray::say_autostart(app, false);
            crate::window::tell(app, "autostart_unknown", &autostart_said(want, None));
        }
    }
}

fn autostart_said(want: bool, real: Option<bool>) -> String {
    let wanted = if want { "켜기" } else { "끄기" };
    match real {
        Some(true) => format!("로그인 시 시작을 {wanted}로 바꾸지 못했다 — 지금은 켜져 있다"),
        Some(false) => format!("로그인 시 시작을 {wanted}로 바꾸지 못했다 — 지금은 꺼져 있다"),
        None => "로그인 시 시작의 상태를 OS 에 물어보지 못했다".to_string(),
    }
}

#[cfg(test)]
mod tests {
    /// 주석을 걷어낸, **실제로 도는 코드**만.
    ///
    /// 줄 **맨 앞**의 `//` 만 지운다. 글자 가운데의 `//` 를 지우면 `"gil://refresh"` 같은
    /// 이름이 반토막 난다 — 실측으로 걸린 자리다.
    fn running(source: &str) -> String {
        let body = source.split_once("#[cfg(test)]").map(|(one, _)| one).unwrap_or(source);
        body.lines()
            .filter(|line| !line.trim_start().starts_with("//"))
            .collect::<Vec<_>>()
            .join("\n")
    }

    /// `marker` 부터 최대 `chars` 글자. **글자 경계에서 자른다** — 한글 한 자가 세 바이트라
    /// 바이트로 자르면 한가운데가 잘려 터진다(실측).
    fn after<'a>(code: &'a str, marker: &str) -> &'a str {
        let at = code.find(marker).unwrap_or_else(|| panic!("{marker} 를 찾지 못했다"));
        &code[at..]
    }

    /// 그 함수의 **본문만** — 다음 함수까지 읽어 엉뚱한 곳에서 걸리지 않게.
    fn body_of<'a>(code: &'a str, marker: &str) -> &'a str {
        let rest = after(code, marker);
        &rest[..rest.find("\n}").map(|at| at + 2).unwrap_or(rest.len())]
    }

    /// **OS 의 정식 자리만 쓴다** — 우회로 조립하지 않는다.
    #[test]
    fn autostart_uses_the_official_seat_and_never_hand_builds_one() {
        let code = running(include_str!("autostart.rs"));
        assert!(code.contains("autolaunch()"), "정식 문을 쓰지 않는다");
        for forbidden in [
            "LaunchAgents", "plist", "crontab", ".zshrc", ".bash_profile",
            "launchctl", "Run\\\\", "Startup",
        ] {
            assert!(!code.contains(forbidden), "자동 시작을 {forbidden} 로 우회한다");
        }
    }

    /// **조용히 성공하지 않는다.**
    ///
    /// 사람의 뜻과 OS 의 실제 상태가 어긋나면 표시는 **실제**를 따르고, 어긋났다는 사실을
    /// 창에 알린다. 껐다고 믿는데 켜져 있는 것이 가장 나쁜 결과다.
    #[test]
    fn a_failed_toggle_is_never_painted_as_success() {
        let code = running(include_str!("autostart.rs"));
        let body = body_of(&code, "pub fn toggle");
        // 청한 뒤에 **다시 묻는다.**
        let asked = body.find("enable()").expect("켜는 자리");
        let again = body.find("let real").expect("다시 묻는 자리");
        assert!(asked < again, "청하기 전에 상태를 읽는다");
        // 어긋나면 알린다.
        assert!(body.contains("mismatch") || body.contains("tell("), "어긋남을 알리지 않는다");
        assert!(body.contains("say_autostart"), "표시를 실제에 맞추지 않는다");
        // 모를 때 「아니오」로 가장하지 않는다.
        // **그 함수의 본문만** 본다. 넉넉히 자르면 다음 함수까지 읽어 엉뚱한 곳에서 걸린다.
        let asking = body_of(&code, "pub fn enabled");
        assert!(asking.contains("Option<bool>"), "모름을 표현하지 않는다");
        assert!(!asking.contains("unwrap_or(false)"), "모름을 아니오로 가장한다");
    }

    /// 켤 때도 **모든 Project 를 관측하지 않는다.**
    #[test]
    fn starting_at_login_observes_no_project() {
        let code = running(include_str!("autostart.rs"));
        for forbidden in ["view_of(", "detail_of(", "ProjectSession", "restore_registry"] {
            assert!(!code.contains(forbidden), "자동 시작이 {forbidden} 를 만진다");
        }
        // 그리고 시작 차례에 Graph 를 읽는 자리가 없다 — 마지막 하나는 **화면**이 읽는다.
        let main = running(include_str!("main.rs"));
        let at = main.find("fn main").expect("main");
        for forbidden in ["view_of(", "detail_of(", "monitor_view_v1"] {
            assert!(!main[at..].contains(forbidden), "시작이 {forbidden} 로 Project 를 읽는다");
        }
    }
}
