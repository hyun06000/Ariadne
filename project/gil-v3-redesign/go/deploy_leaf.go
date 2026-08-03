package main

import "strings"

// ── 배포된 잎을 찾는 일 (이슈 #108) ────────────────────────────────────────────
//
// 두 결함이 같은 자리에서 났다.
//
// (1) `gil close` 는 "산 잎(success) 없으면 못 닫는다"를 집행하는데, 생애주기의 **마지막**
//     관문인 배포에는 그 검사가 없었다. 형제 가지를 병렬로 파면 죽은 가지가 산 가지보다
//     많은 게 정상이라(#106·#107), 사람이 브랜치를 잘못 짚기 쉽다. 실제로 리포터는 죽은
//     가지에서 close 를 시도하다 도구에 막혀 옳은 가지로 옮겼다 — **close 가 잡아준 실수를
//     deploy 는 못 잡았다.** 집행이 두 자리에서 갈리면 느슨한 쪽이 실질 규칙이 된다.
//
// (2) 배포 마커의 귀속이 **선언(--at)에만** 의존했다. --at 없이 dev 를 통째로 내보내는 게
//     기본형인데, 그 경우 마커는 어느 노드에도 안 붙어 그래프에서 통째로 사라졌다. 화면에
//     마지막으로 남는 노드가 붉은 fail 잎이라, 사람은 "죽은 잎이 배포됐다"고 읽었다 —
//     기록은 정상인데 그림이 반대로 말했다.
//
// 왜 first-parent 로는 못 찾나. 정석대로 갈수록(사이클 → 체인 merge → chain-close →
// dev merge → deploy) 머지가 겹겹이 쌓이고, 산 잎은 언제나 머지의 **둘째 부모** 쪽에 있다.
// 첫 부모만 거슬러 오르는 탐색은 그것을 영영 못 본다(#104 와 같은 뿌리). **워크플로우를 잘
// 지킨 배포일수록 마커를 잃는다** — 규율을 지킨 쪽이 벌을 받는 셈이었다.
//
// 그래서 조상 탐색은 **모든 부모**를 본다. 가까운 것부터(너비 우선) 훑어 처음 만나는 산 잎에
// 붙인다. 그리고 배포하는 쪽은 그 잎을 `Gil-Deployed-Leaf` 로 **적어 둔다** — 다음에 읽는
// 쪽은 탐색할 필요 없이 그 값을 믿으면 된다. 찾지 못하면 침묵하지 않는다: 층 레인에
// "귀속 스텝 미상"으로 그린다. 없는 것과 못 찾은 것은 다르다.

// leafScan — 배포 귀속 판정에 필요한 만큼의 커밋 그래프(부모·스텝 정체·배포 트레일러).
type leafScan struct {
	parents   map[string][]string // sha → 부모 sha 들(모든 부모 — 머지의 둘째도)
	ref       map[string]string   // sha → chain/cycle/step (스텝 커밋만)
	kind      map[string]string   // sha → Gil-Kind
	deployTag map[string]string   // 배포 마커 커밋 sha → 태그
	deployAt  map[string]string   // 배포 마커 커밋 sha → **선언된** 귀속(--at 또는 Gil-Deployed-Leaf)
}

// scanForDeploy — revs 에서 도달하는 커밋들을 한 번의 git log 로 훑는다.
// run 은 호출자의 git 실행기(CLI 는 gitTry, 뷰어는 viewerGit) — 같은 판정을 두 자리에서
// 서로 다르게 하지 않으려고 로직 하나를 둘이 나눠 쓴다.
func scanForDeploy(run func(...string) ([]byte, error), revs ...string) *leafScan {
	const fs = "\x1f"
	const rs = "\x1e"
	args := []string{"log", "--format=%H" + fs + "%P" + fs +
		"%(trailers:key=Gil-Chain,valueonly)" + fs +
		"%(trailers:key=Gil-Cycle,valueonly)" + fs +
		"%(trailers:key=Gil-Step,valueonly)" + fs +
		"%(trailers:key=Gil-Kind,valueonly)" + fs +
		"%(trailers:key=Gil-Deploy,valueonly)" + fs +
		"%(trailers:key=Gil-Deploy-At,valueonly)" + fs +
		"%(trailers:key=Gil-Deployed-Leaf,valueonly)" + rs}
	args = append(args, revs...)
	s := &leafScan{parents: map[string][]string{}, ref: map[string]string{},
		kind: map[string]string{}, deployTag: map[string]string{}, deployAt: map[string]string{}}
	out, err := run(args...)
	if err != nil {
		return s
	}
	for _, rec := range strings.Split(string(out), rs) {
		rec = strings.Trim(rec, "\n")
		if strings.TrimSpace(rec) == "" {
			continue
		}
		f := strings.SplitN(rec, fs, 9)
		if len(f) < 9 {
			continue
		}
		sha := strings.TrimSpace(f[0])
		if sha == "" {
			continue
		}
		s.parents[sha] = strings.Fields(f[1])
		chain, cycle, step := strings.TrimSpace(f[2]), strings.TrimSpace(f[3]), strings.TrimSpace(f[4])
		kind := strings.TrimSpace(f[5])
		if step != "" {
			s.ref[sha] = chain + "/" + cycle + "/" + step
			s.kind[sha] = kind
		}
		if tag := strings.TrimSpace(f[6]); tag != "" && step == "" {
			s.deployTag[sha] = tag
			at := strings.TrimSpace(f[7])
			if at == "" {
				at = strings.TrimSpace(f[8]) // Gil-Deployed-Leaf — 배포가 스스로 적어 둔 잎
			}
			s.deployAt[sha] = at
		}
	}
	return s
}

