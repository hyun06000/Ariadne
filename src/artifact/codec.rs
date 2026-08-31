//! Canonical manifest binary — **한 세계를 정확히 한 벌의 바이트로 적는다.**
//!
//! Manifest 는 사람이 손으로 고치는 문서가 아니라 **내용으로 주소가 정해지는 내부 객체**다.
//! YAML·JSON 으로 적으면 공백 하나, 따옴표 하나, key 순서 하나가 바뀔 때마다 주소가 달라진다.
//! 같은 세계에 두 주소가 생기면 「이름이 같으면 세계가 같다」(Artifact Model §13)가 무너진다.
//!
//! 그래서 엄격한 이진 형식을 쓴다.
//!
//! ```text
//! ── 머리 (21 바이트) ────────────────────────────────────
//! magic             8 bytes   "GILMANIF" (ASCII)
//! format_version    4 bytes   big-endian u32 = 1
//! digest_algorithm  1 byte    1 = SHA-256
//! entry_count       8 bytes   big-endian u64
//!
//! ── 항목 (entry_count 번 되풀이) ────────────────────────
//! path_length       4 bytes   big-endian u32  (1..=4096)
//! path              path_length bytes  canonical UTF-8
//! content_digest    32 bytes  SHA-256 raw
//! ```
//!
//! 정수는 전부 **big-endian 고정 폭**이다. 플랫폼의 native endian 이나 `usize` 폭에 기대지
//! 않는다 — 같은 세계는 어느 기계에서 적어도 같은 바이트가 되어야 한다.
//!
//! # 알고리즘은 머리에 한 번만 적는다
//!
//! 한 manifest 안의 모든 항목은 머리가 밝힌 알고리즘 하나를 따른다. 항목마다 태그를
//! 되풀이하지 않는다 — 되풀이하면 서로 다른 알고리즘이 한 세계에 섞일 수 있고, 그것이
//! 무슨 뜻인지 v0 은 정하지 않았다.
//!
//! # 읽는 쪽은 입력을 믿지 않는다
//!
//! 길이 필드 하나로 메모리를 무제한 선할당하지 않는다. 남은 입력과 플랫폼 한계를 함께 보며
//! 읽고, **비canonical 표현을 조용히 고쳐 받아들이지 않는다** — 거절한다.

use std::fmt;

use sha2::{Digest, Sha256};

use super::{ContentDigest, DigestAlgorithm, EntryPath, Manifest, ManifestEntry};

/// 이 바이트로 시작하지 않으면 manifest 가 아니다.
const MAGIC: [u8; 8] = *b"GILMANIF";
/// 지금 쓰는 형식의 번호. 모르는 번호는 짐작해 읽지 않는다.
const FORMAT_VERSION: u32 = 1;
/// `digest_algorithm` 자리에 적히는 값. v0 은 SHA-256 하나뿐이다.
const TAG_SHA256: u8 = 1;

/// 머리의 크기 — magic 8 + version 4 + algorithm 1 + count 8.
const HEADER: usize = 8 + 4 + 1 + 8;
/// 한 항목이 아무리 짧아도 이만큼은 든다 — length 4 + 경로 1 + digest 32.
const MIN_ENTRY: u64 = 4 + 1 + 32;
/// 경로 하나의 상한. 플랫폼의 흔한 한계보다 넉넉하되 **무제한은 아니다.**
const MAX_PATH_BYTES: u32 = 4096;
/// SHA-256 의 길이.
const DIGEST_BYTES: usize = 32;

/// 메모리의 세계를 canonical 바이트로 적는다.
///
/// 같은 `Manifest` 는 **언제나 바이트까지 같은 결과**가 된다. 항목이 어떤 순서로 모였든
/// [`Manifest`] 가 이미 canonical 정렬을 지니기 때문이다.
pub(crate) fn encode(manifest: &Manifest) -> Vec<u8> {
    let mut out = Vec::with_capacity(HEADER + manifest.len() * 64);
    out.extend_from_slice(&MAGIC);
    out.extend_from_slice(&FORMAT_VERSION.to_be_bytes());
    out.push(TAG_SHA256);
    out.extend_from_slice(&(manifest.len() as u64).to_be_bytes());

    for entry in manifest.entries() {
        let path = entry.path.as_str().as_bytes();
        out.extend_from_slice(&(path.len() as u32).to_be_bytes());
        out.extend_from_slice(path);
        out.extend_from_slice(entry.content.raw());
    }
    out
}

