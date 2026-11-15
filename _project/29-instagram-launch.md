# 29 — Instagram launch for @moodily_official

**Status:** creative ready, nothing posted. Posting is a human action and stays with the owner.
**Assets:** `assets/img/social/*.svg` (1080×1350) — open `assets/img/social/index.html` to see them all.
**Regenerate:** `python3 scripts/social_posts.py` · **Verify:** `node scripts/check_social.mjs`

---

## Why the posts are generated, not designed

Every number on these cards is read at build time from `src/data/evidence.json`, and every price
and deliverable from `src/data/services.json` — the same registries the website publishes from.
A statistic therefore cannot drift between moodily.in and Instagram, and a figure that the site's
evidence rules would reject cannot reach the feed either. When a price changes, the posts are
regenerated; nobody retypes a number into a design tool.

Each statistic card prints its **source and year on the image**, not only in the caption. Captions
get truncated, re-shared and screenshotted; the claim and its provenance must travel together.

## What is deliberately absent

- **No fabricated scarcity.** No "only 2 slots left" unless the slot count in `pricing.json` says so.
- **No invented results.** No "we grew a client 300%". The before/after post compares an *incomplete
  listing to a complete one* — a thing we control — not a results graph we cannot evidence.
- **No "90% of people search near me" family of stats.** Researched, found to have no traceable
  primary source, excluded from the site, and excluded here for the same reason.
- **No ranking promises.** Post 01 says so out loud, as the pinned post.

---

## Posting order and captions

Post in this order. Instagram fills the grid newest-first, so after all nine are up the grid reads
bottom-to-top in this sequence — 01 ends up bottom-left, which is where a new visitor's eye lands
last and where the "what we never do" promise does the most work as a closing argument.

**Cadence:** 3 posts a week (Tue / Thu / Sat, ~7–9pm IST) for three weeks. Then reassess with real
numbers instead of a plan.

**Every caption ends with the same two lines.** Consistency is what makes a CTA get remembered:

> मुफ़्त Digital Audit चाहिए? DM करिए या WhatsApp कीजिए — moodily.in
> कोई रैंक की guarantee नहीं, कोई छुपी fees नहीं. Scope और price लिखित में.

---

### 01 — `01-what-we-never-do.svg` · PIN THIS POST

> **जो हम कभी नहीं करेंगे.**
>
> ज़्यादातर digital agency आपको वो बताती है जो आप सुनना चाहते हैं. हम उल्टा शुरू करते हैं — पहले
> वो, जो हम कभी नहीं करेंगे:
>
> ✕ Google पर पहले नंबर की guarantee. कोई भी ईमानदार agency यह नहीं दे सकती — ranking Google तय
> करता है, हम नहीं.
> ✕ नकली या ख़रीदे हुए reviews. एक भी नहीं.
> ✕ आपके accounts की ownership. आपका Google Business Profile, आपका WhatsApp, आपका domain — सब
> आपके ही नाम पर. हम सिर्फ़ manager access से काम करते हैं.
> ✕ छुपी हुई fees. हर काम का scope और price पहले, लिखित में.
>
> जो करेंगे: आपकी जानकारी Google, WhatsApp और website पर पूरी, सही और अपडेटेड रखना. बस यही.

*Hashtags:* #localbusinessindia #googlebusinessprofile #whatsappbusiness #smallbusinessindia #digitalindia

---

### 02 — `02-google-connections.svg`

> हर महीने भारत में **90 करोड़+** बार लोग Google Search और Maps के ज़रिए businesses तक पहुँचते हैं.
>
> Google के अपने आँकड़े कहते हैं कि 3.5 करोड़ से ज़्यादा Indian businesses पहले से Search और Maps
> पर हैं.
>
> सवाल ये नहीं कि "online जाना चाहिए या नहीं". सवाल ये है कि जब कोई आपके इलाक़े में आपकी जैसी दुकान
> ढूँढता है — आप उस list में हैं या नहीं.
>
> Source: Google India official blog, 2024.

---

### 03 — `03-free-audit.svg`

> पैसे की बात बाद में. पहले ये देखिए कि आपका business अभी online दिखता कैसा है.
>
> 1️⃣ आप WhatsApp पर बताइए — business क्या है, कहाँ है
> 2️⃣ हम आपका Google, WhatsApp, website और social देखते हैं
> 3️⃣ 3 सबसे ज़रूरी सुधार बताते हैं — प्राथमिकता के साथ
> 4️⃣ हर सुधार पर साफ़ label: ये आप ख़ुद कर सकते हैं / इसमें हम मदद करें
>
> मुफ़्त है. उसके बाद कुछ ख़रीदना ज़रूरी नहीं — और हम पीछे नहीं पड़ेंगे.

---

### 04 — `04-health-reviews.svg`

> **36%** भारतीय doctor, dentist या clinic चुनते समय online reviews देखते हैं — 17 देशों में सबसे
> ज़्यादा. उन 17 markets का औसत सिर्फ़ 20% है.
>
> मतलब: clinic, dental practice, physiotherapy centre या medical store चला रहे हैं तो मरीज़ आपके
> दरवाज़े तक पहुँचने से पहले आपके बारे में पढ़ चुका होता है.
>
> अगर वहाँ पुराना नंबर, ग़लत timing या कोई फ़ोटो नहीं — तो पहली छाप वही बन जाती है.
>
> Source: YouGov, 2022 (18,000+ लोग, 17 markets).

