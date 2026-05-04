package components

import (
	"os"
	"os/exec"
	"runtime"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
)

// OpenedURLMsg confirms a URL was handed off to the OS opener.
type OpenedURLMsg struct {
	URL string
	Err error
}

// OpenURL hands a URL to $BROWSER, falling back to the OS default opener.
func OpenURL(target string) tea.Cmd {
	return func() tea.Msg {
		var cmd *exec.Cmd
		if browser := os.Getenv("BROWSER"); browser != "" {
			parts := strings.Fields(browser)
			args := append(parts[1:], target)
			cmd = exec.Command(parts[0], args...)
		} else {
			switch runtime.GOOS {
			case "darwin":
				cmd = exec.Command("open", target)
			case "windows":
				cmd = exec.Command("rundll32", "url.dll,FileProtocolHandler", target)
			default:
				cmd = exec.Command("xdg-open", target)
			}
		}
		err := cmd.Start()
		return OpenedURLMsg{URL: target, Err: err}
	}
}
