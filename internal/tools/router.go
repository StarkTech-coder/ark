/*
Package tools provides intent classification, tokenization, and parallel execution pipelines.

This file implements input tokenization, dynamic intent parsing for crypto tickers,
weather queries, time synchronization, and Wikipedia topic extraction, subsequently
dispatching parallel goroutines to execute queries asynchronously.
*/
package tools

import (
	"regexp"
	"strings"
	"sync"
)

// IntentResult encapsulates parsed entities and feature flags extracted from a prompt.
type IntentResult struct {
	Cryptos   []string
	Cities    []string
	NeedsTime bool
	WikiTopic string
}

// cryptoMap maps supported cryptocurrency alias tokens to standardized ticker IDs.
var cryptoMap = map[string]string{
	"btc": "btc", "bitcoin": "btc",
	"eth": "eth", "ethereum": "eth",
	"sol": "sol", "solana": "sol",
}

// cityMap maps Turkish city names and suffix variations to canonical city names.
var cityMap = map[string]string{
	"istanbul": "Istanbul", "istanbula": "Istanbul", "istanbulda": "Istanbul", "istanbuldan": "Istanbul", "istanbulun": "Istanbul",
	"bursa": "Bursa", "bursaya": "Bursa", "bursada": "Bursa", "bursadan": "Bursa", "bursanin": "Bursa",
	"ankara": "Ankara", "ankaraya": "Ankara", "ankarada": "Ankara", "ankaradan": "Ankara", "ankaranin": "Ankara",
	"izmir": "Izmir", "izmire": "Izmir", "izmirde": "Izmir", "izmirden": "Izmir", "izmirin": "Izmir",
}

// Tokenize converts input text to lowercase, sanitizes punctuation marks while preserving
// Turkish extended characters, and returns a slice of space-delimited word tokens.
func Tokenize(text string) []string {
	clean := strings.ToLower(text)
	// Replace punctuation and special non-alphanumeric symbols with whitespace
	re := regexp.MustCompile(`[^\w\sğüşıöçĞÜŞİÖÇ]`)
	clean = re.ReplaceAllString(clean, " ")
	return strings.Fields(clean)
}

// ExtractIntents analyzes input tokens using exact token matching to extract cryptocurrency,
// location, time-check, and Wikipedia lookup intents without substring collision errors.
func ExtractIntents(input string) IntentResult {
	tokens := Tokenize(input)
	res := IntentResult{}

	cryptoSet := make(map[string]bool)
	citySet := make(map[string]bool)

	for _, t := range tokens {
		if coin, ok := cryptoMap[t]; ok {
			cryptoSet[coin] = true
		}
		if city, ok := cityMap[t]; ok {
			citySet[city] = true
		}
		if t == "time" || t == "date" || t == "clock" || t == "saat" || t == "tarih" {
			res.NeedsTime = true
		}
	}

	for coin := range cryptoSet {
		res.Cryptos = append(res.Cryptos, coin)
	}
	for city := range citySet {
		res.Cities = append(res.Cities, city)
	}

	// Default location fallback to "Bursa" if weather intent is present without explicit city
	lowerInput := strings.ToLower(input)
	if (strings.Contains(lowerInput, "weather") || strings.Contains(lowerInput, "hava")) && len(res.Cities) == 0 {
		res.Cities = append(res.Cities, "Bursa")
	}

	// Wikipedia topic extraction trigger check
	if strings.Contains(lowerInput, "what is") || strings.Contains(lowerInput, "who is") ||
		strings.Contains(lowerInput, "nedir") || strings.Contains(lowerInput, "kimdir") || strings.Contains(lowerInput, "hakkında") {
		words := strings.Fields(lowerInput)
		if len(words) > 0 {
			res.WikiTopic = words[0]
		}
	}

	return res
}

// ExecuteAllIntentsParallel executes all extracted tool queries concurrently using Go goroutines
// protected by sync.WaitGroup and sync.Mutex, aggregating results into a formatted multiline response.
func ExecuteAllIntentsParallel(input string) string {
	intents := ExtractIntents(input)
	var wg sync.WaitGroup
	var mu sync.Mutex
	var results []string

	// 1. Concurrent Cryptocurrency Price Queries
	for _, coin := range intents.Cryptos {
		wg.Add(1)
		go func(c string) {
			defer wg.Done()
			data, err := FetchCryptoPrice(c)
			if err == nil {
				mu.Lock()
				results = append(results, data)
				mu.Unlock()
			}
		}(coin)
	}

	// 2. Concurrent Weather Forecast Queries
	for _, city := range intents.Cities {
		wg.Add(1)
		go func(c string) {
			defer wg.Done()
			data, err := FetchWeather(c)
			if err == nil {
				mu.Lock()
				results = append(results, data)
				mu.Unlock()
			}
		}(city)
	}

	// 3. World Time Synchronization Query
	if intents.NeedsTime {
		wg.Add(1)
		go func() {
			defer wg.Done()
			data, err := FetchWorldTime()
			if err == nil {
				mu.Lock()
				results = append(results, data)
				mu.Unlock()
			}
		}()
	}

	// 4. Concurrent Wikipedia Article Summary Lookup
	if intents.WikiTopic != "" {
		wg.Add(1)
		go func(topic string) {
			defer wg.Done()
			data, err := FetchWikipediaSummary(topic)
			if err == nil {
				mu.Lock()
				results = append(results, data)
				mu.Unlock()
			}
		}(intents.WikiTopic)
	}

	wg.Wait()
	return strings.Join(results, "\n\n----------------------------------------\n\n")
}
