//! Report — Step 을 닫을 때 함께 남기는 기록.
//!
//! v0.1 에서 Report 는 **이름 붙은 칸의 모음**이다. 어떤 칸이 있어야 하는지는
//! `gil-spec.yaml` 의 `close_requires` 가 정한다(코드가 아니라).

use std::collections::BTreeMap;

/// 이름 붙은 칸들의 모음. 순서는 이름순으로 고정된다(메시지·시험이 흔들리지 않게).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Report {
    fields: BTreeMap<String, String>,
}

impl Report {
    pub fn new() -> Self {
        Report::default()
    }

    /// 칸 하나를 채운 새 Report 를 돌려준다.
    pub fn with(mut self, name: impl Into<String>, value: impl Into<String>) -> Self {
        self.insert(name, value);
        self
    }

    pub fn insert(&mut self, name: impl Into<String>, value: impl Into<String>) {
        self.fields.insert(name.into(), value.into());
    }

    pub fn remove(&mut self, name: &str) {
        self.fields.remove(name);
    }

    pub fn get(&self, name: &str) -> Option<&str> {
        self.fields.get(name).map(String::as_str)
    }

    /// 그 이름의 칸이 있는가.
    ///
    /// v0.1 은 **있는지만** 본다. 내용이 비었는지는 명세가 말하지 않아서 재지 않는다.
    pub fn has(&self, name: &str) -> bool {
        self.fields.contains_key(name)
    }

    pub fn field_names(&self) -> impl Iterator<Item = &str> {
        self.fields.keys().map(String::as_str)
    }

    pub fn is_empty(&self) -> bool {
        self.fields.is_empty()
    }
}

impl<K, V> FromIterator<(K, V)> for Report
where
    K: Into<String>,
    V: Into<String>,
{
    fn from_iter<I: IntoIterator<Item = (K, V)>>(iter: I) -> Self {
        Report {
            fields: iter.into_iter().map(|(k, v)| (k.into(), v.into())).collect(),
        }
    }
}
