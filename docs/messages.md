# The messages

The texts are the product. Everything else in Docketbell exists to send the right
words to the right person at the right time.

## How they're written

Research on court reminders (ideas42, the NYC Criminal Court study published in
*Science*, J-PAL) points to the same few habits:

1. **Be specific.** Every reminder names the day, time and place. Vague reminders don't work.
2. **Say what's at stake, kindly.** The heads-up text says plainly that a judge may
   issue a warrant. It informs, it doesn't threaten.
3. **Prompt a plan.** People miss court because of rides, shifts and childcare, not
   because they don't care. The "make a plan" text names those things.
4. **Make answering easy.** `1` confirms and `2` asks for help. Digits work in every
   language and on every keyboard.
5. **Offer a person.** Every text that might worry someone includes a phone number.
6. **Keep it private.** Phones are shared. Texts never include charges or case numbers.
7. **Keep it cheap.** English texts use only the basic SMS alphabet (straight quotes,
   no dashes) so each costs one or two segments.

## Every text, in English

Sample values: Maria, Main Street Defenders, (212) 555-0199, next Tuesday at 9:30 AM.

| Text | When | What Maria gets | Segments |
|---|---|---|---|
| **Welcome** | Right after someone is signed up for reminders. | Hi Maria, this is Main Street Defenders. We'll text you reminders before your court date: Tuesday, November 10 at 9:30 AM, Main Street Courthouse, Courtroom 4B, 100 Main St. Reply 1 to confirm you got this. Reply STOP to opt out. | 2 |
| **Heads-up** | The first countdown reminder, usually a week before. Explains what is at stake. | Maria, your court date is Tuesday, November 10 at 9:30 AM, Main Street Courthouse, Courtroom 4B, 100 Main St. If you miss it, the judge may issue a warrant for your arrest. Reply 1 to confirm, or 2 if you need help. | 2 |
| **Make a plan** | Later countdown reminders, usually 3 days before. Prompts a plan to get there. | Maria, your court date is Tuesday, November 10 at 9:30 AM. Make a plan now: how you'll get there, and time off work or childcare if you need it. Reply 2 if something could stop you from going. | 2 |
| **Day before** | The day before the court date. | Reminder: your court date is tomorrow, Tuesday, November 10 at 9:30 AM, Main Street Courthouse, Courtroom 4B, 100 Main St. Please arrive early. Missing court can lead to a warrant. Questions? Call (212) 555-0199. | 2 |
| **Morning of** | The morning of the court date (only if 0 is in the reminder schedule). | Today: your court date is at 9:30 AM, Main Street Courthouse, Courtroom 4B, 100 Main St. Please arrive early. If you are running late, call (212) 555-0199. | 1 |
| **Date changed** | When staff change the date or time. | Maria, your court date has changed. The new date is Tuesday, November 10 at 9:30 AM, Main Street Courthouse, Courtroom 4B, 100 Main St. Please go on the new date. Reply 1 to confirm. | 2 |
| **Date canceled** | When staff cancel a court date. | Maria, your court date on Tuesday, November 10 was canceled. You do not need to go to court that day. We'll text you if a new date is set. Questions? Call (212) 555-0199. | 2 |
| **Missed court** | After staff mark a court date as missed. Encourages a quick call back. | Maria, our records show you may have missed court on Tuesday, November 10. It's not too late to fix this. Call (212) 555-0199 today and we'll help you get a new date. | 2 |
| **Thanks for confirming** | When someone replies 1 or YES. | Thank you, Maria. You're confirmed for Tuesday, November 10 at 9:30 AM. If anything changes, reply 2 or call (212) 555-0199. | 1 |
| **Help is on the way** | When someone replies 2 or NO. Also flags the court date for staff. | Thanks for telling us, Maria. Someone from Main Street Defenders will contact you soon. You can also call (212) 555-0199. Please don't skip court without talking to us first. | 2 |
| **Opted out** | When someone replies STOP. | You won't get more texts from Main Street Defenders. Reply START to get reminders again. Questions about your case? Call (212) 555-0199. | 1 |
| **Opted back in** | When someone replies START after opting out. | You'll get court date reminders from Main Street Defenders again. Reply STOP to opt out. | 1 |
| **Help and info** | When someone replies HELP or INFO. | Main Street Defenders: court date reminders. Reply 1 to confirm your date, 2 if you need help. Call (212) 555-0199 with questions. Reply STOP to opt out. Msg & data rates may apply. | 2 |
| **Didn't understand** | When a reply isn't a keyword. Sent at most once a day; staff see the message. | Sorry, we couldn't read that. Reply 1 to confirm your court date or 2 if you need help. A staff member will also read your message. | 1 |
| **No upcoming date** | When someone confirms but has no upcoming court date on file. | Thanks. We don't see an upcoming court date for you. If you think that's wrong, call (212) 555-0199. | 1 |
| **Language changed** | When someone texts the name of a language, such as ESPAÑOL. | OK. We'll text you in English from now on. Reply STOP to opt out. | 1 |