// nearestSuccess — from 에서 조상 쪽으로 **모든 부모**를 너비 우선으로 훑어, 처음 만나는
// 산 잎(success 스텝)의 chain/cycle/step. 없으면 "".
//
// 너비 우선인 이유: "가장 가까운"이 거리로 정의돼야 한다. 깊이 우선이면 어느 부모를 먼저
// 골랐느냐가 답을 정한다 — 그건 사실이 아니라 순회 순서다.
func (s *leafScan) nearestSuccess(from string) string {
	if s == nil {
		return ""
	}
	seen := map[string]bool{from: true}
	queue := []string{from}
	for len(queue) > 0 {
		cur := queue[0]
		queue = queue[1:]
		if s.kind[cur] == "success" {
			if r := s.ref[cur]; r != "" {
				return r
			}
		}
		for _, p := range s.parents[cur] {
			if !seen[p] {
				seen[p] = true
				queue = append(queue, p)
			}
		}
	}
	return ""
}

// cliGitBytes — CLI 쪽 git 실행기를 scanForDeploy 가 받는 모양으로 맞춘다.
func cliGitBytes(args ...string) ([]byte, error) {
	out, err := gitTry(args...)
	return []byte(out), err
}

// deployLiveLeaf — 지금 배포하려는 계보에서 **세상으로 나가는 산 잎**. 없으면 "".
//
// --at 으로 잎을 직접 가리켰고 그것이 산 잎이면 그 값이다(사람이 아는 사실이 우선).
// 그 밖에는 배포되는 가지 끝(층이 있으면 dev, 없으면 HEAD)에서 조상 쪽으로 훑어 찾는다.
// 두 번째 반환값은 **이 계보에 스텝이 하나라도 있었나**다. 스텝이 아예 없는 저장소(막
// `gil init` 한 자리, 문서만 있는 자리)는 "죽은 잎만 남았다"와 다른 상태다 — 거기서 산 잎을
// 요구하면, 정작 사람이 들어야 할 말(층이 아직 안 섰다 같은)이 이 거부에 가려진다.
// 이 검사가 막으려는 것은 **생각한 흔적이 있는데 그 끝이 다 죽은 계보**다.
func deployLiveLeaf(at string) (string, bool) {
	if at = strings.TrimSpace(at); at != "" {
		chain, rest, ok := cut(at, "/")
		if ok {
			cycle, step, ok2 := cut(rest, "/")
			if ok2 {
				for _, s := range currentCycle(chain, cycle) {
					if s.step == step && s.kind == "success" {
						return at, true // 가리킨 자리가 산 잎이다 — 더 찾을 것이 없다
					}
				}
			}
		}
	}
	tip := "HEAD"
	if hasDevLayer() {
		tip = devBranchName
	}
	sha, err := gitTry("rev-parse", tip)
	if err != nil {
		return "", false
	}
	sha = strings.TrimSpace(sha)
	s := scanForDeploy(cliGitBytes, sha)
	return s.nearestSuccess(sha), len(s.ref) > 0
}

// deployAttributions — 배포 마커 커밋 sha → 귀속된 스텝(chain/cycle/step). 선언이 있으면
// 그 값을(탐색 없이 — 배포한 쪽이 아는 사실이 읽는 쪽의 추측보다 정확하다), 없으면 조상
// 탐색으로. 그래도 없으면 빈 문자열이 남는다 — **그 사실도 값이다.** 뷰어는 그때 마커를
// 지우지 않고 층 레인에 "귀속 스텝 미상"으로 그린다.
func deployAttributions(run func(...string) ([]byte, error), revs ...string) map[string]string {
	s := scanForDeploy(run, revs...)
	out := map[string]string{}
	for sha := range s.deployTag {
		if at := s.deployAt[sha]; at != "" {
			out[sha] = at
			continue
		}
		out[sha] = s.nearestSuccess(sha)
	}
	return out
}
