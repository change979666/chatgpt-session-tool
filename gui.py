import customtkinter as ctk
import threading
from tkinter import filedialog


class ChatApp(ctk.CTk):
    def __init__(self, browser_manager):
        super().__init__()
        self.browser_manager = browser_manager
        
        self.title("ChatGPT 桌面客户端")
        self.geometry("800x600")
        
        # Grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        # Chat display area
        self.chat_display = ctk.CTkTextbox(self, state="disabled")
        self.chat_display.grid(
            row=0,
            column=0,
            padx=10,
            pady=10,
            sticky="nsew",
        )

        # Input area
        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)
        self.input_frame.grid_columnconfigure(1, weight=0)
        self.input_frame.grid_columnconfigure(2, weight=0)
        self.input_frame.grid_columnconfigure(3, weight=0)

        self.msg_entry = ctk.CTkEntry(
            self.input_frame,
            placeholder_text="请输入你的问题...",
            state="disabled",
        )
        self.msg_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.msg_entry.bind("<Return>", self.send_message_event)

        self.paste_img_btn = ctk.CTkButton(
            self.input_frame,
            text="粘贴图片",
            command=self.paste_image_thread,
            state="disabled",
            width=90,
        )
        self.paste_img_btn.grid(row=0, column=1, padx=(0, 10))

        self.upload_btn = ctk.CTkButton(
            self.input_frame,
            text="上传文件",
            command=self.upload_file_thread,
            state="disabled",
            width=90,
        )
        self.upload_btn.grid(row=0, column=2, padx=(0, 10))

        self.send_btn = ctk.CTkButton(
            self.input_frame,
            text="发送",
            command=self.send_message,
            state="disabled",
        )
        self.send_btn.grid(row=0, column=3)

        # Login / Start Browser Button
        self.login_btn = ctk.CTkButton(
            self,
            text="打开浏览器并登录",
            command=self.start_browser_thread,
        )
        self.login_btn.grid(row=2, column=0, pady=10)

        self.debug_btn = ctk.CTkButton(
            self,
            text="调试（DOM）",
            command=self.debug_dom_thread,
        )
        self.debug_btn.grid(row=3, column=0, pady=(0, 10))

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def start_browser_thread(self):
        self.login_btn.configure(state="disabled", text="浏览器启动中...")
        threading.Thread(target=self._start_browser, daemon=True).start()

    def _start_browser(self):
        try:
            # Start visible browser so user can login
            # This call now blocks until the browser is ready, but that's fine
            # because we are already in a background thread.
            self.browser_manager.start_browser(headless=False)

            def _ui_ready():
                self.login_btn.configure(text="浏览器已连接（不要关闭）")
                self.append_message(
                    "System",
                    "浏览器已启动。请在弹出的窗口中登录 ChatGPT。",
                )
                self.msg_entry.configure(state="normal")
                self.send_btn.configure(state="normal")
                self.paste_img_btn.configure(state="normal")
                self.upload_btn.configure(state="normal")

            self.after(0, _ui_ready)
        except Exception as e:
            def _ui_error(err=e):
                self.append_message(
                    "System",
                    f"启动浏览器失败：{err}",
                )
                self.login_btn.configure(
                    state="normal",
                    text="打开浏览器并登录",
                )

            self.after(0, _ui_error)

    def send_message_event(self, event):
        self.send_message()

    def debug_dom_thread(self):
        threading.Thread(target=self._debug_dom, daemon=True).start()

    def _debug_dom(self):
        if not self.browser_manager.is_active:
            self.append_message("System", "错误：浏览器未连接。")
            return

        info = self.browser_manager.debug_info(timeout=10)
        self.append_message("System", str(info))

    def paste_image_thread(self):
        threading.Thread(target=self._paste_image, daemon=True).start()

    def _paste_image(self):
        if not self.browser_manager.is_active:
            self.append_message("System", "错误：浏览器未连接。")
            return
        self.append_message("System", "正在从剪贴板粘贴图片...")
        res = self.browser_manager.paste_clipboard_image(timeout=30)
        if res is True:
            self.append_message("System", "已粘贴/添加图片（如未显示，请稍等）。")
        else:
            self.append_message("System", str(res))

    def upload_file_thread(self):
        # File dialog must be opened on the main thread.
        path = filedialog.askopenfilename(title="选择要上传的文件")
        if not path:
            return
        threading.Thread(
            target=self._upload_file,
            args=(path,),
            daemon=True,
        ).start()

    def _upload_file(self, path):
        if not self.browser_manager.is_active:
            self.append_message("System", "错误：浏览器未连接。")
            return
        self.append_message("System", f"正在上传文件：{path}")
        res = self.browser_manager.upload_file(path, timeout=30)
        if res is True:
            self.append_message("System", "文件已添加（如未显示，请稍等）。")
        else:
            self.append_message("System", str(res))

    def send_message(self):
        msg = self.msg_entry.get()
        if not msg:
            return

        self.append_message("You", msg)
        self.msg_entry.delete(0, "end")

        # Send in background thread to not freeze UI
        threading.Thread(
            target=self._send_and_receive,
            args=(msg,),
            daemon=True,
        ).start()

    def _send_and_receive(self, msg):
        if not self.browser_manager.is_active:
            self.append_message("System", "错误：浏览器未连接。")
            return

        before_count = self.browser_manager.send_message(msg)
        if isinstance(before_count, str):
            self.append_message("System", before_count)
            return

        # Wait for response (simplified)
        # In a real app, we'd poll for the response completion
        self.append_message("System", "等待回复中...")
        
        # This is where we'd implement better completion detection.
        # For now, we just simulate or grab what we can
        response = self.browser_manager.get_latest_response(
            before_count=before_count,
            timeout=60,
        )
        self.append_message("ChatGPT", str(response))

    def append_message(self, sender, text):
        def _do():
            self.chat_display.configure(state="normal")
            self.chat_display.insert("end", f"{sender}: {text}\n\n")
            self.chat_display.configure(state="disabled")
            self.chat_display.see("end")

        self.after(0, _do)

    def on_close(self):
        try:
            threading.Thread(
                target=self.browser_manager.close,
                kwargs={"timeout": 2},
                daemon=True,
            ).start()
        finally:
            self.destroy()
