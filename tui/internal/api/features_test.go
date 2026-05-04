package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// route registers a handler for an exact method+path match. Tests fail fast on
// unexpected calls so type errors in URL templates show up immediately.
type route struct {
	method, path string
	body         string
	status       int
}

func mux(t *testing.T, routes ...route) http.Handler {
	t.Helper()
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		for _, rt := range routes {
			if r.Method == rt.method && r.URL.Path == rt.path {
				if rt.status != 0 {
					w.WriteHeader(rt.status)
				}
				if rt.body != "" {
					_, _ = w.Write([]byte(rt.body))
				}
				return
			}
		}
		t.Errorf("unexpected request: %s %s", r.Method, r.URL.Path)
		w.WriteHeader(http.StatusNotFound)
	})
}

func TestTasksRoundTrip(t *testing.T) {
	srv := httptest.NewServer(mux(t,
		route{"GET", "/tasks", `[{"task_id":"t1","title":"Buy milk"}]`, 0},
		route{"POST", "/tasks", `{"task_id":"t2","title":"x"}`, 201},
		route{"PUT", "/tasks/t1", `{"task_id":"t1","title":"updated"}`, 0},
		route{"DELETE", "/tasks/t1", "", 204},
	))
	defer srv.Close()
	c := New(srv.URL, "pat_test")
	tasks, err := c.ListTasks()
	if err != nil || len(tasks) != 1 || tasks[0].Title != "Buy milk" {
		t.Errorf("list: %v %v", tasks, err)
	}
	if _, err := c.CreateTask(TaskInput{Title: "x"}); err != nil {
		t.Errorf("create: %v", err)
	}
	if _, err := c.UpdateTask("t1", TaskInput{Title: "updated"}); err != nil {
		t.Errorf("update: %v", err)
	}
	if err := c.DeleteTask("t1"); err != nil {
		t.Errorf("delete: %v", err)
	}
}

func TestNotesQueryParam(t *testing.T) {
	got := ""
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got = r.URL.RawQuery
		_, _ = w.Write([]byte("[]"))
	}))
	defer srv.Close()
	c := New(srv.URL, "pat_test")
	if _, err := c.ListNotes("hello world"); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "q=hello+world") && !strings.Contains(got, "q=hello%20world") {
		t.Errorf("query=%q", got)
	}
}

func TestHabitsToggleSendsBody(t *testing.T) {
	var seenBody map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewDecoder(r.Body).Decode(&seenBody)
		_, _ = w.Write([]byte(`{"habit_id":"h","log_date":"2026-04-30","done":true}`))
	}))
	defer srv.Close()
	c := New(srv.URL, "pat_test")
	res, err := c.ToggleHabit("h", "2026-04-30")
	if err != nil {
		t.Fatal(err)
	}
	if !res.Done {
		t.Error("done should be true")
	}
	if seenBody["log_date"] != "2026-04-30" {
		t.Errorf("body=%v", seenBody)
	}
}

func TestJournalUpsert(t *testing.T) {
	srv := httptest.NewServer(mux(t,
		route{"PUT", "/journal/2026-04-30", `{"entry_date":"2026-04-30","content":"hi"}`, 0},
	))
	defer srv.Close()
	c := New(srv.URL, "pat_test")
	got, err := c.UpsertJournal("2026-04-30", JournalInput{Content: "hi"})
	if err != nil {
		t.Fatal(err)
	}
	if got.Content != "hi" {
		t.Errorf("content=%q", got.Content)
	}
}

func TestFinancesSummary(t *testing.T) {
	srv := httptest.NewServer(mux(t,
		route{"GET", "/finances/summary", `{"total_income":5000,"total_expenses":3000,"total_debt":12000,"net_cash_flow":2000}`, 0},
	))
	defer srv.Close()
	c := New(srv.URL, "pat_test")
	s, err := c.FinancesSummary()
	if err != nil {
		t.Fatal(err)
	}
	if s.TotalIncome != 5000 || s.NetCashFlow != 2000 {
		t.Errorf("summary=%+v", s)
	}
}

func TestTokensPATForbidden(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
	}))
	defer srv.Close()
	c := New(srv.URL, "pat_test")
	_, err := c.ListTokens()
	if err == nil {
		t.Fatal("expected error")
	}
	// the sentinel should propagate
	if err.Error() == "" || !errorContains(err, "tokens") {
		t.Errorf("err=%v", err)
	}
}

func errorContains(err error, sub string) bool {
	return err != nil && (containsFold(err.Error(), sub))
}

func containsFold(s, sub string) bool {
	return strings.Contains(strings.ToLower(s), strings.ToLower(sub))
}

func TestExportReturnsURL(t *testing.T) {
	srv := httptest.NewServer(mux(t,
		route{"GET", "/export", `{"url":"https://s3.example/zip"}`, 0},
	))
	defer srv.Close()
	c := New(srv.URL, "pat_test")
	res, err := c.Export()
	if err != nil {
		t.Fatal(err)
	}
	if res.URL != "https://s3.example/zip" {
		t.Errorf("url=%q", res.URL)
	}
}

func TestAssistantChat(t *testing.T) {
	srv := httptest.NewServer(mux(t,
		route{"POST", "/assistant/chat", `{"reply":"hi","conversation_id":"c1"}`, 0},
	))
	defer srv.Close()
	c := New(srv.URL, "pat_test")
	res, err := c.Chat(ChatRequest{Message: "yo"})
	if err != nil {
		t.Fatal(err)
	}
	if res.Reply != "hi" || res.ConversationID != "c1" {
		t.Errorf("res=%+v", res)
	}
}
