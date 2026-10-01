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

// SwitchSpaceRight moves to the next macOS Space on the right.
func SwitchSpaceRight() {
	// Key code 124 = Right Arrow
	script := `tell application "System Events" to key code 124 using {control down}`
	RunCommand(script)
	RunCommand(`delay 0.6`) // Buffer delay for macOS Space transition animation
}

// SwitchSpaceLeft moves to the previous macOS Space on the left.
func SwitchSpaceLeft() {
	// Key code 123 = Left Arrow
	script := `tell application "System Events" to key code 123 using {control down}`
	RunCommand(script)
	RunCommand(`delay 0.6`)
}

// GoToFirstSpace returns to Space 1 safely by issuing left window switches and checks execution errors.
func GoToFirstSpace() {
	for i := 0; i < 3; i++ {
		script := `tell application "System Events" to key code 123 using {control down}`
		cmd := exec.Command("osascript", "-e", script)
		if err := cmd.Run(); err != nil {
			fmt.Printf("Space switch failed (Left): %v\n", err)
		}
	}
	RunCommand(`delay 0.5`)
}
