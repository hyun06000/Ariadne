//! **Companion 의 설정** — Project 의 사실이 아니라 이 창의 사정.
//!
//! Host UI Model §9.1.2 가 정한 것을 그대로 옮긴다. 여기 담기는 것은 **어느 Project 를
//! 등록해 두었고, 마지막으로 무엇을 보고 있었고, 창이 어디에 있었는가** 셋뿐이다.
//!
//! # 여기 담지 않는 것
//!
//! `MonitorViewV1` · `NodeDetailV1` · Step 선택 · Cycle 접힘 · scroll · 열린 상세 ·
//! Graph · Journey · Memory · Will · watcher 상태. 앞의 넷은 **창이 사는 동안의 임시
//! 상태**이고, 뒤의 것들은 애초에 Project 의 사실이라 `.gil` 이 지닌다.
//!
//! # 왜 Tauri 를 모르는가
//!
//! 이 파일은 폴더 하나를 받아 그 안의 파일을 읽고 쓴다. 앱이 어느 폴더를 주는지는 부르는
//! 쪽이 정한다 — 그래서 시험이 임시 폴더를 건네 실제 설정을 건드리지 않고 잴 수 있다.
//!
//! # 손상된 설정을 덮어쓰지 않는다
//!
//! 읽지 못한 설정을 「빈 설정」으로 가장하면, 사람이 등록해 둔 목록이 조용히 사라진다.
//! 그래서 읽지 못하면 **원본을 그대로 두고** 이번 실행만 아무것도 적지 않는 상태로 연다.

use std::io::Write;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::geometry::Geometry;

/// 이 판이 아는 설정의 판. 모르는 판은 **읽지 않고 덮어쓰지도 않는다.**
pub const SCHEMA_VERSION: u32 = 1;

/// 설정 파일의 이름. 앱 전용 폴더 안에 이것 하나만 둔다.
pub const FILE_NAME: &str = "companion-settings.json";

/// 등록해 둔 Project 하나.
///
/// `root` 는 **native adapter 안에서만** 쓰는 비공개 위치다. 화면으로 나가지 않는다(§9.1.2).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SavedProject {
    pub root: PathBuf,
    pub scope_id: String,
    pub label: String,
}

/// 이 창의 사정 전부.
///
/// `projects` 의 **차례가 곧 last-used order** 다 — 앞이 가장 최근이다. 따로 시각을 적지
/// 않는 이유는, 시각을 적으면 「언제」와 「몇 번째」가 어긋날 수 있고 우리에게 필요한 것은
/// 차례뿐이기 때문이다.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CompanionSettings {
    pub schema_version: u32,
    #[serde(default)]
    pub projects: Vec<SavedProject>,
    /// 마지막으로 **View 를 성공적으로 읽은** scope. 열지 못한 것은 여기 오지 않는다.
    #[serde(default)]
    pub last_selected: Option<String>,
    #[serde(default)]
    pub window: Geometry,
}

impl Default for CompanionSettings {
    fn default() -> CompanionSettings {
        CompanionSettings {
            schema_version: SCHEMA_VERSION,
            projects: Vec::new(),
            last_selected: None,
            window: Geometry::default(),
        }
    }
}

impl CompanionSettings {
    /// 이 Project 를 목록 맨 앞으로 — **가장 최근에 쓴 것**이 된다.
    pub fn touch(&mut self, scope_id: &str, root: &Path, label: &str) {
        self.projects.retain(|one| one.scope_id != scope_id);
        self.projects.insert(
            0,
            SavedProject {
                root: root.to_path_buf(),
                scope_id: scope_id.to_string(),
                label: label.to_string(),
            },
        );
    }

    /// 목록에서 지운다. **Project 파일은 건드리지 않는다** — 여기 있는 것은 이름뿐이다.
    pub fn forget(&mut self, scope_id: &str) -> bool {
        let before = self.projects.len();
        self.projects.retain(|one| one.scope_id != scope_id);
        if self.last_selected.as_deref() == Some(scope_id) {
            // **다른 Project 를 추측하지 않는다.** 빈 선택으로 간다(§9.1.2).
            self.last_selected = None;
        }
        self.projects.len() != before
    }
}

