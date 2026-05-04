package screens

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/neilfarmer/memoire/tui/internal/api"
)

// fakeBackend collects requests and returns canned responses for the CRUD
// endpoints exercised by the edit flow tests.
type fakeBackend struct {
	mu       sync.Mutex
	calls    []string
	bodies   []string
	srv      *httptest.Server
}

func newFakeBackend(t *testing.T) *fakeBackend {
	t.Helper()
	fb := &fakeBackend{}
	fb.srv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fb.mu.Lock()
		fb.calls = append(fb.calls, r.Method+" "+r.URL.Path)
		body, _ := io.ReadAll(r.Body)
		fb.bodies = append(fb.bodies, string(body))
		fb.mu.Unlock()

		switch {
		case r.URL.Path == "/tasks" && r.Method == "GET":
			_, _ = w.Write([]byte(`[{"task_id":"t1","title":"Old","status":"todo","priority":"low"}]`))
		case r.URL.Path == "/tasks" && r.Method == "POST":
			w.WriteHeader(http.StatusCreated)
			_, _ = w.Write([]byte(`{"task_id":"t2","title":"New"}`))
		case r.URL.Path == "/tasks/t1" && r.Method == "PUT":
			_, _ = w.Write([]byte(`{"task_id":"t1","title":"Updated"}`))
		case r.URL.Path == "/tasks/t1" && r.Method == "DELETE":
			w.WriteHeader(http.StatusNoContent)

		case r.URL.Path == "/notes" && r.Method == "GET":
			_, _ = w.Write([]byte(`[{"note_id":"n1","title":"Note 1"}]`))
		case r.URL.Path == "/notes/folders" && r.Method == "GET":
			_, _ = w.Write([]byte(`[{"folder_id":"f1","name":"Inbox"}]`))
		case r.URL.Path == "/notes" && r.Method == "POST":
			w.WriteHeader(http.StatusCreated)
			_, _ = w.Write([]byte(`{"note_id":"n2","title":"New"}`))
		case r.URL.Path == "/notes/n1" && r.Method == "GET":
			_, _ = w.Write([]byte(`{"note_id":"n1","title":"Note 1","body":"hello"}`))
		case r.URL.Path == "/notes/n1" && r.Method == "PUT":
			_, _ = w.Write([]byte(`{"note_id":"n1","title":"Updated"}`))

		case r.URL.Path == "/habits" && r.Method == "GET":
			_, _ = w.Write([]byte(`[{"habit_id":"h1","name":"Run"}]`))
		case r.URL.Path == "/habits" && r.Method == "POST":
			w.WriteHeader(http.StatusCreated)
			_, _ = w.Write([]byte(`{"habit_id":"h2"}`))
		case r.URL.Path == "/habits/h1" && r.Method == "PUT":
			_, _ = w.Write([]byte(`{"habit_id":"h1","name":"Run updated"}`))

		case r.URL.Path == "/goals" && r.Method == "GET":
			_, _ = w.Write([]byte(`[{"goal_id":"g1","title":"G","status":"active"}]`))
		case r.URL.Path == "/goals" && r.Method == "POST":
			w.WriteHeader(http.StatusCreated)
			_, _ = w.Write([]byte(`{"goal_id":"g2"}`))
		case r.URL.Path == "/goals/g1" && r.Method == "PUT":
			_, _ = w.Write([]byte(`{"goal_id":"g1"}`))

		case r.URL.Path == "/bookmarks" && r.Method == "GET":
			_, _ = w.Write([]byte(`[{"bookmark_id":"b1","url":"https://x","title":"X"}]`))
		case r.URL.Path == "/bookmarks" && r.Method == "POST":
			w.WriteHeader(http.StatusCreated)
			_, _ = w.Write([]byte(`{"bookmark_id":"b2"}`))
		case r.URL.Path == "/bookmarks/b1" && r.Method == "PUT":
			_, _ = w.Write([]byte(`{"bookmark_id":"b1"}`))

		case r.URL.Path == "/journal" && r.Method == "GET":
			_, _ = w.Write([]byte(`[]`))
		case strings.HasPrefix(r.URL.Path, "/journal/") && r.Method == "GET":
			w.WriteHeader(http.StatusNotFound)
		case strings.HasPrefix(r.URL.Path, "/journal/") && r.Method == "PUT":
			_, _ = w.Write([]byte(`{"entry_date":"2026-04-30","content":"hi"}`))

		case r.URL.Path == "/feeds" && r.Method == "GET":
			_, _ = w.Write([]byte(`[]`))
		case r.URL.Path == "/feeds" && r.Method == "POST":
			w.WriteHeader(http.StatusCreated)
			_, _ = w.Write([]byte(`{"feed_id":"fd1"}`))
		case r.URL.Path == "/feeds/articles" && r.Method == "GET":
			_, _ = w.Write([]byte(`[]`))

		case r.URL.Path == "/debts" && r.Method == "GET":
			_, _ = w.Write([]byte(`[]`))
		case r.URL.Path == "/income" && r.Method == "GET":
			_, _ = w.Write([]byte(`[]`))
		case r.URL.Path == "/fixed-expenses" && r.Method == "GET":
			_, _ = w.Write([]byte(`[]`))
		case r.URL.Path == "/finances/summary" && r.Method == "GET":
			_, _ = w.Write([]byte(`{}`))
		case r.URL.Path == "/debts" && r.Method == "POST":
			w.WriteHeader(http.StatusCreated)
			_, _ = w.Write([]byte(`{"debt_id":"d1"}`))

		case r.URL.Path == "/settings" && r.Method == "GET":
			_, _ = w.Write([]byte(`{"display_name":"Neil"}`))
		case r.URL.Path == "/settings" && r.Method == "PUT":
			_, _ = w.Write([]byte(`{"display_name":"Updated"}`))

		case r.URL.Path == "/health" && r.Method == "GET":
			_, _ = w.Write([]byte(`[]`))
		case strings.HasPrefix(r.URL.Path, "/health/") && r.Method == "GET":
			w.WriteHeader(http.StatusNotFound)
		case strings.HasPrefix(r.URL.Path, "/health/") && r.Method == "PUT":
			_, _ = w.Write([]byte(`{"log_date":"2026-04-30"}`))

		case r.URL.Path == "/nutrition" && r.Method == "GET":
			_, _ = w.Write([]byte(`[]`))
		case strings.HasPrefix(r.URL.Path, "/nutrition/") && r.Method == "GET":
			w.WriteHeader(http.StatusNotFound)
		case strings.HasPrefix(r.URL.Path, "/nutrition/") && r.Method == "PUT":
			_, _ = w.Write([]byte(`{"log_date":"2026-04-30"}`))

		case r.URL.Path == "/favorites" && r.Method == "GET":
			_, _ = w.Write([]byte(`[]`))
		case r.URL.Path == "/tokens" && r.Method == "GET":
			_, _ = w.Write([]byte(`[]`))
		case r.URL.Path == "/tokens" && r.Method == "POST":
			w.WriteHeader(http.StatusCreated)
			_, _ = w.Write([]byte(`{"token_id":"k1","name":"x","token":"pat_secret"}`))

		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	t.Cleanup(fb.srv.Close)
	return fb
}

func (fb *fakeBackend) saw(method, path string) bool {
	want := method + " " + path
	fb.mu.Lock()
	defer fb.mu.Unlock()
	for _, c := range fb.calls {
		if c == want {
			return true
		}
	}
	return false
}

func (fb *fakeBackend) lastBody() string {
	fb.mu.Lock()
	defer fb.mu.Unlock()
	if len(fb.bodies) == 0 {
		return ""
	}
	return fb.bodies[len(fb.bodies)-1]
}

func (fb *fakeBackend) bodyContains(s string) bool {
	fb.mu.Lock()
	defer fb.mu.Unlock()
	for _, b := range fb.bodies {
		if strings.Contains(b, s) {
			return true
		}
	}
	return false
}

func (fb *fakeBackend) client() *api.Client { return api.New(fb.srv.URL, "pat_test") }

// drainCmd executes a tea.Cmd synchronously and feeds the result back to the
// model. It loops to drain tea.Batch chains.
func drainCmd(t *testing.T, m tea.Model, cmd tea.Cmd) tea.Model {
	t.Helper()
	for cmd != nil {
		msg := cmd()
		if batch, ok := msg.(tea.BatchMsg); ok {
			for _, c := range batch {
				m = drainCmd(t, m, c)
			}
			cmd = nil
			continue
		}
		var nextCmd tea.Cmd
		m, nextCmd = m.Update(msg)
		cmd = nextCmd
	}
	return m
}

func runScreen(t *testing.T, s tea.Model) tea.Model {
	t.Helper()
	cmd := s.Init()
	s.(interface{ SetSize(w, h int) }).SetSize(120, 40)
	return drainCmd(t, s, cmd)
}

// pressKey synthesises a key event by string name and returns the next model.
func pressKey(t *testing.T, m tea.Model, key string) tea.Model {
	t.Helper()
	var msg tea.KeyMsg
	switch key {
	case "enter":
		msg = tea.KeyMsg{Type: tea.KeyEnter}
	case "esc":
		msg = tea.KeyMsg{Type: tea.KeyEscape}
	case "tab":
		msg = tea.KeyMsg{Type: tea.KeyTab}
	case "down":
		msg = tea.KeyMsg{Type: tea.KeyDown}
	case "up":
		msg = tea.KeyMsg{Type: tea.KeyUp}
	default:
		msg = tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(key)}
	}
	out, cmd := m.Update(msg)
	return drainCmd(t, out, cmd)
}

