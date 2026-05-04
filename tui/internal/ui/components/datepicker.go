package components

import (
	"fmt"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/styles"
)

// DateGrid renders a 6x7 month calendar with the given date highlighted and
// optional dot markers on dates with content (e.g. journal entries).
type DateGrid struct {
	Selected time.Time
	Markers  map[string]bool
}

func (g DateGrid) View() string {
	first := time.Date(g.Selected.Year(), g.Selected.Month(), 1, 0, 0, 0, 0, g.Selected.Location())
	leadIn := int(first.Weekday())
	rows := []string{
		styles.Title.Render(g.Selected.Format("January 2006")),
		styles.MutedText.Render("Su Mo Tu We Th Fr Sa"),
	}
	weeks := make([][]string, 6)
	day := first.AddDate(0, 0, -leadIn)
	for w := 0; w < 6; w++ {
		row := make([]string, 7)
		for d := 0; d < 7; d++ {
			cell := fmt.Sprintf("%2d", day.Day())
			if day.Month() != g.Selected.Month() {
				cell = styles.MutedText.Render(cell)
			} else if sameDay(day, g.Selected) {
				cell = styles.Selected.Render(cell)
			} else if g.Markers[day.Format("2006-01-02")] {
				cell = lipgloss.NewStyle().Foreground(styles.Accent).Render(cell)
			}
			row[d] = cell
			day = day.AddDate(0, 0, 1)
		}
		weeks[w] = row
	}
	for _, w := range weeks {
		rows = append(rows, strings.Join(w, " "))
	}
	return styles.Box.Render(strings.Join(rows, "\n"))
}

func sameDay(a, b time.Time) bool {
	return a.Year() == b.Year() && a.Month() == b.Month() && a.Day() == b.Day()
}
