package main
import ("os";"path/filepath";"testing")
func TestSHAGate(t *testing.T){
  d:=t.TempDir()
  bin:=filepath.Join(d,"gil-linux-amd64")
  os.WriteFile(bin,[]byte("REALBYTES"),0o644)
  sums:=filepath.Join(d,"SHA256SUMS")
  // forge a wrong declared hash
  os.WriteFile(sums,[]byte("deadbeef00000000000000000000000000000000000000000000000000000000  gil-linux-amd64\n"),0o644)
  declared,_:=declaredSHA256(sums,"gil-linux-amd64")
  actual,_:=sha256File(bin)
  if declared==actual { t.Fatal("expected mismatch") }
  if declared!="deadbeef00000000000000000000000000000000000000000000000000000000" { t.Fatalf("bad declared %s",declared) }
  // matching case
  os.WriteFile(sums,[]byte(actual+"  gil-linux-amd64\n"),0o644)
  d2,_:=declaredSHA256(sums,"gil-linux-amd64")
  if d2!=actual { t.Fatal("expected match") }
  // missing asset
  m,_:=declaredSHA256(sums,"gil-darwin-arm64")
  if m!="" { t.Fatal("expected empty for missing asset") }
}
