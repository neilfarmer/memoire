package ui

import "github.com/charmbracelet/bubbles/key"

type GlobalKeys struct {
	Quit      key.Binding
	Help      key.Binding
	Palette   key.Binding
	Sidebar   key.Binding
	Refresh   key.Binding
	Dashboard key.Binding
	Tasks     key.Binding
	Notes     key.Binding
	Journal   key.Binding
	Habits    key.Binding
	Goals     key.Binding
	Health    key.Binding
	Nutrition key.Binding
	Finances  key.Binding
	Feeds     key.Binding
	Bookmarks key.Binding
	Favorites key.Binding
	Settings  key.Binding
	Tokens    key.Binding
	Assistant key.Binding
}

func DefaultKeys() GlobalKeys {
	return GlobalKeys{
		Quit:      key.NewBinding(key.WithKeys("ctrl+c", "ctrl+q"), key.WithHelp("ctrl+q", "quit")),
		Help:      key.NewBinding(key.WithKeys("?"), key.WithHelp("?", "help")),
		Palette:   key.NewBinding(key.WithKeys("ctrl+p"), key.WithHelp("ctrl+p", "command palette")),
		Sidebar:   key.NewBinding(key.WithKeys("tab"), key.WithHelp("tab", "focus sidebar")),
		Refresh:   key.NewBinding(key.WithKeys("ctrl+r"), key.WithHelp("ctrl+r", "refresh")),
		Dashboard: key.NewBinding(key.WithKeys("g d")),
		Tasks:     key.NewBinding(key.WithKeys("g t")),
		Notes:     key.NewBinding(key.WithKeys("g n")),
		Journal:   key.NewBinding(key.WithKeys("g j")),
		Habits:    key.NewBinding(key.WithKeys("g h")),
		Goals:     key.NewBinding(key.WithKeys("g o")),
	}
}

// SidebarOrder is the canonical screen order in the sidebar and for numeric
// shortcuts (1..9).
var SidebarOrder = []Screen{
	ScreenDashboard,
	ScreenTasks,
	ScreenNotes,
	ScreenJournal,
	ScreenHabits,
	ScreenGoals,
	ScreenHealth,
	ScreenNutrition,
	ScreenFinances,
	ScreenFeeds,
	ScreenBookmarks,
	ScreenFavorites,
	ScreenAssistant,
	ScreenSettings,
	ScreenTokens,
	ScreenAdmin,
}

// SidebarIcons gives a single-glyph icon for each screen.
var SidebarIcons = map[Screen]string{
	ScreenDashboard: "◆",
	ScreenTasks:     "✓",
	ScreenNotes:     "▤",
	ScreenJournal:   "◐",
	ScreenHabits:    "◉",
	ScreenGoals:     "◈",
	ScreenHealth:    "♥",
	ScreenNutrition: "♦",
	ScreenFinances:  "$",
	ScreenFeeds:     "≋",
	ScreenBookmarks: "⚓",
	ScreenFavorites: "★",
	ScreenAssistant: "✦",
	ScreenSettings:  "⚙",
	ScreenTokens:    "⚿",
	ScreenAdmin:     "⚒",
}

// SidebarIcon returns the icon for a screen or a default bullet.
func SidebarIcon(s Screen) string {
	if v, ok := SidebarIcons[s]; ok {
		return v
	}
	return "•"
}

// SidebarLabels gives the human label for each screen.
var SidebarLabels = map[Screen]string{
	ScreenDashboard: "Dashboard",
	ScreenTasks:     "Tasks",
	ScreenNotes:     "Notes",
	ScreenJournal:   "Journal",
	ScreenHabits:    "Habits",
	ScreenGoals:     "Goals",
	ScreenHealth:    "Health",
	ScreenNutrition: "Nutrition",
	ScreenFinances:  "Finances",
	ScreenFeeds:     "Feeds",
	ScreenBookmarks: "Bookmarks",
	ScreenFavorites: "Favorites",
	ScreenAssistant: "Assistant",
	ScreenSettings:  "Settings",
	ScreenTokens:    "Tokens",
	ScreenAdmin:     "Admin",
}
