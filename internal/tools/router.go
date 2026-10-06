package tools

import (
	"regexp"
	"strings"
	"sync"
)

type IntentResult struct {
	Cryptos   []string
	Cities    []string
	NeedsTime bool
	WikiTopic string
}

var cryptoMap = map[string]string{
	"btc": "btc", "bitcoin": "btc",
	"eth": "eth", "ethereum": "eth",
	"sol": "sol", "solana": "sol",
}

var cityMap = map[string]string{
	"istanbul": "Istanbul", "istanbula": "Istanbul", "istanbulda": "Istanbul", "istanbuldan": "Istanbul", "istanbulun": "Istanbul",
	"bursa": "Bursa", "bursaya": "Bursa", "bursada": "Bursa", "bursadan": "Bursa", "bursanin": "Bursa",
	"ankara": "Ankara", "ankaraya": "Ankara", "ankarada": "Ankara", "ankaradan": "Ankara", "ankaranin": "Ankara",
	"izmir": "Izmir", "izmire": "Izmir", "izmirde": "Izmir", "izmirden": "Izmir", "izmirin": "Izmir",
}

// Tokenize: Türkçe karakterleri bozmadan noktalama işaretlerini temizler
func Tokenize(text string) []string {
	clean := strings.ToLower(text)
	// Kesme işaretlerini ve noktalamayı boşlukla değiştir
	re := regexp.MustCompile(`[^\w\sğüşıöçĞÜŞİÖÇ]`)
	clean = re.ReplaceAllString(clean, " ")
	return strings.Fields(clean)
}

// ExtractIntents: Exact Match ile kelimeleri tarar (Substring hatası yok)
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
		if t == "saat" || t == "saati" || t == "saatini" || t == "tarih" {
			res.NeedsTime = true
		}
	}

	for coin := range cryptoSet {
		res.Cryptos = append(res.Cryptos, coin)
	}
	for city := range citySet {
		res.Cities = append(res.Cities, city)
	}

	// Eğer hava kelimesi geçiyor ve şehir belirtilmediyse varsayılan Bursa
	if strings.Contains(strings.ToLower(input), "hava") && len(res.Cities) == 0 {
		res.Cities = append(res.Cities, "Bursa")
	}

	// Wikipedia Tespiti
	lower := strings.ToLower(input)
	if strings.Contains(lower, "nedir") || strings.Contains(lower, "kimdir") || strings.Contains(lower, "hakkında") {
		words := strings.Fields(lower)
		if len(words) > 0 {
			res.WikiTopic = words[0]
		}
	}

	return res
}

// ExecuteAllIntentsParallel: Tüm tool'ları eşzamanlı (Goroutine) çalıştırır
func ExecuteAllIntentsParallel(input string) string {
	intents := ExtractIntents(input)
	var wg sync.WaitGroup
	var mu sync.Mutex
	var results []string

	// 1. Kripto İstekleri (Paralel)
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

	// 2. Hava Durumu İstekleri (Paralel)
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

	// 3. Saat Bilgisi
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

	// 4. Wikipedia İsteği (Paralel)
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
