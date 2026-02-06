"""
Validate Custom Tools Installation and Configuration
Tests that all registered custom tools are properly installed and functional.
"""

import sys
import os
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Tuple

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def check_command_exists(command: str) -> bool:
    """Check if a command exists in PATH."""
    try:
        result = subprocess.run(
            ['which', command],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Error checking command '{command}': {e}")
        return False


def get_command_version(command: str, version_flag: str = '--version') -> str:
    """Get version of a command."""
    try:
        result = subprocess.run(
            [command, version_flag],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Return first line of output
            return result.stdout.split('\n')[0]
        return "Unknown version"
    except Exception as e:
        return f"Error: {e}"


def validate_command_tools(db_path: str = "./data/agent.db") -> Tuple[List[Dict], List[Dict]]:
    """
    Validate all command-type tools in the database.

    Returns:
        Tuple of (valid_tools, invalid_tools)
    """
    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    session = Session()

    valid_tools = []
    invalid_tools = []

    try:
        # Get all command-type tools
        result = session.execute(text("""
            SELECT
                ct.id,
                ct.name,
                ct.tool_type,
                ct.workspace_dir,
                ct.is_enabled,
                COUNT(DISTINCT ctc.id) as command_count
            FROM custom_tools ct
            LEFT JOIN custom_tool_commands ctc ON ct.id = ctc.tool_id
            WHERE ct.tool_type = 'command'
            GROUP BY ct.id, ct.name, ct.tool_type, ct.workspace_dir, ct.is_enabled
        """))

        tools = result.fetchall()

        logger.info(f"Found {len(tools)} command-type tools in database\n")

        for tool in tools:
            tool_id, name, tool_type, workspace_dir, is_enabled, command_count = tool

            logger.info(f"Validating tool: {name}")
            logger.info(f"  ID: {tool_id}")
            logger.info(f"  Type: {tool_type}")
            logger.info(f"  Workspace: {workspace_dir}")
            logger.info(f"  Enabled: {is_enabled}")
            logger.info(f"  Commands: {command_count}")

            # Check if command exists
            command_exists = check_command_exists(name)

            if command_exists:
                version = get_command_version(name)
                logger.info(f"  ✅ Command found: {version}")

                # Check workspace directory
                if workspace_dir:
                    workspace_path = Path(workspace_dir)
                    if workspace_path.exists():
                        logger.info(f"  ✅ Workspace exists")
                    else:
                        logger.warning(f"  ⚠️  Workspace does not exist: {workspace_dir}")

                valid_tools.append({
                    'id': tool_id,
                    'name': name,
                    'version': version,
                    'workspace_dir': workspace_dir,
                    'is_enabled': is_enabled,
                    'command_count': command_count
                })
            else:
                logger.error(f"  ❌ Command NOT found in PATH")
                invalid_tools.append({
                    'id': tool_id,
                    'name': name,
                    'workspace_dir': workspace_dir,
                    'is_enabled': is_enabled,
                    'command_count': command_count
                })

            logger.info("")

        return valid_tools, invalid_tools

    finally:
        session.close()


def validate_python_internal_tools(db_path: str = "./data/agent.db") -> Tuple[List[Dict], List[Dict]]:
    """
    Validate all python_internal-type tools in the database.

    Returns:
        Tuple of (valid_tools, invalid_tools)
    """
    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    session = Session()

    valid_tools = []
    invalid_tools = []

    try:
        # Get all python_internal tools
        result = session.execute(text("""
            SELECT
                ct.id,
                ct.name,
                ct.tool_type,
                ct.is_enabled
            FROM custom_tools ct
            WHERE ct.tool_type = 'python_internal'
        """))

        tools = result.fetchall()

        if tools:
            logger.info(f"\nFound {len(tools)} python_internal-type tools in database\n")

            for tool in tools:
                tool_id, name, tool_type, is_enabled = tool

                logger.info(f"Validating tool: {name}")
                logger.info(f"  ID: {tool_id}")
                logger.info(f"  Type: {tool_type}")
                logger.info(f"  Enabled: {is_enabled}")

                # Check if Python module exists
                module_path = backend_dir / "agent" / "tools" / f"{name}_tool.py"

                if module_path.exists():
                    logger.info(f"  ✅ Module found: {module_path}")
                    valid_tools.append({
                        'id': tool_id,
                        'name': name,
                        'module_path': str(module_path),
                        'is_enabled': is_enabled
                    })
                else:
                    logger.error(f"  ❌ Module NOT found: {module_path}")
                    invalid_tools.append({
                        'id': tool_id,
                        'name': name,
                        'expected_path': str(module_path),
                        'is_enabled': is_enabled
                    })

                logger.info("")

        return valid_tools, invalid_tools

    finally:
        session.close()


def print_summary(valid_cmd_tools: List[Dict], invalid_cmd_tools: List[Dict],
                 valid_py_tools: List[Dict], invalid_py_tools: List[Dict]):
    """Print validation summary."""
    logger.info("=" * 60)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 60)

    total_valid = len(valid_cmd_tools) + len(valid_py_tools)
    total_invalid = len(invalid_cmd_tools) + len(invalid_py_tools)
    total_tools = total_valid + total_invalid

    logger.info(f"\nCommand Tools:")
    logger.info(f"  ✅ Valid: {len(valid_cmd_tools)}")
    logger.info(f"  ❌ Invalid: {len(invalid_cmd_tools)}")

    logger.info(f"\nPython Internal Tools:")
    logger.info(f"  ✅ Valid: {len(valid_py_tools)}")
    logger.info(f"  ❌ Invalid: {len(invalid_py_tools)}")

    logger.info(f"\nOverall:")
    logger.info(f"  Total Tools: {total_tools}")
    logger.info(f"  Valid: {total_valid}")
    logger.info(f"  Invalid: {total_invalid}")

    if invalid_cmd_tools:
        logger.warning("\n⚠️  Missing command-line tools:")
        for tool in invalid_cmd_tools:
            logger.warning(f"  - {tool['name']} (ID: {tool['id']})")
        logger.warning("\nTo fix: Install missing tools in Docker container or system")

    if invalid_py_tools:
        logger.warning("\n⚠️  Missing Python modules:")
        for tool in invalid_py_tools:
            logger.warning(f"  - {tool['name']} (ID: {tool['id']})")
            logger.warning(f"    Expected: {tool['expected_path']}")
        logger.warning("\nTo fix: Create missing Python tool modules")

    logger.info("")

    return total_invalid == 0


def main():
    """Main validation function."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate custom tools installation")
    parser.add_argument("--db-path", default="./data/agent.db", help="Path to database")
    args = parser.parse_args()

    logger.info("Starting custom tools validation...\n")

    # Validate command tools
    valid_cmd_tools, invalid_cmd_tools = validate_command_tools(args.db_path)

    # Validate python_internal tools
    valid_py_tools, invalid_py_tools = validate_python_internal_tools(args.db_path)

    # Print summary
    all_valid = print_summary(valid_cmd_tools, invalid_cmd_tools, valid_py_tools, invalid_py_tools)

    if all_valid:
        logger.info("✅ All tools are properly configured!")
        return 0
    else:
        logger.error("❌ Some tools are missing or misconfigured")
        return 1


if __name__ == "__main__":
    sys.exit(main())
