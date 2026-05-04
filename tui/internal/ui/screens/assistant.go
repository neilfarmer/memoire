package screens

import (
	"strings"

	"github.com/charmbracelet/bubbles/textarea"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/api"
	"github.com/neilfarmer/memoire/tui/internal/styles"
	"github.com/neilfarmer/memoire/tui/internal/ui/components"
)

type assistantPane int

const (
	assistantPaneInput assistantPane = iota
	assistantPaneConvos
	assistantPaneMessages
)

type Assistant struct {
	client *api.Client
	width  int
	height int

	loading      bool
	err          error
	convos       []api.Conversation
	messages     []api.ChatMessage
	currentConv  string
	model        string
	pane         assistantPane

	input    textarea.Model
	view     viewport.Model
	convCur  int
	sending  bool
}

type convosLoadedMsg struct {
	convos []api.Conversation
	err    error
}
type convDetailMsg struct {
	convID string
	detail api.ConversationDetail
	err    error
}
type chatReplyMsg struct {
	resp api.ChatResponse
	err  error
}

func newAssistant(c *api.Client) *Assistant {
	a := &Assistant{client: c, model: "nova-lite"}
	a.input = textarea.New()
	a.input.Placeholder = "Type a message... (ctrl+j to send)"
	a.input.SetHeight(3)
	a.view = viewport.New(40, 20)
	a.input.Focus()
	return a
}

func (a *Assistant) Init() tea.Cmd { return a.refreshConvos() }

func (a *Assistant) refreshConvos() tea.Cmd {
	c := a.client
	return func() tea.Msg {
		out, err := c.ListConversations()
		return convosLoadedMsg{convos: out, err: err}
	}
}

func (a *Assistant) loadConv(id string) tea.Cmd {
	c := a.client
	return func() tea.Msg {
		d, err := c.GetConversation(id)
		return convDetailMsg{convID: id, detail: d, err: err}
	}
}

func (a *Assistant) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch m := msg.(type) {
	case convosLoadedMsg:
		a.err = m.err
		a.convos = m.convos
		return a, nil
	case convDetailMsg:
		a.err = m.err
		a.currentConv = m.convID
		a.messages = m.detail.Messages
		a.refreshView()
		return a, nil
	case chatReplyMsg:
		a.sending = false
		if m.err != nil {
			a.err = m.err
			return a, nil
		}
		a.currentConv = m.resp.ConversationID
		a.messages = append(a.messages, api.ChatMessage{Role: "assistant", Content: m.resp.Reply})
		a.refreshView()
		return a, a.refreshConvos()
	case tea.KeyMsg:
		return a.handleKey(m)
	}
	switch a.pane {
	case assistantPaneInput:
		var cmd tea.Cmd
		a.input, cmd = a.input.Update(msg)
		return a, cmd
	case assistantPaneMessages:
		var cmd tea.Cmd
		a.view, cmd = a.view.Update(msg)
		return a, cmd
	}
	return a, nil
}

func (a *Assistant) handleKey(m tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch m.String() {
	case "ctrl+j":
		return a, a.send()
	case "ctrl+l":
		return a, a.clearHistory()
	case "ctrl+n":
		return a, a.newConversation()
	case "ctrl+m":
		if a.model == "nova-lite" {
			a.model = "nova-pro"
		} else {
			a.model = "nova-lite"
		}
		return a, nil
	case "tab":
		a.pane = (a.pane + 1) % 3
		switch a.pane {
		case assistantPaneInput:
			a.input.Focus()
		default:
			a.input.Blur()
		}
		return a, nil
	}
	if a.pane == assistantPaneConvos {
		switch m.String() {
		case "up", "k":
			if a.convCur > 0 {
				a.convCur--
			}
		case "down", "j":
			if a.convCur < len(a.convos)-1 {
				a.convCur++
			}
		case "enter":
			if a.convCur < len(a.convos) {
				return a, a.loadConv(a.convos[a.convCur].ConversationID)
			}
		}
		return a, nil
	}
	if a.pane == assistantPaneInput {
		var cmd tea.Cmd
		a.input, cmd = a.input.Update(m)
		return a, cmd
	}
	var cmd tea.Cmd
	a.view, cmd = a.view.Update(m)
	return a, cmd
}

