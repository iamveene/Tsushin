"""
Migration: Fix nuclei tool prompt and parameter to prevent URL contamination.

This migration updates the existing nuclei tool configuration to:
1. Update the system prompt to emphasize using the user's current request
2. Remove the default URL from the url parameter
3. Update the parameter description

Run with: docker compose exec backend python migrations/fix_nuclei_tool_prompt.py
"""

from sqlalchemy import create_engine, text
import os

def run_migration():
    """Apply the nuclei tool fix migration."""

    db_path = os.environ.get("DATABASE_URL", "sqlite:///data/agent.db")
    engine = create_engine(db_path)

    new_system_prompt = (
        "You are a security analyst assistant with access to the Nuclei vulnerability scanner. "
        "Nuclei is a fast, template-based vulnerability scanner that can detect security issues. "
        "CRITICAL: Always extract the URL from the user's CURRENT message. "
        "NEVER use URLs from previous conversations or memory. "
        "When the user asks to scan a URL, use the 'scan_url' command with the exact URL they specified."
    )

    new_url_description = "Target URL to scan - MUST be extracted from user's current request, never from memory"

    with engine.connect() as conn:
        # Check if nuclei tool exists
        result = conn.execute(text("SELECT id FROM custom_tools WHERE name = 'nuclei'"))
        tool_row = result.fetchone()

        if not tool_row:
            print("Nuclei tool not found - nothing to migrate")
            return

        tool_id = tool_row[0]
        print(f"Found nuclei tool with id={tool_id}")

        # Update the tool's system prompt
        conn.execute(
            text("UPDATE custom_tools SET system_prompt = :prompt WHERE id = :tool_id"),
            {"prompt": new_system_prompt, "tool_id": tool_id}
        )
        print("✓ Updated nuclei system prompt")

        # Find all commands with url parameter and update them
        result = conn.execute(
            text("SELECT id, command_name FROM custom_tool_commands WHERE tool_id = :tool_id"),
            {"tool_id": tool_id}
        )
        commands = result.fetchall()

        for command_row in commands:
            command_id = command_row[0]
            command_name = command_row[1]

            # Check if url parameter exists for this command
            check_result = conn.execute(
                text("SELECT id FROM custom_tool_parameters WHERE command_id = :command_id AND parameter_name = 'url'"),
                {"command_id": command_id}
            )
            url_param_exists = check_result.fetchone() is not None

            if url_param_exists:
                # Update the url parameter - remove default and update description
                update_result = conn.execute(
                    text("""
                        UPDATE custom_tool_parameters
                        SET default_value = NULL, description = :description
                        WHERE command_id = :command_id AND parameter_name = 'url'
                    """),
                    {"description": new_url_description, "command_id": command_id}
                )
                if update_result.rowcount > 0:
                    print(f"✓ Updated url parameter for command '{command_name}'")
            else:
                # Check if command template uses {url} placeholder
                template_result = conn.execute(
                    text("SELECT command_template FROM custom_tool_commands WHERE id = :command_id"),
                    {"command_id": command_id}
                )
                template_row = template_result.fetchone()
                if template_row and '{url}' in template_row[0]:
                    # Add missing url parameter
                    conn.execute(
                        text("""
                            INSERT INTO custom_tool_parameters (command_id, parameter_name, is_mandatory, default_value, description)
                            VALUES (:command_id, 'url', 1, NULL, :description)
                        """),
                        {"command_id": command_id, "description": new_url_description}
                    )
                    print(f"✓ Added missing url parameter for command '{command_name}'")

        if not commands:
            print("⚠ No commands found for nuclei tool")

        conn.commit()
        print("\n✅ Migration completed successfully!")


if __name__ == "__main__":
    run_migration()
