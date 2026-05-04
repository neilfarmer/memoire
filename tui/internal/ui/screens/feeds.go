package screens

import (
	"strings"

	"github.com/charmbracelet/bubbles/table"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/huh"
	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/api"
	"github.com/neilfarmer/memoire/tui/internal/styles"
	"github.com/neilfarmer/memoire/tui/internal/ui/components"
)

type feedsPane int

const (
	feedsPaneFeeds feedsPane = iota
	feedsPaneArticles
)

type feedsMode int

const (
	feedsList feedsMode = iota
	feedsDetail
	feedsAddForm
	feedsConfirmDeleteFeed
)

type Feeds struct {
	client *api.Client
	width  int
	height int

	mode    feedsMode
	pane    feedsPane
	loading bool
	err     error

	feeds        []api.Feed
	articles     []api.Article
	feedsTbl     table.Model
	articlesTbl  table.Model

	currentArticle  api.Article
	articleText     string
	loadingArticle  bool
	addForm         *huh.Form
	addURL          string
}

type feedsLoadedMsg struct {
	feeds    []api.Feed
	articles []api.Article
	err      error
}
type articleTextMsg struct {
	text api.ArticleText
	err  error
}
type feedsMutatedMsg struct{ err error }

func newFeeds(c *api.Client) *Feeds {
	f := &Feeds{client: c}
	f.feedsTbl = components.NewTable(feedTblCols(), nil, 18)
	f.articlesTbl = components.NewTable(articleTblCols(60), nil, 18)
	return f
}

func feedTblCols() []components.Column {
	return []components.Column{
		{Title: "FEED", Width: 28},
	}
}

func articleTblCols(w int) []components.Column {
	titleW := w - 18 - 12 - 6
	if titleW < 16 {
		titleW = 16
	}
	return []components.Column{
		{Title: " ", Width: 3},
		{Title: "DATE", Width: 12},
		{Title: "SOURCE", Width: 18},
		{Title: "TITLE", Width: titleW},
	}
}

func (f *Feeds) Init() tea.Cmd { return f.refresh() }

func (f *Feeds) refresh() tea.Cmd {
	c := f.client
	return func() tea.Msg {
		var msg feedsLoadedMsg
		if feeds, err := c.ListFeeds(); err == nil {
			msg.feeds = feeds
		} else {
			msg.err = err
		}
		if arts, err := c.ListFeedArticles(false); err == nil {
			msg.articles = arts
		}
		return msg
	}
}

func (f *Feeds) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch m := msg.(type) {
	case feedsLoadedMsg:
		f.loading = false
		f.err = m.err
		f.feeds = m.feeds
		f.articles = m.articles
		f.refreshRows()
		return f, nil
	case feedsMutatedMsg:
		f.err = m.err
		f.mode = feedsList
		return f, f.refresh()
	case articleTextMsg:
		f.loadingArticle = false
		if m.err != nil {
			f.err = m.err
		}
		f.articleText = m.text.Text
		return f, nil
	case components.OpenedURLMsg:
		return f, nil
	case tea.KeyMsg:
		return f.handleKey(m)
	}
	if f.mode == feedsAddForm && f.addForm != nil {
		af, cmd := f.addForm.Update(msg)
		if x, ok := af.(*huh.Form); ok {
			f.addForm = x
		}
		if f.addForm.State == huh.StateCompleted {
			return f, f.submitAdd()
		}
		return f, cmd
	}
	if f.mode == feedsList {
		var cmd tea.Cmd
		if f.pane == feedsPaneFeeds {
			f.feedsTbl, cmd = f.feedsTbl.Update(msg)
		} else {
			f.articlesTbl, cmd = f.articlesTbl.Update(msg)
		}
		return f, cmd
	}
	return f, nil
}

