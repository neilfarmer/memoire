package ui

import (
	"testing"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/neilfarmer/memoire/tui/internal/api"
)

// TestLetterKeyDropsSidebarFocus reproduces the lockup case: user is on the
// Tasks screen, sidebar is focused (default), and presses `e` to edit. The
// app must drop sidebar focus so the screen receives the key and so future
// arrow keys go to the form, not the sidebar.
func TestLetterKeyDropsSidebarFocus(t *testing.T) {
	client := api.New("https://example.invalid", "pat_test")
	app := New(client, DefaultFactories(client))
	_ = app.Init()
	app.Update(tea.WindowSizeMsg{Width: 100, Height: 40})

	// jump to tasks
	app.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'2'}})
	app.sideFocus = true // simulate the buggy state

	app.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'e'}})
	if app.sideFocus {
		t.Errorf("pressing letter key with sidebar focused should drop focus to content")
	}

	// Now arrow keys should not move sidebar.
	startCursor := app.sideCursor
	app.Update(tea.KeyMsg{Type: tea.KeyDown})
	if app.sideCursor != startCursor {
		t.Errorf("after dropping sidebar focus, arrows should not move sidebar; got cursor %d", app.sideCursor)
	}
}
