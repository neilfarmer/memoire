package api

import (
	"net/url"
)

type NoteSummary struct {
	NoteID    string   `json:"note_id"`
	Title     string   `json:"title"`
	Preview   string   `json:"preview,omitempty"`
	Tags      []string `json:"tags,omitempty"`
	FolderID  string   `json:"folder_id,omitempty"`
	UpdatedAt string   `json:"updated_at,omitempty"`
}

type Note struct {
	NoteID    string   `json:"note_id"`
	Title     string   `json:"title"`
	Body      string   `json:"body"`
	Tags      []string `json:"tags,omitempty"`
	FolderID  string   `json:"folder_id,omitempty"`
	UpdatedAt string   `json:"updated_at,omitempty"`
	CreatedAt string   `json:"created_at,omitempty"`
}

type NoteInput struct {
	FolderID string   `json:"folder_id,omitempty"`
	Title    string   `json:"title,omitempty"`
	Body     string   `json:"body,omitempty"`
	Tags     []string `json:"tags,omitempty"`
}

type NoteFolder struct {
	FolderID string `json:"folder_id"`
	Name     string `json:"name"`
	Color    string `json:"color,omitempty"`
	ParentID string `json:"parent_id,omitempty"`
}

type NoteFolderInput struct {
	Name     string `json:"name,omitempty"`
	Color    string `json:"color,omitempty"`
	ParentID string `json:"parent_id,omitempty"`
}

type AttachmentRef struct {
	AttachmentID string `json:"attachment_id"`
	UploadURL    string `json:"upload_url,omitempty"`
	Key          string `json:"key,omitempty"`
}

func (c *Client) ListNotes(query string) ([]NoteSummary, error) {
	q := url.Values{}
	if query != "" {
		q.Set("q", query)
	}
	var out []NoteSummary
	return out, c.GetQ("/notes", q, &out)
}

func (c *Client) GetNote(id string) (Note, error) {
	var out Note
	return out, c.Get("/notes/"+url.PathEscape(id), &out)
}

func (c *Client) CreateNote(in NoteInput) (Note, error) {
	var out Note
	return out, c.Post("/notes", in, &out)
}

func (c *Client) UpdateNote(id string, in NoteInput) (Note, error) {
	var out Note
	return out, c.Put("/notes/"+url.PathEscape(id), in, &out)
}

func (c *Client) DeleteNote(id string) error {
	return c.Delete("/notes/" + url.PathEscape(id))
}

func (c *Client) ListNoteFolders() ([]NoteFolder, error) {
	var out []NoteFolder
	return out, c.Get("/notes/folders", &out)
}

func (c *Client) CreateNoteFolder(in NoteFolderInput) (NoteFolder, error) {
	var out NoteFolder
	return out, c.Post("/notes/folders", in, &out)
}

func (c *Client) UpdateNoteFolder(id string, in NoteFolderInput) (NoteFolder, error) {
	var out NoteFolder
	return out, c.Put("/notes/folders/"+url.PathEscape(id), in, &out)
}

func (c *Client) DeleteNoteFolder(id string) error {
	return c.Delete("/notes/folders/" + url.PathEscape(id))
}

func (c *Client) RequestNoteImageUpload(in map[string]any) (AttachmentRef, error) {
	var out AttachmentRef
	return out, c.Post("/notes/images", in, &out)
}

func (c *Client) RequestNoteAttachment(noteID string, in map[string]any) (AttachmentRef, error) {
	var out AttachmentRef
	return out, c.Post("/notes/"+url.PathEscape(noteID)+"/attachments", in, &out)
}

func (c *Client) DeleteNoteAttachment(noteID, attachmentID string) error {
	return c.Delete("/notes/" + url.PathEscape(noteID) + "/attachments/" + url.PathEscape(attachmentID))
}

// AttachmentURL composes the GET URL for a note attachment so the caller can
// hand it off to $BROWSER. The redirect to a presigned S3 URL is followed by
// the browser, not this client.
func (c *Client) AttachmentURL(noteID, attachmentID string) string {
	return c.BaseURL + "/notes/" + url.PathEscape(noteID) + "/attachments/" + url.PathEscape(attachmentID)
}
