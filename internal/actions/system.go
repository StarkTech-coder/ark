/*
Package actions provides low-level macOS system control utilities for the ARK system.

This package wraps macOS-specific capabilities including AppleScript invocation,
Space/Desktop switching via simulated keystrokes, audio asset playback using afplay,
and home-relative path resolution.
*/
package actions

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

// GetRootDir dynamically resolves the absolute path to the user's ARK project root directory (~/Desktop/ark).
// Returns "." if the user's home directory cannot be retrieved.
func GetRootDir() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return "."
	}
	return filepath.Join(home, "Desktop", "ark")
}

// RunCommand executes a raw AppleScript snippet using the macOS osascript binary.
func RunCommand(script string) {
	fmt.Println("Executing script:", script)
	cmd := exec.Command("osascript", "-e", script)
	if err := cmd.Run(); err != nil {
		fmt.Printf("Action failed: %v\n", err)
	} 
}

// RunTerminalCommand executes a native binary or shell command synchronously.
func RunTerminalCommand(command string, args ...string) {
	cmd := exec.Command(command, args...)
	if err := cmd.Run(); err != nil {
		fmt.Printf("Terminal command failed: %v\n", err)
	}
}

// PlaySystemSound plays a target WAV/MP3 audio asset synchronously using the macOS native afplay utility.
func PlaySystemSound(soundName string) {
	assetPath := filepath.Join(GetRootDir(), "assets", soundName)
	cmd := exec.Command("/usr/bin/afplay", assetPath)
	if err := cmd.Run(); err != nil {
		fmt.Printf("Audio playback failed (%s): %v\n", soundName, err)
	}
}

// RunAppleScript launches or brings a target macOS application to the foreground by name.
func RunAppleScript(appName string) {
	script := fmt.Sprintf(`tell application "%s" to activate`, appName)
	RunCommand(script)
}

// SwitchSpaceRight simulates Ctrl + Right Arrow (Key code 124) to navigate to the adjacent right macOS Space.
func SwitchSpaceRight() {
	// Key code 124 = Right Arrow
	script := `tell application "System Events" to key code 124 using {control down}`
	RunCommand(script)
	RunCommand(`delay 0.6`) // Buffer delay to accommodate macOS Space transition animations
}

// SwitchSpaceLeft simulates Ctrl + Left Arrow (Key code 123) to navigate to the adjacent left macOS Space.
func SwitchSpaceLeft() {
	// Key code 123 = Left Arrow
	script := `tell application "System Events" to key code 123 using {control down}`
	RunCommand(script)
	RunCommand(`delay 0.6`)
}

// GoToFirstSpace forces the macOS workspace focus back to Space 1 by executing sequential left switches.
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