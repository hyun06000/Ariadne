//! Artifact 객체 저장소 — **내용이 주소인 append-only 창고.**
//!
//! ```text
//! .gil/
//!   artifacts/
//!     blobs/sha256/ab/cdef…      일반 파일의 바이트 그대로
//!     manifests/sha256/12/3456…  한 세계의 canonical manifest
//!     tmp/                       확정 전에 흘려 쓰는 자리
//! ```
//!
//! 두 층 다 **불변**이다. 같은 주소의 객체를 덮어쓰지 않는다 — 내용이 주소를 정하므로
//! 같은 주소는 곧 같은 내용이고, 덮어쓸 이유가 없다.
//!
//! # 세 층 중 둘만 여기 있다
//!
//! ```text
//! SnapshotRef → manifest    아직 없다 (Snapshot registry, 다음 조각)
//! manifest    → blob 목록   여기
//! blob        → 바이트      여기
//! ```
//!
//! 그래서 여기 눕는 객체는 **아직 아무 `SnapshotRef` 도 가리키지 않는다.** 미참조 객체는
//! 논리 손상이 아니다(Artifact Model §3.5·§10) — 논리 World 상태는 `state.yaml` 이 지고,
//! 이 창고는 그것이 가리킬 때만 뜻을 갖는다.
//!
//! # 경로를 사람의 글자로 짓지 않는다
//!
//! 객체 경로는 **검증된 [`ContentDigest`] 에서만** 조립한다. 사용자 입력이나 절대 경로를
//! 이어 붙이는 자리가 없으므로, 창고 밖으로 새는 경로를 만들 수 없다.

use std::fmt;
use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use sha2::{Digest, Sha256};

use super::codec::{self, CodecError};
use super::registry::ManifestAddress;
use super::{CHUNK, ContentDigest, DigestAlgorithm, Manifest};

/// 루트 `.gil/` 아래 창고가 놓이는 자리.
const ARTIFACTS: &str = "artifacts";
const BLOBS: &str = "blobs";
const MANIFESTS: &str = "manifests";
const TMP: &str = "tmp";
/// 주소의 첫 두 글자를 폴더로 쓴다 — 한 폴더에 파일이 수십만 개 쌓이지 않게.
const SHARD: usize = 2;

/// 임시 파일 이름이 겹치지 않게 세는 수. 프로세스 안에서 단조롭게 는다.
static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);

/// 저장할 객체의 종류. 경로도 오류 메시지도 이것으로 갈린다.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum ObjectKind {
    Blob,
    Manifest,
}

impl ObjectKind {
    fn dir(self) -> &'static str {
        match self {
            ObjectKind::Blob => BLOBS,
            ObjectKind::Manifest => MANIFESTS,
        }
    }
}

impl fmt::Display for ObjectKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            ObjectKind::Blob => "blob",
            ObjectKind::Manifest => "manifest",
        })
    }
}

/// `.gil/artifacts/` 하나.
#[derive(Debug, Clone)]
pub(crate) struct ObjectStore {
    root: PathBuf,
}

impl ObjectStore {
    /// 그 프로젝트의 `.gil` 아래 창고.
    pub(crate) fn at(gil_dir: &Path) -> ObjectStore {
        ObjectStore {
            root: gil_dir.join(ARTIFACTS),
        }
    }

    /// 창고 자신의 자리 — `.gil/artifacts/`.
    pub(crate) fn root(&self) -> &Path {
        &self.root
    }

    /// 확정 전에 흘려 쓰는 자리.
    pub(crate) fn tmp(&self) -> PathBuf {
        self.root.join(TMP)
    }

