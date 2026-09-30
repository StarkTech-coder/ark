package modes

import "ark/internal/actions"

// RunHUDMode plays audio feedback and launches terminal resource monitoring.
func RunHUDMode() {
	actions.PlaySystemSound("ark_system.wav")
	cmd := `tell application "Terminal" to do script "btop"`
	actions.RunCommand(cmd)
}