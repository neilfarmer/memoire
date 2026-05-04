package ui

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/neilfarmer/memoire/tui/internal/api"
)

func TestAppRendersAfterResize(t *testing.T) {
	client := api.New("https://example.com", "pat_test")
	app := New(client, DefaultFactories(client))
	// Init runs before first render in real usage, so call it.
	_ = app.Init()
	model, _ := app.Update(tea.WindowSizeMsg{Width: 100, Height: 40})
	out := model.View()
	if out == "" {
		t.Fatal("empty view")
	}
	if !strings.Contains(out, "memoire") {
		t.Errorf("expected app name in header, got: %q", out[:min(200, len(out))])
	}
	if !strings.Contains(out, "Dashboard") {
		t.Errorf("expected sidebar entry Dashboard, got: %q", out[:min(200, len(out))])
	}
}

func TestNumericNavigation(t *testing.T) {
	client := api.New("https://example.com", "pat_test")
	app := New(client, DefaultFactories(client))
	_ = app.Init()
	app.Update(tea.WindowSizeMsg{Width: 100, Height: 40})
	// "2" should switch to Tasks (index 1 in SidebarOrder, key "2").
	model, _ := app.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'2'}})
	a := model.(*App)
	if a.current != ScreenTasks {
		t.Errorf("expected current=tasks, got %s", a.current)
	}
}

func TestHelpToggle(t *testing.T) {
	client := api.New("https://example.com", "pat_test")
	app := New(client, DefaultFactories(client))
	_ = app.Init()
	app.Update(tea.WindowSizeMsg{Width: 100, Height: 40})
	model, _ := app.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'?'}})
	view := model.View()
	if !strings.Contains(view, "Help") {
		t.Errorf("expected Help overlay, got: %q", view[:min(200, len(view))])
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
