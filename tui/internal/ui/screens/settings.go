package screens

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/huh"
	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/api"
	"github.com/neilfarmer/memoire/tui/internal/styles"
	"github.com/neilfarmer/memoire/tui/internal/ui/components"
)

type settingsMode int

const (
	settingsView settingsMode = iota
	settingsEdit
)

type Settings struct {
	client *api.Client
	width  int
	height int

	mode       settingsMode
	loading    bool
	err        error
	settings   api.Settings
	form       *huh.Form
	formIn     settingsForm
	flash      string
}

type settingsForm struct {
	displayName            string
	palName                string
	timezone               string
	darkMode               bool
	ntfyURL                string
	autosaveSeconds        string
	profileInferenceHours  string
}

type settingsLoadedMsg struct {
	settings api.Settings
	err      error
}
type settingsMutatedMsg struct {
	settings api.Settings
	err      error
}
type exportURLMsg struct {
	url string
	err error
}
type testNotificationMsg struct{ err error }

func newSettings(c *api.Client) *Settings { return &Settings{client: c} }

func (s *Settings) Init() tea.Cmd { return s.refresh() }

func (s *Settings) refresh() tea.Cmd {
	c := s.client
	return func() tea.Msg {
		out, err := c.GetSettings()
		return settingsLoadedMsg{settings: out, err: err}
	}
}

func (s *Settings) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch m := msg.(type) {
	case settingsLoadedMsg:
		s.loading = false
		s.err = m.err
		s.settings = m.settings
		return s, nil
	case settingsMutatedMsg:
		s.err = m.err
		s.settings = m.settings
		s.mode = settingsView
		s.flash = "Saved."
		return s, nil
	case exportURLMsg:
		if m.err != nil {
			s.err = m.err
		} else {
			s.flash = "Export ready: " + m.url
		}
		return s, nil
	case testNotificationMsg:
		if m.err != nil {
			s.err = m.err
			s.flash = "Test notification failed: " + m.err.Error()
		} else {
			s.flash = "Test notification sent."
		}
		return s, nil
	case tea.KeyMsg:
		return s.handleKey(m)
	}
	if s.mode == settingsEdit && s.form != nil {
		f, cmd := s.form.Update(msg)
		if x, ok := f.(*huh.Form); ok {
			s.form = x
		}
		if s.form.State == huh.StateCompleted {
			return s, s.submit()
		}
		return s, cmd
	}
	return s, nil
}

func (s *Settings) handleKey(m tea.KeyMsg) (tea.Model, tea.Cmd) {
	if s.mode == settingsEdit {
		if m.String() == "esc" {
			s.mode = settingsView
			s.form = nil
			return s, nil
		}
		if m.String() == "ctrl+s" {
			return s, s.submit()
		}
		f, cmd := s.form.Update(m)
		if x, ok := f.(*huh.Form); ok {
			s.form = x
		}
		if s.form.State == huh.StateCompleted {
			return s, s.submit()
		}
		return s, cmd
	}
	switch m.String() {
	case "e":
		return s, s.startEdit()
	case "x":
		return s, s.export()
	case "T":
		return s, s.testNotification()
	case "r", "ctrl+r":
		return s, s.refresh()
	}
	return s, nil
}

func (s *Settings) startEdit() tea.Cmd {
	cur := s.settings
	s.formIn = settingsForm{
		displayName:           strVal(cur, "display_name"),
		palName:               strVal(cur, "pal_name"),
		timezone:              strVal(cur, "timezone"),
		darkMode:              boolVal(cur, "dark_mode"),
		ntfyURL:               strVal(cur, "ntfy_url"),
		autosaveSeconds:       intStrFromAny(cur["autosave_seconds"]),
		profileInferenceHours: intStrFromAny(cur["profile_inference_hours"]),
	}
	d := &s.formIn
	s.form = huh.NewForm(
		huh.NewGroup(
			huh.NewInput().Title("Display name").Value(&d.displayName),
			huh.NewInput().Title("Assistant name (Pal name)").Value(&d.palName),
			huh.NewInput().Title("Timezone (e.g. America/New_York)").Value(&d.timezone),
			huh.NewConfirm().Title("Dark mode").Value(&d.darkMode),
		),
		huh.NewGroup(
			huh.NewInput().Title("ntfy.sh topic URL").Value(&d.ntfyURL),
			huh.NewInput().Title("Autosave seconds").Value(&d.autosaveSeconds),
			huh.NewInput().Title("Profile inference hours").Value(&d.profileInferenceHours),
		),
	)
	s.mode = settingsEdit
	return s.form.Init()
}