/// canonical 바이트를 세계로 되읽는다 — **검증하며.**
pub(crate) fn decode(bytes: &[u8]) -> Result<Manifest, CodecError> {
    let mut cursor = Cursor::new(bytes);

    if cursor.take(8)? != MAGIC {
        return Err(CodecError::BadMagic);
    }
    let version = u32::from_be_bytes(cursor.take_array::<4>()?);
    if version != FORMAT_VERSION {
        return Err(CodecError::UnknownFormatVersion {
            found: version,
            known: FORMAT_VERSION,
        });
    }
    let tag = cursor.take(1)?[0];
    if tag != TAG_SHA256 {
        return Err(CodecError::UnknownDigestAlgorithm { found: tag });
    }
    let count = u64::from_be_bytes(cursor.take_array::<8>()?);

    // **길이 필드 하나로 메모리를 잡지 않는다.** 남은 입력이 그만큼의 항목을 담을 수
    // 없으면 그 수는 거짓이므로, 자리를 마련하기 전에 먼저 거절한다.
    let room = cursor.left() as u64;
    let needed = count
        .checked_mul(MIN_ENTRY)
        .ok_or(CodecError::EntryCountTooLarge { count })?;
    if needed > room {
        return Err(CodecError::EntryCountTooLarge { count });
    }

    let mut entries: Vec<ManifestEntry> = Vec::with_capacity(count as usize);
    for _ in 0..count {
        let length = u32::from_be_bytes(cursor.take_array::<4>()?);
        if length == 0 || length > MAX_PATH_BYTES {
            return Err(CodecError::PathLengthOutOfRange { length });
        }
        let raw = cursor.take(length as usize)?;
        let text = std::str::from_utf8(raw).map_err(|_| CodecError::PathNotUtf8)?;
        // 경로 계약은 관측과 **같은 문**을 지난다 — 두 자리가 갈리면 왕복이 깨진다.
        let path = EntryPath::parse(text).ok_or_else(|| CodecError::PathNotCanonical {
            shown: text.to_string(),
        })?;

        // **엄격한 오름차순.** 같거나 뒤로 가면 canonical 이 아니다. 정렬해서 고치지 않는다.
        if let Some(last) = entries.last() {
            match path.key().cmp(last.path.key()) {
                std::cmp::Ordering::Greater => {}
                std::cmp::Ordering::Equal => {
                    return Err(CodecError::DuplicatePath { path: path.to_string() });
                }
                std::cmp::Ordering::Less => {
                    return Err(CodecError::OutOfOrder {
                        after: last.path.to_string(),
                        found: path.to_string(),
                    });
                }
            }
        }

        let digest = cursor.take_array::<DIGEST_BYTES>()?;
        entries.push(ManifestEntry {
            path,
            content: ContentDigest::from_raw(DigestAlgorithm::Sha256, digest),
        });
    }

    if cursor.left() != 0 {
        return Err(CodecError::TrailingBytes { left: cursor.left() });
    }
    Ok(Manifest::from_verified(entries))
}

/// canonical 바이트의 지문 — **내부 객체 주소**다.
///
/// 공개 `SnapshotRef` 가 아니다(Artifact Model §13). 사람이 보는 세계의 이름은 `snapshot:A1`.
pub(crate) fn address(bytes: &[u8]) -> ContentDigest {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    ContentDigest::from_raw(DigestAlgorithm::Sha256, hasher.finalize().into())
}

/// 남은 바이트를 세며 읽는 자리 — **모자라면 읽지 않고 멈춘다.**
struct Cursor<'a> {
    bytes: &'a [u8],
    at: usize,
}

impl<'a> Cursor<'a> {
    fn new(bytes: &'a [u8]) -> Cursor<'a> {
        Cursor { bytes, at: 0 }
    }

    fn left(&self) -> usize {
        self.bytes.len() - self.at
    }

    fn take(&mut self, count: usize) -> Result<&'a [u8], CodecError> {
        if self.left() < count {
            return Err(CodecError::Truncated {
                wanted: count,
                left: self.left(),
                at: self.at,
            });
        }
        let slice = &self.bytes[self.at..self.at + count];
        self.at += count;
        Ok(slice)
    }

    fn take_array<const N: usize>(&mut self) -> Result<[u8; N], CodecError> {
        let slice = self.take(N)?;
        let mut out = [0u8; N];
        out.copy_from_slice(slice);
        Ok(out)
    }
}

