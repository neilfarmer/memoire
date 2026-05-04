package ui

import (
	"net/url"
	"strconv"
	"time"

	"github.com/charmbracelet/bubbles/key"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/api"
	"github.com/neilfarmer/memoire/tui/internal/logx"
	"github.com/neilfarmer/memoire/tui/internal/styles"
	"github.com/neilfarmer/memoire/tui/internal/ui/components"
	"github.com/neilfarmer/memoire/tui/internal/ui/screens"
)

// ScreenFactory builds a Screen lazily on first navigation.
type ScreenFactory func(client *api.Client) screens.Screen

// App is the root Bubble Tea Model.
type App struct {
	client      *api.Client
	apiHost     string
	keys        GlobalKeys
	current     Screen
	sideCursor  int  // index into SidebarOrder; current sidebar selection
	sideFocus   bool // true = arrow keys move sideCursor, false = sent to screen
	registry    map[Screen]screens.Screen
	factories   map[Screen]ScreenFactory
	width       int
	height      int
	flash       string
	flashLevel  FlashLevel
	flashID     int64
	helpOpen    bool
	leaderG     bool
	connected   bool
	lastConnAt  time.Time
}

// New builds the root App with the given API client and screen factories.
func New(client *api.Client, factories map[Screen]ScreenFactory) *App {
	host := ""
	if u, err := url.Parse(client.BaseURL); err == nil {
		host = u.Host
	}
	return &App{
		client:    client,
		apiHost:   host,
		keys:      DefaultKeys(),
		current:   ScreenDashboard,
		sideCursor: 0,
		sideFocus:  true,
		registry:  map[Screen]screens.Screen{},
		factories: factories,
		connected: true,
	}
}

func (a *App) Init() tea.Cmd {
	return a.activate(a.current)
}

func (a *App) activate(s Screen) tea.Cmd {
	first := false
	if _, ok := a.registry[s]; !ok {
		first = true
		factory, ok := a.factories[s]
		if !ok {
			a.registry[s] = screens.NewPlaceholder(SidebarLabels[s])
		} else {
			a.registry[s] = factory(a.client)
		}
	}
	a.current = s
	a.registry[s].SetSize(a.contentWidth(), a.contentHeight())
	logx.Debug("activate screen", "screen", string(s), "first_init", first)
	return a.registry[s].Init()
}

func (a *App) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch m := msg.(type) {
	case tea.WindowSizeMsg:
		a.width, a.height = m.Width, m.Height
		for _, s := range a.registry {
			s.SetSize(a.contentWidth(), a.contentHeight())
		}
	case tea.KeyMsg:
		// Filter terminal OSC responses that some terminals leak as keys
		// (e.g. background-color reply "]11;rgb:..."). Forwarding these to
		// the screen causes feedback loops + freezes.
		if isTerminalNoiseKey(m.String()) {
			return a, nil
		}
		logx.Debug("key event", "key", m.String(), "side_focus", a.sideFocus, "screen", string(a.current))
		if cmd, handled := a.handleKey(m); handled {
			return a, cmd
		}
	case NavigateMsg:
		return a, a.activate(m.To)
	case FlashMsg:
		return a, a.setFlash(m)
	case FlashClearMsg:
		if m.ID == a.flashID {
			a.flash = ""
		}
	case ErrorMsg:
		logx.Error("error msg", "err", m.Err)
		return a, a.setFlash(FlashMsg{Text: "error: " + m.Err.Error(), Level: FlashError, TTL: 6 * time.Second})
	case HelpToggleMsg:
		a.helpOpen = !a.helpOpen
		return a, nil
	}
	if cur, ok := a.registry[a.current]; ok {
		updated, cmd := cur.Update(msg)
		if s, ok := updated.(screens.Screen); ok {
			a.registry[a.current] = s
		}
		return a, cmd
	}
	return a, nil
}