See them in every language, with costs, on the **Messages** page of the dashboard.

## Placeholders

Custom texts (Admin → *Custom message texts*) can use:

| Placeholder | Example |
|---|---|
| `{first_name}` | Maria |
| `{org_name}` | Main Street Defenders |
| `{org_phone}` | (212) 555-0199 |
| `{date}` | Tuesday, November 17 / martes, 17 de noviembre / 11月17日星期二 |
| `{time}` | 9:30 AM / 9:30 a.m. / 上午9:30 |
| `{place}` | Main Street Courthouse, Courtroom 4B, 100 Main St |
| `{court_name}`, `{court_address}`, `{room}` | The parts of `{place}` |

Unknown placeholders are rejected when you save, so a typo can't reach anyone's phone.

## Replies people can send

| They text | Meaning | What happens |
|---|---|---|
| `1`, yes, ok, sí, 是的, có, 네, да, نعم, wi | Confirm | Marked **Confirmed**; thank-you reply. |
| `2`, no, can't, no puedo, 不能, нет, pa kapab | Needs help | Marked **Needs help** and sent to the inbox; reply says someone will call. |
| `STOP`, unsubscribe, cancel, end, quit, alto | Opt out | No more texts; one confirmation. |
| `START`, unstop | Opt back in | Texts resume. |
| `HELP`, info, ayuda | Information | Program information and phone number. |
| Español, 中文, Tiếng Việt, 한국어, Русский, العربية, Kreyòl, English | Change language | Future texts in that language. |
| Anything else | A question | Goes to the inbox; at most one "we couldn't read that" reply a day. |

Texts from unknown numbers are never answered automatically, but staff see them in the inbox.

## Languages

| Language | Texts | Dashboard |
|---|---|---|
| English | ✓ | ✓ |
| Español (Spanish) | ✓ | ✓ |
| 中文（简体）(Simplified Chinese) | ✓ | |
| Tiếng Việt (Vietnamese) | ✓ | |
| 한국어 (Korean) | ✓ | |
| Русский (Russian) | ✓ | |
| العربية (Arabic) | ✓ | |
| Kreyòl ayisyen (Haitian Creole) | ✓ | |

The translations were written carefully, with US usage in mind (formal address,
gender-neutral Arabic, Southern Vietnamese, US Spanish "corte"). Have a qualified
translator or a native-speaking colleague review them before you go live. Court
language access rules may require it. Corrections are very welcome as a
[translation issue](https://github.com/lobojoel2003/Docketbell/issues/new?template=translation.yml).

Dates and times come from Unicode CLDR through Babel, so they read naturally:
"martes, 17 de noviembre a las 9:30 a.m.", "11月17日星期二上午9:30",
"вторник, 17 ноября в 09:30". Haitian Creole uses its own day and month names.

## Adding a language

1. Add it to `DOCKETBELL_LANGUAGES` in `docketbell/settings.py`, plus its names
   (for language switching) in `docketbell/core/replies.py`, and its confirm/help words.
2. `cd docketbell && DEBUG=true python ../manage.py makemessages -l <locale> --no-location`
3. Translate the 16 texts in `docketbell/locale/<locale>/LC_MESSAGES/django.po` (the
   ones with a "Translators: SMS" note) and set its `Plural-Forms` header.
4. `make messages`, then check the **Messages** page and run `make test`. The tests
   fail if any text is missing, loses a placeholder or drops a reply keyword.

## Cost

Carriers bill per *segment*: 160 characters in the basic SMS alphabet, or 70 when a
text contains any other character (accents like "á", or Chinese, Russian or Arabic
letters). The **Messages** page shows each text's segments and cost at your price
(`DOCKETBELL_COST_PER_SEGMENT`). A typical English court date (welcome plus three
reminders) is 8 segments: about 7 cents at the default $0.0083 per segment, before carrier fees. For context, ideas42
estimated three short reminders at about 3 cents.
