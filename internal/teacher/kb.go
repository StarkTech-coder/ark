package teacher

import (
	"os"
	"path/filepath"
)

const KBPath = "ground-communication-kb"

// ScanKB scans the knowledge base and returns all PDF paths.
func ScanKB() ([]string, error) {
	var pdfs []string

	err := filepath.Walk(KBPath, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}

		if info.IsDir() {
			return nil
		}

		if filepath.Ext(path) == ".pdf" {
			pdfs = append(pdfs, path)
		}

		return nil
	})

	if err != nil {
		return nil, err
	}

	return pdfs, nil
}