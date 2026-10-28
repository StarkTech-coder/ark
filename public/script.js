document.addEventListener("DOMContentLoaded", () => {
    "use strict";

    let dragCounter = 0;
    let isSttActive = false;
    let isCmdActive = false;
    let isWebSearchActive = false;
    let isRagActive = false;

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
    // 4. MİKROFON, YILDIRIM, WEB VE RAG BUTONLARI (KONTROLLÜ GÜÇLENDİRİLMİŞ ENJEKSİYON)
    // ==========================================
    const injectMicButtons = () => {
        // Eğer butonlar zaten eklenmişse tekrar tetikleme
        if (document.getElementById("ark-rag-btn")) return;

        // Chainlit input formunu veya butonların ekleneceği ana satırı arıyoruz
        const targetContainer = document.querySelector('form') ||
            document.querySelector('[class*="composer"]') ||
            document.querySelector('[class*="Composer"]') ||
            document.querySelector('textarea')?.closest('div');

        if (!targetContainer) return;

        // Gönder tuşunu veya input içerisindeki son buton grubunu buluyoruz
        const sendBtn = targetContainer.querySelector('button[type="submit"]') ||
            targetContainer.querySelector('button:last-of-type');

        let actionWrapper = document.getElementById("ark-action-wrapper");
        if (!actionWrapper) {
            actionWrapper = document.createElement("div");
            actionWrapper.id = "ark-action-wrapper";

            if (sendBtn && sendBtn.parentNode) {
                sendBtn.parentNode.insertBefore(actionWrapper, sendBtn);
            } else {
                targetContainer.appendChild(actionWrapper);
            }
        }

        // --- RAG KNOWLEDGE BASE (KİTAP) BUTONU ---
        const ragBtn = document.createElement("button");
        ragBtn.id = "ark-rag-btn";
        ragBtn.type = "button";
        ragBtn.title = "ARK RAG Ders Notları / PDF Modu (Aç / Kapat)";
        ragBtn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"></path>
              <path d="M6 6h10"></path>
              <path d="M6 10h10"></path>
            </svg>
        `;
        ragBtn.addEventListener("click", async () => {
            try {
                const res = await fetch("/ark/rag/toggle", { method: "POST" });
                const data = await res.json();
                isRagActive = data.active;
                ragBtn.classList.toggle("active", isRagActive);
                ragBtn.title = isRagActive ? "ARK RAG Ders Notları Modu: AKTİF" : "ARK RAG Ders Notları Modu: PASİF";
            } catch (e) { console.error("RAG Toggle Error:", e); }
        });
        actionWrapper.appendChild(ragBtn);

        // --- WEB ARAMA (KÜRE) BUTONU ---
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
                webBtn.classList.toggle("active", isWebSearchActive);
                webBtn.title = isWebSearchActive ? "ARK Web Arama Modu: AKTİF" : "ARK Web Arama Modu: PASİF";
            } catch (e) { console.error("Web Toggle Error:", e); }
        });
        actionWrapper.appendChild(webBtn);

        // --- MİKROFON BUTONU ---
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
                try { await fetch("/ark/listen/stop", { method: "POST" }); } catch (e) { }
                return;
            }
            isSttActive = true;
            micBtn.classList.add("active", "animate-pulse");
            try {
                const res = await fetch("/ark/listen/stt", { method: "POST" });
                const data = await res.json();
                if (data.text) setInputText(data.text, true);
            } catch (e) { }
            finally {
                isSttActive = false;
                micBtn.classList.remove("active", "animate-pulse");
            }
        });
        actionWrapper.appendChild(micBtn);

        // --- YILDIRIM / KOMUT BUTONU ---
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
                try { await fetch("/ark/listen/stop", { method: "POST" }); } catch (e) { }
                return;
            }
            isCmdActive = true;
            cmdMicBtn.classList.add("active", "animate-pulse");
            try {
                await fetch("/ark/listen/cmd", { method: "POST" });
            } catch (e) { }
            finally {
                isCmdActive = false;
                cmdMicBtn.classList.remove("active", "animate-pulse");
            }
        });
        actionWrapper.appendChild(cmdMicBtn);
    };

    // Sürekli kontrol mekanizması (DOM değişikliklerini anında yakalar)
    const observer = new MutationObserver(() => {
        customizeFooterDisclaimer();
        injectMicButtons();
    });
    observer.observe(document.body, { childList: true, subtree: true });

    // İlk yükleme tetikleyicileri
    setTimeout(customizeFooterDisclaimer, 300);
    setTimeout(injectMicButtons, 500);
});