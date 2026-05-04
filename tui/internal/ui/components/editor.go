package components

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
)

// EditorClosedMsg returns from EditExternal once the editor exits.
type EditorClosedMsg struct {
	Content string
	Err     error
}

// EditExternal launches $EDITOR (default: vi) on a tmpfile seeded with the
// given content. Uses tea.ExecProcess so bubbletea suspends the alt-screen
// + raw mode while the editor runs and restores terminal state on exit.
// Calling exec.Command.Run() directly while tea owns the terminal corrupts
// the session.
func EditExternal(initial, ext string) tea.Cmd {
	editor := os.Getenv("EDITOR")
	if editor == "" {
		editor = "vi"
	}
	f, err := os.CreateTemp(os.TempDir(), "memoire-*"+normaliseExt(ext))
	if err != nil {
		return func() tea.Msg { return EditorClosedMsg{Err: err} }
	}
	path := f.Name()
	if _, err := f.WriteString(initial); err != nil {
		_ = f.Close()
		_ = os.Remove(path)
		return func() tea.Msg { return EditorClosedMsg{Err: err} }
	}
	_ = f.Close()

	parts := strings.Fields(editor)
	args := append(parts[1:], path)
	cmd := exec.Command(parts[0], args...)
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	return tea.ExecProcess(cmd, func(execErr error) tea.Msg {
		defer os.Remove(path)
		if execErr != nil {
			return EditorClosedMsg{Err: fmt.Errorf("%s: %w", editor, execErr)}
		}
		buf, err := os.ReadFile(path)
		if err != nil {
			return EditorClosedMsg{Err: err}
		}
		return EditorClosedMsg{Content: string(buf)}
	})
}

func normaliseExt(ext string) string {
	if ext == "" {
		return ".md"
	}
	if filepath.Ext(ext) == "" {
		return "." + strings.TrimPrefix(ext, ".")
	}
	return ext
}
