package dispatcher

import "ark/internal/modes"

func Route(command string) {
	switch command {
	case "01":
		modes.RunWorkMode()
	case "02":
		modes.RunResearchMode()
	case "03":
		modes.RunSocialMode()
	}
}
