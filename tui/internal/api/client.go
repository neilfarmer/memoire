package api

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/neilfarmer/memoire/tui/internal/logx"
)

// Client wraps an authenticated HTTP client for the memoire API.
type Client struct {
	BaseURL string
	PAT     string
	HTTP    *http.Client
}

// New builds a Client with a default 30s timeout.
func New(baseURL, pat string) *Client {
	return &Client{
		BaseURL: strings.TrimRight(baseURL, "/"),
		PAT:     pat,
		HTTP:    &http.Client{Timeout: 30 * time.Second},
	}
}

// APIError is returned for non-2xx responses.
type APIError struct {
	Status  int
	Message string
	Body    string
}

func (e *APIError) Error() string {
	if e.Message != "" {
		return fmt.Sprintf("api: %d %s", e.Status, e.Message)
	}
	return fmt.Sprintf("api: %d", e.Status)
}

// ErrPATForbidden surfaces 403s from /tokens routes (PATs cannot manage PATs).
var ErrPATForbidden = errors.New("personal access tokens cannot manage tokens; sign in via the web UI")

// IsForbidden reports whether err represents a 403 response.
func IsForbidden(err error) bool {
	var ae *APIError
	if errors.As(err, &ae) {
		return ae.Status == http.StatusForbidden
	}
	return false
}

// IsNotFound reports whether err represents a 404 response.
func IsNotFound(err error) bool {
	var ae *APIError
	if errors.As(err, &ae) {
		return ae.Status == http.StatusNotFound
	}
	return false
}

// Do executes a request and decodes the JSON response into out (which may be nil).
func (c *Client) Do(method, path string, body, out any) error {
	return c.DoQuery(method, path, nil, body, out)
}

// DoQuery is like Do but appends url.Values to the request URL.
func (c *Client) DoQuery(method, path string, q url.Values, body, out any) error {
	if c.BaseURL == "" {
		return errors.New("api: BaseURL not set")
	}
	if c.PAT == "" {
		return errors.New("api: PAT not set")
	}
	full := c.BaseURL + path
	if len(q) > 0 {
		full += "?" + q.Encode()
	}
	var reader io.Reader
	if body != nil {
		buf, err := json.Marshal(body)
		if err != nil {
			return fmt.Errorf("marshal body: %w", err)
		}
		reader = bytes.NewReader(buf)
	}
	req, err := http.NewRequest(method, full, reader)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+c.PAT)
	req.Header.Set("Accept", "application/json")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	start := time.Now()
	resp, err := c.HTTP.Do(req)
	if err != nil {
		logx.Error("api request failed", "method", method, "path", path, "err", err)
		return fmt.Errorf("%s %s: %w", method, path, err)
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)
	logx.Debug("api response", "method", method, "path", path, "status", resp.StatusCode, "elapsed_ms", time.Since(start).Milliseconds(), "body_len", len(respBody))
	if resp.StatusCode >= 400 {
		ae := &APIError{Status: resp.StatusCode, Body: string(respBody)}
		var parsed struct {
			Error   string `json:"error"`
			Message string `json:"message"`
		}
		if json.Unmarshal(respBody, &parsed) == nil {
			if parsed.Error != "" {
				ae.Message = parsed.Error
			} else if parsed.Message != "" {
				ae.Message = parsed.Message
			}
		}
		// Surface PAT-forbidden errors with the dedicated sentinel for the
		// tokens screen (which needs to disable mutating actions).
		if ae.Status == http.StatusForbidden && strings.HasPrefix(path, "/tokens") {
			return errors.Join(ErrPATForbidden, ae)
		}
		logx.Warn("api error", "method", method, "path", path, "status", ae.Status, "msg", ae.Message)
		return ae
	}
	if out == nil || len(respBody) == 0 {
		return nil
	}
	if err := json.Unmarshal(respBody, out); err != nil {
		return fmt.Errorf("decode %s response: %w", path, err)
	}
	return nil
}

// Convenience verb wrappers.

func (c *Client) Get(path string, out any) error  { return c.Do(http.MethodGet, path, nil, out) }
func (c *Client) GetQ(path string, q url.Values, out any) error {
	return c.DoQuery(http.MethodGet, path, q, nil, out)
}
func (c *Client) Post(path string, body, out any) error {
	return c.Do(http.MethodPost, path, body, out)
}
func (c *Client) Put(path string, body, out any) error {
	return c.Do(http.MethodPut, path, body, out)
}
func (c *Client) Patch(path string, body, out any) error {
	return c.Do(http.MethodPatch, path, body, out)
}
func (c *Client) Delete(path string) error { return c.Do(http.MethodDelete, path, nil, nil) }
