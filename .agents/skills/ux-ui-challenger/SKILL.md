---
name: ux-ui-challenger
description: Challenge information architecture, navigation, user flows, and accessibility before implementing or changing product UI. Use for meaningful UX decisions, not visual styling alone.
---

# UX/UI Challenger

Use this before implementation when a UI change affects a user journey, navigation, onboarding, permissions, confirmation, destructive action, or a mobile/responsive interaction.

1. Identify the user goal, entry point, primary path, failure path, and success state from the relevant product instructions and existing UI.
2. Challenge assumptions that create ambiguity, hidden state, inaccessible interaction, unclear ownership, or an irreversible action without confirmation.
3. Prefer the smallest flow that preserves the established product navigation and design system. State any assumption that materially affects the result.
4. Define acceptance criteria for loading, empty, error, disabled, keyboard, screen-reader, and mobile states when they apply.
5. Hand visual styling to `design-taste-frontend` and the repository design-system rules; do not invent a competing visual language.

Skip this for copy-only, token-only, or purely mechanical visual changes with no flow or behavior impact.
