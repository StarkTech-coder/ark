/*
Package dispatcher provides command routing logic for the ARK backend system.

It receives standard system mode identifiers (e.g., "01", "02", "03", "04")
and delegates execution to the corresponding mode handlers in the modes package.
*/
package dispatcher

import (
	"ark/internal/modes"
	"fmt"
)

// Route dispatches command IDs to their corresponding mode handlers.
// If an unknown command ID is passed, it logs a warning message to standard output.
func Route(command string) {
	switch command {
	case "01":
		// Trigger Work / Productivity Workspace Mode
		modes.RunWorkMode()
	case "02":
		// Trigger Research & Analysis Workspace Mode
		modes.RunResearchMode()
	case "03":
		// Trigger Social & Communication Mode
		modes.RunSocialMode()
	case "04":
		// Trigger HUD (Heads-Up Display) Mode - Displays real-time system metrics (CPU cores, RAM, and temperature) in the terminal
		modes.RunHUDMode()
	default:
		// Fallback guard for unrecognized command identifiers
		fmt.Printf("[ARK WARN] Unknown command ID received in Go router: '%s'\n", command)
	}
}
