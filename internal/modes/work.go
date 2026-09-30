package modes

import "ark/internal/actions"

// RunWorkMode initializes the primary development environment (Spotify, VS Code, Chrome, Notes).
func RunWorkMode() {
	actions.RunCommand(`tell application "Spotify" to activate`)
	actions.RunCommand(`delay 0.5`)
	actions.RunCommand(`tell application "Spotify" to play track "spotify:playlist:1CD9FdYqz6fNRVbw45vLNy"`)

	actions.RunCommand(`delay 0.5`)
	actions.RunCommand(`tell application "Visual Studio Code" to activate`)

	actions.RunCommand(`delay 0.5`)
	actions.RunCommand(`tell application "Google Chrome" to activate`)
	OpenGmailAndRestore()

	actions.RunCommand(`delay 0.5`)
	actions.RunCommand(`tell application "Notes" to activate`)

	actions.PlaySystemSound("ark_finish.wav")
}

// OpenGmailAndRestore opens Gmail in Chrome and restores previous tabs via system shortcut.
func OpenGmailAndRestore() {
	actions.RunCommand(`tell application "Google Chrome" to open location "https://mail.google.com"`)
	actions.RunCommand(`delay 1.0`)
	actions.RunCommand(`tell application "System Events" to keystroke "t" using {command down, shift down}`)
}