func (f *Feeds) refreshRows() {
	frows := make([]components.Row, 0, len(f.feeds))
	for _, x := range f.feeds {
		title := x.Title
		if title == "" {
			title = x.URL
		}
		frows = append(frows, components.Row{truncate(title, 28)})
	}
	f.feedsTbl.SetRows(frows)
	arows := make([]components.Row, 0, len(f.articles))
	for _, a := range f.articles {
		mark := " "
		if a.Read {
			mark = "·"
		}
		arows = append(arows, components.Row{
			mark, truncate(a.PubDate, 12), truncate(a.SourceFeed, 18), a.Title,
		})
	}
	f.articlesTbl.SetRows(arows)
}

func (f *Feeds) handleKey(m tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch f.mode {
	case feedsConfirmDeleteFeed:
		if m.String() == "y" {
			return f, f.deleteFeed()
		}
		if m.String() == "n" || m.String() == "esc" {
			f.mode = feedsList
		}
		return f, nil
	case feedsDetail:
		switch m.String() {
		case "esc", "q":
			f.mode = feedsList
		case "o":
			return f, components.OpenURL(articleURL(f.currentArticle))
		case "h":
			return f, f.heart()
		case "r":
			return f, f.markRead(articleURL(f.currentArticle))
		}
		return f, nil
	case feedsAddForm:
		if m.String() == "esc" {
			f.mode = feedsList
			f.addForm = nil
		}
		return f, nil
	}
	switch m.String() {
	case "tab":
		if f.pane == feedsPaneFeeds {
			f.pane = feedsPaneArticles
		} else {
			f.pane = feedsPaneFeeds
		}
	case "enter":
		if f.pane == feedsPaneArticles {
			idx := f.articlesTbl.Cursor()
			if idx < len(f.articles) {
				a := f.articles[idx]
				f.currentArticle = a
				f.articleText = ""
				f.loadingArticle = true
				f.mode = feedsDetail
				return f, f.fetchArticleText(articleURL(a))
			}
		}
	case "n":
		return f, f.startAdd()
	case "d":
		if f.pane == feedsPaneFeeds && len(f.feeds) > 0 {
			f.mode = feedsConfirmDeleteFeed
		}
	case "r", "ctrl+r":
		return f, f.refresh()
	case "F":
		c := f.client
		return f, func() tea.Msg {
			arts, err := c.ListFeedArticles(true)
			return feedsLoadedMsg{articles: arts, err: err, feeds: f.feeds}
		}
	}
	var cmd tea.Cmd
	if f.pane == feedsPaneFeeds {
		f.feedsTbl, cmd = f.feedsTbl.Update(m)
	} else {
		f.articlesTbl, cmd = f.articlesTbl.Update(m)
	}
	return f, cmd
}

func articleURL(a api.Article) string {
	if a.Link != "" {
		return a.Link
	}
	return a.URL
}

func (f *Feeds) startAdd() tea.Cmd {
	f.addURL = ""
	f.addForm = huh.NewForm(huh.NewGroup(
		huh.NewInput().Title("Feed URL").Value(&f.addURL).Validate(notEmpty),
	))
	f.mode = feedsAddForm
	return f.addForm.Init()
}

func (f *Feeds) submitAdd() tea.Cmd {
	c := f.client
	url := strings.TrimSpace(f.addURL)
	f.addForm = nil
	f.mode = feedsList
	return func() tea.Msg {
		_, err := c.AddFeed(url)
		return feedsMutatedMsg{err: err}
	}
}

func (f *Feeds) deleteFeed() tea.Cmd {
	idx := f.feedsTbl.Cursor()
	if idx >= len(f.feeds) {
		return nil
	}
	id := f.feeds[idx].FeedID
	c := f.client
	return func() tea.Msg { return feedsMutatedMsg{err: c.DeleteFeed(id)} }
}

func (f *Feeds) fetchArticleText(url string) tea.Cmd {
	c := f.client
	return func() tea.Msg {
		txt, err := c.FeedArticleText(url)
		return articleTextMsg{text: txt, err: err}
	}
}

