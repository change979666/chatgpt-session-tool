import os
import threading
import queue
import time
import tempfile

from PIL import ImageGrab
from playwright.sync_api import sync_playwright


class ChatGPTBrowser:
    def __init__(self, user_data_dir="user_data"):
        self.user_data_dir = os.path.abspath(user_data_dir)
        self.cmd_queue = queue.Queue()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.is_active = False
        self.ready_event = threading.Event()
        self.headless = False

    def start_browser(self, headless=False, timeout=30):
        """Starts the browser thread and waits for it to be ready."""
        self.headless = headless
        if not self.thread.is_alive():
            self.thread.start()
        if not self.ready_event.wait(timeout=timeout):
            raise TimeoutError("Browser startup timed out")

    def _run_loop(self):
        """Internal loop running in a separate thread to manage Playwright."""
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                page = browser.new_page()
                try:
                    page.goto("https://chatgpt.com/")
                except Exception:
                    # Might fail transiently, but we want to keep browser open.
                    pass
                
                self.is_active = True
                self.ready_event.set()
                
                while True:
                    cmd = self.cmd_queue.get()
                    if cmd is None:  # Stop signal
                        break
                    
                    action, data, result_queue = cmd
                    
                    if action == "SEND":
                        self._handle_send(page, data, result_queue)
                    elif action == "GET_RESPONSE":
                        self._handle_get_response(page, data, result_queue)
                    elif action == "DEBUG":
                        self._handle_debug(page, result_queue)
                    elif action == "UPLOAD_FILE":
                        self._handle_upload_file(page, data, result_queue)
                    elif action == "PASTE_IMAGE":
                        self._handle_paste_image(page, result_queue)
                
                browser.close()
            except Exception as e:
                print(f"Browser thread crashed: {e}")
            finally:
                self.is_active = False
                # Ensure we don't block forever if crash.
                self.ready_event.set()

    def _handle_send(self, page, message, result_queue):
        try:
            assistant_selector = 'div[data-message-author-role="assistant"]'
            before_count = page.locator(assistant_selector).count()

            input_selector = "#prompt-textarea"
            page.wait_for_selector(input_selector, timeout=15000)
            page.fill(input_selector, message)
            page.press(input_selector, "Enter")

            # Return assistant message count before sending so we can
            # wait for the next assistant response.
            result_queue.put(before_count)
        except Exception as e:
            result_queue.put(f"Error sending: {e}")

    def _handle_get_response(self, page, data, result_queue):
        try:
            selector = 'div[data-message-author-role="assistant"]'
            before_count = 0
            timeout = 60
            if isinstance(data, dict):
                before_count = int(data.get("before_count", 0))
                timeout = int(data.get("timeout", 60))

            deadline = time.time() + timeout
            last_text = None
            stable_ticks = 0

            stop_locators = [
                page.locator('[data-testid="stop-button"]'),
                page.locator('button[aria-label*="Stop"]'),
                page.locator('button:has-text("Stop")'),
                page.locator('button:has-text("停止")'),
                page.locator('button:has-text("停止生成")'),
            ]

            def _is_generating() -> bool:
                for loc in stop_locators:
                    try:
                        if loc.first.is_visible():
                            return True
                    except Exception:
                        continue
                return False

            while time.time() < deadline:
                count = page.locator(selector).count()
                if count > before_count:
                    locator = page.locator(selector).nth(count - 1)
                    current = locator.inner_text()
                    if current and current.strip():
                        if last_text == current:
                            stable_ticks += 1
                        else:
                            stable_ticks = 0
                            last_text = current

                        # Consider done when text has stabilized for a bit and
                        # generation button is not visible.
                        if stable_ticks >= 3 and not _is_generating():
                            result_queue.put(last_text)
                            return

                # Response may still be streaming; poll.
                time.sleep(0.5)

            if last_text:
                result_queue.put(last_text)
            else:
                msg = "Timed out waiting for response (check selectors)."
                result_queue.put(msg)
                
        except Exception as e:
            result_queue.put(f"Error getting response: {e}")

    def _handle_debug(self, page, result_queue):
        try:
            url = ""
            title = ""
            try:
                url = page.url
            except Exception:
                url = "(unknown)"
            try:
                title = page.title()
            except Exception:
                title = "(unknown)"

            input_prompt = "#prompt-textarea"
            assistant_sel = 'div[data-message-author-role="assistant"]'
            user_sel = 'div[data-message-author-role="user"]'

            prompt_count = page.locator(input_prompt).count()
            assistant_count = page.locator(assistant_sel).count()
            user_count = page.locator(user_sel).count()

            # Common alternative inputs (may vary over time)
            textarea_count = page.locator("textarea").count()
            contenteditable_locator = page.locator('[contenteditable="true"]')
            contenteditable_count = contenteditable_locator.count()

            lines = [
                "[Debug] Browser DOM snapshot",
                f"url={url}",
                f"title={title}",
                f"#prompt-textarea count={prompt_count}",
                f"assistant nodes={assistant_count}",
                f"user nodes={user_count}",
                f"textarea count={textarea_count}",
                f"contenteditable=true count={contenteditable_count}",
                "Tip: if prompt count is 0, selectors likely changed ",
                "or you are not logged in.",
            ]
            result_queue.put("\n".join(lines))
        except Exception as e:
            result_queue.put(f"Error in debug: {e}")

    def _focus_prompt(self, page):
        input_selector = "#prompt-textarea"
        page.wait_for_selector(input_selector, timeout=15000)
        page.click(input_selector)
        return input_selector

    def _handle_upload_file(self, page, file_path, result_queue):
        try:
            if not file_path or not os.path.exists(file_path):
                result_queue.put("Error: file not found")
                return

            # Try to locate any file input on the page.
            file_inputs = page.locator('input[type="file"]')
            if file_inputs.count() == 0:
                # Try clicking an attach button to reveal inputs.
                candidates = [
                    page.locator('button[aria-label*="Attach"]'),
                    page.locator('button:has-text("Attach")'),
                    page.locator('button:has-text("上传")'),
                    page.locator('button:has-text("附件")'),
                    page.locator('button:has-text("文件")'),
                ]
                for loc in candidates:
                    try:
                        if loc.first.is_visible():
                            loc.first.click()
                            break
                    except Exception:
                        continue
                file_inputs = page.locator('input[type="file"]')

            if file_inputs.count() == 0:
                result_queue.put("Error: no file input found")
                return

            # Set the file(s). Works even if input is hidden in most cases.
            file_inputs.first.set_input_files(file_path)
            result_queue.put(True)
        except Exception as e:
            result_queue.put(f"Error uploading file: {e}")

    def _handle_paste_image(self, page, result_queue):
        """Paste image from OS clipboard into ChatGPT.

        Strategy:
        1) Detect an image in clipboard.
        2) Prefer uploading it via input[type=file] (more reliable).
        3) Fallback to Ctrl+V into the prompt.
        """
        try:
            clip = ImageGrab.grabclipboard()
            if clip is None:
                result_queue.put("剪贴板里没有图片")
                return

            # Sometimes Windows clipboard returns a list of file paths.
            if isinstance(clip, list) and clip:
                # If user copied an image file, upload the first one.
                first = clip[0]
                if isinstance(first, str) and os.path.exists(first):
                    q = queue.Queue()
                    self._handle_upload_file(page, first, q)
                    result_queue.put(q.get())
                    return

            # If it's an image object, save to a temp png.
            if hasattr(clip, "save"):
                tmp_dir = os.path.join(self.user_data_dir, "_tmp")
                os.makedirs(tmp_dir, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    suffix=".png",
                    dir=tmp_dir,
                    delete=False,
                ) as f:
                    tmp_path = f.name
                clip.save(tmp_path, format="PNG")

                q = queue.Queue()
                self._handle_upload_file(page, tmp_path, q)
                upload_res = q.get()
                if upload_res is True:
                    result_queue.put(True)
                    return

                # Fallback to paste.
                self._focus_prompt(page)
                page.keyboard.press("Control+V")
                result_queue.put(
                    f"已尝试粘贴（上传失败：{upload_res}）"
                )
                return

            # Fallback: focus prompt and paste.
            self._focus_prompt(page)
            page.keyboard.press("Control+V")
            result_queue.put(True)
        except Exception as e:
            result_queue.put(f"Error pasting image: {e}")

    def send_message(self, message, timeout=30):
        if not self.is_active:
            return "Error: Browser not connected."
        q = queue.Queue()
        self.cmd_queue.put(("SEND", message, q))
        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            return "Error: send timed out"

    def get_latest_response(self, before_count=0, timeout=60):
        if not self.is_active:
            return "Error: Browser not connected."
        q = queue.Queue()

        data = {"before_count": before_count, "timeout": timeout}
        self.cmd_queue.put(("GET_RESPONSE", data, q))
        try:
            return q.get(timeout=timeout + 5)
        except queue.Empty:
            return "Error: response timed out"

    def close(self, timeout=5):
        self.cmd_queue.put(None)
        if self.thread.is_alive():
            self.thread.join(timeout=timeout)

    def debug_info(self, timeout=10):
        if not self.is_active:
            return "Error: Browser not connected."
        q = queue.Queue()
        self.cmd_queue.put(("DEBUG", None, q))
        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            return "Error: debug timed out"

    def upload_file(self, file_path, timeout=30):
        if not self.is_active:
            return "Error: Browser not connected."
        q = queue.Queue()
        self.cmd_queue.put(("UPLOAD_FILE", file_path, q))
        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            return "Error: upload timed out"

    def paste_clipboard_image(self, timeout=30):
        if not self.is_active:
            return "Error: Browser not connected."
        q = queue.Queue()
        self.cmd_queue.put(("PASTE_IMAGE", None, q))
        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            return "Error: paste timed out"
