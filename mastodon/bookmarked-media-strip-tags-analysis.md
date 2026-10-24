# Mastodon description hashtag strip list

Analyzed live on 2026-10-24. The repository exporter now uses this list. The live job has not been changed in this session.

## Scope and selection

- 16,776 bookmark records whose posts have media, across all retained history; 1,027 were bookmarked in the last 30 days (the job's current window).
- 3,832 distinct case-insensitive tags. Each tag counted once per bookmark, regardless of repeated occurrences or attachment count. Counts span all accounts, matching the job.
- Candidate threshold: at least 100 bookmarks across retained history. This is a conservative initial cutoff, not a learned rule to apply automatically.
- Selected 101 frequent tags for exact, case-insensitive removal. Preserve every tag absent from the list, including uncommon generic tags.
- The user also selected the 14 formerly preserved names and identity/source labels for removal. Tags outside the list remain preserved. No substring, prefix, or fuzzy matching: stripping `model` must never strip `nancymodel`.

The companion `bookmarked-media-strip-tags.txt` contains one lowercase tag per line without a leading hash.

## Removals and observed frequency

| Tag | All history | Last 30 days |
| --- | ---: | ---: |
| #nsfw | 8573 | 554 |
| #sexy | 6144 | 449 |
| #erotic | 4835 | 324 |
| #nude | 4262 | 373 |
| #ero | 3030 | 185 |
| #boobs | 1398 | 204 |
| #tits | 1174 | 162 |
| #nudemodel | 952 | 87 |
| #nudes | 948 | 110 |
| #porn | 888 | 55 |
| #naked | 879 | 116 |
| #pussy | 851 | 138 |
| #nudeart | 716 | 14 |
| #girls | 676 | 21 |
| #model | 650 | 20 |
| #nudephotography | 613 | 18 |
| #busty | 579 | 82 |
| #hotgirls | 576 | 20 |
| #redhead | 564 | 15 |
| #breasts | 532 | 93 |
| #photography | 497 | 24 |
| #erotica | 461 | 88 |
| #ass | 442 | 81 |
| #babe | 421 | 95 |
| #nudity | 414 | 100 |
| #bigtits | 381 | 46 |
| #nudeinnature | 370 | 7 |
| #nipples | 340 | 87 |
| #beauty | 329 | 24 |
| #nudistgirl | 328 | 10 |
| #lingerie | 325 | 13 |
| #artphoto | 309 | 7 |
| #cute | 299 | 14 |
| #softcore | 294 | 73 |
| #beautifulwomen | 288 | 87 |
| #artisticnude | 283 | 7 |
| #blonde | 279 | 9 |
| #butt | 268 | 80 |
| #nudegirlmodel | 258 | 1 |
| #pussylips | 255 | 85 |
| #artnude | 251 | 6 |
| #pornstar | 250 | 26 |
| #femalenude | 246 | 66 |
| #adultcontent | 240 | 80 |
| #hornybabe | 239 | 81 |
| #adult | 238 | 23 |
| #booty | 235 | 78 |
| #clit | 234 | 85 |
| #sexygirl | 234 | 81 |
| #fullnude | 228 | 79 |
| #brunette | 227 | 3 |
| #nudewoman | 219 | 67 |
| #perfectbody | 219 | 4 |
| #petitetits | 216 | 2 |
| #veryhot | 215 | 7 |
| #fyp | 212 | 67 |
| #photographer | 212 | 4 |
| #femalebody | 209 | 66 |
| #blackandwhite | 195 | 1 |
| #sex | 186 | 5 |
| #amateur | 182 | 5 |
| #lust | 175 | 3 |
| #naughty | 166 | 1 |
| #nudebeach | 156 | 2 |
| #explicit | 154 | 0 |
| #love | 151 | 0 |
| #beautiful | 147 | 21 |
| #petite | 147 | 6 |
| #studiophoto | 142 | 3 |
| #wetbody | 142 | 7 |
| #teen | 134 | 3 |
| #bigboobs | 132 | 3 |
| #nakedoutdoors | 131 | 4 |
| #shaved | 131 | 6 |
| #bigbreasts | 124 | 3 |
| #glamour | 119 | 11 |
| #yummy | 118 | 0 |
| #tanlines | 116 | 5 |
| #wifeymaterial | 115 | 0 |
| #fotografie | 112 | 8 |
| #vintage | 112 | 9 |
| #kinky | 111 | 12 |
| #daddylikes | 108 | 0 |
| #femalebeauty | 106 | 3 |
| #fitbody | 106 | 1 |
| #fuckdoll | 106 | 0 |
| #hotasfuck | 105 | 0 |

## Additional frequent tags selected for removal

These 14 tags are also stripped, as requested, including names, brands, communities, source labels, and ambiguous phrases.

| Tag | All history | Last 30 days |
| --- | ---: | ---: |
| #wataa | 554 | 20 |
| #aypapi | 335 | 0 |
| #freyja | 230 | 7 |
| #womansart | 206 | 6 |
| #metart | 180 | 16 |
| #womenschoice | 163 | 6 |
| #redlib | 147 | 4 |
| #reddit | 146 | 1 |
| #justyourtype | 127 | 66 |
| #nbwvideos | 127 | 0 |
| #princess | 118 | 0 |
| #onlyfans | 108 | 32 |
| #misskey写真部 | 101 | 1 |
| #playboy | 100 | 3 |

## Implementation caveat

In `config-map-bookmarked-media-sync-scripts.yaml`, the exporter previously removed every HTML anchor before applying a blanket hashtag regex. The updated exporter preserves hashtag-anchor text before filtering this exact list, while retaining removal of ordinary links and URLs. HTML node boundaries also matter: plain fragment text can merge adjacent links or URLs into false tag tokens. This analysis separated anchors and line breaks before counting.

No stored Immich descriptions were modified. Analysis covers retained bookmarked media posts, not deleted posts or a complete historical Immich inventory. All 101 tags meeting the original frequency cutoff are now selected for removal; other tags remain preserved.
