package config

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/huh"
)

// Prompt runs an interactive form to fill missing fields and returns the
// populated config. Callers should Save() afterwards if they want it
// persisted.
func Prompt(initial Config) (Config, error) {
	cfg := initial
	form := huh.NewForm(
		huh.NewGroup(
			huh.NewInput().
				Title("API URL").
				Description("Base URL of your memoire API (no trailing slash).").
				Placeholder("https://api.memoire.example.com").
				Value(&cfg.API.URL).
				Validate(func(s string) error {
					s = strings.TrimSpace(s)
					if s == "" {
						return fmt.Errorf("required")
					}
					if !strings.HasPrefix(s, "https://") && !strings.HasPrefix(s, "http://") {
						return fmt.Errorf("must start with http:// or https://")
					}
					return nil
				}),
			huh.NewInput().
				Title("Personal Access Token").
				Description("Generated from Settings > API Tokens in the web UI.").
				Placeholder("pat_...").
				EchoMode(huh.EchoModePassword).
				Value(&cfg.Auth.PAT).
				Validate(func(s string) error {
					if strings.TrimSpace(s) == "" {
						return fmt.Errorf("required")
					}
					return nil
				}),
		),
	)
	if err := form.Run(); err != nil {
		return cfg, err
	}
	cfg.API.URL = strings.TrimRight(strings.TrimSpace(cfg.API.URL), "/")
	cfg.Auth.PAT = strings.TrimSpace(cfg.Auth.PAT)
	return cfg, nil
}
