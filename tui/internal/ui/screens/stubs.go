package screens

// Stub constructors. Each returns a Placeholder until the real screen lands.
// Replacing one means: add the real type in its own file, then drop the stub
// from this file (the real constructor takes the same signature).

import "github.com/neilfarmer/memoire/tui/internal/api"

func newStub(name string) Screen { return NewPlaceholder(name) }

func NewDashboard(c *api.Client) Screen { return newDashboard(c) }
func NewTasks(c *api.Client) Screen   { return newTasks(c) }
func NewNotes(c *api.Client) Screen   { return newNotes(c) }
func NewJournal(c *api.Client) Screen { return newJournal(c) }
func NewHabits(c *api.Client) Screen  { return newHabits(c) }
func NewGoals(c *api.Client) Screen   { return newGoals(c) }
func NewHealth(c *api.Client) Screen    { return newHealth(c) }
func NewNutrition(c *api.Client) Screen { return newNutrition(c) }
func NewFinances(c *api.Client) Screen  { return newFinances(c) }
func NewFeeds(c *api.Client) Screen     { return newFeeds(c) }
func NewBookmarks(c *api.Client) Screen { return newBookmarks(c) }
func NewFavorites(c *api.Client) Screen { return newFavorites(c) }
func NewAssistant(c *api.Client) Screen { return newAssistant(c) }
func NewSettings(c *api.Client) Screen  { return newSettings(c) }
func NewTokens(c *api.Client) Screen    { return newTokens(c) }
func NewAdmin(c *api.Client) Screen     { return newAdmin(c) }
