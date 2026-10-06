package tools

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"time"
)

var httpClient = &http.Client{Timeout: 5 * time.Second}

// FetchCryptoPrice Binance Public API üzerinden anlık USDT fiyatını çeker
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
		return "", fmt.Errorf("kripto verisi çekilemedi (HTTP Status: %d)", resp.StatusCode)
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

	return fmt.Sprintf("[CANLI KRİPTO VERİSİ (Binance)]\n- Sembol: %s\n- Fiyat: $%.2f USD",
		data.Symbol, price), nil
}

// FetchWeather Dinamik şehir parametresi alır; boş ise varsayılan olarak "Bursa" kullanır.
func FetchWeather(city ...string) (string, error) {
	targetCity := "Bursa"
	if len(city) > 0 && city[0] != "" {
		targetCity = city[0]
	}

	// 1. Şehrin Enlem / Boylam koordinatlarını Open-Meteo Geocoding ile al
	geoURL := fmt.Sprintf("https://geocoding-api.open-meteo.com/v1/search?name=%s&count=1&language=tr&format=json", url.QueryEscape(targetCity))
	gReq, err := http.NewRequest("GET", geoURL, nil)
	if err != nil {
		return "", err
	}
	gReq.Header.Set("User-Agent", "ARK-HUD-LocalAgent/1.0")

	gResp, err := httpClient.Do(gReq)
	if err != nil {
		return "", fmt.Errorf("konum koordinatı alınamadı: %v", err)
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
		return "", fmt.Errorf("şehir koordinatları bulunamadı: %s", targetCity)
	}

	lat := geoData.Results[0].Latitude
	lon := geoData.Results[0].Longitude
	resolvedCity := geoData.Results[0].Name

	// 2. Open-Meteo üzerinden hava durumunu çek
	weatherURL := fmt.Sprintf("https://api.open-meteo.com/v1/forecast?latitude=%f&longitude=%f&current_weather=true", lat, lon)
	wReq, err := http.NewRequest("GET", weatherURL, nil)
	if err != nil {
		return "", err
	}
	wReq.Header.Set("User-Agent", "ARK-HUD-LocalAgent/1.0")

	wResp, err := httpClient.Do(wReq)
	if err != nil {
		return "", fmt.Errorf("hava durumu alınamadı: %v", err)
	}
	defer func() { _ = wResp.Body.Close() }()

	var wData struct {
		CurrentWeather struct {
			Temperature float64 `json:"temperature"`
			Windspeed   float64 `json:"windspeed"`
		} `json:"current_weather"`
	}
	if err := json.NewDecoder(wResp.Body).Decode(&wData); err != nil {
		return "", fmt.Errorf("hava verisi okunamadı: %v", err)
	}

	return fmt.Sprintf("[CANLI HAVA DURUMU]\n- Konum/Şehir: %s\n- Sıcaklık: %.1f°C\n- Rüzgar Hızı: %.1f km/h",
		resolvedCity, wData.CurrentWeather.Temperature, wData.CurrentWeather.Windspeed), nil
}

// FetchWorldTime Sunucudan bağımsız olarak kesin zaman bilgisini alır
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

	return fmt.Sprintf("[CANLI SİSTEM SAATİ]\n- Zaman Dilimi: %s\n- Tarih: %s\n- Saat: %s", tData.TimeZone, tData.Date, tData.Time), nil
}

// FetchWikipediaSummary Türkçe Wikipedia üzerinden aranan başlığın resmi tanım özetini getirir
func FetchWikipediaSummary(query string) (string, error) {
	escapedQuery := url.PathEscape(query)
	wikiURL := fmt.Sprintf("https://tr.wikipedia.org/api/rest_v1/page/summary/%s", escapedQuery)

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
		return "", fmt.Errorf("wikipedia maddesi bulunamadı")
	}

	var wData struct {
		Title   string `json:"title"`
		Extract string `json:"extract"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&wData); err != nil {
		return "", err
	}

	return fmt.Sprintf("[WIKIPEDIA TR - %s]\n%s", wData.Title, wData.Extract), nil
}