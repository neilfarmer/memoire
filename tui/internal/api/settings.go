package api

type Settings map[string]any

func (c *Client) GetSettings() (Settings, error) {
	out := Settings{}
	return out, c.Get("/settings", &out)
}

func (c *Client) UpdateSettings(in Settings) (Settings, error) {
	out := Settings{}
	return out, c.Put("/settings", in, &out)
}

func (c *Client) TestNotification(provider, recipient string) error {
	body := map[string]string{}
	if provider != "" {
		body["provider"] = provider
	}
	if recipient != "" {
		body["recipient"] = recipient
	}
	return c.Post("/settings/test-notification", body, nil)
}
