// Package logx wraps slog with a default file destination.
//
// Set MEMOIRE_LOG to a file path to enable. Default: /tmp/memoire-tui.log.
// MEMOIRE_LOG=off disables logging entirely.
package logx

import (
	"io"
	"log/slog"
	"os"
)

var (
	enabled bool
	logger  *slog.Logger
	out     io.Closer
)

// Init opens the log file (or stays a no-op if disabled). Safe to call once
// from main.
func Init() error {
	dest := os.Getenv("MEMOIRE_LOG")
	if dest == "off" {
		logger = slog.New(slog.NewTextHandler(io.Discard, nil))
		return nil
	}
	if dest == "" {
		dest = "/tmp/memoire-tui.log"
	}
	f, err := os.OpenFile(dest, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		logger = slog.New(slog.NewTextHandler(io.Discard, nil))
		return err
	}
	out = f
	enabled = true
	logger = slog.New(slog.NewTextHandler(f, &slog.HandlerOptions{Level: slog.LevelDebug}))
	logger.Info("memoire-tui started", "log_path", dest, "pid", os.Getpid())
	return nil
}

// Close flushes and closes the log file.
func Close() {
	if out != nil {
		_ = out.Close()
	}
}

// Path returns the active log path or "off".
func Path() string {
	if !enabled {
		return "off"
	}
	if dest := os.Getenv("MEMOIRE_LOG"); dest != "" {
		return dest
	}
	return "/tmp/memoire-tui.log"
}

func get() *slog.Logger {
	if logger == nil {
		logger = slog.New(slog.NewTextHandler(io.Discard, nil))
	}
	return logger
}

func Debug(msg string, args ...any) { get().Debug(msg, args...) }
func Info(msg string, args ...any)  { get().Info(msg, args...) }
func Warn(msg string, args ...any)  { get().Warn(msg, args...) }
func Error(msg string, args ...any) { get().Error(msg, args...) }
