package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadFromFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "config.toml")
	if err := os.WriteFile(path, []byte("[api]\nurl = \"https://example.com\"\n[auth]\npat = \"pat_xyz\"\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("MEMOIRE_API_URL", "")
	t.Setenv("MEMOIRE_PAT", "")
	cfg, _, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if cfg.API.URL != "https://example.com" {
		t.Errorf("api.url=%q", cfg.API.URL)
	}
	if cfg.Auth.PAT != "pat_xyz" {
		t.Errorf("auth.pat=%q", cfg.Auth.PAT)
	}
}

func TestEnvOverridesFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "config.toml")
	_ = os.WriteFile(path, []byte("[api]\nurl = \"https://file\"\n[auth]\npat = \"file_pat\"\n"), 0o600)
	t.Setenv("MEMOIRE_API_URL", "https://env")
	t.Setenv("MEMOIRE_PAT", "env_pat")
	cfg, _, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if cfg.API.URL != "https://env" || cfg.Auth.PAT != "env_pat" {
		t.Errorf("env did not override: %+v", cfg)
	}
}

func TestSaveRoundTrip(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "out", "config.toml")
	cfg := Config{API: APIConfig{URL: "https://api"}, Auth: AuthConfig{PAT: "pat_1"}}
	if err := Save(cfg, path); err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0o600 {
		t.Errorf("perms=%v", info.Mode().Perm())
	}
	t.Setenv("MEMOIRE_API_URL", "")
	t.Setenv("MEMOIRE_PAT", "")
	got, _, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if got != cfg {
		t.Errorf("got %+v want %+v", got, cfg)
	}
}

func TestPathXDG(t *testing.T) {
	t.Setenv("XDG_CONFIG_HOME", "/tmp/xdg")
	p, err := Path("")
	if err != nil {
		t.Fatal(err)
	}
	want := "/tmp/xdg/memoire-tui/config.toml"
	if p != want {
		t.Errorf("path=%s want %s", p, want)
	}
}

func TestValidate(t *testing.T) {
	if err := (Config{}).Validate(); err == nil {
		t.Error("empty should fail")
	}
	if err := (Config{API: APIConfig{URL: "x"}, Auth: AuthConfig{PAT: "y"}}).Validate(); err != nil {
		t.Errorf("valid failed: %v", err)
	}
}

func TestTrailingSlashStripped(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "c.toml")
	_ = os.WriteFile(path, []byte("[api]\nurl = \"https://x.com/\"\n[auth]\npat = \"p\"\n"), 0o600)
	t.Setenv("MEMOIRE_API_URL", "")
	t.Setenv("MEMOIRE_PAT", "")
	cfg, _, _ := Load(path)
	if cfg.API.URL != "https://x.com" {
		t.Errorf("got %q", cfg.API.URL)
	}
}
