package ui

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/neilfarmer/memoire/tui/internal/api"
)

func newTestApp() *App {
	client := api.New("https://example.invalid", "pat_test")
	app := New(client, DefaultFactories(client))
	_ = app.Init()
	app.Update(tea.WindowSizeMsg{Width: 100, Height: 40})
	return app
}

func keyArrow(s string) tea.KeyMsg {
	switch s {
	case "up":
		return tea.KeyMsg{Type: tea.KeyUp}
	case "down":
		return tea.KeyMsg{Type: tea.KeyDown}
	case "right":
		return tea.KeyMsg{Type: tea.KeyRight}
	case "left":
		return tea.KeyMsg{Type: tea.KeyLeft}
	case "tab":
		return tea.KeyMsg{Type: tea.KeyTab}
	case "shift+tab":
		return tea.KeyMsg{Type: tea.KeyShiftTab}
	case "enter":
		return tea.KeyMsg{Type: tea.KeyEnter}
	case "esc":
		return tea.KeyMsg{Type: tea.KeyEscape}
	}
	return tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(s)}
}

func TestStartupFocus(t *testing.T) {
	app := newTestApp()
	if !app.sideFocus {
		t.Errorf("sideFocus should default to true (sidebar focused); got false")
	}
	if app.current != ScreenDashboard {
		t.Errorf("current should be Dashboard; got %s", app.current)
	}
}

func TestArrowDownFromStartupNavigatesSidebar(t *testing.T) {
	app := newTestApp()
	model, _ := app.Update(keyArrow("down"))
	a := model.(*App)
	if a.sideCursor != 1 {
		t.Errorf("down arrow should move sidebar cursor to 1; got %d", a.sideCursor)
	}
	if a.current != ScreenTasks {
		t.Errorf("current should preview-activate to Tasks; got %s", a.current)
	}
}

func TestSidebarArrowFocusWhenSideFocus(t *testing.T) {
	app := newTestApp()
	app.sideFocus = true
	model, _ := app.Update(keyArrow("down"))
	a := model.(*App)
	if a.sideCursor != 1 {
		t.Errorf("sideCursor should be 1 after down; got %d", a.sideCursor)
	}
	if a.current != ScreenTasks {
		t.Errorf("current should be Tasks (preview-activated); got %s", a.current)
	}
}

func TestArrowGoesToContentWhenContentFocused(t *testing.T) {
	app := newTestApp()
	app.sideFocus = false
	startCursor := app.sideCursor
	model, _ := app.Update(keyArrow("down"))
	a := model.(*App)
	if a.sideCursor != startCursor {
		t.Errorf("sideCursor should not change when content focused; got %d", a.sideCursor)
	}
	if a.sideFocus {
		t.Errorf("sideFocus should remain false")
	}
}

func TestBackslashJumpsToSidebar(t *testing.T) {
	app := newTestApp()
	model, _ := app.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'\\'}})
	a := model.(*App)
	if !a.sideFocus {
		t.Errorf("backslash should focus sidebar")
	}
}

func TestShiftTabTogglesFocus(t *testing.T) {
	app := newTestApp()
	app.sideFocus = false
	model, _ := app.Update(keyArrow("shift+tab"))
	a := model.(*App)
	if !a.sideFocus {
		t.Errorf("shift+tab should toggle to sidebar focus")
	}
	model, _ = a.Update(keyArrow("shift+tab"))
	a = model.(*App)
	if a.sideFocus {
		t.Errorf("shift+tab should toggle back to content focus")
	}
}

func TestEnterFromSidebarFocusesContent(t *testing.T) {
	app := newTestApp()
	app.sideFocus = true
	model, _ := app.Update(keyArrow("enter"))
	a := model.(*App)
	if a.sideFocus {
		t.Errorf("enter on sidebar should focus content")
	}
}

func TestSidebarFocusedHeaderRendersHints(t *testing.T) {
	app := newTestApp()
	app.sideFocus = true
	out := app.View()
	if !strings.Contains(out, "↑↓") {
		t.Errorf("sidebar focus hints missing")
	}
}
