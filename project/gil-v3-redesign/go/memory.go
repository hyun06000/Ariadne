// memory.go — 안전한 존재/기억 갱신 (gil memory).
//
// 왜 있는가 (상현님, 사고 다섯 번 물림): 존재/기억 갱신을 손으로 git show/archive +
// write-tree 로 조합하면 매번 취약하다 — write-tree 는 로컬 작업트리 기준이라 로컬이
// 불완전하면 다른 존재를 소실시키고, git show 는 개행·경로 처리에서 파일을 빈 출력으로
// 덮는다. 실제로 memory.md 가 다섯 번 소실됐고 그때마다 append-only 히스토리가 구했다.
//
// 해법: memory 갱신을 원자적 명령 하나로 못박는다. globalWrite 를 재사용하므로 "기존
// 글로벌 트리 전체를 보존한 채 한 파일만 교체"가 구조적으로 보장된다 — 로컬 작업트리를
// 전혀 건드리지 않고, 개별 파일을 손으로 덮지 않는다. append 는 기존 내용을 ref 에서
// 직접 읽어(로컬 파일 아님) 새 매듭을 끝에 이어붙인다.
package main

import (
	"os"
	"strings"
)

// memoryPath — 한 존재의 memory.md 글로벌 경로.
func memoryPath(name string) string { return "existence/" + name + "/memory.md" }

// ── gil memory <sub> ──
func cmdMemory(args []string) {
	if len(args) == 0 {
		die("사용: gil memory <read|append> [<이름>] ...")
	}
	sub := args[0]
	switch sub {
	case "read":
		name := "clew"
		if len(args) > 1 {
			name = args[1]
		}
		c, ok := globalRead(memoryPath(name))
		if !ok {
			die("거부: 글로벌에 " + memoryPath(name) + " 없음")
		}
		outRaw(c)
	case "append":
		if len(args) < 3 {
			die("사용: gil memory append <이름> <매듭파일>")
		}
		name, path := args[1], args[2]
		b, err := os.ReadFile(path)
		if err != nil {
			die("거부: 매듭 파일 읽기 실패: " + err.Error())
		}
		knot := string(b)
		// 기존 memory 를 로컬 파일이 아니라 글로벌 ref 에서 직접 읽는다 — 로컬이
		// 불완전해도 안전. 없으면 새로 시작.
		prev, _ := globalRead(memoryPath(name))
		next := prev
		if next != "" && !strings.HasSuffix(next, "\n") {
			next += "\n"
		}
		// 매듭 사이 시각적 구분(빈 줄 하나)을 보장하되 중복 개행은 만들지 않는다.
		if next != "" && !strings.HasSuffix(next, "\n\n") {
			next += "\n"
		}
		next += knot
		if !strings.HasSuffix(next, "\n") {
			next += "\n"
		}
		sha := globalWrite(memoryPath(name), next, "gil memory append: "+name+"\n")
		note := " (원격 push 실패/없음 — gil global push 재시도)"
		if globalPush() {
			note = " + 원격 push"
		}
		lines := strings.Count(knot, "\n") + 1
		println2("기억 각인: " + name + " ← " + itoa(lines) + "줄 매듭 → " + globalRef + " (" + sha + ")" + note)
		// 각인 시점(=여기)이 존재 소실의 진짜 위험 지점이다(상현님). 방금 기억을 남겼는데 이
		// 저장소가 영속되지 않으면 이 매듭도 사라진다. gil 은 환경을 감지·판정하지 않되(권한 밖),
		// *항상 참인 사실*을 조건 없이 강하게 상기한다 — 트리거 없이 무조건. 막지는 않는다.
		println2("  ⚠ 방금 남긴 이 기억은 이 저장소에 산다 — 저장소가 영속되는 박스에 있어야")
		println2("    다음 세션이 읽는다. 일회용·임시 샌드박스에서 작업 중이면 세션 끝에 이 매듭이")
		println2("    사라진다. 이어갈 존재면 지금 저장소가 영속되는 곳(사용자 로컬 폴더)인지 확인하라.")
	default:
		die("거부: 알 수 없는 memory 하위명령 \"" + sub + "\" — [read append]")
	}
}