func TestTasksEditFlow(t *testing.T) {
	fb := newFakeBackend(t)
	s := newTasks(fb.client())
	m := runScreen(t, s)

	// Verify list loaded.
	if !fb.saw("GET", "/tasks") {
		t.Fatal("list call missing")
	}
	// Press 'e' on first row -> form opens.
	m = pressKey(t, m, "e")
	tasks := m.(*Tasks)
	if tasks.mode != taskForm {
		t.Fatalf("expected taskForm mode; got %d", tasks.mode)
	}
	// Force form completion through API path directly (form requires interactive
	// huh navigation that we can't drive synchronously). Tests the submit
	// path itself.
	tasks.formData.id = "t1"
	tasks.formData.title = "Updated"
	tasks.formData.status = "todo"
	cmd := tasks.submitForm()
	drainCmd(t, tasks, cmd)
	if !fb.saw("PUT", "/tasks/t1") {
		t.Errorf("update call missing; saw: %v", fb.calls)
	}
	if !fb.bodyContains("Updated") {
		t.Errorf("title not sent; bodies=%v", fb.bodies)
	}
}

func TestTasksCreateFlow(t *testing.T) {
	fb := newFakeBackend(t)
	s := newTasks(fb.client())
	m := runScreen(t, s)
	tasks := m.(*Tasks)
	tasks.formData = taskFormState{title: "New task", status: "todo"}
	drainCmd(t, tasks, tasks.submitForm())
	if !fb.saw("POST", "/tasks") {
		t.Errorf("create call missing; saw: %v", fb.calls)
	}
}

