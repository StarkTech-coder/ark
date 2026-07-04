package main

import (
	"ark/internal/dispatcher"
	"os"
)

func main() {
	if len(os.Args) < 2 {
		return
	}
	dispatcher.Route(os.Args[1])
}