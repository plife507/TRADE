"""
src/cli/art_stylesheet.py
Master stylesheet for Bitcoin/Crypto Cash-themed CLI art wrapper.

This file contains ALL art definitions, colors, ASCII art, and wrapper functions.
All other Python files just import and call these - keeping them clean and minimal.

Theme: $100 bill aesthetics with Bitcoin/Bybit branding
Colors: Gold, Green, Blue (like US currency)
"""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.table import Table
import shutil


# =============================================================================
# COLOR DEFINITIONS - $100 Bill Theme
# =============================================================================

class BillArtColors:
    """Color palette inspired by $100 bills and crypto."""
    
    # Gold tones (like currency thread/seals)
    GOLD_BRIGHT = "#FFD700"
    GOLD_DARK = "#D4AF37"
    GOLD_METALLIC = "#CFB53B"
    
    # Green tones (like US currency)
    GREEN_BRIGHT = "#00C853"
    GREEN_DARK = "#2E7D32"
    GREEN_MONEY = "#85bb65"
    GREEN_BILL = "#3D9140"
    
    # Blue tones (security features/Bybit brand)
    BLUE_BRIGHT = "#1976D2"
    BLUE_DARK = "#0D47A1"
    BLUE_BYBIT = "#F7A600"  # Bybit's actual orange-gold
    
    # Accent colors
    CREAM = "#FFFDD0"
    PAPER = "#F5F5DC"
    
    # Semantic mappings for art
    BORDER = GOLD_BRIGHT
    BITCOIN = GREEN_BRIGHT
    DOLLAR = GREEN_MONEY
    LOGO = BLUE_BRIGHT
    ACCENT = GOLD_METALLIC


# =============================================================================
# DYNAMIC WIDTH HELPERS
# =============================================================================

def get_terminal_width() -> int:
    """Get terminal width, with a sensible default."""
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return 80


def make_border(char: str = "═", width: int = None, left: str = "", right: str = "") -> str:
    """Create a border line that fits the terminal width."""
    if width is None:
        width = min(get_terminal_width() - 4, 90)  # Leave margin, cap at 90
    
    inner_width = width - len(left) - len(right)
    return f"{left}{char * inner_width}{right}"


def make_pattern_border(width: int = None) -> str:
    """Create a guilloché-style pattern border."""
    if width is None:
        width = min(get_terminal_width() - 4, 90)
    
    pattern = "░▒▓█▓▒░"
    repeats = (width - 6) // len(pattern)
    inner = (pattern * repeats)[:width - 6]
    return f"┃ {inner} ┃"


# =============================================================================
# ASCII ART DEFINITIONS
# =============================================================================