    /// 창고 최상위에 있어도 되는 이름들 — 이것 말고는 GIL 이 모르는 것이다.
    pub(crate) const TOP_LEVEL: &'static [&'static str] = &[BLOBS, MANIFESTS, TMP];

    /// 이 이름이 **GIL 이 만든 임시 파일**의 이름인가 — `<pid>-<표>`.
    ///
    /// 이름 규칙을 아는 자리가 하나여야 한다. 만드는 쪽과 거두는 쪽이 각자 규칙을 적으면
    /// 언젠가 갈리고, 그러면 **남의 파일을 지우거나 제 잔해를 못 거둔다.**
    pub(crate) fn is_temp_name(name: &str) -> bool {
        match name.split_once('-') {
            Some((pid, ticket)) => {
                !pid.is_empty()
                    && !ticket.is_empty()
                    && pid.bytes().all(|b| b.is_ascii_digit())
                    && ticket.bytes().all(|b| b.is_ascii_digit())
            }
            None => false,
        }
    }

    /// 객체가 눕는 자리 — **검증된 지문에서만 조립한다.**
    fn object_path(&self, kind: ObjectKind, digest: &ContentDigest) -> PathBuf {
        let hex = digest.hex();
        let (shard, rest) = hex.split_at(SHARD);
        self.root
            .join(kind.dir())
            .join(digest.algorithm().as_str())
            .join(shard)
            .join(rest)
    }

    // ── 쓰기 ───────────────────────────────────────────────────────────────

    /// 흘려 읽으며 바이트를 창고에 눕히고 그 지문을 돌려준다.
    ///
    /// **한 번의 스트림으로 지문과 사본을 함께 만든다** — 파일을 두 번 읽지 않고, 파일
    /// 크기만 한 버퍼도 잡지 않는다(Artifact Model §3.5).
    pub(crate) fn put_blob(&self, reader: impl Read) -> Result<ContentDigest, ObjectError> {
        self.put(ObjectKind::Blob, reader)
    }

    /// 세계를 canonical 바이트로 적어 창고에 눕히고 그 **내부 주소**를 돌려준다.
    ///
    /// 돌려주는 것은 그냥 지문이 아니라 [`ManifestAddress`] 다 — 종류를 타입이 지므로,
    /// blob 주소를 세계의 주소로 적는 실수가 컴파일을 통과하지 못한다.
    pub(crate) fn put_manifest(
        &self,
        manifest: &Manifest,
    ) -> Result<ManifestAddress, ObjectError> {
        let bytes = codec::encode(manifest);
        let digest = self.put(ObjectKind::Manifest, &bytes[..])?;
        Ok(ManifestAddress::of_manifest(digest))
    }

    /// **하나뿐인 publish.** blob 이든 manifest 든 이 원리를 지난다.
    ///
    /// ```text
    /// 1. tmp/ 에 전체를 스트리밍          아직 주소가 없다
    /// 2. flush + sync_all                 내용을 디스크에 밀어 넣는다
    /// 3. 지문으로 최종 경로를 정한다
    /// 4. 부모 디렉터리 준비
    /// 5. temp → final **hard link**
    /// ```
    ///
    /// # 왜 rename 이 아니라 hard link 인가
    ///
    /// Unix 의 `rename` 은 최종 경로가 이미 있으면 **말없이 갈아 끼운다.** 두 프로세스가
    /// 같은 주소를 동시에 확정하면 먼저 놓인 append-only 객체가 덮어써진다. 내용이 같을
    /// 것으로 기대되더라도, **덮어쓰는 동작 자체**가 append-only 를 어긴다.
    ///
    /// `hard_link` 는 최종 경로가 이미 있으면 `AlreadyExists` 로 **실패한다.** 그래서 기존
    /// 객체를 건드릴 길이 원천적으로 없다.
    ///
    /// 지원하지 않는 파일 시스템에서는 **rename 으로 물러서지 않는다.** 보장을 약화하는
    /// fallback 을 두느니 [`ObjectError::PublishUnsupported`] 로 거절한다.
    fn put(&self, kind: ObjectKind, mut reader: impl Read) -> Result<ContentDigest, ObjectError> {
        let tmp_dir = self.root.join(TMP);
        create_dir(&tmp_dir)?;

        let ticket = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
        let temp = tmp_dir.join(format!("{}-{ticket}", std::process::id()));

        // ①②  흘려 쓰고, 디스크에 밀어 넣는다.
        let digest = {
            let mut file = File::create(&temp).map_err(|source| ObjectError::Io {
                doing: "임시 객체를 만들지",
                source: source.to_string(),
            })?;
            let mut hasher = Sha256::new();
            let mut chunk = vec![0u8; CHUNK];
            loop {
                let read = reader.read(&mut chunk).map_err(|source| ObjectError::Io {
                    doing: "객체가 될 바이트를 읽지",
                    source: source.to_string(),
                })?;
                if read == 0 {
                    break;
                }
                hasher.update(&chunk[..read]);
                file.write_all(&chunk[..read])
                    .map_err(|source| ObjectError::Io {
                        doing: "임시 객체에 쓰지",
                        source: source.to_string(),
                    })?;
            }
            file.flush().map_err(|source| ObjectError::Io {
                doing: "임시 객체를 flush 하지",
                source: source.to_string(),
            })?;
            file.sync_all().map_err(|source| ObjectError::Io {
                doing: "임시 객체를 디스크에 밀어 넣지",
                source: source.to_string(),
            })?;
            ContentDigest::from_raw(DigestAlgorithm::Sha256, hasher.finalize().into())
        };

        // ③④  주소가 정해졌다. 자리를 마련한다.
        let final_path = self.object_path(kind, &digest);
        let parent = final_path
            .parent()
            .expect("객체 경로는 언제나 부모를 지닌다")
            .to_path_buf();
        create_dir(&parent)?;

        // ⑤  **덮어쓸 수 없는 방식으로** 제자리에 건다.
        match fs::hard_link(&temp, &final_path) {
            Ok(()) => {
                let _ = fs::remove_file(&temp);
                sync_dir(&parent)?;
                #[cfg(test)]
                meddle::after_link(&final_path);
                // 방금 건 객체를 **다시 열어** 주소와 내용이 맞는지 본다.
                //
                // 흘려 쓰며 잰 지문은 **읽어들인 바이트**의 것이지, 디스크에 실제로 앉은
                // 바이트의 것이 아니다. 그 둘이 갈리는 일은 드물지만, 갈린 채 확정되면
                // 그 거짓이 나중에 복원되는 세계가 된다.
                let found = digest_of_file(&final_path, kind, &digest)?;
                match found == digest {
                    true => Ok(digest),
                    false => Err(ObjectError::Corrupt {
                        kind,
                        address: digest.hex(),
                        found: found.hex(),
                    }),
                }
            }
            // 누군가 먼저 같은 주소를 확정했다. **그것을 건드리지 않고** 확인만 한다.
            Err(source) if source.kind() == io::ErrorKind::AlreadyExists => {
                let found = digest_of_file(&final_path, kind, &digest)?;
                let _ = fs::remove_file(&temp);
                match found == digest {
                    true => Ok(digest),
                    false => Err(ObjectError::Corrupt {
                        kind,
                        address: digest.hex(),
                        found: found.hex(),
                    }),
                }
            }
            // hard link 를 못 거는 파일 시스템이다. **rename 으로 물러서지 않는다.**
            Err(source) if unsupported(&source) => {
                let _ = fs::remove_file(&temp);
                Err(ObjectError::PublishUnsupported {
                    kind,
                    source: source.to_string(),
                })
            }
            Err(source) => {
                // 제 손으로 만든 임시 이름은 제 손으로 걷는다 — 실패한 확정이 tmp/ 를
                // 키우면, 다음 사람이 그것을 미완의 객체로 오해한다.
                let _ = fs::remove_file(&temp);
                Err(ObjectError::Io {
                    doing: "객체를 제자리에 걸지",
                    source: source.to_string(),
                })
            }
        }
    }

    // ── 읽기 ───────────────────────────────────────────────────────────────

    /// blob 의 바이트를 흘려 내보낸다 — **주소와 실제 내용을 다시 견주며.**
    ///
    /// 저장 경로만 믿지 않는다. 창고의 파일이 밖에서 바뀌었다면 그것은 손상이고, 조용히
    /// 흘려보내면 그 거짓이 복원된 세계가 된다.
    pub(crate) fn read_blob(
        &self,
        digest: &ContentDigest,
        out: &mut impl Write,
    ) -> Result<(), ObjectError> {
        let path = self.object_path(ObjectKind::Blob, digest);
        let mut file = open(&path, ObjectKind::Blob, digest)?;

        let mut hasher = Sha256::new();
        let mut chunk = vec![0u8; CHUNK];
        loop {
            let read = file.read(&mut chunk).map_err(|source| ObjectError::Io {
                doing: "blob 을 읽지",
                source: source.to_string(),
            })?;
            if read == 0 {
                break;
            }
            hasher.update(&chunk[..read]);
            out.write_all(&chunk[..read])
                .map_err(|source| ObjectError::Io {
                    doing: "blob 을 내보내지",
                    source: source.to_string(),
                })?;
        }
        let found = ContentDigest::from_raw(DigestAlgorithm::Sha256, hasher.finalize().into());
        match &found == digest {
            true => Ok(()),
            false => Err(ObjectError::Corrupt {
                kind: ObjectKind::Blob,
                address: digest.hex(),
                found: found.hex(),
            }),
        }
    }

    /// manifest 를 되읽는다 — 주소를 다시 견주고, 그 다음 schema 를 검증한다.
    pub(crate) fn read_manifest(&self, at: &ManifestAddress) -> Result<Manifest, ObjectError> {
        let digest = at.digest();
        let path = self.object_path(ObjectKind::Manifest, digest);
        let mut file = open(&path, ObjectKind::Manifest, digest)?;

        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes)
            .map_err(|source| ObjectError::Io {
                doing: "manifest 를 읽지",
                source: source.to_string(),
            })?;

        let found = codec::address(&bytes);
        if &found != digest {
            return Err(ObjectError::Corrupt {
                kind: ObjectKind::Manifest,
                address: digest.hex(),
                found: found.hex(),
            });
        }
        codec::decode(&bytes).map_err(|source| ObjectError::NotCanonical {
            address: digest.hex(),
            source,
        })
    }
}

