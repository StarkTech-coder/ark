package modes

import "ark/internal/actions"

// RunSocialMode launches communication tools (WhatsApp, Instagram) with audio feedback.
func RunSocialMode() {
	actions.RunCommand(`tell application "WhatsApp" to activate`)
	actions.RunCommand(`delay 0.5`)
	actions.RunCommand(`tell application "Instagram" to activate`)
	actions.PlaySystemSound("ark_social.wav")
}
