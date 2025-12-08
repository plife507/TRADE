"""
src/cli/styles.py
Centralized style definitions for the TRADE CLI.

Art wrapper and $100 bill theming is in art_stylesheet.py - import from there.
"""
from rich.style import Style
from rich.theme import Theme
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.table import Table
from typing import Optional, List, Dict, Any

# Import art wrapper for easy access (all art lives in art_stylesheet.py)
from .art_stylesheet import (
    BillArtWrapper,
    BillArtColors,
    BillArtDefinitions,
    get_bill_title_panel,
    get_bill_menu_panel,
    print_bill_header,
    print_bill_footer,
    print_menu_borders,
)

# Cyberpunk / Retro Game Theme Colors (keep for backwards compatibility)
class CLIColors:
    NEON_CYAN = "#00f3ff"
    NEON_MAGENTA = "#ff00ff" 
    NEON_GREEN = "#00ff41"
    NEON_YELLOW = "#fcee0a"
    NEON_RED = "#ff003c"
    DARK_BG = "#0a0a0a"
    DARK_PANEL = "#1a1a1a"
    DIM_TEXT = "#666666"
    
    # $100 Bill Theme Colors (from art_stylesheet)
    GOLD = BillArtColors.GOLD_BRIGHT
    GOLD_DARK = BillArtColors.GOLD_DARK
    DOLLAR_GREEN = BillArtColors.GREEN_MONEY
    RICH_GREEN = BillArtColors.GREEN_BRIGHT
    CRIMSON = BillArtColors.GOLD_BRIGHT  # Use gold instead of red for consistency
    SECURITY_BLUE = BillArtColors.BLUE_BRIGHT
    
    # Semantic mappings
    SUCCESS = NEON_GREEN
    ERROR = NEON_RED
    WARNING = NEON_YELLOW
    INFO = NEON_CYAN
    PRIMARY = NEON_CYAN
    SECONDARY = NEON_MAGENTA
    BORDER = BillArtColors.GOLD_DARK  # Use gold border for $100 bill theme

class CLIIcons:
    # System - trailing space for proper spacing
    SETTINGS = "⚙️ "
    QUIT = "🚪 "
    BACK = "🔙 "
    WARNING = "⚠️ "
    ERROR = "❌ "
    SUCCESS = "✅ "
    PANIC = "🚨 "
    
    # Crypto / Finance - trailing space for proper spacing
    WALLET = "💰 "
    BITCOIN = "₿ "
    DOLLAR = "💵 " 
    CHART_UP = "📈 "
    CHART_DOWN = "📉 "
    CANDLE = "📊 "
    BANK = "🏦 "
    LEDGER = "📒 "
    EXCHANGE = "💱 "
    LOCK = "🔒 "
    KEY = "🔑 "
    BAG = "💰 "
    COIN = "🪙 "
    
    # Actions - trailing space for proper spacing
    TRADE = "⚡ "       
    LIMIT = "⏱️ "       
    STOP = "🛑 "        
    LIQUIDITY = "💧 "   
    MINING = "⛏️ "      
    NETWORK = "🌐 "
    DATABASE = "💾 "    
    BOT = "🤖 "
    TARGET = "🎯 "

# ASCII Art Title
TITLE_ART = """
████████╗██████╗  █████╗ ██████╗ ███████╗
╚══██╔══╝██╔══██╗██╔══██╗██╔══██╗██╔════╝
   ██║   ██████╔╝███████║██║  ██║█████╗  
   ██║   ██╔══██╗██╔══██║██║  ██║██╔══╝  
   ██║   ██║  ██║██║  ██║██████╔╝███████╗
   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚══════╝
"""

class CLIStyles:
    """Helper methods for consistent CLI styling."""
    
    # Toggle to use $100 bill art wrapper (default: True)
    use_art_wrapper = True
    
    @staticmethod
    def get_title_panel(subtitle: str = None, is_demo: bool = True) -> Panel:
        """
        Create the main title panel with ASCII art.
        
        If use_art_wrapper is True, returns the $100 bill themed panel.
        Otherwise returns the original cyberpunk themed panel.
        """
        # Use $100 bill art wrapper if enabled
        if CLIStyles.use_art_wrapper:
            return get_bill_title_panel(is_demo)
        
        # Original cyberpunk theme (fallback)
        color = CLIColors.NEON_GREEN if is_demo else CLIColors.NEON_RED
        border_color = CLIColors.NEON_CYAN if is_demo else CLIColors.NEON_RED
        
        title_text = Text(TITLE_ART, style=f"bold {color}")
        
        return Panel(
            Align.center(title_text),
            subtitle=f"[{CLIColors.DIM_TEXT}]{subtitle}[/]" if subtitle else None,
            border_style=border_color,
            padding=(0, 2),
            title="[bold]BYBIT UNIFIED[/]",
            title_align="center"
        )

    @staticmethod
    def create_menu_table() -> Table:
        """Create a consistently styled menu table."""
        menu = Table(show_header=False, box=None, padding=(0, 1))
        menu.add_column("Key", style=f"bold {CLIColors.NEON_CYAN}", justify="right", width=4)
        menu.add_column("Action", style="bold white", width=25)
        menu.add_column("Description", style=CLIColors.DIM_TEXT, width=50)
        return menu

    @staticmethod
    def section_header(title: str, style: str = "bold cyan") -> Panel:
        """Create a section header panel."""
        return Panel(
            Align.center(f"[{style}]{title}[/]"),
            border_style="blue",
            padding=(0, 1)
        )

    @staticmethod
    def status_badge(text: str, color: str = "green") -> str:
        """Create a small status badge string."""
        # Map semantic colors to art wrapper colors if enabled
        if CLIStyles.use_art_wrapper:
            color_map = {
                "green": BillArtColors.GREEN_BRIGHT,
                "red": BillArtColors.GOLD_BRIGHT,  # Use gold instead of harsh red
                "yellow": BillArtColors.GOLD_METALLIC,
                "cyan": BillArtColors.BLUE_BRIGHT,
            }
            color = color_map.get(color, color)
        return f"[bold {color}]▐[/][black on {color}] {text} [/][bold {color}]▌[/]"
    
    @staticmethod
    def print_art_header():
        """Print the art header decoration (if enabled)."""
        if CLIStyles.use_art_wrapper:
            print_bill_header()
    
    @staticmethod
    def print_art_footer():
        """Print the art footer decoration (if enabled)."""
        if CLIStyles.use_art_wrapper:
            print_bill_footer()
    
    @staticmethod
    def get_menu_panel(content, title: str = "MENU", is_main: bool = False) -> Panel:
        """Get a styled menu panel (uses art wrapper if enabled)."""
        if CLIStyles.use_art_wrapper:
            return get_bill_menu_panel(content, title, is_main)
        # Fallback to basic panel
        return Panel(
            Align.center(content),
            title=f"[bold]{title}[/]",
            border_style=CLIColors.BORDER,
        )
