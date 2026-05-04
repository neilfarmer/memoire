package screens

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/bubbles/table"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/huh"
	"github.com/charmbracelet/lipgloss"

	"github.com/neilfarmer/memoire/tui/internal/api"
	"github.com/neilfarmer/memoire/tui/internal/styles"
	"github.com/neilfarmer/memoire/tui/internal/ui/components"
)

type noteMode int

const (
	noteList noteMode = iota
	noteDetail
	noteForm
	noteFolderList
	noteFolderForm
	noteConfirmDelete
	noteConfirmDeleteFolder
)

type Notes struct {
	client *api.Client
	width  int
	height int

	mode    noteMode
	loading bool
	err     error

	folders     []api.NoteFolder
	notes       []api.NoteSummary
	view        []api.NoteSummary
	current     api.Note
	folderID    string  // empty = all
	folderCur   int     // cursor in folder management overlay
	tbl         table.Model
	folderTbl   table.Model

	form           *huh.Form
	formData       noteFormState
	folderForm     *huh.Form
	folderFormName string
}

type noteFormState struct {
	id       string
	title    string
	body     string
	tags     string
	folderID string
}

type notesLoadedMsg struct {
	folders []api.NoteFolder
	notes   []api.NoteSummary
	err     error
}
type noteLoadedMsg struct {
	note api.Note
	err  error
}
type noteMutatedMsg struct{ err error }

func newNotes(c *api.Client) *Notes {
	n := &Notes{client: c}
	n.tbl = components.NewTable(noteCols(80), nil, 18)
	n.folderTbl = components.NewTable(folderCols(60), nil, 14)
	return n
}

func noteCols(w int) []components.Column {
	titleW := w - 18 - 16 - 12
	if titleW < 20 {
		titleW = 20
	}
	return []components.Column{
		{Title: "FOLDER", Width: 18},
		{Title: "TITLE", Width: titleW},
		{Title: "TAGS", Width: 16},
		{Title: "UPDATED", Width: 12},
	}
}

// shortDate returns just YYYY-MM-DD from an ISO timestamp so it never wraps.
func shortDate(s string) string {
	if len(s) >= 10 {
		return s[:10]
	}
	return s
}

func folderCols(w int) []components.Column {
	nameW := w - 14
	if nameW < 16 {
		nameW = 16
	}
	return []components.Column{
		{Title: "NAME", Width: nameW},
		{Title: "COLOR", Width: 12},
	}
}

func (n *Notes) Init() tea.Cmd { return n.refresh() }

func (n *Notes) refresh() tea.Cmd {
	c := n.client
	return func() tea.Msg {
		var msg notesLoadedMsg
		if f, err := c.ListNoteFolders(); err == nil {
			msg.folders = f
		} else {
			msg.err = err
		}
		if notes, err := c.ListNotes(""); err == nil {
			msg.notes = notes
		} else if msg.err == nil {
			msg.err = err
		}
		return msg
	}
}

func (n *Notes) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch m := msg.(type) {
	case notesLoadedMsg:
		n.loading = false
		n.err = m.err
		n.folders = m.folders
		n.notes = m.notes
		n.refilter()
		return n, nil
	case noteLoadedMsg:
		if m.err != nil {
			n.err = m.err
			return n, nil
		}
		n.current = m.note
		n.mode = noteDetail
		return n, nil
	case noteEditPrepMsg:
		// User pressed 'e' on the list view; we fetched the full note. Now
		// open the edit form populated with the body.
		n.current = m.note
		n.formData = noteFormState{
			id:       m.note.NoteID,
			title:    m.note.Title,
			body:     m.note.Body,
			tags:     strings.Join(m.note.Tags, ", "),
			folderID: m.note.FolderID,
		}
		n.form = n.newForm("Edit note")
		n.mode = noteForm
		return n, n.form.Init()
	case noteMutatedMsg:
		if m.err != nil {
			n.err = m.err
		}
		n.mode = noteList
		return n, n.refresh()
	case components.EditorClosedMsg:
		if m.Err != nil {
			n.err = m.Err
			return n, nil
		}
		n.formData.body = m.Content
		return n, nil
	case tea.KeyMsg:
		return n.handleKey(m)
	}
	if n.mode == noteForm && n.form != nil {
		f, cmd := n.form.Update(msg)
		if ff, ok := f.(*huh.Form); ok {
			n.form = ff
		}
		if n.form.State == huh.StateCompleted {
			return n, n.submitForm()
		}
		return n, cmd
	}
	if n.mode == noteFolderForm && n.folderForm != nil {
		f, cmd := n.folderForm.Update(msg)
		if ff, ok := f.(*huh.Form); ok {
			n.folderForm = ff
		}
		if n.folderForm.State == huh.StateCompleted {
			return n, n.submitFolder()
		}
		return n, cmd
	}
	if n.mode == noteList {
		var cmd tea.Cmd
		n.tbl, cmd = n.tbl.Update(msg)
		return n, cmd
	}
	if n.mode == noteFolderList {
		var cmd tea.Cmd
		n.folderTbl, cmd = n.folderTbl.Update(msg)
		return n, cmd
	}
	return n, nil
}

