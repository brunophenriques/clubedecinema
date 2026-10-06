# Header loading and hit areas

Cold-cache Chromium tests held font and image responses independently, with
120 ms network latency and throttled downloads. Before the fix, loading Archivo
changed the logout button's width from 50.6875 to 50.046875 px. Its left edge
moved despite a stationary pointer. Showing chat after the week response also
inserted a new flex item. On narrow screens, resolving admin permissions expanded
the navigation and moved the controls; the dark theme used a different gap.

The header rail now reserves explicit grid tracks for account, chat and theme.
Login/logout share a fixed track; chat's track remains reserved while the week
loads. Pages without chat use two tracks. All header controls and the account
avatar have a minimum 44 x 44 px hit area. Narrow screens reserve a separate
control row. Both themes use the same spacing.

The avatar reserves a 44 px container and a 28 x 28 px image. Film posters already
reserve a 2:3 aspect ratio, and the feature artwork has explicit height; image
loading does not determine their layout height. Decorative button SVGs and
pseudo-elements do not receive pointer events. Pointer cursors apply to control
contents; only button labels and the avatar button suppress text selection.

Run `python scripts/check_header_loading.py` with Playwright and Chromium
installed and the local application running. Set `CINEMA_PREVIEW_URL` to change
the default `http://127.0.0.1:8002`. Authentication responses are browser-only
fixtures; no real account, vote or film data is modified. The test checks centre
and edge clicks, hit targets, exact bounds, both themes, and desktop/390/320 px
viewports before authentication, after authentication, after the week response,
after font loading and after visible images settle. It also activates theme and
chat normally. Screenshots are written to `.local/`.
