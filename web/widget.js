/* Faiyke chat widget (English and German). Add to any page, just before </body>:
 *   <script src="https://YOUR-SERVER/widget.js" data-api="https://YOUR-SERVER"
 *           data-privacy-url="https://YOUR-SITE/datenschutz" defer></script>
 * Optional: data-lang="de" or "en" (default: the page's language, then the browser's).
 * Optional: data-optional-storage="off" stops the widget from remembering the read-aloud and voice settings in the
 * visitor's browser (set it until your own cookie banner has been accepted). The random chat number stays in session storage.
 * The server must list your website in ALLOWED_ORIGINS.
 *
 * Features: chat, "Book a call" button (when BOOKING_URL is set on the server), thumbs up/down on
 * answers, voice input (microphone) and spoken answers (browser speech features, where supported).
 * Safety: text from the server is only ever shown as plain text, never as HTML.
 */
(function () {
  var script = document.currentScript;
  var API = (script && script.getAttribute("data-api")) || "";
  var PRIVACY = (script && script.getAttribute("data-privacy-url")) || "";
  var REMEMBER = !(script && script.getAttribute("data-optional-storage") === "off");   // read-aloud and voice settings
  var lang = ((script && script.getAttribute("data-lang")) || document.documentElement.lang || navigator.language || "en")
    .toLowerCase().indexOf("de") === 0 ? "de" : "en";

  var T = {
    en: {
      sub: "AI assistant · Mon–Fri 8–18, Sat 10–14",
      hi: "Hi, I’m Faiyke’s AI assistant. How can I help?",
      note: "You are chatting with an AI assistant. Please don’t share passwords or card numbers. If you ask for a person, we’ll ask your permission before passing on your details. ",
      privacy: "Privacy",
      placeholder: "Type your question…",
      book: "Book a call", stopped: "Stopped.", suggested: "Suggested questions", send: "Send", open: "Open chat", close: "Close chat", dialog: "Chat with Faiyke", field: "Your message",
      listen: "Listen", stop: "Stop", mic: "Speak your question", micStop: "Stop listening", autoRead: "Read answers aloud",
      listening: "Listening…", micNote: "Listening. Your browser’s speech service processes the audio. Click the microphone to stop.",
      micDenied: "Microphone access is blocked. Allow it in your browser’s site settings.",
      micFail: "Voice input didn’t work. Try again or type your question.",
      del: "Delete my chat", delSure: "Click again to delete this chat",
      voiceConsent: "Voice input sends what you say to your browser’s speech service (for example Google or Microsoft) to turn it into text. Use it only if that is OK for you.",
      allow: "Use voice input", notNow: "Not now",
      good: "Good answer", bad: "Bad answer", thanks: "Thanks for the feedback",
      whyPh: "What was wrong? (optional, no personal details)", whySend: "Send",
      fail: "Sorry, something went wrong. Please email info@faiyke.com or call/WhatsApp +49 176 41565516.",
      offline: "Sorry, I can’t connect right now. Please email info@faiyke.com or call/WhatsApp +49 176 41565516.",
      human: "Talk to a person", humanMsg: "I’d like to talk to a person.", basedOn: "Based on",
      unsure: "Not sure about this one? A person on our team can confirm it.",
      thinking: "Thinking…", checking: "Checking", and: "and", more: "more",
      reasons: ["Wrong information", "Didn’t answer my question", "Too long", "Something else"]
    },
    de: {
      sub: "KI-Assistent · Mo–Fr 8–18, Sa 10–14 Uhr",
      hi: "Hallo, ich bin der KI-Assistent von Faiyke. Wie kann ich helfen?",
      note: "Sie schreiben mit einem KI-Assistenten. Bitte geben Sie keine Passwörter oder Kartennummern an. Wenn Sie mit einer Person sprechen möchten, fragen wir vor der Weitergabe Ihrer Daten um Ihre Erlaubnis. ",
      privacy: "Datenschutz",
      placeholder: "Ihre Frage…",
      book: "Gespräch buchen", stopped: "Gestoppt.", suggested: "Vorgeschlagene Fragen", send: "Senden", open: "Chat öffnen", close: "Chat schließen", dialog: "Chat mit Faiyke", field: "Ihre Nachricht",
      listen: "Vorlesen", stop: "Stopp", mic: "Frage einsprechen", micStop: "Aufnahme beenden", autoRead: "Antworten vorlesen",
      listening: "Ich höre zu…", micNote: "Ich höre zu. Der Spracherkennungsdienst Ihres Browsers verarbeitet das Audio. Zum Beenden das Mikrofon anklicken.",
      micDenied: "Der Mikrofonzugriff ist blockiert. Bitte in den Website-Einstellungen des Browsers erlauben.",
      micFail: "Spracheingabe hat nicht funktioniert. Bitte erneut versuchen oder tippen.",
      del: "Meinen Chat löschen", delSure: "Nochmal klicken, um diesen Chat zu löschen",
      voiceConsent: "Die Spracheingabe sendet Ihre Sprache an den Spracherkennungsdienst Ihres Browsers (zum Beispiel Google oder Microsoft), der sie in Text umwandelt. Bitte nur nutzen, wenn das für Sie in Ordnung ist.",
      allow: "Spracheingabe nutzen", notNow: "Nicht jetzt",
      good: "Gute Antwort", bad: "Schlechte Antwort", thanks: "Danke für die Rückmeldung",
      whyPh: "Was war falsch? (optional, keine persönlichen Daten)", whySend: "Senden",
      fail: "Entschuldigung, da ist etwas schiefgelaufen. Bitte schreiben Sie an info@faiyke.com oder rufen Sie an / WhatsApp: +49 176 41565516.",
      offline: "Entschuldigung, ich kann mich gerade nicht verbinden. Bitte schreiben Sie an info@faiyke.com oder rufen Sie an / WhatsApp: +49 176 41565516.",
      human: "Mit einer Person sprechen", humanMsg: "Ich möchte mit einer Person sprechen.", basedOn: "Grundlage",
      unsure: "Nicht sicher? Eine Person aus unserem Team kann das bestätigen.",
      thinking: "Einen Moment…", checking: "Ich prüfe", and: "und", more: "weitere",
      reasons: ["Falsche Angabe", "Frage nicht beantwortet", "Zu lang", "Etwas anderes"]
    }
  }[lang];

  var KEY = "faiyke_session", READ_KEY = "faiyke_autoread";
  var sessionId = null;
  try { sessionId = sessionStorage.getItem(KEY); } catch (e) {}
  var busy = false;
  var bookingUrl = ""; // from the server's settings; only a plain https address is ever used
  var HTTPS = /^https:\/\/[^\s"'<>]+$/;
  try {
    fetch(API + "/api/config").then(function (r) { return r.json(); }).then(function (d) {
      var u = d && d.booking_url;
      bookingUrl = (typeof u === "string" && HTTPS.test(u)) ? u : "";
      if (d && typeof d.privacy_url === "string" && HTTPS.test(d.privacy_url)) addPrivacy(d.privacy_url);
    }).catch(function () {});
  } catch (e) {}

  var css = [
    ".fy-btn{position:fixed;right:20px;bottom:20px;width:58px;height:58px;border-radius:50%;border:0;background:#ff6b1a;color:#fff;cursor:pointer;display:grid;place-items:center;box-shadow:0 2px 4px rgba(27,22,36,.2),0 10px 30px rgba(27,22,36,.28);z-index:2147483000;transition:transform .15s}",
    ".fy-btn:hover{transform:scale(1.05)}",
    ".fy-btn svg,.fy-mark svg,.fy-work svg{overflow:visible}",
    ".fy-btn:focus-visible,.fy-form button:focus-visible,.fy-bar button:focus-visible,.fy-speak:focus-visible,.fy-why button:focus-visible,.fy-unsure button:focus-visible,.fy-reasons button:focus-visible{outline:2px solid #5a3b96;outline-offset:2px}",
    ".fy-st{fill:none;stroke-width:2.7;stroke-linecap:round;transform-box:fill-box;transform-origin:center}",
    ".fy-st:nth-child(1){stroke:#c2506e}.fy-st:nth-child(2){stroke:#7f8bf0}.fy-st:nth-child(3){stroke:#2bb3bd}.fy-st:nth-child(4){stroke:#e0952a}.fy-st:nth-child(5){stroke:#7bbf5a}",
    ".fy-panel [hidden]{display:none!important}",
    ".fy-panel{position:fixed;right:20px;bottom:90px;width:380px;max-width:calc(100vw - 32px);height:600px;max-height:calc(100vh - 116px);display:none;flex-direction:column;background:#f1efea;color:#161513;border-radius:20px;box-shadow:0 2px 6px rgba(27,22,36,.12),0 18px 50px rgba(27,22,36,.3);overflow:hidden;font:15px/1.55 'Segoe UI Variable Text','Segoe UI',system-ui,-apple-system,sans-serif;z-index:2147483000}",
    ".fy-panel.fy-open{display:flex;animation:fy-in .18s ease-out}",
    "@keyframes fy-in{from{opacity:0;transform:translateY(8px)}}",
    ".fy-head{display:flex;align-items:center;gap:11px;padding:14px 16px;border-bottom:1px solid #dcd8d0;font-weight:650}",
    ".fy-mark{flex:none;width:30px;height:30px;display:grid;place-items:center}.fy-mark svg{width:100%;height:100%}",
    ".fy-head small{display:block;font-weight:400;color:#6c6479;font-size:12.5px;line-height:1.3}",
    ".fy-ttl{flex:1;min-width:0}",
    ".fy-speak,.fy-del{flex:none;width:34px;height:34px;border-radius:10px;border:1px solid #dcd8d0;background:#fbfaf8;color:#6c6479;display:grid;place-items:center;cursor:pointer}",
    ".fy-speak:hover:not(:disabled),.fy-del:hover{color:#161513}.fy-speak:disabled{opacity:.45;cursor:default}",
    ".fy-del.fy-sure{width:auto;padding:0 10px;font:inherit;font-size:12.5px;font-weight:600;color:#b3261e;border-color:#b3261e}",
    ".fy-consent{margin:0 12px 8px;padding:10px 12px;border:1px solid #dcd8d0;border-radius:14px;font-size:13px;line-height:1.45;color:#4d4559;background:#f1efea}",
    ".fy-consent p{margin:0 0 8px}",
    ".fy-consent button{border:0;border-radius:10px;padding:6px 13px;margin-right:6px;font:inherit;font-weight:600;font-size:13px;background:#ff6b1a;color:#fff;cursor:pointer}",
    ".fy-consent button.fy-plain{background:none;color:#4d4559;border:1px solid #dcd8d0}",
    ".fy-speak[aria-pressed=true]{background:#ff6b1a;border-color:#ff6b1a;color:#161513}",
    ".fy-log{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:14px;background:#f1efea}",
    ".fy-msg{overflow-wrap:anywhere;white-space:pre-wrap}",
    ".fy-bot{align-self:flex-start;max-width:94%}",
    ".fy-me{align-self:flex-end;max-width:84%;background:#161513;color:#fff;padding:9px 14px;border-radius:18px 18px 5px 18px}",
    ".fy-err{color:#b3261e}",
    ".fy-work{display:flex;align-items:center;gap:9px;color:#4d4559;font-size:14px;white-space:normal}",
    ".fy-work .fy-loader{flex:none;width:24px;height:24px}.fy-work .fy-loader svg{width:100%;height:100%}",
    ".fy-work .fy-st{animation:fy-sway 1.5s ease-in-out infinite}.fy-work .fy-st:nth-child(2){animation-delay:.12s}.fy-work .fy-st:nth-child(3){animation-delay:.24s}.fy-work .fy-st:nth-child(4){animation-delay:.36s}.fy-work .fy-st:nth-child(5){animation-delay:.48s}",
    "@keyframes fy-sway{0%,100%{transform:translateY(1.5px) scaleY(.88)}50%{transform:translateY(-1.5px) scaleY(1.06)}}",
    ".fy-cta{display:inline-block;margin-top:8px;padding:8px 15px;border-radius:10px;background:#ff6b1a;color:#fff;font-weight:600;text-decoration:none;font-size:14px}",
    ".fy-cta:hover{filter:brightness(1.06)}",
    ".fy-tools{align-self:flex-start;max-width:94%;margin-top:-8px}",
    ".fy-src{display:flex;flex-wrap:wrap;align-items:center;gap:5px 6px;margin:0 0 4px;padding:0;list-style:none;font-size:12px;color:#6c6479}",
    ".fy-src li.fy-s{display:inline-flex;align-items:center;gap:6px;padding:2px 9px 2px 8px;border:1px solid #dcd8d0;border-radius:999px;background:#fbfaf8;color:#4d4559;line-height:1.4}",
    ".fy-src li.fy-s::before{content:'';width:6px;height:6px;border-radius:50%;background:var(--fyc,#6c6479);flex:none}",
    ".fy-unsure{margin:2px 0 6px;padding:2px 0 2px 11px;border-left:3px solid #ff6b1a;font-size:13.5px;color:#4d4559;display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px}",
    ".fy-unsure p{margin:0;white-space:normal}",
    ".fy-unsure button{border:1px solid #dcd8d0;background:#fbfaf8;color:#161513;border-radius:999px;padding:5px 12px;font:inherit;font-size:13px;font-weight:600;cursor:pointer}",
    ".fy-unsure button:hover{border-color:#6c6479}",
    ".fy-bar{display:flex;align-items:center;gap:2px;margin-left:-6px}",
    ".fy-bar button{border:0;background:none;color:#6c6479;font:inherit;font-size:12.5px;padding:4px 7px;border-radius:8px;cursor:pointer;display:inline-flex;align-items:center}",
    ".fy-bar button:hover{background:#e9e6e0;color:#161513}",
    ".fy-bar button[aria-pressed=true]{color:#161513;background:#e9e6e0}",
    ".fy-thanks{margin-left:6px;font-size:12.5px;color:#6c6479}",
    ".fy-chips{align-self:flex-start;max-width:94%;display:flex;flex-wrap:wrap;gap:6px;margin-top:-4px}",
    ".fy-chips button,.fy-reasons button{border:1px solid #dcd8d0;background:#fbfaf8;color:inherit;border-radius:999px;padding:6px 12px;font:inherit;font-size:13.5px;line-height:1.35;text-align:left;cursor:pointer}",
    ".fy-chips button:hover,.fy-reasons button:hover{border-color:#5a3b96;color:#5a3b96}",
    ".fy-chips button:focus-visible{outline:2px solid #5a3b96;outline-offset:2px}",
    ".fy-whybox{margin-top:6px;display:grid;gap:6px}.fy-reasons{display:flex;flex-wrap:wrap;gap:5px}.fy-reasons button{padding:4px 11px;font-size:13px}",
    ".fy-why{display:flex;gap:6px}",
    ".fy-why input{flex:1;min-width:0;padding:7px 11px;border:1px solid #dcd8d0;border-radius:12px;font:inherit;font-size:13.5px;background:#fbfaf8;color:inherit}",
    ".fy-why input:focus{outline:0;border-color:#5a3b96}",
    ".fy-why button{border:0;border-radius:12px;padding:0 13px;background:#ff6b1a;color:#fff;font:inherit;font-weight:600;font-size:13.5px;cursor:pointer}",
    ".fy-note{font-size:12px;color:#6c6479;line-height:1.45;padding:0 2px}",
    ".fy-note a{color:inherit}",
    ".fy-status{padding:0 18px 6px;font-size:12px;line-height:1.4;color:#6c6479}.fy-status:empty{display:none}.fy-status.fy-bad{color:#b3261e}",
    ".fy-form{display:flex;align-items:flex-end;gap:6px;margin:0 12px 12px;padding:6px 6px 6px 14px;border:1px solid #dcd8d0;border-radius:14px;background:#fbfaf8}",
    ".fy-form:focus-within{border-color:#5a3b96}",
    ".fy-form textarea{flex:1;min-width:0;border:0;outline:0;resize:none;max-height:120px;padding:7px 0;font:inherit;background:none;color:inherit}",
    ".fy-form button{flex:none;width:36px;height:36px;border:0;border-radius:10px;background:#ff6b1a;color:#fff;cursor:pointer;display:grid;place-items:center;position:relative}",
    ".fy-form button:disabled{background:#dcd8d0;color:#8a8196;cursor:default}",
    ".fy-form .fy-mic{background:none;color:#4d4559}.fy-form .fy-mic:hover{background:#e9e6e0}",
    ".fy-form .fy-mic[aria-pressed=true]{background:#b3261e;color:#fff}",
    ".fy-form .fy-mic[aria-pressed=true]::after{content:'';position:absolute;inset:-4px;border-radius:50%;border:2px solid #b3261e;animation:fy-ring 1.4s infinite ease-out}",
    "@keyframes fy-ring{from{opacity:.7;transform:scale(.9)}to{opacity:0;transform:scale(1.3)}}",
    "@media (max-width:520px){.fy-panel{right:0;bottom:0;width:100vw;max-width:none;height:100dvh;max-height:none;border-radius:0}.fy-btn{right:16px;bottom:16px}}",
    "@media (prefers-reduced-motion:reduce){.fy-panel.fy-open,.fy-work .fy-st,.fy-form .fy-mic[aria-pressed=true]::after{animation:none}.fy-btn{transition:none}}",
    "@media (prefers-color-scheme:dark){.fy-panel{background:#17131f;color:#efeaf6}.fy-head{border-color:#2b2537}.fy-head small,.fy-note,.fy-status,.fy-thanks,.fy-src{color:#978fa6}.fy-log{background:#17131f}.fy-me{background:#3a2f52;color:#f6f2fb}.fy-work,.fy-unsure{color:#bdb5ca}.fy-form{background:#1d1827;border-color:#2b2537}.fy-form:focus-within{border-color:#b9a0f2}.fy-form button{background:#ff7a2e;color:#1b1624}.fy-form button:disabled{background:#2b2537;color:#978fa6}.fy-form .fy-mic{background:none;color:#bdb5ca}.fy-form .fy-mic:hover{background:#2b2537}.fy-form .fy-mic[aria-pressed=true]{background:#f2877f;color:#17131f}.fy-err,.fy-status.fy-bad{color:#f2877f}.fy-speak,.fy-del{background:#1d1827;border-color:#2b2537;color:#978fa6}.fy-speak:hover:not(:disabled),.fy-del:hover{color:#efeaf6}.fy-del.fy-sure{color:#f2877f;border-color:#f2877f}.fy-consent{background:#1d1827;border-color:#2b2537;color:#bdb5ca}.fy-consent button{background:#ff7a2e}.fy-consent button.fy-plain{background:none;color:#bdb5ca;border-color:#2b2537}.fy-speak[aria-pressed=true]{background:#ff7a2e;border-color:#ff7a2e;color:#1b1624}.fy-bar button{color:#978fa6}.fy-bar button:hover,.fy-bar button[aria-pressed=true]{background:#2b2537;color:#efeaf6}.fy-chips button,.fy-reasons button{background:#1d1827;border-color:#2b2537}.fy-chips button:hover,.fy-reasons button:hover{border-color:#b9a0f2;color:#b9a0f2}.fy-why input{background:#1d1827;border-color:#2b2537}.fy-why input:focus{border-color:#b9a0f2}.fy-why button,.fy-cta{background:#ff7a2e;color:#1b1624}.fy-src li.fy-s{background:#1d1827;border-color:#2b2537;color:#bdb5ca}.fy-unsure button{background:#1d1827;border-color:#2b2537;color:#efeaf6}.fy-btn:focus-visible,.fy-form button:focus-visible,.fy-bar button:focus-visible,.fy-speak:focus-visible,.fy-why button:focus-visible,.fy-unsure button:focus-visible,.fy-reasons button:focus-visible{outline-color:#b9a0f2}}"
  ].join("");
  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text) n.textContent = text;
    return n;
  }
  var ICON = {
    chat: '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>',
    send: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
    mic: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
    speaker: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/></svg>',
    trash: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>',
    up: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 11v9H4v-9h3zM7 11l4-8a2 2 0 0 1 2 2v4h6a2 2 0 0 1 2 2l-1.5 7A2 2 0 0 1 17.5 20H7"/></svg>',
    down: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 13V4h3v9h-3zM17 13l-4 8a2 2 0 0 1-2-2v-4H5a2 2 0 0 1-2-2l1.5-7A2 2 0 0 1 6.5 4H17"/></svg>'
  };

  /* The mark: five strands, one per service line. Built with the DOM (never from server text). */
  var SVGNS = "http://www.w3.org/2000/svg";
  var STRANDS = ["M5 4C3 12 7 20 5 28", "M10.5 3C8.5 11 12.5 21 10.5 29", "M16 3C14 12 18 20 16 29", "M21.5 3C19.5 11 23.5 21 21.5 29", "M27 4C25 12 29 20 27 28"];
  function strandsSvg(size) {
    var svg = document.createElementNS(SVGNS, "svg");
    svg.setAttribute("viewBox", "0 0 32 32"); svg.setAttribute("aria-hidden", "true");
    if (size) { svg.setAttribute("width", size); svg.setAttribute("height", size); }
    STRANDS.forEach(function (d) {
      var p = document.createElementNS(SVGNS, "path");
      p.setAttribute("class", "fy-st"); p.setAttribute("d", d);
      svg.appendChild(p);
    });
    return svg;
  }
  function workEl(text) {  // what the assistant is doing, before the answer starts to appear
    var w = el("span", "fy-work");
    w.setAttribute("role", "status");
    var l = el("span", "fy-loader");
    l.appendChild(strandsSvg());
    w.appendChild(l); w.appendChild(el("span", "", text));
    return w;
  }
  function checkingText(list) {
    if (!list.length) return T.thinking;
    if (list.length === 1) return T.checking + " " + list[0].title + "…";
    if (list.length === 2) return T.checking + " " + list[0].title + " " + T.and + " " + list[1].title + "…";
    return T.checking + " " + list[0].title + " " + T.and + " " + (list.length - 1) + " " + T.more + "…";
  }
  /* Which parts of our information an answer used: titles only, checked again here, shown as plain text. */
  var LINE_KEYS = { hair: "#c2506e", ai: "#7f8bf0", web: "#2bb3bd", it: "#e0952a", crm: "#7bbf5a", general: "#6c6479" };
  function cleanSources(list) {
    if (!Array.isArray(list)) return [];
    return list.filter(function (x) {
      return x && typeof x.title === "string" && x.title.length > 0 && x.title.length <= 60 && typeof LINE_KEYS[x.line] === "string";
    }).slice(0, 3).map(function (x) { return { line: x.line, title: x.title }; });
  }
  function sourceList(list) {
    if (!list.length) return null;
    var ul = el("ul", "fy-src");
    ul.setAttribute("aria-label", T.basedOn);
    ul.appendChild(el("li", "", T.basedOn));
    list.forEach(function (x) {
      var li = el("li", "fy-s", x.title);
      li.style.setProperty("--fyc", LINE_KEYS[x.line]);
      ul.appendChild(li);
    });
    return ul;
  }
  function askPerson() {  // starts the normal hand-off conversation: the assistant asks, and waits for a yes
    if (busy) return;
    input.value = T.humanMsg; grow();
    if (form.requestSubmit) form.requestSubmit();
  }
  function unsureBox() {
    var b = el("div", "fy-unsure");
    b.appendChild(el("p", "", T.unsure));
    var go = el("button", "", T.human);
    go.type = "button";
    go.addEventListener("click", askPerson);
    b.appendChild(go);
    return b;
  }

  var btn = el("button", "fy-btn");
  btn.appendChild(strandsSvg(30));
  btn.setAttribute("aria-label", T.open);
  var panel = el("div", "fy-panel");
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", T.dialog);
  var head = el("div", "fy-head");
  var mark = el("span", "fy-mark");
  mark.setAttribute("aria-hidden", "true");
  mark.appendChild(strandsSvg());
  var title = el("div", "fy-ttl", "Faiyke");
  title.appendChild(el("small", "", T.sub));
  var speakBtn = el("button", "fy-speak");
  speakBtn.type = "button"; speakBtn.innerHTML = ICON.speaker; speakBtn.hidden = true;
  speakBtn.setAttribute("aria-label", T.autoRead); speakBtn.title = T.autoRead;
  var delBtn = el("button", "fy-del");
  delBtn.type = "button"; delBtn.innerHTML = ICON.trash;
  delBtn.setAttribute("aria-label", T.del); delBtn.title = T.del;
  var humanBtn = el("button", "fy-speak fy-human");
  humanBtn.type = "button";
  humanBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="3.5"/><path d="M5 20c.8-3.6 3.6-5.5 7-5.5s6.2 1.9 7 5.5"/></svg>';
  humanBtn.setAttribute("aria-label", T.human); humanBtn.title = T.human;
  humanBtn.addEventListener("click", function () { askPerson(); });
  head.appendChild(mark); head.appendChild(title); head.appendChild(humanBtn); head.appendChild(speakBtn); head.appendChild(delBtn);
  var log = el("div", "fy-log");
  log.setAttribute("aria-live", "polite");
  var status = el("div", "fy-status");
  status.setAttribute("aria-live", "polite");
  var form = el("form", "fy-form");
  var input = el("textarea");
  input.rows = 1; input.maxLength = 1000; input.placeholder = T.placeholder;
  input.setAttribute("aria-label", T.field);
  var mic = el("button", "fy-mic");
  mic.type = "button"; mic.innerHTML = ICON.mic; mic.hidden = true;
  mic.setAttribute("aria-pressed", "false"); mic.setAttribute("aria-label", T.mic); mic.title = T.mic;
  var send = el("button");
  send.type = "submit"; send.disabled = true;
  send.setAttribute("aria-label", T.send);
  send.innerHTML = ICON.send;
  var CAN_STREAM = !!(window.fetch && window.ReadableStream && window.TextDecoder);
  var stopFn = null;  // set while an answer is streaming: the send button then works as a Stop button
  var STOP_ICON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';
  function updateSend() {
    humanBtn.disabled = busy;
    if (busy && stopFn) {
      send.disabled = false; send.type = "button"; send.innerHTML = STOP_ICON; send.setAttribute("aria-label", T.stop);
    } else {
      send.type = "submit"; send.innerHTML = ICON.send; send.setAttribute("aria-label", T.send);
      send.disabled = busy || !input.value.trim();
    }
  }
  send.addEventListener("click", function () { if (busy && stopFn) stopFn(); });
  function grow() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
    updateSend();
  }

  function plainAsk(text) {
    return fetch(API + "/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message: text })
    }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); });
  }
  function streamAsk(text, onText, onReset, signal, onSources) {
    return fetch(API + "/api/chat/stream", {
      method: "POST", headers: { "Content-Type": "application/json" }, signal: signal,
      body: JSON.stringify({ session_id: sessionId, message: text })
    }).then(function (r) {
      var type = r.headers.get("Content-Type") || "";
      if (type.indexOf("text/event-stream") !== 0 || !r.body) {  // an error from the server comes as plain JSON
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      }
      var reader = r.body.getReader(), dec = new TextDecoder("utf-8"), buf = "", result = null;
      function pump() {
        return reader.read().then(function (chunk) {
          if (chunk.done) return result || { ok: false, d: {} };  // ended without a final result: a failure
          buf += dec.decode(chunk.value, { stream: true });
          if (buf.length > 1000000) { reader.cancel(); return { ok: false, d: {} }; }
          var parts = buf.split("\n\n"); buf = parts.pop();
          parts.forEach(function (p) {
            if (p.indexOf("data: ") !== 0) return;
            var ev; try { ev = JSON.parse(p.slice(6)); } catch (e) { return; }
            if (typeof ev.session_id === "string") sessionId = ev.session_id;
            if (typeof ev.t === "string") onText(ev.t);
            else if (Array.isArray(ev.src)) { if (onSources) onSources(cleanSources(ev.src)); }
            else if (ev.reset) onReset();
            else if (ev.done && typeof ev.done === "object") result = { ok: true, d: ev.done };
          });
          return pump();
        });
      }
      return pump();
    });
  }
  input.addEventListener("input", function () { setStatus(""); grow(); });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); if (form.requestSubmit) form.requestSubmit(); }
  });
  var consent = el("div", "fy-consent");
  consent.hidden = true;
  consent.setAttribute("role", "alertdialog");
  var consentText = el("p", "", T.voiceConsent);
  var consentYes = el("button", "", T.allow), consentNo = el("button", "fy-plain", T.notNow);
  consentYes.type = consentNo.type = "button";
  consent.appendChild(consentText); consent.appendChild(consentYes); consent.appendChild(consentNo);
  form.appendChild(input); form.appendChild(mic); form.appendChild(send);
  panel.appendChild(head); panel.appendChild(log); panel.appendChild(status); panel.appendChild(consent); panel.appendChild(form);
  document.body.appendChild(btn); document.body.appendChild(panel);

  function setStatus(msg, bad) {
    status.textContent = msg || "";
    status.className = "fy-status" + (bad ? " fy-bad" : "");
  }

  var note = el("div", "fy-note", T.note);
  var privacyA = null;
  function addPrivacy(u) {  // one link, https only (from the embed code or the server's settings)
    if (privacyA || typeof u !== "string" || !HTTPS.test(u)) return;
    privacyA = el("a", "", T.privacy); privacyA.href = u; privacyA.target = "_blank"; privacyA.rel = "noopener noreferrer";
    note.appendChild(privacyA);
  }
  addPrivacy(PRIVACY);
  log.appendChild(note);
  add(T.hi, "bot");

  function add(text, who) {
    var m = el("div", "fy-msg " + (who === "me" ? "fy-me" : "fy-bot"), text);
    log.appendChild(m);
    log.scrollTop = log.scrollHeight;
    return m;
  }

  /* ---------- voice output (speechSynthesis) ---------- */
  var synth = window.speechSynthesis || null;
  var autoRead = false;
  try { autoRead = REMEMBER && localStorage.getItem(READ_KEY) === "1"; } catch (e) {}
  var speakingText = "", speakToken = 0;
  function locale() { return lang === "de" ? "de-DE" : "en-US"; }
  function plain(s) {
    return s.replace(/https?:\/\/\S+/g, "").replace(/[*`#]/g, "").replace(/^\s*[-•]\s+/gm, "");
  }
  function chunks(s) {
    var parts = s.match(/[^.!?\n]+[.!?]*\s*/g) || [], out = [], cur = "";
    parts.forEach(function (p) {
      p = p.trim();
      if (!p) return;
      if (cur && (cur + " " + p).length > 180) { out.push(cur); cur = p; } else cur = cur ? cur + " " + p : p;
    });
    if (cur) out.push(cur);
    return out;
  }
  function syncListen() {
    Array.prototype.forEach.call(log.querySelectorAll(".fy-listen"), function (b) {
      b.textContent = b._txt === speakingText ? T.stop : T.listen;
    });
  }
  function stopSpeak() {
    speakToken++; speakingText = "";
    if (synth) synth.cancel();
    syncListen();
  }
  function speak(text) {
    if (!synth) return;
    stopSpeak();
    var token = speakToken, queue = chunks(plain(text));
    if (!queue.length) return;
    speakingText = text; syncListen();
    var voice = null, vs = synth.getVoices() || [];
    for (var i = 0; i < vs.length; i++) {
      if (vs[i].lang && vs[i].lang.toLowerCase().indexOf(lang) === 0) { voice = vs[i]; if (vs[i].localService) break; }
    }
    (function next() {
      if (token !== speakToken) return;
      var part = queue.shift();
      if (!part) { speakingText = ""; syncListen(); return; }
      var u = new SpeechSynthesisUtterance(part);
      u.lang = locale(); if (voice) u.voice = voice;
      u.onend = next;
      u.onerror = function () { if (token === speakToken) { speakingText = ""; syncListen(); } };
      synth.speak(u);
    })();
  }
  function updateSpeakBtn() {
    speakBtn.hidden = !synth;
    speakBtn.setAttribute("aria-pressed", autoRead ? "true" : "false");
  }
  speakBtn.addEventListener("click", function () {
    autoRead = !autoRead;
    try { if (REMEMBER) localStorage.setItem(READ_KEY, autoRead ? "1" : "0"); } catch (e) {}
    if (!autoRead) stopSpeak();
    updateSpeakBtn();
  });
  updateSpeakBtn();

  /* ---------- voice input (SpeechRecognition) ---------- */
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition || null;
  var rec = null, listening = false;
  function updateMic() {
    mic.hidden = !SR;
    mic.setAttribute("aria-pressed", listening ? "true" : "false");
    var label = listening ? T.micStop : T.mic;
    mic.setAttribute("aria-label", label); mic.title = label;
    input.placeholder = listening ? T.listening : T.placeholder;
  }
  function stopMic() {
    if (rec) { try { rec.abort(); } catch (e) {} }
    rec = null; listening = false;
    updateMic();
  }
  function startMic() {
    if (!SR || busy) return;
    stopSpeak();
    var base = input.value ? input.value.replace(/\s+$/, "") + " " : "";
    var r = new SR();
    r.lang = locale(); r.interimResults = true; r.continuous = false; r.maxAlternatives = 1;
    r.onresult = function (e) {
      var s = "";
      for (var i = 0; i < e.results.length; i++) s += e.results[i][0].transcript;
      input.value = (base + s).slice(0, 1000);
      grow();
    };
    r.onerror = function (e) {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") setStatus(T.micDenied, true);
      else if (e.error !== "no-speech" && e.error !== "aborted") setStatus(T.micFail, true);
    };
    r.onend = function () {
      if (rec !== r) return;
      rec = null; listening = false; updateMic();
      if (status.textContent === T.micNote) setStatus("");
      input.focus();
    };
    rec = r; listening = true;
    try { r.start(); } catch (e) { rec = null; listening = false; setStatus(T.micFail, true); }
    updateMic();
    if (listening) setStatus(T.micNote);
  }
  /* Voice input needs a yes first: the audio goes to the browser's speech service (a third party). */
  var VOICE_OK = "faiyke_voice_ok", afterConsent = null;
  var voiceYes = false;
  function voiceAllowed() { try { return voiceYes || (REMEMBER && localStorage.getItem(VOICE_OK) === "1"); } catch (e) { return voiceYes; } }
  function hideConsent() { consent.hidden = true; afterConsent = null; }
  consentYes.addEventListener("click", function () {
    voiceYes = true;
    try { if (REMEMBER) localStorage.setItem(VOICE_OK, "1"); } catch (e) {}
    var go = afterConsent; hideConsent();
    if (go) go();
  });
  consentNo.addEventListener("click", function () { hideConsent(); input.focus(); });
  panel.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if (busy && stopFn) { stopFn(); return; }  // Esc stops a running answer, as the Stop button does
    hideConsent();
  });
  mic.addEventListener("click", function () {
    if (listening) { rec.stop(); return; }
    if (voiceAllowed()) { startMic(); return; }
    afterConsent = startMic; consent.hidden = false; consentYes.focus();
  });
  updateMic();

  /* ---------- erasure: delete this chat on the server and in this browser ---------- */
  var delArmed = false, delTimer = null;
  function disarmDel() {
    delArmed = false; clearTimeout(delTimer);
    delBtn.className = "fy-del"; delBtn.innerHTML = ICON.trash;
    delBtn.setAttribute("aria-label", T.del); delBtn.title = T.del;
  }
  delBtn.addEventListener("click", function () {
    if (busy) return;
    if (!delArmed) {  // two clicks, so a stray click cannot delete the chat
      delArmed = true; delBtn.className = "fy-del fy-sure"; delBtn.textContent = T.delSure;
      delBtn.setAttribute("aria-label", T.delSure);
      delTimer = setTimeout(disarmDel, 4000);
      return;
    }
    var sid = sessionId;
    if (sid) {
      try {
        fetch(API + "/api/forget", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: sid })
        }).catch(function () {});
      } catch (e) {}
    }
    sessionId = null;
    try { sessionStorage.removeItem(KEY); localStorage.removeItem(VOICE_OK); localStorage.removeItem(READ_KEY); } catch (e) {}
    autoRead = false; updateSpeakBtn();
    stopSpeak(); stopMic(); hideConsent(); setStatus("");
    log.textContent = ""; log.appendChild(note); add(T.hi, "bot");
    disarmDel();
  });

  /* ---------- feedback ---------- */
  function sendFeedback(fid, rating, comment) {
    var body = { session_id: sessionId, fid: fid, rating: rating };
    if (comment) body.comment = comment;
    try {
      fetch(API + "/api/feedback", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
      }).catch(function () {});
    } catch (e) {}
  }
  /* Follow-up questions under the latest answer. The server has already checked them; they are checked again here
     and only ever shown as plain text. A click sends the text like anything the customer types. */
  function makeChips(list) {
    if (!Array.isArray(list)) return null;
    var items = list.filter(function (s) { return typeof s === "string" && s.length >= 3 && s.length <= 90; }).slice(0, 3);
    if (!items.length) return null;
    var box = el("div", "fy-chips");
    box.setAttribute("role", "group"); box.setAttribute("aria-label", T.suggested);
    items.forEach(function (s) {
      var b = el("button", "", s);
      b.type = "button";
      b.addEventListener("click", function () { if (busy) return; input.value = s; grow(); if (form.requestSubmit) form.requestSubmit(); });
      box.appendChild(b);
    });
    return box;
  }
  function clearChips() {
    Array.prototype.forEach.call(log.querySelectorAll(".fy-chips"), function (n) { n.parentNode.removeChild(n); });
  }

  function makeTools(text, fid, d) {
    var box = el("div", "fy-tools");
    var unsure = !!(d && d.unsure === true);
    if (unsure) box.appendChild(unsureBox());  // "not sure" is its own state, with a way forward
    else { var srcs = sourceList(cleanSources(d && d.sources)); if (srcs) box.appendChild(srcs); }
    var bar = el("div", "fy-bar");
    box.appendChild(bar);
    if (synth) {
      var ls = el("button", "fy-listen", T.listen);
      ls.type = "button"; ls._txt = text;
      ls.addEventListener("click", function () { if (speakingText === text) stopSpeak(); else speak(text); });
      bar.appendChild(ls);
    }
    if (fid && sessionId) {
      var vote = "", upB = el("button"), downB = el("button"), asked = false;
      upB.type = downB.type = "button";
      upB.innerHTML = ICON.up; downB.innerHTML = ICON.down;
      upB.setAttribute("aria-label", T.good); upB.title = T.good;
      downB.setAttribute("aria-label", T.bad); downB.title = T.bad;
      upB.setAttribute("aria-pressed", "false"); downB.setAttribute("aria-pressed", "false");
      var thanks = el("span", "fy-thanks");
      thanks.setAttribute("aria-live", "polite");
      var rate = function (r) {
        if (vote === r) return;
        vote = r;
        upB.setAttribute("aria-pressed", r === "up" ? "true" : "false");
        downB.setAttribute("aria-pressed", r === "down" ? "true" : "false");
        thanks.textContent = T.thanks;
        sendFeedback(fid, r);
        if (r === "down" && !asked) {
          asked = true;
          var wrap = el("div", "fy-whybox");
          var reasons = el("div", "fy-reasons");
          reasons.setAttribute("role", "group"); reasons.setAttribute("aria-label", T.bad);
          T.reasons.forEach(function (r) {
            var chip = el("button", "", r);
            chip.type = "button";
            chip.addEventListener("click", function () {  // one tap is enough: the reason is the feedback
              sendFeedback(fid, "down", r);
              if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
            });
            reasons.appendChild(chip);
          });
          var why = el("form", "fy-why");
          var inp = el("input");
          inp.type = "text"; inp.maxLength = 300; inp.placeholder = T.whyPh; inp.setAttribute("aria-label", T.whyPh);
          var go = el("button", "", T.whySend); go.type = "submit";
          why.appendChild(inp); why.appendChild(go);
          why.addEventListener("submit", function (e) {
            e.preventDefault();
            var v = inp.value.trim();
            if (v) sendFeedback(fid, "down", v);
            if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
          });
          wrap.appendChild(reasons); wrap.appendChild(why);
          box.appendChild(wrap);
        }
      };
      upB.addEventListener("click", function () { rate("up"); });
      downB.addEventListener("click", function () { rate("down"); });
      bar.appendChild(upB); bar.appendChild(downB); bar.appendChild(thanks);
    }
    return box;
  }

  btn.addEventListener("click", function () {
    var open = panel.classList.toggle("fy-open");
    btn.setAttribute("aria-label", open ? T.close : T.open);
    if (open) input.focus(); else { stopSpeak(); stopMic(); hideConsent(); setStatus(""); }
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text || busy) return;
    stopSpeak(); stopMic(); setStatus(""); clearChips();
    input.value = ""; busy = true; grow();
    add(text, "me");
    var wait = add("", "bot");
    function showWork(text) { wait.textContent = ""; wait.appendChild(workEl(text)); }
    showWork(T.thinking);
    log.setAttribute("aria-busy", "true");  // screen readers wait for the finished answer

    var acc = "", frame = 0, ctl = null, job;
    function paint() {  // at most once per frame; plain text only, so nothing streamed can become markup
      frame = 0;
      if (acc) wait.textContent = acc;
      log.scrollTop = log.scrollHeight;
    }
    function onText(piece) { acc += piece; if (!frame) frame = requestAnimationFrame(paint); }
    function onReset() { acc = ""; showWork(T.thinking); }
    function onSources(list) { if (!acc) showWork(checkingText(list)); }  // before the answer starts: what is being read

    if (CAN_STREAM) {
      ctl = window.AbortController ? new AbortController() : null;
      if (ctl) { stopFn = function () { ctl.abort(); }; updateSend(); }
      job = streamAsk(text, onText, onReset, ctl && ctl.signal, onSources);
    } else {
      job = plainAsk(text);
    }
    job.then(function (res) {
      if (res.d.session_id) {
        sessionId = res.d.session_id;
        try { sessionStorage.setItem(KEY, sessionId); } catch (e) {}
      }
      var good = typeof res.d.reply === "string" && res.d.reply !== "";
      var reply = good ? res.d.reply : (typeof res.d.error === "string" && res.d.error) || T.fail;
      wait.textContent = reply;
      if (!good) wait.className += " fy-err";
      if (res.d.book === true && bookingUrl) {
        var cta = el("a", "fy-cta", T.book);
        cta.href = bookingUrl; cta.target = "_blank"; cta.rel = "noopener noreferrer";
        wait.appendChild(el("br"));
        wait.appendChild(cta);
      }
      if (good) {
        var fid = /^[0-9a-f]{16}$/.test(res.d.fid || "") ? res.d.fid : "";
        log.appendChild(makeTools(reply, fid, res.d));
        var chips = makeChips(res.d.next);
        if (chips) log.appendChild(chips);
        if (autoRead) speak(reply);
      }
    }).catch(function () {
      if (ctl && ctl.signal.aborted) {  // the customer pressed Stop: keep what had arrived
        wait.textContent = acc.trim() || T.stopped;
      } else {
        wait.textContent = T.offline;
        wait.className += " fy-err";
      }
    }).then(function () {
      if (frame) cancelAnimationFrame(frame);
      stopFn = null; log.removeAttribute("aria-busy");
      busy = false; grow(); log.scrollTop = log.scrollHeight; input.focus();
    });
  });
})();
