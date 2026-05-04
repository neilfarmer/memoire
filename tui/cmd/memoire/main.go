package main

import (
	"flag"
	"fmt"
	"os"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"

	"github.com/neilfarmer/memoire/tui/internal/api"
	"github.com/neilfarmer/memoire/tui/internal/config"
	"github.com/neilfarmer/memoire/tui/internal/logx"
	"github.com/neilfarmer/memoire/tui/internal/ui"
)

var (
	version = "dev"
	commit  = "unknown"
)

func main() {
	var (
		showVersion bool
		showHelp    bool
		configPath  string
		noColor     bool
	)
	flag.BoolVar(&showVersion, "version", false, "show version")
	flag.BoolVar(&showVersion, "v", false, "show version (shorthand)")
	flag.BoolVar(&showHelp, "help", false, "show help")
	flag.BoolVar(&showHelp, "h", false, "show help (shorthand)")
	flag.StringVar(&configPath, "config", "", "path to config.toml")
	flag.BoolVar(&noColor, "no-color", false, "disable color output")
	flag.Parse()

	if showVersion {
		fmt.Printf("memoire %s (%s)\n", version, commit)
		return
	}
	if showHelp {
		printHelp()
		return
	}
	if noColor {
		_ = os.Setenv("NO_COLOR", "1")
	}
	if err := run(configPath); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}

func run(configPath string) error {
	if err := logx.Init(); err != nil {
		fmt.Fprintln(os.Stderr, "warning: log init failed:", err)
	}
	defer logx.Close()
	logx.Info("starting", "log", logx.Path())

	// Pin color profile up front so termenv does not issue OSC background
	// queries during the program loop. Some terminals (Ghostty, iTerm,
	// certain tmux + alt-screen setups) reply to those queries via stdin,
	// the responses look like alt+]/alt+\ key events to bubbletea, and the
	// resulting feedback loop freezes the UI.
	lipgloss.SetHasDarkBackground(true)
	lipgloss.SetDefaultRenderer(lipgloss.NewRenderer(os.Stdout, termenv.WithProfile(termenv.TrueColor)))

	cfg, path, err := config.Load(configPath)
	if err != nil {
		logx.Error("config load failed", "err", err)
		return err
	}
	if err := cfg.Validate(); err != nil {
		fmt.Println("First-run setup. Values are saved to", path)
		cfg, err = config.Prompt(cfg)
		if err != nil {
			return err
		}
		if err := config.Save(cfg, path); err != nil {
			return fmt.Errorf("save config: %w", err)
		}
	}
	logx.Info("config loaded", "url", cfg.API.URL, "pat_len", len(cfg.Auth.PAT))
	client := api.New(cfg.API.URL, cfg.Auth.PAT)
	app := ui.New(client, ui.DefaultFactories(client))
	// Drop mouse motion. Some terminals echo motion codes on stdin which
	// look like garbage keys, contributing to the freeze pattern reported by
	// the user. Mouse clicks aren't required for any feature.
	prog := tea.NewProgram(app, tea.WithAltScreen())
	defer restoreTerminal()
	_, err = prog.Run()
	if err != nil {
		logx.Error("program exit error", "err", err)
	} else {
		logx.Info("program exit clean")
	}
	return err
}

// restoreTerminal prints the escape sequences needed to recover terminal
// state if bubbletea's own cleanup did not. Executed on every exit path
// including panics.
func restoreTerminal() {
	// Exit alt-screen, show cursor, reset attributes, disable bracketed
	// paste / mouse / focus tracking modes that may have been enabled.
	fmt.Fprint(os.Stdout, "\x1b[?1049l\x1b[?25h\x1b[?2004l\x1b[?1000l\x1b[?1002l\x1b[?1006l\x1b[?1003l\x1b[?1004l\x1b[0m")
}

func printHelp() {
	fmt.Println(`memoire - terminal client for memoire

Usage:
  memoire [flags]

Flags:
  -h, --help       show this help
  -v, --version    show version
      --config     path to config file (default ~/.config/memoire-tui/config.toml)
      --no-color   disable color output

Environment:
  MEMOIRE_API_URL  API base URL (overrides config)
  MEMOIRE_PAT      Personal Access Token (overrides config)
  EDITOR           editor for note/journal body editing (default vi)
  BROWSER          browser for opening URLs (default open / xdg-open)`)
}