---

### 05 — `05-listing-before-after.svg`

> एक ही दुकान. दो नतीजे.
>
> अधूरी listing: समय नहीं लिखा, फ़ोटो पुरानी, नंबर बदल गया, रास्ता गलत. ग्राहक 10 सेकंड में अगली
> दुकान पर चला जाता है — आपको पता भी नहीं चलता.
>
> पूरी listing: समय, फ़ोटो, services, सही रास्ता. Call, Directions और WhatsApp एक tap पर.
>
> हम ये guarantee नहीं देते कि आप पहले नंबर पर आएँगे. हम ये करते हैं कि जब कोई आप तक पहुँचे, उसे
> पूरी और सही जानकारी मिले.

---

### 06 — `06-google-quick-fix.svg`

> आपका Google Business Profile पहले से है, पर अधूरा है? **₹1,999 में Quick Fix.**
>
> पूरी जाँच · category, services, description, समय और attributes सुधार · आपकी दी हुई 10 फ़ोटो तक
> upload और arrange · Call/WhatsApp/website links ठीक करना · Google review QR code.
>
> जो हम नहीं कर सकते, वो भी साफ़: verification Google ख़ुद आपके नंबर/पते पर करता है — उसका समय हम
> तय नहीं कर सकते. और rank की कोई guarantee नहीं.
>
> Fixed price. Scope लिखित में. कोई surprise bill नहीं.

---

### 07 — `07-review-habit.svg`

> जो लोग Google पर किसी दुकान का पता या नंबर देखते हैं, उनमें से **34%** हमेशा या ज़्यादातर बार
> reviews भी पढ़ते हैं. (12% "हमेशा" + 22% "ज़्यादातर बार".) कभी-न-कभी पढ़ने वाले 88% हैं.
>
> यानी आपकी listing सिर्फ़ एक फ़ोन नंबर नहीं है. वो वो जगह है जहाँ ग्राहक तय करता है कि आना है या नहीं.
>
> Source: LocalCircles, 2022 — 56,000+ जवाब, 357 ज़िले (20% tier 3/4 और ग्रामीण).

---

### 08 — `08-whatsapp-basic.svg`

> दिन में कितनी बार आप वही जवाब टाइप करते हैं? "Rate list भेज दीजिए", "आप कहाँ हैं?", "कितने बजे
> तक खुला है?"
>
> **₹1,499 में WhatsApp Business Basic:** profile, catalogue में 10 items, greeting और away
> message, 5 quick replies, labels (New enquiry / Order / Paid / Follow-up), और chat link + QR.
>
> एक बार set हो जाए तो वही जवाब एक tap में चला जाता है — और कोई enquiry बीच में खोती नहीं.

---

### 09 — `09-honest-reviews.svg`

> ये post हमारे ही काम के ख़िलाफ़ जाता है. फिर भी कर रहे हैं.
>
> सिर्फ़ **3%** भारतीयों को Google reviews पर ऊँचा भरोसा है. 45% को लगता है reviews सही नहीं
> होतीं, और 37% को लगता है वे positively biased हैं.
>
> (LocalCircles 2022, 56,000+ जवाब, 357 ज़िलों से.)
>
> इसलिए नकली review ख़रीदना बेकार है — लोग पहले से शक कर रहे हैं. जो काम करता है वो ये है: असली
> जानकारी, पूरी, और अपडेटेड. Moodily न fake review लिखता है, न ख़रीदता है.

---

## Profile setup (do this before post 01)

**Bio (150 char limit):**
> छोटे business को Google, WhatsApp और website पर सही से दिखाना.
> Fixed price · scope लिखित में · रैंक की कोई guarantee नहीं
> 👇 मुफ़्त Digital Audit

**Link:** `moodily.in` — add `?utm_source=instagram&utm_medium=bio` so the traffic is attributable
in GA4. Without the parameter you will not be able to tell Instagram traffic from direct.

**Highlights** (create after there are stories to save): `कीमतें` · `काम` · `सवाल-जवाब` · `हम कौन`

**Name field:** `Moodily — Local Business Digital` (the name field is searchable on Instagram; the
handle alone is not enough for anyone to find you by what you do).

---

## Honest expectation setting

Edoogate, the account this was modelled on, has roughly a dozen polished carousels and **73
followers**. Good creative is necessary and nowhere near sufficient. Instagram will not, on its
own, bring a Rasra shopkeeper to moodily.in.

Treat these nine posts as **sales collateral that happens to live on Instagram**: something to send
a prospect in DM, link from a WhatsApp Business catalogue, and show as proof the business is real
and has a point of view. Measure them that way.

**What to actually measure after three weeks** (Instagram Insights + GA4):
- profile visits, and link clicks from bio — the only numbers that connect to the site
- DMs that mention a post
- which of the three post types (stat / service / promise) gets saved and shared, not liked

If link clicks after nine posts are in single digits, the channel is not the problem to solve —
distribution is, and that argues for the directory idea, local WhatsApp groups and Google Business
posts over more Instagram creative.
