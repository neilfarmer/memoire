package components

import (
	"fmt"
	"strings"

	"github.com/neilfarmer/memoire/tui/internal/styles"
)

// SummaryStat is a single stat line for trend summaries.
type SummaryStat struct {
	Label string
	Value string
	Trend string
}

// SummaryView renders a compact stat block. The terminal can't reliably draw
// sparkline charts so we replace them with one-line stats.
func SummaryView(title string, stats []SummaryStat) string {
	rows := []string{styles.Title.Render(title)}
	for _, s := range stats {
		row := fmt.Sprintf("%-20s %s", s.Label, s.Value)
		if s.Trend != "" {
			row += "  " + styles.MutedText.Render(s.Trend)
		}
		rows = append(rows, row)
	}
	return strings.Join(rows, "\n")
}

// Bar renders a simple horizontal bar like `[=====     ] 50%`.
func Bar(pct, width int) string {
	if width <= 0 {
		width = 20
	}
	if pct < 0 {
		pct = 0
	}
	if pct > 100 {
		pct = 100
	}
	filled := pct * width / 100
	empty := width - filled
	return "[" + strings.Repeat("=", filled) + strings.Repeat(" ", empty) + "]"
}
