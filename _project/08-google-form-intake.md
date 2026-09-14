# 08 — Google Form intake, Sheets CRM, catalogue & deployment

## A. Current state (audited 2026-09-14)

- **Contact form:** `/contact/` used a custom form (`FORM_TEMPLATE` in `build.py`) with `form.endpoint` empty. Submissions were not stored anywhere; the visitor had to tap "send" on WhatsApp on the thank-you page, otherwise the lead was lost.
- **CTA links:** every service CTA links to `/contact/?service=<id>`, with `&offer=founding-10` for offer CTAs.
- **Catalogue:** 8 service lines (local business, medical, education, professionals, creators, research, knowledge-to-product, AI) and no design, presentation, invitation or social services.

## B. Files changed

| File | Change |
|---|---|
| `src/data/intake.json` | **New.** Google Form URL, entry IDs, 14 form categories with optional prefilled URLs, service→category map, per-service overrides |
| `src/data/catalogue.json` | **New.** 8 outcomes, 13 groups (items, formats, price_service, samples) |
| `src/data/services.json` | +13 packages (presentations ×3, invitations ×3, business documents/print ×4, social ×3); **draft starting prices** flagged `_todo_price` |
| `src/data/faqs.json` | +4 FAQ sets |
| `build.py` | Components `intake`, `outcomes`, `catalogue`, `catalogue-group`, `revision-policy`, `formats`; validation; nav; event names |
| `src/pages/contact/index.html` | Branded wrapper around the Google Form (fallback form kept while `form_url` is empty) |
| `src/pages/services/{presentation-design,invitation-design,business-documents,social-media-design}.html` | **New** landing pages |
| `src/pages/index.html`, `services/index.html`, 7 existing service pages | Outcome cards, filterable catalogue, formats & real samples sections |
| `assets/js/site.js`, `assets/css/site.css` | Intake prefill logic, filters, auto-tracking, styles |
| `src/pages/terms.html`, `privacy.html` | Revision policy; Google Forms data note |

## C. How the flow works

```
Any CTA  →  /contact/?service=presentation-content-design[&offer=founding-10]
            ├─ "आपने चुना": package name, form category, starting/offer price
            ├─ [Continue Requirement Form →]  opens Google Form in a new tab, pre-selected:
            │     1. intake.json service_prefill_urls[service]          (if pasted)
            │     2. else categories[category].prefill_url              (if pasted)
            │     3. else form_url + entry_ids (category, package, offer code)
            │     4. else plain form_url
            ├─ WhatsApp alternative (message prefilled with the package)
            └─ form_url empty → built-in fallback form (nothing breaks before setup)
Google Form → Google Sheet (responses) → owner columns = CRM
```

Why a new tab rather than an iframe: embedded Google Forms get cut off in height on phones, scroll inside the page, hide Google's own validation, and load ~1 MB before the visitor chooses to fill the form. A new tab is faster and also works when third-party cookies are blocked.

---

## 1. Build the Google Form (owner, ~40 minutes)

forms.google.com → Blank form. Title: **Moodily — Requirement Form**. Description: *"3–5 मिनट। आपकी service के हिसाब से सवाल आएँगे। Answers सिर्फ़ आपकी requirement का जवाब देने के लिए।"*

**Settings:**
- Responses → *Collect email addresses*: **Do not collect** (email is an optional question).
- *Limit to 1 response*: **off**, so no sign-in is needed.
- Do **not** add File upload questions: they force a Google sign-in. Use a "Reference/source link" question instead.
- Presentation → confirmation message: *"धन्यवाद! 1 working day में WhatsApp/email पर जवाब देंगे। जल्दी बात करनी हो: wa.me/919354123255"*

Use **Sections**. Section C's category question sends each person only to their section.

### Section A — Basic details
| Question | Type | Required |
|---|---|---|
| Name | Short answer | ✔ |
| WhatsApp | Short answer (Response validation → Regular expression → Matches `^[+0-9 ]{10,15}$`) | ✔ |
| Email | Short answer (validation: Text → Email) | |
| City / Country | Short answer | ✔ |
| Preferred language | Multiple choice: Hindi / English / Hinglish / Both | ✔ |

