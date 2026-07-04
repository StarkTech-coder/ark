package actions

import (
	"fmt"
	"os/exec"
)

// RunCommand AppleScript için
func RunCommand(script string) {
	fmt.Println("Executing script:", script)
	cmd := exec.Command("osascript", "-e", script)
	err := cmd.Run()
	if err != nil {
		fmt.Printf("Action failed: %v\n", err)
	}
}

// Yeni: Terminal komutları (afplay vb.) için
func RunTerminalCommand(command string, args ...string) {
	cmd := exec.Command(command, args...)
	err := cmd.Run()
	if err != nil {
		fmt.Printf("Terminal command failed: %v\n", err)
	}
}

func RunAppleScript(appName string) {
	script := fmt.Sprintf(`tell application "%s" to activate`, appName)
	RunCommand(script)
}
