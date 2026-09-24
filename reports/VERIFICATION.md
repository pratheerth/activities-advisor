# Baseline verification

## Completed

- 26 automated tests passed on Python 3.12.
- Mock HTTP checks cover OpenWeather geocoding, date/timezone-aware forecast filtering, Tavily Search/Extract payloads, and the OpenAI tool/structured-output request.
- Conversation tests cover follow-ups, complete retained tool-call pairs, session isolation, restart persistence between completed turns, timeouts, loop limits and error sanitization.
- The two-turn offline rehearsal passed all six structural checks. It is a fixture, not a real language-quality result.
- Chromium browser checks passed for the initial page, four tool activity entries, itinerary rendering, a follow-up revision, trace access, mobile width, and New trip reset. No browser console errors were recorded.
- Desktop and mobile screenshots were visually inspected. They use explicitly labelled offline fixture data.
- JavaScript syntax checked with Node.

## Still required on the recording machine

No real provider credentials were available for this build. Run live mode with your own OpenAI, OpenWeather and Tavily accounts, execute `python -m advisor.check --out reports/live-rehearsal.json`, and review the answers and evidence.

Mock API contracts do not prove account permissions, quotas, real model behavior, current venue facts or deployed reliability. This package is a baseline ready for local live rehearsal, not a production or recording sign-off.

The test run emitted a Starlette/AnyIO deprecation warning; all tests passed.
