package ui

import "time"

// Screen identifies a top-level view in the app.
type Screen string

const (
	ScreenDashboard Screen = "dashboard"
	ScreenTasks     Screen = "tasks"
	ScreenNotes     Screen = "notes"
	ScreenJournal   Screen = "journal"
	ScreenHabits    Screen = "habits"
	ScreenGoals     Screen = "goals"
	ScreenHealth    Screen = "health"
	ScreenNutrition Screen = "nutrition"
	ScreenFinances  Screen = "finances"
	ScreenFeeds     Screen = "feeds"
	ScreenBookmarks Screen = "bookmarks"
	ScreenFavorites Screen = "favorites"
	ScreenSettings  Screen = "settings"
	ScreenTokens    Screen = "tokens"
	ScreenAssistant Screen = "assistant"
	ScreenAdmin     Screen = "admin"
)

// NavigateMsg requests a screen switch.
type NavigateMsg struct{ To Screen }

// FlashMsg posts a transient status message to the status bar.
type FlashMsg struct {
	Text  string
	Level FlashLevel
	TTL   time.Duration
}

type FlashLevel int

const (
	FlashInfo FlashLevel = iota
	FlashSuccess
	FlashWarn
	FlashError
)

// FlashClearMsg fires after a FlashMsg's TTL.
type FlashClearMsg struct{ ID int64 }

// ErrorMsg surfaces an unexpected error.
type ErrorMsg struct{ Err error }

// QuitConfirmMsg toggles the quit-confirm overlay.
type QuitConfirmMsg struct{}

// HelpToggleMsg toggles the help overlay.
type HelpToggleMsg struct{}

// PaletteToggleMsg toggles the command palette overlay.
type PaletteToggleMsg struct{}