func (a *Assistant) refreshView() {
	rows := []string{}
	for _, m := range a.messages {
		role := strings.Title(m.Role)
		head := lipgloss.NewStyle().Foreground(styles.Primary).Bold(true).Render(role)
		body := components.RenderMarkdown(m.Content, a.view.Width-2)
		rows = append(rows, head, body, "")
	}
	a.view.SetContent(strings.Join(rows, "\n"))
	a.view.GotoBottom()
}

func (a *Assistant) send() tea.Cmd {
	body := strings.TrimSpace(a.input.Value())
	if body == "" {
		return nil
	}
	a.input.Reset()
	a.messages = append(a.messages, api.ChatMessage{Role: "user", Content: body})
	a.refreshView()
	a.sending = true
	c := a.client
	model := a.model
	convID := a.currentConv
	return func() tea.Msg {
		resp, err := c.Chat(api.ChatRequest{Message: body, Model: model, ConversationID: convID})
		return chatReplyMsg{resp: resp, err: err}
	}
}

func (a *Assistant) clearHistory() tea.Cmd {
	c := a.client
	a.messages = nil
	a.currentConv = ""
	a.refreshView()
	return func() tea.Msg {
		_ = c.ClearAssistantHistory()
		return convosLoadedMsg{}
	}
}

func (a *Assistant) newConversation() tea.Cmd {
	a.messages = nil
	a.currentConv = ""
	a.refreshView()
	return nil
}

func (a *Assistant) View() string {
	leftWidth := 24
	rightWidth := a.width - leftWidth - 4
	if rightWidth < 30 {
		rightWidth = 30
	}
	a.view.Width = rightWidth - 2
	a.view.Height = a.height - 8

	convoRows := []string{styles.Title.Render("Conversations")}
	for i, c := range a.convos {
		row := c.Title
		if row == "" {
			row = c.ConversationID
		}
		if i == a.convCur {
			row = styles.Selected.Render(row)
		}
		convoRows = append(convoRows, truncate(row, leftWidth-4))
	}
	convoBox := styles.Box
	if a.pane == assistantPaneConvos {
		convoBox = styles.BoxFocused
	}
	left := convoBox.Width(leftWidth).Render(strings.Join(convoRows, "\n"))

	msgBox := styles.Box
	if a.pane == assistantPaneMessages {
		msgBox = styles.BoxFocused
	}
	msgs := msgBox.Width(rightWidth).Height(a.height - 8).Render(a.view.View())

	a.input.SetWidth(rightWidth - 2)
	inputBox := styles.Box
	if a.pane == assistantPaneInput {
		inputBox = styles.BoxFocused
	}
	input := inputBox.Width(rightWidth).Render(a.input.View())

	statusLine := styles.MutedText.Render("model " + a.model + " · ctrl+j send · ctrl+m cycle model · ctrl+l clear · ctrl+n new convo · tab switch pane")
	if a.sending {
		statusLine = styles.SuccessText.Render("...sending...") + "  " + statusLine
	}

	right := lipgloss.JoinVertical(lipgloss.Left, msgs, input, statusLine)
	return lipgloss.JoinHorizontal(lipgloss.Top, left, right)
}

func (a *Assistant) Title() string { return "Assistant" }
func (a *Assistant) StatusHints() []string {
	return []string{
		styles.KeyHint("ctrl+j", "send"),
		styles.KeyHint("ctrl+l", "clear"),
		styles.KeyHint("ctrl+m", "model"),
		styles.KeyHint("ctrl+n", "new convo"),
		styles.KeyHint("tab", "pane"),
	}
}
func (a *Assistant) Help() []components.HelpEntry {
	return []components.HelpEntry{
		{Keys: "ctrl+j", Desc: "send message"},
		{Keys: "ctrl+m", Desc: "toggle model (nova-lite / nova-pro)"},
		{Keys: "ctrl+l", Desc: "clear current conversation"},
		{Keys: "ctrl+n", Desc: "start a new conversation"},
		{Keys: "tab", Desc: "cycle pane (input / conversations / messages)"},
		{Keys: "enter (in conversations)", Desc: "open conversation"},
	}
}
func (a *Assistant) SetSize(w, h int) { a.width, a.height = w, h }
