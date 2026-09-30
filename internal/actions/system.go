package actions

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

// GetRootDir dynamically resolves the user's home-relative project directory.
func GetRootDir() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return "."
	}
	return filepath.Join(home, "Desktop", "ark")
}

// RunCommand executes an AppleScript snippet via osascript.
func RunCommand(script string) {
	fmt.Println("Executing script:", script)
	cmd := exec.Command("osascript", "-e", script)
	if err := cmd.Run(); err != nil {
		fmt.Printf("Action failed: %v\n", err)
	}
}

// RunTerminalCommand executes a native shell command synchronously.
func RunTerminalCommand(command string, args ...string) {
	cmd := exec.Command(command, args...)
	if err := cmd.Run(); err != nil {
		fmt.Printf("Terminal command failed: %v\n", err)
	}
}

// PlaySystemSound plays an audio asset synchronously using macOS afplay.
func PlaySystemSound(soundName string) {
	assetPath := filepath.Join(GetRootDir(), "assets", soundName)
	cmd := exec.Command("/usr/bin/afplay", assetPath)
	if err := cmd.Run(); err != nil {
		fmt.Printf("Audio playback failed (%s): %v\n", soundName, err)
	}
}

// RunAppleScript activates a target macOS application.
func RunAppleScript(appName string) {
	script := fmt.Sprintf(`tell application "%s" to activate`, appName)
	RunCommand(script)
}
