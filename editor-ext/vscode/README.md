# gil viewer — VS Code 확장 (Phase 1a)

gil 사고 그래프(체인·사이클·스텝)를 **에디터 패널에서 실시간 관전**한다. VS Code·Cursor·
Windsurf(전부 VS Code 계열) 호환.

## 무엇을 하나

`gil: 뷰어 열기` 명령을 실행하면 확장이:
1. 빈 포트를 찾아 `gil viewer serve` 를 자식 프로세스로 띄우고,
2. 서버가 응답할 때까지 기다린 뒤,
3. `asExternalUri` 로 (원격/Codespaces 포함) 포트 포워딩하고,
4. WebView 패널에 그 뷰어를 **iframe 으로** 띄운다.

뷰어 코어는 하나도 안 바꾼다 — **1.5초 폴링 실시간 관전(`● live`)이 그대로** 산다. 이후
gil 스텝이 새겨지면 패널이 자동 새로고침된다.

## 전제

- **`gil` 이 PATH 에 있어야** 한다(또는 설정 `gilViewer.binaryPath` 로 경로 지정). 저장소-로컬
  (`./gil`)이면 절대경로를 넣는다.
- 열린 워크스페이스 폴더가 **gil 저장소**여야 한다(`gil init` 된 곳).

## 개발 실행

```bash
npm install
npm run compile
# VS Code 에서 이 폴더를 열고 F5 (Extension Development Host) → 명령 팔레트 → "gil: 뷰어 열기"
# 또는:  code --extensionDevelopmentPath=$(pwd) <gil 저장소 경로>
```

## 로드맵

- **Phase 1a (지금)** — 뷰어 패널만. serve + asExternalUri + iframe.
- **Phase 1b** — 인터랙션: 노드 클릭 → URI Handler 로 Claude Code 호출, pending 승인/기각을
  `gil approve/reject` CLI 직접 실행(WebView postMessage ↔ 확장).
- **Phase 2** — `vsce package` → Marketplace / Open VSX 게시, gil 바이너리 번들.

> Claude Code 확장은 폐쇄적(공개 API 없음)이라 직접 붙지 못한다. 인터랙션은 URI Handler
> (일방향 호출) + 우리 확장의 CLI 호출 + git 감시로 우회한다 — 상세는 상위 레포 설계 매듭.
