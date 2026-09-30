package modes

import "ark/internal/actions"

// RunResearchMode activates Safari and provides audio confirmation.
func RunResearchMode() {
	actions.RunCommand(`tell application "Safari" to activate`)
	actions.PlaySystemSound("ark_research.wav")
}