func TestNotesEditFlow(t *testing.T) {
	fb := newFakeBackend(t)
	s := newNotes(fb.client())
	m := runScreen(t, s)
	notes := m.(*Notes)
	notes.formData = noteFormState{id: "n1", title: "Updated", body: "hi"}
	drainCmd(t, notes, notes.submitForm())
	if !fb.saw("PUT", "/notes/n1") {
		t.Errorf("update missing; saw %v", fb.calls)
	}
}

func TestNotesCreateFlow(t *testing.T) {
	fb := newFakeBackend(t)
	s := newNotes(fb.client())
	m := runScreen(t, s)
	notes := m.(*Notes)
	notes.formData = noteFormState{title: "New", body: "x"}
	drainCmd(t, notes, notes.submitForm())
	if !fb.saw("POST", "/notes") {
		t.Errorf("create missing; saw %v", fb.calls)
	}
}

func TestHabitsCreateFlow(t *testing.T) {
	fb := newFakeBackend(t)
	s := newHabits(fb.client())
	m := runScreen(t, s)
	h := m.(*Habits)
	h.formIn = habitFormState{name: "Read"}
	drainCmd(t, h, h.submit())
	if !fb.saw("POST", "/habits") {
		t.Errorf("create missing; saw %v", fb.calls)
	}
}

func TestHabitsUpdateFlow(t *testing.T) {
	fb := newFakeBackend(t)
	s := newHabits(fb.client())
	m := runScreen(t, s)
	h := m.(*Habits)
	h.formIn = habitFormState{id: "h1", name: "Run+"}
	drainCmd(t, h, h.submit())
	if !fb.saw("PUT", "/habits/h1") {
		t.Errorf("update missing; saw %v", fb.calls)
	}
}

func TestGoalsCreateFlow(t *testing.T) {
	fb := newFakeBackend(t)
	s := newGoals(fb.client())
	m := runScreen(t, s)
	g := m.(*Goals)
	g.formIn = goalFormState{title: "Goal A", status: "active"}
	drainCmd(t, g, g.submit())
	if !fb.saw("POST", "/goals") {
		t.Errorf("create missing; saw %v", fb.calls)
	}
}

