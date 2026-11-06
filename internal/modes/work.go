package modes

import (
	"ark/internal/actions"
)

// RunWorkMode initializes the primary development environment across four macOS Spaces.
// Layout:
//   - Space 1: Media & Web Browsing (Spotify, Google Chrome)
//   - Space 2: Core IDE & Documentation (Visual Studio Code, Notes)
//   - Space 3: Research Environment (Safari)
//   - Space 4: Terminal & Servers (Ollama, Chainlit)
func RunWorkMode() {
	actions.GoToFirstSpace()
	actions.RunCommand(`delay 0.5`)

	// Space 1: Media & Web Browsing
	actions.RunCommand(`tell application "Spotify" to activate`)
	actions.RunCommand(`delay 0.4`)
	actions.RunCommand(`tell application "Spotify" to play track "spotify:playlist:1CD9FdYqz6fNRVbw45vLNy"`)
	actions.RunCommand(`delay 0.4`)
	actions.RunCommand(`tell application "Google Chrome" to activate`)
	actions.RunCommand(`tell application "Google Chrome" to open location "https://mail.google.com"`)
	actions.RunCommand(`delay 1.0`)

	// Space 2: Core IDE & Documentation
	actions.SwitchSpaceRight()
	actions.RunCommand(`delay 1.2`)
	actions.RunCommand(`tell application "Visual Studio Code" to activate`)
	actions.RunCommand(`delay 0.6`)
	actions.RunCommand(`tell application "Notes" to activate`)
	actions.RunCommand(`delay 1.0`)

	// Space 3: Research Environment
	actions.SwitchSpaceRight()
	actions.RunCommand(`delay 1.2`)
	actions.RunCommand(`
		tell application "Safari"
			reopen
			activate
		end tell
	`)
	actions.RunCommand(`delay 2.0`)

	// Space 4: Terminal & Servers
	actions.SwitchSpaceRight()
	actions.RunCommand(`delay 1.2`)
	actions.RunCommand(`
		tell application "Terminal"
			activate
			do script "cd ~/Desktop/ark && source venv/bin/activate && ollama serve"
		end tell
	`)
	actions.RunCommand(`delay 3.0`)
	actions.RunCommand(`
		tell application "Terminal"
			activate
			do script "cd ~/Desktop/ark && source venv/bin/activate && venv/bin/chainlit run chat_ui.py"
		end tell
	`)
	actions.RunCommand(`delay 1.0`)

	actions.PlaySystemSound("ark_finish.wav")
}