func (a *App) handleKey(m tea.KeyMsg) (tea.Cmd, bool) {
	if a.helpOpen {
		if m.String() == "?" || m.String() == "esc" {
			a.helpOpen = false
			return nil, true
		}
	}
	switch {
	case key.Matches(m, a.keys.Quit):
		return tea.Quit, true
	case m.String() == "?":
		a.helpOpen = !a.helpOpen
		return nil, true
	}
	// Numeric shortcuts always work regardless of focus.
	if n, err := strconv.Atoi(m.String()); err == nil && n >= 1 && n <= 9 && n <= len(SidebarOrder) {
		a.sideCursor = n - 1
		a.sideFocus = false
		return a.activate(SidebarOrder[n-1]), true
	}
	// Leader 'g' for full sidebar coverage.
	if m.String() == "g" && !a.leaderG {
		a.leaderG = true
		return nil, true
	}
	if a.leaderG {
		a.leaderG = false
		mapping := map[string]Screen{
			"d": ScreenDashboard, "t": ScreenTasks, "n": ScreenNotes, "j": ScreenJournal,
			"h": ScreenHabits, "o": ScreenGoals, "H": ScreenHealth, "u": ScreenNutrition,
			"f": ScreenFinances, "r": ScreenFeeds, "b": ScreenBookmarks, "v": ScreenFavorites,
			"a": ScreenAssistant, "s": ScreenSettings, "k": ScreenTokens, "x": ScreenAdmin,
		}
		if dest, ok := mapping[m.String()]; ok {
			a.sideCursor = indexOfScreen(dest)
			a.sideFocus = false
			return a.activate(dest), true
		}
		return nil, true
	}
	// shift+tab always toggles focus (k9s-style). Tab is consumed by huh forms
	// and by feeds/finances pane switching, so we use shift+tab to avoid the
	// clash. Must run before the sidebar block.
	if m.String() == "shift+tab" {
		a.sideFocus = !a.sideFocus
		return nil, true
	}
	if a.sideFocus {
		switch m.String() {
		case "up", "k":
			if a.sideCursor > 0 {
				a.sideCursor--
			}
			return a.activate(SidebarOrder[a.sideCursor]), true
		case "down", "j":
			if a.sideCursor < len(SidebarOrder)-1 {
				a.sideCursor++
			}
			return a.activate(SidebarOrder[a.sideCursor]), true
		case "enter", "right", "l":
			a.sideFocus = false
			return a.activate(SidebarOrder[a.sideCursor]), true
		case "esc":
			a.sideFocus = false
			return nil, true
		}
		// Any other key (letters, ctrl combos) means user is interacting with
		// content — drop sidebar focus and let the screen handle it. Without
		// this the screen receives a keystroke while we still steal arrows,
		// producing a soft lock when the screen opens a form/textarea/picker.
		a.sideFocus = false
	}
	// Esc inside content returns focus to sidebar (only when current screen
	// is at its top-level — screens that consume esc themselves must do so
	// before this fires; that's handled by the routing below: handleKey is
	// called before the screen.Update, but we only steal esc if no modal /
	// drilldown is active, which we approximate by checking whether the
	// screen wants the key by way of the global flag — for now we steal esc
	// only when sideFocus is false AND it's at the table level. Screens that
	// need esc themselves intercept before delegating, so we return false
	// here so they can handle it. We provide an explicit binding `\` to pop
	// to sidebar for users who want a one-key way back.
	if m.String() == "\\" {
		a.sideFocus = true
		return nil, true
	}
	return nil, false
}

// isTerminalNoiseKey reports whether a tea KeyMsg.String() looks like a
// terminal OSC response or other escape-leakage rather than user input.
func isTerminalNoiseKey(k string) bool {
	if k == "" {
		return false
	}
	if k[0] == ']' || k[0] == '[' {
		return true
	}
	for _, marker := range []string{";rgb:", "rgb:", "]11", "alt+]", "alt+\\"} {
		if containsStr(k, marker) {
			return true
		}
	}
	return false
}

func containsStr(s, sub string) bool {
	if len(sub) == 0 {
		return true
	}
	if len(sub) > len(s) {
		return false
	}
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}

func indexOfScreen(s Screen) int {
	for i, x := range SidebarOrder {
		if x == s {
			return i
		}
	}
	return 0
}