func TestGoalsUpdateFlow(t *testing.T) {
	fb := newFakeBackend(t)
	s := newGoals(fb.client())
	m := runScreen(t, s)
	g := m.(*Goals)
	g.formIn = goalFormState{id: "g1", title: "X"}
	drainCmd(t, g, g.submit())
	if !fb.saw("PUT", "/goals/g1") {
		t.Errorf("update missing; saw %v", fb.calls)
	}
}

func TestBookmarksCreateFlow(t *testing.T) {
	fb := newFakeBackend(t)
	s := newBookmarks(fb.client())
	m := runScreen(t, s)
	b := m.(*Bookmarks)
	b.formIn = bookmarkFormState{url: "https://example.com", title: "ex"}
	drainCmd(t, b, b.submit())
	if !fb.saw("POST", "/bookmarks") {
		t.Errorf("create missing; saw %v", fb.calls)
	}
}

func TestBookmarksUpdateFlow(t *testing.T) {
	fb := newFakeBackend(t)
	s := newBookmarks(fb.client())
	m := runScreen(t, s)
	b := m.(*Bookmarks)
	b.formIn = bookmarkFormState{id: "b1", url: "https://x", title: "y"}
	drainCmd(t, b, b.submit())
	if !fb.saw("PUT", "/bookmarks/b1") {
		t.Errorf("update missing; saw %v", fb.calls)
	}
}

func TestJournalUpsertFlow(t *testing.T) {
	fb := newFakeBackend(t)
	s := newJournal(fb.client())
	m := runScreen(t, s)
	j := m.(*Journal)
	j.formData = journalFormState{title: "Day", body: "hi"}
	drainCmd(t, j, j.submit())
	// Expect PUT /journal/<today>.
	found := false
	for _, c := range fb.calls {
		if strings.HasPrefix(c, "PUT /journal/") {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("journal upsert missing; saw %v", fb.calls)
	}
}

func TestHealthEditFlow(t *testing.T) {
	fb := newFakeBackend(t)
	s := newHealth(fb.client())
	m := runScreen(t, s)
	h := m.(*Health)
	h.formIn = healthFormState{steps: "5000", weight: "180"}
	drainCmd(t, h, h.submit())
	found := false
	for _, c := range fb.calls {
		if strings.HasPrefix(c, "PUT /health/") {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("health upsert missing; saw %v", fb.calls)
	}
}

func TestNutritionAddMealFlow(t *testing.T) {
	fb := newFakeBackend(t)
	s := newNutrition(fb.client())
	m := runScreen(t, s)
	n := m.(*Nutrition)
	n.formIn = mealFormState{name: "Eggs", calories: "200"}
	drainCmd(t, n, n.submitMeal())
	found := false
	for _, c := range fb.calls {
		if strings.HasPrefix(c, "PUT /nutrition/") {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("nutrition upsert missing; saw %v", fb.calls)
	}
}

func TestSettingsUpdateFlow(t *testing.T) {
	fb := newFakeBackend(t)
	s := newSettings(fb.client())
	m := runScreen(t, s)
	st := m.(*Settings)
	st.formIn = settingsForm{displayName: "Updated", darkMode: true}
	drainCmd(t, st, st.submit())
	if !fb.saw("PUT", "/settings") {
		t.Errorf("settings update missing; saw %v", fb.calls)
	}
}

func TestFinancesCreateDebtFlow(t *testing.T) {
	fb := newFakeBackend(t)
	s := newFinances(fb.client())
	m := runScreen(t, s)
	f := m.(*Finances)
	f.tab = tabDebts
	f.formIn = financeFormState{name: "Card", debtType: "credit_card", amount: "100"}
	drainCmd(t, f, f.submit())
	if !fb.saw("POST", "/debts") {
		t.Errorf("debt create missing; saw %v", fb.calls)
	}
}

func TestFeedsAddFlow(t *testing.T) {
	fb := newFakeBackend(t)
	s := newFeeds(fb.client())
	m := runScreen(t, s)
	f := m.(*Feeds)
	f.addURL = "https://example.com/rss"
	drainCmd(t, f, f.submitAdd())
	if !fb.saw("POST", "/feeds") {
		t.Errorf("feed add missing; saw %v", fb.calls)
	}
}

func TestTokensCreateFlow(t *testing.T) {
	fb := newFakeBackend(t)
	s := newTokens(fb.client())
	m := runScreen(t, s)
	tk := m.(*Tokens)
	tk.formName = "test"
	drainCmd(t, tk, tk.submit())
	if !fb.saw("POST", "/tokens") {
		t.Errorf("token create missing; saw %v", fb.calls)
	}
}