/// 이름이 디렉터리에 실제로 새겨지도록 부모를 디스크에 밀어 넣는다.
///
/// # 이 보장의 실제 범위
///
/// Unix 에서는 부모 디렉터리를 열어 `fsync` 한다 — 그래야 전원이 끊겨도 **이름이** 남는다.
/// 그 밖의 플랫폼에서는 하지 않는다(표준 라이브러리로 안전하게 할 방법이 없다).
///
/// macOS 의 `fsync` 는 드라이브의 쓰기 캐시까지 비우지 않는다(`F_FULLFSYNC` 가 그 일을 한다).
/// 따라서 여기서 얻는 것은 **파일 시스템 계층까지의 내구성**이며, 전원 차단 복구가 완전하다고
/// 주장하지 않는다.
#[cfg(unix)]
fn sync_dir(at: &Path) -> Result<(), ObjectError> {
    File::open(at)
        .and_then(|dir| dir.sync_all())
        .map_err(|source| ObjectError::Io {
            doing: "객체 폴더를 디스크에 밀어 넣지",
            source: source.to_string(),
        })
}

#[cfg(not(unix))]
fn sync_dir(_at: &Path) -> Result<(), ObjectError> {
    // 이 플랫폼에서는 표준 라이브러리로 디렉터리를 fsync 할 수 없다. 하지 않는다.
    Ok(())
}

/// 확정과 검증 사이를 비집는 손 — **시험에만 있다.**
///
/// 「썼으니 있다」를 믿지 않는지 재려면 쓴 것과 앉은 것이 갈린 순간을 만들어야 하는데,
/// 그 순간은 밖에서 만들 수 없다. 그래서 그 한 자리만 시험에 연다.
#[cfg(test)]
mod meddle {
    use std::cell::RefCell;
    use std::path::Path;

    thread_local! {
        static AFTER_LINK: RefCell<Option<Vec<u8>>> = const { RefCell::new(None) };
    }

    /// 다음 확정 직후 객체를 이 바이트로 바꾼다. 한 번만 듣는다.
    pub(super) fn plant(bytes: &[u8]) {
        AFTER_LINK.with(|slot| *slot.borrow_mut() = Some(bytes.to_vec()));
    }

    pub(super) fn after_link(at: &Path) {
        if let Some(bytes) = AFTER_LINK.with(|slot| slot.borrow_mut().take()) {
            let _ = std::fs::write(at, bytes);
        }
    }
}

/// 이 오류가 「이 파일 시스템은 hard link 를 못 건다」는 뜻인가.
fn unsupported(source: &io::Error) -> bool {
    matches!(
        source.kind(),
        io::ErrorKind::Unsupported | io::ErrorKind::PermissionDenied
    )
}

fn create_dir(at: &Path) -> Result<(), ObjectError> {
    fs::create_dir_all(at).map_err(|source| ObjectError::Io {
        doing: "객체 폴더를 만들지",
        source: source.to_string(),
    })
}