/// 설정을 읽지 못한 이유 — 종류를 잃지 않는다.
#[derive(Debug, Clone, PartialEq)]
pub enum SettingsRefusal {
    /// 이 Companion 이 모르는 판이다. 앞으로 나온 판일 수도 있다.
    UnsupportedSchema { found: u32, known: u32 },
    /// 글자가 설정의 모양이 아니다.
    Damaged { said: String },
    /// 파일을 읽지 못했다 — 권한이나 자리의 문제다.
    Unreadable { said: String },
}

impl SettingsRefusal {
    /// UI 가 갈래를 정하는 낱말.
    pub fn code(&self) -> &'static str {
        match self {
            SettingsRefusal::UnsupportedSchema { .. } => "settings_unsupported",
            SettingsRefusal::Damaged { .. } => "settings_damaged",
            SettingsRefusal::Unreadable { .. } => "settings_unreadable",
        }
    }

    /// 사람에게 보일 한 줄. **경로를 담지 않는다**(§9.1.2).
    pub fn said(&self) -> String {
        match self {
            SettingsRefusal::UnsupportedSchema { found, known } => format!(
                "이 Companion 이 모르는 설정 판이다 (설정 v{found} · 아는 판 v{known}) — \
                 원본을 그대로 두고 이번 실행은 저장하지 않는다"
            ),
            SettingsRefusal::Damaged { .. } => {
                "설정 파일을 읽었지만 설정의 모양이 아니다 — 원본을 그대로 두고 \
                 이번 실행은 저장하지 않는다"
                    .to_string()
            }
            SettingsRefusal::Unreadable { .. } => {
                "설정 파일을 읽지 못했다 — 원본을 그대로 두고 이번 실행은 저장하지 않는다"
                    .to_string()
            }
        }
    }
}

/// 설정을 적는 일이 실패한 이유.
#[derive(Debug, Clone, PartialEq)]
pub enum SaveError {
    Io { said: String },
}

/// 설정 파일 하나를 지키는 자리.
///
/// 폴더를 밖에서 받는다 — 앱은 OS 가 준 app-config 폴더를, 시험은 임시 폴더를 건넨다.
pub struct Store {
    dir: PathBuf,
}

impl Store {
    pub fn at(dir: impl Into<PathBuf>) -> Store {
        Store { dir: dir.into() }
    }

    pub fn path(&self) -> PathBuf {
        self.dir.join(FILE_NAME)
    }

    /// 저장된 설정. 아직 없으면 `None` — **잘못이 아니라 첫 실행이다.**
    pub fn load(&self) -> Result<Option<CompanionSettings>, SettingsRefusal> {
        let said = match std::fs::read_to_string(self.path()) {
            Ok(said) => said,
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(err) => {
                return Err(SettingsRefusal::Unreadable { said: err.to_string() });
            }
        };
        // **판을 먼저 본다.** 모르는 판을 우리 모양으로 읽으려다 칸을 잃으면, 그것이 곧
        // 조용한 덮어쓰기가 된다.
        let seen: serde_json::Value = serde_json::from_str(&said)
            .map_err(|err| SettingsRefusal::Damaged { said: err.to_string() })?;
        let found = seen.get("schema_version").and_then(|one| one.as_u64());
        match found {
            Some(found) if found as u32 == SCHEMA_VERSION => {}
            Some(found) => {
                return Err(SettingsRefusal::UnsupportedSchema {
                    found: found as u32,
                    known: SCHEMA_VERSION,
                });
            }
            None => {
                return Err(SettingsRefusal::Damaged {
                    said: "판 번호가 없다".to_string(),
                });
            }
        }
        serde_json::from_value(seen)
            .map(Some)
            .map_err(|err| SettingsRefusal::Damaged { said: err.to_string() })
    }