func (a *App) setFlash(f FlashMsg) tea.Cmd {
	a.flashID++
	id := a.flashID
	a.flash = f.Text
	a.flashLevel = f.Level
	ttl := f.TTL
	if ttl == 0 {
		ttl = 4 * time.Second
	}
	return tea.Tick(ttl, func(time.Time) tea.Msg { return FlashClearMsg{ID: id} })
}

func (a *App) View() string {
	if a.width == 0 || a.height == 0 {
		return "loading..."
	}
	header := components.Header{
		Section:   SidebarLabels[a.current],
		Connected: a.connected,
		APIHost:   a.apiHost,
		Auth:      "PAT",
		Width:     a.width,
	}.View()

	items := make([]components.SidebarItem, 0, len(SidebarOrder))
	for _, s := range SidebarOrder {
		items = append(items, components.SidebarItem{
			Key:   string(s),
			Label: SidebarLabels[s],
			Icon:  SidebarIcon(s),
		})
	}
	side := components.Sidebar{
		Items:   items,
		Active:  string(SidebarOrder[a.sideCursor]),
		Width:   24,
		Focused: a.sideFocus,
	}.View()

	var content string
	if cur, ok := a.registry[a.current]; ok {
		content = cur.View()
	}
	// Hard-clip content height so an oversized screen view cannot push the
	// sidebar off-screen.
	contentBox := lipgloss.NewStyle().Width(a.contentWidth()).Height(a.contentHeight()).MaxHeight(a.contentHeight()).Render(content)

	hints := []string{
		styles.KeyHint("\\", "sidebar"),
		styles.KeyHint("?", "help"),
		styles.KeyHint("ctrl+q", "quit"),
	}
	if a.sideFocus {
		hints = []string{
			styles.KeyHint("↑↓", "nav"),
			styles.KeyHint("↵", "focus content"),
			styles.KeyHint("?", "help"),
			styles.KeyHint("ctrl+q", "quit"),
		}
	} else if cur, ok := a.registry[a.current]; ok {
		extra := cur.StatusHints()
		hints = append(extra, hints...)
	}
	status := components.StatusBar{
		Screen: SidebarLabels[a.current],
		Flash:  a.flash,
		Hints:  hints,
		Width:  a.width,
	}.View()

	body := lipgloss.JoinHorizontal(lipgloss.Top, side, contentBox)
	out := lipgloss.JoinVertical(lipgloss.Left, header, body, status)

	if a.helpOpen {
		return components.HelpView(a.width, a.height, a.helpSections(), a.helpOrder())
	}
	return out
}

func (a *App) helpSections() map[string][]components.HelpEntry {
	out := map[string][]components.HelpEntry{
		"Global": {
			{Keys: "?", Desc: "toggle help"},
			{Keys: "ctrl+q", Desc: "quit"},
			{Keys: "1-9", Desc: "jump to sidebar item"},
			{Keys: "g <letter>", Desc: "leader nav (g t = tasks, g n = notes, ...)"},
			{Keys: "ctrl+r", Desc: "refresh current screen"},
		},
	}
	if cur, ok := a.registry[a.current]; ok {
		if entries := cur.Help(); len(entries) > 0 {
			out[cur.Title()] = entries
		}
	}
	return out
}

func (a *App) helpOrder() []string {
	order := []string{"Global"}
	if cur, ok := a.registry[a.current]; ok {
		order = append(order, cur.Title())
	}
	return order
}

func (a *App) contentWidth() int {
	w := a.width - 26 // sidebar 24 + 2 padding
	if w < 40 {
		w = 40
	}
	return w
}

func (a *App) contentHeight() int {
	h := a.height - 5 // header (2 lines) + statusbar (2 lines) + spacing
	if h < 10 {
		h = 10
	}
	return h
}

// SetConnection toggles the header indicator. Currently only used by initial
// reachability check.
func (a *App) SetConnection(ok bool) {
	a.connected = ok
	if ok {
		a.lastConnAt = time.Now()
	}
}

// keep the styles import in use for KeyHint and adaptive colors.
var _ = styles.Primary
