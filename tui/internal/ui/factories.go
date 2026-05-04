package ui

import (
	"github.com/neilfarmer/memoire/tui/internal/api"
	"github.com/neilfarmer/memoire/tui/internal/ui/screens"
)

// DefaultFactories registers a Placeholder for every Screen. Real screens
// replace entries here as they're implemented.
func DefaultFactories(client *api.Client) map[Screen]ScreenFactory {
	out := map[Screen]ScreenFactory{}
	for _, s := range SidebarOrder {
		label := SidebarLabels[s]
		s := s // capture
		_ = label
		out[s] = func(c *api.Client) screens.Screen {
			return screens.NewPlaceholder(SidebarLabels[s])
		}
	}
	// Real screen factories override the placeholders.
	out[ScreenDashboard] = func(c *api.Client) screens.Screen { return screens.NewDashboard(c) }
	out[ScreenTasks] = func(c *api.Client) screens.Screen { return screens.NewTasks(c) }
	out[ScreenNotes] = func(c *api.Client) screens.Screen { return screens.NewNotes(c) }
	out[ScreenJournal] = func(c *api.Client) screens.Screen { return screens.NewJournal(c) }
	out[ScreenHabits] = func(c *api.Client) screens.Screen { return screens.NewHabits(c) }
	out[ScreenGoals] = func(c *api.Client) screens.Screen { return screens.NewGoals(c) }
	out[ScreenHealth] = func(c *api.Client) screens.Screen { return screens.NewHealth(c) }
	out[ScreenNutrition] = func(c *api.Client) screens.Screen { return screens.NewNutrition(c) }
	out[ScreenFinances] = func(c *api.Client) screens.Screen { return screens.NewFinances(c) }
	out[ScreenFeeds] = func(c *api.Client) screens.Screen { return screens.NewFeeds(c) }
	out[ScreenBookmarks] = func(c *api.Client) screens.Screen { return screens.NewBookmarks(c) }
	out[ScreenFavorites] = func(c *api.Client) screens.Screen { return screens.NewFavorites(c) }
	out[ScreenAssistant] = func(c *api.Client) screens.Screen { return screens.NewAssistant(c) }
	out[ScreenSettings] = func(c *api.Client) screens.Screen { return screens.NewSettings(c) }
	out[ScreenTokens] = func(c *api.Client) screens.Screen { return screens.NewTokens(c) }
	out[ScreenAdmin] = func(c *api.Client) screens.Screen { return screens.NewAdmin(c) }
	return out
}
