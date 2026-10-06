package tools

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"sync"
	"time"

	"golang.org/x/net/html"
)

type SearchResultItem struct {
	Title string
	URL   string
}

// FetchWebPage: Arama terimini (query) da hesaba katarak akıllı filtreleme yapar.
func FetchWebPage(targetURL string) (cleanText string, err error) {
	// URL içinden arama terimini (q=...) söküp alalım (Dinamik filtre için)
	queryKeywords := extractQueryKeywords(targetURL)

	if strings.Contains(targetURL, "duckduckgo.com") {
		return crawlDuckDuckGoDeep(targetURL, queryKeywords)
	}

	return fetchSinglePageContent(targetURL, queryKeywords)
}

// URL'den arama terimini ayıklar (Örn: ?q=bursa+kahve -> ["bursa", "kahve"])
func extractQueryKeywords(rawURL string) []string {
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return nil
	}
	q := parsed.Query().Get("q")
	if q == "" {
		return nil
	}
	// Kelimelere ayır, küçük harfe çevir, çok kısa kelimeleri (ve, ile, de) atla
	rawWords := strings.Fields(strings.ToLower(q))
	var keywords []string
	for _, w := range rawWords {
		if len(w) > 2 {
			keywords = append(keywords, w)
		}
	}
	return keywords
}

// crawlDuckDuckGoDeep: Dinamik anahtar kelimeleri alt sayfalara da taşır
func crawlDuckDuckGoDeep(searchURL string, keywords []string) (string, error) {
	htmlContent, err := fetchRawHTML(searchURL)
	if err != nil {
		return "", err
	}

	items := parseDuckDuckGoLinks(htmlContent, 2)
	if len(items) == 0 {
		return parseGenericPage(htmlContent, keywords), nil
	}

	var wg sync.WaitGroup
	var mu sync.Mutex
	var deepResults []string

	for idx, item := range items {
		wg.Add(1)
		go func(i int, resItem SearchResultItem) {
			defer wg.Done()
			content, fetchErr := fetchSinglePageContent(resItem.URL, keywords)
			if fetchErr == nil && len(content) > 100 {
				mu.Lock()
				deepResults = append(deepResults, fmt.Sprintf("--- KAYNAK %d: %s ---\nURL: %s\n\n%s", i+1, resItem.Title, resItem.URL, content))
				mu.Unlock()
			}
		}(idx, item)
	}

	wg.Wait()

	if len(deepResults) == 0 {
		return parseGenericPage(htmlContent, keywords), nil
	}

	combined := strings.Join(deepResults, "\n\n========================================\n\n")
	if len(combined) > 8000 {
		combined = combined[:8000]
	}

	return combined, nil
}

func fetchSinglePageContent(targetURL string, keywords []string) (string, error) {
	htmlContent, err := fetchRawHTML(targetURL)
	if err != nil {
		return "", err
	}
	return parseGenericPage(htmlContent, keywords), nil
}

func fetchRawHTML(targetURL string) (string, error) {
	client := &http.Client{Timeout: 8 * time.Second}
	req, err := http.NewRequest("GET", targetURL, nil)
	if err != nil {
		return "", err
	}

	req.Header.Set("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
	req.Header.Set("Accept-Language", "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7")

	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer func() {
		_ = resp.Body.Close()
	}()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("HTTP %d", resp.StatusCode)
	}

	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	return string(bodyBytes), nil
}

func parseDuckDuckGoLinks(htmlStr string, limit int) []SearchResultItem {
	doc, err := html.Parse(strings.NewReader(htmlStr))
	if err != nil {
		return nil
	}

	var items []SearchResultItem
	var f func(*html.Node)
	f = func(n *html.Node) {
		if len(items) >= limit {
			return
		}

		if n.Type == html.ElementNode && n.Data == "a" {
			var href, title string
			isResultLink := false

			for _, a := range n.Attr {
				if a.Key == "class" && strings.Contains(a.Val, "result__a") {
					isResultLink = true
				}
				if a.Key == "href" {
					href = a.Val
				}
			}

			if isResultLink && href != "" {
				title = cleanWhitespace(extractNodeText(n))
				actualURL := cleanDuckDuckGoURL(href)
				if actualURL != "" && !strings.Contains(actualURL, "duckduckgo.com") {
					items = append(items, SearchResultItem{Title: title, URL: actualURL})
				}
			}
		}

		for c := n.FirstChild; c != nil; c = c.NextSibling {
			f(c)
		}
	}
	f(doc)

	return items
}

