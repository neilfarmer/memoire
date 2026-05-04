package screens

import (
	"github.com/charmbracelet/bubbles/list"
)

// SimpleItem is a generic list item carrying a title, description, and any
// underlying payload value.
type SimpleItem struct {
	TitleText string
	Desc      string
	Value     any
}

func (i SimpleItem) FilterValue() string { return i.TitleText + " " + i.Desc }
func (i SimpleItem) Title() string       { return i.TitleText }
func (i SimpleItem) Description() string { return i.Desc }

// MakeList builds a list.Model with our standard styling.
func MakeList(title string, items []list.Item, width, height int) list.Model {
	l := list.New(items, list.NewDefaultDelegate(), width, height)
	l.Title = title
	l.SetShowStatusBar(true)
	l.SetFilteringEnabled(true)
	l.SetShowHelp(false)
	return l
}
