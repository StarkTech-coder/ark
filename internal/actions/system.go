package actions

import (
	"fmt"
	"os/exec"
)

// RunAppleScript, sadece uygulama açmakla kalmaz, komut da gönderir
func RunCommand(script string) {
	fmt.Println("Executing script:", script)
	cmd := exec.Command("osascript", "-e", script)
	err := cmd.Run()
	if err != nil {
		fmt.Printf("Action failed: %v\n", err)
	}
}

// Orijinal fonksiyonu bozmamak için bu ismi koruyalım
func RunAppleScript(appName string) {
	script := fmt.Sprintf(`tell application "%s" to activate`, appName)
	RunCommand(script)
}