func (n *Notes) refilter() {
	view := make([]api.NoteSummary, 0, len(n.notes))
	for _, x := range n.notes {
		if n.folderID != "" && x.FolderID != n.folderID {
			continue
		}
		view = append(view, x)
	}
	n.view = view
	rows := make([]components.Row, 0, len(view))
	for _, x := range view {
		rows = append(rows, components.Row{
			truncate(n.folderName(x.FolderID), 18),
			x.Title,
			truncate(strings.Join(x.Tags, ","), 16),
			shortDate(x.UpdatedAt),
		})
	}
	n.tbl.SetRows(rows)
	frows := make([]components.Row, 0, len(n.folders))
	for _, f := range n.folders {
		frows = append(frows, components.Row{f.Name, orDash(f.Color)})
	}
	n.folderTbl.SetRows(frows)
}

func (n *Notes) folderName(id string) string {
	if id == "" {
		return "(none)"
	}
	for _, f := range n.folders {
		if f.FolderID == id {
			return f.Name
		}
	}
	return id
}

func (n *Notes) handleKey(m tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch n.mode {
	case noteConfirmDelete:
		if m.String() == "y" {
			n.mode = noteList
			return n, n.deleteCurrent()
		}
		if m.String() == "n" || m.String() == "esc" {
			n.mode = noteList
		}
		return n, nil
	case noteConfirmDeleteFolder:
		if m.String() == "y" {
			return n, n.deleteFolder()
		}
		if m.String() == "n" || m.String() == "esc" {
			n.mode = noteFolderList
		}
		return n, nil
	case noteDetail:
		switch m.String() {
		case "esc", "q":
			n.mode = noteList
		case "e":
			return n, n.startEdit()
		case "d":
			n.mode = noteConfirmDelete
		}
		return n, nil
	case noteForm:
		if m.String() == "esc" {
			n.mode = noteList
			n.form = nil
			return n, nil
		}
		if m.String() == "ctrl+s" {
			return n, n.submitForm()
		}
		if m.String() == "ctrl+e" {
			return n, components.EditExternal(n.formData.body, ".md")
		}
		f, cmd := n.form.Update(m)
		if ff, ok := f.(*huh.Form); ok {
			n.form = ff
		}
		if n.form.State == huh.StateCompleted {
			return n, n.submitForm()
		}
		return n, cmd
	case noteFolderForm:
		if m.String() == "esc" {
			n.mode = noteFolderList
			n.folderForm = nil
			return n, nil
		}
		f, cmd := n.folderForm.Update(m)
		if ff, ok := f.(*huh.Form); ok {
			n.folderForm = ff
		}
		if n.folderForm.State == huh.StateCompleted {
			return n, n.submitFolder()
		}
		return n, cmd
	case noteFolderList:
		switch m.String() {
		case "esc", "q":
			n.mode = noteList
		case "n":
			return n, n.startFolderForm()
		case "d":
			if len(n.folders) > 0 {
				n.mode = noteConfirmDeleteFolder
			}
		case "enter":
			idx := n.folderTbl.Cursor()
			if idx < len(n.folders) {
				n.folderID = n.folders[idx].FolderID
				n.refilter()
				n.mode = noteList
			}
		}
		var cmd tea.Cmd
		n.folderTbl, cmd = n.folderTbl.Update(m)
		return n, cmd
	}
	switch m.String() {
	case "enter":
		idx := n.tbl.Cursor()
		if idx < len(n.view) {
			return n, n.openNote(n.view[idx].NoteID)
		}
	case "n":
		return n, n.startNew()
	case "e":
		return n, n.startEdit()
	case "d":
		idx := n.tbl.Cursor()
		if idx < len(n.view) {
			n.current = api.Note{NoteID: n.view[idx].NoteID, Title: n.view[idx].Title}
			n.mode = noteConfirmDelete
		}
	case "F":
		n.mode = noteFolderList
	case "f":
		n.cycleFolder()
	case "X":
		n.folderID = ""
		n.refilter()
	case "r", "ctrl+r":
		return n, n.refresh()
	}
	var cmd tea.Cmd
	n.tbl, cmd = n.tbl.Update(m)
	return n, cmd
}