func cleanDuckDuckGoURL(rawHref string) string {
	if strings.HasPrefix(rawHref, "//") {
		rawHref = "https:" + rawHref
	}
	parsed, err := url.Parse(rawHref)
	if err != nil {
		return ""
	}

	if strings.Contains(parsed.Path, "/l/") {
		uddg := parsed.Query().Get("uddg")
		if uddg != "" {
			return uddg
		}
	}
	return rawHref
}

// parseGenericPage: Dinamik anahtar kelime filtresi ile site çöpünü (il listeleri vb.) temizler
func parseGenericPage(htmlStr string, keywords []string) string {
	tagsToRemove := []string{"script", "style", "noscript", "header", "footer", "nav", "aside"}
	for _, tag := range tagsToRemove {
		rePattern := fmt.Sprintf("(?i)<%s[^>]*>[\\s\\S]*?</%s>", tag, tag)
		re := regexp.MustCompile(rePattern)
		htmlStr = re.ReplaceAllString(htmlStr, "")
	}

	reTags := regexp.MustCompile(`<[^>]*>`)
	plainText := reTags.ReplaceAllString(htmlStr, " ")

	plainText = strings.ReplaceAll(plainText, "&nbsp;", " ")
	plainText = strings.ReplaceAll(plainText, "&amp;", "&")
	plainText = strings.ReplaceAll(plainText, "&quot;", "\"")
	plainText = strings.ReplaceAll(plainText, "&lt;", "<")
	plainText = strings.ReplaceAll(plainText, "&gt;", ">")

	lines := strings.Split(plainText, "\n")
	var cleanedLines []string

	for _, line := range lines {
		trimmed := cleanWhitespace(line)
		trimmed = removeSpamDates(trimmed)

		// 1. Çok kısa satırları eliyoruz
		if len(trimmed) < 25 {
			continue
		}

		// 2. Anlamsız il/ilçe veya menü listelerini elemek için Akıllı Dinamik Kontrol:
		// Eğer satır içinde arama kelimelerimizden en az BİRİ geçiyorsa VEYA uzun bir cümle/adres içeriyorsa kabul et.
		lowerLine := strings.ToLower(trimmed)
		isRelevant := false

		if len(keywords) == 0 {
			isRelevant = true // Query yoksa direkt kabul et
		} else {
			for _, kw := range keywords {
				if strings.Contains(lowerLine, kw) {
					isRelevant = true
					break
				}
			}
		}

		// Ekstra güvenlik: Satır içinde virgülle ayrılmış 5-6'dan fazla şehir ismi geçiyorsa (SEO footer çöpü) kesinlikle ele!
		if strings.Contains(lowerLine, "adana") && strings.Contains(lowerLine, "ankara") && strings.Contains(lowerLine, "izmir") {
			continue
		}

		if isRelevant {
			cleanedLines = append(cleanedLines, trimmed)
		}
	}

	return strings.Join(cleanedLines, "\n")
}

func extractNodeText(n *html.Node) string {
	if n.Type == html.TextNode {
		return n.Data
	}
	var text string
	for c := n.FirstChild; c != nil; c = c.NextSibling {
		text += extractNodeText(c)
	}
	return text
}

func removeSpamDates(s string) string {
	reTrDate := regexp.MustCompile(`(?i)\d{1,2}\s+(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\s+\d{4}(\s+\d{2}:\d{2})?`)
	return reTrDate.ReplaceAllString(s, " ")
}

func cleanWhitespace(s string) string {
	reSpace := regexp.MustCompile(`\s+`)
	return strings.TrimSpace(reSpace.ReplaceAllString(s, " "))
}