class BillArtDefinitions:
    """All ASCII art definitions in one centralized place."""
    
    # -------------------------------------------------------------------------
    # MAIN TRADE LOGO - Big ASCII Art for startup
    # -------------------------------------------------------------------------
    TRADE_LOGO = """
████████╗██████╗  █████╗ ██████╗ ███████╗
╚══██╔══╝██╔══██╗██╔══██╗██╔══██╗██╔════╝
   ██║   ██████╔╝███████║██║  ██║█████╗  
   ██║   ██╔══██╗██╔══██║██║  ██║██╔══╝  
   ██║   ██║  ██║██║  ██║██████╔╝███████╗
   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚══════╝"""

    # -------------------------------------------------------------------------
    # BYBIT LOGO - ASCII Art
    # -------------------------------------------------------------------------
    BYBIT_LOGO = """
██████╗ ██╗   ██╗██████╗ ██╗████████╗
██╔══██╗╚██╗ ██╔╝██╔══██╗██║╚══██╔══╝
██████╔╝ ╚████╔╝ ██████╔╝██║   ██║   
██╔══██╗  ╚██╔╝  ██╔══██╗██║   ██║   
██████╔╝   ██║   ██████╔╝██║   ██║   
╚═════╝    ╚═╝   ╚═════╝ ╚═╝   ╚═╝"""

    BYBIT_LOGO_SMALL = "【 BYBIT 】"
    
    # -------------------------------------------------------------------------
    # UNIFIED TRADING BOT - Combined Logo
    # -------------------------------------------------------------------------
    UNIFIED_HEADER = """
╔══════════════════════════════════════════════════════════════════════════════╗
║  ₿                    UNIFIED TRADING ACCOUNT                            ₿   ║
║                         Crypto Futures CLI                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝"""

    # -------------------------------------------------------------------------
    # MONEY/CASH DECORATIONS
    # -------------------------------------------------------------------------
    CASH_BORDER_TOP = """
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  💵 ░▒▓█▓▒░  ₿  ░▒▓█▓▒░  $  ░▒▓█▓▒░  ₿  ░▒▓█▓▒░  $  ░▒▓█▓▒░  ₿  ░▒▓█▓▒░ 💵  ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"""
    
    # -------------------------------------------------------------------------
    # BITCOIN SYMBOLS
    # -------------------------------------------------------------------------
    BITCOIN_SYMBOL = "₿"
    BITCOIN_ICON = "[₿]"
    BITCOIN_BADGE = "◈₿◈"
    
    # -------------------------------------------------------------------------
    # DOLLAR/MONEY SYMBOLS  
    # -------------------------------------------------------------------------
    DOLLAR_SYMBOL = "$"
    DOLLAR_ICON = "[$]"
    DOLLAR_BADGE = "◈$◈"
    
    # -------------------------------------------------------------------------
    # CORNER PIECES - Currency style
    # -------------------------------------------------------------------------
    CORNER_TL = "╔"
    CORNER_TR = "╗"
    CORNER_BL = "╚"
    CORNER_BR = "╝"
    
    CORNER_TL_FANCY = "┏━◈"
    CORNER_TR_FANCY = "◈━┓"
    CORNER_BL_FANCY = "┗━◈"
    CORNER_BR_FANCY = "◈━┛"
    
    # -------------------------------------------------------------------------
    # FLOURISH ELEMENTS
    # -------------------------------------------------------------------------
    FLOURISH_LEFT = "◄═══"
    FLOURISH_RIGHT = "═══►"
    FLOURISH_CENTER = "═══◆═══"
    
    # Serial number style
    SERIAL_LEFT = "【"
    SERIAL_RIGHT = "】"
    
    # -------------------------------------------------------------------------
    # FOOTER BRANDING (shorter, centered)
    # -------------------------------------------------------------------------
    FOOTER_BRAND = "◈ TRADE × BYBIT ◈"
    FOOTER_CRYPTO = "₿ Crypto Futures Trading ₿"


# =============================================================================
# ART WRAPPER CLASS - Renders art with colors
# =============================================================================

