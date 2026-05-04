package screens

import (
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

// TestTasksKeyEOpensForm exercises the actual key-event path that a real
// user takes: press 'e' on a row in the tasks table and verify the form
// opens with the right initial state.
func TestTasksKeyEOpensForm(t *testing.T) {
	fb := newFakeBackend(t)
	s := newTasks(fb.client())
	m := runScreen(t, s)

	tasks := m.(*Tasks)
	if len(tasks.filtered) == 0 {
		t.Fatalf("expected one task in filtered list, got %d", len(tasks.filtered))
	}
	if tasks.tbl.Cursor() != 0 {
		t.Errorf("cursor should default to row 0; got %d", tasks.tbl.Cursor())
	}

	// Real user keypress: KeyRunes for 'e'.
	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'e'}})
	tasks = m.(*Tasks)
	if tasks.mode != taskForm {
		t.Fatalf("after pressing 'e', mode should be taskForm; got %d", tasks.mode)
	}
	if tasks.form == nil {
		t.Fatal("form should be non-nil after startEdit")
	}
	if tasks.formData.id != "t1" {
		t.Errorf("formData.id should be t1; got %q", tasks.formData.id)
	}
	if tasks.formData.title != "Old" {
		t.Errorf("formData.title should be loaded as 'Old'; got %q", tasks.formData.title)
	}
}

// TestTasksKeyNOpensForm: 'n' for new task.
func TestTasksKeyNOpensForm(t *testing.T) {
	fb := newFakeBackend(t)
	s := newTasks(fb.client())
	m := runScreen(t, s)

	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'n'}})
	tasks := m.(*Tasks)
	if tasks.mode != taskForm {
		t.Fatalf("after pressing 'n', mode should be taskForm; got %d", tasks.mode)
	}
	if tasks.formData.id != "" {
		t.Errorf("new task should have empty id; got %q", tasks.formData.id)
	}
	if tasks.formData.status != "todo" || tasks.formData.priority != "medium" {
		t.Errorf("new task defaults missing: %+v", tasks.formData)
	}
}

// TestTasksFormCancelEsc: pressing esc in form returns to list mode without
// firing the API.
func TestTasksFormCancelEsc(t *testing.T) {
	fb := newFakeBackend(t)
	s := newTasks(fb.client())
	m := runScreen(t, s)
	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'e'}})
	if m.(*Tasks).mode != taskForm {
		t.Fatal("expected form mode")
	}
	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyEscape})
	if m.(*Tasks).mode != taskList {
		t.Errorf("esc should return to taskList; got %d", m.(*Tasks).mode)
	}
}

// TestNotesKeyEOpensForm: ensures notes 'e' works.
func TestNotesKeyEOpensForm(t *testing.T) {
	fb := newFakeBackend(t)
	s := newNotes(fb.client())
	m := runScreen(t, s)
	notes := m.(*Notes)
	if len(notes.view) == 0 {
		t.Fatalf("expected notes loaded, got %d", len(notes.view))
	}
	// Pressing 'e' on notes only works when a note is loaded as current. From
	// the list, user presses Enter first to open detail, then 'e'. Simulate
	// that flow.
	// Open detail via Enter:
	m = drainCmd(t, m, m.(*Notes).openNote("n1"))
	notes = m.(*Notes)
	if notes.mode != noteDetail {
		t.Fatalf("expected noteDetail; got %d", notes.mode)
	}
	// Now press 'e' on detail.
	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'e'}})
	notes = m.(*Notes)
	if notes.mode != noteForm {
		t.Fatalf("expected noteForm; got %d", notes.mode)
	}
}

// TestHabitsKeyEOpensForm
func TestHabitsKeyEOpensForm(t *testing.T) {
	fb := newFakeBackend(t)
	s := newHabits(fb.client())
	m := runScreen(t, s)
	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'e'}})
	if m.(*Habits).mode != habitForm {
		t.Errorf("expected habitForm; got %d", m.(*Habits).mode)
	}
}

// TestGoalsKeyEOpensForm
func TestGoalsKeyEOpensForm(t *testing.T) {
	fb := newFakeBackend(t)
	s := newGoals(fb.client())
	m := runScreen(t, s)
	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'e'}})
	if m.(*Goals).mode != goalForm {
		t.Errorf("expected goalForm; got %d", m.(*Goals).mode)
	}
}

// TestBookmarksKeyEOpensForm
func TestBookmarksKeyEOpensForm(t *testing.T) {
	fb := newFakeBackend(t)
	s := newBookmarks(fb.client())
	m := runScreen(t, s)
	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'e'}})
	if m.(*Bookmarks).mode != bookmarkForm {
		t.Errorf("expected bookmarkForm; got %d", m.(*Bookmarks).mode)
	}
}

// TestTasksFormReceivesTextInput types into the form's title field via real
// KeyMsg events and verifies the formData updates. Reproduces what a user
// does after pressing 'e'.
func TestTasksFormReceivesTextInput(t *testing.T) {
	fb := newFakeBackend(t)
	s := newTasks(fb.client())
	m := runScreen(t, s)
	// Press 'e' to open form.
	m, cmd := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'e'}})
	m = drainCmd(t, m, cmd)
	tasks := m.(*Tasks)
	if tasks.mode != taskForm {
		t.Fatalf("form did not open; mode=%d", tasks.mode)
	}
	// Send a window-size hint so the form can lay itself out.
	m, _ = m.Update(tea.WindowSizeMsg{Width: 100, Height: 40})
	// Type "X" — title field is selected first.
	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'X'}})
	tasks = m.(*Tasks)
	// huh inputs bind to the *string field. Title should now contain X
	// appended OR the form should accept the rune (depending on huh impl).
	if !contains(tasks.formData.title, "X") && !contains(tasks.form.View(), "X") {
		t.Errorf("after typing X, neither formData.title nor view contains it; title=%q view-len=%d",
			tasks.formData.title, len(tasks.form.View()))
	}
}

func contains(s, sub string) bool {
	if sub == "" {
		return true
	}
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
