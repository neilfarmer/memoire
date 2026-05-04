package styles

import "github.com/charmbracelet/lipgloss"

// k9s-inspired adaptive palette. Cyan-leaning accents, dark/light surfaces,
// strong status colours.
var (
	Primary  = lipgloss.AdaptiveColor{Light: "#0891b2", Dark: "#22d3ee"} // cyan
	Accent   = lipgloss.AdaptiveColor{Light: "#d97706", Dark: "#fbbf24"} // amber
	Danger   = lipgloss.AdaptiveColor{Light: "#dc2626", Dark: "#f87171"}
	Positive = lipgloss.AdaptiveColor{Light: "#16a34a", Dark: "#34d399"}
	Warning  = lipgloss.AdaptiveColor{Light: "#ca8a04", Dark: "#facc15"}
	Info     = lipgloss.AdaptiveColor{Light: "#2563eb", Dark: "#60a5fa"}
	Magenta  = lipgloss.AdaptiveColor{Light: "#9333ea", Dark: "#c084fc"}

	Surface = lipgloss.AdaptiveColor{Light: "#fafafa", Dark: "#0b0f14"}
	Panel   = lipgloss.AdaptiveColor{Light: "#ffffff", Dark: "#11161d"}
	Border  = lipgloss.AdaptiveColor{Light: "#cbd5e1", Dark: "#334155"}
	Subtle  = lipgloss.AdaptiveColor{Light: "#e2e8f0", Dark: "#1e293b"}
	Text    = lipgloss.AdaptiveColor{Light: "#0f172a", Dark: "#e2e8f0"}
	Muted   = lipgloss.AdaptiveColor{Light: "#64748b", Dark: "#94a3b8"}
)

// Borders.
var (
	BorderRounded = lipgloss.RoundedBorder()
	BorderThick   = lipgloss.ThickBorder()
	BorderDouble  = lipgloss.DoubleBorder()
)

// Text styles.
var (
	Title       = lipgloss.NewStyle().Bold(true).Foreground(Text)
	Heading     = lipgloss.NewStyle().Bold(true).Foreground(Primary)
	Subtitle    = lipgloss.NewStyle().Foreground(Muted)
	MutedText   = lipgloss.NewStyle().Foreground(Muted)
	Body        = lipgloss.NewStyle().Foreground(Text)
	DangerText  = lipgloss.NewStyle().Foreground(Danger).Bold(true)
	SuccessText = lipgloss.NewStyle().Foreground(Positive)
	WarnText    = lipgloss.NewStyle().Foreground(Warning)
	InfoText    = lipgloss.NewStyle().Foreground(Info)
	AccentText  = lipgloss.NewStyle().Foreground(Accent).Bold(true)
	Code        = lipgloss.NewStyle().
			Background(lipgloss.AdaptiveColor{Light: "#f1f5f9", Dark: "#1e293b"}).
			Foreground(Accent).Padding(0, 1)
)

// Inline pieces.
var (
	Selected = lipgloss.NewStyle().
			Foreground(lipgloss.AdaptiveColor{Light: "#ffffff", Dark: "#0b0f14"}).
			Background(Primary).Bold(true)

	Pill       = lipgloss.NewStyle().Padding(0, 1).Border(BorderRounded).BorderForeground(Border)
	PillActive = lipgloss.NewStyle().Padding(0, 1).Border(BorderRounded).BorderForeground(Primary).Foreground(Primary).Bold(true)

	Chip       = lipgloss.NewStyle().Padding(0, 1).Foreground(Muted).Background(Subtle)
	ChipPrimary = lipgloss.NewStyle().Padding(0, 1).Foreground(lipgloss.AdaptiveColor{Light: "#ffffff", Dark: "#0b0f14"}).Background(Primary).Bold(true)
	ChipAccent  = lipgloss.NewStyle().Padding(0, 1).Foreground(lipgloss.AdaptiveColor{Light: "#ffffff", Dark: "#0b0f14"}).Background(Accent).Bold(true)
	ChipDanger  = lipgloss.NewStyle().Padding(0, 1).Foreground(lipgloss.AdaptiveColor{Light: "#ffffff", Dark: "#0b0f14"}).Background(Danger).Bold(true)
)

// Boxes.
var (
	Box        = lipgloss.NewStyle().Border(BorderRounded).BorderForeground(Border).Padding(0, 1)
	BoxFocused = lipgloss.NewStyle().Border(BorderRounded).BorderForeground(Primary).Padding(0, 1)
	Panel1     = lipgloss.NewStyle().Border(BorderThick).BorderForeground(Border).Padding(0, 1)
	PanelFocus = lipgloss.NewStyle().Border(BorderThick).BorderForeground(Primary).Padding(0, 1)
)

// KeyHint formats `<key> desc` k9s-style.
func KeyHint(key, desc string) string {
	k := lipgloss.NewStyle().Foreground(Primary).Bold(true).Render("<" + key + ">")
	return k + " " + lipgloss.NewStyle().Foreground(Muted).Render(desc)
}

// StatusColor returns a lipgloss style for a known status string.
func StatusColor(status string) lipgloss.Style {
	switch status {
	case "done", "completed", "active":
		return SuccessText
	case "in_progress", "doing":
		return InfoText
	case "todo", "pending":
		return WarnText
	case "abandoned", "failed", "error":
		return DangerText
	}
	return MutedText
}

// PriorityColor returns a style for a priority value.
func PriorityColor(p string) lipgloss.Style {
	switch p {
	case "high", "urgent":
		return DangerText
	case "medium":
		return WarnText
	case "low":
		return MutedText
	}
	return Body
}