class BillArtWrapper:
    """
    Wrapper class that renders art elements with proper colors.
    All other files just call these methods - no art logic elsewhere.
    """
    
    _console = Console()
    _enabled = True  # Can be toggled off if needed
    
    @classmethod
    def set_enabled(cls, enabled: bool):
        """Toggle art wrapper on/off."""
        cls._enabled = enabled
    
    @classmethod
    def is_enabled(cls) -> bool:
        """Check if art wrapper is enabled."""
        return cls._enabled
    
    @classmethod
    def _get_width(cls) -> int:
        """Get usable width for borders."""
        return min(cls._console.width or 80, 100) - 4
    
    # -------------------------------------------------------------------------
    # STARTUP SCREEN ART
    # -------------------------------------------------------------------------
    @classmethod
    def _center_ascii_block(cls, ascii_art: str, color: str) -> str:
        """
        Center a multi-line ASCII art block by padding all lines to equal width.
        This ensures proper alignment when centered in terminal.
        """
        lines = ascii_art.strip().split('\n')
        max_width = max(len(line) for line in lines)
        
        # Pad all lines to the same width (centered within the block)
        centered_lines = []
        for line in lines:
            padding = max_width - len(line)
            left_pad = padding // 2
            right_pad = padding - left_pad
            centered_line = ' ' * left_pad + line + ' ' * right_pad
            centered_lines.append(f"[bold {color}]{centered_line}[/]")
        
        return '\n'.join(centered_lines)
    
    @classmethod
    def print_startup_art(cls):
        """Print the big startup screen with TRADE logo and Bybit branding."""
        if not cls._enabled:
            return
        
        # Use fixed width for consistent borders (wider for startup)
        border_width = 50
        
        # Top border - centered
        top_border = f"╔═₿═{'═' * (border_width - 8)}═₿═╗"
        cls._console.print(Align.center(f"[{BillArtColors.GOLD_BRIGHT}]{top_border}[/]"))
        cls._console.print()
        
        # Print TRADE logo - center the entire block
        trade_block = cls._center_ascii_block(BillArtDefinitions.TRADE_LOGO, BillArtColors.GREEN_BRIGHT)
        trade_text = Text.from_markup(trade_block)
        cls._console.print(Align.center(trade_text))
        
        cls._console.print()
        
        # Divider with Bitcoin - centered
        divider = f"[{BillArtColors.GOLD_METALLIC}]──────────◈─₿─◈──────────[/]"
        cls._console.print(Align.center(divider))
        
        cls._console.print()
        
        # Print BYBIT logo - center the entire block
        bybit_block = cls._center_ascii_block(BillArtDefinitions.BYBIT_LOGO, BillArtColors.BLUE_BRIGHT)
        bybit_text = Text.from_markup(bybit_block)
        cls._console.print(Align.center(bybit_text))
        
        cls._console.print()
        
        # Unified Trading Account tagline - centered
        cls._console.print(Align.center(f"[bold {BillArtColors.GOLD_BRIGHT}]═══════ UNIFIED TRADING ACCOUNT ═══════[/]"))
        cls._console.print(Align.center(f"[{BillArtColors.GREEN_MONEY}]💵 Crypto Futures CLI 💵[/]"))
        
        cls._console.print()
        
        # Bottom guilloché pattern - fixed width, centered
        pattern_unit = "░▒▓█▓▒░"
        pattern_repeats = 5
        pattern = pattern_unit * pattern_repeats
        pattern_line = f"┃  ₿  {pattern}  $  ┃"
        cls._console.print(Align.center(f"[{BillArtColors.GOLD_DARK}]{pattern_line}[/]"))
        
        # Bottom border - centered
        bottom_border = f"╚═$═{'═' * (border_width - 8)}═$═╝"
        cls._console.print(Align.center(f"[{BillArtColors.GOLD_BRIGHT}]{bottom_border}[/]"))
        cls._console.print()
    
    @classmethod
    def print_mini_logo(cls):
        """Print a smaller version of the logo for menu headers."""
        if not cls._enabled:
            return
        
        # Compact header - build as single block for proper centering
        mini_logo = (
            f"[bold {BillArtColors.GREEN_BRIGHT}]╔═══ TRADE ═══╗[/]\n"
            f"[bold {BillArtColors.BLUE_BRIGHT}]║    BYBIT    ║[/]\n"
            f"[bold {BillArtColors.GOLD_BRIGHT}]╚═════════════╝[/]"
        )
        cls._console.print(Align.center(Text.from_markup(mini_logo)))
    
    # -------------------------------------------------------------------------
    # HEADER WRAPPER
    # -------------------------------------------------------------------------
    @classmethod
    def print_header_art(cls, is_demo: bool = True):
        """
        Print the decorated header with $100 bill styling.
        Call this BEFORE print_header() content.
        """
        if not cls._enabled:
            return
        
        # Fixed-width centered border
        border_width = 70
        border = f"═₿═{'═' * (border_width - 6)}═₿═"
        cls._console.print(Align.center(f"[{BillArtColors.GOLD_BRIGHT}]{border}[/]"))
    
    @classmethod
    def print_header_art_bottom(cls, is_demo: bool = True):
        """
        Print the bottom header decoration.
        Call this AFTER print_header() content.
        """
        if not cls._enabled:
            return
        
        # Fixed-width centered border
        border_width = 70
        border = f"═$═{'═' * (border_width - 6)}═$═"
        cls._console.print(Align.center(f"[{BillArtColors.GOLD_BRIGHT}]{border}[/]"))
    
    @classmethod
    def get_decorated_title(cls, is_demo: bool = True) -> Panel:
        """
        Get the main title panel with $100 bill decoration.
        Simplified for better display.
        """
        # Color scheme based on mode
        title_color = BillArtColors.GREEN_BRIGHT if is_demo else BillArtColors.GOLD_BRIGHT
        border_color = BillArtColors.GOLD_DARK if is_demo else BillArtColors.GOLD_BRIGHT
        bybit_color = BillArtColors.BLUE_BRIGHT
        
        # Build the title content - simplified for terminal compatibility
        title_lines = []
        
        # Bybit branding
        title_lines.append(f"[bold {bybit_color}]━━━━━━━━ ◈ POWERED BY BYBIT ◈ ━━━━━━━━[/]")
        
        content = "\n".join(title_lines)
        
        return Panel(
            Align.center(Text.from_markup(content)),
            border_style=border_color,
            padding=(0, 1),
            title=f"[bold {BillArtColors.BITCOIN}]₿[/] [bold {BillArtColors.GOLD_BRIGHT}]UNIFIED TRADING ACCOUNT[/] [bold {BillArtColors.BITCOIN}]₿[/]",
            subtitle=f"[{BillArtColors.GREEN_MONEY}]💵 Crypto Futures CLI 💵[/]",
        )
    
    # -------------------------------------------------------------------------
    # MENU WRAPPER
    # -------------------------------------------------------------------------
    @classmethod
    def print_menu_top(cls):
        """Print decorative top border for menus."""
        if not cls._enabled:
            return
        
        # Fixed-width centered border (looks cleaner than dynamic)
        border_width = 70
        pattern_unit = "░▒▓█▓▒░"
        pattern_width = border_width - 14
        repeats = pattern_width // len(pattern_unit)
        pattern = pattern_unit * repeats
        
        top_line = f"┏━◈{'━' * (border_width - 8)}◈━┓"
        pattern_line = f"┃  ₿  {pattern}  ₿  ┃"
        
        cls._console.print(Align.center(f"[{BillArtColors.GOLD_DARK}]{top_line}[/]"))
        cls._console.print(Align.center(f"[{BillArtColors.GOLD_DARK}]{pattern_line}[/]"))
    
    @classmethod
    def print_menu_bottom(cls):
        """Print decorative bottom border for menus."""
        if not cls._enabled:
            return
        
        # Fixed-width centered border (matches top)
        border_width = 70
        pattern_unit = "░▒▓█▓▒░"
        pattern_width = border_width - 14
        repeats = pattern_width // len(pattern_unit)
        pattern = pattern_unit * repeats
        
        pattern_line = f"┃  $  {pattern}  $  ┃"
        bottom_line = f"┗━◈{'━' * (border_width - 8)}◈━┛"
        
        cls._console.print(Align.center(f"[{BillArtColors.GOLD_DARK}]{pattern_line}[/]"))
        cls._console.print(Align.center(f"[{BillArtColors.GOLD_DARK}]{bottom_line}[/]"))
    
    @classmethod
    def get_menu_panel(cls, content, title: str = "MENU", is_main: bool = False) -> Panel:
        """
        Wrap menu content in a $100 bill styled panel.
        
        Args:
            content: The menu content (Table, Text, etc.)
            title: Panel title
            is_main: If True, use more elaborate styling
        """
        border_color = BillArtColors.GOLD_BRIGHT if is_main else BillArtColors.GOLD_DARK
        
        # Create title with Bitcoin symbols
        styled_title = f"[bold {BillArtColors.BITCOIN}]₿[/] [bold {BillArtColors.GOLD_BRIGHT}]{title}[/] [bold {BillArtColors.BITCOIN}]₿[/]"
        
        # Create subtitle with dollar signs
        styled_subtitle = f"[{BillArtColors.GREEN_MONEY}]◈ $ ◈[/]"
        
        return Panel(
            Align.center(content),
            title=styled_title,
            subtitle=styled_subtitle,
            border_style=border_color,
            padding=(1, 2),
        )
    
    # -------------------------------------------------------------------------
    # SECTION WRAPPERS
    # -------------------------------------------------------------------------
    @classmethod
    def print_section_divider(cls, title: str = ""):
        """Print a decorative section divider."""
        if not cls._enabled:
            cls._console.print()
            return
        
        width = cls._get_width()
        if title:
            # Centered title in divider
            side_len = (width - len(title) - 6) // 2
            left_pad = "═" * side_len
            right_pad = "═" * side_len
            cls._console.print(f"[{BillArtColors.GOLD_METALLIC}]{left_pad} ◈ {title} ◈ {right_pad}[/]")
        else:
            border = make_border("◈━", width // 2)
            cls._console.print(f"[{BillArtColors.GOLD_DARK}]{border}[/]")
    
    @classmethod
    def get_result_panel(cls, content, success: bool = True) -> Panel:
        """Wrap result content in themed panel."""
        if success:
            border_color = BillArtColors.GREEN_BRIGHT
            title = f"[bold {BillArtColors.GREEN_BRIGHT}]✓ SUCCESS[/]"
        else:
            border_color = "#ff003c"  # Keep red for errors
            title = "[bold #ff003c]✗ ERROR[/]"
        
        return Panel(
            content,
            title=title,
            border_style=border_color,
            padding=(0, 1),
        )
    
    # -------------------------------------------------------------------------
    # DECORATIVE ELEMENTS
    # -------------------------------------------------------------------------
    @classmethod
    def print_crypto_flourish(cls):
        """Print a small crypto-themed flourish."""
        if not cls._enabled:
            return
        flourish = f"[{BillArtColors.GOLD_METALLIC}]◄═══[/] [{BillArtColors.BITCOIN}]₿[/] [{BillArtColors.GOLD_METALLIC}]═══►[/]"
        cls._console.print(Align.center(flourish))
    
    @classmethod
    def print_bybit_badge(cls):
        """Print a small Bybit brand badge."""
        if not cls._enabled:
            return
        badge = f"[{BillArtColors.GOLD_DARK}]【[/][bold {BillArtColors.BLUE_BRIGHT}]BYBIT[/][{BillArtColors.GOLD_DARK}]】[/]"
        cls._console.print(Align.center(badge))
    
    @classmethod  
    def get_status_badge(cls, text: str, badge_type: str = "info") -> str:
        """
        Get a themed status badge string.
        
        Args:
            text: Badge text
            badge_type: 'success', 'warning', 'error', 'info', 'gold'
        """
        color_map = {
            "success": BillArtColors.GREEN_BRIGHT,
            "warning": BillArtColors.GOLD_BRIGHT,
            "error": "#ff003c",
            "info": BillArtColors.BLUE_BRIGHT,
            "gold": BillArtColors.GOLD_METALLIC,
        }
        color = color_map.get(badge_type, BillArtColors.GOLD_DARK)
        
        return f"[bold {color}]▐[/][black on {color}] {text} [/][bold {color}]▌[/]"
    
    @classmethod
    def print_footer(cls):
        """Print the footer branding."""
        if not cls._enabled:
            return
        
        width = cls._get_width()
        # Centered footer brand
        brand = BillArtDefinitions.FOOTER_BRAND
        pad_len = (width - len(brand)) // 2
        pad = "═" * pad_len
        footer_line = f"{pad} {brand} {pad}"
        
        cls._console.print()
        cls._console.print(f"[{BillArtColors.GOLD_DARK}]{footer_line}[/]")


# =============================================================================
# CONVENIENCE FUNCTIONS - For easy imports
# =============================================================================

def print_bill_header(is_demo: bool = True):
    """Convenience function to print full decorated header."""
    BillArtWrapper.print_header_art(is_demo)

def print_bill_footer():
    """Convenience function to print footer."""
    BillArtWrapper.print_footer()

def get_bill_title_panel(is_demo: bool = True) -> Panel:
    """Convenience function to get title panel."""
    return BillArtWrapper.get_decorated_title(is_demo)

def get_bill_menu_panel(content, title: str = "MENU", is_main: bool = False) -> Panel:
    """Convenience function to get menu panel."""
    return BillArtWrapper.get_menu_panel(content, title, is_main)

def print_menu_borders(position: str = "top"):
    """Print menu border - 'top' or 'bottom'."""
    if position == "top":
        BillArtWrapper.print_menu_top()
    else:
        BillArtWrapper.print_menu_bottom()