func (n *Notes) cycleFolder() {
	if len(n.folders) == 0 {
		return
	}
	if n.folderID == "" {
		n.folderID = n.folders[0].FolderID
		n.refilter()
		return
	}
	for i, f := range n.folders {
		if f.FolderID == n.folderID {
			if i+1 < len(n.folders) {
				n.folderID = n.folders[i+1].FolderID
			} else {
				n.folderID = ""
			}
			n.refilter()
			return
		}
	}
}

func (n *Notes) openNote(id string) tea.Cmd {
	c := n.client
	return func() tea.Msg {
		note, err := c.GetNote(id)
		return noteLoadedMsg{note: note, err: err}
	}
}

func (n *Notes) startNew() tea.Cmd {
	n.formData = noteFormState{folderID: n.folderID}
	n.form = n.newForm("New note")
	n.mode = noteForm
	return n.form.Init()
}

func (n *Notes) startEdit() tea.Cmd {
	if n.current.NoteID == "" {
		idx := n.tbl.Cursor()
		if idx >= len(n.view) {
			return nil
		}
		return n.openNoteForEdit(n.view[idx].NoteID)
	}
	n.formData = noteFormState{
		id:       n.current.NoteID,
		title:    n.current.Title,
		body:     n.current.Body,
		tags:     strings.Join(n.current.Tags, ", "),
		folderID: n.current.FolderID,
	}
	n.form = n.newForm("Edit note")
	n.mode = noteForm
	return n.form.Init()
}

func (n *Notes) openNoteForEdit(id string) tea.Cmd {
	c := n.client
	return func() tea.Msg {
		note, err := c.GetNote(id)
		if err != nil {
			return noteLoadedMsg{err: err}
		}
		return noteEditPrepMsg{note: note}
	}
}

type noteEditPrepMsg struct{ note api.Note }

func (n *Notes) newForm(title string) *huh.Form {
	d := &n.formData
	return huh.NewForm(
		huh.NewGroup(
			huh.NewInput().Title("Title").Value(&d.title).Validate(func(s string) error {
				if strings.TrimSpace(s) == "" {
					return fmt.Errorf("required")
				}
				return nil
			}),
			huh.NewText().Title("Body (markdown — ctrl+e for $EDITOR)").Value(&d.body).Lines(8),
			huh.NewInput().Title("Tags (comma separated)").Value(&d.tags),
		),
	).WithTheme(huh.ThemeBase())
}

func (n *Notes) submitForm() tea.Cmd {
	d := n.formData
	in := api.NoteInput{
		FolderID: d.folderID,
		Title:    strings.TrimSpace(d.title),
		Body:     d.body,
		Tags:     splitTags(d.tags),
	}
	id := d.id
	c := n.client
	n.form = nil
	n.mode = noteList
	return func() tea.Msg {
		var err error
		if id == "" {
			_, err = c.CreateNote(in)
		} else {
			_, err = c.UpdateNote(id, in)
		}
		return noteMutatedMsg{err: err}
	}
}

func (n *Notes) deleteCurrent() tea.Cmd {
	id := n.current.NoteID
	c := n.client
	return func() tea.Msg { return noteMutatedMsg{err: c.DeleteNote(id)} }
}

func (n *Notes) startFolderForm() tea.Cmd {
	n.folderFormName = ""
	n.folderForm = huh.NewForm(huh.NewGroup(
		huh.NewInput().Title("Folder name").Value(&n.folderFormName).Validate(notEmpty),
	))
	n.mode = noteFolderForm
	return n.folderForm.Init()
}

func (n *Notes) submitFolder() tea.Cmd {
	name := strings.TrimSpace(n.folderFormName)
	c := n.client
	n.mode = noteFolderList
	n.folderForm = nil
	return func() tea.Msg {
		_, err := c.CreateNoteFolder(api.NoteFolderInput{Name: name})
		return noteMutatedMsg{err: err}
	}
}

func (n *Notes) deleteFolder() tea.Cmd {
	idx := n.folderTbl.Cursor()
	if idx >= len(n.folders) {
		return nil
	}
	id := n.folders[idx].FolderID
	c := n.client
	return func() tea.Msg { return noteMutatedMsg{err: c.DeleteNoteFolder(id)} }
}