    /// **통째로 새로 적고 제자리로 옮긴다.**
    ///
    /// ```text
    ///   1. 옆자리 임시 파일에 완전한 내용을 적는다
    ///   2. 그 파일을 동기화한다        ← 여기까지 해야 바이트가 정말 디스크에 있다
    ///   3. 제자리로 rename 한다        ← 원자적이다. 반쯤 쓰인 설정이 남지 않는다
    ///   4. 폴더를 동기화한다           ← rename 자체가 살아남게
    /// ```
    ///
    /// 1·2 에서 죽으면 **옛 설정이 그대로** 있고 임시 파일만 남는다. 어느 실패 경로에서도
    /// Project 파일은 만지지 않는다 — 이 함수는 제 폴더 밖을 모른다.
    pub fn save(&self, settings: &CompanionSettings) -> Result<(), SaveError> {
        let fail = |err: std::io::Error| SaveError::Io { said: err.to_string() };
        std::fs::create_dir_all(&self.dir).map_err(fail)?;

        let said = serde_json::to_string_pretty(settings)
            .map_err(|err| SaveError::Io { said: err.to_string() })?;
        // 이름에 pid 를 넣는다 — 두 실행이 같은 임시 파일을 두고 다투지 않게.
        let beside = self.dir.join(format!(".{FILE_NAME}.{}.tmp", std::process::id()));

        let write = || -> std::io::Result<()> {
            let mut file = std::fs::File::create(&beside)?;
            file.write_all(said.as_bytes())?;
            file.write_all(b"\n")?;
            file.sync_all()?;
            Ok(())
        };
        if let Err(err) = write() {
            let _ = std::fs::remove_file(&beside);
            return Err(fail(err));
        }
        if let Err(err) = std::fs::rename(&beside, self.path()) {
            let _ = std::fs::remove_file(&beside);
            return Err(fail(err));
        }
        // 폴더까지 동기화해야 rename 이 살아남는다. 못 해도 설정 자체는 제자리에 있다.
        if let Ok(dir) = std::fs::File::open(&self.dir) {
            let _ = dir.sync_all();
        }
        Ok(())
    }
}

/// 이번 실행이 설정을 다루는 방식.
///
/// 읽지 못한 설정 위에서는 **아무것도 적지 않는다**. 그래야 사람이 등록해 둔 목록이 조용히
/// 사라지지 않는다(§9.1.2).
pub struct Desk {
    store: Store,
    settings: std::sync::Mutex<CompanionSettings>,
    /// `Some` 이면 이번 실행은 **저장하지 않는 임시 상태**다.
    refused: Option<SettingsRefusal>,
}

impl Desk {
    /// 폴더를 열어 설정을 읽는다. 읽지 못하면 임시 상태로 선다.
    pub fn open(dir: impl Into<PathBuf>) -> Desk {
        let store = Store::at(dir);
        match store.load() {
            Ok(Some(settings)) => Desk { store, settings: settings.into(), refused: None },
            Ok(None) => Desk {
                store,
                settings: CompanionSettings::default().into(),
                refused: None,
            },
            Err(refusal) => Desk {
                store,
                // 화면은 빈 목록으로 서되, **원본은 건드리지 않는다.**
                settings: CompanionSettings::default().into(),
                refused: Some(refusal),
            },
        }
    }

    pub fn refusal(&self) -> Option<&SettingsRefusal> {
        self.refused.as_ref()
    }

    /// 이번 실행이 설정을 적을 수 있는가.
    pub fn persists(&self) -> bool {
        self.refused.is_none()
    }

    /// 지금 설정을 들여다본다 — **잠금은 이 한 줄 안에서만 산다.**
    pub fn read<T>(&self, look: impl FnOnce(&CompanionSettings) -> T) -> T {
        look(&self.settings.lock().expect("설정"))
    }

    /// 바꾸고 **곧바로 적는다.** 임시 상태면 바꾸기만 하고 적지 않는다.
    pub fn change(&self, edit: impl FnOnce(&mut CompanionSettings)) -> Result<(), SaveError> {
        let copy = {
            let mut settings = self.settings.lock().expect("설정");
            edit(&mut settings);
            settings.clone()
        };
        if !self.persists() {
            return Ok(());
        }
        self.store.save(&copy)
    }

