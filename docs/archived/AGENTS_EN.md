# AGENTS_EN.md

This file contains guidelines and commands for agentic coding agents working in the ptest repository.

## Build/Lint/Test Commands

### Installation and Setup
```bash
# Install in development mode
pip install -e .

# Install using uv (if available)
uv pip install -e .

# Alternative setup
python setup.py install
```

### Running the Framework
```bash
# Main CLI commands
ptest --help                    # Show help
p --help                       # Short alias for ptest

# Environment management
ptest init --path ./test_env   # Initialize test environment
p init --path ./test_env       # Same with short alias

# Object management
ptest obj install mysql my_db --version 9.9.9
ptest obj start my_db
ptest obj stop my_db
ptest obj list
p obj status                    # Show object status

# Test case management
ptest case add test1 '{"type": "api", "endpoint": "/test"}'
ptest case run test1            # Run single test case
ptest case run all              # Run all test cases
p run all                       # Short alias

# Reports
ptest report --format html     # Generate HTML report
ptest report --format json     # Generate JSON report

# Status
ptest status                    # Show framework status
p status                       # Short alias
```

### Running Single Tests
```bash
# Run a specific test case by ID
ptest case run <test_case_id>

# Alternative using run command
p run <test_case_id>

# Run failed tests only
p run failed
```

### Development Commands
```bash
# No formal test suite exists yet - tests are run through the framework itself
# To test the framework, create a test environment and run test cases:
p init --path ./dev_test
p case add dev_test '{"type": "unit", "description": "Framework test"}'
p case run dev_test
```

## Code Style Guidelines

### Import Organization
- Use `isort`-style imports: standard library → third-party → local imports
- Group imports with blank lines between groups
- Use absolute imports for local modules: `from .utils import setup_logging`
- Avoid wildcard imports (`from module import *`)

```python
# Standard library imports
import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

# Third-party imports (none currently used)

# Local imports
from .utils import setup_logging
from .config import load_config
```

### Type Hints
- Use type hints consistently across all function signatures and class attributes
- Use `from typing import` for complex types: `Dict`, `List`, `Optional`, `Union`
- Use return type annotations: `-> str`, `-> bool`, `-> None`
- For class attributes, use type annotations in the class body

```python
def install(self, params: Dict[str, Any] = {}) -> str:
    """Install object with given parameters."""
    pass

class Example:
    name: str
    status: str = 'stopped'
```

### Naming Conventions
- **Classes**: PascalCase (e.g., `ObjectManager`, `BaseManagedObject`)
- **Functions/Methods**: snake_case (e.g., `init_environment`, `setup_logging`)
- **Variables**: snake_case (e.g., `test_path`, `config_file`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `DEFAULT_CONFIG`, `MAX_TIMEOUT`)
- **Private methods**: prefix with underscore (e.g., `_validate_params`)

### Error Handling
- Use specific exception types: `ValueError`, `FileNotFoundError`, `json.JSONDecodeError`
- Return formatted error messages with ✗ prefix for failures
- Return formatted success messages with ✓ prefix for success
- Use try/except blocks for external operations (file I/O, subprocess)

```python
try:
    data = json.loads(args.data)
except json.JSONDecodeError:
    print_colored("✗ Invalid JSON format for test case data", 91)
    return

if name not in self.objects:
    return f"✗ Object '{name}' does not exist"
```

### Logging
- Use the framework's logger: `self.env_manager.logger.info()`
- Log important operations: object lifecycle, test execution, errors
- Use appropriate log levels: `INFO` for normal operations, `ERROR` for failures

### File Structure
- Follow the existing modular structure with separate managers for different concerns
- Use `__init__.py` files for package imports
- Keep related functionality in the same module (e.g., all object management in `objects/`)

### Docstrings and Comments
- Use docstrings for all classes and public methods
- Follow the existing docstring style (simple description)
- Use TODO comments for future improvements with specific details

```python
def install(self, params: Dict[str, Any] = {}) -> str:
    """Install the object with given parameters."""
    # TODO: Add validation for parameters
    pass
```

### Color Output
- Use the utility functions for colored terminal output
- Import from `utils`: `get_colored_text`, `print_colored`
- Use consistent color codes: 92 (green) for success, 91 (red) for errors, 94 (blue) for info

```python
from ..utils import get_colored_text, print_colored

print_colored(f"✓ Test case '{case_id}' added", 92)
result = f"{get_colored_text('PASSED', 92)} ({duration:.2f}s)"
```

### Configuration
- Use the centralized configuration system in `config.py`
- Load configuration using `load_config()` function
- Use `DEFAULT_CONFIG` for default values
- Store configuration in JSON format

### CLI Structure
- Follow the existing CLI pattern with subcommands
- Use `argparse` for command-line parsing
- Provide helpful descriptions and examples
- Support both long (`ptest`) and short (`p`) command aliases

### Testing Patterns
- The framework itself is the testing tool - tests are managed through `CaseManager`
- Test cases are identified by string IDs
- Test results are tracked through `TestCaseResult` objects
- Use the existing simulation pattern for test execution until real test logic is implemented

### Chinese Comments
- The codebase contains Chinese comments and variable names
- Maintain consistency with existing Chinese documentation
- Use Chinese for user-facing messages and descriptions where already established

## Development Notes

- The framework uses a modular architecture with separate managers for different concerns
- Environment management is handled by `EnvironmentManager`
- Objects are managed through `ObjectManager` with specific object types
- Test cases are managed by `CaseManager` with result tracking
- Reports are generated by `ReportGenerator` in HTML or JSON formats
- The codebase is in active development with many TODOs for future improvements
- Current test execution is simulated - real test logic implementation is pending