/// canonical manifest 로 읽히지 않는 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum CodecError {
    /// 이 바이트로 시작하지 않는다 — manifest 가 아니다.
    BadMagic,
    /// 이 gil 이 모르는 형식 번호다.
    UnknownFormatVersion { found: u32, known: u32 },
    /// 이 gil 이 모르는 digest 알고리즘이다.
    UnknownDigestAlgorithm { found: u8 },
    /// 입력이 중간에 끊겼다.
    Truncated {
        wanted: usize,
        left: usize,
        at: usize,
    },
    /// 적힌 항목 수가 남은 입력으로 담을 수 없는 값이다.
    EntryCountTooLarge { count: u64 },
    /// 경로 길이가 0 이거나 상한을 넘는다.
    PathLengthOutOfRange { length: u32 },
    /// 경로가 UTF-8 이 아니다.
    PathNotUtf8,
    /// 경로가 canonical 계약을 어긴다.
    PathNotCanonical { shown: String },
    /// 항목이 오름차순이 아니다.
    OutOfOrder { after: String, found: String },
    /// 같은 경로가 두 번 적혔다.
    DuplicatePath { path: String },
    /// 다 읽고도 바이트가 남았다.
    TrailingBytes { left: usize },
}

impl fmt::Display for CodecError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            CodecError::BadMagic => {
                write!(f, "manifest 의 머리 표식이 아니다 — 이 객체는 manifest 가 아니다")
            }
            CodecError::UnknownFormatVersion { found, known } => write!(
                f,
                "manifest 형식 {found} 은(는) 이 gil 이 모른다 (아는 것: {known}) — \
                 모르는 형식을 짐작해 읽지 않는다"
            ),
            CodecError::UnknownDigestAlgorithm { found } => write!(
                f,
                "manifest 의 digest 알고리즘 태그 {found} 을(를) 이 gil 이 모른다 \
                 (아는 것: {TAG_SHA256} = sha256)"
            ),
            CodecError::Truncated { wanted, left, at } => write!(
                f,
                "manifest 가 {at} 바이트에서 끊겼다 — {wanted} 바이트가 더 있어야 하는데 \
                 {left} 바이트만 남았다"
            ),
            CodecError::EntryCountTooLarge { count } => write!(
                f,
                "manifest 가 항목 {count} 개라고 적었는데 남은 입력이 그만큼을 담지 못한다"
            ),
            CodecError::PathLengthOutOfRange { length } => write!(
                f,
                "manifest 의 경로 길이 {length} 는 쓸 수 없다 (1..={MAX_PATH_BYTES})"
            ),
            CodecError::PathNotUtf8 => {
                write!(f, "manifest 의 경로가 UTF-8 이 아니다")
            }
            CodecError::PathNotCanonical { shown } => write!(
                f,
                "manifest 의 경로 {shown:?} 가 canonical 이 아니다 — 상대 경로 · `/` 구분자 · \
                 `.`·`..`·`\\` 없음"
            ),
            CodecError::OutOfOrder { after, found } => write!(
                f,
                "manifest 의 항목이 오름차순이 아니다: {after} 다음에 {found} 가 왔다. \
                 정렬해서 받아들이지 않는다 — canonical 이 아닌 것은 거절한다"
            ),
            CodecError::DuplicatePath { path } => {
                write!(f, "manifest 에 {path} 가 두 번 적혔다")
            }
            CodecError::TrailingBytes { left } => write!(
                f,
                "manifest 를 다 읽고도 {left} 바이트가 남았다 — canonical 표현이 아니다"
            ),
        }
    }
}

impl std::error::Error for CodecError {}