fn open(path: &Path, kind: ObjectKind, digest: &ContentDigest) -> Result<File, ObjectError> {
    File::open(path).map_err(|source| match source.kind() {
        io::ErrorKind::NotFound => ObjectError::Missing {
            kind,
            address: digest.hex(),
        },
        _ => ObjectError::Io {
            doing: "객체를 열지",
            source: source.to_string(),
        },
    })
}

/// 이미 있는 객체를 흘려 읽어 지문을 다시 잰다.
fn digest_of_file(
    path: &Path,
    kind: ObjectKind,
    address: &ContentDigest,
) -> Result<ContentDigest, ObjectError> {
    let mut file = open(path, kind, address)?;
    let mut hasher = Sha256::new();
    let mut chunk = vec![0u8; CHUNK];
    loop {
        let read = file.read(&mut chunk).map_err(|source| ObjectError::Io {
            doing: "이미 있는 객체를 확인하지",
            source: source.to_string(),
        })?;
        if read == 0 {
            break;
        }
        hasher.update(&chunk[..read]);
    }
    Ok(ContentDigest::from_raw(
        DigestAlgorithm::Sha256,
        hasher.finalize().into(),
    ))
}

/// 창고가 답하지 못한 이유.
///
/// 어느 것이든 **논리 상태는 확정되지 않았다.** 손상을 조용히 넘기거나 새 객체로 덮어써
/// 고치지 않는다 — 고쳐진 창고는 무엇이 진짜였는지 더는 말하지 못한다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum ObjectError {
    /// 그 주소의 객체가 없다.
    Missing { kind: ObjectKind, address: String },
    /// 있는데 내용이 주소와 다르다.
    Corrupt {
        kind: ObjectKind,
        address: String,
        found: String,
    },
    /// manifest 로 읽히지 않는다.
    NotCanonical { address: String, source: CodecError },
    /// 이 파일 시스템이 hard link 를 지원하지 않는다 — 보장을 약화하는 대신 멈춘다.
    PublishUnsupported {
        kind: ObjectKind,
        source: String,
    },
    /// 창고를 읽거나 쓰지 못했다.
    Io {
        doing: &'static str,
        source: String,
    },
}

impl fmt::Display for ObjectError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ObjectError::Missing { kind, address } => write!(
                f,
                "{kind} 객체 sha256:{address} 가 창고에 없다.\n\
                 어떤 Snapshot 도 확정하지 않았다."
            ),
            ObjectError::Corrupt {
                kind,
                address,
                found,
            } => write!(
                f,
                "{kind} 객체 sha256:{address} 의 내용이 주소와 다르다 (실제 sha256:{found}).\n\
                 창고가 손상됐다 — 조용히 덮어써 고치지 않는다.\n\
                 어떤 Snapshot 도 확정하지 않았다."
            ),
            ObjectError::NotCanonical { address, source } => write!(
                f,
                "manifest 객체 sha256:{address} 를 읽지 못했다 — {source}.\n\
                 어떤 Snapshot 도 확정하지 않았다."
            ),
            ObjectError::PublishUnsupported { kind, source } => write!(
                f,
                "이 파일 시스템에서 {kind} 객체를 append-only 로 확정할 수 없다 — {source}.\n\
                 GIL 은 기존 객체를 덮어쓸 수 있는 방식으로 물러서지 않는다.\n\
                 `.gil` 을 hard link 를 지원하는 파일 시스템에 두고 다시 시도한다.\n\
                 어떤 Snapshot 도 확정하지 않았다."
            ),
            ObjectError::Io { doing, source } => write!(
                f,
                "{doing} 못했다 — {source}.\n어떤 Snapshot 도 확정하지 않았다."
            ),
        }
    }
}

impl std::error::Error for ObjectError {}

