# TWIFO Issues List

Date: 2026 02 13

## 1 Products show as UNKNOWN in web summaries

Observed
The web summary header badge shows UNKNOWN for products on articles where products should be known.

Example
MZ_XCCY Weekly -02-06_20260209_w

Expected
Products should display as a list such as USDJPY, EURUSD, GBPUSD.

Notes
The sum.pdf clearly shows a Products line, and the sum.json should contain the same products field. The web renderer appears to not read or not map the products field correctly.

## 2 Daily View buttons missing products on line 3

Observed
Daily View sidebar buttons do not show products on the third line even when products exist for the article.

Expected
Each Daily View button should show
Line 1 Firm name
Line 2 Article title
Line 3 Products from sum.json if present, otherwise blank

Notes
If products are present in sum.json, they should also appear in the Daily View button line 3. If products are only present in pdf but not in json, then the extraction pipeline should be updated so products are persisted into sum.json.

## 3 Firm mapping failing, showing O or Other and missing MZ to Mizuno

Observed
Web summaries show O and Other instead of the correct firm.
PDF summaries also show O and Other instead of the correct firm.

Example
MZ should map to Mizuno, but it shows O and Unknown.

Expected
Firm code MZ should map to Mizuno.
Other firm codes should map using the existing prefix map consistently across
Daily View button line 1
Web summary header firm badge
PDF summary header firm line

Notes
This appears to be a recurring system wide mapping issue, not a one off.
Likely causes include
Provider code not being extracted correctly from artifacts or filename
Prefix map lookup not using the right key format
Provider value being overwritten to O somewhere in the pipeline

## 4 PDF summary title is wrong, shows sum instead of the article title

Observed
The pdf summary document title header shows the word sum at the top.
This is not the article title.

Expected
The pdf summary should show the article title at the top, not sum.

Notes
The title is available and already shown on the web page as the main heading, so the pdf generation step should use the same title string.

## Desired end state

Daily View
Left sidebar shows yesterday articles with
Firm name on line 1 using correct mapping
Title on line 2
Products on line 3 from sum.json
Right panel shows the web summary for the selected article

Web summary
Firm badge shows correct firm name
Products badge shows correct products list

PDF summary
Top header shows article title
Firm and products show correctly, matching the web summary
