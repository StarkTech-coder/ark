/*
Package tools provides web crawling, HTML parsing, and intelligent content filtering.

This file implements robust web scraping capabilities, including DuckDuckGo deep search crawling,
parallel subpage fetching, HTML element sanitization, and keyword-based content filtering
to extract clean, relevant plain-text payloads for downstream LLM ingestion.
*/
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

// SearchResultItem represents an individual web search result containing its title and target URL.
type SearchResultItem struct {
	Title string
	URL   string
}

// FetchWebPage performs intelligent web content extraction and filtering using dynamic search query keywords.
func FetchWebPage(targetURL string) (cleanText string, err error) {
	// Extract search query keywords from the target URL parameters for dynamic filtering.
	queryKeywords := extractQueryKeywords(targetURL)

	if strings.Contains(targetURL, "duckduckgo.com") {
		return crawlDuckDuckGoDeep(targetURL, queryKeywords)
	}

	return fetchSinglePageContent(targetURL, queryKeywords)
}

// extractQueryKeywords extracts and sanitizes search terms from the URL query string (e.g., ?q=bursa+coffee -> ["bursa", "coffee"]).
func extractQueryKeywords(rawURL string) []string {
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return nil
	}
	q := parsed.Query().Get("q")
	if q == "" {
		return nil
	}
	// Split into words, convert to lowercase, and skip extremely short words.
	rawWords := strings.Fields(strings.ToLower(q))
	var keywords []string
	for _, w := range rawWords {
		if len(w) > 2 {
			keywords = append(keywords, w)
		}
	}
	return keywords
}

// crawlDuckDuckGoDeep crawls DuckDuckGo search results and concurrently propagates query keywords to top subpages.
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
				deepResults = append(deepResults, fmt.Sprintf("--- SOURCE %d: %s ---\nURL: %s\n\n%s", i+1, resItem.Title, resItem.URL, content))
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

// fetchSinglePageContent downloads and parses raw HTML content for a single target URL.
func fetchSinglePageContent(targetURL string, keywords []string) (string, error) {
	htmlContent, err := fetchRawHTML(targetURL)
	if err != nil {
		return "", err
	}
	return parseGenericPage(htmlContent, keywords), nil
}

// fetchRawHTML executes an HTTP GET request with a strict timeout and standard desktop User-Agent headers.
func fetchRawHTML(targetURL string) (string, error) {
	client := &http.Client{Timeout: 8 * time.Second}
	req, err := http.NewRequest("GET", targetURL, nil)
	if err != nil {
		return "", err
	}

	req.Header.Set("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
	req.Header.Set("Accept-Language", "en-US,en;q=0.9,tr-TR;q=0.8,tr;q=0.7")

	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer func() {
		_ = resp.Body.Close()
	}()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("HTTP error status code: %d", resp.StatusCode)
	}

	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	return string(bodyBytes), nil
}

// parseDuckDuckGoLinks parses HTML DOM nodes to extract clean search result links up to the specified limit.
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

// cleanDuckDuckGoURL unwraps and cleans redirected target URLs extracted from DuckDuckGo anchor tags.
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

// parseGenericPage strips clutter tags, decodes HTML entities, and filters lines dynamically using query keywords.
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

		// 1. Filter out extremely short lines.
		if len(trimmed) < 25 {
			continue
		}

		// 2. Smart dynamic check to filter out meaningless menu/footer lists:
		// Accept the line if it contains at least ONE of our search keywords OR contains a long sentence/address.
		lowerLine := strings.ToLower(trimmed)
		isRelevant := false

		if len(keywords) == 0 {
			isRelevant = true // Accept directly if no query is provided.
		} else {
			for _, kw := range keywords {
				if strings.Contains(lowerLine, kw) {
					isRelevant = true
					break
				}
			}
		}

		// Extra safety: Drop lines containing multiple common city names separated by commas (SEO footer clutter).
		if strings.Contains(lowerLine, "adana") && strings.Contains(lowerLine, "ankara") && strings.Contains(lowerLine, "izmir") {
			continue
		}

		if isRelevant {
			cleanedLines = append(cleanedLines, trimmed)
		}
	}

	return strings.Join(cleanedLines, "\n")
}

// extractNodeText recursively extracts plain text content from HTML DOM nodes.
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

// removeSpamDates strips generic date strings and timestamps commonly found in blog/news comment sections.
func removeSpamDates(s string) string {
	reTrDate := regexp.MustCompile(`(?i)\d{1,2}\s+(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\s+\d{4}(\s+\d{2}:\d{2})?`)
	return reTrDate.ReplaceAllString(s, " ")
}

// cleanWhitespace normalizes consecutive whitespace characters and trims outer padding.
func cleanWhitespace(s string) string {
	reSpace := regexp.MustCompile(`\s+`)
	return strings.TrimSpace(reSpace.ReplaceAllString(s, " "))
}
