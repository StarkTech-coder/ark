package modes

import "ark/internal/actions"

const SOCIAL_SOUND = "/Users/tony/Desktop/ark/assets/ark_social.wav"

func RunSocialMode() {
	// 1. WhatsApp'ı Başlat
	actions.RunCommand(`tell application "WhatsApp" to activate`)

	// 2. Instagram'ı Başlat (Chrome Apps içerisindeki ismiyle)
	actions.RunCommand(`delay 0.5`)
	actions.RunCommand(`tell application "Instagram" to activate`)

	// 3. ARK Sesli Geri Bildirim
	actions.RunTerminalCommand("afplay", SOCIAL_SOUND)
}