### Section B — Role
| Question | Type | Options |
|---|---|---|
| आप कौन हैं? / Role * | Multiple choice | Individual · Student · Teacher · School · Coaching Institute · Creator · Local Business · Medical Store · Clinic · Professional · Startup · Agency · Company · Other |

### Section C — Service category (branching)
| Question | Type | Notes |
|---|---|---|
| Service category * | Multiple choice, **⋮ → Go to section based on answer** | Options **exactly** (the website pre-fills these labels): Invitation / Personal Design · Business Design · Presentation / PPT · Social Media · Creator Content · Educational Material · Exam / PYQ Material · Research · Knowledge-to-Product · Website / Google Business · AI Workflow / Automation · Professional Authority · Print-ready Design · Custom Digital Work |
| Selected package (website से auto-filled) | Short answer, optional | Filled automatically, e.g. "Presentation — Content + Design". Description: *"अगर पता नहीं तो खाली छोड़ें"* |
| Offer code | Short answer, optional | Auto-filled with `founding-10` from offer CTAs |

**Branching map** (every service section ends with "Continue to section → Final details"):

| Answer | Go to section |
|---|---|
| Invitation / Personal Design | D1 Invitation |
| Presentation / PPT | D2 Presentation |
| Business Design, Print-ready Design | D3 Business / Document |
| Educational Material, Exam / PYQ Material | D4 Education |
| Research | D5 Research |
| Knowledge-to-Product | D6 Knowledge-to-Product |
| AI Workflow / Automation | D7 AI Workflow |
| Website / Google Business | D8 Local Business |
| Social Media, Creator Content, Professional Authority, Custom Digital Work | D9 Design & content details |

### D1 — Invitation
- Event type* (MC: Wedding, Birthday, Anniversary, Baby shower, Housewarming, Save-the-date, Festival/greeting, Other)
- Digital or print?* (MC: Digital / Print / Both)
- Static or animated?* (MC: Static / Animated GIF / Video / Not sure)
- Invitation language (checkboxes: Hindi, English, Other)
- Number of variants (MC: 1 / 2–3 / 4+)
- Event date / deadline (Date)
- Reference link (Short answer)

### D2 — Presentation
- Presentation type* (MC: School, College, Research, Business, Sales, Pitch/Investor, Training/Webinar, Conference, Product, Thesis/Dissertation, Company profile, Other)
- Number of slides* (MC: up to 10 / 11–15 / 16–25 / 25+)
- Level* (MC: Design only — content ready / Content improvement + design / Research + writing + design)
- Audience (Short answer)
- Deadline (Date)
- Editable/source file required? (MC: PPTX / Google Slides / Canva / PDF only)

### D3 — Business / Document / Print
- Asset required* (Checkboxes: Invoice, Quotation, Estimate, Receipt, Letterhead, Proposal, Company profile, Rate card/Price list, Brochure, Catalogue, Visiting card, Digital visiting card, Email signature, Certificate, QR card, Flyer/Poster, Menu, Banner/Standee, Sticker/Label, Packaging concept, Book/eBook cover, Other)
- Logo available?* (MC: Yes / No / Needs refresh)
- Brand colours? (MC: Yes / No / Suggest)
- Business information ready? (MC: Yes / Partly / No)
- Digital or print-ready?* (MC: Digital / Print-ready / Both)
- Editable version required? (MC: Word/Docs/Sheets / Canva / Not needed)
- Help text: *"GSTIN/tax details आप देंगे। Moodily tax/accounting compliance advice नहीं देता।"*

### D4 — Education / PYQ
- Class / exam* (Short answer)
- Subject* (Short answer)
- Topic / chapters (Paragraph)
- Asset type* (Checkboxes: Notes/PDF module, PPT, Worksheets, Tests/Mock tests, Question bank, PYQ analysis, Answer explanations, Flashcards/Quizzes, Mind maps, Revision plan, Lesson plans/Teacher resources, Infographics)
- Source / syllabus (Short answer, link)
- Use* (MC: Individual / Institution (white-label))
- Deadline (Date)
- Help text: *"Moodily किसी exam body से affiliated नहीं है; PYQ analysis trends दिखाता है, guaranteed questions नहीं।"*

