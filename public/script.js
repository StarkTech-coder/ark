document.addEventListener("DOMContentLoaded", () => {
    "use strict";

    let dragCounter = 0;
    let isSttActive = false;
    let isCmdActive = false;
    let isWebSearchActive = false;

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
    // 2. REACT INPUT SETTER
    // ==========================================
    const setInputText = (text, append = true) => {
        const textarea = document.querySelector('textarea, input[type="text"]');
        if (textarea) {
            const currentVal = textarea.value || "";
            let newVal = text;

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
    // 4. MİKROFON, YILDIRIM VE WEB ARAMA BUTONLARI
    // ==========================================
    const injectMicButtons = () => {
        if (document.getElementById("ark-web-btn")) return;

        // Gönder butonunu geniş bir selector ile bulalım
        const submitBtn = document.querySelector(
            'button[type="submit"], button#chat-submit, button[aria-label*="send" i], button[aria-label*="Gönder" i], button:has(svg)'
        ) || document.querySelector('textarea')?.form?.querySelector('button');

        if (!submitBtn || !submitBtn.parentNode) return;

        // Container oluştur/bul
        let actionWrapper = document.getElementById("ark-action-wrapper");
        if (!actionWrapper) {
            actionWrapper = document.createElement("div");
            actionWrapper.id = "ark-action-wrapper";
            submitBtn.parentNode.insertBefore(actionWrapper, submitBtn);
        }

        // --- 0. WEB ARAMA TOGGLE BUTONU ---
        const webBtn = document.createElement("button");
        webBtn.id = "ark-web-btn";
        webBtn.type = "button";
        webBtn.title = "ARK Web Arama Modu (Aç / Kapat)";
        webBtn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="2" y1="12" x2="22" y2="12"></line>
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10z"></path>
            </svg>
        `;
        webBtn.addEventListener("click", async () => {
            try {
                const res = await fetch("/ark/web/toggle", { method: "POST" });
                const data = await res.json();
                isWebSearchActive = data.active;
                if (isWebSearchActive) {
                    webBtn.classList.add("active");
                    webBtn.title = "ARK Web Arama Modu: AKTİF";
                } else {
                    webBtn.classList.remove("active");
                    webBtn.title = "ARK Web Arama Modu: PASİF";
                }
            } catch (e) { console.error("Web Toggle Error:", e); }
        });
        actionWrapper.appendChild(webBtn);

        // --- 1. MİKROFON TOGGLE BUTONU ---
        const micBtn = document.createElement("button");
        micBtn.id = "ark-mic-btn";
        micBtn.type = "button";
        micBtn.title = "ARK Sesli Metin (Başlat / Durdur)";
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
                try { await fetch("/ark/listen/stop", { method: "POST" }); } catch (e) { console.error(e); }
                return;
            }
            isSttActive = true;
            micBtn.classList.add("active", "animate-pulse");

            try {
                const res = await fetch("/ark/listen/stt", { method: "POST" });
                const data = await res.json();
                if (data.text) setInputText(data.text, true);
            } catch (e) { console.error("STT Error:", e); }
            finally {
                isSttActive = false;
                micBtn.classList.remove("active", "animate-pulse");
            }
        });
        actionWrapper.appendChild(micBtn);

        // --- 2. YILDIRIM / KOMUT BUTONU ---
        const cmdMicBtn = document.createElement("button");
        cmdMicBtn.id = "ark-cmd-mic-btn";
        cmdMicBtn.type = "button";
        cmdMicBtn.title = "ARK Komut Modu (Başlat / Durdur)";
        cmdMicBtn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
            </svg>
        `;
        cmdMicBtn.addEventListener("click", async () => {
            if (isCmdActive) {
                try { await fetch("/ark/listen/stop", { method: "POST" }); } catch (e) { console.error(e); }
                return;
            }
            isCmdActive = true;
            cmdMicBtn.classList.add("active", "animate-pulse");

            try {
                // Metin kutusuna yazmadan direkt komut servisine istek gönderir
                const res = await fetch("/ark/listen/cmd", { method: "POST" });
                const data = await res.json();
                console.log("Komut Algılandı & İşlendi:", data.text);
            } catch (e) { console.error("CMD Error:", e); }
            finally {
                isCmdActive = false;
                cmdMicBtn.classList.remove("active", "animate-pulse");
            }
        });
        actionWrapper.appendChild(cmdMicBtn);
    };

    setTimeout(customizeFooterDisclaimer, 500);
    setTimeout(injectMicButtons, 800);

    const observer = new MutationObserver(() => {
        customizeFooterDisclaimer();
        injectMicButtons();
    });
    observer.observe(document.body, { childList: true, subtree: true });
});