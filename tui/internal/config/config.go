package config

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/BurntSushi/toml"
)

type Config struct {
	API  APIConfig  `toml:"api"`
	Auth AuthConfig `toml:"auth"`
}

type APIConfig struct {
	URL string `toml:"url"`
}

type AuthConfig struct {
	PAT string `toml:"pat"`
}

const (
	envAPIURL = "MEMOIRE_API_URL"
	envPAT    = "MEMOIRE_PAT"
)

// Path returns the resolved config file path. Honors XDG_CONFIG_HOME, falling
// back to $HOME/.config/memoire-tui/config.toml.
func Path(override string) (string, error) {
	if override != "" {
		return override, nil
	}
	if x := os.Getenv("XDG_CONFIG_HOME"); x != "" {
		return filepath.Join(x, "memoire-tui", "config.toml"), nil
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, ".config", "memoire-tui", "config.toml"), nil
}

// Load resolves config in order: env vars > file. Returns the merged Config
// and the file path used (even if file did not exist). The caller decides
// whether to prompt the user when fields are missing.
func Load(override string) (Config, string, error) {
	path, err := Path(override)
	if err != nil {
		return Config{}, "", err
	}
	cfg := Config{}
	if data, err := os.ReadFile(path); err == nil {
		if _, err := toml.Decode(string(data), &cfg); err != nil {
			return cfg, path, fmt.Errorf("parse %s: %w", path, err)
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return cfg, path, fmt.Errorf("read %s: %w", path, err)
	}
	if v := os.Getenv(envAPIURL); v != "" {
		cfg.API.URL = v
	}
	if v := os.Getenv(envPAT); v != "" {
		cfg.Auth.PAT = v
	}
	cfg.API.URL = strings.TrimRight(cfg.API.URL, "/")
	return cfg, path, nil
}

// Save writes the config to path with 0600 permissions, creating parent dirs
// as needed.
func Save(cfg Config, path string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o600)
	if err != nil {
		return err
	}
	defer f.Close()
	return toml.NewEncoder(f).Encode(cfg)
}

// Validate returns nil when the config has every field needed to make API
// calls. Used by the entry point to decide whether to launch the first-run
// flow.
func (c Config) Validate() error {
	if c.API.URL == "" {
		return errors.New("api.url is empty")
	}
	if c.Auth.PAT == "" {
		return errors.New("auth.pat is empty")
	}
	return nil
}
