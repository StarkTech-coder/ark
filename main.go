package main

import (
	"ark/internal/dispatcher"
	"ark/internal/tools"
	"fmt"
	"os"
	"strings"
)

func main() {
	if len(os.Args) < 2 {
		return
	}

	// 1. WEB SCRAPING MODU: Python/chat_ui.py 'web' parametresi gönderdiğinde çalışır!
	if os.Args[1] == "web" {
		if len(os.Args) < 3 {
			fmt.Println("[HATA: Kazınacak URL veya arama adresi belirtilmedi]")
			return
		}
		targetURL := os.Args[2]
		cleanText, err := tools.FetchWebPage(targetURL)
		if err != nil {
			fmt.Printf("[HATA: Web kazıma başarısız: %v]\n", err)
			return
		}
		fmt.Println(cleanText)
		return
	}

	// 2. PIPELINE MODU: Otomatik niyet/akış tetikleyici
	if os.Args[1] == "pipeline" {
		if len(os.Args) < 3 {
			fmt.Println("[HATA: Pipeline için prompt belirtilmedi]")
			return
		}
		prompt := strings.Join(os.Args[2:], " ")
		result := tools.ExecuteAllIntentsParallel(prompt)
		fmt.Println(result)
		return
	}

	// 3. API MODU: Tekil doğrudan API çağrıları
	if os.Args[1] == "api" {
		if len(os.Args) < 3 {
			fmt.Println("[HATA: API servisi belirtilmedi]")
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
				fmt.Printf("[HATA: %v]\n", err)
				return
			}
			fmt.Println(res)
		case "weather":
			res, err := tools.FetchWeather(param)
			if err != nil {
				fmt.Printf("[HATA: %v]\n", err)
				return
			}
			fmt.Println(res)
		case "time":
			res, err := tools.FetchWorldTime()
			if err != nil {
				fmt.Printf("[HATA: %v]\n", err)
				return
			}
			fmt.Println(res)
		case "wiki":
			res, err := tools.FetchWikipediaSummary(param)
			if err != nil {
				fmt.Printf("[HATA: %v]\n", err)
				return
			}
			fmt.Println(res)
		default:
			fmt.Println("[HATA: Bilinmeyen API servisi]")
		}
		return
	}

	// 4. Diğer Modlar (01, 02, 03, 04)
	dispatcher.Route(os.Args[1])
}
