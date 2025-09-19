"""Interactive prompts for test chart creation."""
from __future__ import annotations

import curses
from dataclasses import dataclass
from typing import Optional

from .interactive import _CheckboxPrompt, _Option, _run_prompt


@dataclass
class TestChartOptions:
    """Options for test chart creation."""
    create_test_chart: bool = False
    test_suffix: str = "test"
    test_chart_dir: Optional[str] = None
    use_reduced_resources: bool = True
    single_replica: bool = True
    test_storage_size: str = "1Gi"


def ask_test_chart_creation(release_name: str, output_dir: str) -> TestChartOptions:
    """
    Ask user if they want to create a test chart with interactive prompts.
    
    Args:
        release_name: Base release name
        output_dir: Base output directory
        
    Returns:
        TestChartOptions with user selections
    """
    options = TestChartOptions()
    
    # First, ask if they want to create a test chart
    create_test = _ask_yes_no(
        f"Create a test chart for '{release_name}'?",
        "This will generate an additional chart with -test suffixed resource names for testing",
        default=False
    )
    
    if not create_test:
        return options
    
    options.create_test_chart = True
    
    # Ask for test suffix
    options.test_suffix = _ask_text_input(
        "Test suffix for resource names",
        f"Resources will be named like '{release_name}-[suffix]'",
        default="test",
        max_length=20
    )
    
    # Ask for test chart directory
    default_test_dir = f"{output_dir}-{options.test_suffix}"
    options.test_chart_dir = _ask_text_input(
        "Test chart output directory",
        "Directory where the test chart will be created",
        default=default_test_dir,
        max_length=100
    )
    
    # Ask about resource modifications
    modifications = _ask_test_modifications()
    options.use_reduced_resources = modifications["reduce_resources"]
    options.single_replica = modifications["single_replica"]
    
    if modifications["custom_storage"]:
        options.test_storage_size = _ask_text_input(
            "Test storage size",
            "Storage size for PVCs in test environment",
            default="1Gi",
            max_length=10
        )
    
    return options


def _ask_yes_no(title: str, description: str, default: bool = False) -> bool:
    """Ask a yes/no question with curses interface."""
    options = [
        _Option(label="Yes", value="yes"),
        _Option(label="No", value="no"),
    ]
    
    default_value = "yes" if default else "no"
    
    prompt = _CheckboxPrompt(
        f"{title}\\n{description}",
        options,
        default=[default_value],
        minimum=1
    )
    
    result = _run_prompt(prompt)
    return "yes" in result


def _ask_text_input(
    title: str, 
    description: str, 
    default: str = "", 
    max_length: int = 50
) -> str:
    """Ask for text input using a simple curses interface."""
    def input_screen(stdscr):
        curses.use_default_colors()
        stdscr.keypad(True)
        try:
            curses.curs_set(1)  # Show cursor
        except curses.error:
            pass
        
        input_text = default
        cursor_pos = len(input_text)
        
        while True:
            stdscr.erase()
            max_y, max_x = stdscr.getmaxyx()
            
            # Display title and description
            stdscr.addstr(0, 0, title[:max_x-1], curses.A_BOLD)
            stdscr.addstr(1, 0, description[:max_x-1], curses.A_DIM)
            
            # Display input prompt
            prompt_line = 3
            stdscr.addstr(prompt_line, 0, "Enter value (Enter to confirm, Esc to use default):", curses.A_NORMAL)
            
            # Display input box
            input_line = prompt_line + 1
            box_width = min(max_length + 2, max_x - 2)
            input_box = f"[{input_text:<{box_width-2}}]"
            stdscr.addstr(input_line, 0, input_box[:max_x-1])
            
            # Position cursor
            cursor_x = min(cursor_pos + 1, box_width - 1)
            stdscr.move(input_line, cursor_x)
            
            # Display current default
            if default:
                stdscr.addstr(input_line + 2, 0, f"Default: {default}", curses.A_DIM)
            
            stdscr.refresh()
            
            key = stdscr.getch()
            
            if key in (curses.KEY_ENTER, 10, 13):
                return input_text or default
            elif key == 27:  # Esc
                return default
            elif key == curses.KEY_BACKSPACE or key == 127:
                if cursor_pos > 0:
                    input_text = input_text[:cursor_pos-1] + input_text[cursor_pos:]
                    cursor_pos -= 1
            elif key == curses.KEY_LEFT:
                cursor_pos = max(0, cursor_pos - 1)
            elif key == curses.KEY_RIGHT:
                cursor_pos = min(len(input_text), cursor_pos + 1)
            elif key == curses.KEY_HOME:
                cursor_pos = 0
            elif key == curses.KEY_END:
                cursor_pos = len(input_text)
            elif 32 <= key <= 126:  # Printable characters
                if len(input_text) < max_length:
                    input_text = input_text[:cursor_pos] + chr(key) + input_text[cursor_pos:]
                    cursor_pos += 1
    
    return curses.wrapper(input_screen)


def _ask_test_modifications() -> dict:
    """Ask about test environment modifications."""
    title = "Test Environment Modifications"
    description = "Select modifications to apply to test resources:"
    
    options = [
        _Option(label="Reduce CPU/memory resources for test environment", value="reduce_resources"),
        _Option(label="Limit deployments to single replica", value="single_replica"),
        _Option(label="Use smaller storage sizes for PVCs", value="custom_storage"),
    ]
    
    prompt = _CheckboxPrompt(
        f"{title}\\n{description}",
        options,
        default=["reduce_resources", "single_replica"],  # Default selections
    )
    
    selected = _run_prompt(prompt)
    
    return {
        "reduce_resources": "reduce_resources" in selected,
        "single_replica": "single_replica" in selected,
        "custom_storage": "custom_storage" in selected,
    }


class TestChartPrompt:
    """Interactive prompt manager for test chart options."""
    
    @staticmethod
    def should_create_test_chart(release_name: str) -> bool:
        """Simple yes/no prompt for test chart creation."""
        return _ask_yes_no(
            f"Create test chart for '{release_name}'?",
            "Generate additional chart with -test suffixed names for safe testing",
            default=False
        )
    
    @staticmethod
    def get_test_suffix(default: str = "test") -> str:
        """Get custom test suffix from user."""
        return _ask_text_input(
            "Test suffix",
            "Suffix to append to resource names (e.g., 'staging', 'dev', 'test')",
            default=default,
            max_length=20
        )
    
    @staticmethod
    def get_test_modifications() -> dict:
        """Get test environment modifications."""
        return _ask_test_modifications()


def prompt_for_test_chart_options(
    release_name: str,
    output_dir: str,
    interactive: bool = True
) -> TestChartOptions:
    """
    Main function to prompt for test chart options.
    
    Args:
        release_name: Base release name
        output_dir: Base output directory  
        interactive: Whether to use interactive prompts
        
    Returns:
        TestChartOptions with user selections
    """
    if not interactive:
        # Non-interactive mode - return defaults
        return TestChartOptions()
    
    try:
        return ask_test_chart_creation(release_name, output_dir)
    except KeyboardInterrupt:
        print("\\nTest chart creation cancelled by user")
        return TestChartOptions()
    except Exception:
        print("\\nFailed to get test chart options, skipping test chart creation")
        return TestChartOptions()