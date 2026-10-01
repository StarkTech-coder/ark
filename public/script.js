document.addEventListener("DOMContentLoaded", () => {
    "use strict";

    let dragCounter = 0;
    let isSttActive = false;

    // ==========================================
    // 1. DRAG & DROP DOSYA SÜRÜKLEME EFEKTLERİ
    // ==========================================
    const isFileDrag = (event) => {
        const types = event.dataTransfer?.types || [];
        return Array.from(types).includes("Files");
    };

    const setChatDragState = (active) => {
        const composer =
            document.querySelector("form") ||
            document.querySelector('[class*="composer"]') ||
            document.querySelector('[class*="Composer"]');

        if (!composer) return;
        composer.classList.toggle("ark-file-drag-active", active);
    };

    document.addEventListener("dragenter", (event) => {
        if (!isFileDrag(event)) return;
        dragCounter++;
        setChatDragState(true);
    });

    document.addEventListener("dragover", (event) => {
        if (!isFileDrag(event)) return;
        event.preventDefault();
        if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
        setChatDragState(true);
    });

    document.addEventListener("dragleave", (event) => {
        if (!isFileDrag(event)) return;
        dragCounter--;
        if (dragCounter <= 0) {
            dragCounter = 0;
            setChatDragState(false);
        }
    });

    document.addEventListener("drop", (event) => {
        if (!isFileDrag(event)) return;
        dragCounter = 0;
        setChatDragState(false);
    });

    window.addEventListener("blur", () => {
        dragCounter = 0;
        setChatDragState(false);
    });

    // ==========================================
    // 2. REACT INPUT SETTER (EKLEME / APPEND DESTEKLİ)
    // ==========================================
    const setInputText = (text, append = true) => {
        const textarea = document.querySelector('textarea, input[type="text"]');
        if (textarea) {
            const currentVal = textarea.value || "";
            let newVal = text;

            // Kutuda önceden metin varsa sonuna ekleme yap
            if (append && currentVal.trim().length > 0) {
                newVal = `${currentVal.trim()} ${text.trim()}`;
            }

            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype,
                "value"
            ).set;
            nativeInputValueSetter.call(textarea, newVal);
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
        }
    };

    // ==========================================
    // 3. FOOTER AÇIKLAMA ÖZELLEŞTİRMESİ
    // ==========================================
    const customizeFooterDisclaimer = () => {
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
            if (node.nodeValue && node.nodeValue.includes("LLMs can make mistakes")) {
                node.nodeValue = node.nodeValue.replace(
                    "LLMs can make mistakes. Check important info.",
                    "ARK System can make tactical errors. Verify payload integrity."
                );
            }
        }
    };

    // ==========================================
    // 4. MİKROFON & YILDIRIM BUTONLARI VE API KÖPRÜSÜ
    // ==========================================
    const injectMicButtons = () => {
        const submitBtn = document.querySelector(
            'button[type="submit"], button#chat-submit, button[aria-label*="send" i]'
        );
        if (!submitBtn || !submitBtn.parentNode) return;

        // --- 1. MİKROFON TOGGLE BUTONU (BAŞLAT / DURDUR & METNE EKLE) ---
        if (!document.getElementById("ark-mic-btn")) {
            const micBtn = document.createElement("button");
            micBtn.id = "ark-mic-btn";
            micBtn.type = "button";
            micBtn.title = "ARK Sesli Metin (Başlat / Durdur)";
            micBtn.className =
                "p-2 rounded-lg text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors";
            micBtn.innerHTML = `
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
                  <path d="M19 10v1a7 7 0 0 1-14 0v-1"></path>
                  <line x1="12" y1="19" x2="12" y2="23"></line>
                  <line x1="8" y1="23" x2="16" y2="23"></line>
                </svg>
            `;

            micBtn.addEventListener("click", async () => {
                if (isSttActive) {
                    try {
                        await fetch("/ark/listen/stop", { method: "POST" });
                    } catch (e) {
                        console.error("Stop Error:", e);
                    }
                    return;
                }

                isSttActive = true;
                micBtn.style.color = "#ef4444";
                micBtn.style.backgroundColor = "rgba(239, 68, 68, 0.15)";
                micBtn.classList.add("animate-pulse");

                try {
                    const res = await fetch("/ark/listen/stt", { method: "POST" });
                    const data = await res.json();
                    if (data.text) {
                        // Var olan metnin üzerine ekler (append = true)
                        setInputText(data.text, true);
                    }
                } catch (e) {
                    console.error("STT Error:", e);
                } finally {
                    isSttActive = false;
                    micBtn.style.color = "";
                    micBtn.style.backgroundColor = "";
                    micBtn.classList.remove("animate-pulse");
                }
            });

            submitBtn.parentNode.insertBefore(micBtn, submitBtn);
        }

        // --- 2. YILDIRIM / KOMUT BUTONU ---
        if (!document.getElementById("ark-cmd-mic-btn")) {
            const cmdMicBtn = document.createElement("button");
            cmdMicBtn.id = "ark-cmd-mic-btn";
            cmdMicBtn.type = "button";
            cmdMicBtn.title = "ARK Komut Modu (Sesli Komut Çalıştır)";
            cmdMicBtn.className =
                "p-2 rounded-lg text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors";
            cmdMicBtn.innerHTML = `
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
                </svg>
            `;

            cmdMicBtn.addEventListener("click", async () => {
                if (cmdMicBtn.classList.contains("animate-pulse")) return;

                cmdMicBtn.style.color = "#eab308";
                cmdMicBtn.style.backgroundColor = "rgba(234, 179, 8, 0.15)";
                cmdMicBtn.classList.add("animate-pulse");

                try {
                    const res = await fetch("/ark/listen/cmd", { method: "POST" });
                    const data = await res.json();

                    if (data.text) {
                        // Komut modunda metni temizleyip /cmd ile başlatır (append = false)
                        setInputText("/cmd " + data.text, false);
                        setTimeout(() => {
                            if (submitBtn) submitBtn.click();
                        }, 100);
                    }
                } catch (e) {
                    console.error("CMD Error:", e);
                } finally {
                    cmdMicBtn.style.color = "";
                    cmdMicBtn.style.backgroundColor = "";
                    cmdMicBtn.classList.remove("animate-pulse");
                }
            });

            submitBtn.parentNode.insertBefore(cmdMicBtn, submitBtn);
        }
    };

    setTimeout(customizeFooterDisclaimer, 500);
    setTimeout(injectMicButtons, 800);

    const observer = new MutationObserver(() => {
        customizeFooterDisclaimer();
        injectMicButtons();
    });
    observer.observe(document.body, { childList: true, subtree: true });
});