/*
ARK Assistant - Main CLI Router & Execution Entrypoint (ark_bin).

This package acts as the central traffic controller for the ARK backend system.
It receives command-line arguments (os.Args) dispatched from external interfaces
(such as Python's listen.py or chat_ui.py) and routes them to the appropriate
subsystems, including Web Scraping, Parallel Intent Pipelines, Direct API Services,
or standard macOS Workspace Modes via the dispatcher.
*/
package main

import (
	"ark/internal/dispatcher"
	"ark/internal/tools"
	"fmt"
	"os"
	"strings"
)

func main() {
	// Security Gate: Terminate execution immediately if no arguments are provided.
	if len(os.Args) < 2 {
		return
	}

	// 1. WEB SCRAPING MODE: Triggered when Python/chat_ui.py sends the 'web' parameter.
	if os.Args[1] == "web" {
		if len(os.Args) < 3 {
			fmt.Println("[ERROR: Target URL or search address was not provided]")
			return
		}
		targetURL := os.Args[2]
		cleanText, err := tools.FetchWebPage(targetURL)
		if err != nil {
			fmt.Printf("[ERROR: Web scraping failed: %v]\n", err)
			return
		}
		fmt.Println(cleanText)
		return
	}

	// 2. PIPELINE MODE: Automated multi-intent parallel execution trigger.
	if os.Args[1] == "pipeline" {
		if len(os.Args) < 3 {
			fmt.Println("[ERROR: Prompt for pipeline execution was not provided]")
			return
		}
		prompt := strings.Join(os.Args[2:], " ")
		result := tools.ExecuteAllIntentsParallel(prompt)
		fmt.Println(result)
		return
	}

	// 3. API MODE: Direct single-service API query dispatcher.
	if os.Args[1] == "api" {
		if len(os.Args) < 3 {
			fmt.Println("[ERROR: API service name was not specified]")
			return
		}
		service := os.Args[2]
		param := ""
		if len(os.Args) > 3 {
			param = os.Args[3]
		}

		switch service {
		case "crypto":
			res, err := tools.FetchCryptoPrice(param)
			if err != nil {
				fmt.Printf("[ERROR: %v]\n", err)
				return
			}
			fmt.Println(res)
		case "weather":
			res, err := tools.FetchWeather(param)
			if err != nil {
				fmt.Printf("[ERROR: %v]\n", err)
				return
			}
			fmt.Println(res)
		case "time":
			res, err := tools.FetchWorldTime()
			if err != nil {
				fmt.Printf("[ERROR: %v]\n", err)
				return
			}
			fmt.Println(res)
		case "wiki":
			res, err := tools.FetchWikipediaSummary(param)
			if err != nil {
				fmt.Printf("[ERROR: %v]\n", err)
				return
			}
			fmt.Println(res)
		default:
			fmt.Println("[ERROR: Unknown or unsupported API service]")
		}
		return
	}

	// 4. STANDARD MODES: Route standard system mode IDs (01, 02, 03, 04) to the dispatcher.
	dispatcher.Route(os.Args[1])
}