package api

import "net/url"

type ChatMessage struct {
	Role           string `json:"role"`
	Content        string `json:"content"`
	MsgID          string `json:"msg_id,omitempty"`
	ConversationID string `json:"conversation_id,omitempty"`
	Timestamp      string `json:"timestamp,omitempty"`
}

type ChatRequest struct {
	Message        string `json:"message"`
	Model          string `json:"model,omitempty"`
	LocalDate      string `json:"local_date,omitempty"`
	NoHistory      bool   `json:"no_history,omitempty"`
	ConversationID string `json:"conversation_id,omitempty"`
}

type ChatResponse struct {
	Reply          string   `json:"reply"`
	ToolsUsed      []string `json:"tools_used,omitempty"`
	ConversationID string   `json:"conversation_id"`
}

type Conversation struct {
	ConversationID string `json:"conversation_id"`
	Title          string `json:"title,omitempty"`
	CreatedAt      string `json:"created_at,omitempty"`
	UpdatedAt      string `json:"updated_at,omitempty"`
	MessageCount   int    `json:"message_count,omitempty"`
}

type ConversationDetail struct {
	ConversationID string        `json:"conversation_id"`
	Title          string        `json:"title,omitempty"`
	Messages       []ChatMessage `json:"messages"`
}

type AssistantUsage map[string]any
type AssistantMemory map[string]any
type AssistantProfile map[string]any

func (c *Client) Chat(req ChatRequest) (ChatResponse, error) {
	var out ChatResponse
	return out, c.Post("/assistant/chat", req, &out)
}

func (c *Client) ListConversations() ([]Conversation, error) {
	var out []Conversation
	return out, c.Get("/assistant/conversations", &out)
}

func (c *Client) CreateConversation(title string) (Conversation, error) {
	var out Conversation
	return out, c.Post("/assistant/conversations", map[string]string{"title": title}, &out)
}

func (c *Client) GetConversation(id string) (ConversationDetail, error) {
	var out ConversationDetail
	return out, c.Get("/assistant/conversations/"+url.PathEscape(id), &out)
}

func (c *Client) RenameConversation(id, title string) error {
	return c.Patch("/assistant/conversations/"+url.PathEscape(id), map[string]string{"title": title}, nil)
}

func (c *Client) DeleteConversation(id string) error {
	return c.Delete("/assistant/conversations/" + url.PathEscape(id))
}

func (c *Client) AssistantHistory() ([]ChatMessage, error) {
	var out []ChatMessage
	return out, c.Get("/assistant/history", &out)
}

func (c *Client) ClearAssistantHistory() error {
	return c.Delete("/assistant/history")
}

func (c *Client) AssistantUsage() (AssistantUsage, error) {
	out := AssistantUsage{}
	return out, c.Get("/assistant/usage", &out)
}

func (c *Client) AssistantMemory() (AssistantMemory, error) {
	out := AssistantMemory{}
	return out, c.Get("/assistant/memory", &out)
}

func (c *Client) UpdateAssistantContext(masterContext string) error {
	return c.Put("/assistant/memory", map[string]string{"master_context": masterContext}, nil)
}

func (c *Client) UpsertAssistantFact(key, value string) error {
	return c.Put("/assistant/memory/facts/"+url.PathEscape(key), map[string]string{"value": value}, nil)
}

func (c *Client) DeleteAssistantFact(key string) error {
	return c.Delete("/assistant/memory/" + url.PathEscape(key))
}

func (c *Client) AssistantProfile() (AssistantProfile, error) {
	out := AssistantProfile{}
	return out, c.Get("/assistant/profile", &out)
}

func (c *Client) UpdateAssistantProfile(in AssistantProfile) (AssistantProfile, error) {
	out := AssistantProfile{}
	return out, c.Put("/assistant/profile", in, &out)
}

func (c *Client) AnalyzeAssistantProfile() (map[string]any, error) {
	out := map[string]any{}
	return out, c.Post("/assistant/profile/analyze", nil, &out)
}

func (c *Client) CleanupAssistantProfile() (map[string]any, error) {
	out := map[string]any{}
	return out, c.Post("/assistant/profile/cleanup", nil, &out)
}