func (s *Settings) submit() tea.Cmd {
	d := s.formIn
	in := api.Settings{}
	if d.displayName != "" {
		in["display_name"] = d.displayName
	}
	if d.palName != "" {
		in["pal_name"] = d.palName
	}
	if d.timezone != "" {
		in["timezone"] = d.timezone
	}
	in["dark_mode"] = d.darkMode
	if d.ntfyURL != "" {
		in["ntfy_url"] = d.ntfyURL
	}
	if v, err := parseInt(d.autosaveSeconds); err == nil && v > 0 {
		in["autosave_seconds"] = v
	}
	if v, err := parseInt(d.profileInferenceHours); err == nil && v > 0 {
		in["profile_inference_hours"] = v
	}
	c := s.client
	s.form = nil
	s.mode = settingsView
	return func() tea.Msg {
		out, err := c.UpdateSettings(in)
		return settingsMutatedMsg{settings: out, err: err}
	}
}

func (s *Settings) export() tea.Cmd {
	c := s.client
	return func() tea.Msg {
		res, err := c.Export()
		return exportURLMsg{url: res.URL, err: err}
	}
}

func (s *Settings) testNotification() tea.Cmd {
	c := s.client
	return func() tea.Msg {
		err := c.TestNotification("ntfy", "")
		return testNotificationMsg{err: err}
	}
}

func (s *Settings) View() string {
	if s.mode == settingsEdit {
		if s.form != nil {
			return lipgloss.JoinVertical(lipgloss.Left, s.form.View(), "", components.FormHint())
		}
	}
	if s.loading {
		return styles.MutedText.Render("Loading settings...")
	}
	rows := []string{styles.Title.Render("Settings"), ""}
	rows = append(rows, settingsSection("Account", []string{
		fmt.Sprintf("Display name: %s", strVal(s.settings, "display_name")),
		fmt.Sprintf("Assistant name: %s", strVal(s.settings, "pal_name")),
		fmt.Sprintf("Email: %s", strVal(s.settings, "email")),
	}))
	rows = append(rows, settingsSection("Appearance", []string{
		fmt.Sprintf("Dark mode: %v", boolVal(s.settings, "dark_mode")),
		fmt.Sprintf("Timezone: %s", strVal(s.settings, "timezone")),
	}))
	rows = append(rows, settingsSection("Notifications", []string{
		fmt.Sprintf("ntfy URL: %s", strVal(s.settings, "ntfy_url")),
	}))
	rows = append(rows, settingsSection("Editor", []string{
		fmt.Sprintf("Autosave seconds: %s", intStrFromAny(s.settings["autosave_seconds"])),
	}))
	rows = append(rows, settingsSection("Assistant", []string{
		fmt.Sprintf("Profile inference hours: %s", intStrFromAny(s.settings["profile_inference_hours"])),
		fmt.Sprintf("Chat retention days: %s", intStrFromAny(s.settings["chat_retention_days"])),
	}))
	rows = append(rows, "", styles.MutedText.Render("e edit · x export data · T test notification · r refresh"))
	if s.flash != "" {
		rows = append(rows, "", styles.SuccessText.Render(s.flash))
	}
	return lipgloss.JoinVertical(lipgloss.Left, rows...)
}

func settingsSection(title string, lines []string) string {
	rows := []string{styles.Title.Render(title)}
	for _, l := range lines {
		rows = append(rows, "  "+l)
	}
	return strings.Join(rows, "\n") + "\n"
}

func strVal(s api.Settings, key string) string {
	if s == nil {
		return ""
	}
	if v, ok := s[key].(string); ok {
		return v
	}
	return ""
}

func boolVal(s api.Settings, key string) bool {
	if s == nil {
		return false
	}
	v, _ := s[key].(bool)
	return v
}

func intStrFromAny(v any) string {
	switch x := v.(type) {
	case int:
		return fmt.Sprintf("%d", x)
	case int64:
		return fmt.Sprintf("%d", x)
	case float64:
		return fmt.Sprintf("%d", int(x))
	case string:
		return x
	}
	return ""
}

func (s *Settings) Title() string { return "Settings" }
func (s *Settings) StatusHints() []string {
	return []string{
		styles.KeyHint("e", "edit"),
		styles.KeyHint("x", "export"),
		styles.KeyHint("T", "test notification"),
	}
}
func (s *Settings) Help() []components.HelpEntry {
	return []components.HelpEntry{
		{Keys: "e", Desc: "edit settings"},
		{Keys: "x", Desc: "export data (returns presigned URL)"},
		{Keys: "T", Desc: "send test ntfy notification"},
		{Keys: "r", Desc: "refresh"},
	}
}
func (s *Settings) SetSize(w, h int) { s.width, s.height = w, h }
