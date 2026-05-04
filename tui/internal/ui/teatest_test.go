package ui

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/x/exp/teatest"

	"github.com/neilfarmer/memoire/tui/internal/api"
)

// fakeServer mimics the memoire API for end-to-end UI tests.
func fakeServer(t *testing.T) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/tasks" && r.Method == "GET":
			_, _ = w.Write([]byte(`[{"task_id":"t1","title":"Real task","status":"todo","priority":"high"}]`))
		case r.URL.Path == "/tasks/t1" && r.Method == "PUT":
			_, _ = w.Write([]byte(`{"task_id":"t1"}`))
		case r.URL.Path == "/notes" && r.Method == "GET":
			_, _ = w.Write([]byte(`[{"note_id":"n1","title":"Real note"}]`))
		case r.URL.Path == "/notes/folders":
			_, _ = w.Write([]byte(`[]`))
		case r.URL.Path == "/notes/n1" && r.Method == "GET":
			_, _ = w.Write([]byte(`{"note_id":"n1","title":"Real note","body":"hi"}`))
		case r.URL.Path == "/notes/n1" && r.Method == "PUT":
			_, _ = w.Write([]byte(`{"note_id":"n1"}`))
		case r.URL.Path == "/habits" && r.Method == "GET":
			_, _ = w.Write([]byte(`[]`))
		default:
			_, _ = w.Write([]byte(`[]`))
		}
	}))
	t.Cleanup(srv.Close)
	return srv
}

// TestEndToEnd_TasksLoadsAndShowsRow boots the App via teatest, drives real
// tea program loop, asserts the tasks list renders the row from the API.
func TestEndToEnd_TasksLoadsAndShowsRow(t *testing.T) {
	srv := fakeServer(t)
	client := api.New(srv.URL, "pat_test")
	app := New(client, DefaultFactories(client))

	tm := teatest.NewTestModel(t, app, teatest.WithInitialTermSize(120, 40))

	// Wait for dashboard to render, then jump to Tasks via "2".
	teatest.WaitFor(t, tm.Output(), func(out []byte) bool {
		return strings.Contains(string(out), "Dashboard")
	}, teatest.WithCheckInterval(time.Millisecond*50), teatest.WithDuration(2*time.Second))

	tm.Send(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'2'}})

	teatest.WaitFor(t, tm.Output(), func(out []byte) bool {
		return strings.Contains(string(out), "Real task")
	}, teatest.WithCheckInterval(time.Millisecond*50), teatest.WithDuration(2*time.Second))

	tm.Send(tea.Quit())
	tm.WaitFinished(t, teatest.WithFinalTimeout(2*time.Second))
}

// TestEndToEnd_NotesEditOpensForm verifies that pressing 'e' on the Notes
// list opens the edit form populated with the note body fetched from the
// API. Reproduces the bug we just fixed: noteEditPrepMsg unhandled.
func TestEndToEnd_NotesEditOpensForm(t *testing.T) {
	srv := fakeServer(t)
	client := api.New(srv.URL, "pat_test")
	app := New(client, DefaultFactories(client))

	tm := teatest.NewTestModel(t, app, teatest.WithInitialTermSize(120, 40))

	// Jump to notes via "3".
	tm.Send(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'3'}})

	teatest.WaitFor(t, tm.Output(), func(out []byte) bool {
		return strings.Contains(string(out), "Real note")
	}, teatest.WithCheckInterval(time.Millisecond*50), teatest.WithDuration(2*time.Second))

	// Press 'e' on the list. Expect form to open with title field.
	tm.Send(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'e'}})

	teatest.WaitFor(t, tm.Output(), func(out []byte) bool {
		return strings.Contains(string(out), "Title") &&
			strings.Contains(string(out), "<ctrl+s> save")
	}, teatest.WithCheckInterval(time.Millisecond*50), teatest.WithDuration(3*time.Second))

	// Cancel + quit to clean up.
	tm.Send(tea.KeyMsg{Type: tea.KeyEscape})
	tm.Send(tea.Quit())
	tm.WaitFinished(t, teatest.WithFinalTimeout(2*time.Second))
}

// TestEndToEnd_OSCResponseDoesNotFreeze sends synthetic OSC-like key events
// and verifies the program filters them rather than entering a feedback loop.
func TestEndToEnd_OSCResponseDoesNotFreeze(t *testing.T) {
	srv := fakeServer(t)
	client := api.New(srv.URL, "pat_test")
	app := New(client, DefaultFactories(client))
	tm := teatest.NewTestModel(t, app, teatest.WithInitialTermSize(120, 40))

	// Spam OSC-shaped key strings. The filter should drop them.
	for i := 0; i < 50; i++ {
		tm.Send(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("]11;rgb:2828/2c2c/3434")})
	}
	tm.Send(tea.Quit())
	tm.WaitFinished(t, teatest.WithFinalTimeout(2*time.Second))
}
