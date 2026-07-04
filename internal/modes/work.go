package modes

import "ark/internal/actions"

func RunWorkMode() {
	// 1. ÖNCELİK: Spotify
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

	// 4. Notes (Apple Notlar Uygulaması)
	actions.RunCommand(`delay 0.5`)
	actions.RunCommand(`tell application "Notes" to activate`)
	// Notlar uygulamasında otomatik yeni not oluşturmak bazen izin gerektirebilir,
	// sadece açılması için şu komut yeterlidir:
	actions.RunCommand(`tell application "Notes" to activate`)
}

func OpenGmailAndRestore() {
	actions.RunCommand(`tell application "Google Chrome" to open location "https://mail.google.com"`)
	actions.RunCommand(`delay 1.5`)
	actions.RunCommand(`tell application "System Events" to keystroke "t" using {command down, shift down}`)
}
