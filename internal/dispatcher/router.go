package dispatcher

import (
    "ark/internal/modes"
    "fmt"
)

// Route dispatches command IDs to their corresponding mode handlers.
func Route(command string) {
    switch command {
    case "01":
        modes.RunWorkMode()
    case "02":
        modes.RunResearchMode()
    case "03":
        modes.RunSocialMode()
    case "04":
        modes.RunHUDMode()
    default:
        fmt.Printf("[ARK WARN] Unknown command ID received in Go router: '%s'\n", command)
    }
}