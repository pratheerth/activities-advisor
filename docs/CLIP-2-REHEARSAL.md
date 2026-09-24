# Clip 2 rehearsal: meet Activities Advisor

## Teaching purpose

Introduce a functioning local application that will be deployed in Clip 3 and progressively improved through the course. The baseline is not introduced as the completed production system.

## Before recording

1. Start in live mode. The UI must say **Live tools**, not Offline demo.
2. Confirm all three accounts are usable and run the live rehearsal command.
3. Read the initial itinerary and revision. Check the city/date, forecasts, source support, preferences, and honest treatment of unknown hours/costs.
4. Choose a near-term date covered by the forecast. Tomorrow keeps setup simple; explicitly name the calendar date in narration if needed.
5. Rehearse the interaction on the recording machine. Leave the server running; keep API keys off screen.

## Screen sequence

1. Show the blank planner. Introduce its purpose: find suitable activities for a place/date using weather and web information.
2. Submit the Edinburgh example in the README.
3. Let the activity panel show real location, forecast, search and extraction calls. Explain that the model requests tools and inspects returned information. Do not claim every request must use every tool.
4. Inspect the plan and briefly open a source. Proposed schedule times are suggestions, not verified venue opening hours.
5. Ask for less walking and at most two main stops. Show that the revision keeps the same city/date and interests.
6. Briefly show the architecture: browser UI → FastAPI agent loop → OpenAI plus OpenWeather/Tavily. Conversation state supports follow-ups.
7. Transition to deploying this application. Do not introduce routing, caches, approval controls, or dashboards yet.

## Live acceptance checklist

- All four tool integrations work for the initial example, including page extraction.
- Forecast date/location match the request; dates outside coverage are not assigned invented weather.
- At least two recommended venues have relevant, inspectable sources.
- No unsupported precise prices, hours, walking times, bookings, or accessibility guarantees.
- A preference revision changes the plan while retaining relevant context.
- New trip starts fresh.
- Errors show a limitation or clear failure rather than a fabricated successful result.

If a provider is unavailable, fix/retry before recording. A clean take is fine; do not substitute fixture output and represent it as live. Development debugging history is not part of this clip.
