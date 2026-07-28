// flags.go — 참조 구현(argparse)의 동작을 맞추는 작은 플래그 파서.
//
// 표준 flag 패키지는 (1) 위치인자와 플래그 혼합, (2) --parent 같은 반복 플래그를
// argparse의 action="append"처럼 다루기가 번거롭다. gil.py의 인자 규약을 정확히
// 재현하려고 얇은 파서를 둔다: --key value 형태만 받고, 나머지는 위치인자.
package main

import (
	"sort"
	"strings"
)

type flagSet struct {
	prog  string
	strs  map[string]*string
	lists map[string]*[]string
	bools map[string]*bool
}

func newFlags(prog string) *flagSet {
	return &flagSet{prog: prog, strs: map[string]*string{}, lists: map[string]*[]string{}, bools: map[string]*bool{}}
}

// str 은 --name value 단일값 플래그를 등록한다.
func (f *flagSet) str(name, def string) *string {
	v := def
	f.strs[name] = &v
	return f.strs[name]
}

// boolFlag 는 값 없는 스위치(--name)를 등록한다 — 다음 토큰을 값으로 삼지 않는다.
func (f *flagSet) boolFlag(name string) *bool {
	v := false
	f.bools[name] = &v
	return f.bools[name]
}

// strList 는 --name value 를 여러 번 받는 반복 플래그를 등록한다(argparse append).
func (f *flagSet) strList(name string) *[]string {
	v := []string{}
	f.lists[name] = &v
	return f.lists[name]
}

// parse 는 args를 훑어 플래그를 채우고 위치인자를 반환한다.
func (f *flagSet) parse(args []string) []string {
	var pos []string
	for i := 0; i < len(args); i++ {
		a := args[i]
		if strings.HasPrefix(a, "--") {
			name := a[2:]
			// --key=value 형태도 허용
			if eq := strings.Index(name, "="); eq >= 0 {
				val := name[eq+1:]
				name = name[:eq]
				f.assign(name, val)
				continue
			}
			// bool 스위치: 값을 소비하지 않는다.
			if p, ok := f.bools[name]; ok {
				*p = true
				continue
			}
			// --key value: 다음 토큰을 값으로
			if i+1 < len(args) {
				f.assign(name, args[i+1])
				i++
			} else {
				f.assign(name, "")
			}
		} else {
			pos = append(pos, a)
		}
	}
	return pos
}

func (f *flagSet) assign(name, val string) {
	if p, ok := f.strs[name]; ok {
		*p = val
		return
	}
	if p, ok := f.lists[name]; ok {
		*p = append(*p, val)
		return
	}
	msg := "거부: " + f.prog + " — 알 수 없는 플래그 --" + name
	if g := f.nearestFlag(name); g != "" {
		msg += "\n  혹시 --" + g + " 인가?"
	}
	msg += "\n  이 명령이 받는 플래그: " + strings.Join(f.knownFlags(), " ") +
		"\n  전체 사용법: " + f.prog + " --help"
	die(msg)
}

// knownFlags — 이 명령이 실제로 받는 플래그들(정렬). 거부가 "뭘 쓸 수 있는지"를 그 자리에서
// 알려주면 사람도 LLM 도 help 를 따로 찾아 헤매지 않는다(이슈 #47 G3).
func (f *flagSet) knownFlags() []string {
	var out []string
	for k := range f.strs {
		out = append(out, "--"+k)
	}
	for k := range f.lists {
		out = append(out, "--"+k)
	}
	for k := range f.bools {
		out = append(out, "--"+k)
	}
	sort.Strings(out)
	return out
}

// nearestFlag — 오타에 가장 가까운 플래그 하나(편집거리 2 이내). "--title-body"→"--title".
func (f *flagSet) nearestFlag(bad string) string {
	lb := strings.ToLower(bad)
	// 접두/포함 일치를 먼저 본다 — "--title-body" 처럼 **붙여 쓴** 오입력은 편집거리가 멀지만
	// 뜻은 명백하다(실측: --title-body 를 추측해 씀). 이게 단순 오타보다 흔하다.
	for _, k := range f.knownFlags() {
		k = strings.TrimPrefix(k, "--")
		if k != lb && (strings.HasPrefix(lb, k) || strings.HasPrefix(k, lb)) {
			return k
		}
	}
	best, bestD := "", 3
	for _, k := range f.knownFlags() {
		k = strings.TrimPrefix(k, "--")
		if d := editDistance(lb, k); d < bestD {
			best, bestD = k, d
		}
	}
	return best
}
