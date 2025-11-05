# chat_message_manager.py - Unified Chat Message Management System

from nicegui import ui
from typing import Optional
from colorama import Fore, Style, init

init(autoreset=True)


class ChatMessageManager:
    """
    Unified system for managing all chat messages with consistent structure.
    
    Structure:
        - Wrapper (column): Controls alignment (left/right) via CSS classes
        - Bubble (div): Controls size, styling, and content via CSS classes
    
    This separates positioning from appearance for cleaner code.
    """
    
    def __init__(self, chat_log_container):
        """
        Initialize the chat message manager.
        
        Args:
            chat_log_container: The NiceGUI container where messages are displayed
        """
        self.chat_log = chat_log_container
        self.message_counter = 0
        print(f"{Fore.GREEN}[CHAT_MANAGER] Initialized{Style.RESET_ALL}")
    
    def add_user_message(self, text: str) -> str:
        """
        Add a user message to the chat.
        
        Args:
            text: The user's message text
            
        Returns:
            str: The unique message ID
        """
        message_id = f"user_msg_{self.message_counter}"
        self.message_counter += 1
        
        # Escape HTML to prevent injection
        escaped_text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        
        with self.chat_log:
            # REMOVED: .style(...)
            with ui.row().classes('chat-message-wrapper user-wrapper'):
                ui.html(
                    f'<div class="message-bubble user-bubble" id="{message_id}">'
                    f'<strong>You:</strong> {escaped_text}'
                    f'</div>'
                )
        
        print(f"{Fore.CYAN}[CHAT_MANAGER] User message added: {message_id}{Style.RESET_ALL}")
        return message_id
    
    def add_bot_message(self, message_id: Optional[str] = None) -> str:
        """
        Add a bot message placeholder to the chat.
        
        Args:
            message_id: Optional custom message ID. If None, auto-generates one.
            
        Returns:
            str: The message ID
        """
        if not message_id:
            message_id = f"darwin_msg_{self.message_counter}"
            self.message_counter += 1
        
        with self.chat_log:
            # REMOVED: .style(...)
            with ui.row().classes('chat-message-wrapper darwin-wrapper'):
                ui.html(
                    f'<div class="message-bubble darwin-bubble" id="{message_id}"></div>'
                )
        
        print(f"{Fore.GREEN}[CHAT_MANAGER] Bot message placeholder added: {message_id}{Style.RESET_ALL}")
        return message_id
    
    def add_typing_indicator(self, message_id: str) -> str:
        """
        Add a typing indicator to the chat.
        
        Args:
            message_id: The message ID for the typing indicator
            
        Returns:
            str: The message ID
        """
        with self.chat_log:
            # REMOVED: .style(...)
            with ui.row().classes('chat-message-wrapper darwin-wrapper typing-wrapper'):
                ui.html(
                    f'<div class="message-bubble typing-bubble" id="{message_id}">'
                    f'<span class="typing-dots">typing</span>'
                    f'</div>'
                )
        
        print(f"{Fore.YELLOW}[CHAT_MANAGER] Typing indicator added: {message_id}{Style.RESET_ALL}")
        return message_id
    
    def add_error_message(self, error_text: str) -> str:
        """
        Add an error message to the chat.
        
        Args:
            error_text: The error message text
            
        Returns:
            str: The message ID
        """
        message_id = f"error_msg_{self.message_counter}"
        self.message_counter += 1
        
        with self.chat_log:
            # REMOVED: .style(...)
            with ui.row().classes('chat-message-wrapper darwin-wrapper'):
                ui.html(
                    f'<div class="message-bubble error-bubble" id="{message_id}">'
                    f'<strong>⚠️ Error:</strong> {error_text}'
                    f'</div>'
                )
        
        print(f"{Fore.RED}[CHAT_MANAGER] Error message added: {message_id}{Style.RESET_ALL}")
        return message_id
    
    def add_system_message(self, text: str) -> str:
        """
        Add a system message to the chat (centered, neutral styling).
        
        Args:
            text: The system message text
            
        Returns:
            str: The message ID
        """
        message_id = f"system_msg_{self.message_counter}"
        self.message_counter += 1
        
        with self.chat_log:
            # REMOVED: .style(...)
            with ui.row().classes('chat-message-wrapper system-wrapper'):
                ui.html(
                    f'<div class="message-bubble system-bubble" id="{message_id}">'
                    f'{text}'
                    f'</div>'
                )
        
        print(f"{Fore.MAGENTA}[CHAT_MANAGER] System message added: {message_id}{Style.RESET_ALL}")
        return message_id
    
    def clear_chat(self):
        """Clear all messages from the chat."""
        self.chat_log.clear()
        self.message_counter = 0
        print(f"{Fore.YELLOW}[CHAT_MANAGER] Chat cleared{Style.RESET_ALL}")
    
    def get_message_count(self) -> int:
        """Get the total number of messages created."""
        return self.message_counter