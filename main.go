package main

import (
	"ark/internal/dispatcher"
	"os"
)

// main is the CLI entrypoint for ARK executable dispatching.
func main() {
	if len(os.Args) < 2 {
		return
	}
	dispatcher.Route(os.Args[1])
}