package modes

import (
	"ark/internal/actions"
)

// RunWorkMode initializes the primary development environment across three macOS Spaces.
// It uses fixed, deterministic delays to avoid infinite polling loops and CPU spikes.
func RunWorkMode() {
	// 1. Reset focus to the primary workspace (Space 1)
	actions.GoToFirstSpace()

	// --- SPACE 1: Media & Web Browsing ---
	// Activate Spotify and initiate playback immediately
	actions.RunCommand(`tell application "Spotify" to activate`)
	actions.RunCommand(`delay 0.5`)
	actions.RunCommand(`tell application "Spotify" to play track "spotify:playlist:1CD9FdYqz6fNRVbw45vLNy"`)

	// Launch Chrome and open Gmail directly (Chrome will open restored tabs automatically via browser settings)
	actions.RunCommand(`delay 0.5`)
	actions.RunCommand(`tell application "Google Chrome" to activate`)
	actions.RunCommand(`tell application "Google Chrome" to open location "https://mail.google.com"`)

	// Buffer delay for Space 1 operations
	actions.RunCommand(`delay 0.8`)

	// --- SPACE 2: Research Environment ---
	// Transition to Space 2
	actions.SwitchSpaceRight()

	// Launch and force Safari to frontmost focus safely
	actions.RunCommand(`
		tell application "Safari"
			activate
			reopen
		end tell
	`)
	// Deterministic delay for Safari UI to render on Space 2
	actions.RunCommand(`delay 1.0`)

	// --- SPACE 3: Core IDE & Documentation ---
	// Transition to Space 3 and initialize development workspace
	actions.SwitchSpaceRight()
	actions.RunCommand(`tell application "Visual Studio Code" to activate`)
	actions.RunCommand(`delay 0.6`)
	actions.RunCommand(`tell application "Notes" to activate`)

	// Final audio feedback signaling completion
	actions.PlaySystemSound("ark_finish.wav")
}
