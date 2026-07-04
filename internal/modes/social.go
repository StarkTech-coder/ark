package modes

import "ark/internal/actions"

const SOCIAL_SOUND = "/Users/tony/Desktop/ark/assets/ark_social.wav"

func RunSocialMode() {
    // 1. WhatsApp'ı Başlat
    actions.RunCommand(`tell application "WhatsApp" to activate`)
    
    // 2. ARK Sesli Geri Bildirim
    actions.RunTerminalCommand("afplay", SOCIAL_SOUND)
}