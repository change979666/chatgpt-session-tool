# chatgpt-session-tool

A small desktop chat client for ChatGPT that drives a real Chromium browser through
[Playwright](https://playwright.dev/python/) instead of an API key. The browser runs
in a persistent profile, so you log in to chatgpt.com once by hand and the login
session is reused on later launches.

## Features

- Opens a visible Chromium context (`launch_persistent_context`) so you can log in manually.
- Sends prompts into the ChatGPT input box and polls the page until the streamed
  assistant answer stabilizes (and the Stop button disappears) before showing it.
- Uploads arbitrary files to the chat (`input[type=file]`, with attach-button fallbacks).
- Pastes an image from the OS clipboard into the chat.
- Built-in DOM debug snapshot (input/textarea/assistant node counts) for diagnosing
  broken page selectors.
- CustomTkinter GUI with background worker threads so the UI never freezes while
  the browser thread is busy.

## Project layout

- `main.py` — entry point; wires the browser manager to the GUI.
- `browser_manager.py` — `ChatGPTBrowser`: Playwright loop on a thread, command queue
  for SEND / GET_RESPONSE / UPLOAD_FILE / PASTE_IMAGE / DEBUG.
- `gui.py` — CustomTkinter chat window.
- `requirements.txt` — `playwright`, `customtkinter`, `pillow`.

## Requirements & run

```bash
pip install -r requirements.txt
python -m playwright install chromium
python main.py
```

On first start, click "open browser and login", sign in to chatgpt.com in the popup
window, then type messages in the GUI. A `chatgpt_session/` profile directory is
created next to the script — keep it out of version control (it holds your login
cookies).

## Notes

- Selectors target the current chatgpt.com DOM; if the site changes, use the
  "debug (DOM)" button to inspect the live page and update the selectors.
- This project is for personal automation of your own logged-in session.

## License & Attribution / 许可与来源

Original project code authored for this repository is released under the MIT License; see [LICENSE](./LICENSE).

When reusing or redistributing a substantial portion, retain the LICENSE and its copyright notice. The copyright notice includes this original source URL: https://github.com/change979666/chatgpt-session-tool. Please keep the source link visible in your redistributed source or project documentation.

This license applies only to original material that the repository maintainer has the right to license. Third-party libraries, vendor code, platform SDKs, trademarks, screenshots, icons, fonts, and other external assets remain subject to their respective licenses and terms. Review those terms before reuse.

**Project status:** personal/archived project, shared as-is. Maintenance, compatibility, and production readiness are not guaranteed.