func (f *Feeds) heart() tea.Cmd {
	c := f.client
	a := f.currentArticle
	return func() tea.Msg {
		_, err := c.CreateFavorite(api.FavoriteInput{
			Type: "article", URL: articleURL(a), Title: a.Title, Image: a.Image,
		})
		return feedsMutatedMsg{err: err}
	}
}

func (f *Feeds) markRead(url string) tea.Cmd {
	c := f.client
	return func() tea.Msg {
		_, err := c.MarkArticlesRead([]string{url})
		return feedsMutatedMsg{err: err}
	}
}

func (f *Feeds) View() string {
	switch f.mode {
	case feedsAddForm:
		return f.addForm.View()
	case feedsConfirmDeleteFeed:
		return components.ConfirmView("Unsubscribe from this feed?", f.width, f.height)
	case feedsDetail:
		return f.detailView()
	}
	leftWidth := 32
	rightWidth := f.width - leftWidth - 4
	if rightWidth < 30 {
		rightWidth = 30
	}
	if f.height-6 > 0 {
		f.feedsTbl.SetHeight(f.height - 6)
		f.articlesTbl.SetHeight(f.height - 6)
	}
	f.articlesTbl.SetColumns(articleTblCols(rightWidth))
	feedsHints := []string{
		styles.KeyHint("tab", "switch"),
		styles.KeyHint("n", "add"),
		styles.KeyHint("d", "remove"),
	}
	articleHints := []string{
		styles.KeyHint("↵", "read"),
		styles.KeyHint("F", "force refresh"),
	}
	leftBox := components.FrameTable("Feeds", len(f.feeds), f.feedsTbl, feedsHints, f.pane == feedsPaneFeeds)
	rightBox := components.FrameTable("Articles", len(f.articles), f.articlesTbl, articleHints, f.pane == feedsPaneArticles)
	return lipgloss.JoinHorizontal(lipgloss.Top, leftBox, rightBox)
}

func (f *Feeds) detailView() string {
	a := f.currentArticle
	rows := []string{
		components.Crumbs("Feeds", a.SourceFeed, a.Title),
		"",
		styles.Title.Render(a.Title),
	}
	if a.SourceFeed != "" {
		rows = append(rows, styles.MutedText.Render(a.SourceFeed+" · "+a.PubDate))
	}
	rows = append(rows, "")
	if f.loadingArticle {
		rows = append(rows, styles.MutedText.Render("Loading article..."))
	} else if f.articleText != "" {
		rows = append(rows, components.RenderMarkdown(f.articleText, f.width-6))
	} else if a.Snippet != "" {
		rows = append(rows, a.Snippet)
	}
	rows = append(rows, "", styles.MutedText.Render("<o> open  <h> heart  <r> mark read  <esc> back"))
	return styles.Box.Render(strings.Join(rows, "\n"))
}

func (f *Feeds) Title() string { return "Feeds" }
func (f *Feeds) StatusHints() []string {
	return []string{
		styles.KeyHint("tab", "pane"),
		styles.KeyHint("n", "add"),
		styles.KeyHint("F", "force refresh"),
		styles.KeyHint("d", "remove"),
	}
}
func (f *Feeds) Help() []components.HelpEntry {
	return []components.HelpEntry{
		{Keys: "tab", Desc: "switch feeds / articles pane"},
		{Keys: "↵ enter", Desc: "open article"},
		{Keys: "esc", Desc: "back"},
		{Keys: "o (in detail)", Desc: "open article URL in browser"},
		{Keys: "h (in detail)", Desc: "favorite the article"},
		{Keys: "r (in detail)", Desc: "mark as read"},
		{Keys: "n", Desc: "add feed"},
		{Keys: "d", Desc: "remove selected feed"},
		{Keys: "F", Desc: "force refresh articles"},
	}
}
func (f *Feeds) SetSize(w, h int) { f.width, f.height = w, h }