// ── 시험 ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    /// 그 경로들을 담은 세계 하나. 내용은 경로에서 만들어 서로 다르게 둔다.
    fn world(paths: &[&str]) -> Manifest {
        Manifest::new(
            paths
                .iter()
                .map(|path| ManifestEntry {
                    path: EntryPath::parse(path).expect("정상 경로다"),
                    content: address(path.as_bytes()),
                })
                .collect(),
        )
    }

    /// 항목 하나를 손으로 적는다 — 잘못 적힌 manifest 를 짓기 위해.
    fn entry_bytes(path: &str, digest: &ContentDigest) -> Vec<u8> {
        let mut out = Vec::new();
        out.extend_from_slice(&(path.len() as u32).to_be_bytes());
        out.extend_from_slice(path.as_bytes());
        out.extend_from_slice(digest.raw());
        out
    }

    fn header(count: u64) -> Vec<u8> {
        let mut out = Vec::new();
        out.extend_from_slice(&MAGIC);
        out.extend_from_slice(&FORMAT_VERSION.to_be_bytes());
        out.push(TAG_SHA256);
        out.extend_from_slice(&count.to_be_bytes());
        out
    }

    #[test]
    fn a_world_survives_the_round_trip() {
        let before = world(&["a.txt", "src/main.rs", "가/나.txt"]);
        let after = decode(&encode(&before)).expect("제가 적은 것을 제가 읽는다");
        assert_eq!(before, after);
    }

    #[test]
    fn an_empty_world_survives_the_round_trip() {
        let empty = Manifest::new(Vec::new());
        let bytes = encode(&empty);
        assert_eq!(bytes.len(), HEADER, "빈 세계는 머리뿐이다");
        assert_eq!(decode(&bytes).expect("빈 세계도 세계다"), empty);
    }

    #[test]
    fn the_same_world_is_byte_for_byte_the_same() {
        let one = world(&["a.txt", "b.txt"]);
        let two = world(&["a.txt", "b.txt"]);
        assert_eq!(encode(&one), encode(&two));
        assert_eq!(address(&encode(&one)), address(&encode(&two)));
    }

    #[test]
    fn the_input_order_does_not_change_the_bytes() {
        // Manifest 가 canonical 정렬을 지니므로, 어떤 순서로 모아도 같은 바이트가 된다.
        let forward = world(&["a.txt", "m.txt", "z.txt"]);
        let backward = world(&["z.txt", "m.txt", "a.txt"]);
        let jumbled = world(&["m.txt", "z.txt", "a.txt"]);

        assert_eq!(encode(&forward), encode(&backward));
        assert_eq!(encode(&forward), encode(&jumbled));
    }

    #[test]
    fn a_different_world_has_a_different_address() {
        let base = world(&["a.txt", "b.txt"]);
        // 경로가 다르면
        assert_ne!(address(&encode(&base)), address(&encode(&world(&["a.txt", "c.txt"]))));
        // 항목 수가 다르면
        assert_ne!(address(&encode(&base)), address(&encode(&world(&["a.txt"]))));
        // 내용만 다르면
        let mut tweaked = base.clone();
        tweaked.entries[0].content = address(b"something else");
        assert_ne!(address(&encode(&base)), address(&encode(&tweaked)));
    }

    #[test]
    fn a_broken_magic_is_refused() {
        let mut bytes = encode(&world(&["a.txt"]));
        bytes[0] = b'X';
        assert_eq!(decode(&bytes), Err(CodecError::BadMagic));
    }

    #[test]
    fn an_unknown_format_version_is_refused() {
        let mut bytes = encode(&world(&["a.txt"]));
        bytes[8..12].copy_from_slice(&99u32.to_be_bytes());
        assert_eq!(
            decode(&bytes),
            Err(CodecError::UnknownFormatVersion {
                found: 99,
                known: FORMAT_VERSION
            })
        );
    }

    #[test]
    fn an_unknown_digest_algorithm_is_refused() {
        let mut bytes = encode(&world(&["a.txt"]));
        bytes[12] = 7;
        assert_eq!(
            decode(&bytes),
            Err(CodecError::UnknownDigestAlgorithm { found: 7 })
        );
    }

    #[test]
    fn every_truncation_boundary_is_refused() {
        // 머리 한가운데, 경로 길이 한가운데, 경로 한가운데, digest 한가운데 — 전부.
        let whole = encode(&world(&["a.txt", "bb.txt"]));
        for cut in 0..whole.len() {
            let err = decode(&whole[..cut]).expect_err("{cut} 바이트에서 끊겼는데 읽혔다");
            assert!(
                matches!(
                    err,
                    CodecError::Truncated { .. }
                        | CodecError::BadMagic
                        | CodecError::EntryCountTooLarge { .. }
                ),
                "{cut} 바이트에서 엉뚱한 이유로 거절됐다: {err}"
            );
        }
    }

    #[test]
    fn trailing_bytes_are_refused() {
        let mut bytes = encode(&world(&["a.txt"]));
        bytes.push(0);
        assert_eq!(decode(&bytes), Err(CodecError::TrailingBytes { left: 1 }));
    }

    #[test]
    fn entries_out_of_order_are_refused_not_sorted() {
        let digest = address(b"x");
        let mut bytes = header(2);
        bytes.extend(entry_bytes("z.txt", &digest));
        bytes.extend(entry_bytes("a.txt", &digest));

        let err = decode(&bytes).expect_err("정렬되지 않은 manifest 가 읽혔다");
        let CodecError::OutOfOrder { after, found } = &err else {
            panic!("다른 이유로 거절됐다: {err}");
        };
        assert_eq!((after.as_str(), found.as_str()), ("z.txt", "a.txt"));
    }

    #[test]
    fn a_duplicate_path_is_refused() {
        let digest = address(b"x");
        let mut bytes = header(2);
        bytes.extend(entry_bytes("a.txt", &digest));
        bytes.extend(entry_bytes("a.txt", &digest));

        assert_eq!(
            decode(&bytes),
            Err(CodecError::DuplicatePath {
                path: "a.txt".to_string()
            })
        );
    }

    #[test]
    fn a_non_canonical_path_is_refused() {
        let digest = address(b"x");
        for bad in ["/abs.txt", "a/../b.txt", "./a.txt", "a//b.txt", "a\\b.txt", "."] {
            let mut bytes = header(1);
            bytes.extend(entry_bytes(bad, &digest));
            let err = decode(&bytes).expect_err("{bad:?} 가 읽혔다");
            assert!(
                matches!(err, CodecError::PathNotCanonical { .. }),
                "{bad:?} 가 다른 이유로 거절됐다: {err}"
            );
        }
    }

    #[test]
    fn an_empty_path_is_refused() {
        let digest = address(b"x");
        let mut bytes = header(1);
        bytes.extend_from_slice(&0u32.to_be_bytes());
        bytes.extend_from_slice(digest.raw());
        // 항목 수 사전 검사(MIN_ENTRY)를 지나도록 한 바이트를 더 둔다 — 여기서 재려는 것은
        // 길이 0 이 거절되는가이지, 입력이 짧아 걸리는가가 아니다.
        bytes.push(0);
        assert_eq!(
            decode(&bytes),
            Err(CodecError::PathLengthOutOfRange { length: 0 })
        );
    }

    #[test]
    fn a_path_that_is_not_utf8_is_refused() {
        let digest = address(b"x");
        let mut bytes = header(1);
        bytes.extend_from_slice(&2u32.to_be_bytes());
        bytes.extend_from_slice(&[0xFF, 0xFE]);
        bytes.extend_from_slice(digest.raw());
        assert_eq!(decode(&bytes), Err(CodecError::PathNotUtf8));
    }

    #[test]
    fn a_lying_entry_count_is_refused() {
        // 적힌 수보다 실제 항목이 적으면 읽다가 끊긴다.
        let digest = address(b"x");
        let mut bytes = header(3);
        bytes.extend(entry_bytes("a.txt", &digest));
        assert!(matches!(
            decode(&bytes).expect_err("거짓 항목 수가 읽혔다"),
            CodecError::EntryCountTooLarge { count: 3 } | CodecError::Truncated { .. }
        ));

        // 적힌 수보다 실제 항목이 많으면 남는 바이트로 걸린다.
        let mut bytes = header(1);
        bytes.extend(entry_bytes("a.txt", &digest));
        bytes.extend(entry_bytes("b.txt", &digest));
        assert!(matches!(
            decode(&bytes).expect_err("남는 항목이 읽혔다"),
            CodecError::TrailingBytes { .. }
        ));
    }

    #[test]
    fn an_enormous_length_does_not_allocate() {
        // 길이 필드 하나로 메모리를 잡지 않는다. 남은 입력을 먼저 보고 거절한다.
        let mut bytes = header(u64::MAX);
        bytes.extend(entry_bytes("a.txt", &address(b"x")));
        assert_eq!(
            decode(&bytes),
            Err(CodecError::EntryCountTooLarge { count: u64::MAX }),
            "거대한 항목 수를 그대로 믿었다"
        );

        // 경로 길이도 마찬가지 — 상한을 넘으면 그 길이만큼 읽으려 하기 전에 멈춘다.
        let mut bytes = header(1);
        bytes.extend_from_slice(&u32::MAX.to_be_bytes());
        bytes.extend_from_slice(&[0u8; 33]); // 항목 수 사전 검사를 지나도록.
        assert_eq!(
            decode(&bytes),
            Err(CodecError::PathLengthOutOfRange { length: u32::MAX }),
            "거대한 경로 길이를 그대로 믿었다"
        );
    }

    #[test]
    fn the_header_is_exactly_what_the_spec_says() {
        // 형식을 코드와 명세 두 자리에 적었으므로, 한쪽이 낡으면 여기서 갈린다.
        let bytes = encode(&Manifest::new(Vec::new()));
        assert_eq!(&bytes[0..8], b"GILMANIF");
        assert_eq!(&bytes[8..12], &1u32.to_be_bytes(), "format_version = 1");
        assert_eq!(bytes[12], 1, "digest_algorithm = 1 (sha256)");
        assert_eq!(&bytes[13..21], &0u64.to_be_bytes(), "entry_count");
        assert_eq!(HEADER, 21);
    }
}
