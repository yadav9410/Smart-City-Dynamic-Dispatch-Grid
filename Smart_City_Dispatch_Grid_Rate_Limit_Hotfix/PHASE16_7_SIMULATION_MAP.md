# Phase 16.7 — Simulated Resources, Routes, and Map Layers

## What is implemented

- Four deterministic synthetic map markers: medical, fire/rescue, rescue, and safety support.
- Separate Folium layers for the demonstration incident point, mock units, and route illustrations.
- Dashed straight-line geometry and great-circle distance approximations. No road-route provider or ETA calculation is used.
- Generic India demo point by default; optional use of the selected user pin requires an explicit control.
- The selected-pin simulation choice resets when the user changes or submits a location.
- Tests for invalid coordinates, deterministic positions, distance calculations, and simulation safety flags.

## Safety boundary

Every unit is fictional. This phase does not read actual resource availability, use live GPS feeds, correlate the user's report to real resources, create an assignment, reserve a resource, or dispatch anyone. The map preview is opt-in and always labeled simulation-only. Map tiles are loaded from OpenStreetMap only when the map is displayed; location coordinates are not sent to a road-routing or geocoding service by this feature.

For an immediate emergency in India, call 112 directly rather than relying on this prototype.