### D5 — Research
- Research question* (Paragraph)
- Industry / topic* (Short answer)
- Business purpose (MC: Launch decision, Investment/partnership, Content/strategy, Academic, Other)
- Research depth (MC: Quick scan / Standard brief / Deep report)
- Required final formats (Checkboxes: PDF report, PPT, Sheet/table, Executive summary)
- Deadline (Date)

### D6 — Knowledge-to-Product
- Input type* (Checkboxes: Book, Document/notes, Video, Audio/voice notes, Research, Course material, Presentations)
- Approximate size (Short answer, e.g. "120 pages / 3 hours")
- Desired outputs* (Checkboxes: eBook, Course, PPT, Quiz, Mind map, Flashcards, Worksheets, Video scripts, Social posts, Newsletter, FAQ library, Lead magnet, Training manual)
- Audience (Short answer)
- Deadline (Date)

### D7 — AI Workflow
- Repetitive task* (Paragraph)
- Current tools (Checkboxes: Google Sheets, Gmail, WhatsApp, Excel, CRM, Website forms, Notion, Other)
- Frequency (MC: Many times a day / Daily / Weekly / Monthly)
- Desired output (Paragraph)
- Where should a human approve? (Short answer)
- Estimated volume (Short answer, e.g. "50 leads/day")
- Deadline (Date)
- Help text: *"Health/ID/payment data वाले workflows अलग review के बाद ही।"*