func (n *Notes) View() string {
	if n.loading && len(n.notes) == 0 {
		return styles.MutedText.Render("Loading notes...")
	}
	switch n.mode {
	case noteForm:
		if n.form != nil {
			return lipgloss.JoinVertical(lipgloss.Left, n.form.View(), "", components.FormHint())
		}
	case noteFolderForm:
		return n.folderForm.View()
	case noteDetail:
		return n.detailView()
	case noteConfirmDelete:
		return components.ConfirmView("Delete this note?", n.width, n.height)
	case noteConfirmDeleteFolder:
		return components.ConfirmView("Delete this folder? Notes inside become unfiled.", n.width, n.height)
	case noteFolderList:
		return n.folderListView()
	}
	folderLabel := "All folders"
	if n.folderID != "" {
		folderLabel = "Folder: " + n.folderName(n.folderID)
	}
	header := lipgloss.JoinHorizontal(lipgloss.Top,
		styles.ChipPrimary.Render(folderLabel),
		"  ",
		styles.MutedText.Render("press f to cycle  X to clear  F to manage folders"),
	)
	n.tbl.SetColumns(noteCols(n.width - 6))
	if n.height-10 > 0 {
		n.tbl.SetHeight(n.height - 10)
	}
	hints := []string{
		styles.KeyHint("↵", "open"),
		styles.KeyHint("n", "new"),
		styles.KeyHint("e", "edit"),
		styles.KeyHint("d", "delete"),
		styles.KeyHint("f", "filter"),
		styles.KeyHint("F", "folders"),
	}
	body := components.FrameTable("Notes", len(n.view), n.tbl, hints, true)
	return lipgloss.JoinVertical(lipgloss.Left, header, "", body)
}

func (n *Notes) detailView() string {
	editBtn := styles.ChipPrimary.Render(" e · Edit ")
	deleteBtn := styles.Chip.Render(" d · Delete ")
	backBtn := styles.Chip.Render(" esc · Back ")
	actions := lipgloss.JoinHorizontal(lipgloss.Top, editBtn, "  ", deleteBtn, "  ", backBtn)

	rows := []string{
		components.Crumbs("Notes", n.current.Title),
		"",
		actions,
		"",
		styles.Title.Render(n.current.Title),
	}
	meta := []string{}
	if len(n.current.Tags) > 0 {
		meta = append(meta, "#"+strings.Join(n.current.Tags, " #"))
	}
	if n.current.UpdatedAt != "" {
		meta = append(meta, "updated "+shortDate(n.current.UpdatedAt))
	}
	if len(meta) > 0 {
		rows = append(rows, styles.MutedText.Render(strings.Join(meta, " · ")))
	}
	rows = append(rows, "", components.RenderMarkdown(n.current.Body, n.width-6))
	return styles.Box.Render(strings.Join(rows, "\n"))
}

func (n *Notes) folderListView() string {
	header := components.Crumbs("Notes", "Folders")
	n.folderTbl.SetColumns(folderCols(n.width - 6))
	if n.height-8 > 0 {
		n.folderTbl.SetHeight(n.height - 8)
	}
	hints := []string{
		styles.KeyHint("↵", "filter to folder"),
		styles.KeyHint("n", "new"),
		styles.KeyHint("d", "delete"),
		styles.KeyHint("esc", "back"),
	}
	body := components.FrameTable("Folders", len(n.folders), n.folderTbl, hints, true)
	return lipgloss.JoinVertical(lipgloss.Left, header, "", body)
}

func (n *Notes) Title() string { return "Notes" }
func (n *Notes) StatusHints() []string {
	return []string{
		styles.KeyHint("↵", "open"),
		styles.KeyHint("n", "new"),
		styles.KeyHint("e", "edit"),
		styles.KeyHint("d", "delete"),
		styles.KeyHint("f", "filter folder"),
		styles.KeyHint("F", "folders"),
	}
}
func (n *Notes) Help() []components.HelpEntry {
	return []components.HelpEntry{
		{Keys: "↑/↓", Desc: "select row"},
		{Keys: "↵ enter", Desc: "open note"},
		{Keys: "esc", Desc: "back"},
		{Keys: "n", Desc: "new note"},
		{Keys: "e", Desc: "edit note"},
		{Keys: "d", Desc: "delete note"},
		{Keys: "f", Desc: "cycle folder filter"},
		{Keys: "X", Desc: "clear folder filter"},
		{Keys: "F", Desc: "manage folders"},
		{Keys: "ctrl+e (in form)", Desc: "edit body in $EDITOR"},
	}
}
func (n *Notes) SetSize(w, h int) {
	n.width, n.height = w, h
	n.tbl.SetColumns(noteCols(w - 6))
	n.folderTbl.SetColumns(folderCols(w - 6))
	if h-8 > 0 {
		n.tbl.SetHeight(h - 8)
		n.folderTbl.SetHeight(h - 8)
	}
}
