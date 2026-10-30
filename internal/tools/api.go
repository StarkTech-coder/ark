/*
Package tools provides external API clients and web parsing utilities for the ARK system.

This package handles real-time data fetching including cryptocurrency tickers,
geocoded weather forecasts, world time synchronization, and Wikipedia summaries
using standard Go HTTP clients with robust error handling and strict timeouts.
*/
package tools

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"time"
)

// httpClient defines a shared HTTP client with a strict 5-second timeout boundary.
var httpClient = &http.Client{Timeout: 5 * time.Second}

// FetchCryptoPrice queries the public Binance API to retrieve the current USDT trading price for supported coins.
func FetchCryptoPrice(coinID string) (string, error) {
	symbol := "BTCUSDT"
	switch coinID {
	case "eth":
		symbol = "ETHUSDT"
	case "sol":
		symbol = "SOLUSDT"
	}

	apiURL := fmt.Sprintf("https://api.binance.com/api/v3/ticker/price?symbol=%s", symbol)

	req, err := http.NewRequest("GET", apiURL, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("User-Agent", "ARK-HUD-LocalAgent/1.0")

	resp, err := httpClient.Do(req)
	if err != nil {
		return "", err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("failed to fetch crypto price (HTTP Status: %d)", resp.StatusCode)
	}

	var data struct {
		Symbol string `json:"symbol"`
		Price  string `json:"price"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return "", err
	}

	var price float64
	_, _ = fmt.Sscanf(data.Price, "%f", &price)

	return fmt.Sprintf("[LIVE CRYPTO DATA (Binance)]\nSymbol: %s\nPrice: $%.2f USD", data.Symbol, price), nil
}

// FetchWeather fetches current weather metrics for a specified city using Open-Meteo Geocoding and Forecast APIs.
// Defaults to "Bursa" if no city parameter is provided.
func FetchWeather(city ...string) (string, error) {
	targetCity := "Bursa"
	if len(city) > 0 && city[0] != "" {
		targetCity = city[0]
	}

	// 1. Resolve latitude and longitude coordinates using Open-Meteo Geocoding API
	geoURL := fmt.Sprintf("https://geocoding-api.open-meteo.com/v1/search?name=%s&count=1&language=en&format=json", url.QueryEscape(targetCity))
	gReq, err := http.NewRequest("GET", geoURL, nil)
	if err != nil {
		return "", err
	}
	gReq.Header.Set("User-Agent", "ARK-HUD-LocalAgent/1.0")

	gResp, err := httpClient.Do(gReq)
	if err != nil {
		return "", fmt.Errorf("failed to retrieve location coordinates: %v", err)
	}
	defer func() { _ = gResp.Body.Close() }()

	var geoData struct {
		Results []struct {
			Name      string  `json:"name"`
			Latitude  float64 `json:"latitude"`
			Longitude float64 `json:"longitude"`
		} `json:"results"`
	}
	if err := json.NewDecoder(gResp.Body).Decode(&geoData); err != nil || len(geoData.Results) == 0 {
		return "", fmt.Errorf("city coordinates not found: %s", targetCity)
	}

	lat := geoData.Results[0].Latitude
	lon := geoData.Results[0].Longitude
	resolvedCity := geoData.Results[0].Name

	// 2. Fetch current weather forecast metrics using resolved coordinates
	weatherURL := fmt.Sprintf("https://api.open-meteo.com/v1/forecast?latitude=%f&longitude=%f&current_weather=true", lat, lon)
	wReq, err := http.NewRequest("GET", weatherURL, nil)
	if err != nil {
		return "", err
	}
	wReq.Header.Set("User-Agent", "ARK-HUD-LocalAgent/1.0")

	wResp, err := httpClient.Do(wReq)
	if err != nil {
		return "", fmt.Errorf("failed to retrieve weather metrics: %v", err)
	}
	defer func() { _ = wResp.Body.Close() }()

	var wData struct {
		CurrentWeather struct {
			Temperature float64 `json:"temperature"`
			Windspeed   float64 `json:"windspeed"`
		} `json:"current_weather"`
	}
	if err := json.NewDecoder(wResp.Body).Decode(&wData); err != nil {
		return "", fmt.Errorf("failed to parse weather payload: %v", err)
	}

	return fmt.Sprintf("[LIVE WEATHER DATA]\nLocation: %s\nTemperature: %.1f°C\nWind Speed: %.1f km/h", resolvedCity, wData.CurrentWeather.Temperature, wData.CurrentWeather.Windspeed), nil
}

// FetchWorldTime retrieves precise time and date information independently of local system clock settings.
func FetchWorldTime() (string, error) {
	apiURL := "https://timeapi.io/api/time/current/zone?timeZone=Europe/Istanbul"

	req, err := http.NewRequest("GET", apiURL, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("User-Agent", "ARK-HUD-LocalAgent/1.0")

	resp, err := httpClient.Do(req)
	if err != nil {
		return "", err
	}
	defer func() { _ = resp.Body.Close() }()

	var tData struct {
		Date     string `json:"date"`
		Time     string `json:"time"`
		TimeZone string `json:"timeZone"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&tData); err != nil {
		return "", err
	}

	return fmt.Sprintf("[LIVE SYSTEM TIME]\nTimezone: %s\nDate: %s\nTime: %s", tData.TimeZone, tData.Date, tData.Time), nil
}

// FetchWikipediaSummary queries the Wikipedia REST API to retrieve an official summary definition for a given topic query.
func FetchWikipediaSummary(query string) (string, error) {
	escapedQuery := url.PathEscape(query)
	wikiURL := fmt.Sprintf("https://en.wikipedia.org/api/rest_v1/page/summary/%s", escapedQuery)

	req, err := http.NewRequest("GET", wikiURL, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("User-Agent", "ARK-HUD-LocalAgent/1.0")

	resp, err := httpClient.Do(req)
	if err != nil {
		return "", err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("wikipedia article not found")
	}

	var wData struct {
		Title   string `json:"title"`
		Extract string `json:"extract"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&wData); err != nil {
		return "", err
	}

	return fmt.Sprintf("[WIKIPEDIA SUMMARY - %s]\n%s", wData.Title, wData.Extract), nil
}