// ── 시험 ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::super::{ManifestEntry, capture, observe};
    use super::*;

    fn scratch(label: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("gil-objects-{label}"));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).expect("시험이 쓸 자리를 만들 수 있어야 한다");
        dir
    }

    /// 창고 하나와 그것이 사는 프로젝트 루트.
    fn store(label: &str) -> (PathBuf, ObjectStore) {
        let root = scratch(label);
        let store = ObjectStore::at(&root.join(".gil"));
        (root, store)
    }

    fn write(root: &Path, path: &str, bytes: &[u8]) {
        let at = root.join(path);
        if let Some(parent) = at.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        fs::write(&at, bytes).unwrap();
    }

    fn blob_bytes(store: &ObjectStore, digest: &ContentDigest) -> Vec<u8> {
        let mut out = Vec::new();
        store.read_blob(digest, &mut out).expect("blob 을 읽는다");
        out
    }

    fn world(paths: &[(&str, &[u8])]) -> Manifest {
        Manifest::new(
            paths
                .iter()
                .map(|(path, bytes)| ManifestEntry {
                    path: super::super::EntryPath::parse(path).unwrap(),
                    content: codec::address(bytes),
                })
                .collect(),
        )
    }

    // ── blob ──────────────────────────────────────────────────────────────

    #[test]
    fn the_same_bytes_share_one_blob() {
        let (_root, store) = store("blob-share");
        let one = store.put_blob(&b"same bytes"[..]).unwrap();
        let two = store.put_blob(&b"same bytes"[..]).unwrap();

        assert_eq!(one, two, "같은 바이트가 다른 주소를 얻었다");
        let at = store.object_path(ObjectKind::Blob, &one);
        assert!(at.exists());
        // 파일은 하나뿐이다 — 내용이 주소이므로 사본이 생기지 않는다.
        let shard = at.parent().unwrap();
        assert_eq!(fs::read_dir(shard).unwrap().count(), 1);
    }

    #[test]
    fn different_bytes_are_different_blobs() {
        let (_root, store) = store("blob-differ");
        assert_ne!(
            store.put_blob(&b"one"[..]).unwrap(),
            store.put_blob(&b"two"[..]).unwrap()
        );
    }

    #[test]
    fn an_empty_file_is_a_valid_blob() {
        let (_root, store) = store("blob-empty");
        let digest = store.put_blob(&b""[..]).unwrap();
        assert_eq!(blob_bytes(&store, &digest), Vec::<u8>::new());
    }

    #[test]
    fn a_large_blob_streams_through() {
        let (_root, store) = store("blob-large");
        let big = vec![7u8; CHUNK * 3 + 11];
        let digest = store.put_blob(&big[..]).unwrap();
        assert_eq!(blob_bytes(&store, &digest), big, "큰 blob 이 바뀌었다");
    }

    #[test]
    fn a_stored_blob_reads_back_byte_for_byte() {
        let (_root, store) = store("blob-roundtrip");
        for bytes in [&b""[..], b"a", b"\x00\xFF\x00", "가나다".as_bytes(), b"a\r\nb"] {
            let digest = store.put_blob(bytes).unwrap();
            assert_eq!(blob_bytes(&store, &digest), bytes);
        }
    }

    #[test]
    fn an_existing_blob_is_never_overwritten() {
        let (_root, store) = store("blob-no-overwrite");
        let digest = store.put_blob(&b"first"[..]).unwrap();
        let at = store.object_path(ObjectKind::Blob, &digest);
        let before = fs::metadata(&at).unwrap().modified().unwrap();

        // 같은 바이트를 다시 넣는다 — 기존 객체를 공유하고 덮어쓰지 않는다.
        assert_eq!(store.put_blob(&b"first"[..]).unwrap(), digest);
        assert_eq!(fs::metadata(&at).unwrap().modified().unwrap(), before);
        assert_eq!(fs::read(&at).unwrap(), b"first");
    }

    #[test]
    fn a_corrupt_blob_is_refused_not_repaired() {
        let (_root, store) = store("blob-corrupt");
        let digest = store.put_blob(&b"honest"[..]).unwrap();
        let at = store.object_path(ObjectKind::Blob, &digest);
        fs::write(&at, b"tampered").unwrap();

        // 읽을 때 — 경로만 믿지 않고 내용을 다시 잰다.
        let mut out = Vec::new();
        let err = store.read_blob(&digest, &mut out).expect_err("손상이 읽혔다");
        assert!(matches!(err, ObjectError::Corrupt { kind: ObjectKind::Blob, .. }), "{err}");

        // 다시 넣을 때 — 조용히 덮어써 고치지 않는다.
        let err = store.put_blob(&b"honest"[..]).expect_err("손상을 덮어썼다");
        assert!(matches!(err, ObjectError::Corrupt { .. }), "{err}");
        assert_eq!(fs::read(&at).unwrap(), b"tampered", "손상된 객체를 건드렸다");
    }

    #[test]
    fn a_missing_blob_says_so() {
        let (_root, store) = store("blob-missing");
        let digest = store.put_blob(&b"gone"[..]).unwrap();
        fs::remove_file(store.object_path(ObjectKind::Blob, &digest)).unwrap();

        let mut out = Vec::new();
        assert!(matches!(
            store.read_blob(&digest, &mut out).expect_err("없는 blob 이 읽혔다"),
            ObjectError::Missing { kind: ObjectKind::Blob, .. }
        ));
    }

    // ── manifest ──────────────────────────────────────────────────────────

    #[test]
    fn a_manifest_reads_back_by_its_address() {
        let (_root, store) = store("man-roundtrip");
        let before = world(&[("a.txt", b"a"), ("src/main.rs", b"m")]);
        let address = store.put_manifest(&before).unwrap();
        assert_eq!(store.read_manifest(&address).unwrap(), before);
    }

    #[test]
    fn the_same_manifest_shares_one_object() {
        let (_root, store) = store("man-share");
        let one = store.put_manifest(&world(&[("a.txt", b"a")])).unwrap();
        let two = store.put_manifest(&world(&[("a.txt", b"a")])).unwrap();
        assert_eq!(one, two);

        let shard = store.object_path(ObjectKind::Manifest, one.digest());
        assert_eq!(fs::read_dir(shard.parent().unwrap()).unwrap().count(), 1);
    }

    #[test]
    fn a_corrupt_manifest_is_refused() {
        let (_root, store) = store("man-corrupt");
        let address = store.put_manifest(&world(&[("a.txt", b"a")])).unwrap();
        let at = store.object_path(ObjectKind::Manifest, address.digest());

        // 주소와 내용이 갈리면 — 주소 재검증에서 걸린다.
        let mut bytes = fs::read(&at).unwrap();
        bytes.push(0);
        fs::write(&at, &bytes).unwrap();
        assert!(matches!(
            store.read_manifest(&address).expect_err("손상이 읽혔다"),
            ObjectError::Corrupt { kind: ObjectKind::Manifest, .. }
        ));
    }

    #[test]
    fn a_manifest_that_is_not_canonical_is_refused() {
        // 주소는 맞는데 안이 canonical 이 아닌 경우 — schema 검증에서 걸린다.
        let (_root, store) = store("man-not-canonical");
        let junk = b"GILMANIF\x00\x00\x00\x01\x01\x00\x00\x00\x00\x00\x00\x00\x09".to_vec();
        let address = ManifestAddress::of_manifest(store.put(ObjectKind::Manifest, &junk[..]).unwrap());

        let err = store.read_manifest(&address).expect_err("비canonical 이 읽혔다");
        assert!(matches!(err, ObjectError::NotCanonical { .. }), "{err}");
    }

    #[test]
    fn a_missing_manifest_says_so() {
        let (_root, store) = store("man-missing");
        let address = store.put_manifest(&world(&[("a.txt", b"a")])).unwrap();
        fs::remove_file(store.object_path(ObjectKind::Manifest, address.digest())).unwrap();

        assert!(matches!(
            store.read_manifest(&address).expect_err("없는 manifest 가 읽혔다"),
            ObjectError::Missing { kind: ObjectKind::Manifest, .. }
        ));
    }

    // ── 관측과 창고를 잇는 자리 ───────────────────────────────────────────

    #[test]
    fn capturing_stores_every_blob_and_the_manifest() {
        let (root, store) = store("capture-all");
        write(&root, "a.txt", b"alpha");
        write(&root, "deep/b.txt", b"beta");
        write(&root, ".gil/state.yaml", b"format: 3\n");

        let manifest = capture(&root, &store).expect("관측하며 담는다");
        assert_eq!(manifest.len(), 2, "루트 .gil 이 섞였다");

        // 모든 blob 이 창고에 있고, 원본 바이트를 돌려준다.
        for entry in manifest.entries() {
            let want: &[u8] = match entry.path.as_str() {
                "a.txt" => b"alpha",
                "deep/b.txt" => b"beta",
                other => panic!("모르는 자리: {other}"),
            };
            assert_eq!(blob_bytes(&store, &entry.content), want);
        }

        // manifest 도 담기고, 되읽으면 같은 세계다.
        let address = store.put_manifest(&manifest).unwrap();
        assert_eq!(store.read_manifest(&address).unwrap(), manifest);
    }

    #[test]
    fn a_world_that_moved_has_the_same_object_addresses() {
        let (here, here_store) = store("capture-here");
        let (far, far_store) = store("capture-somewhere-else-entirely");
        for root in [&here, &far] {
            write(root, "a/b/c.txt", b"same bytes");
        }
        assert_ne!(here, far);

        let one = capture(&here, &here_store).unwrap();
        let two = capture(&far, &far_store).unwrap();
        assert_eq!(one, two, "절대 위치가 세계에 섞였다");
        assert_eq!(
            codec::address(&codec::encode(&one)),
            codec::address(&codec::encode(&two)),
            "같은 세계가 다른 주소를 얻었다"
        );
    }

    #[test]
    fn a_change_between_the_two_scans_confirms_no_world() {
        let (root, store) = store("capture-changed");
        write(&root, "a.txt", b"a");

        // 첫 훑기와 두 번째 사이에 바뀌면 논리 Snapshot 은 서지 않는다.
        // 결정적으로 만들기 위해 첫 훑기가 끝난 세계와 다른 세계를 두 번 관측시킨다.
        let candidate = capture(&root, &store).expect("아직은 조용하다");
        assert_eq!(candidate.len(), 1);

        // 이제 실제로 흔든다 — 관측기 안의 두 훑기 사이를 비집는다.
        let err = super::super::observe_twice(&root, || write(&root, "b.txt", b"b"))
            .expect_err("관측 중 변경이 통과했다");
        assert_eq!(err, super::super::ObserveError::ChangedDuringObservation);
    }

    #[test]
    fn the_artifacts_store_never_joins_the_next_observation() {
        // 창고는 루트 `.gil/` 안에 있으므로 다음 관측에 섞이지 않는다.
        let (root, store) = store("capture-store-excluded");
        write(&root, "a.txt", b"a");

        let first = capture(&root, &store).expect("담는다");
        assert!(store.root.exists(), "창고가 만들어지지 않았다");
        assert!(store.root.starts_with(root.join(".gil")), "창고가 .gil 밖에 있다");

        let again = observe(&root).expect("다시 본다");
        assert_eq!(first, again, "창고가 다음 관측에 섞였다");
    }

    #[test]
    fn capturing_reads_every_file_exactly_twice() {
        // **검증되지 않은 세 번째 관측으로 blob 을 저장하지 않는다.**
        //
        // 세계가 조용하면 세 번 읽어도 결과가 같아, 결과만으로는 이 규칙을 잴 수 없다.
        // 그래서 훑기 횟수를 직접 센다 — 첫 훑기가 지문과 사본을 함께 만들고, 두 번째가
        // 그것을 검증한다. 그 둘뿐이다.
        let (root, store) = store("capture-two-reads");
        write(&root, "a.txt", b"a");
        write(&root, "deep/b.txt", b"b");

        let before = super::super::scan_count::now();
        capture(&root, &store).expect("담는다");
        assert_eq!(
            super::super::scan_count::now() - before,
            2,
            "capture 가 프로젝트를 두 번이 아닌 횟수만큼 훑었다"
        );

        // observe 도 마찬가지로 두 번이다 — 저장 없이.
        let before = super::super::scan_count::now();
        observe(&root).expect("본다");
        assert_eq!(super::super::scan_count::now() - before, 2);
    }

    #[test]
    fn a_nested_gil_still_refuses_even_when_capturing() {
        let (root, store) = store("capture-nested-gil");
        write(&root, "a.txt", b"a");
        fs::create_dir_all(root.join("sub/.gil")).unwrap();

        let err = capture(&root, &store).expect_err("중첩 GIL 이 통과했다");
        assert!(
            matches!(err, super::super::ObserveError::NestedGilRepository { .. }),
            "{err}"
        );
    }

    // ── 확정은 덮어쓰지 않는다 ────────────────────────────────────────────

    /// tmp/ 에 남은 파일 수. 확정이 끝났으면 언제나 0 이어야 한다.
    fn leftovers(store: &ObjectStore) -> usize {
        let tmp = store.root.join(TMP);
        match fs::read_dir(&tmp) {
            Ok(entries) => entries.count(),
            Err(_) => 0,
        }
    }

    #[test]
    fn publishing_the_same_object_twice_leaves_the_first_file_untouched() {
        // rename 은 조용히 갈아 끼운다. hard link 는 그럴 수 없다 — **같은 파일이 남는다.**
        let (_root, store) = store("publish-same-inode");
        let digest = store.put_blob(&b"append only"[..]).unwrap();
        let at = store.object_path(ObjectKind::Blob, &digest);
        let before = fs::metadata(&at).unwrap();

        assert_eq!(store.put_blob(&b"append only"[..]).unwrap(), digest);
        let after = fs::metadata(&at).unwrap();

        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt;
            assert_eq!(before.ino(), after.ino(), "확정이 기존 객체를 갈아 끼웠다");
        }
        assert_eq!(before.modified().unwrap(), after.modified().unwrap());
        assert_eq!(fs::read(&at).unwrap(), b"append only");
    }

    #[cfg(unix)]
    #[test]
    fn a_published_object_is_not_a_link_to_the_temp_file() {
        // hard link 로 걸었으니 임시 이름을 지워야 링크가 하나로 남는다. 지우지 않으면
        // tmp/ 가 창고만큼 커지고, 그 자리를 비우는 손이 객체까지 함께 위태롭게 한다.
        use std::os::unix::fs::MetadataExt;
        let (_root, store) = store("publish-one-link");
        let digest = store.put_blob(&b"linked once"[..]).unwrap();
        let at = store.object_path(ObjectKind::Blob, &digest);
        assert_eq!(fs::metadata(&at).unwrap().nlink(), 1, "임시 이름이 남아 있다");
    }

    #[test]
    fn nothing_is_left_in_tmp_after_a_publish() {
        let (_root, store) = store("publish-tmp-clean");
        store.put_blob(&b"one"[..]).unwrap();
        store.put_manifest(&world(&[("a.txt", b"a")])).unwrap();
        assert_eq!(leftovers(&store), 0, "확정 뒤 tmp 에 잔해가 남았다");

        // 이미 있는 주소를 다시 확정하는 길에서도 잔해가 없어야 한다.
        store.put_blob(&b"one"[..]).unwrap();
        assert_eq!(leftovers(&store), 0, "재확정 뒤 tmp 에 잔해가 남았다");
    }

    #[test]
    fn a_failed_publish_leaves_nothing_in_tmp() {
        // 손상된 객체를 만나 거절하는 길에서도 임시 파일은 걷어낸다.
        let (_root, store) = store("publish-tmp-clean-on-error");
        let digest = store.put_blob(&b"honest"[..]).unwrap();
        fs::write(store.object_path(ObjectKind::Blob, &digest), b"tampered").unwrap();

        store.put_blob(&b"honest"[..]).expect_err("손상이 통과했다");
        assert_eq!(leftovers(&store), 0, "거절하고도 tmp 에 잔해가 남았다");
    }

    #[test]
    fn an_existing_object_with_the_same_bytes_is_accepted_as_is() {
        // 다른 프로세스가 먼저 놓은 것 — 확인만 하고 **건드리지 않는다.**
        let (_root, store) = store("publish-already-there");
        let digest = codec::address(b"pre-placed");
        let at = store.object_path(ObjectKind::Blob, &digest);
        fs::create_dir_all(at.parent().unwrap()).unwrap();
        fs::write(&at, b"pre-placed").unwrap();
        let before = fs::metadata(&at).unwrap().modified().unwrap();

        assert_eq!(store.put_blob(&b"pre-placed"[..]).unwrap(), digest);
        assert_eq!(fs::metadata(&at).unwrap().modified().unwrap(), before);
    }

    #[test]
    fn an_existing_object_with_other_bytes_is_refused_and_kept() {
        let (_root, store) = store("publish-already-corrupt");
        let digest = codec::address(b"real");
        let at = store.object_path(ObjectKind::Blob, &digest);
        fs::create_dir_all(at.parent().unwrap()).unwrap();
        fs::write(&at, b"someone else's bytes").unwrap();

        let err = store.put_blob(&b"real"[..]).expect_err("손상 위에 확정했다");
        assert!(
            matches!(err, ObjectError::Corrupt { kind: ObjectKind::Blob, .. }),
            "{err}"
        );
        assert_eq!(fs::read(&at).unwrap(), b"someone else's bytes", "덮어썼다");
        assert_eq!(leftovers(&store), 0);
    }

    #[test]
    fn a_manifest_publish_takes_the_same_no_clobber_path() {
        // blob 만 안전하고 manifest 는 아닌 창고는 append-only 가 아니다.
        let (_root, store) = store("publish-manifest-no-clobber");
        let address = store.put_manifest(&world(&[("a.txt", b"a")])).unwrap();
        let at = store.object_path(ObjectKind::Manifest, address.digest());
        fs::write(&at, b"not a manifest at all").unwrap();

        let err = store
            .put_manifest(&world(&[("a.txt", b"a")]))
            .expect_err("손상된 manifest 위에 확정했다");
        assert!(
            matches!(err, ObjectError::Corrupt { kind: ObjectKind::Manifest, .. }),
            "{err}"
        );
        assert_eq!(fs::read(&at).unwrap(), b"not a manifest at all");
    }

    #[test]
    fn a_publish_that_did_not_land_as_written_is_refused() {
        // 「썼으니 있다」를 믿지 않는다 — 확정 직후 실제로 앉은 바이트를 다시 잰다.
        let (_root, store) = store("publish-landed-wrong");
        meddle::plant(b"not what was written");

        let err = store.put_blob(&b"what was written"[..]).expect_err("거짓이 확정됐다");
        assert!(
            matches!(err, ObjectError::Corrupt { kind: ObjectKind::Blob, .. }),
            "{err}"
        );
        // 조용히 다시 써서 고치지 않는다 — 고치면 무엇이 진짜였는지 더는 말하지 못한다.
        let at = store.object_path(ObjectKind::Blob, &codec::address(b"what was written"));
        assert_eq!(fs::read(&at).unwrap(), b"not what was written");
    }

    #[test]
    fn a_published_object_is_verified_by_reading_it_back() {
        // 확정 직후 다시 열어 재는 것은 「썼다고 믿기」가 아니라 「있는 것을 확인하기」다.
        let (_root, store) = store("publish-verified");
        let digest = store.put_blob(&b"verify me"[..]).unwrap();
        assert_eq!(blob_bytes(&store, &digest), b"verify me");
        assert_eq!(
            digest_of_file(
                &store.object_path(ObjectKind::Blob, &digest),
                ObjectKind::Blob,
                &digest
            )
            .unwrap(),
            digest
        );
    }

    #[test]
    fn many_publishers_of_one_object_all_agree_and_only_one_file_lands() {
        // 같은 주소를 동시에 확정해도 이기는 쪽이 먼저 놓인 객체를 갈아 끼우지 않는다.
        let (_root, store) = store("publish-concurrent");
        let bytes = vec![3u8; CHUNK + 5];

        let results: Vec<ContentDigest> = std::thread::scope(|scope| {
            let handles: Vec<_> = (0..8)
                .map(|_| {
                    let store = store.clone();
                    let bytes = bytes.clone();
                    scope.spawn(move || store.put_blob(&bytes[..]).expect("동시 확정이 깨졌다"))
                })
                .collect();
            handles.into_iter().map(|h| h.join().unwrap()).collect()
        });

        let first = results[0].clone();
        assert!(results.iter().all(|d| *d == first), "동시 확정이 갈렸다");
        let shard = store.object_path(ObjectKind::Blob, &first);
        assert_eq!(fs::read_dir(shard.parent().unwrap()).unwrap().count(), 1);
        assert_eq!(blob_bytes(&store, &first), bytes);
        assert_eq!(leftovers(&store), 0);
    }

    #[test]
    fn two_publishes_never_share_a_temp_name() {
        // 임시 이름이 겹치면 한쪽이 다른 쪽의 절반쯤 쓰인 바이트를 확정한다.
        let (_root, store) = store("publish-temp-unique");
        let a = store.put_blob(&b"aaaa"[..]).unwrap();
        let b = store.put_blob(&b"bbbb"[..]).unwrap();
        assert_ne!(a, b);
        assert_eq!(blob_bytes(&store, &a), b"aaaa");
        assert_eq!(blob_bytes(&store, &b), b"bbbb");

        // 표는 단조롭게 는다 — 두 확정이 같은 표를 받지 않는다.
        let one = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
        let two = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
        assert!(two > one);
    }

    #[test]
    fn an_empty_object_is_published_the_same_way() {
        let (_root, store) = store("publish-empty");
        let digest = store.put_blob(&b""[..]).unwrap();
        let at = store.object_path(ObjectKind::Blob, &digest);
        assert!(at.exists());
        assert_eq!(fs::read(&at).unwrap(), Vec::<u8>::new());
        assert_eq!(leftovers(&store), 0);

        assert_eq!(store.put_blob(&b""[..]).unwrap(), digest);
    }

    #[cfg(unix)]
    #[test]
    fn a_publish_that_cannot_be_no_clobber_refuses_instead_of_weakening() {
        // hard link 를 못 거는 자리에서 rename 으로 물러서면 append-only 가 조용히 사라진다.
        // 그런 파일 시스템을 시험 안에서 마련할 수 없으므로, link 를 거절하는 상황 자체를
        // 쓰기 권한으로 만든다 — 확정기가 보는 것은 어느 쪽이든 「link 를 못 걸었다」다.
        use std::os::unix::fs::PermissionsExt;
        let (_root, store) = store("publish-unsupported");
        let digest = store.put_blob(&b"blocked"[..]).unwrap();
        let at = store.object_path(ObjectKind::Blob, &digest);
        let parent = at.parent().unwrap().to_path_buf();
        fs::remove_file(&at).unwrap();
        fs::set_permissions(&parent, fs::Permissions::from_mode(0o555)).unwrap();

        let outcome = store.put_blob(&b"blocked"[..]);
        // root 로 돌면 권한이 막지 못한다 — 그때 이 시험은 잴 것이 없다.
        let blocked = fs::write(parent.join("probe"), b"x").is_err();
        fs::set_permissions(&parent, fs::Permissions::from_mode(0o755)).unwrap();
        if !blocked {
            return;
        }

        let err = outcome.expect_err("덮어쓸 수 있는 방식으로 물러섰다");
        assert!(
            matches!(err, ObjectError::PublishUnsupported { kind: ObjectKind::Blob, .. }),
            "{err}"
        );
        assert!(!at.exists(), "거절하고도 객체를 놓았다");
        assert_eq!(leftovers(&store), 0, "거절하고도 tmp 에 잔해가 남았다");
        assert!(err.to_string().contains("덮어쓸 수 있는 방식으로 물러서지 않는다"));
    }

    #[test]
    fn the_object_path_is_sharded_by_the_first_two_hex_characters() {
        let (_root, store) = store("path-shape");
        let digest = store.put_blob(&b"x"[..]).unwrap();
        let hex = digest.hex();
        let at = store.object_path(ObjectKind::Blob, &digest);

        let rest = at.file_name().unwrap().to_str().unwrap();
        let shard = at.parent().unwrap().file_name().unwrap().to_str().unwrap();
        assert_eq!(shard, &hex[..2]);
        assert_eq!(rest, &hex[2..]);
        assert_eq!(
            at.parent().unwrap().parent().unwrap().file_name().unwrap(),
            "sha256"
        );
        assert!(hex.chars().all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase()));
    }
}
