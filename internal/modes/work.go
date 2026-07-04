package modes

import "ark/internal/actions"

func RunWorkMode() {
	// 0. ÖNCELİK: Odak Modu (DND Aç)
	// "Do Not Disturb" modunu aktif etmek için System Events kullanıyoruz
	actions.RunCommand(`tell application "System Events" to tell control center to set focus mode to true`)

	// 1. Spotify
	actions.RunCommand(`tell application "Spotify" to activate`)
	actions.RunCommand(`delay 0.5`)
	actions.RunCommand(`tell application "Spotify" to play track "spotify:playlist:1CD9FdYqz6fNRVbw45vLNy"`)

	// 2. VS Code
	actions.RunCommand(`delay 0.5`)
	actions.RunCommand(`tell application "Visual Studio Code" to activate`)

	// 3. Chrome ve Gmail
	actions.RunCommand(`delay 0.5`)
	actions.RunCommand(`tell application "Google Chrome" to activate`)
	OpenGmailAndRestore()

	// 4. Notes
	actions.RunCommand(`delay 0.5`)
	actions.RunCommand(`tell application "Notes" to activate`)
}

func OpenGmailAndRestore() {
	actions.RunCommand(`tell application "Google Chrome" to open location "https://mail.google.com"`)
	actions.RunCommand(`delay 1.5`)
	actions.RunCommand(`tell application "System Events" to keystroke "t" using {command down, shift down}`)
}
