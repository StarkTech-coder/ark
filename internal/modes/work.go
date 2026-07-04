package modes

import "ark/internal/actions"

func RunWorkMode() {
	// 1. ÖNCELİK: Spotify
	actions.RunCommand(`tell application "Spotify" to activate`)
	actions.RunCommand(`delay 0.5`) // Spotify'ın uyanmasını bekle
	actions.RunCommand(`tell application "Spotify" to play track "spotify:playlist:1CD9FdYqz6fNRVbw45vLNy"`)

	// 2. VS Code
	actions.RunCommand(`delay 0.5`) // Geçiş için kısa bekleme
	actions.RunCommand(`tell application "Visual Studio Code" to activate`)

	// 3. Chrome ve Gmail
	actions.RunCommand(`delay 0.5`) // Geçiş için kısa bekleme
	actions.RunCommand(`tell application "Google Chrome" to activate`)
	OpenGmailAndRestore()
}

func OpenGmailAndRestore() {
	actions.RunCommand(`tell application "Google Chrome" to open location "https://mail.google.com"`)
	actions.RunCommand(`delay 1.5`) // Sayfanın yüklenmesi için bekle
	actions.RunCommand(`tell application "System Events" to keystroke "t" using {command down, shift down}`)
}