### D8 — Local Business / Website / Google
- Business type* (Short answer)
- Google Business Profile status* (MC: Not created / Created, not verified / Verified / Don't know)
- Website status (MC: None / Have one / Needs redesign)
- WhatsApp Business status (MC: Not using / Using normal WhatsApp / Using WhatsApp Business)
- Main customer problem* (MC: Customers can't find us, Few enquiries, Too much time on WhatsApp, Few reviews, No online catalogue, Other)
- Desired service (Checkboxes: Google profile, WhatsApp Business, Website/landing page, QR/visiting card, Reviews system, Monthly management, Medical store workflow, Not sure)

### D9 — Design & content details (Social, Creator, Professional, Custom)
- What do you need?* (Paragraph)
- Platforms / where it will be used (Checkboxes: Instagram, Facebook, LinkedIn, YouTube, WhatsApp, Website, Print, Other)
- Quantity (Short answer)
- Reference / existing profile link (Short answer)

### Section F — Final details (everyone)
| Question | Type | Options |
|---|---|---|
| Primary goal * | Multiple choice | More customers · More sales · Save time · Better presentation · Digital presence · Learning · Content creation · Automation · Other |
| Deadline * | Multiple choice | 24–48 hours · 3–5 days · 1 week · 2 weeks · Flexible |
| Budget * | Multiple choice | Under ₹1,000 · ₹1,000–₹3,000 · ₹3,000–₹7,500 · ₹7,500–₹15,000 · ₹15,000–₹50,000 · ₹50,000+ · Need recommendation |
| Reference / source link | Short answer | |
| Message / detailed brief | Paragraph | |
| Consent * | Checkbox (1 option, required) | I agree that Moodily may contact me via WhatsApp/email regarding this enquiry. |

Put this in the Section F description: **"Do not submit prescriptions, Aadhaar, PAN, medical records, passwords, banking credentials or other sensitive personal information."**

## 2. Connect it to the website (owner, ~10 minutes)

1. **Send → 🔗 link → untick "Shorten URL"** → copy (ends in `/viewform`) → `src/data/intake.json → form_url`.
2. **⋮ → Get pre-filled link**:
   - In *Service category* choose any option.
   - Type `PKG` in *Selected package* and `OFFER` in *Offer code*.
   - Click **Get link → Copy link**. It looks like `…/viewform?usp=pp_url&entry.111111=Presentation+/+PPT&entry.222222=PKG&entry.333333=OFFER`.
   - Copy the three numbers into `entry_ids`: `service_category` = `entry.111111`, `sub_service` = `entry.222222`, `offer_code` = `entry.333333`.
3. That's enough: every CTA now pre-selects the right category, package and offer. `categories.*.prefill_url` and `service_prefill_urls` are optional overrides for special cases.
4. **Keep option labels exactly as listed in section C.** Google only pre-selects a choice when the text matches character for character.
5. `python3 build.py && python3 tests/check_site.py`, then commit and push.

The build rejects `forms.gle` short links (they drop prefill values) and malformed entry IDs. Until `form_url` is set, `/contact/` shows the built-in form, so no lead path is broken.

## 3. Google Sheets as a lightweight CRM

**Responses tab → Link to Sheets → Create a new spreadsheet** ("Moodily Leads").

**Form-generated columns** (Google creates them; rename the headers only if you want):
Timestamp · Name (Lead Name) · WhatsApp · Email · City / Country (Location) · Preferred language · Role · Service category (Service) · Selected package (Sub-service) · Offer code · *service-specific answers* · Primary goal · Deadline · Budget · Reference link · Message · Consent

**Owner columns:** add them to the **right** of the last form column. Google keeps them aligned when new responses arrive. Never insert or sort rows in the response tab; use **Data → Filter views** instead.

| Column | Data validation (Data → Data validation → Dropdown) |
|---|---|
| Lead Status | New, Contacted, Qualified, Quote sent, Follow-up, Won, Lost, On hold |
| Priority | Hot, Warm, Cold |
| Quoted Price | Number (₹) |
| Quote Date | Date |
| Next Follow-up | Date |
| Won/Lost | Won, Lost, Open |
| Payment Status | Not due, Advance paid, Paid, Refunded |
| Delivery Date | Date |
| Revenue | Number (₹) |
| Lead Source | Website form, WhatsApp, Instagram, Referral, Offer, Other |
| Notes | Text |

Tip: select the service-specific answer columns → right-click → **Group columns**, and collapse them to keep the sheet readable.

**Conditional formatting** (Format → Conditional formatting → Custom formula; select from row 2 down, then change the letters to your columns: B=Budget, D=Deadline, A=Timestamp, S=Lead Status, W=Next Follow-up):

| Highlight | Formula | Colour |
|---|---|---|
| High-value lead | `=OR($B2="₹15,000–₹50,000",$B2="₹50,000+")` | green |
| Urgent deadline | `=OR($D2="24–48 hours",$D2="3–5 days")` | orange |
| Uncontacted > 24h | `=AND($A2<>"",OR($S2="",$S2="New"),NOW()-$A2>1)` | red |
| Overdue follow-up | `=AND($W2<>"",$W2<TODAY(),$S2<>"Won",$S2<>"Lost")` | purple |

**Free alerts:**
- Google Form → Responses → ⋮ → *Get email notifications for new responses*.
- In Sheets: Tools → Notification settings → *Notify me when a user submits a form*.

**Weekly demand review:** add a second tab with `=QUERY('Form Responses 1'!A:Z,"select <Service col>, count(A) where A is not null group by <Service col> order by count(A) desc",1)` to see which services are asked for most. Do the same for Budget. No CRM software is needed yet.

## 4. Deployment checklist

- [ ] Google Form built with the labels above; sign-in not required; no file-upload questions
- [ ] Form linked to the "Moodily Leads" Sheet; owner columns, dropdowns and conditional formatting added
- [ ] `intake.json`: `form_url` (full `/viewform`) + 3 `entry_ids`
- [ ] Review the **draft starting prices** of the 13 new packages in `services.json` (`_todo_price`); change any before launch
- [ ] `python3 build.py && python3 tests/check_site.py` pass; commit and push (CI green)
- [ ] Phone test: `/services/presentation-design/` → "Quote माँगें" → `/contact/` shows the package → Form opens pre-selected → submit → row appears in Sheet
- [ ] Offer test: `/offers/founding-10/` → CTA → contact shows offer note → Form has `founding-10`
- [ ] WhatsApp alternative opens with the package in the message
- [ ] GTM: update the trigger regex (see 03 doc, "Event taxonomy v2") and mark `google_form_click` and `whatsapp_click` as key events
- [ ] Privacy page mentions Google Forms (done)
- [ ] Add real samples (images in `/assets/img/samples/` + entries in `catalogue.json`) as soon as the owner provides them. Never use others' work.

**Rollback:** set `form_url` to `""` and rebuild. `/contact/` returns to the built-in form immediately. Full rollback: revert the PR.
