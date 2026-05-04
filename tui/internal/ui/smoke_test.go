package ui

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/neilfarmer/memoire/tui/internal/api"
)

// TestSmokeAllScreens drives the App through every sidebar entry and
// confirms each screen renders something non-empty containing its own
// title. This catches missing screens, type-assertion regressions in the
// factory map, and panics in initial render paths.
func TestSmokeAllScreens(t *testing.T) {
	client := api.New("https://example.invalid", "pat_smoke")
	app := New(client, DefaultFactories(client))
	_ = app.Init()
	model, _ := app.Update(tea.WindowSizeMsg{Width: 120, Height: 40})

	for i, s := range SidebarOrder {
		num := rune('1' + i%9)
		// numeric shortcut handles 1..9; for entries beyond 9, route via
		// NavigateMsg directly.
		var m tea.Model
		if i < 9 {
			m, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{num}})
		} else {
			m, _ = model.Update(NavigateMsg{To: s})
		}
		model = m
		out := model.View()
		if out == "" {
			t.Errorf("%s: empty render", s)
			continue
		}
		want := SidebarLabels[s]
		if !strings.Contains(out, want) {
			t.Errorf("%s: render missing label %q", s, want)
		}
	}
}
