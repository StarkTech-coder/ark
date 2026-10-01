package modes

import "ark/internal/actions"

// RunHUDMode plays audio feedback and launches terminal resource monitoring.
func RunHUDMode() {
	cmd := `tell application "Terminal" to do script "btop"`
	actions.RunCommand(cmd)
	actions.PlaySystemSound("ark_system.wav")
}