    /// 지금 값을 그대로 다시 적는다 — 닫기 전에 마지막 값을 눕히는 자리.
    pub fn flush(&self) -> Result<(), SaveError> {
        self.change(|_| {})
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    use std::collections::BTreeSet;

    /// 설정에 **사실이 섞여 들어오지 않았는가.**
    ///
    /// 사람이 칸을 하나 더 만드는 순간을 잡으려고 둔다. 아래 이름 말고는 설정이 될 수 없다.
    ///
    /// 글자를 훑어 금지어를 찾지 않는다 — `last_selected` 안에 `selected` 가 들어 있듯, 낱말은
    /// 서로를 품는다. **칸 이름 전부를 허용 목록과 견주는 것**만이 정확하다.
    pub fn only_settings_keys(said: &str) -> Result<(), String> {
        const ALLOWED: &[&str] = &[
            // 최상위
            "schema_version", "projects", "last_selected", "window",
            // 등록한 Project 하나
            "root", "scope_id", "label",
            // 창의 자리
            "position", "size", "maximized",
        ];
        let allowed: BTreeSet<&str> = ALLOWED.iter().copied().collect();

        fn walk(at: &serde_json::Value, allowed: &BTreeSet<&str>) -> Result<(), String> {
            match at {
                serde_json::Value::Object(fields) => {
                    for (name, value) in fields {
                        if !allowed.contains(name.as_str()) {
                            return Err(format!("설정에 모르는 칸 {name:?} 이 있다"));
                        }
                        walk(value, allowed)?;
                    }
                    Ok(())
                }
                serde_json::Value::Array(items) => {
                    for one in items {
                        walk(one, allowed)?;
                    }
                    Ok(())
                }
                _ => Ok(()),
            }
        }

        let seen: serde_json::Value = serde_json::from_str(said).map_err(|err| err.to_string())?;
        if !seen.is_object() {
            return Err("설정이 객체가 아니다".to_string());
        }
        walk(&seen, &allowed)
    }

    fn scratch(label: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("gil-settings-{label}"));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).expect("자리를 만든다");
        dir
    }

    #[test]
    fn an_empty_config_directory_is_a_first_run_not_a_failure() {
        let store = Store::at(scratch("first-run"));
        assert_eq!(store.load().expect("첫 실행은 잘못이 아니다"), None);
    }

    #[test]
    fn what_was_saved_comes_back_exactly() {
        let store = Store::at(scratch("round-trip"));
        let mut settings = CompanionSettings::default();
        settings.touch("project:aaa", Path::new("/tmp/하나"), "하나");
        settings.touch("project:bbb", Path::new("/tmp/둘"), "둘");
        settings.last_selected = Some("project:bbb".to_string());
        settings.window = Geometry {
            position: Some([120.0, 80.0]),
            size: [640.0, 960.0],
            maximized: true,
        };

        store.save(&settings).expect("적는다");
        assert_eq!(store.load().expect("읽는다"), Some(settings));
    }

    #[test]
    fn the_most_recent_project_sits_at_the_front() {
        let mut settings = CompanionSettings::default();
        settings.touch("project:a", Path::new("/tmp/a"), "a");
        settings.touch("project:b", Path::new("/tmp/b"), "b");
        settings.touch("project:c", Path::new("/tmp/c"), "c");
        // 다시 쓴 것이 맨 앞으로 온다 — 칸이 늘지 않는다.
        settings.touch("project:a", Path::new("/tmp/a"), "a");

        let order: Vec<&str> = settings.projects.iter().map(|one| one.scope_id.as_str()).collect();
        assert_eq!(order, ["project:a", "project:c", "project:b"]);
        assert_eq!(settings.projects.len(), 3, "같은 Project 가 두 칸이 되었다");
    }

    #[test]
    fn forgetting_the_current_project_leaves_an_empty_selection() {
        let mut settings = CompanionSettings::default();
        settings.touch("project:a", Path::new("/tmp/a"), "a");
        settings.touch("project:b", Path::new("/tmp/b"), "b");
        settings.last_selected = Some("project:b".to_string());

        assert!(settings.forget("project:b"), "지우지 못했다");
        assert_eq!(settings.projects.len(), 1);
        // **다른 Project 를 추측하지 않는다.**
        assert_eq!(settings.last_selected, None, "남은 Project 를 골라 버렸다");
        assert!(!settings.forget("project:없음"), "없는 것을 지웠다고 답했다");
    }

    #[test]
    fn forgetting_another_project_leaves_the_selection_alone() {
        let mut settings = CompanionSettings::default();
        settings.touch("project:a", Path::new("/tmp/a"), "a");
        settings.touch("project:b", Path::new("/tmp/b"), "b");
        settings.last_selected = Some("project:b".to_string());
        settings.forget("project:a");
        assert_eq!(settings.last_selected.as_deref(), Some("project:b"));
    }

    // ── 손상과 미지원 ──────────────────────────────────────────────

    #[test]
    fn a_newer_schema_is_refused_and_left_untouched() {
        let dir = scratch("newer");
        let store = Store::at(&dir);
        let original = r#"{"schema_version":99,"projects":[],"last_selected":null}"#;
        std::fs::write(store.path(), original).expect("적는다");

        match store.load().expect_err("모르는 판이다") {
            SettingsRefusal::UnsupportedSchema { found, known } => {
                assert_eq!((found, known), (99, SCHEMA_VERSION));
            }
            other => panic!("다른 거절이 나왔다: {other:?}"),
        }

        // **원본이 그대로다.** 그리고 이번 실행은 아무것도 적지 않는다.
        let desk = Desk::open(&dir);
        assert!(!desk.persists(), "임시 상태가 아니다");
        desk.change(|settings| settings.touch("project:새것", Path::new("/tmp/새것"), "새것"))
            .expect("임시 상태에서는 조용히 넘어간다");
        assert_eq!(
            std::fs::read_to_string(store.path()).expect("읽는다"),
            original,
            "모르는 판을 덮어썼다"
        );
    }

    #[test]
    fn a_damaged_file_is_refused_and_left_untouched() {
        let dir = scratch("damaged");
        let store = Store::at(&dir);
        let original = "이건 JSON 이 아니다 {{{";
        std::fs::write(store.path(), original).expect("적는다");

        assert!(matches!(store.load(), Err(SettingsRefusal::Damaged { .. })));
        let desk = Desk::open(&dir);
        assert!(!desk.persists());
        assert_eq!(desk.refusal().expect("거절").code(), "settings_damaged");
        desk.flush().expect("임시 상태");
        assert_eq!(
            std::fs::read_to_string(store.path()).expect("읽는다"),
            original,
            "손상된 설정을 덮어썼다"
        );
    }

    #[test]
    fn a_file_without_a_schema_number_is_damaged_not_empty() {
        let dir = scratch("no-version");
        let store = Store::at(&dir);
        std::fs::write(store.path(), r#"{"projects":[]}"#).expect("적는다");
        assert!(matches!(store.load(), Err(SettingsRefusal::Damaged { .. })));
    }

    #[test]
    fn a_refusal_says_what_happened_without_naming_a_path() {
        for refusal in [
            SettingsRefusal::UnsupportedSchema { found: 9, known: 1 },
            SettingsRefusal::Damaged { said: "/tmp/어딘가/파일".to_string() },
            SettingsRefusal::Unreadable { said: "/tmp/어딘가/파일".to_string() },
        ] {
            let said = refusal.said();
            assert!(!said.is_empty(), "할 말이 없다");
            assert!(!said.contains('/'), "거절에 자리가 실렸다: {said}");
            assert!(said.contains("저장하지 않는다"), "임시 상태임을 말하지 않았다: {said}");
        }
    }

    // ── 통째로 적고 제자리로 옮긴다 ────────────────────────────────

    #[test]
    fn a_failed_save_leaves_the_last_good_settings_in_place() {
        let dir = scratch("atomic");
        let store = Store::at(&dir);
        let mut good = CompanionSettings::default();
        good.touch("project:지켜야할것", Path::new("/tmp/지켜야할것"), "지켜야 할 것");
        store.save(&good).expect("좋은 설정을 적는다");
        let bytes = std::fs::read(store.path()).expect("읽는다");

        // 옮길 자리를 **폴더로** 막아 rename 을 실패시킨다.
        let blocked = Store::at(dir.join("막힌자리"));
        std::fs::create_dir_all(blocked.path()).expect("자리를 막는다");
        let refused = blocked.save(&CompanionSettings::default());
        assert!(refused.is_err(), "막힌 자리에 적혔다고 답했다");

        // **좋은 설정이 그대로다.**
        assert_eq!(std::fs::read(store.path()).expect("읽는다"), bytes, "옛 설정이 상했다");
        assert_eq!(store.load().expect("읽는다"), Some(good));
        // 임시 파일이 남지 않았다.
        let leftovers: Vec<_> = std::fs::read_dir(blocked.path().parent().expect("폴더"))
            .expect("훑는다")
            .flatten()
            .map(|one| one.file_name().to_string_lossy().into_owned())
            .filter(|name| name.contains(".tmp"))
            .collect();
        assert!(leftovers.is_empty(), "임시 파일이 남았다: {leftovers:?}");
    }

    #[test]
    fn saving_touches_only_the_one_settings_file() {
        let dir = scratch("only-one");
        let store = Store::at(&dir);
        std::fs::write(dir.join("남의파일.txt"), "건드리지 마라").expect("적는다");

        let mut settings = CompanionSettings::default();
        settings.touch("project:a", Path::new("/tmp/a"), "a");
        store.save(&settings).expect("적는다");
        store.save(&settings).expect("또 적는다");

        let mut names: Vec<String> = std::fs::read_dir(&dir)
            .expect("훑는다")
            .flatten()
            .map(|one| one.file_name().to_string_lossy().into_owned())
            .collect();
        names.sort();
        assert_eq!(names, ["companion-settings.json", "남의파일.txt"], "다른 파일이 생겼다");
        assert_eq!(
            std::fs::read_to_string(dir.join("남의파일.txt")).expect("읽는다"),
            "건드리지 마라"
        );
    }

    // ── 사실이 섞이지 않는다 ────────────────────────────────────────

    #[test]
    fn no_view_no_detail_no_presentation_state_ever_reaches_the_settings() {
        let dir = scratch("no-facts");
        let store = Store::at(&dir);
        let mut settings = CompanionSettings::default();
        settings.touch("project:a", Path::new("/tmp/a"), "a");
        settings.last_selected = Some("project:a".to_string());
        store.save(&settings).expect("적는다");

        let said = std::fs::read_to_string(store.path()).expect("읽는다");
        // **칸 이름 전부**가 허용 목록 안에 있다 — 중첩된 것까지.
        only_settings_keys(&said).expect("설정에 모르는 칸이 있다");

        // 그리고 사실·표현 상태의 칸 이름이 하나도 없다(§9.1.2 · §12-9).
        // 글자가 아니라 **칸 이름**으로 본다 — `last_selected` 가 `selected` 를 품듯
        // 낱말은 서로를 품기 때문이다.
        let seen: serde_json::Value = serde_json::from_str(&said).expect("JSON");
        let mut names = Vec::new();
        fn collect(at: &serde_json::Value, into: &mut Vec<String>) {
            match at {
                serde_json::Value::Object(fields) => {
                    for (name, value) in fields {
                        into.push(name.clone());
                        collect(value, into);
                    }
                }
                serde_json::Value::Array(items) => items.iter().for_each(|one| collect(one, into)),
                _ => {}
            }
        }
        collect(&seen, &mut names);
        for forbidden in [
            "timeline", "current_will", "captured_at_unix_ms", "step_ref", "cycle_ref",
            "report", "selected", "collapsed", "scroll", "detail", "world", "journey",
            "memory", "will", "watcher", "next_actions", "current",
        ] {
            assert!(
                !names.iter().any(|name| name == forbidden),
                "설정에 {forbidden:?} 칸이 생겼다"
            );
        }
    }
}
