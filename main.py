from browser_manager import ChatGPTBrowser
from gui import ChatApp

def main():
    # Initialize the browser manager
    # We use a persistent user data directory to save login cookies
    browser = ChatGPTBrowser(user_data_dir="chatgpt_session")
    
    # Initialize and run the GUI
    app = ChatApp(browser)
    app.mainloop()
    
    # Cleanup
    browser.close()

if __name__ == "__main__":
    main()
